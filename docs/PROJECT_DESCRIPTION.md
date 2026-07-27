# MandateGuard -- project description

**Team submission for American Express CodeStreet 2026.**

## The problem

Banks are starting to let AI agents take real financial actions -- issuing refunds, moving money, adjusting accounts -- on behalf of customers and operations teams. Today, almost every "AI governance" story for this stops at a policy document or an allow/deny API an agent can choose to call. Nothing stops a misconfigured or compromised agent from calling the bank directly, exceeding a limit under concurrent load, replaying an old authorization, or leaving no verifiable record of what actually happened. Trust in agentic finance requires more than a rulebook; it requires a system the agent physically cannot get around.

## What we built

MandateGuard is a working governance layer that sits between AI agents and a bank, implemented as a real, enforced action broker rather than an advisory service. We went deep on one financial action -- `refund_payment` -- and built every layer of enforcement around it:

- **Identity and mandate.** Every request carries a signed, short-lived agent token. MandateGuard derives the agent's identity and permissions from that token and from trusted bank-side customer data -- never from anything the agent merely claims.
- **Policy.** A stateless OPA/Rego policy engine evaluates each request against versioned, hierarchical rules -- per-agent scope, risk-mode-aware approval thresholds, and hard maximums -- and returns `ALLOW`, `DENY`, or `HOLD_FOR_APPROVAL`.
- **Reserved exposure.** An `ALLOW` decision atomically reserves the request amount against customer, agent and fleet daily budgets in the same locked transaction, so concurrent requests against a shared cap never overshoot it -- proven under real concurrent load, not simulated.
- **One-use permits.** Only after reservation does MandateGuard issue a short-lived, single-use, parameter-bound Ed25519-signed permit. The mock bank will not execute a refund for any caller without the broker's own service credential *and* a valid matching permit -- so an agent, even a compromised one, cannot call the bank directly and cannot reuse, replay or tamper with an authorization.
- **Verifiable execution.** The bank signs its own result; the broker verifies that signature before trusting a "success," and every completed action produces a signed, hash-verifiable execution receipt.
- **Live governance.** Operators can halt the entire fleet, revoke an individual agent, or tighten risk mode -- each backed by a monotonically increasing epoch so any permit or approval issued before the change is rejected after it. Held actions require human approval, and that approval is rechecked against live policy and current epochs before it can execute -- so an approval can never override a hard limit, a halt, or a revocation that happened in between.
- **Tamper-evident audit.** Every state change appends to a hash-chained audit log; signed checkpoints let an auditor detect if a historical event was edited or deleted.
- **Shadow replay.** Before a candidate policy change goes live, an operator can replay it against real historical requests and see exactly what would have changed -- with a hard guarantee that replay never touches a live budget, permit, or refund.

All of this is operable from a single operator dashboard -- fleet status, live feed, exposure, held approvals, agent management, policy replay and receipt search -- with no terminal required to run the full demo.

## Why this matters

The value isn't "an agent that is well-behaved." It's that MandateGuard makes bad behavior -- bugs, prompt injection, a compromised agent, an operator error -- physically incapable of producing an unauthorized, unbounded, or unverifiable financial action. That is the actual bar a bank would need cleared before letting an AI agent touch real money.

## What we proved, not just claimed

Every number in our materials is measured and saved, not estimated: zero budget overshoot under a real concurrent burst, a measured fleet-halt commit-to-denial bound, measured policy and end-to-end latency percentiles, 100% receipt coverage for successful executions, and a reproducible eleven-scenario deterministic demo that produces matching results across repeated runs. See `docs/verification/PERFORMANCE.md` and `STATUS.md`'s verification log for the full, repeatable record.

## Honest scope

This is a single-action (`refund_payment`), single-currency (USD) prototype on one local PostgreSQL instance, using prototype dev keys and shared-secret service credentials rather than production hardware-backed identity. Reconciliation of an `UNKNOWN` bank outcome is manual by design, so a doubtful result is never retried blindly. We built the deterministic safety core first and deliberately left out anomaly detection, a real LLM agent, and infrastructure like Kafka/Redis/Kubernetes -- those are natural next steps once the enforcement core is trusted, not prerequisites for it.
