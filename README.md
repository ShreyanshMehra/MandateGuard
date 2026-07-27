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

See [PROJECT_PLAN.md](PROJECT_PLAN.md) for the complete build sequence and acceptance checks.
