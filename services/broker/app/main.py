"""MandateGuard broker service."""

import uuid

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.exceptions import HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import text

from .config import OPA_URL
from .db import engine
from .routes_refunds import router as refunds_router

SERVICE_NAME = "broker"

app = FastAPI(title="MandateGuard Broker")
app.include_router(refunds_router)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    if isinstance(exc.detail, dict) and "error" in exc.detail:
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": "HTTP_ERROR", "message": str(exc.detail), "correlation_id": str(uuid.uuid4())}},
    )


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
    if engine is None:
        return False
    try:
        with engine.connect() as conn:
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
