"""Governance workflows (Milestone 5): held-action approval/denial with
re-evaluation, agent revoke/restore, fleet halt/resume/risk mode, signed
audit checkpoints and read-only candidate-policy shadow replay.

All endpoints here are operator-only (`X-Operator-Token`, dev-only stand-in
for the Milestone 6 dashboard's real login) and are not agent-facing.
"""

import uuid

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from . import config
from .audit import append_audit_event
from .checkpoints import create_checkpoint, verify_checkpoint
from .clients import MockBankUnavailableError, OpaUnavailableError, evaluate_refund_policy, fetch_trusted_payment
from .controls import DuplicateControlAction, halt, resume, revoke_agent, restore_agent, set_risk_mode
from .db import get_session
from .errors import api_error
from .governance import fetch_governance_snapshot
from .models import Agent, ActionRequest, Approval, AuditCheckpoint, PolicyEvaluation, PolicyReplayResult, PolicyReplayRun
from .replay import run_replay
from .routes_refunds import _process_execution, _to_response
from .schemas import ActionResponse, ApprovalRequest, ControlRequest, ReplayRequest, RiskModeRequest
from .security import require_operator

router = APIRouter(prefix="/api/v1/admin")


def _require_idempotency_key(idempotency_key: str | None) -> str:
    if not idempotency_key:
        raise api_error(400, "IDEMPOTENCY_KEY_REQUIRED", "The Idempotency-Key header is required.")
    return idempotency_key


@router.post("/agents/{agent_id}/revoke")
def revoke(
    agent_id: str,
    body: ControlRequest,
    x_operator_token: str | None = Header(default=None),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    session: Session = Depends(get_session),
) -> dict:
    actor = require_operator(x_operator_token)
    key = _require_idempotency_key(idempotency_key)
    try:
        agent = revoke_agent(session, agent_id=uuid.UUID(agent_id), reason=body.reason, actor=actor, idempotency_key=key)
    except DuplicateControlAction:
        session.rollback()
        agent = session.get(Agent, uuid.UUID(agent_id))
    session.commit()
    return {"agent_id": str(agent.id), "status": agent.status, "epoch": agent.epoch}


@router.post("/agents/{agent_id}/restore")
def restore(
    agent_id: str,
    body: ControlRequest,
    x_operator_token: str | None = Header(default=None),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    session: Session = Depends(get_session),
) -> dict:
    actor = require_operator(x_operator_token)
    key = _require_idempotency_key(idempotency_key)
    try:
        agent = restore_agent(session, agent_id=uuid.UUID(agent_id), reason=body.reason, actor=actor, idempotency_key=key)
    except DuplicateControlAction:
        session.rollback()
        agent = session.get(Agent, uuid.UUID(agent_id))
    session.commit()
    return {"agent_id": str(agent.id), "status": agent.status, "epoch": agent.epoch}


@router.post("/fleet/halt")
def fleet_halt(
    body: ControlRequest,
    x_operator_token: str | None = Header(default=None),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    session: Session = Depends(get_session),
) -> dict:
    actor = require_operator(x_operator_token)
    key = _require_idempotency_key(idempotency_key)
    try:
        state = halt(session, reason=body.reason, actor=actor, idempotency_key=key)
    except DuplicateControlAction:
        session.rollback()
        governance = fetch_governance_snapshot(session)
        state = {"run_state": governance.run_state, "risk_mode": governance.risk_mode, "epoch": governance.epoch}
    session.commit()
    return state


@router.post("/fleet/resume")
def fleet_resume(
    body: ControlRequest,
    x_operator_token: str | None = Header(default=None),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    session: Session = Depends(get_session),
) -> dict:
    actor = require_operator(x_operator_token)
    key = _require_idempotency_key(idempotency_key)
    try:
        state = resume(session, reason=body.reason, actor=actor, idempotency_key=key)
    except DuplicateControlAction:
        session.rollback()
        governance = fetch_governance_snapshot(session)
        state = {"run_state": governance.run_state, "risk_mode": governance.risk_mode, "epoch": governance.epoch}
    session.commit()
    return state


@router.post("/fleet/risk-mode")
def fleet_risk_mode(
    body: RiskModeRequest,
    x_operator_token: str | None = Header(default=None),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    session: Session = Depends(get_session),
) -> dict:
    actor = require_operator(x_operator_token)
    key = _require_idempotency_key(idempotency_key)
    try:
        state = set_risk_mode(session, mode=body.mode, reason=body.reason, actor=actor, idempotency_key=key)
    except DuplicateControlAction:
        session.rollback()
        governance = fetch_governance_snapshot(session)
        state = {"run_state": governance.run_state, "risk_mode": governance.risk_mode, "epoch": governance.epoch}
    session.commit()
    return state


@router.post("/actions/{action_id}/approve", response_model=ActionResponse)
def approve_action(
    action_id: str,
    body: ApprovalRequest,
    x_operator_token: str | None = Header(default=None),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    session: Session = Depends(get_session),
) -> ActionResponse:
    actor = require_operator(x_operator_token)
    key = _require_idempotency_key(idempotency_key)

    existing_approval = session.query(Approval).filter(Approval.idempotency_key == key).one_or_none()
    if existing_approval is not None:
        return _to_response(session.get(ActionRequest, existing_approval.action_id))

    action = session.get(ActionRequest, uuid.UUID(action_id))
    if action is None:
        raise api_error(404, "ACTION_NOT_FOUND", "No action with that ID.")
    if action.state != "HELD":
        raise api_error(409, "ACTION_NOT_HELD", "This action is not awaiting approval.")

    governance = fetch_governance_snapshot(session)
    agent = session.get(Agent, action.agent_id)

    stale = agent.epoch != action.agent_epoch_snapshot or governance.epoch != action.control_epoch_snapshot
    if stale:
        action.state = "DENIED"
        action.decision = "DENY"
        action.public_reason_code = "STALE_CONTEXT_RECHECK_REQUIRED"
        action.operator_explanation = (
            "Agent or fleet control state changed since this action was held; "
            "approval was rejected rather than executed against a stale context."
        )
        session.add(Approval(id=uuid.uuid4(), action_id=action.id, approver=actor, decision="DENIED", reason=body.reason, idempotency_key=key))
        append_audit_event(
            session, stream_id=f"action:{action.id}", event_type="APPROVAL_REJECTED_STALE_CONTEXT", actor=f"operator:{actor}",
            correlation_id=action.id, control_epoch_snapshot=governance.epoch,
            payload={"held_control_epoch": action.control_epoch_snapshot, "current_control_epoch": governance.epoch,
                     "held_agent_epoch": action.agent_epoch_snapshot, "current_agent_epoch": agent.epoch},
        )
        session.commit()
        return _to_response(action)

    try:
        payment = fetch_trusted_payment(action.payment_id)
    except MockBankUnavailableError:
        raise api_error(503, "BANK_CONTEXT_UNAVAILABLE", "MandateGuard could not reach the mock bank.")

    if payment is None or payment["currency"] != action.currency or action.amount_minor > payment["refundable_remaining_minor"]:
        action.state = "DENIED"
        action.decision = "DENY"
        action.public_reason_code = "APPROVAL_RECHECK_CONTEXT_INVALID"
        action.operator_explanation = "The payment context changed since this action was held; approval was rejected."
        session.add(Approval(id=uuid.uuid4(), action_id=action.id, approver=actor, decision="APPROVED", reason=body.reason, idempotency_key=key))
        append_audit_event(
            session, stream_id=f"action:{action.id}", event_type="APPROVAL_RECHECK_DENIED", actor=f"operator:{actor}",
            correlation_id=action.id, payload={"reason": "PAYMENT_CONTEXT_INVALID"},
        )
        session.commit()
        return _to_response(action)

    opa_input = {
        "agent": {"id": agent.token_subject, "authenticated": True, "status": agent.status},
        "request": {
            "action": config.SUPPORTED_ACTION,
            "payment_id": action.payment_id,
            "customer_id": action.customer_id,
            "amount_minor": action.amount_minor,
            "currency": action.currency,
        },
        "context": {"risk_mode": governance.risk_mode},
    }
    try:
        result = evaluate_refund_policy(opa_input)
    except OpaUnavailableError:
        raise api_error(503, "POLICY_SERVICE_UNAVAILABLE", "MandateGuard could not reach the policy service.")

    session.add(
        PolicyEvaluation(
            id=uuid.uuid4(), action_id=action.id, phase="APPROVAL_RECHECK",
            input_snapshot=opa_input, output_snapshot=result,
            decision=result["outcome"], reason_code=result["reason_code"],
            policy_version_id=governance.policy_version_id,
        )
    )
    session.add(Approval(id=uuid.uuid4(), action_id=action.id, approver=actor, decision="APPROVED", reason=body.reason, idempotency_key=key))

    # A HOLD recheck outcome means only the amount-threshold rule still
    # applies -- exactly the condition a human approval is meant to satisfy
    # (docs/refund_policy.rego: hold_obligations). A DENY recheck outcome
    # means something else now blocks it (hard max, revoked agent, wrong
    # currency, out-of-scope customer, ...); the rego "else chain" precedence
    # comment is explicit that a hard limit must never be weakened by an
    # approval, so DENY always wins over the operator's decision to approve.
    if result["outcome"] in ("ALLOW", "HOLD"):
        action.state = "RECEIVED"
        action.decision = "ALLOW"
        action.public_reason_code = "APPROVED_BY_OPERATOR"
        action.operator_explanation = f"Approved by operator: {body.reason or 'no reason given'}"
        action.policy_version_id = governance.policy_version_id
        action.risk_mode_snapshot = governance.risk_mode
        action.control_epoch_snapshot = governance.epoch
        action.agent_epoch_snapshot = agent.epoch
        append_audit_event(
            session, stream_id=f"action:{action.id}", event_type="ACTION_APPROVED", actor=f"operator:{actor}",
            correlation_id=action.id, control_epoch_snapshot=governance.epoch, payload={"reason": body.reason},
        )
        session.commit()
        _process_execution(session, action, agent, governance)
    else:
        action.state = "DENIED"
        action.decision = "DENY"
        action.public_reason_code = result["reason_code"]
        action.operator_explanation = result["operator_explanation"]
        append_audit_event(
            session, stream_id=f"action:{action.id}", event_type="APPROVAL_RECHECK_DENIED", actor=f"operator:{actor}",
            correlation_id=action.id, payload={"reason_code": result["reason_code"]},
        )
        session.commit()

    return _to_response(action)


@router.post("/actions/{action_id}/deny", response_model=ActionResponse)
def deny_action(
    action_id: str,
    body: ApprovalRequest,
    x_operator_token: str | None = Header(default=None),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    session: Session = Depends(get_session),
) -> ActionResponse:
    actor = require_operator(x_operator_token)
    key = _require_idempotency_key(idempotency_key)

    existing_approval = session.query(Approval).filter(Approval.idempotency_key == key).one_or_none()
    if existing_approval is not None:
        return _to_response(session.get(ActionRequest, existing_approval.action_id))

    action = session.get(ActionRequest, uuid.UUID(action_id))
    if action is None:
        raise api_error(404, "ACTION_NOT_FOUND", "No action with that ID.")
    if action.state != "HELD":
        raise api_error(409, "ACTION_NOT_HELD", "This action is not awaiting approval.")

    action.state = "DENIED"
    action.decision = "DENY"
    action.public_reason_code = "OPERATOR_DENIED"
    action.operator_explanation = body.reason or "An operator denied this held action."
    session.add(Approval(id=uuid.uuid4(), action_id=action.id, approver=actor, decision="DENIED", reason=body.reason, idempotency_key=key))
    append_audit_event(
        session, stream_id=f"action:{action.id}", event_type="ACTION_DENIED_BY_OPERATOR", actor=f"operator:{actor}",
        correlation_id=action.id, payload={"reason": body.reason},
    )
    session.commit()
    return _to_response(action)


@router.post("/audit/checkpoints")
def post_checkpoint(x_operator_token: str | None = Header(default=None), session: Session = Depends(get_session)) -> dict:
    require_operator(x_operator_token)
    checkpoint = create_checkpoint(session)
    session.commit()
    return {
        "checkpoint_id": str(checkpoint.id),
        "manifest": checkpoint.manifest,
        "manifest_hash": checkpoint.manifest_hash,
        "signature_b64": checkpoint.signature_b64,
        "key_id": checkpoint.key_id,
    }


@router.get("/audit/checkpoints/{checkpoint_id}/verify")
def get_checkpoint_verify(
    checkpoint_id: str, x_operator_token: str | None = Header(default=None), session: Session = Depends(get_session)
) -> dict:
    require_operator(x_operator_token)
    checkpoint = session.get(AuditCheckpoint, uuid.UUID(checkpoint_id))
    if checkpoint is None:
        raise api_error(404, "CHECKPOINT_NOT_FOUND", "No checkpoint with that ID.")
    return verify_checkpoint(session, checkpoint)


@router.post("/policy/replay")
def post_replay(
    body: ReplayRequest, x_operator_token: str | None = Header(default=None), session: Session = Depends(get_session)
) -> dict:
    actor = require_operator(x_operator_token)
    run = run_replay(session, candidate_config=body.candidate_config, from_time=body.from_time, to_time=body.to_time, actor=actor)
    session.commit()
    return {"run_id": str(run.id), "status": run.status, "summary": run.summary}


@router.get("/policy/replay/{run_id}")
def get_replay(run_id: str, x_operator_token: str | None = Header(default=None), session: Session = Depends(get_session)) -> dict:
    require_operator(x_operator_token)
    run = session.get(PolicyReplayRun, uuid.UUID(run_id))
    if run is None:
        raise api_error(404, "REPLAY_RUN_NOT_FOUND", "No replay run with that ID.")
    results = session.query(PolicyReplayResult).filter(PolicyReplayResult.run_id == run.id).all()
    return {
        "run_id": str(run.id),
        "status": run.status,
        "summary": run.summary,
        "results": [
            {
                "action_id": str(r.action_id),
                "baseline_decision": r.baseline_decision,
                "candidate_decision": r.candidate_decision,
                "baseline_reason_code": r.baseline_reason_code,
                "candidate_reason_code": r.candidate_reason_code,
                "changed": r.changed,
            }
            for r in results
        ],
    }
