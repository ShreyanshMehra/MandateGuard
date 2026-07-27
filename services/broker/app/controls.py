"""Operator control actions: agent revoke/restore and fleet halt/resume/risk
mode (Milestone 5). Every control action is idempotent on its caller-supplied
idempotency key, bumps the relevant monotonic epoch, records a before/after
snapshot in `control_actions`, and appends a hash-chained audit event -- so
in-flight permits and pending approvals become verifiably stale relative to
the new epoch (docs/DATA_MODEL.md "Permits and outcomes").
"""

import uuid

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .audit import append_audit_event
from .errors import api_error
from .models import Agent, ControlAction


class DuplicateControlAction(Exception):
    """Raised when an idempotency key was already used for a control action."""


def _record(
    session: Session,
    *,
    action_type: str,
    target: str | None,
    idempotency_key: str,
    reason: str,
    actor: str,
    before_snapshot: dict,
    after_snapshot: dict,
) -> ControlAction:
    control_action = ControlAction(
        id=uuid.uuid4(),
        action_type=action_type,
        target=target,
        idempotency_key=idempotency_key,
        reason=reason,
        actor=actor,
        before_snapshot=before_snapshot,
        after_snapshot=after_snapshot,
    )
    session.add(control_action)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        raise DuplicateControlAction()
    return control_action


def revoke_agent(session: Session, *, agent_id: uuid.UUID, reason: str, actor: str, idempotency_key: str) -> Agent:
    agent = session.get(Agent, agent_id)
    if agent is None:
        raise api_error(404, "AGENT_NOT_FOUND", "No agent with that ID.")

    before = {"status": agent.status, "epoch": agent.epoch}
    if agent.status != "REVOKED":
        agent.status = "REVOKED"
        agent.status_reason = reason
        agent.epoch += 1
    after = {"status": agent.status, "epoch": agent.epoch}

    _record(
        session, action_type="REVOKE_AGENT", target=str(agent_id), idempotency_key=idempotency_key,
        reason=reason, actor=actor, before_snapshot=before, after_snapshot=after,
    )
    append_audit_event(
        session, stream_id=f"agent:{agent_id}", event_type="AGENT_REVOKED", actor=actor,
        correlation_id=agent_id, payload={"reason": reason, "epoch": agent.epoch},
    )
    return agent


def restore_agent(session: Session, *, agent_id: uuid.UUID, reason: str, actor: str, idempotency_key: str) -> Agent:
    agent = session.get(Agent, agent_id)
    if agent is None:
        raise api_error(404, "AGENT_NOT_FOUND", "No agent with that ID.")

    before = {"status": agent.status, "epoch": agent.epoch}
    if agent.status != "ACTIVE":
        agent.status = "ACTIVE"
        agent.status_reason = reason
        agent.epoch += 1
    after = {"status": agent.status, "epoch": agent.epoch}

    _record(
        session, action_type="RESTORE_AGENT", target=str(agent_id), idempotency_key=idempotency_key,
        reason=reason, actor=actor, before_snapshot=before, after_snapshot=after,
    )
    append_audit_event(
        session, stream_id=f"agent:{agent_id}", event_type="AGENT_RESTORED", actor=actor,
        correlation_id=agent_id, payload={"reason": reason, "epoch": agent.epoch},
    )
    return agent


def _apply_governance_change(
    session: Session, *, action_type: str, reason: str, actor: str, idempotency_key: str, **updates: str
) -> dict:
    row = session.execute(
        text("SELECT run_state, risk_mode, epoch FROM broker.governance_state WHERE id = true FOR UPDATE")
    ).one()
    before = {"run_state": row.run_state, "risk_mode": row.risk_mode, "epoch": row.epoch}

    changed = any(before[key] != value for key, value in updates.items())
    new_run_state = updates.get("run_state", row.run_state)
    new_risk_mode = updates.get("risk_mode", row.risk_mode)
    new_epoch = row.epoch + 1 if changed else row.epoch

    if changed:
        session.execute(
            text(
                """
                UPDATE broker.governance_state
                SET run_state = CAST(:run_state AS broker.governance_run_state),
                    risk_mode = CAST(:risk_mode AS broker.risk_mode),
                    epoch = :epoch, last_actor = :actor, last_reason = :reason, updated_at = now()
                WHERE id = true
                """
            ),
            {
                "run_state": new_run_state,
                "risk_mode": new_risk_mode,
                "epoch": new_epoch,
                "actor": actor,
                "reason": reason,
            },
        )

    after = {"run_state": new_run_state, "risk_mode": new_risk_mode, "epoch": new_epoch}

    _record(
        session, action_type=action_type, target=None, idempotency_key=idempotency_key,
        reason=reason, actor=actor, before_snapshot=before, after_snapshot=after,
    )
    append_audit_event(
        session, stream_id="control:global", event_type=action_type, actor=actor,
        payload={"reason": reason, **after}, control_epoch_snapshot=new_epoch,
    )
    return after


def halt(session: Session, *, reason: str, actor: str, idempotency_key: str) -> dict:
    return _apply_governance_change(
        session, action_type="HALT", reason=reason, actor=actor, idempotency_key=idempotency_key, run_state="HALTED"
    )


def resume(session: Session, *, reason: str, actor: str, idempotency_key: str) -> dict:
    return _apply_governance_change(
        session, action_type="RESUME", reason=reason, actor=actor, idempotency_key=idempotency_key, run_state="RUNNING"
    )


def set_risk_mode(session: Session, *, mode: str, reason: str, actor: str, idempotency_key: str) -> dict:
    if mode not in ("NORMAL", "ELEVATED"):
        raise api_error(400, "INVALID_RISK_MODE", "risk mode must be NORMAL or ELEVATED.")
    return _apply_governance_change(
        session, action_type="SET_RISK_MODE", reason=reason, actor=actor, idempotency_key=idempotency_key, risk_mode=mode
    )
