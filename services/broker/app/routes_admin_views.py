"""Read-only operator views (Milestone 6): the data the dashboard renders.

Everything here is a GET with no side effects, gated the same way as the
mutating governance endpoints in routes_controls.py (`X-Operator-Token`).
Kept in a separate router/module from routes_controls.py so mutations and
views don't mix in one file as the admin surface grows.
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header
from sqlalchemy import text
from sqlalchemy.orm import Session

from .budgets import scope_usage_minor
from .db import get_session
from .errors import api_error
from .governance import fetch_governance_snapshot
from .models import Agent, ActionRequest, ExecutionReceipt
from .permits import verify_bank_result
from .security import require_operator

router = APIRouter(prefix="/api/v1/admin")


@router.get("/governance")
def get_governance(x_operator_token: str | None = Header(default=None), session: Session = Depends(get_session)) -> dict:
    require_operator(x_operator_token)
    snapshot = fetch_governance_snapshot(session)
    return {
        "run_state": snapshot.run_state,
        "risk_mode": snapshot.risk_mode,
        "epoch": snapshot.epoch,
        "policy_version_number": snapshot.policy_version_number,
        "fleet_budget_scope": snapshot.config.get("fleet_budget_scope"),
    }


@router.get("/agents")
def list_agents(x_operator_token: str | None = Header(default=None), session: Session = Depends(get_session)) -> dict:
    require_operator(x_operator_token)
    agents = session.query(Agent).order_by(Agent.token_subject).all()
    return {
        "agents": [
            {
                "agent_id": str(a.id),
                "token_subject": a.token_subject,
                "display_name": a.display_name,
                "status": a.status,
                "status_reason": a.status_reason,
                "epoch": a.epoch,
            }
            for a in agents
        ]
    }


@router.get("/actions")
def list_actions(
    state: str | None = None,
    limit: int = 50,
    x_operator_token: str | None = Header(default=None),
    session: Session = Depends(get_session),
) -> dict:
    require_operator(x_operator_token)
    limit = max(1, min(limit, 200))
    query = (
        session.query(ActionRequest, Agent.token_subject)
        .join(Agent, Agent.id == ActionRequest.agent_id)
        .order_by(ActionRequest.created_at.desc())
    )
    if state:
        query = query.filter(ActionRequest.state == state)
    rows = query.limit(limit).all()
    return {
        "actions": [
            {
                "action_id": str(action.id),
                "agent": token_subject,
                "state": action.state,
                "decision": action.decision,
                "payment_id": action.payment_id,
                "customer_id": action.customer_id,
                "amount_minor": action.amount_minor,
                "currency": action.currency,
                "reason_code": action.public_reason_code,
                "created_at": action.created_at.isoformat(),
            }
            for action, token_subject in rows
        ]
    }


@router.get("/actions/{action_id}")
def get_action_detail(
    action_id: str, x_operator_token: str | None = Header(default=None), session: Session = Depends(get_session)
) -> dict:
    require_operator(x_operator_token)
    try:
        action_uuid = uuid.UUID(action_id)
    except ValueError:
        raise api_error(404, "ACTION_NOT_FOUND", "No action with that ID.")

    row = (
        session.query(ActionRequest, Agent.token_subject)
        .join(Agent, Agent.id == ActionRequest.agent_id)
        .filter(ActionRequest.id == action_uuid)
        .one_or_none()
    )
    if row is None:
        raise api_error(404, "ACTION_NOT_FOUND", "No action with that ID.")
    action, token_subject = row

    reservation = session.execute(
        text("SELECT amount_minor, currency, state, resolution_reason FROM broker.budget_reservations WHERE action_id = :id"),
        {"id": action_uuid},
    ).mappings().one_or_none()
    permit = session.execute(
        text("SELECT jti, status, attempt_number, expires_at FROM broker.action_permits WHERE action_id = :id ORDER BY attempt_number DESC LIMIT 1"),
        {"id": action_uuid},
    ).mappings().one_or_none()
    receipt = session.query(ExecutionReceipt).filter(ExecutionReceipt.action_id == action_uuid).one_or_none()
    events = session.execute(
        text(
            "SELECT sequence, event_type, actor, payload, created_at FROM broker.audit_events "
            "WHERE stream_id = :stream_id ORDER BY sequence"
        ),
        {"stream_id": f"action:{action_uuid}"},
    ).mappings().all()

    return {
        "action_id": str(action.id),
        "agent": token_subject,
        "state": action.state,
        "decision": action.decision,
        "payment_id": action.payment_id,
        "customer_id": action.customer_id,
        "amount_minor": action.amount_minor,
        "currency": action.currency,
        "reason_code": action.public_reason_code,
        "operator_explanation": action.operator_explanation,
        "risk_mode_snapshot": action.risk_mode_snapshot,
        "control_epoch_snapshot": action.control_epoch_snapshot,
        "agent_epoch_snapshot": action.agent_epoch_snapshot,
        "created_at": action.created_at.isoformat(),
        "reservation": dict(reservation) if reservation else None,
        "permit": {**dict(permit), "expires_at": permit["expires_at"].isoformat()} if permit else None,
        "receipt": (
            {
                "bank_transaction_id": receipt.document.get("bank_transaction_id"),
                "document_hash": receipt.document_hash,
                "key_id": receipt.key_id,
            }
            if receipt
            else None
        ),
        "audit_events": [
            {
                "sequence": e["sequence"],
                "event_type": e["event_type"],
                "actor": e["actor"],
                "payload": e["payload"],
                "created_at": e["created_at"].isoformat(),
            }
            for e in events
        ],
    }


@router.get("/exposure")
def get_exposure(x_operator_token: str | None = Header(default=None), session: Session = Depends(get_session)) -> dict:
    require_operator(x_operator_token)
    snapshot = fetch_governance_snapshot(session)
    budgets = snapshot.config["budgets"]
    currency = "USD"
    window_start = datetime.now(timezone.utc).date()

    fleet_scope_id = snapshot.config["fleet_budget_scope"]
    fleet_usage = scope_usage_minor(session, "fleet", fleet_scope_id, window_start, currency)

    agents = session.query(Agent).order_by(Agent.token_subject).all()
    agent_exposure = [
        {
            "agent": a.token_subject,
            "usage_minor": scope_usage_minor(session, "agent", a.token_subject, window_start, currency),
            "cap_minor": budgets["agent_daily_cap_minor"],
        }
        for a in agents
    ]

    customer_rows = session.execute(
        text(
            """
            SELECT ra.scope_id AS customer_id, SUM(ra.amount_minor) AS usage_minor
            FROM broker.reservation_allocations ra
            JOIN broker.budget_reservations br ON br.id = ra.reservation_id
            WHERE ra.scope = 'customer' AND ra.window_start = :window_start
              AND br.currency = :currency AND br.state IN ('RESERVED', 'COMMITTED', 'UNKNOWN')
            GROUP BY ra.scope_id
            ORDER BY usage_minor DESC
            LIMIT 10
            """
        ),
        {"window_start": window_start, "currency": currency},
    ).mappings().all()

    return {
        "fleet": {"usage_minor": fleet_usage, "cap_minor": budgets["fleet_daily_cap_minor"]},
        "agents": agent_exposure,
        "top_customers": [
            {"customer_id": r["customer_id"], "usage_minor": int(r["usage_minor"]), "cap_minor": budgets["customer_daily_cap_minor"]}
            for r in customer_rows
        ],
    }


@router.get("/receipts")
def list_receipts(
    limit: int = 50, x_operator_token: str | None = Header(default=None), session: Session = Depends(get_session)
) -> dict:
    require_operator(x_operator_token)
    limit = max(1, min(limit, 200))
    receipts = session.query(ExecutionReceipt).order_by(ExecutionReceipt.created_at.desc()).limit(limit).all()
    return {
        "receipts": [
            {
                "action_id": str(r.action_id),
                "bank_transaction_id": r.document.get("bank_transaction_id"),
                "amount_minor": r.document.get("amount_minor"),
                "currency": r.document.get("currency"),
                "document_hash": r.document_hash,
                "key_id": r.key_id,
                "created_at": r.created_at.isoformat(),
            }
            for r in receipts
        ]
    }


@router.get("/receipts/{action_id}/verify")
def verify_receipt(
    action_id: str, x_operator_token: str | None = Header(default=None), session: Session = Depends(get_session)
) -> dict:
    require_operator(x_operator_token)
    try:
        action_uuid = uuid.UUID(action_id)
    except ValueError:
        raise api_error(404, "RECEIPT_NOT_FOUND", "No receipt for that action ID.")

    receipt = session.query(ExecutionReceipt).filter(ExecutionReceipt.action_id == action_uuid).one_or_none()
    if receipt is None:
        raise api_error(404, "RECEIPT_NOT_FOUND", "No receipt for that action ID.")

    signature_valid = verify_bank_result(receipt.document, receipt.signature_b64)
    return {
        "action_id": action_id,
        "signature_valid": signature_valid,
        "document_hash": receipt.document_hash,
        "key_id": receipt.key_id,
        "document": receipt.document,
    }
