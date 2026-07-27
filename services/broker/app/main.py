"""MandateGuard broker service.

Milestone 2 scope: process and dependency health only. Identity, policy
intake, budgets, permits and execution are added in later milestones per
HANDOFF.md.
"""

import os

import httpx
from fastapi import FastAPI, Response
from sqlalchemy import create_engine, text

SERVICE_NAME = "broker"
DATABASE_URL = os.environ.get("DATABASE_URL", "")
OPA_URL = os.environ.get("OPA_URL", "http://opa:8181")

app = FastAPI(title="MandateGuard Broker")

_engine = create_engine(DATABASE_URL, pool_pre_ping=True) if DATABASE_URL else None


@app.get("/health")
def health() -> dict:
    return {"service": SERVICE_NAME, "status": "alive"}


@app.get("/ready")
def ready(response: Response) -> dict:
    checks = {"database": _check_database(), "opa": _check_opa()}
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


def _check_opa() -> bool:
    try:
        resp = httpx.get(f"{OPA_URL}/health", timeout=2.0)
        return resp.status_code == 200
    except httpx.HTTPError:
        return False
