"""MandateGuard mock bank service.

Milestone 3 scope: health/readiness and the trusted payment-context lookup
the broker uses to build policy input. Permit-gated refund execution is
added in Milestone 4 per HANDOFF.md.
"""

import hmac
import os

from fastapi import Depends, FastAPI, Header, HTTPException, Response
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .db import engine, get_session
from .models import Payment

SERVICE_NAME = "mock-bank"
BROKER_SERVICE_TOKEN = os.environ.get("BROKER_SERVICE_TOKEN", "")

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
