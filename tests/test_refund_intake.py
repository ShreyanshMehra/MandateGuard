"""Milestone 3 acceptance tests for POST /api/v1/refunds.

Run against the live docker-compose stack (broker on localhost:8000, seeded
by database/migrations/versions/0002_seed_baseline_data.py). Exercises the
acceptance gate from HANDOFF.md section 11: valid, forged, expired,
wrong-currency, revoked and out-of-scope requests must each produce the
expected safe result. "Wrong-action" is not reachable through the public API
(RefundRequest has no action field -- refund_payment is the only action this
endpoint can express); that branch of the policy is covered instead by
policies/refund_policy_test.rego's unpermitted_action / unsupported_action
cases.

Usage: BROKER_URL=http://localhost:8000 pytest tests/test_refund_intake.py
"""

import base64
import os
import time
import uuid
from pathlib import Path

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

BROKER_URL = os.environ.get("BROKER_URL", "http://localhost:8000")
SECRETS_DIR = Path(__file__).resolve().parent.parent / "secrets" / "dev"

REFUND_AGENT_KEY_ID = "refund-agent-v1:dev-2026-07"
REFUND_AGENT_KEY_PATH = SECRETS_DIR / "refund-agent-v1__refund-agent-v1_dev-2026-07.pem"

REVOKED_AGENT_KEY_ID = "revoked-demo-agent-v1:dev-2026-07"
REVOKED_AGENT_KEY_PATH = SECRETS_DIR / "revoked-demo-agent-v1__revoked-demo-agent-v1_dev-2026-07.pem"

PAYMENT_001 = "payment-demo-001"  # customer-demo-001, USD, refundable 50000 -- in scope for refund-agent-v1
PAYMENT_002 = "payment-demo-002"  # customer-demo-002, USD, refundable 200000 -- in scope for refund-agent-v1
PAYMENT_003 = "payment-demo-003"  # customer-demo-999, USD, refundable 10000 -- out of scope for refund-agent-v1


def _mint_token(agent_id: str, key_id: str, key_path: Path, ttl_seconds: int = 120) -> str:
    now = int(time.time())
    return jwt.encode(
        {"sub": agent_id, "iat": now, "exp": now + ttl_seconds, "jti": str(uuid.uuid4())},
        key=key_path.read_bytes(),
        algorithm="EdDSA",
        headers={"kid": key_id},
    )


def _forged_token(agent_id: str, key_id: str) -> str:
    """Sign with a freshly generated key that has never been registered, but
    claim a real, on-file key_id -- exercises signature verification failure
    rather than an unknown-key lookup failure."""
    now = int(time.time())
    bogus_key = Ed25519PrivateKey.generate()
    from cryptography.hazmat.primitives import serialization

    pem = bogus_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return jwt.encode(
        {"sub": agent_id, "iat": now, "exp": now + 120, "jti": str(uuid.uuid4())},
        key=pem,
        algorithm="EdDSA",
        headers={"kid": key_id},
    )


@pytest.fixture(scope="module")
def client() -> httpx.Client:
    with httpx.Client(base_url=BROKER_URL, timeout=10.0) as c:
        yield c


@pytest.fixture()
def refund_agent_token() -> str:
    return _mint_token("refund-agent-v1", REFUND_AGENT_KEY_ID, REFUND_AGENT_KEY_PATH)


def _post_refund(client: httpx.Client, token: str, idempotency_key: str, body: dict, auth: bool = True) -> httpx.Response:
    headers = {"Idempotency-Key": idempotency_key}
    if auth:
        headers["Authorization"] = f"Bearer {token}"
    return client.post("/api/v1/refunds", headers=headers, json=body)


def _refund_body(payment_id: str, amount_minor: int, currency: str = "USD") -> dict:
    return {
        "payment_id": payment_id,
        "amount_minor": amount_minor,
        "currency": currency,
        "reason_code": "CUSTOMER_REQUEST",
    }


def test_valid_request_is_allowed(client: httpx.Client, refund_agent_token: str) -> None:
    resp = _post_refund(
        client, refund_agent_token, f"valid-{uuid.uuid4()}", _refund_body(PAYMENT_001, 5000)
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["decision"] == "ALLOW"
    assert data["reason_code"] == "REQUEST_ALLOWED"
    assert data["status"] == "RECEIVED"


def test_idempotent_replay_returns_same_action(client: httpx.Client, refund_agent_token: str) -> None:
    key = f"idem-{uuid.uuid4()}"
    body = _refund_body(PAYMENT_001, 5000)
    first = _post_refund(client, refund_agent_token, key, body)
    second = _post_refund(client, refund_agent_token, key, body)
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["action_id"] == second.json()["action_id"]


def test_idempotency_key_conflict_on_different_body(client: httpx.Client, refund_agent_token: str) -> None:
    key = f"idem-conflict-{uuid.uuid4()}"
    _post_refund(client, refund_agent_token, key, _refund_body(PAYMENT_001, 5000))
    conflict = _post_refund(client, refund_agent_token, key, _refund_body(PAYMENT_001, 6000))
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_KEY_CONFLICT"


def test_missing_idempotency_key_is_rejected(client: httpx.Client, refund_agent_token: str) -> None:
    resp = client.post(
        "/api/v1/refunds",
        headers={"Authorization": f"Bearer {refund_agent_token}"},
        json=_refund_body(PAYMENT_001, 5000),
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "IDEMPOTENCY_KEY_REQUIRED"


def test_forged_signature_is_rejected(client: httpx.Client) -> None:
    token = _forged_token("refund-agent-v1", REFUND_AGENT_KEY_ID)
    resp = _post_refund(client, token, f"forged-{uuid.uuid4()}", _refund_body(PAYMENT_001, 5000))
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "AGENT_IDENTITY_INVALID"


def test_expired_token_is_rejected(client: httpx.Client) -> None:
    token = _mint_token("refund-agent-v1", REFUND_AGENT_KEY_ID, REFUND_AGENT_KEY_PATH, ttl_seconds=-30)
    resp = _post_refund(client, token, f"expired-{uuid.uuid4()}", _refund_body(PAYMENT_001, 5000))
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "AGENT_IDENTITY_INVALID"


def test_unknown_key_id_is_rejected(client: httpx.Client) -> None:
    token = _mint_token("refund-agent-v1", "no-such-key:dev-2026-07", REFUND_AGENT_KEY_PATH)
    resp = _post_refund(client, token, f"unknownkid-{uuid.uuid4()}", _refund_body(PAYMENT_001, 5000))
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "AGENT_IDENTITY_INVALID"


def test_missing_authorization_header_is_rejected(client: httpx.Client) -> None:
    resp = _post_refund(client, "", f"noauth-{uuid.uuid4()}", _refund_body(PAYMENT_001, 5000), auth=False)
    assert resp.status_code == 401


def test_wrong_currency_is_denied(client: httpx.Client, refund_agent_token: str) -> None:
    resp = _post_refund(
        client, refund_agent_token, f"wrongccy-{uuid.uuid4()}", _refund_body(PAYMENT_001, 5000, currency="EUR")
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["decision"] == "DENY"
    assert data["reason_code"] == "CURRENCY_MISMATCH"


def test_revoked_agent_is_denied(client: httpx.Client) -> None:
    token = _mint_token("revoked-demo-agent-v1", REVOKED_AGENT_KEY_ID, REVOKED_AGENT_KEY_PATH)
    resp = _post_refund(client, token, f"revoked-{uuid.uuid4()}", _refund_body(PAYMENT_001, 5000))
    assert resp.status_code == 201
    data = resp.json()
    assert data["decision"] == "DENY"
    assert data["reason_code"] == "AGENT_INACTIVE"


def test_out_of_scope_customer_is_denied(client: httpx.Client, refund_agent_token: str) -> None:
    resp = _post_refund(
        client, refund_agent_token, f"outofscope-{uuid.uuid4()}", _refund_body(PAYMENT_003, 5000)
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["decision"] == "DENY"
    assert data["reason_code"] == "CUSTOMER_SCOPE_MISMATCH"


def test_payment_not_found_is_denied(client: httpx.Client, refund_agent_token: str) -> None:
    resp = _post_refund(
        client, refund_agent_token, f"nopayment-{uuid.uuid4()}", _refund_body("payment-does-not-exist", 5000)
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["decision"] == "DENY"
    assert data["reason_code"] == "PAYMENT_NOT_FOUND"


def test_amount_exceeds_refundable_is_denied(client: httpx.Client, refund_agent_token: str) -> None:
    resp = _post_refund(
        client, refund_agent_token, f"exceedsrefundable-{uuid.uuid4()}", _refund_body(PAYMENT_001, 60000)
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["decision"] == "DENY"
    assert data["reason_code"] == "AMOUNT_EXCEEDS_REFUNDABLE"


def test_amount_above_approval_threshold_holds(client: httpx.Client, refund_agent_token: str) -> None:
    resp = _post_refund(
        client, refund_agent_token, f"hold-{uuid.uuid4()}", _refund_body(PAYMENT_001, 30000)
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["decision"] == "HOLD"
    assert data["reason_code"] == "APPROVAL_REQUIRED"
    assert data["status"] == "HELD"


def test_amount_above_hard_max_is_denied(client: httpx.Client, refund_agent_token: str) -> None:
    resp = _post_refund(
        client, refund_agent_token, f"hardmax-{uuid.uuid4()}", _refund_body(PAYMENT_002, 150000)
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["decision"] == "DENY"
    assert data["reason_code"] == "HARD_MAX_EXCEEDED"


def test_get_action_returns_own_action(client: httpx.Client, refund_agent_token: str) -> None:
    create = _post_refund(client, refund_agent_token, f"getown-{uuid.uuid4()}", _refund_body(PAYMENT_001, 5000))
    action_id = create.json()["action_id"]
    resp = client.get(f"/api/v1/actions/{action_id}", headers={"Authorization": f"Bearer {refund_agent_token}"})
    assert resp.status_code == 200
    assert resp.json()["action_id"] == action_id


def test_get_action_hides_other_agents_actions(client: httpx.Client, refund_agent_token: str) -> None:
    create = _post_refund(client, refund_agent_token, f"getother-{uuid.uuid4()}", _refund_body(PAYMENT_001, 5000))
    action_id = create.json()["action_id"]
    revoked_token = _mint_token("revoked-demo-agent-v1", REVOKED_AGENT_KEY_ID, REVOKED_AGENT_KEY_PATH)
    resp = client.get(f"/api/v1/actions/{action_id}", headers={"Authorization": f"Bearer {revoked_token}"})
    assert resp.status_code == 404


def test_get_nonexistent_action_is_not_found(client: httpx.Client, refund_agent_token: str) -> None:
    resp = client.get(
        f"/api/v1/actions/{uuid.uuid4()}", headers={"Authorization": f"Bearer {refund_agent_token}"}
    )
    assert resp.status_code == 404
