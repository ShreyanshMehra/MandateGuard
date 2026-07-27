"""Refund action intake and execution (Milestones 3 and 4).

Implements the full allowed-request sequence from docs/ARCHITECTURE.md:
identity, policy decision and persistence (steps 1-8), then -- for ALLOW
decisions only -- atomic budget reservation, signed permit issuance, bank
execution and outcome finalization (steps 9-15). Each step after the
initial decision commit is its own short transaction so no database
transaction is ever open during the OPA or mock-bank HTTP calls
(docs/DATA_MODEL.md "Transaction rule").
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
from .budgets import BudgetExceededError, reserve_budget
from .clients import (
    MockBankUnavailableError,
    OpaUnavailableError,
    evaluate_refund_policy,
    execute_bank_refund,
    fetch_trusted_payment,
)
from .db import get_session
from .errors import api_error
from .governance import GovernanceSnapshot, fetch_governance_snapshot
from .models import ActionRequest, Agent, ExecutionReceipt, PolicyEvaluation
from .permits import issue_permit, verify_bank_result
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


def _process_execution(session: Session, action: ActionRequest, agent: Agent, governance: GovernanceSnapshot) -> None:
    """Budget reservation through bank execution for an ALLOW-decided action.
    Mutates and repeatedly commits `action` in place; each step is its own
    short transaction (invariant 16). Idempotent replays never reach this
    function a second time -- they return the already-decided action before
    the caller commits, so no reservation/permit/refund is created twice."""
    try:
        reservation = reserve_budget(
            session,
            action_id=action.id,
            agent_token_subject=agent.token_subject,
            customer_id=action.customer_id,
            amount_minor=action.amount_minor,
            currency=action.currency,
            config=governance.config,
        )
    except BudgetExceededError as exc:
        action.state = "DENIED"
        action.decision = "DENY"
        action.public_reason_code = f"BUDGET_EXCEEDED_{exc.scope.upper()}"
        action.operator_explanation = f"The {exc.scope} budget cap would be exceeded by this refund."
        append_audit_event(
            session, stream_id=f"action:{action.id}", event_type="BUDGET_DENIED",
            actor="system:budget", correlation_id=action.id, payload={"scope": exc.scope},
        )
        session.commit()
        return

    action.state = "BUDGET_RESERVED"
    append_audit_event(
        session, stream_id=f"action:{action.id}", event_type="BUDGET_RESERVED",
        actor="system:budget", correlation_id=action.id,
        payload={"reservation_id": str(reservation.id), "amount_minor": reservation.amount_minor},
    )
    session.commit()

    permit, permit_token = issue_permit(
        action_id=action.id,
        reservation_id=reservation.id,
        payment_id=action.payment_id,
        amount_minor=action.amount_minor,
        currency=action.currency,
        attempt_number=1,
        policy_version_id=action.policy_version_id,
        control_epoch_snapshot=action.control_epoch_snapshot,
        agent_epoch_snapshot=action.agent_epoch_snapshot,
    )
    session.add(permit)
    action.state = "PERMIT_ISSUED"
    append_audit_event(
        session, stream_id=f"action:{action.id}", event_type="PERMIT_ISSUED",
        actor="system:permit", correlation_id=action.id, payload={"jti": permit.jti},
    )
    action.state = "EXECUTING"
    session.commit()

    outcome = execute_bank_refund(
        request_id=str(action.id),
        payment_id=action.payment_id,
        amount_minor=action.amount_minor,
        currency=action.currency,
        permit_token=permit_token,
    )

    verified = outcome.status == "SUCCEEDED" and outcome.document is not None and outcome.document.get(
        "permit_jti"
    ) == permit.jti and verify_bank_result(outcome.document, outcome.signature_b64)

    if verified:
        reservation.state = "COMMITTED"
        permit.status = "CONSUMED"
        action.state = "SUCCEEDED"
        document_hash = hashlib.sha256(
            json.dumps(outcome.document, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        session.add(
            ExecutionReceipt(
                id=uuid.uuid4(),
                action_id=action.id,
                document=outcome.document,
                document_hash=document_hash,
                signature_b64=outcome.signature_b64,
                key_id=outcome.key_id,
                schema_version="1.0",
                created_at=datetime.now(timezone.utc),
            )
        )
        append_audit_event(
            session, stream_id=f"action:{action.id}", event_type="EXECUTION_SUCCEEDED",
            actor="system:execution", correlation_id=action.id,
            payload={"bank_transaction_id": outcome.document["bank_transaction_id"]},
        )
    elif outcome.status == "FAILED":
        reservation.state = "RELEASED"
        reservation.resolution_reason = "EXECUTION_FAILED"
        permit.status = "CANCELLED"
        action.state = "FAILED"
        append_audit_event(
            session, stream_id=f"action:{action.id}", event_type="EXECUTION_FAILED",
            actor="system:execution", correlation_id=action.id, payload={},
        )
    else:
        # UNKNOWN, or a SUCCEEDED response that failed signature/claim
        # verification -- the broker cannot trust it, so the reservation
        # keeps consuming capacity (invariant 6) pending manual reconciliation.
        reservation.state = "UNKNOWN"
        action.state = "UNKNOWN"
        append_audit_event(
            session, stream_id=f"action:{action.id}", event_type="EXECUTION_UNKNOWN",
            actor="system:execution", correlation_id=action.id,
            payload={"reason": "BANK_RESULT_UNVERIFIED" if outcome.status == "SUCCEEDED" else "BANK_UNREACHABLE"},
        )

    session.commit()


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

    if decision_outcome == "ALLOW":
        _process_execution(session, action, agent, governance)

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


@router.get("/internal/v1/budget-usage/{scope}/{scope_id}")
def get_budget_usage(scope: str, scope_id: str, session: Session = Depends(get_session)) -> dict:
    """Dev/test introspection only: current committed+reserved usage for a
    budget scope today, and the configured cap. Not part of the product
    surface (no operator auth); used by the Milestone 4 concurrency test to
    compute headroom so the acceptance run stays deterministic across
    repeated local runs instead of assuming a pristine budget window."""
    from datetime import datetime, timezone

    from .budgets import scope_usage_minor

    governance = fetch_governance_snapshot(session)
    budgets = governance.config["budgets"]
    cap_key = {"customer": "customer_daily_cap_minor", "agent": "agent_daily_cap_minor", "fleet": "fleet_daily_cap_minor"}[scope]
    currency = "USD"
    window_start = datetime.now(timezone.utc).date()
    usage = scope_usage_minor(session, scope, scope_id, window_start, currency)
    return {"scope": scope, "scope_id": scope_id, "usage_minor": usage, "cap_minor": budgets[cap_key]}


@router.get("/internal/v1/payment-balance/{payment_id}")
def get_payment_balance(payment_id: str) -> dict:
    """Dev/test introspection only, mirroring get_budget_usage above: lets the
    Milestone 4 concurrency test bound its request amount by the live
    refundable balance as well as fleet budget headroom, since both are real
    caps a burst of concurrent requests can legitimately hit."""
    payment = fetch_trusted_payment(payment_id)
    if payment is None:
        raise api_error(404, "PAYMENT_NOT_FOUND", "No payment with that ID.")
    return payment


@router.get("/internal/v1/agent-by-subject/{token_subject}")
def get_agent_by_subject(token_subject: str, session: Session = Depends(get_session)) -> dict:
    """Dev/test introspection only: the public API never exposes an agent's
    internal UUID or epoch (there is no agent-facing use for it). Milestone 5's
    governance tests need it to call the operator revoke/restore endpoints,
    which are keyed by UUID per docs/DATA_MODEL.md."""
    agent = session.query(Agent).filter(Agent.token_subject == token_subject).one_or_none()
    if agent is None:
        raise api_error(404, "AGENT_NOT_FOUND", "No agent with that token subject.")
    return {"agent_id": str(agent.id), "status": agent.status, "epoch": agent.epoch}
