"""Milestone 4 acceptance tests: atomic budgets, permits and bank execution.

Run against the live docker-compose stack. Before running, reset dev state
so bank balances and budget usage start from the seeded baseline:

    docker cp scripts/reset_dev_state.sql mandateguard-postgres-1:/tmp/reset_dev_state.sql
    docker compose exec -T postgres psql -U mandateguard_admin -d mandateguard -f /tmp/reset_dev_state.sql

Usage: BROKER_URL=http://localhost:8000 pytest tests/test_budget_execution.py
"""

import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import jwt
import pytest

BROKER_URL = os.environ.get("BROKER_URL", "http://localhost:8000")
SECRETS_DIR = Path(__file__).resolve().parent.parent / "secrets" / "dev"

REFUND_AGENT_KEY_ID = "refund-agent-v1:dev-2026-07"
REFUND_AGENT_KEY_PATH = SECRETS_DIR / "refund-agent-v1__refund-agent-v1_dev-2026-07.pem"

EXECUTION_PAYMENT = "payment-demo-004"  # customer-demo-002, USD, refundable 5000000 -- dedicated to M4 execution tests


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
        json={"payment_id": EXECUTION_PAYMENT, "amount_minor": amount_minor, "currency": "USD", "reason_code": "CUSTOMER_REQUEST"},
    )


def test_valid_request_executes_and_settles(client: httpx.Client, refund_agent_token: str) -> None:
    resp = _post_refund(client, refund_agent_token, f"exec-{uuid.uuid4()}", 1000)
    assert resp.status_code == 201
    data = resp.json()
    assert data["decision"] == "ALLOW"
    assert data["status"] == "SUCCEEDED"


def test_concurrent_requests_never_overshoot_the_fleet_budget(client: httpx.Client, refund_agent_token: str) -> None:
    # Bound the per-request amount by whichever real cap is tighter right now
    # (fleet daily budget or the demo payment's live refundable balance) so
    # the burst always lands roughly ten successes against a ten-request cap,
    # per the Milestone 4 acceptance gate, regardless of state left over from
    # earlier test runs against this shared dev stack.
    usage = client.get("/internal/v1/budget-usage/fleet/refund-fleet").json()
    fleet_headroom = usage["cap_minor"] - usage["usage_minor"]
    payment_balance = client.get(f"/internal/v1/payment-balance/{EXECUTION_PAYMENT}").json()["refundable_remaining_minor"]
    headroom = min(fleet_headroom, payment_balance)
    assert headroom >= 10, "run scripts/reset_dev_state.sql before this test -- demo budget/balance is exhausted"

    amount = min(20000, max(1, headroom // 10))  # stay well under the 25000 NORMAL approval threshold
    expected_successes = headroom // amount
    request_count = expected_successes + 10  # fire well past the cap to prove no overshoot

    tokens_and_keys = [(refund_agent_token, f"burst-{uuid.uuid4()}") for _ in range(request_count)]

    def fire(token_key: tuple[str, str]) -> httpx.Response:
        token, key = token_key
        with httpx.Client(base_url=BROKER_URL, timeout=15.0) as c:
            return _post_refund(c, token, key, amount)

    with ThreadPoolExecutor(max_workers=request_count) as pool:
        responses = list(pool.map(fire, tokens_and_keys))

    bodies = [r.json() for r in responses if r.status_code == 201]
    succeeded = [b for b in bodies if b["status"] == "SUCCEEDED"]
    not_succeeded = [b for b in bodies if b["status"] != "SUCCEEDED"]

    assert len(succeeded) == expected_successes, (
        f"expected exactly {expected_successes} successes (never more -- zero overshoot), "
        f"got {len(succeeded)}: {[b['status'] for b in bodies]}"
    )
    assert len(not_succeeded) == request_count - expected_successes

    final_usage = client.get("/internal/v1/budget-usage/fleet/refund-fleet").json()
    assert final_usage["usage_minor"] <= final_usage["cap_minor"]


def _run_inside_broker_container(snippet: str) -> str:
    """Runs a Python snippet inside the already-running broker container, which
    has network access to mock-bank and the mounted permit signing key. Used to
    probe the mock bank's execution endpoint directly -- bypassing all broker
    logic -- the way an attacker on the internal network would, since mock-bank
    is deliberately not published to the host (docker-compose.yml)."""
    import subprocess

    result = subprocess.run(
        ["docker", "compose", "exec", "-T", "broker", "python", "-c", snippet],
        cwd=Path(__file__).resolve().parent.parent,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.stdout + result.stderr


_PROBE_PREAMBLE = """
import base64, json, os, time, uuid
import httpx, jwt
from cryptography.hazmat.primitives import serialization
key = serialization.load_pem_private_key(open(os.environ['BROKER_PERMIT_KEY_PATH'], 'rb').read(), password=None)
def make_permit(**overrides):
    now = int(time.time())
    claims = {
        'jti': str(uuid.uuid4()), 'action_id': str(uuid.uuid4()),
        'payment_id': 'payment-demo-003', 'amount_minor': 500, 'currency': 'USD',
        'iat': now, 'exp': now + 60,
    }
    claims.update(overrides)
    return jwt.encode(claims, key=key, algorithm='EdDSA', headers={'kid': os.environ['BROKER_PERMIT_KEY_ID']}), claims['jti']
"""


def test_direct_bank_call_without_permit_is_rejected() -> None:
    out = _run_inside_broker_container(
        _PROBE_PREAMBLE
        + """
r = httpx.post('http://mock-bank:8000/internal/v1/refunds',
    headers={'X-Broker-Service-Token': os.environ['BROKER_SERVICE_TOKEN']},
    json={'request_id': str(uuid.uuid4()), 'payment_id': 'payment-demo-003', 'amount_minor': 500, 'currency': 'USD'})
print(r.status_code, r.json()['detail']['error']['code'])
"""
    )
    assert "401 PERMIT_REQUIRED" in out, out


def test_tampered_permit_amount_is_rejected() -> None:
    out = _run_inside_broker_container(
        _PROBE_PREAMBLE
        + """
token, jti = make_permit()
r = httpx.post('http://mock-bank:8000/internal/v1/refunds',
    headers={'X-Broker-Service-Token': os.environ['BROKER_SERVICE_TOKEN'], 'X-Action-Permit': token},
    json={'request_id': str(uuid.uuid4()), 'payment_id': 'payment-demo-002', 'amount_minor': 999999, 'currency': 'USD'})
print(r.status_code, r.json()['detail']['error']['code'])
"""
    )
    assert "401 PERMIT_INVALID" in out, out


def test_permit_replay_is_rejected_and_creates_no_second_refund() -> None:
    request_id = str(uuid.uuid4())
    out = _run_inside_broker_container(
        _PROBE_PREAMBLE
        + f"""
token, jti = make_permit()
first = httpx.post('http://mock-bank:8000/internal/v1/refunds',
    headers={{'X-Broker-Service-Token': os.environ['BROKER_SERVICE_TOKEN'], 'X-Action-Permit': token}},
    json={{'request_id': str(uuid.uuid4()), 'payment_id': 'payment-demo-003', 'amount_minor': 500, 'currency': 'USD'}})
second = httpx.post('http://mock-bank:8000/internal/v1/refunds',
    headers={{'X-Broker-Service-Token': os.environ['BROKER_SERVICE_TOKEN'], 'X-Action-Permit': token}},
    json={{'request_id': str(uuid.uuid4()), 'payment_id': 'payment-demo-003', 'amount_minor': 500, 'currency': 'USD'}})
print(first.status_code, second.status_code, second.json()['detail']['error']['code'])
"""
    )
    assert "200 409 PERMIT_ALREADY_USED" in out, out
