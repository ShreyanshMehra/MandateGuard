# MandateGuard Build Status

Last updated: 2026-07-27

This file is the durable handoff point. Read it first after any interrupted or context-limited session.

## Current milestone

**Milestone 8 — Deck, video and final packaging**

Status: engineering/documentation deliverables complete, pending final commit. Video recording, live rehearsal and actual submission are human actions this file cannot perform -- see "Not started" below.

## Completed

- [x] Problem statement and strategic direction reviewed independently.
- [x] Core product decisions locked.
- [x] Plain-English explanation and detailed build plan created.
- [x] Git repository initialized on `main`.
- [x] Initial project directories created.
- [x] Local toolchain checked: Git, Python, Node, Docker CLI and Docker Compose are installed.
- [x] Docker Desktop started and its engine is reachable.
- [x] Independent architecture and data/API reviews completed.
- [x] Milestone 1 contracts reviewed and committed as `c48a99b`.
- [x] Self-contained `HANDOFF.md` created with all remaining milestones and resume instructions.
- [x] OPA policy package committed and independently reviewed (`5034008`).
- [x] Docker Compose scaffold created: `postgres`, `opa`, `broker`, `mock-bank`, `agent-simulator`, `frontend`.
- [x] `docker/backend.Dockerfile` (shared image, `SERVICE_DIR` build arg) builds broker, mock-bank and agent-simulator.
- [x] Each backend service exposes `GET /health` (liveness) and `GET /ready` (dependency check: broker verifies Postgres + OPA, agent-simulator verifies broker).
- [x] `database/init/00-roles-and-schemas.sh` creates the `mandateguard_broker`/`mandateguard_bank` roles and `broker`/`bank` schemas with cross-schema privileges revoked, matching the trust boundary in `docs/ARCHITECTURE.md`.
- [x] Minimal Vite + React + TypeScript frontend scaffold that calls the broker `/health` endpoint.
- [x] Full stack built and brought up; all six containers reached a healthy/running state.
- [x] Repository created at `https://github.com/ShreyanshMehra/MandateGuard` and Milestone 2 pushed to `origin/main`.
- [x] Alembic migration project (`database/migrations/`) with a scope-limited initial schema: `broker.agents`, `agent_credentials`, `policy_versions`, `governance_state`, `action_requests`, `policy_evaluations`, `audit_stream_heads`, `audit_events`, and `bank.payments`. Budget, permit, receipt, approval, control-action and checkpoint tables are deliberately deferred to the milestones that implement them.
- [x] Idempotent baseline seed migration loading `policy_config.json` as `policy_versions` version 1, the governance-state singleton, two demo agents (one `ACTIVE`, one `REVOKED`) with their Ed25519 public keys, and three demo payments.
- [x] `migrate` Compose service runs Alembic to `head` (via `ADMIN_DATABASE_URL`) before `broker`/`mock-bank` start, using `service_completed_successfully`.
- [x] Per-agent Ed25519 dev keypairs generated into gitignored `secrets/dev/`; `scripts/generate_agent_keys.py` and `scripts/mint_agent_token.py` added for key generation and local token minting.
- [x] Mock bank exposes `GET /internal/v1/payments/{payment_id}`, gated by a shared `X-Broker-Service-Token` header, as the broker's only source of trusted customer/refundable-amount data.
- [x] Broker verifies short-lived EdDSA agent tokens (`kid` → on-file public key, `sub` → `token_subject`, TTL capped by `MAX_AGENT_TOKEN_TTL_SECONDS`); a cryptographically valid but `REVOKED` agent is forwarded to OPA as an auditable `AGENT_INACTIVE` deny rather than rejected at the auth layer.
- [x] `POST /api/v1/refunds` implemented: idempotency-key intake, governance-state halt check, trusted bank lookup, pre-OPA trusted-data checks (payment-not-found, currency-mismatch, amount-exceeds-refundable), OPA call outside the DB transaction, and persistence of the exact decision input/output snapshot plus a hash-chained `ACTION_DECIDED` audit event.
- [x] `GET /api/v1/actions/{action_id}` implemented, scoped to the requesting agent's own actions.
- [x] `tests/test_refund_intake.py` (18 tests, all passing) covers the Milestone 3 acceptance gate: valid ALLOW, forged signature, expired token, unknown key ID, missing auth, wrong-currency, revoked agent, out-of-scope customer, payment-not-found, amount-exceeds-refundable, HOLD (approval threshold) and hard-max DENY, idempotent replay, idempotency-key conflict, and action-visibility scoping. "Wrong-action" is not reachable via the public API contract (no `action` field on `RefundRequest`); that branch is covered by the existing OPA unit tests in `policies/refund_policy_test.rego`.
- [x] Migration `0003`: `budget_locks`, `budget_reservations`, `reservation_allocations`, `action_permits`, `execution_receipts` (broker schema); `permit_uses`, `refunds`, `bank_operation_events` (bank schema). Migration `0004`: a dedicated `payment-demo-004` (5,000,000 minor) so Milestone 4's execution tests don't drain the fixed-balance payments Milestone 3's tests assume.
- [x] `services/broker/app/budgets.py`: atomic customer/agent/fleet budget reservation. Scopes locked in deterministic sorted order via `budget_locks` + `SELECT ... FOR UPDATE`; usage summed under that lock and compared to the cap (from the active policy version's `budgets` config) before any reservation row is written -- this is what gives zero-overshoot concurrency. `RESERVED` and `UNKNOWN` reservations keep consuming capacity; only `RELEASED` frees it.
- [x] `services/broker/app/permits.py`: Ed25519-signed, single-use, parameter-bound (payment/amount/currency), short-lived (60s TTL) action permits, using a broker-owned dev keypair (`secrets/dev/broker-permit-signing__...pem`, gitignored). Also verifies the mock bank's Ed25519-signed execution result against a second, bank-owned dev keypair.
- [x] `POST /internal/v1/refunds` on the mock bank: requires the broker service token *and* a valid unexpired permit whose claims match the request body; applies the refund atomically under a payment row lock; rejects a reused permit JTI via a unique constraint on `bank.refunds.permit_jti` (mapped to a clean 409, not a 500); returns an Ed25519-signed result document. `GET /internal/v1/refunds/{request_id}` supports manual reconciliation of `UNKNOWN` outcomes.
- [x] `POST /api/v1/refunds` extended: for an ALLOW decision, reserves budget, issues a permit, calls the mock bank, and verifies the signed result -- each step its own short transaction (invariant: no DB transaction open during the OPA or mock-bank HTTP call). Outcomes: `SUCCEEDED` (reservation `COMMITTED`, permit `CONSUMED`, signed `execution_receipts` row written), `FAILED` (reservation `RELEASED`, permit `CANCELLED`), or `UNKNOWN` (reservation stays `UNKNOWN`, still consuming budget, pending manual reconciliation -- never retried blindly). A `BudgetExceededError` short-circuits straight to a `DENY`/`BUDGET_EXCEEDED_{SCOPE}` action.
- [x] `tests/test_budget_execution.py` (5 tests, all passing): real execution + settlement against the mock bank; a concurrent burst against a shared fleet/payment headroom that always lands exactly the expected number of successes and never overshoots; and three direct-to-mock-bank probes (run inside the broker container, since mock-bank is not published to the host) proving a missing permit, a tampered permit claim and a replayed permit JTI are all rejected without a second refund.
- [x] `scripts/reset_dev_state.sql`: resets bank balances, budget/permit/receipt tables and audit streams to the freshly-seeded baseline, since Milestone 4 execution -- unlike Milestone 3's no-op ALLOW path -- actually mutates balances and consumes budget, so repeated local test runs need a reset between them. Extended in Milestone 5 to also restore each agent's originally-seeded status/epoch (not blanket-ACTIVE, since `revoked-demo-agent-v1` is seeded REVOKED on purpose) and reset `governance_state` to `RUNNING`/`NORMAL`/epoch 0.
- [x] Migration `0005`: `control_actions`, `approvals`, `audit_checkpoints`, `audit_checkpoint_items`, `policy_replay_runs`, `policy_replay_results` (broker schema).
- [x] `services/broker/app/controls.py`: idempotent (caller-supplied `Idempotency-Key`) agent revoke/restore and fleet halt/resume/risk-mode changes, each bumping the relevant monotonic epoch (`agents.epoch` or `governance_state.epoch`) only when something actually changed, recording a before/after snapshot in `control_actions`, and appending a hash-chained audit event.
- [x] `POST/GET /api/v1/admin/actions/{id}/approve|deny`: held-action approval/denial with re-evaluation. Compares the action's held-time `control_epoch_snapshot`/`agent_epoch_snapshot` against current epochs first -- a mismatch (agent revoked, or fleet halted/resumed/risk-changed since the hold) fails the approval closed with `STALE_CONTEXT_RECHECK_REQUIRED` rather than executing against a stale context. Otherwise re-runs OPA (`phase=APPROVAL_RECHECK`); a DENY recheck outcome always wins over the operator's approval (hard limits, revocation, scope), while a HOLD recheck outcome (the amount-threshold condition the approval exists to satisfy) proceeds into the same budget-reserve/permit-issue/bank-execute pipeline Milestone 4 built.
- [x] `services/broker/app/checkpoints.py`: signs a manifest of every audit stream's `(last_sequence, last_event_hash)` with a dedicated Ed25519 dev key (`secrets/dev/audit-checkpoint-signing__...pem`, gitignored) and verifies it by replaying each stream's event chain from scratch and recomputing every event's hash, detecting any edit or deletion of a historical `audit_events` row relative to the checkpoint.
- [x] `services/broker/app/replay.py` + a new `input.override_config` field in `policies/refund_policy.rego` (falls back to the live bundled config when absent): read-only candidate-policy shadow replay that re-evaluates each historical action's exact stored OPA input against a candidate config using the real Rego rules, writing only to dedicated `policy_replay_runs`/`policy_replay_results` tables -- never touching `action_requests` or creating reservations, permits, refunds or live audit events.
- [x] `tests/test_governance_workflows.py` (8 tests, all passing): epoch bump on revoke/restore, held-action approve-to-execution and deny, stale-context rejection after a control change mid-approval, fleet halt denying new requests and resume restoring them, audit checkpoint tamper detection via a direct SQL edit to a historical event, and read-only replay that changes a held action's decision under a permissive candidate config while leaving the live action's state untouched.

- [x] `services/broker/app/routes_admin_views.py`: read-only operator endpoints backing the dashboard -- `GET /api/v1/admin/governance`, `/agents`, `/actions` (list + per-action detail with reservation/permit/receipt/audit-trail), `/exposure` (fleet + per-agent + top-10-customer usage today), `/receipts` (list + per-receipt signature verification). All gated by `X-Operator-Token`, same as the Milestone 5 mutation endpoints.
- [x] CORS opened on the broker (`DASHBOARD_ORIGIN`, defaults to `http://localhost:5173`) so the dashboard can call it directly from the browser; `X-Operator-Token` explicitly allowed as a custom header.
- [x] `frontend/src/`: a dependency-free React dashboard (no router or UI kit -- plain fetch + local state, matching the Milestone 2 scaffold's minimalism) with the seven required screens as separate components (`FleetControls`, `LiveFeed`, `Exposure`, `HeldApprovals`, `Agents`, `PolicyReplay`, `Receipts`), an operator-token input persisted to `localStorage`, and polling refresh on the live-data panels. `tsc -b` and `vite build` both pass cleanly.
- [x] `scripts/run_scenarios.py`: all eleven deterministic demo scenarios from HANDOFF.md's Milestone 6 list, run end-to-end against the live stack after an automatic dev-state reset, each printing PASS/FAIL and its key metric. Two consecutive full runs (reset + all eleven) produced matching key results (e.g. the concurrent burst allowed exactly the same number of successes both times), confirming reproducibility.
- [x] Fixed a bug this milestone's testing surfaced: `ExecutionReceipt` was missing `created_at` from its ORM mapping (present in the migration, not the model), which crashed every real bank execution once the new receipts-list endpoint's ordering touched the column; fixed by mapping it and setting it explicitly when a receipt is created.
- [x] Dashboard browser walkthrough: performed after Milestone 6 landed, using a throwaway Playwright script kept entirely outside the repo (per explicit scope choice at the time). All seven tabs screenshotted and rendered correctly with real live data; interactive round-trips exercised through the actual browser UI -- policy replay produced a correct real diff, clicking "Verify" on a receipt showed a green VALID pill, and approving a held action via the UI executed it and removed it from the list. Zero browser console/page errors across all runs. A post-check `pytest tests/` after reset still passed (30 passed, 1 skipped at the time), confirming the live UI mutation didn't corrupt state.
- [x] `tests/test_verification.py` (9 tests, all passing): concurrent identical requests sharing one `Idempotency-Key` settle to exactly one action and one receipt; an expired permit is rejected the same way a tampered one is; stopping the `opa`/`mock-bank` containers proves the broker fails closed (503, `POLICY_SERVICE_UNAVAILABLE`/`BANK_CONTEXT_UNAVAILABLE`) and recovers cleanly afterward; the fleet-halt commit-to-denial bound is measured directly; a revoke fired concurrently with a request burst denies every request issued after the revoke's 200 response; a successful execution's receipt is checked field-by-field against the data model, and confirmed absent for denied/held actions; the mock bank's per-request-id refund lookup (the manual-reconciliation building block) is proven stable and non-mutating on repeated reads.
- [x] `scripts/measure_performance.py`: measures and saves (not just prints) OPA policy-call and end-to-end latency percentiles, the fleet-halt commit-to-denial bound, shadow-replay duration, receipt coverage and a fresh zero-overshoot confirmation to `docs/verification/PERFORMANCE.md`, reproducible by re-running against a reset stack.
- [x] Fresh-machine Docker verification: `docker compose down -v` (removed the named Postgres volume) plus `docker rmi` of all five project-built images, then a full `docker compose build` + `docker compose up -d` from nothing but the repo checkout. All six containers reached healthy/running; `pytest tests/` (38 passed, 2 skipped -- same documented headroom-skip pattern), `scripts/run_scenarios.py` (11/11) and `scripts/measure_performance.py` all passed cleanly against the freshly built, freshly migrated, freshly seeded stack. Scope note: base images (`python`, `node`, `postgres`, `opa`) were already present in the local Docker image cache, so this did not re-exercise a first-time image pull over the network -- everything downstream of that (build, migrate, seed, run) was verified from zero project state.
- [x] `README.md` rewritten end to end: accurate architecture summary and diagram, fresh-machine quickstart, demo/test/measurement instructions, project structure, honest limitations -- replacing the stale Milestone-2-era scaffold description.
- [x] `docs/PROJECT_DESCRIPTION.md`: the mandatory project description (problem, what was built, why it matters, what was measured vs. claimed, honest scope).
- [x] `docs/DECK.md` (portable markdown source) and `docs/deck.html` (self-contained, presentable HTML version, published as a Claude artifact) -- a 12-slide deck plus appendix: problem, what was built, architecture, permit lifecycle, concurrency correctness, governance controls, audit/replay, measured results table, the eleven-scenario demo, honest limitations, close, and an appendix (tech stack, selected invariants, doc index).
- [x] `docs/VIDEO_SCRIPT.md`: a shot-by-shot, timestamped storyboard for the 90-120 second walkthrough video, built around the same eleven scenarios and mapped to exact dashboard tabs/terminal commands so it's rehearsable and reproducible, not improvised.
- [x] `docs/DEMO_REHEARSAL.md`: a live-demo checklist (setup, a dashboard-first narrated sequence, a terminal-only fallback via `scripts/run_scenarios.py`, and known rough edges to narrate around rather than hide).

## In progress

- [ ] Nothing in progress on the engineering/documentation side.

## Not started (human actions, outside what this file can automate)

- [ ] Record the actual 90-120 second walkthrough video (script is ready: `docs/VIDEO_SCRIPT.md`).
- [ ] Live-rehearse the demo at least once against the checklist (`docs/DEMO_REHEARSAL.md`) before presenting.
- [ ] Export/finalize the deck for submission (`docs/deck.html` can be presented directly from a browser, printed to PDF, or its content in `docs/DECK.md` pasted into PowerPoint/Keynote/Google Slides).
- [ ] Submit early per HANDOFF.md's guidance, then treat later submissions as verified-fix-only.

## Next actions

1. Record the walkthrough video from `docs/VIDEO_SCRIPT.md`, do at least one live rehearsal from `docs/DEMO_REHEARSAL.md`, then submit.
2. Continue committing and pushing to `origin/main` at each milestone boundary.

## Current blockers

- No active implementation blocker. Remaining Milestone 8 items (video recording, live rehearsal, submission) are human actions outside what an automated session can perform.

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
| 2026-07-27 | OPA strict check, format check and policy tests | Pass — OPA 1.17, `PASS: 22/22` |
| 2026-07-27 | `docker compose config` validates | Pass |
| 2026-07-27 | `docker compose build` (all 4 custom images) | Pass |
| 2026-07-27 | `docker compose up -d` then `docker compose ps` | Pass — postgres, opa, broker, mock-bank, agent-simulator, frontend all `Up`/`healthy` |
| 2026-07-27 | `curl http://localhost:8000/ready` | Pass — `{"status":"ready","checks":{"database":true,"opa":true}}` |
| 2026-07-27 | `curl http://localhost:8100/ready` | Pass — `{"status":"ready","checks":{"broker":true}}` |
| 2026-07-27 | `curl http://localhost:5173/` | Pass — HTTP 200 |
| 2026-07-27 | `psql \dn` inside postgres container | Pass — `broker` owned by `mandateguard_broker`, `bank` owned by `mandateguard_bank` |
| 2026-07-27 | mock-bank port published to host | Confirmed not published; only broker, agent-simulator, opa and frontend ports are mapped |
| 2026-07-27 | `alembic upgrade head` via `migrate` Compose service | Pass — both migrations applied, `broker`/`bank` tables created and seeded |
| 2026-07-27 | `pytest tests/test_refund_intake.py -v` against the live stack | Pass — `18 passed` |
| 2026-07-27 | `alembic upgrade head` via `migrate` Compose service (migrations 0003, 0004) | Pass — budget/permit/execution tables created, `payment-demo-004` seeded |
| 2026-07-27 | Manual smoke test: `POST /api/v1/refunds` for an ALLOW-eligible amount | Pass — `status: SUCCEEDED`, bank balance decremented, signed refund recorded in `bank.refunds` |
| 2026-07-27 | `pytest tests/` (both suites) against the live stack, after `scripts/reset_dev_state.sql` | Pass — `23 passed` |
| 2026-07-27 | OPA strict check, format check and policy tests after `override_config` change | Pass — OPA 1.17, `PASS: 22/22` |
| 2026-07-27 | `alembic upgrade head` via `migrate` Compose service (migration 0005) | Pass — control/approval/checkpoint/replay tables created |
| 2026-07-27 | `pytest tests/test_governance_workflows.py -v` against the live stack, after reset | Pass — `8 passed` |
| 2026-07-27 | `pytest tests/` (all three suites) against the live stack, after reset | Pass — `30 passed, 1 skipped` (the skip is the concurrency-headroom-dependent approval test, which needs the fleet budget headroom that `test_budget_execution.py`'s concurrency burst consumes earlier in the same run -- it passes `8/8` when `test_governance_workflows.py` is run alone after a reset) |
| 2026-07-27 | `tsc -b && vite build` in `frontend/` | Pass — clean type-check, `159.51 kB` JS bundle |
| 2026-07-27 | Direct HTTP checks of every new `/api/v1/admin/*` view endpoint the dashboard calls | Pass — governance, agents, actions (list + detail), exposure, receipts (list + verify) all returned the expected shape |
| 2026-07-27 | CORS preflight (`OPTIONS` with `Origin: http://localhost:5173`) against the broker | Pass — `access-control-allow-origin` and `x-operator-token` both present |
| 2026-07-27 | `pytest tests/` after the `ExecutionReceipt.created_at` mapping fix | Pass — `30 passed, 1 skipped` (same as above, confirming no regression) |
| 2026-07-27 | `python scripts/run_scenarios.py` (all 11 scenarios), twice in a row from a reset | Pass both runs — `11/11 scenarios passed`, matching key metrics each time (e.g. concurrent burst: `32` fired, `22` allowed, `22` succeeded, both runs) |
| 2026-07-27 | Dashboard browser walkthrough | Pass — throwaway Playwright script (kept outside the repo) screenshotted all 7 tabs against live data and drove real interactive round-trips (policy replay, receipt verify, held-action approve); zero console errors; `pytest tests/` still passed after the live-mutating interaction |
| 2026-07-27 | `pytest tests/test_verification.py -v` standalone, after reset | Pass — `9 passed` |
| 2026-07-27 | `pytest tests/` (all four suites) against the live stack, after reset | Pass — `38 passed, 2 skipped` (same documented shared-fleet-headroom skip pattern as Milestone 5/6 runs) |
| 2026-07-27 | `python scripts/measure_performance.py` against the live stack, after reset | Pass — results written to `docs/verification/PERFORMANCE.md`: policy p50/p95/p99 ≈ 50/52/58ms, end-to-end p50/p95/p99 ≈ 80/97/151ms (n=40), halt commit-to-denial bound max 83ms over 5 repeats, shadow-replay 477ms for 40 evaluated actions, receipt coverage 40/40 (100%), concurrent burst zero-overshoot confirmed (24/24, never more) |
| 2026-07-27 | `python scripts/run_scenarios.py` (all 11 scenarios) re-run after this milestone's changes | Pass — `11/11 scenarios passed`, no regression from the new tests/measurement script |
| 2026-07-27 | Fresh-machine verification: `docker compose down -v` + `docker rmi` of all 5 project images, then `docker compose build` + `docker compose up -d` from the repo checkout alone | Pass — all 6 containers reached healthy/running; broker and agent-simulator `/ready` both `true`; frontend HTTP 200 |
| 2026-07-27 | `pytest tests/` against the freshly rebuilt stack | Pass — `38 passed, 2 skipped` |
| 2026-07-27 | `python scripts/run_scenarios.py` against the freshly rebuilt stack | Pass — `11/11 scenarios passed` |
| 2026-07-27 | `python scripts/measure_performance.py` against the freshly rebuilt stack | Pass — results re-saved to `docs/verification/PERFORMANCE.md`; receipt coverage 40/40 (100%), zero-overshoot burst 24/24 |
