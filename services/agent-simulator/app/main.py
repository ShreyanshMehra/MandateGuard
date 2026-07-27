"""MandateGuard agent simulator.

Milestone 2 scope: process and dependency health only. Deterministic
scenario generation (`/demo/v1/...`) is added in Milestone 6 per
HANDOFF.md.
"""

import os

import httpx
from fastapi import FastAPI, Response

SERVICE_NAME = "agent-simulator"
BROKER_URL = os.environ.get("BROKER_URL", "http://broker:8000")

app = FastAPI(title="MandateGuard Agent Simulator")


@app.get("/health")
def health() -> dict:
    return {"service": SERVICE_NAME, "status": "alive"}


@app.get("/ready")
def ready(response: Response) -> dict:
    checks = {"broker": _check_broker()}
    ok = all(checks.values())
    response.status_code = 200 if ok else 503
    return {"service": SERVICE_NAME, "status": "ready" if ok else "not_ready", "checks": checks}


def _check_broker() -> bool:
    try:
        resp = httpx.get(f"{BROKER_URL}/health", timeout=2.0)
        return resp.status_code == 200
    except httpx.HTTPError:
        return False
