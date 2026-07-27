# MVP API Contract

All timestamps are UTC ISO 8601. All money uses integer minor units. JSON fields use `snake_case`.

## Agent API

### `POST /api/v1/refunds`

Headers:

```text
Authorization: Bearer <signed-agent-token>
Idempotency-Key: <unique-string>
```

Body:

```json
{
  "payment_id": "pay_001",
  "amount_minor": 10000,
  "currency": "USD",
  "reason_code": "CUSTOMER_REQUEST"
}
```

The agent does not send `agent_id`, `customer_id`, limit values or policy facts.

Response is an action resource containing the current status, decision, safe reason codes and links. The permit remains internal.

Idempotency behavior:

- Same agent, key and canonical body: return the original action.
- Same agent and key with a different body: return `409 Conflict`.
- Concurrent identical requests: create at most one action, reservation, permit and bank refund.

A policy denial is a successful domain decision, not an authentication error. Invalid caller identity uses `401` or `403`; a valid but forbidden action returns an action with decision `DENY`.

### `GET /api/v1/actions/{action_id}`

An agent can read only its own action.

### `GET /api/v1/actions/{action_id}/receipt`

Returns the redacted signed execution receipt when available.

## Operator API

### Authentication and overview

```text
POST /api/v1/operator/login
GET  /api/v1/operator/overview
GET  /api/v1/operator/events
```

`events` is a server-sent event stream for the live dashboard.

### Actions and approvals

```text
GET  /api/v1/operator/actions
GET  /api/v1/operator/actions/{action_id}
POST /api/v1/operator/actions/{action_id}/approval
GET  /api/v1/operator/limits/usage
```

Approval body includes `APPROVE` or `DENY`, a required reason and an idempotency key. Approval triggers complete policy/control/budget re-evaluation and cannot override a halt, revocation or hard limit.

### Agent and fleet controls

```text
POST /api/v1/operator/agents/{agent_id}/revoke
POST /api/v1/operator/agents/{agent_id}/restore
POST /api/v1/operator/fleet/halt
POST /api/v1/operator/fleet/resume
PUT  /api/v1/operator/fleet/risk-mode
```

Every mutation requires a reason and idempotency key. Halt, resume and risk-mode changes increment the global control epoch. Revoke and restore increment the agent epoch.

### Policy lifecycle

```text
GET  /api/v1/operator/policies
POST /api/v1/operator/policies/candidates
POST /api/v1/operator/policies/{policy_id}/approve
POST /api/v1/operator/policies/{policy_id}/replay
POST /api/v1/operator/policies/{policy_id}/activate
POST /api/v1/operator/policies/{policy_id}/rollback
GET  /api/v1/operator/replays/{replay_id}
```

The creator cannot approve their own candidate. Only an approved version can activate. Activation and rollback increment the global epoch.

### Receipts and audit

```text
GET  /api/v1/operator/receipts/{action_id}
POST /api/v1/operator/receipts/{action_id}/verify
POST /api/v1/operator/audit/checkpoints
POST /api/v1/operator/audit/verify
```

## Broker-internal API

```text
GET  /.well-known/permit-jwks.json
POST /internal/v1/permits/{jti}/consume
```

The consume operation is broker-service authenticated and atomic. It locks the permit, action, reservation, agent and governance state; rechecks expiry, halt, revocation and epochs; then moves an eligible permit from `ISSUED` to `CONSUMED` and the action to `EXECUTING`.

## Mock-bank internal API

```text
GET  /internal/v1/payments/{payment_id}
POST /internal/v1/refunds
GET  /internal/v1/refunds/by-request/{request_id}
GET  /.well-known/execution-jwks.json
```

The refund endpoint requires broker service authentication and a valid permit. Request financial fields must exactly match permit claims. A bank transaction consumes the unique permit/request identifiers, locks the payment and records the refund at most once.

The bank signs its definitive execution result. A timeout is reconciled by querying `by-request`; the broker never blindly repeats the refund command.

The bank port is not published to the host. The simulator may share the Docker network for the bypass demo but does not possess the broker service credential.

## Demo runner API

The simulator, not the broker, exposes:

```text
POST /demo/v1/reset
POST /demo/v1/scenarios/{scenario_name}
GET  /demo/v1/runs/{run_id}
```

Scenario names cover normal refund, held approval, permission denial, direct bypass, concurrent burst, elevated risk, halt, duplicate request, permit replay, audit tamper and policy replay.

## Service operations

Every service exposes:

```text
GET /health
GET /ready
```

`health` proves the process is alive. `ready` verifies required dependencies for safe traffic.

## Error envelope

Transport and validation failures use:

```json
{
  "error": {
    "code": "STABLE_MACHINE_CODE",
    "message": "Safe human-readable message",
    "correlation_id": "uuid"
  }
}
```

Agent-facing messages do not reveal sensitive internal rule thresholds. Operator responses may contain the fuller explanation.
