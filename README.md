# MandateGuard

MandateGuard is a working governance layer for financial AI agents, built for American Express CodeStreet 2026.

> No AI agent can perform a financial action without bounded authority, reserved financial exposure, and verifiable proof of execution.

It implements one financial action deeply -- `refund_payment` -- as a real, permit-gated, signature-verified action broker rather than a voluntary allow/deny API. An agent cannot execute a refund without authenticated identity and a live permission check; it cannot bypass MandateGuard and call the bank directly; customer/agent/fleet exposure limits hold under real concurrency; every terminal action produces a verifiable, signed execution receipt; and a candidate policy can be replayed against historical traffic before it is ever activated.

## Status

All eight build milestones are complete. See [HANDOFF.md](HANDOFF.md) for the full build log and [STATUS.md](STATUS.md) for the current verification log. Measured performance and coverage numbers live in [docs/verification/PERFORMANCE.md](docs/verification/PERFORMANCE.md) -- nothing in the project's numbers is an invented estimate.

## Architecture

```text
Agent simulator
      |
      | signed identity + refund request
      v
MandateGuard broker ---------------------- Operator dashboard
      |          |                                  |
      |          +---- PostgreSQL ------------------+
      |            (separate broker/bank schemas)
      |
      +---- structured policy input ----> OPA
      |<--- allow / deny / hold ----------+
      |
      +---- service identity + permit ---> Mock bank
      |<--- signed result / timeout --------+
```

- **Broker** (FastAPI) -- the only public entry point and the policy enforcement point. Authenticates agents, asks OPA for a decision, atomically reserves budget, issues a short-lived signed permit, executes through the mock bank, verifies the signed result, and appends hash-chained audit events.
- **OPA/Rego** -- stateless policy evaluation over versioned JSON config (`policies/`). Owns no identity, budget or execution state.
- **PostgreSQL** -- separate `broker` and `bank` schemas, owned by different roles with cross-schema writes revoked. The broker is the source of truth for identity, budgets, permits, actions, approvals and audit events; the bank schema owns payments and refunds.
- **Mock bank** (FastAPI, Docker-internal only) -- accepts execution only from the broker's service credential plus a valid, unexpired, single-use, parameter-bound Ed25519 permit; signs its own result so the broker verifies rather than trusts it.
- **Agent simulator** -- mints signed agent tokens and drives the demo/adversarial scenarios.
- **Operator dashboard** (React) -- fleet status/emergency controls, live action feed, exposure, held approvals, agent revocation, policy replay comparison, and receipt search/verification.

Full design detail: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/DATA_MODEL.md](docs/DATA_MODEL.md), [docs/API_CONTRACT.md](docs/API_CONTRACT.md), [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md), [docs/PRODUCT_CONTRACT.md](docs/PRODUCT_CONTRACT.md).

## Quickstart (fresh machine)

Requirements: Docker Desktop with Compose v2, and a Git checkout of this repository. Nothing else needs to be installed on the host -- Python, Node, PostgreSQL and OPA all run inside containers.

```powershell
git clone https://github.com/ShreyanshMehra/MandateGuard.git
Set-Location MandateGuard
Copy-Item .env.example .env
docker compose build
docker compose up -d
docker compose ps
```

Wait for every service to report `healthy`/`Up`, then confirm the stack end to end:

```powershell
curl http://localhost:8000/ready   # broker: checks Postgres + OPA
curl http://localhost:8100/ready   # agent simulator: checks broker
curl http://localhost:5173/        # dashboard
```

`postgres` and `mock-bank` are intentionally not published to the host -- only the broker may reach the mock bank, per the trust boundary in `docs/ARCHITECTURE.md`.

## Running the demo

The dashboard is the primary way to observe and operate the system:

1. Open `http://localhost:5173/`.
2. Enter the dev operator token (`dev_operator_token_change_me` by default; overridable via the `OPERATOR_TOKEN` env var in `docker-compose.yml`) in the token field.
3. Use the seven tabs to watch live traffic, approve/deny held actions, halt/resume the fleet, revoke/restore agents, run a policy replay, and search/verify receipts.

To drive the eleven deterministic demo scenarios end to end from the terminal (useful for rehearsal or CI-style verification):

```powershell
python scripts/run_scenarios.py
```

This resets dev state first, then runs normal refund, held approval, permission denial, direct-bank bypass rejection, a concurrent split-refund burst, elevated-risk tightening, fleet halt under load, duplicate idempotency, permit replay, audit tamper detection and candidate policy replay -- printing PASS/FAIL and the key metric for each. Two consecutive resets-and-reruns produce matching key results, which is the acceptance bar for "deterministic."

## Running the tests

```powershell
docker cp scripts/reset_dev_state.sql mandateguard-postgres-1:/tmp/reset_dev_state.sql
docker compose exec -T postgres psql -U mandateguard_admin -d mandateguard -f /tmp/reset_dev_state.sql
python -m pytest tests/ -v
```

The suite (`tests/test_refund_intake.py`, `test_budget_execution.py`, `test_governance_workflows.py`, `test_verification.py`) runs against the live stack -- reset dev state between runs, since execution mutates real bank balances and budget usage. One test is skipped whenever the fleet daily budget doesn't have enough headroom left in the same run for a HOLD-triggering amount; it passes cleanly when its file is run alone after a reset.

To reproduce the saved latency/coverage numbers:

```powershell
python scripts/measure_performance.py
```

This writes `docs/verification/PERFORMANCE.md`.

## Project structure

```text
services/broker/        FastAPI broker: identity, policy calls, budgets, permits, execution, governance, audit
services/mock-bank/     FastAPI mock bank: trusted payment context, permit-gated execution, signed results
services/agent-simulator/  Agent token minting and scenario traffic
frontend/               React operator dashboard
policies/               OPA/Rego policy package and its own test suite
database/                Alembic migrations and role/schema bootstrap SQL
scripts/                Dev-state reset, demo scenarios, performance measurement, key/token generation
tests/                   Milestone acceptance test suites, run against the live stack
docs/                    Product/architecture/threat-model/data-model contracts, decision records, verification results
```

## Honest limitations

- Synthetic data and limits, not real American Express policy.
- One currency (USD) and one financial workflow (`refund_payment`).
- One local PostgreSQL instance; no multi-region deployment.
- Prototype dev keys and shared-secret service credentials, not production hardware-backed identity or mTLS.
- No guarantee of reversing a refund the mock bank already applied.
- Tamper-evident audit checkpoints, not immutable storage.
- Shadow replay is a historical comparison against saved requests, not a live prediction.
- No fraud detection or prompt-injection-prevention claim.
- Manual, not automatic, reconciliation of `UNKNOWN` bank outcomes -- by design, to avoid ever retrying a refund blindly.

See [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md) for the full threat model and failure rules this prototype does and does not defend against.
