# MandateGuard

MandateGuard is a prototype governance layer for financial AI agents, created for American Express CodeStreet 2026.

Its core promise is simple:

> No AI agent can perform a financial action without bounded authority, reserved financial exposure, and verifiable proof of execution.

The prototype will focus deeply on one workflow: card-payment refunds.

## Locked product choices

- Keep the Governance Layer for Financial Agents problem statement.
- Build an action-executing broker, not a voluntary allow/deny API.
- Issue signed, short-lived, single-use Action Permits.
- Produce an Execution Receipt for every completed or failed action.
- Support `ALLOW`, `DENY`, and `HOLD_FOR_APPROVAL`.
- Enforce hierarchical and dynamically tightened limits.
- Use policy shadow replay as the secondary differentiator.
- Build a deterministic demonstration and a 90–120 second video.
- Use FastAPI, OPA, PostgreSQL, React, and Docker Compose.
- Do not add anomaly-detection ML or a real LLM until the safety core is correct.

See [PROJECT_PLAN.md](PROJECT_PLAN.md) for the complete build sequence and acceptance checks, and [HANDOFF.md](HANDOFF.md) / [STATUS.md](STATUS.md) for the current milestone state.

## Running the scaffold

```powershell
Copy-Item .env.example .env
docker compose build
docker compose up -d
docker compose ps
```

This starts `postgres`, `opa`, `broker`, `mock-bank`, `agent-simulator` and `frontend`. The broker (`http://localhost:8000`), agent simulator (`http://localhost:8100`), OPA (`http://localhost:8181`) and frontend (`http://localhost:5173`) are published to the host; `mock-bank` and `postgres` are intentionally Docker-internal only. Every backend service exposes `GET /health` and `GET /ready`; `broker /ready` also verifies PostgreSQL and OPA connectivity.

Domain endpoints (refund intake, identity, budgets, permits, dashboards) are not implemented yet — see `HANDOFF.md` section 11 for the milestone sequence.
