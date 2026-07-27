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
- Database migrations, seeded identity/policy/payment data, agent token verification and audited `POST /api/v1/refunds` intake (Milestone 3)
- Atomic budget reservation, Ed25519 action permits and permit-gated, signature-verified mock-bank execution (Milestone 4)
- Held-action approval/denial, agent revoke/restore, fleet halt/resume/risk mode, signed audit checkpoints and read-only candidate-policy shadow replay (Milestone 5)
- React operator dashboard and a deterministic 11-scenario demo runner (Milestone 6)

The OPA/Rego rule engine is implemented under `policies/`. It was independently reviewed and verified with OPA 1.17 using strict compilation, formatting validation and `PASS: 22/22` policy tests.

Milestone 2 (runnable service scaffold) is complete: `docker-compose.yml` wires `postgres`, `opa`, `broker`, `mock-bank`, `agent-simulator` and `frontend`; every backend service exposes `/health` and `/ready`; the full stack builds and reaches a healthy state. See `STATUS.md` for verification output.

Milestone 3 (identity, data and decisions) is complete: Alembic migrations create the broker/bank tables needed for identity, policy and action intake (budget, permit, receipt, approval, control-action and checkpoint tables are deliberately deferred to the milestones that implement them, per `docs/DATA_MODEL.md`); a baseline seed loads governance state, demo agents/keys, `policy_config.json` as `policy_versions` version 1, and demo payments; `POST /api/v1/refunds` verifies a signed, short-lived Ed25519 agent token, fetches trusted payment/customer context from the mock bank, calls OPA outside the DB transaction, and persists the exact decision input/output plus a hash-chained audit event. All 18 acceptance tests in `tests/test_refund_intake.py` pass, covering valid/forged/expired/unknown-key/missing-auth tokens, wrong-currency, revoked-agent, out-of-scope-customer, payment-not-found, amount-exceeds-refundable, HOLD (approval threshold) and hard-max DENY, idempotent replay and conflict, and `GET /api/v1/actions/{id}` scoping. See `STATUS.md` for the verification log.

Milestone 4 (financial correctness and enforcement) is complete: `budget_locks`/`budget_reservations`/`reservation_allocations` reserve customer, agent and fleet amount budgets atomically (sorted `FOR UPDATE` locking, all-or-nothing, caps read from the active policy version's config); an ALLOW decision issues a short-lived, single-use, parameter-bound Ed25519 `action_permits` token (`services/broker/app/permits.py`); the mock bank's `POST /internal/v1/refunds` only accepts the broker's service credential plus a valid unexpired permit whose claims match the request, applies the refund atomically under a row lock, and returns an Ed25519-signed result the broker verifies before trusting it; outcomes commit/release/mark-`UNKNOWN` the reservation and consume/cancel the permit accordingly, with a signed `execution_receipts` document on success. Every step after the initial decision commit (budget reserve, permit issue, bank call, finalize) is its own short transaction, so no DB transaction is ever open during the OPA or mock-bank HTTP call. All 5 tests in `tests/test_budget_execution.py` pass: real execution and settlement, zero-overshoot concurrent bursts against a shared budget, and direct-to-bank probes for missing/tampered/replayed permits. `tests/test_refund_intake.py`'s 18 Milestone 3 tests still pass unmodified in substance (two status assertions updated since ALLOW now runs to completion instead of stopping at `RECEIVED`). Both suites require a dev-state reset between runs since execution now mutates real balances -- see `scripts/reset_dev_state.sql`. Scope reductions, documented and deliberate: velocity/count limits and `policy_limits`-table-driven caps are deferred to Milestone 5; caps are read directly from policy config instead. No background reconciliation loop -- `UNKNOWN` outcomes are left for manual reconciliation (the mock bank's `GET /internal/v1/refunds/{request_id}` supports it) rather than an automatic retry loop, to avoid ever double-refunding blindly.

Milestone 5 (governance workflows) is complete: `services/broker/app/controls.py` implements idempotent agent revoke/restore and fleet halt/resume/risk-mode changes, each bumping the relevant monotonic epoch (`agents.epoch` or `governance_state.epoch`), recording a before/after snapshot in `control_actions`, and appending a hash-chained audit event. `POST/GET /api/v1/admin/actions/{id}/approve|deny` implement held-action approval and denial: a HELD action's `control_epoch_snapshot`/`agent_epoch_snapshot` (captured when it was held) are compared against the current epochs before anything else runs, so an agent revoke or fleet halt/resume/risk change between hold and approval makes the approval fail closed with `STALE_CONTEXT_RECHECK_REQUIRED` rather than executing against a stale authorization context; otherwise policy is re-evaluated live (`phase=APPROVAL_RECHECK`) and a DENY recheck outcome (hard limits, revocation, scope) always wins over the operator's approval, while a HOLD recheck outcome (the amount-threshold rule the approval exists to satisfy) proceeds to the same budget-reserve/permit/execute pipeline as a normal ALLOW. `services/broker/app/checkpoints.py` signs a manifest of every audit stream's `(last_sequence, last_event_hash)` with a dedicated Ed25519 dev key and verifies it by replaying each covered stream's event chain from scratch, recomputing every event's hash and confirming it still matches -- so an edited or deleted historical `audit_events` row is detected relative to the checkpoint. `services/broker/app/replay.py` implements read-only candidate-policy shadow replay: it re-evaluates each historical action's exact stored OPA input against a candidate config passed via a new `input.override_config` field in `policies/refund_policy.rego` (falls back to the live bundled config when absent, so ordinary requests are unaffected), using the real Rego rules rather than a reimplementation, and only ever writes to the dedicated `policy_replay_runs`/`policy_replay_results` tables -- it never creates reservations, permits, refunds or live audit events, and never touches `action_requests`. All 8 tests in `tests/test_governance_workflows.py` pass: epoch bump on revoke/restore, held-action approve-to-execution and deny, stale-context rejection after a control change, fleet halt denying new requests and resume restoring them, checkpoint tamper detection via a direct SQL edit to a historical audit event, and a read-only replay that changes the decision for a held action under a permissive candidate config while leaving the live action's state untouched. Operator endpoints (`/api/v1/admin/...`) are gated by a dev-only shared `X-Operator-Token` secret, a stand-in for the Milestone 6 dashboard's real operator login. Scope reductions, documented and deliberate: velocity/rolling-window limits and `policy_limits`-table-driven caps remain deferred (still read directly from policy config); candidate policy version approval/activation/rollback lifecycle (`policy_versions` status transitions) is left to the Milestone 6 dashboard work, since replay itself is already fully read-only and independently useful without it.

Milestone 6 (dashboard and demo) is complete: the seven required screens are implemented as a dependency-free React dashboard (`frontend/src/components/`) against new read-only operator endpoints (`services/broker/app/routes_admin_views.py`) -- Fleet status/emergency controls, Live action feed, Customer/agent/fleet exposure, Held approvals, Agent details/revocation, Policy replay comparison, and Receipt search/export/verification -- all gated by the same dev-only `X-Operator-Token` as the Milestone 5 admin endpoints, with the broker's CORS policy (`DASHBOARD_ORIGIN`) opened for the dashboard's own origin so it can call the broker directly from the browser. `scripts/run_scenarios.py` implements all eleven deterministic demo scenarios from this section's list end-to-end against the live stack (resetting dev state first, then narrating PASS/FAIL plus key metrics per scenario); scenario order inside the script is chosen for shared-state determinism within one run (the concurrent burst, which deliberately maxes out whatever fleet budget headroom remains, runs last) rather than the list order below, and two full reset-then-run passes were verified to produce the same key results each time. `tsc -b` and `vite build` both pass cleanly and the dashboard was verified against the live stack via its actual HTTP contract (every admin endpoint it calls was hit directly and returned the expected shape) and a CORS preflight check. It was later also click-tested end-to-end in a real headless-Chromium browser (screenshots of all seven tabs plus interactive round-trips on policy replay, receipt verification and held-action approval, zero console errors) using a throwaway Playwright script kept outside the repo -- see the Verification log below. Scope reductions, documented and deliberate: the dashboard is read/act via existing endpoints only, with no new admin login (still the shared operator token) and no visual polish beyond a single dark-mode-only stylesheet -- both are reasonable follow-ups but not required by this milestone's acceptance gate.

Milestone 7 (verification) is complete: `tests/test_verification.py` (9 tests, all passing) covers the P0 gaps not already exercised by the Milestone 3-6 suites -- concurrent identical requests sharing one `Idempotency-Key` settle to exactly one action and one receipt; a permit with an `exp` in the past is rejected by the mock bank the same way a tampered one is; stopping the `opa` and `mock-bank` containers mid-test proves the broker fails closed (503, `POLICY_SERVICE_UNAVAILABLE`/`BANK_CONTEXT_UNAVAILABLE`) with no partial `action_requests` row possible (the code raises before the row is ever inserted) and recovers cleanly once the container is back; a fleet halt's commit-to-denial bound is measured directly (the very next request after the halt call returns is always denied); a revoke fired concurrently with a request burst is proven to deny every request issued after the revoke's 200 response, with no window where a post-revoke request can still be allowed; a successful execution's receipt is checked field-by-field against `docs/DATA_MODEL.md`'s execution-receipt shape, and confirmed absent for denied/held actions; and the mock bank's per-`request_id` refund lookup -- the manual-reconciliation building block for `UNKNOWN` outcomes, per the Milestone 4 scope note -- is proven to be a stable, non-mutating read. `scripts/measure_performance.py` measures and saves (never prints-only) the numbers HANDOFF.md section 11 asks for -- OPA policy-call and end-to-end request latency percentiles (p50/p95/p99 over 40 samples), the fleet-halt commit-to-denial bound (5 repeats), shadow-replay duration, receipt coverage (successful actions with a verifiable receipt), and a fresh zero-budget-overshoot confirmation under a concurrent burst -- to `docs/verification/PERFORMANCE.md`, reproducible by re-running the script against a reset stack. Scope reductions, documented and deliberate: true mid-flight "bank goes down between payment-fetch and execution" `UNKNOWN`-outcome injection was not built, since both calls share one endpoint and one container in this environment (per the Milestone 4 scope note, there is no automatic reconciliation loop to test against in the first place -- reconciliation is manual, and the test above verifies the safe primitive that manual path depends on) -- a chaos-injection endpoint on the mock bank would close this gap and is a reasonable Milestone 8+ follow-up, not required by this milestone's acceptance gate.

Milestone 8 (deck, video and final packaging) engineering/documentation deliverables are complete: `README.md` was rewritten end to end (accurate architecture summary and diagram, fresh-machine quickstart, demo/test/measurement commands, project structure, honest limitations). `docs/PROJECT_DESCRIPTION.md` is the mandatory project description. `docs/DECK.md` (portable markdown) and `docs/deck.html` (self-contained HTML, publishable directly or printable to PDF) are a twelve-slide-plus-appendix deck covering the problem, what was built, architecture, the permit lifecycle, concurrency correctness, governance controls, audit/replay, the measured-results table, the eleven-scenario demo, honest limitations, close, and reference material. `docs/VIDEO_SCRIPT.md` is a shot-by-shot, timestamped storyboard for the 90-120 second walkthrough, mapped to exact dashboard tabs and terminal commands. `docs/DEMO_REHEARSAL.md` is a live-demo checklist with a dashboard-first sequence and a terminal-only fallback. A true fresh-machine verification was run: `docker compose down -v` (removed the named Postgres volume) plus `docker rmi` of all five project-built images, then a full rebuild and bring-up from the repo checkout alone -- all six containers reached healthy/running, and `pytest tests/` (38 passed, 2 skipped), `scripts/run_scenarios.py` (11/11) and `scripts/measure_performance.py` all passed cleanly against that freshly built, freshly migrated, freshly seeded stack. Scope note: the local Docker image cache already had the base images (`python`, `node`, `postgres`, `opa`), so this did not exercise a first-time network pull of those -- everything downstream of that was verified from zero project state. What remains is human action this session cannot perform: recording the actual video, a live rehearsal, and submission itself.

### In progress

- Nothing in progress on the engineering/documentation side; remaining Milestone 8 work (video recording, live rehearsal, submission) is human action.

### Not started

- Recording the walkthrough video (script ready)
- Live demo rehearsal
- Submission

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
| 3 | Database, identity, policy and action intake | Complete | Valid requests persist; forged/default-denied cases fail safely |
| 4 | Atomic budgets, permits and mock-bank execution | Complete | Concurrency has zero overshoot; direct/replay/mutation attempts fail |
| 5 | Approvals, controls, receipts and shadow replay | Complete | All governance workflows work and are audited |
| 6 | Dashboard and deterministic demo | Complete | Full demo runs from UI without terminal use |
| 7 | Security, concurrency and performance verification | Complete | P0 test matrix passes and measured results are saved |
| 8 | Deck, video and final packaging | Docs/deck/rehearsal-plan complete; video/rehearsal/submission are human actions | Fresh-machine runbook, deck and video are submission-ready |

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
