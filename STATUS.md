# MandateGuard Build Status

Last updated: 2026-07-27

This file is the durable handoff point. Read it first after any interrupted or context-limited session.

## Current milestone

**Milestone 3 — Identity, data and decisions**

Status: complete, pending final commit

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

## In progress

- [ ] Nothing in progress; ready to start Milestone 4.

## Next actions

1. Milestone 4: atomic budget reserve/commit/release, signed single-use permits, and real mock-bank execution wired to the `ALLOW` path.
2. Extend the schema/migrations for budgets, permits and receipts when that work starts (kept out of Milestone 3 on purpose).
3. Continue committing and pushing to `origin/main` at each milestone boundary.

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
