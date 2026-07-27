"""Atomic budget reservation (docs/DATA_MODEL.md "Financial exposure").

Customer, agent and fleet scopes reserve together or none reserve
(invariant 4). Scopes are locked in deterministic (sorted) key order to
avoid deadlocks between concurrently reserving requests, then usage is
summed under that lock and compared against the effective cap before any
reservation row is written -- this is what gives zero-overshoot concurrency.
Velocity/count limits and policy_limits-table-driven caps are deferred to
Milestone 5; caps are read directly from the active policy version's config.
"""

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from .models import BudgetReservation, ReservationAllocation


class BudgetExceededError(Exception):
    def __init__(self, scope: str):
        self.scope = scope
        super().__init__(f"budget exceeded for scope {scope}")


def _scopes(config: dict, agent_token_subject: str, customer_id: str) -> list[tuple[str, str, int]]:
    budgets = config["budgets"]
    fleet_scope_id = config["fleet_budget_scope"]
    return sorted(
        [
            ("agent", agent_token_subject, budgets["agent_daily_cap_minor"]),
            ("customer", customer_id, budgets["customer_daily_cap_minor"]),
            ("fleet", fleet_scope_id, budgets["fleet_daily_cap_minor"]),
        ],
        key=lambda s: s[0],
    )


def _lock_scope(session: Session, scope: str, scope_id: str, window_start: date, currency: str) -> None:
    session.execute(
        text(
            "INSERT INTO broker.budget_locks (scope, scope_id, window_start, currency) "
            "VALUES (:scope, :scope_id, :window_start, :currency) "
            "ON CONFLICT (scope, scope_id, window_start, currency) DO NOTHING"
        ),
        {"scope": scope, "scope_id": scope_id, "window_start": window_start, "currency": currency},
    )
    session.execute(
        text(
            "SELECT 1 FROM broker.budget_locks "
            "WHERE scope = :scope AND scope_id = :scope_id AND window_start = :window_start AND currency = :currency "
            "FOR UPDATE"
        ),
        {"scope": scope, "scope_id": scope_id, "window_start": window_start, "currency": currency},
    )


def scope_usage_minor(session: Session, scope: str, scope_id: str, window_start: date, currency: str) -> int:
    """Sum of amounts allocated to a scope by reservations that still consume
    capacity: RESERVED and UNKNOWN count (invariant 6); RELEASED does not."""
    row = session.execute(
        text(
            """
            SELECT COALESCE(SUM(ra.amount_minor), 0) AS total
            FROM broker.reservation_allocations ra
            JOIN broker.budget_reservations br ON br.id = ra.reservation_id
            WHERE ra.scope = :scope AND ra.scope_id = :scope_id AND ra.window_start = :window_start
              AND br.currency = :currency AND br.state IN ('RESERVED', 'COMMITTED', 'UNKNOWN')
            """
        ),
        {"scope": scope, "scope_id": scope_id, "window_start": window_start, "currency": currency},
    ).one()
    return int(row.total)


def reserve_budget(
    session: Session,
    *,
    action_id: uuid.UUID,
    agent_token_subject: str,
    customer_id: str,
    amount_minor: int,
    currency: str,
    config: dict,
) -> BudgetReservation:
    window_start = datetime.now(timezone.utc).date()
    scopes = _scopes(config, agent_token_subject, customer_id)

    for scope, scope_id, _cap in scopes:
        _lock_scope(session, scope, scope_id, window_start, currency)

    for scope, scope_id, cap in scopes:
        current = scope_usage_minor(session, scope, scope_id, window_start, currency)
        if current + amount_minor > cap:
            raise BudgetExceededError(scope)

    reservation = BudgetReservation(
        id=uuid.uuid4(),
        action_id=action_id,
        amount_minor=amount_minor,
        currency=currency,
        state="RESERVED",
    )
    session.add(reservation)
    session.flush()

    for scope, scope_id, _cap in scopes:
        session.add(
            ReservationAllocation(
                id=uuid.uuid4(),
                reservation_id=reservation.id,
                scope=scope,
                scope_id=scope_id,
                amount_minor=amount_minor,
                window_start=window_start,
            )
        )

    return reservation
