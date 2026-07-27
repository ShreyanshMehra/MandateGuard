"""MandateGuard mock bank service.

Milestone 2 scope: process and dependency health only. The payment/refund
ledger and permit-gated execution endpoint are added in Milestone 4 per
HANDOFF.md.
"""

import os

from fastapi import FastAPI, Response
from sqlalchemy import create_engine, text

SERVICE_NAME = "mock-bank"
DATABASE_URL = os.environ.get("DATABASE_URL", "")

app = FastAPI(title="MandateGuard Mock Bank")

_engine = create_engine(DATABASE_URL, pool_pre_ping=True) if DATABASE_URL else None


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
    if _engine is None:
        return False
    try:
        with _engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
