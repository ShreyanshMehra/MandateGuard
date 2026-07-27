"""Milestone 5 acceptance tests: approvals, controls, checkpoints, replay.

Run against the live docker-compose stack. Before running, reset dev state
(see tests/test_budget_execution.py's module docstring for the command).

Usage: BROKER_URL=http://localhost:8000 pytest tests/test_governance_workflows.py
"""

import os
import subprocess
import time
import uuid
from pathlib import Path

import httpx
import jwt
import pytest

BROKER_URL = os.environ.get("BROKER_URL", "http://localhost:8000")
SECRETS_DIR = Path(__file__).resolve().parent.parent / "secrets" / "dev"
REPO_ROOT = Path(__file__).resolve().parent.parent

OPERATOR_TOKEN = os.environ.get("OPERATOR_TOKEN", "dev_operator_token_change_me")
OPERATOR_HEADERS = {"X-Operator-Token": OPERATOR_TOKEN}

REFUND_AGENT_KEY_ID = "refund-agent-v1:dev-2026-07"
REFUND_AGENT_KEY_PATH = SECRETS_DIR / "refund-agent-v1__refund-agent-v1_dev-2026-07.pem"
GOVERNANCE_PAYMENT = "payment-demo-004"


def _mint_token(agent_id: str, key_id: str, key_path: Path, ttl_seconds: int = 120) -> str:
    now = int(time.time())
    return jwt.encode(
        {"sub": agent_id, "iat": now, "exp": now + ttl_seconds, "jti": str(uuid.uuid4())},
        key=key_path.read_bytes(),
        algorithm="EdDSA",
        headers={"kid": key_id},
    )


@pytest.fixture(scope="module")
def client() -> httpx.Client:
    with httpx.Client(base_url=BROKER_URL, timeout=15.0) as c:
        yield c


@pytest.fixture()
def refund_agent_token() -> str:
    return _mint_token("refund-agent-v1", REFUND_AGENT_KEY_ID, REFUND_AGENT_KEY_PATH)


def _post_refund(client: httpx.Client, token: str, idempotency_key: str, amount_minor: int) -> httpx.Response:
    return client.post(
        "/api/v1/refunds",
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": idempotency_key},
        json={"payment_id": GOVERNANCE_PAYMENT, "amount_minor": amount_minor, "currency": "USD", "reason_code": "CUSTOMER_REQUEST"},
    )


def _agent_id(client: httpx.Client, token_subject: str) -> str:
    return client.get(f"/internal/v1/agent-by-subject/{token_subject}").json()["agent_id"]


def test_operator_token_required(client: httpx.Client) -> None:
    resp = client.post("/api/v1/admin/fleet/halt", json={"reason": "test"}, headers={"Idempotency-Key": str(uuid.uuid4())})
    assert resp.status_code == 401


def test_agent_revoke_then_restore_bumps_epoch(client: httpx.Client) -> None:
    agent_id = _agent_id(client, "refund-agent-v1")
    before = client.get(f"/internal/v1/agent-by-subject/refund-agent-v1").json()

    revoke_resp = client.post(
        f"/api/v1/admin/agents/{agent_id}/revoke",
        json={"reason": "governance test"},
        headers={**OPERATOR_HEADERS, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert revoke_resp.status_code == 200
    revoked = revoke_resp.json()
    assert revoked["status"] == "REVOKED"
    assert revoked["epoch"] == before["epoch"] + 1

    restore_resp = client.post(
        f"/api/v1/admin/agents/{agent_id}/restore",
        json={"reason": "governance test cleanup"},
        headers={**OPERATOR_HEADERS, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert restore_resp.status_code == 200
    restored = restore_resp.json()
    assert restored["status"] == "ACTIVE"
    assert restored["epoch"] == revoked["epoch"] + 1


def _hold_amount(client: httpx.Client) -> int:
    """A HOLD-triggering amount (> the 25000 NORMAL approval threshold) that
    also fits the fleet budget's live headroom, so this test stays correct
    even when it runs after test_budget_execution.py's concurrency burst has
    consumed most of the shared daily fleet cap in the same pytest session."""
    usage = client.get("/internal/v1/budget-usage/fleet/refund-fleet").json()
    headroom = usage["cap_minor"] - usage["usage_minor"]
    if headroom < 25001:
        pytest.skip("insufficient fleet budget headroom in this run; run scripts/reset_dev_state.sql first")
    return min(30000, headroom)


def test_held_action_approved_executes(client: httpx.Client, refund_agent_token: str) -> None:
    resp = _post_refund(client, refund_agent_token, f"hold-approve-{uuid.uuid4()}", _hold_amount(client))
    assert resp.status_code == 201
    data = resp.json()
    assert data["decision"] == "HOLD"
    assert data["status"] == "HELD"

    approve_resp = client.post(
        f"/api/v1/admin/actions/{data['action_id']}/approve",
        json={"reason": "looks fine"},
        headers={**OPERATOR_HEADERS, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert approve_resp.status_code == 200
    approved = approve_resp.json()
    assert approved["decision"] == "ALLOW"
    assert approved["status"] == "SUCCEEDED"


def test_held_action_denied(client: httpx.Client, refund_agent_token: str) -> None:
    resp = _post_refund(client, refund_agent_token, f"hold-deny-{uuid.uuid4()}", 30000)
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "HELD"

    deny_resp = client.post(
        f"/api/v1/admin/actions/{data['action_id']}/deny",
        json={"reason": "does not look right"},
        headers={**OPERATOR_HEADERS, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert deny_resp.status_code == 200
    denied = deny_resp.json()
    assert denied["decision"] == "DENY"
    assert denied["status"] == "DENIED"
    assert denied["reason_code"] == "OPERATOR_DENIED"


def test_stale_context_after_revoke_rejects_approval(client: httpx.Client, refund_agent_token: str) -> None:
    resp = _post_refund(client, refund_agent_token, f"hold-stale-{uuid.uuid4()}", 30000)
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "HELD"

    agent_id = _agent_id(client, "refund-agent-v1")
    try:
        revoke_resp = client.post(
            f"/api/v1/admin/agents/{agent_id}/revoke",
            json={"reason": "simulate control change mid-approval"},
            headers={**OPERATOR_HEADERS, "Idempotency-Key": str(uuid.uuid4())},
        )
        assert revoke_resp.status_code == 200

        approve_resp = client.post(
            f"/api/v1/admin/actions/{data['action_id']}/approve",
            json={"reason": "approve anyway"},
            headers={**OPERATOR_HEADERS, "Idempotency-Key": str(uuid.uuid4())},
        )
        assert approve_resp.status_code == 200
        approved = approve_resp.json()
        assert approved["status"] == "DENIED"
        assert approved["reason_code"] == "STALE_CONTEXT_RECHECK_REQUIRED"
    finally:
        client.post(
            f"/api/v1/admin/agents/{agent_id}/restore",
            json={"reason": "governance test cleanup"},
            headers={**OPERATOR_HEADERS, "Idempotency-Key": str(uuid.uuid4())},
        )


def test_fleet_halt_denies_new_requests_then_resume_restores(client: httpx.Client, refund_agent_token: str) -> None:
    try:
        halt_resp = client.post(
            "/api/v1/admin/fleet/halt",
            json={"reason": "governance test halt"},
            headers={**OPERATOR_HEADERS, "Idempotency-Key": str(uuid.uuid4())},
        )
        assert halt_resp.status_code == 200
        assert halt_resp.json()["run_state"] == "HALTED"

        resp = _post_refund(client, refund_agent_token, f"halted-{uuid.uuid4()}", 1000)
        assert resp.status_code == 201
        data = resp.json()
        assert data["decision"] == "DENY"
        assert data["reason_code"] == "FLEET_HALTED"
    finally:
        resume_resp = client.post(
            "/api/v1/admin/fleet/resume",
            json={"reason": "governance test cleanup"},
            headers={**OPERATOR_HEADERS, "Idempotency-Key": str(uuid.uuid4())},
        )
        assert resume_resp.status_code == 200
        assert resume_resp.json()["run_state"] == "RUNNING"


def _run_sql_inside_postgres(sql: str) -> str:
    """Runs a SQL statement inside the running postgres container, used to
    simulate direct tampering with a historical audit_events row -- the way
    checkpoint verification is meant to catch, since no application code path
    can mutate audit_events."""
    result = subprocess.run(
        ["docker", "compose", "exec", "-T", "postgres", "psql", "-U", "mandateguard_admin", "-d", "mandateguard", "-c", sql],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.stdout + result.stderr


def test_audit_checkpoint_detects_tampering(client: httpx.Client, refund_agent_token: str) -> None:
    resp = _post_refund(client, refund_agent_token, f"checkpoint-source-{uuid.uuid4()}", 1000)
    assert resp.status_code == 201
    action_id = resp.json()["action_id"]
    stream_id = f"action:{action_id}"

    checkpoint_resp = client.post("/api/v1/admin/audit/checkpoints", headers=OPERATOR_HEADERS)
    assert checkpoint_resp.status_code == 200
    checkpoint_id = checkpoint_resp.json()["checkpoint_id"]

    verify_resp = client.get(f"/api/v1/admin/audit/checkpoints/{checkpoint_id}/verify", headers=OPERATOR_HEADERS)
    assert verify_resp.status_code == 200
    assert verify_resp.json()["tampered"] is False

    _run_sql_inside_postgres(
        f"UPDATE broker.audit_events SET actor = 'tampered-actor' "
        f"WHERE stream_id = '{stream_id}' AND sequence = 1"
    )

    verify_after_tamper = client.get(f"/api/v1/admin/audit/checkpoints/{checkpoint_id}/verify", headers=OPERATOR_HEADERS)
    assert verify_after_tamper.status_code == 200
    result = verify_after_tamper.json()
    assert result["tampered"] is True
    assert any(s["stream_id"] == stream_id and not s["chain_intact"] for s in result["streams"])


def test_policy_replay_is_read_only_and_reflects_candidate_config(client: httpx.Client, refund_agent_token: str) -> None:
    resp = _post_refund(client, refund_agent_token, f"replay-source-{uuid.uuid4()}", 30000)
    assert resp.status_code == 201
    action_id = resp.json()["action_id"]
    before_status = client.get(f"/api/v1/actions/{action_id}", headers={"Authorization": f"Bearer {refund_agent_token}"}).json()

    base_config = {
        "schema_version": "1.0",
        "policy_version": "replay-candidate-v1",
        "supported_action": "refund_payment",
        "supported_currency": "USD",
        "approval_role": "REFUND_APPROVER",
        "fleet_budget_scope": "refund-fleet",
        "risk_modes": {
            "NORMAL": {"approval_threshold_minor": 1000000, "hard_max_minor": 2000000},
            "ELEVATED": {"approval_threshold_minor": 10000, "hard_max_minor": 50000},
        },
        "agents": {
            "refund-agent-v1": {
                "enabled": True,
                "allowed_actions": ["refund_payment"],
                "customer_scopes": ["customer-demo-001", "customer-demo-002"],
            },
        },
    }

    replay_resp = client.post(
        "/api/v1/admin/policy/replay",
        json={"candidate_config": base_config},
        headers=OPERATOR_HEADERS,
    )
    assert replay_resp.status_code == 200
    run = replay_resp.json()
    assert run["status"] == "COMPLETED"
    assert run["summary"]["evaluated"] >= 1

    run_detail = client.get(f"/api/v1/admin/policy/replay/{run['run_id']}", headers=OPERATOR_HEADERS).json()
    result_for_action = next((r for r in run_detail["results"] if r["action_id"] == action_id), None)
    assert result_for_action is not None
    assert result_for_action["baseline_decision"] == "HOLD"
    assert result_for_action["candidate_decision"] == "ALLOW"
    assert result_for_action["changed"] is True

    after_status = client.get(f"/api/v1/actions/{action_id}", headers={"Authorization": f"Bearer {refund_agent_token}"}).json()
    assert after_status == before_status
