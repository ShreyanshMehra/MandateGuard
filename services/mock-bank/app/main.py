"""MandateGuard mock bank service.

Milestone 3 scope: health/readiness and the trusted payment-context lookup
the broker uses to build policy input. Milestone 4 adds permit-gated refund
execution: only the broker's service credential may call this endpoint, and
only with a valid, unexpired, single-use Ed25519 permit whose claims match
the request. The signed result lets the broker verify -- rather than merely
trust -- that a refund was actually applied (docs/DATA_MODEL.md invariant 15).
"""

import base64
import hmac
import json
import os
import uuid
from pathlib import Path

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from fastapi import Depends, FastAPI, Header, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .db import engine, get_session
from .models import BankOperationEvent, Payment, PermitUse, Refund

SERVICE_NAME = "mock-bank"
BROKER_SERVICE_TOKEN = os.environ.get("BROKER_SERVICE_TOKEN", "")
BROKER_PERMIT_PUBLIC_KEY_B64 = os.environ.get("BROKER_PERMIT_PUBLIC_KEY_B64", "")

BANK_RESULT_KEY_PATH = os.environ.get("BANK_RESULT_KEY_PATH", "")
BANK_RESULT_KEY_ID = os.environ.get("BANK_RESULT_KEY_ID", "")
_BANK_RESULT_PRIVATE_KEY = (
    serialization.load_pem_private_key(Path(BANK_RESULT_KEY_PATH).read_bytes(), password=None)
    if BANK_RESULT_KEY_PATH
    else None
)

app = FastAPI(title="MandateGuard Mock Bank")


@app.get("/health")
def health() -> dict:
    return {"service": SERVICE_NAME, "status": "alive"}


@app.get("/ready")
def ready(response: Response) -> dict:
    checks = {"database": _check_database()}
    ok = all(checks.values())
    response.status_code = 200 if ok else 503
    return {"service": SERVICE_NAME, "status": "ready" if ok else "not_ready", "checks": checks}


def _check_database() -> bool:
    if engine is None:
        return False
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def require_broker_service_auth(x_broker_service_token: str = Header(default="")) -> None:
    if not BROKER_SERVICE_TOKEN or not hmac.compare_digest(x_broker_service_token, BROKER_SERVICE_TOKEN):
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "BROKER_AUTH_REQUIRED", "message": "Broker service authentication required."}},
        )


@app.get("/internal/v1/payments/{payment_id}", dependencies=[Depends(require_broker_service_auth)])
def get_payment(payment_id: str, session: Session = Depends(get_session)) -> dict:
    payment = session.execute(select(Payment).where(Payment.payment_id == payment_id)).scalar_one_or_none()
    if payment is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "PAYMENT_NOT_FOUND", "message": "No payment with that ID."}},
        )
    return {
        "payment_id": payment.payment_id,
        "customer_id": payment.customer_id,
        "currency": payment.currency,
        "original_amount_minor": payment.original_amount_minor,
        "refundable_remaining_minor": payment.refundable_remaining_minor,
    }


class RefundExecutionRequest(BaseModel):
    request_id: str
    payment_id: str
    amount_minor: int
    currency: str


def _bank_error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"error": {"code": code, "message": message}})


def _verify_permit(permit_token: str) -> dict:
    if not BROKER_PERMIT_PUBLIC_KEY_B64:
        raise _bank_error(500, "BANK_MISCONFIGURED", "Broker permit public key is not configured.")
    public_key = Ed25519PublicKey.from_public_bytes(base64.b64decode(BROKER_PERMIT_PUBLIC_KEY_B64))
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    try:
        return jwt.decode(
            permit_token,
            key=public_pem,
            algorithms=["EdDSA"],
            options={"require": ["exp", "iat", "jti"]},
        )
    except jwt.InvalidTokenError:
        raise _bank_error(401, "PERMIT_INVALID", "The action permit is missing, malformed or expired.")


def _sign_document(document: dict) -> str:
    canonical = json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
    signature = _BANK_RESULT_PRIVATE_KEY.sign(canonical)
    return base64.b64encode(signature).decode("ascii")


@app.post("/internal/v1/refunds", dependencies=[Depends(require_broker_service_auth)])
def execute_refund(
    body: RefundExecutionRequest,
    x_action_permit: str = Header(default=""),
    session: Session = Depends(get_session),
) -> dict:
    if not x_action_permit:
        raise _bank_error(401, "PERMIT_REQUIRED", "This endpoint requires a valid X-Action-Permit header.")

    claims = _verify_permit(x_action_permit)
    permit_jti = claims["jti"]

    if (
        claims.get("payment_id") != body.payment_id
        or claims.get("amount_minor") != body.amount_minor
        or claims.get("currency") != body.currency
    ):
        raise _bank_error(401, "PERMIT_INVALID", "Permit claims do not match the execution request.")

    existing_refund = session.execute(select(Refund).where(Refund.request_id == body.request_id)).scalar_one_or_none()
    if existing_refund is not None:
        if existing_refund.permit_jti != permit_jti:
            raise _bank_error(409, "REQUEST_ID_CONFLICT", "This request ID was already used with a different permit.")
        return _refund_result_document(existing_refund)

    payment = session.execute(
        select(Payment).where(Payment.payment_id == body.payment_id).with_for_update()
    ).scalar_one_or_none()
    if payment is None:
        raise _bank_error(404, "PAYMENT_NOT_FOUND", "No payment with that ID.")
    if payment.currency != body.currency or body.amount_minor > payment.refundable_remaining_minor:
        raise _bank_error(422, "REFUND_NOT_APPLICABLE", "The refund cannot be applied to this payment.")

    session.add(PermitUse(id=uuid.uuid4(), permit_jti=permit_jti, request_id=body.request_id, result="PENDING"))
    payment.refundable_remaining_minor -= body.amount_minor
    bank_transaction_id = f"btx_{uuid.uuid4().hex[:20]}"

    refund = Refund(
        id=uuid.uuid4(),
        request_id=body.request_id,
        permit_jti=permit_jti,
        payment_id=body.payment_id,
        amount_minor=body.amount_minor,
        currency=body.currency,
        bank_transaction_id=bank_transaction_id,
        status="SUCCEEDED",
    )
    session.add(refund)
    session.add(
        BankOperationEvent(
            id=uuid.uuid4(),
            request_id=body.request_id,
            event_type="REFUND_APPLIED",
            payload={
                "payment_id": body.payment_id,
                "amount_minor": body.amount_minor,
                "bank_transaction_id": bank_transaction_id,
            },
        )
    )
    session.execute(
        text("UPDATE bank.permit_uses SET result = 'SUCCEEDED' WHERE permit_jti = :jti AND request_id = :rid"),
        {"jti": permit_jti, "rid": body.request_id},
    )
    try:
        session.commit()
    except IntegrityError:
        # refunds.permit_jti is globally unique -- this permit was already
        # consumed under a different request_id (invariant 2: at most once).
        session.rollback()
        raise _bank_error(409, "PERMIT_ALREADY_USED", "This permit has already been consumed.")

    return _refund_result_document(refund)


def _refund_result_document(refund: Refund) -> dict:
    document = {
        "request_id": refund.request_id,
        "permit_jti": refund.permit_jti,
        "payment_id": refund.payment_id,
        "amount_minor": refund.amount_minor,
        "currency": refund.currency,
        "bank_transaction_id": refund.bank_transaction_id,
        "status": refund.status,
    }
    return {
        "document": document,
        "signature_b64": _sign_document(document),
        "key_id": BANK_RESULT_KEY_ID,
    }


@app.get("/internal/v1/refunds/{request_id}", dependencies=[Depends(require_broker_service_auth)])
def get_refund(request_id: str, session: Session = Depends(get_session)) -> dict:
    refund = session.execute(select(Refund).where(Refund.request_id == request_id)).scalar_one_or_none()
    if refund is None:
        raise _bank_error(404, "REFUND_NOT_FOUND", "No refund recorded for that request ID.")
    return _refund_result_document(refund)
