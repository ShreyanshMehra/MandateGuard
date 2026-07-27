"""Milestone 7 measurement run: latency, halt bound, replay duration, receipt
coverage and zero-overshoot confirmation, saved to a file so nothing in the
deck is an unsaved or irreproducible number (HANDOFF.md Milestone 7).

Resets dev state first, then:
  1. Fires SAMPLE_SIZE sequential low-value ALLOW requests, timing the OPA
     call (measured broker-side is not exposed, so this times the whole
     policy-evaluation leg via a dedicated OPA-only call) and the full
     end-to-end request separately, and reports p50/p95/p99 for both.
  2. Measures the fleet-halt commit-to-denial bound (same technique as
     tests/test_verification.py, repeated a few times for a stable max).
  3. Runs a policy-replay pass over whatever actions exist and times it.
  4. Computes receipt coverage: of all SUCCEEDED actions, what fraction have
     a verifiable receipt.
  5. Re-confirms zero budget overshoot from a small concurrent burst.

Usage:
    docker compose up -d
    python scripts/measure_performance.py

Writes docs/verification/PERFORMANCE.md.
"""

import json
import os
import statistics
import subprocess
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import httpx
import jwt

REPO_ROOT = Path(__file__).resolve().parent.parent
SECRETS_DIR = REPO_ROOT / "secrets" / "dev"
BROKER_URL = os.environ.get("BROKER_URL", "http://localhost:8000")
OPA_URL = os.environ.get("OPA_URL", "http://localhost:8181")
OPERATOR_TOKEN = os.environ.get("OPERATOR_TOKEN", "dev_operator_token_change_me")
OPERATOR_HEADERS = {"X-Operator-Token": OPERATOR_TOKEN}

REFUND_AGENT_KEY_ID = "refund-agent-v1:dev-2026-07"
REFUND_AGENT_KEY_PATH = SECRETS_DIR / "refund-agent-v1__refund-agent-v1_dev-2026-07.pem"
EXECUTION_PAYMENT = "payment-demo-004"

SAMPLE_SIZE = int(os.environ.get("PERF_SAMPLE_SIZE", "40"))
OUT_PATH = REPO_ROOT / "docs" / "verification" / "PERFORMANCE.md"


def _mint_token() -> str:
    now = int(time.time())
    return jwt.encode(
        {"sub": "refund-agent-v1", "iat": now, "exp": now + 300, "jti": str(uuid.uuid4())},
        key=REFUND_AGENT_KEY_PATH.read_bytes(),
        algorithm="EdDSA",
        headers={"kid": REFUND_AGENT_KEY_ID},
    )


def _reset_dev_state() -> None:
    subprocess.run(
        ["docker", "cp", str(REPO_ROOT / "scripts" / "reset_dev_state.sql"), "mandateguard-postgres-1:/tmp/reset_dev_state.sql"],
        check=True,
    )
    subprocess.run(
        ["docker", "compose", "exec", "-T", "postgres", "psql", "-U", "mandateguard_admin", "-d", "mandateguard", "-f", "/tmp/reset_dev_state.sql"],
        cwd=REPO_ROOT, check=True, capture_output=True,
    )


def _percentiles(samples: list[float]) -> dict[str, float]:
    s = sorted(samples)
    n = len(s)

    def pct(p: float) -> float:
        idx = min(n - 1, int(round(p * (n - 1))))
        return s[idx]

    return {"p50_ms": pct(0.50) * 1000, "p95_ms": pct(0.95) * 1000, "p99_ms": pct(0.99) * 1000, "min_ms": s[0] * 1000, "max_ms": s[-1] * 1000}


def measure_latency(client: httpx.Client, token: str) -> dict:
    opa_input = {
        "agent": {"id": "refund-agent-v1", "authenticated": True, "status": "ACTIVE"},
        "request": {"action": "refund_payment", "payment_id": EXECUTION_PAYMENT, "customer_id": "customer-demo-002", "amount_minor": 500, "currency": "USD"},
        "context": {"risk_mode": "NORMAL"},
    }
    opa_samples = []
    with httpx.Client(base_url=OPA_URL, timeout=15.0) as opa_client:
        for _ in range(SAMPLE_SIZE):
            t0 = time.perf_counter()
            r = opa_client.post("/v1/data/mandateguard/refund/decision", json={"input": opa_input})
            r.raise_for_status()
            opa_samples.append(time.perf_counter() - t0)

    e2e_samples = []
    for _ in range(SAMPLE_SIZE):
        t0 = time.perf_counter()
        resp = client.post(
            "/api/v1/refunds",
            headers={"Authorization": f"Bearer {token}", "Idempotency-Key": f"perf-{uuid.uuid4()}"},
            json={"payment_id": EXECUTION_PAYMENT, "amount_minor": 200, "currency": "USD", "reason_code": "CUSTOMER_REQUEST"},
        )
        elapsed = time.perf_counter() - t0
        if resp.status_code == 201 and resp.json()["status"] == "SUCCEEDED":
            e2e_samples.append(elapsed)

    return {
        "sample_size": SAMPLE_SIZE,
        "policy_latency": _percentiles(opa_samples),
        "end_to_end_latency": _percentiles(e2e_samples),
        "end_to_end_successes": len(e2e_samples),
    }


def measure_halt_bound(client: httpx.Client, token: str, repeats: int = 5) -> dict:
    bounds = []
    for _ in range(repeats):
        halt_resp = client.post(
            "/api/v1/admin/fleet/halt", json={"reason": "perf measurement"},
            headers={**OPERATOR_HEADERS, "Idempotency-Key": str(uuid.uuid4())},
        )
        halt_resp.raise_for_status()
        t0 = time.perf_counter()
        resp = client.post(
            "/api/v1/refunds",
            headers={"Authorization": f"Bearer {token}", "Idempotency-Key": f"perf-halt-{uuid.uuid4()}"},
            json={"payment_id": EXECUTION_PAYMENT, "amount_minor": 200, "currency": "USD", "reason_code": "CUSTOMER_REQUEST"},
        )
        bound = time.perf_counter() - t0
        assert resp.json()["reason_code"] == "FLEET_HALTED", "halt bound measurement invalid: request was not denied"
        bounds.append(bound)
        client.post(
            "/api/v1/admin/fleet/resume", json={"reason": "perf measurement cleanup"},
            headers={**OPERATOR_HEADERS, "Idempotency-Key": str(uuid.uuid4())},
        ).raise_for_status()
    return {"repeats": repeats, "max_ms": max(bounds) * 1000, "mean_ms": statistics.mean(bounds) * 1000, "samples_ms": [b * 1000 for b in bounds]}


def measure_replay_duration(client: httpx.Client) -> dict:
    base_config = {
        "schema_version": "1.0", "policy_version": "perf-candidate-v1", "supported_action": "refund_payment",
        "supported_currency": "USD", "approval_role": "REFUND_APPROVER", "fleet_budget_scope": "refund-fleet",
        "risk_modes": {"NORMAL": {"approval_threshold_minor": 25000, "hard_max_minor": 100000}, "ELEVATED": {"approval_threshold_minor": 10000, "hard_max_minor": 50000}},
        "agents": {"refund-agent-v1": {"enabled": True, "allowed_actions": ["refund_payment"], "customer_scopes": ["customer-demo-001", "customer-demo-002"]}},
    }
    t0 = time.perf_counter()
    resp = client.post("/api/v1/admin/policy/replay", json={"candidate_config": base_config}, headers=OPERATOR_HEADERS)
    elapsed = time.perf_counter() - t0
    resp.raise_for_status()
    run = resp.json()
    return {"duration_ms": elapsed * 1000, "evaluated": run["summary"]["evaluated"], "changed": run["summary"].get("changed")}


def measure_receipt_coverage(client: httpx.Client) -> dict:
    succeeded = client.get("/api/v1/admin/actions", params={"state": "SUCCEEDED", "limit": 200}, headers=OPERATOR_HEADERS).json()["actions"]
    receipts = client.get("/api/v1/admin/receipts", params={"limit": 200}, headers=OPERATOR_HEADERS).json()["receipts"]
    receipt_action_ids = {r["action_id"] for r in receipts}
    covered = sum(1 for a in succeeded if a["action_id"] in receipt_action_ids)
    total = len(succeeded)
    return {"succeeded_actions": total, "with_receipt": covered, "coverage_pct": (100.0 * covered / total) if total else None}


def measure_zero_overshoot(client: httpx.Client, token: str) -> dict:
    usage = client.get("/internal/v1/budget-usage/fleet/refund-fleet").json()
    payment_balance = client.get(f"/internal/v1/payment-balance/{EXECUTION_PAYMENT}").json()["refundable_remaining_minor"]
    headroom = min(usage["cap_minor"] - usage["usage_minor"], payment_balance)
    if headroom < 10:
        return {"skipped": True, "reason": "insufficient headroom; run after a reset"}
    amount = min(20000, max(1, headroom // 10))
    expected = headroom // amount
    request_count = expected + 10

    def fire(_: int) -> httpx.Response:
        with httpx.Client(base_url=BROKER_URL, timeout=15.0) as c:
            return c.post(
                "/api/v1/refunds",
                headers={"Authorization": f"Bearer {token}", "Idempotency-Key": f"perf-burst-{uuid.uuid4()}"},
                json={"payment_id": EXECUTION_PAYMENT, "amount_minor": amount, "currency": "USD", "reason_code": "CUSTOMER_REQUEST"},
            )

    with ThreadPoolExecutor(max_workers=request_count) as pool:
        responses = list(pool.map(fire, range(request_count)))
    succeeded = sum(1 for r in responses if r.status_code == 201 and r.json()["status"] == "SUCCEEDED")
    final_usage = client.get("/internal/v1/budget-usage/fleet/refund-fleet").json()
    return {
        "fired": request_count, "expected_successes": expected, "actual_successes": succeeded,
        "zero_overshoot": succeeded == expected and final_usage["usage_minor"] <= final_usage["cap_minor"],
    }


def main() -> None:
    print("Resetting dev state...")
    _reset_dev_state()

    token = _mint_token()
    results: dict = {"measured_at": datetime.now(timezone.utc).isoformat()}

    with httpx.Client(base_url=BROKER_URL, timeout=15.0) as client:
        print(f"Measuring latency over {SAMPLE_SIZE} samples...")
        results["latency"] = measure_latency(client, token)

        print("Measuring fleet-halt commit-to-denial bound...")
        results["halt_commit_to_denial_bound"] = measure_halt_bound(client, token)

        print("Measuring shadow-replay duration...")
        results["shadow_replay"] = measure_replay_duration(client)

        print("Measuring receipt coverage...")
        results["receipt_coverage"] = measure_receipt_coverage(client)

        print("Measuring zero-overshoot under a concurrent burst...")
        results["zero_overshoot"] = measure_zero_overshoot(client, token)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# MandateGuard performance and coverage measurements",
        "",
        f"Measured: {results['measured_at']}",
        "",
        "Generated by `scripts/measure_performance.py` against the live docker-compose stack after a dev-state reset. "
        "Re-run the script to reproduce; do not hand-edit the numbers below.",
        "",
        "## Policy (OPA) latency",
        "",
        f"n={results['latency']['sample_size']}",
        "",
        "| p50 | p95 | p99 | min | max |",
        "|---|---|---|---|---|",
        "| {p50_ms:.2f}ms | {p95_ms:.2f}ms | {p99_ms:.2f}ms | {min_ms:.2f}ms | {max_ms:.2f}ms |".format(**results["latency"]["policy_latency"]),
        "",
        "## End-to-end request latency (ALLOW, real bank execution)",
        "",
        f"n={results['latency']['end_to_end_successes']} successful requests",
        "",
        "| p50 | p95 | p99 | min | max |",
        "|---|---|---|---|---|",
        "| {p50_ms:.2f}ms | {p95_ms:.2f}ms | {p99_ms:.2f}ms | {min_ms:.2f}ms | {max_ms:.2f}ms |".format(**results["latency"]["end_to_end_latency"]),
        "",
        "## Fleet-halt commit-to-denial bound",
        "",
        f"Over {results['halt_commit_to_denial_bound']['repeats']} halt/request/resume cycles: "
        f"max {results['halt_commit_to_denial_bound']['max_ms']:.2f}ms, "
        f"mean {results['halt_commit_to_denial_bound']['mean_ms']:.2f}ms.",
        "",
        "## Shadow-replay duration",
        "",
        f"{results['shadow_replay']['duration_ms']:.2f}ms for {results['shadow_replay']['evaluated']} evaluated actions "
        f"({results['shadow_replay']['changed']} changed under the candidate config).",
        "",
        "## Receipt coverage",
        "",
        f"{results['receipt_coverage']['with_receipt']}/{results['receipt_coverage']['succeeded_actions']} SUCCEEDED actions "
        f"have a verifiable execution receipt "
        f"({results['receipt_coverage']['coverage_pct']:.1f}%)." if results["receipt_coverage"]["succeeded_actions"] else "No SUCCEEDED actions to measure.",
        "",
        "## Zero budget overshoot under a concurrent burst",
        "",
        f"Fired {results['zero_overshoot'].get('fired')} concurrent requests against remaining fleet/payment headroom: "
        f"{results['zero_overshoot'].get('actual_successes')} succeeded (expected exactly "
        f"{results['zero_overshoot'].get('expected_successes')}). Zero overshoot: {results['zero_overshoot'].get('zero_overshoot')}."
        if not results["zero_overshoot"].get("skipped") else f"Skipped: {results['zero_overshoot'].get('reason')}",
        "",
        "## Raw JSON",
        "",
        "```json",
        json.dumps(results, indent=2),
        "```",
        "",
    ]
    OUT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUT_PATH}")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
