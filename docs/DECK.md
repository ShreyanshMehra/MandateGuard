# MandateGuard -- pitch deck source

Twelve slides plus an appendix. This markdown is the portable source of truth (for pasting into PowerPoint/Keynote/Google Slides); `docs/deck.html` is the same content as a self-contained, presentable HTML deck.

---

## 1. Title

**MandateGuard**
A governance layer for financial AI agents

No AI agent can perform a financial action without bounded authority, reserved financial exposure, and verifiable proof of execution.

American Express CodeStreet 2026

---

## 2. The problem

- Banks are starting to let AI agents take real financial actions.
- Most "AI governance" today stops at a policy document or a voluntary allow/deny API.
- Nothing stops a misconfigured or compromised agent from:
  - Calling the bank directly, bypassing the policy layer entirely
  - Exceeding a limit under concurrent load
  - Replaying or mutating an old authorization
  - Leaving no verifiable record of what happened
- Trust in agentic finance needs enforcement, not a rulebook the agent could ignore.

---

## 3. What we built

MandateGuard is a real, enforced action broker for one financial action, built deep rather than wide: `refund_payment`.

- Agents authenticate with signed, short-lived tokens -- never self-declared identity.
- OPA evaluates versioned policy and returns `ALLOW` / `DENY` / `HOLD_FOR_APPROVAL`.
- An `ALLOW` atomically reserves customer/agent/fleet budget before anything executes.
- Only a reserved request gets a short-lived, single-use, signed permit.
- The mock bank executes only for the broker's own credential plus a valid permit, and signs its own result.
- Every terminal action gets a verifiable execution receipt.

---

## 4. Architecture

```text
Agent simulator
      |  signed identity + refund request
      v
MandateGuard broker ---------------------- Operator dashboard
      |          |                                  |
      |          +---- PostgreSQL ------------------+
      |            (separate broker / bank schemas)
      |
      +-- structured policy input --> OPA
      |<---- allow / deny / hold ----+
      |
      +-- service identity + permit --> Mock bank
      |<------ signed result -----------+
```

The mock bank is Docker-internal only. Even an agent on the same network cannot reach it -- only the broker holds the service credential.

---

## 5. The permit lifecycle

1. Verify the agent's signed token.
2. Fetch trusted customer/refundable-amount data from the bank (never from the agent).
3. Ask OPA for a decision against the live policy.
4. On `ALLOW`, reserve customer + agent + fleet budget in one locked transaction.
5. Issue a 60-second, single-use, parameter-bound Ed25519 permit.
6. Call the bank; verify its signed result before trusting "success."
7. Commit or release the reservation; write a signed execution receipt.

A permit that is expired, tampered, replayed, or issued before a revoke/halt is rejected -- proven directly against the bank's execution endpoint, bypassing the broker entirely, the way an attacker would.

---

## 6. Concurrency you can't cheat

Twenty concurrent requests against a ten-request cap should produce exactly ten reservations -- never eleven.

- Budget scopes are locked in deterministic sorted order (`SELECT ... FOR UPDATE`) and checked before any reservation is written.
- Measured, not simulated: a real concurrent burst against live budget headroom lands exactly at the cap, every time.
- Same guarantee for idempotency -- ten concurrent requests sharing one idempotency key settle to exactly one action and one receipt.

---

## 7. Governance that actually holds

- **Fleet halt** -- one operator action denies every new request; measured commit-to-denial bound in the tens of milliseconds.
- **Agent revoke** -- immediate for new requests; a monotonic epoch invalidates anything issued before it.
- **Held-action approval** -- re-runs live policy and re-checks epochs before executing. An approval can never override a hard limit, an active halt, or a revocation that happened while the action was waiting.
- Proven with a real control-change race mid-approval: the stale context is rejected, not silently approved.

---

## 8. Tamper-evident audit, safe policy testing

- Every state change appends to a hash-chained audit log per action.
- Signed checkpoints let an auditor detect a single edited or deleted historical event -- demonstrated with a direct SQL tamper.
- Shadow replay lets an operator test a candidate policy against real historical requests before it goes live -- with a hard guarantee it can never touch a live budget, permit, or refund.

---

## 9. Measured results

All numbers below are saved and reproducible via `scripts/measure_performance.py` -- see `docs/verification/PERFORMANCE.md`.

| Metric | Result |
|---|---|
| Policy (OPA) latency | p50 50ms / p95 52ms / p99 58ms |
| End-to-end request latency | p50 80ms / p95 97ms / p99 151ms |
| Fleet-halt commit-to-denial bound | max 83ms over 5 repeats |
| Receipt coverage | 100% of successful executions |
| Budget overshoot under concurrency | zero, every run |
| Shadow-replay duration | 477ms for 40 evaluated actions |

---

## 10. The deterministic demo

Eleven scenarios, runnable end to end from the dashboard or `scripts/run_scenarios.py`, resetting to the same baseline every time:

Normal refund - Held refund and approval - Permission denial - Direct-bank bypass rejection - Concurrent split-refund burst - Elevated-risk tightening - Fleet halt under load - Duplicate idempotency request - Permit replay - Audit tamper detection - Candidate policy replay

Two consecutive resets-and-reruns produce matching key results -- that's the bar for "the judge can trust this demo."

---

## 11. Honest limitations

- One action (`refund_payment`), one currency (USD), one local PostgreSQL instance.
- Prototype dev keys and shared-secret service credentials -- not hardware-backed identity or mTLS.
- No guarantee of reversing a refund the bank already applied.
- Tamper-evident checkpoints, not physically immutable storage.
- `UNKNOWN` bank outcomes reconcile manually, by design -- so a doubtful result is never retried blindly.
- No fraud detection, no prompt-injection-prevention claim, no real LLM agent yet.

We built the deterministic safety core first. Everything above is a natural next step once the enforcement core is trusted -- not a prerequisite for it.

---

## 12. Close

MandateGuard doesn't ask an AI agent to behave. It makes an unauthorized, unbounded, or unverifiable financial action physically impossible.

That's the bar a bank needs cleared before an agent touches real money -- and we built and measured it, end to end.

---

## Appendix

### A. Tech stack

FastAPI (broker, mock bank, agent simulator) - OPA/Rego (policy) - PostgreSQL (broker + bank schemas, role-separated) - React + TypeScript (dashboard) - Docker Compose (local orchestration) - Ed25519 (permits, bank results, audit checkpoints)

### B. Non-negotiable invariants (selected)

1. No bank refund without broker identity and a valid permit.
2. A permit is consumed at most once.
3. Customer, agent and fleet budgets reserve together or none reserve.
4. Approval never overrides a hard control (halt, revoke, hard max).
5. No database transaction stays open across an OPA or bank call.
6. Shadow replay cannot change live budgets, actions, permits or refunds.

Full invariant list: `HANDOFF.md` section 9.

### C. Where to look

- `README.md` -- fresh-machine quickstart and project structure
- `HANDOFF.md` / `STATUS.md` -- full build log and verification history
- `docs/ARCHITECTURE.md`, `docs/DATA_MODEL.md`, `docs/API_CONTRACT.md`, `docs/THREAT_MODEL.md` -- design contracts
- `docs/verification/PERFORMANCE.md` -- measured numbers, reproducible
- `tests/` -- 40 acceptance tests across four suites, run against the live stack
