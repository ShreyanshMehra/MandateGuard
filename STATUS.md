# MandateGuard Build Status

Last updated: 2026-07-27

This file is the durable handoff point. Read it first after any interrupted or context-limited session.

## Current milestone

**Milestone 1 — Product contract, threat model and architecture**

Status: in progress

## Completed

- [x] Problem statement and strategic direction reviewed independently.
- [x] Core product decisions locked.
- [x] Plain-English explanation and detailed build plan created.
- [x] Git repository initialized on `main`.
- [x] Initial project directories created.
- [x] Local toolchain checked: Git, Python, Node, Docker CLI and Docker Compose are installed.
- [x] Docker Desktop started and its engine is reachable.
- [x] Independent architecture and data/API reviews completed.

## In progress

- [x] Freeze the MVP product contract and safety invariants.
- [x] Freeze the threat model and failure behavior.
- [x] Confirm API, data and trust-boundary design.

## Next actions

1. Review and finalize the architecture documents.
2. Create the Docker Compose scaffold and service health endpoints.
3. Start Docker Desktop and verify the empty stack.
4. Commit Milestone 1 after its acceptance checks pass.

## Current blockers

- No active implementation blocker.

## Locked decisions

- One deeply implemented action: `refund_payment`.
- MandateGuard executes/proxies actions; agents cannot call the mock bank directly.
- Outcomes are `ALLOW`, `DENY`, and `HOLD_FOR_APPROVAL`.
- Budgets use atomic reserve/commit/release semantics.
- Permits are signed, short-lived, parameter-bound and one-use.
- PostgreSQL is the source of truth for mutable financial exposure.
- OPA evaluates stateless authorization policy.
- The dashboard is React; services are FastAPI; local orchestration is Docker Compose.
- Policy shadow replay is the secondary differentiator.
- No learned anomaly detection or real LLM until the deterministic safety core is complete.

## Verification log

| Date | Check | Result |
|---|---|---|
| 2026-07-27 | Workspace exists and opens in VS Code | Pass |
| 2026-07-27 | Git 2.49, Python 3.12, Node 22, Docker 28 and Compose 2.34 available | Pass |
| 2026-07-27 | Docker engine reachable | Pass — Docker Engine 28.0.4 |
