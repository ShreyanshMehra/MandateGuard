"""Deterministic demo scenarios for MandateGuard (Milestone 6).

Runs the eleven scenarios from HANDOFF.md section 11 against the live
docker-compose stack, resetting dev state first so a rerun produces the same
key results every time. Each scenario prints PASS/FAIL plus the key metric a
judge would want to see; nothing here is a pytest replacement -- it's a
narrated, repeatable walkthrough of the same guarantees tests/ verifies.

Usage:
    docker compose up -d
    python scripts/run_scenarios.py            # run all eleven, in order
    python scripts/run_scenarios.py held_approval elevated_risk

Requires: BROKER_URL (default http://localhost:8000), OPERATOR_TOKEN
(default dev_operator_token_change_me), and a repo checkout so
secrets/dev/*.pem and scripts/reset_dev_state.sql are reachable.
"""

import json
import os
import subprocess
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import jwt

REPO_ROOT = Path(__file__).resolve().parent.parent
SECRETS_DIR = REPO_ROOT / "secrets" / "dev"
BROKER_URL = os.environ.get("BROKER_URL", "http://localhost:8000")
OPERATOR_TOKEN = os.environ.get("OPERATOR_TOKEN", "dev_operator_token_change_me")
OPERATOR_HEADERS = {"X-Operator-Token": OPERATOR_TOKEN}

REFUND_AGENT_KEY_ID = "refund-agent-v1:dev-2026-07"
REFUND_AGENT_KEY_PATH = SECRETS_DIR / "refund-agent-v1__refund-agent-v1_dev-2026-07.pem"
REVOKED_AGENT_KEY_ID = "revoked-demo-agent-v1:dev-2026-07"
REVOKED_AGENT_KEY_PATH = SECRETS_DIR / "revoked-demo-agent-v1__revoked-demo-agent-v1_dev-2026-07.pem"

PAYMENT_001 = "payment-demo-001"
PAYMENT_003 = "payment-demo-003"
EXECUTION_PAYMENT = "payment-demo-004"


def _mint_token(agent_id: str, key_id: str, key_path: Path, ttl_seconds: int = 120) -> str:
    now = int(time.time())
    return jwt.encode(
        {"sub": agent_id, "iat": now, "exp": now + ttl_seconds, "jti": str(uuid.uuid4())},
        key=key_path.read_bytes(),
        algorithm="EdDSA",
        headers={"kid": key_id},
    )


def _client() -> httpx.Client:
    return httpx.Client(base_url=BROKER_URL, timeout=15.0)


def _post_refund(client: httpx.Client, token: str, idempotency_key: str, payment_id: str, amount_minor: int) -> httpx.Response:
    return client.post(
        "/api/v1/refunds",
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": idempotency_key},
        json={"payment_id": payment_id, "amount_minor": amount_minor, "currency": "USD", "reason_code": "CUSTOMER_REQUEST"},
    )


def _run_inside_broker_container(snippet: str) -> str:
    result = subprocess.run(
        ["docker", "compose", "exec", "-T", "broker", "python", "-c", snippet],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=30,
    )
    return result.stdout + result.stderr


def _run_sql_inside_postgres(sql: str) -> str:
    result = subprocess.run(
        ["docker", "compose", "exec", "-T", "postgres", "psql", "-U", "mandateguard_admin", "-d", "mandateguard", "-c", sql],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=30,
    )
    return result.stdout + result.stderr


def reset_dev_state() -> None:
    sql = (REPO_ROOT / "scripts" / "reset_dev_state.sql").read_text()
    result = subprocess.run(
        ["docker", "compose", "exec", "-T", "postgres", "psql", "-U", "mandateguard_admin", "-d", "mandateguard"],
        cwd=REPO_ROOT, input=sql, capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"reset_dev_state.sql failed:\n{result.stdout}\n{result.stderr}")


class Scenario:
    def __init__(self, name: str, description: str, fn):
        self.name = name
        self.description = description
        self.fn = fn


def scenario_normal_refund() -> dict:
    with _client() as client:
        token = _mint_token("refund-agent-v1", REFUND_AGENT_KEY_ID, REFUND_AGENT_KEY_PATH)
        resp = _post_refund(client, token, f"scenario-normal-{uuid.uuid4()}", EXECUTION_PAYMENT, 1000)
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["decision"] == "ALLOW" and data["status"] == "SUCCEEDED", data
        return {"action_id": data["action_id"], "status": data["status"]}


def scenario_held_approval() -> dict:
    with _client() as client:
        token = _mint_token("refund-agent-v1", REFUND_AGENT_KEY_ID, REFUND_AGENT_KEY_PATH)
        resp = _post_refund(client, token, f"scenario-hold-{uuid.uuid4()}", EXECUTION_PAYMENT, 30000)
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["status"] == "HELD", data

        approve = client.post(
            f"/api/v1/admin/actions/{data['action_id']}/approve",
            json={"reason": "scenario: operator approves"},
            headers={**OPERATOR_HEADERS, "Idempotency-Key": str(uuid.uuid4())},
        )
        assert approve.status_code == 200, approve.text
        approved = approve.json()
        assert approved["status"] == "SUCCEEDED", approved
        return {"action_id": data["action_id"], "held_reason": data["reason_code"], "final_status": approved["status"]}


def scenario_permission_denial() -> dict:
    with _client() as client:
        token = _mint_token("revoked-demo-agent-v1", REVOKED_AGENT_KEY_ID, REVOKED_AGENT_KEY_PATH)
        resp = _post_refund(client, token, f"scenario-denied-{uuid.uuid4()}", PAYMENT_001, 5000)
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["decision"] == "DENY" and data["reason_code"] == "AGENT_INACTIVE", data
        return {"action_id": data["action_id"], "reason_code": data["reason_code"]}


def scenario_direct_bypass() -> dict:
    out = _run_inside_broker_container(
        """
import os, uuid, httpx
r = httpx.post('http://mock-bank:8000/internal/v1/refunds',
    headers={'X-Broker-Service-Token': os.environ['BROKER_SERVICE_TOKEN']},
    json={'request_id': str(uuid.uuid4()), 'payment_id': 'payment-demo-003', 'amount_minor': 500, 'currency': 'USD'})
print(r.status_code, r.json()['detail']['error']['code'])
"""
    )
    assert "401 PERMIT_REQUIRED" in out, out
    return {"probe_output": out.strip()}


def scenario_concurrent_burst() -> dict:
    with _client() as client:
        token = _mint_token("refund-agent-v1", REFUND_AGENT_KEY_ID, REFUND_AGENT_KEY_PATH)
        usage = client.get("/internal/v1/budget-usage/fleet/refund-fleet").json()
        headroom = usage["cap_minor"] - usage["usage_minor"]
        payment_balance = client.get(f"/internal/v1/payment-balance/{EXECUTION_PAYMENT}").json()["refundable_remaining_minor"]
        headroom = min(headroom, payment_balance)
        assert headroom >= 10, "insufficient headroom -- run this scenario right after a reset"

        amount = min(20000, max(1, headroom // 10))
        expected_successes = headroom // amount
        request_count = expected_successes + 10

        def fire(_: int) -> httpx.Response:
            with _client() as c:
                return _post_refund(c, token, f"scenario-burst-{uuid.uuid4()}", EXECUTION_PAYMENT, amount)

        with ThreadPoolExecutor(max_workers=request_count) as pool:
            responses = list(pool.map(fire, range(request_count)))

        succeeded = [r for r in responses if r.status_code == 201 and r.json()["status"] == "SUCCEEDED"]
        assert len(succeeded) == expected_successes, f"expected {expected_successes}, got {len(succeeded)}"
        return {"requests_fired": request_count, "cap_allowed": expected_successes, "succeeded": len(succeeded)}


def scenario_elevated_risk() -> dict:
    with _client() as client:
        token = _mint_token("refund-agent-v1", REFUND_AGENT_KEY_ID, REFUND_AGENT_KEY_PATH)

        under_normal = _post_refund(client, token, f"scenario-risk-before-{uuid.uuid4()}", EXECUTION_PAYMENT, 15000).json()
        assert under_normal["decision"] == "ALLOW", under_normal

        set_risk = client.post(
            "/api/v1/admin/fleet/risk-mode",
            json={"mode": "ELEVATED", "reason": "scenario: tighten for elevated risk"},
            headers={**OPERATOR_HEADERS, "Idempotency-Key": str(uuid.uuid4())},
        )
        assert set_risk.status_code == 200 and set_risk.json()["risk_mode"] == "ELEVATED", set_risk.text

        try:
            under_elevated = _post_refund(client, token, f"scenario-risk-after-{uuid.uuid4()}", EXECUTION_PAYMENT, 15000).json()
            assert under_elevated["decision"] == "HOLD", under_elevated
        finally:
            client.post(
                "/api/v1/admin/fleet/risk-mode",
                json={"mode": "NORMAL", "reason": "scenario cleanup"},
                headers={**OPERATOR_HEADERS, "Idempotency-Key": str(uuid.uuid4())},
            )

        return {"decision_under_normal": under_normal["decision"], "decision_under_elevated": under_elevated["decision"]}


def scenario_fleet_halt() -> dict:
    with _client() as client:
        token = _mint_token("refund-agent-v1", REFUND_AGENT_KEY_ID, REFUND_AGENT_KEY_PATH)
        halt = client.post(
            "/api/v1/admin/fleet/halt",
            json={"reason": "scenario: halt under load"},
            headers={**OPERATOR_HEADERS, "Idempotency-Key": str(uuid.uuid4())},
        )
        assert halt.status_code == 200 and halt.json()["run_state"] == "HALTED", halt.text
        try:
            during_halt = _post_refund(client, token, f"scenario-halted-{uuid.uuid4()}", EXECUTION_PAYMENT, 1000).json()
            assert during_halt["decision"] == "DENY" and during_halt["reason_code"] == "FLEET_HALTED", during_halt
        finally:
            resume = client.post(
                "/api/v1/admin/fleet/resume",
                json={"reason": "scenario cleanup"},
                headers={**OPERATOR_HEADERS, "Idempotency-Key": str(uuid.uuid4())},
            )
            assert resume.status_code == 200 and resume.json()["run_state"] == "RUNNING", resume.text
        return {"denied_reason": during_halt["reason_code"]}


def scenario_duplicate_idempotency() -> dict:
    with _client() as client:
        token = _mint_token("refund-agent-v1", REFUND_AGENT_KEY_ID, REFUND_AGENT_KEY_PATH)
        key = f"scenario-dup-{uuid.uuid4()}"
        first = _post_refund(client, token, key, EXECUTION_PAYMENT, 1000).json()
        second = _post_refund(client, token, key, EXECUTION_PAYMENT, 1000).json()
        assert first["action_id"] == second["action_id"], (first, second)
        return {"action_id": first["action_id"], "replay_matched": True}


_PERMIT_PROBE_PREAMBLE = """
import os, time, uuid
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


def scenario_permit_replay() -> dict:
    out = _run_inside_broker_container(
        _PERMIT_PROBE_PREAMBLE
        + """
token, jti = make_permit()
first = httpx.post('http://mock-bank:8000/internal/v1/refunds',
    headers={'X-Broker-Service-Token': os.environ['BROKER_SERVICE_TOKEN'], 'X-Action-Permit': token},
    json={'request_id': str(uuid.uuid4()), 'payment_id': 'payment-demo-003', 'amount_minor': 500, 'currency': 'USD'})
second = httpx.post('http://mock-bank:8000/internal/v1/refunds',
    headers={'X-Broker-Service-Token': os.environ['BROKER_SERVICE_TOKEN'], 'X-Action-Permit': token},
    json={'request_id': str(uuid.uuid4()), 'payment_id': 'payment-demo-003', 'amount_minor': 500, 'currency': 'USD'})
print(first.status_code, second.status_code, second.json()['detail']['error']['code'])
"""
    )
    assert "200 409 PERMIT_ALREADY_USED" in out, out
    return {"probe_output": out.strip()}


def scenario_audit_tamper() -> dict:
    with _client() as client:
        token = _mint_token("refund-agent-v1", REFUND_AGENT_KEY_ID, REFUND_AGENT_KEY_PATH)
        resp = _post_refund(client, token, f"scenario-tamper-source-{uuid.uuid4()}", EXECUTION_PAYMENT, 1000).json()
        action_id = resp["action_id"]
        stream_id = f"action:{action_id}"

        checkpoint = client.post("/api/v1/admin/audit/checkpoints", headers=OPERATOR_HEADERS).json()
        before = client.get(f"/api/v1/admin/audit/checkpoints/{checkpoint['checkpoint_id']}/verify", headers=OPERATOR_HEADERS).json()
        assert before["tampered"] is False, before

        _run_sql_inside_postgres(f"UPDATE broker.audit_events SET actor = 'tampered-actor' WHERE stream_id = '{stream_id}' AND sequence = 1")

        after = client.get(f"/api/v1/admin/audit/checkpoints/{checkpoint['checkpoint_id']}/verify", headers=OPERATOR_HEADERS).json()
        assert after["tampered"] is True, after
        return {"checkpoint_id": checkpoint["checkpoint_id"], "tampered_before": before["tampered"], "tampered_after": after["tampered"]}


def scenario_policy_replay() -> dict:
    with _client() as client:
        token = _mint_token("refund-agent-v1", REFUND_AGENT_KEY_ID, REFUND_AGENT_KEY_PATH)
        resp = _post_refund(client, token, f"scenario-replay-source-{uuid.uuid4()}", EXECUTION_PAYMENT, 30000).json()
        action_id = resp["action_id"]
        assert resp["decision"] == "HOLD", resp

        candidate_config = {
            "schema_version": "1.0", "policy_version": "scenario-candidate-v1",
            "supported_action": "refund_payment", "supported_currency": "USD",
            "approval_role": "REFUND_APPROVER", "fleet_budget_scope": "refund-fleet",
            "risk_modes": {
                "NORMAL": {"approval_threshold_minor": 1000000, "hard_max_minor": 2000000},
                "ELEVATED": {"approval_threshold_minor": 10000, "hard_max_minor": 50000},
            },
            "agents": {"refund-agent-v1": {"enabled": True, "allowed_actions": ["refund_payment"], "customer_scopes": ["customer-demo-001", "customer-demo-002"]}},
        }
        run = client.post("/api/v1/admin/policy/replay", json={"candidate_config": candidate_config}, headers=OPERATOR_HEADERS).json()
        assert run["status"] == "COMPLETED", run
        detail = client.get(f"/api/v1/admin/policy/replay/{run['run_id']}", headers=OPERATOR_HEADERS).json()
        result = next(r for r in detail["results"] if r["action_id"] == action_id)
        assert result["baseline_decision"] == "HOLD" and result["candidate_decision"] == "ALLOW", result

        live_after = client.get(f"/api/v1/admin/actions/{action_id}", headers=OPERATOR_HEADERS).json()
        assert live_after["state"] == "HELD", live_after
        return {"run_id": run["run_id"], "baseline": result["baseline_decision"], "candidate": result["candidate_decision"], "live_state_unchanged": live_after["state"]}


# Numbered per HANDOFF.md's Milestone 6 scenario list, but executed in an
# order chosen for shared-state determinism within a single run: the fleet
# budget-consuming scenarios run first while headroom is large and known,
# and the concurrent burst (#5, which deliberately maxes out whatever
# headroom remains) runs last so no later scenario depends on budget it
# might have consumed. This keeps a full "reset then run all" reproducible
# without needing per-scenario isolation.
SCENARIOS = [
    Scenario("normal_refund", "1. Normal refund", scenario_normal_refund),
    Scenario("held_approval", "2. Held refund and approval", scenario_held_approval),
    Scenario("permission_denial", "3. Permission denial", scenario_permission_denial),
    Scenario("direct_bypass", "4. Direct-bank bypass rejection", scenario_direct_bypass),
    Scenario("elevated_risk", "6. Elevated-risk tightening", scenario_elevated_risk),
    Scenario("fleet_halt", "7. Fleet halt under load", scenario_fleet_halt),
    Scenario("duplicate_idempotency", "8. Duplicate idempotency request", scenario_duplicate_idempotency),
    Scenario("permit_replay", "9. Permit replay", scenario_permit_replay),
    Scenario("audit_tamper", "10. Audit tamper detection", scenario_audit_tamper),
    Scenario("policy_replay", "11. Candidate policy replay", scenario_policy_replay),
    Scenario("concurrent_burst", "5. Concurrent split-refund burst", scenario_concurrent_burst),
]


def main() -> None:
    requested = sys.argv[1:]
    scenarios = [s for s in SCENARIOS if not requested or s.name in requested]
    if not scenarios:
        print(f"No matching scenarios. Available: {', '.join(s.name for s in SCENARIOS)}")
        raise SystemExit(2)

    print("Resetting dev state...")
    reset_dev_state()

    failures = 0
    for scenario in scenarios:
        try:
            result = scenario.fn()
            print(f"PASS  {scenario.description}")
            print(f"      {json.dumps(result)}")
        except AssertionError as exc:
            failures += 1
            print(f"FAIL  {scenario.description}")
            print(f"      {exc}")
        except Exception as exc:  # noqa: BLE001 -- surface any unexpected error per scenario, keep going
            failures += 1
            print(f"ERROR {scenario.description}")
            print(f"      {type(exc).__name__}: {exc}")

    print()
    print(f"{len(scenarios) - failures}/{len(scenarios)} scenarios passed.")
    raise SystemExit(1 if failures else 0)


if __name__ == "__main__":
    main()
