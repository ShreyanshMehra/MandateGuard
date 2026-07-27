"""Refund action intake (Milestone 3 scope).

Implements the allowed-request sequence from docs/ARCHITECTURE.md up through
"ask OPA for the decision" and "persist all lifecycle events" (steps 1-8 and
15). Budget reservation, permit issuance and bank execution (steps 9-14) are
added in Milestone 4 -- an ALLOW decision here is persisted with the action
left in the RECEIVED state, decision=ALLOW, pending that work.
"""

import hashlib
import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import config
from .audit import append_audit_event
from .clients import MockBankUnavailableError, OpaUnavailableError, evaluate_refund_policy, fetch_trusted_payment
from .db import get_session
from .errors import api_error
from .governance import fetch_governance_snapshot
from .models import ActionRequest, Agent, PolicyEvaluation
from .schemas import ActionResponse, RefundRequest
from .security import extract_bearer_token, verify_agent_token

router = APIRouter()


def _canonical_hash(body: RefundRequest) -> str:
    canonical = json.dumps(body.model_dump(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _to_response(action: ActionRequest) -> ActionResponse:
    return ActionResponse(
        action_id=str(action.id),
        status=action.state,
        decision=action.decision,
        reason_code=action.public_reason_code,
        public_explanation=action.operator_explanation,
    )


@router.post("/api/v1/refunds", response_model=ActionResponse, status_code=201)
def create_refund(
    body: RefundRequest,
    authorization: str | None = Header(default=None),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    session: Session = Depends(get_session),
) -> ActionResponse:
    if not idempotency_key:
        raise api_error(400, "IDEMPOTENCY_KEY_REQUIRED", "The Idempotency-Key header is required.")

    token = extract_bearer_token(authorization)
    agent = verify_agent_token(token, session)

    request_hash = _canonical_hash(body)

    existing = (
        session.query(ActionRequest)
        .filter(ActionRequest.agent_id == agent.id, ActionRequest.idempotency_key == idempotency_key)
        .one_or_none()
    )
    if existing is not None:
        if existing.canonical_request_hash != request_hash:
            raise api_error(
                409,
                "IDEMPOTENCY_KEY_CONFLICT",
                "This idempotency key was already used with a different request body.",
            )
        return _to_response(existing)

    action_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    try:
        governance = fetch_governance_snapshot(session)
    except Exception:
        raise api_error(503, "GOVERNANCE_STATE_UNAVAILABLE", "MandateGuard could not read governance state.")

    decision_outcome: str
    public_reason_code: str
    operator_explanation: str
    policy_evaluation_row: dict | None = None
    customer_id: str | None = None

    if governance.run_state == "HALTED":
        decision_outcome = "DENY"
        public_reason_code = "FLEET_HALTED"
        operator_explanation = "The fleet is halted; no new money-changing actions are authorized."
    else:
        try:
            payment = fetch_trusted_payment(body.payment_id)
        except MockBankUnavailableError:
            raise api_error(503, "BANK_CONTEXT_UNAVAILABLE", "MandateGuard could not reach the mock bank.")

        if payment is None:
            decision_outcome = "DENY"
            public_reason_code = "PAYMENT_NOT_FOUND"
            operator_explanation = f"No payment exists with ID {body.payment_id!r}."
        elif payment["currency"] != body.currency:
            decision_outcome = "DENY"
            public_reason_code = "CURRENCY_MISMATCH"
            operator_explanation = (
                f"Requested currency {body.currency!r} does not match the payment's currency "
                f"{payment['currency']!r} on file."
            )
            customer_id = payment["customer_id"]
        elif body.amount_minor > payment["refundable_remaining_minor"]:
            decision_outcome = "DENY"
            public_reason_code = "AMOUNT_EXCEEDS_REFUNDABLE"
            operator_explanation = (
                f"Requested amount_minor {body.amount_minor} exceeds the refundable remaining amount "
                f"{payment['refundable_remaining_minor']} on this payment."
            )
            customer_id = payment["customer_id"]
        else:
            customer_id = payment["customer_id"]
            opa_input = {
                "agent": {"id": agent.token_subject, "authenticated": True, "status": agent.status},
                "request": {
                    "action": config.SUPPORTED_ACTION,
                    "payment_id": body.payment_id,
                    "customer_id": customer_id,
                    "amount_minor": body.amount_minor,
                    "currency": body.currency,
                },
                "context": {"risk_mode": governance.risk_mode},
            }
            try:
                result = evaluate_refund_policy(opa_input)
            except OpaUnavailableError:
                raise api_error(503, "POLICY_SERVICE_UNAVAILABLE", "MandateGuard could not reach the policy service.")

            decision_outcome = result["outcome"]
            public_reason_code = result["reason_code"]
            operator_explanation = result["operator_explanation"]
            policy_evaluation_row = {
                "input_snapshot": opa_input,
                "output_snapshot": result,
                "decision": decision_outcome,
                "reason_code": public_reason_code,
            }

    state = {"ALLOW": "RECEIVED", "HOLD": "HELD", "DENY": "DENIED"}[decision_outcome]

    action = ActionRequest(
        id=action_id,
        agent_id=agent.id,
        idempotency_key=idempotency_key,
        canonical_request_hash=request_hash,
        payment_id=body.payment_id,
        customer_id=customer_id,
        amount_minor=body.amount_minor,
        currency=body.currency,
        reason_code=body.reason_code,
        state=state,
        decision=decision_outcome,
        public_reason_code=public_reason_code,
        operator_explanation=operator_explanation,
        policy_version_id=governance.policy_version_id if policy_evaluation_row else None,
        risk_mode_snapshot=governance.risk_mode,
        control_epoch_snapshot=governance.epoch,
        agent_epoch_snapshot=agent.epoch,
        created_at=now,
    )
    session.add(action)

    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        existing = (
            session.query(ActionRequest)
            .filter(ActionRequest.agent_id == agent.id, ActionRequest.idempotency_key == idempotency_key)
            .one_or_none()
        )
        if existing is not None and existing.canonical_request_hash == request_hash:
            return _to_response(existing)
        raise api_error(
            409,
            "IDEMPOTENCY_KEY_CONFLICT",
            "This idempotency key was already used with a different request body.",
        )

    if policy_evaluation_row is not None:
        session.add(
            PolicyEvaluation(
                id=uuid.uuid4(),
                action_id=action_id,
                phase="INITIAL",
                input_snapshot=policy_evaluation_row["input_snapshot"],
                output_snapshot=policy_evaluation_row["output_snapshot"],
                decision=policy_evaluation_row["decision"],
                reason_code=policy_evaluation_row["reason_code"],
                policy_version_id=governance.policy_version_id,
            )
        )

    append_audit_event(
        session,
        stream_id=f"action:{action_id}",
        event_type="ACTION_DECIDED",
        actor=f"agent:{agent.token_subject}",
        correlation_id=action_id,
        policy_version_id=governance.policy_version_id if policy_evaluation_row else None,
        control_epoch_snapshot=governance.epoch,
        payload={
            "action_id": str(action_id),
            "decision": decision_outcome,
            "reason_code": public_reason_code,
            "payment_id": body.payment_id,
            "amount_minor": body.amount_minor,
            "currency": body.currency,
        },
    )

    session.commit()
    return _to_response(action)


@router.get("/api/v1/actions/{action_id}", response_model=ActionResponse)
def get_action(
    action_id: str,
    authorization: str | None = Header(default=None),
    session: Session = Depends(get_session),
) -> ActionResponse:
    token = extract_bearer_token(authorization)
    agent: Agent = verify_agent_token(token, session)

    try:
        action_uuid = uuid.UUID(action_id)
    except ValueError:
        raise api_error(404, "ACTION_NOT_FOUND", "No action with that ID.")

    action = (
        session.query(ActionRequest)
        .filter(ActionRequest.id == action_uuid, ActionRequest.agent_id == agent.id)
        .one_or_none()
    )
    if action is None:
        raise api_error(404, "ACTION_NOT_FOUND", "No action with that ID.")

    return _to_response(action)
