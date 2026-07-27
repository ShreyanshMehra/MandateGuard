# MandateGuard Project Handoff

Last updated: 2026-07-27

This document is the self-contained continuation guide for the CodeStreet 2026 MandateGuard prototype. Read this file and `STATUS.md` before doing any future work.

## 1. Project location and repository

```text
C:\Users\shrey\OneDrive\Desktop\MandateGuard
```

- Git branch: `main`
- Last verified checkpoint at the time of this handoff: `c48a99b docs: define MandateGuard MVP architecture`
- Docker Desktop is installed and was successfully started.
- The project intentionally uses Git commits plus `STATUS.md` so progress survives context or token limits.

Resume with:

```powershell
Set-Location 'C:\Users\shrey\OneDrive\Desktop\MandateGuard'
Get-Content -Encoding UTF8 .\STATUS.md
git status --short --branch
git log --oneline -5
docker info --format '{{.ServerVersion}}'
```

Do not discard uncommitted files. Inspect them first because they may contain work from an interrupted milestone or subagent.

## 2. Objective

Build a working governance layer for financial AI agents that proves:

1. An agent cannot execute a refund without authenticated identity and permission.
2. An agent cannot bypass MandateGuard and call the bank directly.
3. Customer, agent and fleet limits cannot be exceeded, even with concurrent requests.
4. An approval or permit cannot be modified, duplicated or replayed.
5. Revocation and fleet halt invalidate all unconsumed authority.
6. Every decision and actual bank outcome produces a verifiable execution receipt.
7. A candidate rule can be tested against historical requests before activation.

The project is a financial action broker, not merely an allow/deny dashboard.

## 3. Core product promise

> No AI agent can perform a financial action without bounded authority, reserved financial exposure, and verifiable proof of execution.

Temporary product name: **MandateGuard**.

## 4. Current state

### Completed

- Independent judge, security, pitch, architecture and data/API reviews
- Problem choice confirmed: Governance Layer for Financial Agents
- Plain-English product explanation and PDF
- Detailed 17-step project plan
- Git repository initialization and first architecture checkpoint
- MVP product contract
- Threat model and failure rules
- Trust-boundary architecture
- API contract
- Data-model contract
- Architecture decision records
- Local toolchain audit
- Docker engine startup verification
- Runnable Docker Compose scaffold with health/readiness checks (Milestone 2)

The OPA/Rego rule engine is implemented under `policies/`. It was independently reviewed and verified with OPA 1.17 using strict compilation, formatting validation and `PASS: 22/22` policy tests.

Milestone 2 (runnable service scaffold) is complete: `docker-compose.yml` wires `postgres`, `opa`, `broker`, `mock-bank`, `agent-simulator` and `frontend`; every backend service exposes `/health` and `/ready`; the full stack builds and reaches a healthy state. See `STATUS.md` for verification output.

### In progress

- Milestone 3: database, identity, policy and action intake

### Not started

- PostgreSQL schema and migrations (roles/schemas exist; tables do not)
- Agent/operator authentication
- Atomic budgets
- Signed permits and bank-signed outcomes
- Approval and emergency-control workflows
- Tamper-evident receipt generation
- Policy shadow replay
- React dashboard
- Deterministic scenario runner
- Integration, concurrency and performance tests
- Presentation and video

## 5. Locked decisions

These decisions were explicitly accepted and should not be reopened without a concrete technical reason.

- Implement one action deeply: `refund_payment`.
- Use one demo currency: USD.
- Agents provide payment, amount, currency and reason only.
- Agent identity comes from a signed token.
- Customer identity and refundable amount come from trusted bank data.
- MandateGuard executes/proxies actions; agents never receive reusable permits.
- Outcomes are `ALLOW`, `DENY`, and `HOLD_FOR_APPROVAL`.
- Approval never overrides halt, revocation or hard financial limits.
- Budgets use atomic reserve/commit/release behavior.
- `UNKNOWN` external outcomes retain their reservation until reconciliation.
- Permits are Ed25519-signed, short-lived, exact-parameter-bound and one-use.
- Mock bank requires both broker service identity and a valid permit.
- Bank produces its own signed execution result.
- PostgreSQL owns mutable exposure and action state.
- OPA owns stateless permission and approval rules.
- Stable Rego logic uses versioned JSON configuration; arbitrary Rego upload is out of scope.
- Rule shadow replay is the secondary differentiator.
- The core demo is deterministic.
- No learned anomaly detection, blockchain, Kafka, Redis, Kubernetes or real LLM until the safety core is complete.

## 6. Technology stack

### Services

- React + TypeScript dashboard
- FastAPI broker
- FastAPI mock bank
- FastAPI agent simulator
- OPA/Rego policy service
- PostgreSQL
- Docker Compose

### Recommended pinned baseline

Verify image availability during the first pull, but do not use `latest`.

```text
Python image: python:3.12.13-slim
Node image: node:22.23.1-alpine3.24
PostgreSQL image: postgres:17.10-alpine
OPA image: openpolicyagent/opa:1.17.0-static
```

Recommended backend direct dependencies:

```text
fastapi==0.139.2
uvicorn==0.51.0
sqlalchemy==2.0.51
psycopg[binary]==3.3.4
alembic==1.18.5
PyJWT==2.13.0
cryptography==49.0.0
httpx==0.28.1
pytest==9.1.1
```

Use exact frontend pins and commit `package-lock.json`. Run `npm ci` in reproducible builds.

## 7. Logical architecture

```text
Agent simulator
      |
      | signed identity + refund request
      v
MandateGuard broker ---------------------- Operator dashboard
      |          |                                  |
      |          +---- broker schema ---------------+
      |
      +---- structured policy input ----> OPA
      |<--- allow / deny / hold ----------+
      |
      +---- broker identity + permit ----> Mock bank
      |<--- bank-signed result / timeout --+
                                      |
                                      +---- bank schema
```

One PostgreSQL server contains separate `broker` and `bank` schemas with different roles. The broker must not directly edit bank refund tables.

The mock-bank port must remain Docker-internal. The simulator may share the network for the bypass demonstration but must not have the broker credential.

## 8. Required state machines

Keep action, reservation and permit states separate.

### Action

```text
RECEIVED
├── DENIED
├── HELD ──approval + complete recheck──> BUDGET_RESERVED
└── BUDGET_RESERVED
      └── PERMIT_ISSUED
            └── EXECUTING
                  ├── SUCCEEDED
                  ├── FAILED
                  └── UNKNOWN
                        ├── RECONCILED_SUCCEEDED
                        └── RECONCILED_FAILED
```

### Reservation

```text
RESERVED → COMMITTED
         → RELEASED
         → UNKNOWN → COMMITTED or RELEASED after reconciliation
```

### Permit

```text
ISSUED → CONSUMED
       → CANCELLED
       → EXPIRED
```

Never release a reservation merely because an HTTP request timed out.

## 9. Non-negotiable invariants

1. No bank refund without broker identity and a valid permit.
2. A permit is consumed at most once.
3. A request changes the bank ledger at most once.
4. Customer, agent and fleet budgets reserve together or none reserve.
5. No new reservation exceeds any current effective cap.
6. `UNKNOWN` reservations continue consuming capacity.
7. Held and denied actions never receive permits.
8. Approval never overrides hard controls.
9. Changed request data invalidates the permit.
10. Unconsumed permits issued before halt/revocation are rejected.
11. Every state mutation and operator action creates an audit event.
12. Every decision stores the exact policy version and input hash.
13. Shadow replay cannot change live budgets, actions, permits or refunds.
14. Customer identity is derived from bank data.
15. A successful execution is accepted only with a valid bank-signed result.
16. No database transaction remains open across an OPA or mock-bank call.

## 10. Milestone plan

There are eight durable milestones. Each milestone ends with tests, a `STATUS.md` update and a Git commit.

| # | Milestone | Status | Acceptance gate |
|---:|---|---|---|
| 1 | Product contract, threats and architecture | Complete | Contracts reviewed, contradictions removed, initial commit created |
| 2 | Runnable service scaffold | Complete | All containers build; health/readiness checks pass |
| 3 | Database, identity, policy and action intake | Pending | Valid requests persist; forged/default-denied cases fail safely |
| 4 | Atomic budgets, permits and mock-bank execution | Pending | Concurrency has zero overshoot; direct/replay/mutation attempts fail |
| 5 | Approvals, controls, receipts and shadow replay | Pending | All governance workflows work and are audited |
| 6 | Dashboard and deterministic demo | Pending | Full demo runs from UI without terminal use |
| 7 | Security, concurrency and performance verification | Pending | P0 test matrix passes and measured results are saved |
| 8 | Deck, video and final packaging | Pending | Fresh-machine runbook, deck and video are submission-ready |

## 11. Exact future work

### Milestone 2 — Runnable scaffold

Create:

```text
docker-compose.yml
requirements.txt
requirements-dev.txt
docker/backend.Dockerfile
services/broker/...
services/mock_bank/...
services/agent_simulator/...
frontend/...
database/init/...
```

Required Compose services:

- `postgres`
- `opa`
- `broker`
- `mock-bank`
- `agent-simulator`
- `frontend`

Use a named PostgreSQL volume, never a OneDrive bind mount. Add health checks. Confirm with:

```powershell
docker compose config
docker compose build
docker compose up -d
docker compose ps
docker compose logs --tail 100
```

Acceptance: every service is healthy/ready, the frontend loads, and the broker can reach OPA, PostgreSQL and the mock bank.

### Milestone 3 — Identity, data and decisions

1. Add Alembic and create broker/bank schemas and roles.
2. Implement core enums and tables from `docs/DATA_MODEL.md`.
3. Seed governance state, payments, agents, public keys and baseline policy configuration.
4. Generate per-agent Ed25519 development keys.
5. Verify signed short-lived agent tokens.
6. Implement idempotent `POST /api/v1/refunds` intake.
7. Fetch trusted payment/customer context from the mock bank.
8. Call OPA outside a database transaction.
9. Persist exact decision input/output and audit event.

Acceptance: valid, forged, expired, wrong-action, wrong-currency, revoked and out-of-scope requests produce the expected safe result.

### Milestone 4 — Financial correctness and enforcement

1. Add semantic budget lock rows and sorted `FOR UPDATE` locking.
2. Implement customer, agent, fleet and rolling velocity limits.
3. Reserve all scopes atomically.
4. Implement Ed25519 Action Permit signing.
5. Implement atomic permit consumption with epoch recheck.
6. Restrict mock-bank execution to the broker credential.
7. Verify permit claims and unique request/JTI use in the bank transaction.
8. Sign the bank execution result.
9. Commit, release or retain reservation according to definitive/unknown outcome.
10. Reconcile unknown results by request ID; never retry the refund blindly.

Acceptance: twenty concurrent requests against a ten-request cap result in exactly ten reservations/refunds, never eleven. Direct calls, mutation, replay and duplicate retries do not create additional refunds.

### Milestone 5 — Governance workflows

1. Implement held-action approval and denial.
2. Re-evaluate policy and budgets after approval.
3. Implement agent revoke/restore with agent epoch increments.
4. Implement risk mode, halt and resume with global epoch increments.
5. Measure halt behavior precisely; do not claim already completed actions are undone.
6. Add per-stream hash-chained audit events.
7. Add signed exported checkpoints.
8. Create signed execution receipts.
9. Implement candidate policy configuration, separate approval, shadow replay, activation and rollback.

Acceptance: stale permits fail after control changes; tampering is detected relative to a checkpoint; replay cannot mutate live state.

### Milestone 6 — Dashboard and demo

Build screens for:

- Fleet status and emergency controls
- Live action feed
- Customer, agent and fleet exposure
- Held approvals
- Agent details and revocation
- Policy replay comparison
- Receipt search, export and verification

Build deterministic scenarios:

1. Normal refund
2. Held refund and approval
3. Permission denial
4. Direct-bank bypass rejection
5. Concurrent split-refund burst
6. Elevated-risk tightening
7. Fleet halt under load
8. Duplicate idempotency request
9. Permit replay
10. Audit tamper detection
11. Candidate policy replay

Acceptance: reset and rerun produce the same key results, and the judge can operate the full demo from the UI.

### Milestone 7 — Verification

Automate P0 tests from `docs/DATA_MODEL.md` and the architecture reviews, especially:

- Concurrent shared-cap correctness
- Concurrent idempotency
- Direct bypass
- Permit mutation, expiry and replay
- Revoke/halt races
- Unknown outcome and reconciliation
- Approval recheck
- OPA and bank failure behavior
- Receipt completeness
- Audit tamper detection
- Shadow replay isolation and determinism

Measure and save:

- p50/p95/p99 policy latency
- p50/p95/p99 end-to-end latency
- Halt commit-to-denial bound
- Zero budget overshoot result
- Receipt coverage
- Shadow-replay duration

Never put an unsaved or irreproducible number in the deck.

### Milestone 8 — Submission

1. Clean reset/seed command.
2. Fresh-machine Docker run verification.
3. Final README and architecture diagram.
4. Mandatory project description.
5. Ten-to-twelve-slide main deck plus appendix.
6. Ninety-to-120-second walkthrough video.
7. Demo rehearsal and backup recording.
8. Submit early and use later submissions only for verified fixes.

## 12. Progress-saving protocol

At the end of every meaningful unit:

1. Run the relevant acceptance test.
2. Run `git diff --check`.
3. Inspect `git status` and the diff.
4. Update `STATUS.md` with completed work, exact next action, blockers and decisive test output.
5. Commit with one focused message.
6. Add the new commit hash to this handoff or `STATUS.md` when useful.

Recommended commit pattern:

```text
docs: ...
chore: scaffold ...
feat(policy): ...
feat(identity): ...
feat(budget): ...
feat(permit): ...
feat(bank): ...
feat(governance): ...
feat(audit): ...
feat(replay): ...
feat(ui): ...
test: ...
```

Do not mark a milestone complete because files exist. Mark it complete only after the acceptance gate passes.

## 13. Environment notes

- Host `python`, `python3` and `py` resolve to different installations. Prefer containers.
- If host Python is unavoidable, use `py -3.12 -m venv .venv` and the venv interpreter explicitly.
- Use a committed npm lockfile and `npm ci`.
- OneDrive may cause file-watcher latency. Enable Vite polling if needed.
- Store PostgreSQL in a named Docker volume, not inside the synced project directory.
- Files are UTF-8. Windows PowerShell 5 may require `Get-Content -Encoding UTF8` to display punctuation correctly.
- OPA and PostgreSQL are not installed on the host; run them in Compose.
- Do not publish the mock-bank port to the host.

## 14. Honest limitations to preserve

- Synthetic data and limits, not American Express policy
- One currency and one financial workflow
- One local PostgreSQL instance
- Prototype keys and service credentials rather than production hardware-backed identity/mTLS
- No guarantee of cancelling a refund already consumed by the bank
- Tamper-evident checkpoints, not immutable storage
- No multi-region revocation or disaster recovery
- Shadow replay is a historical comparison, not a prediction
- No fraud detection or prompt-injection-prevention claim

## 15. Definition of done

The prototype is not done until all of the following are true:

- A legitimate refund visibly changes the mock-bank ledger.
- A high-value refund visibly enters hold and can be approved safely.
- A direct rogue-agent bank call visibly fails.
- Concurrent requests cannot overspend customer, agent or fleet limits.
- Modified, stale and replayed permits fail.
- Halt and revoke have measured, defensible behavior.
- Unknown outcomes reconcile without duplicate execution.
- Every terminal action has a complete verifiable receipt.
- Historical traffic can be replayed against a candidate rule without changing live state.
- All P0 tests pass from a clean environment.
- The complete demonstration can be run from the dashboard.
- The deck contains only measured or explicitly illustrative claims.
