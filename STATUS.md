# MandateGuard Build Status

Last updated: 2026-07-27

This file is the durable handoff point. Read it first after any interrupted or context-limited session.

## Current milestone

**Milestone 2 — Runnable service scaffold**

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

## In progress

- [ ] Nothing in progress; ready to start Milestone 3.

## Next actions

1. Add Alembic and create the broker/bank tables from `docs/DATA_MODEL.md` (Milestone 3, step 1-2).
2. Seed governance state, payments, agents, public keys and baseline policy configuration.
3. Implement agent token verification and idempotent `POST /api/v1/refunds` intake wired to OPA.

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
