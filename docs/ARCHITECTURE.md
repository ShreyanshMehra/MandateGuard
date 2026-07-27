# MVP Architecture

## Components

### Operator dashboard

A React application for live activity, approvals, exposure, revocation, fleet controls, policy replay and receipt verification.

### MandateGuard broker

A FastAPI service that is both the public API and the policy enforcement point. It authenticates agents, validates requests, asks OPA for a decision, reserves limits, issues permits, executes through the mock bank, reconciles outcomes and appends lifecycle events.

### OPA policy service

Evaluates versioned Rego rules against structured input. It returns `ALLOW`, `DENY`, or `HOLD_FOR_APPROVAL`, a stable reason code, operator explanation and effective constraints.

OPA does not own identity, budgets, permits, action state or execution.

### PostgreSQL

One PostgreSQL server contains separate `broker` and `bank` schemas owned by different roles. The broker schema is the transactional source of truth for identities, rules metadata, controls, budgets, reservations, actions, approvals, permit nonces and audit events. The bank schema owns payments and refunds.

The broker role cannot write bank tables, and the bank role cannot modify governance tables.

### Mock bank

A private FastAPI service that owns the simulated payment/refund ledger. It accepts execution only from the broker, verifies the signed permit, prevents duplicate nonce/request use, and signs its execution result.

### Agent simulator

Produces deterministic normal, out-of-mandate, burst, duplicate, replay and bypass scenarios.

## Logical flow

```text
Agent simulator
      |
      | signed identity + refund request
      v
MandateGuard broker ---------------------- Operator dashboard
      |          |                                  |
      |          +---- PostgreSQL ------------------+
      |
      +---- structured policy input ----> OPA
      |<--- allow / deny / hold ----------+
      |
      +---- service identity + permit ---> Mock bank
      |<--- signed result / timeout --------+
```

The mock bank is not exposed to agent credentials. In production, broker-only access would also be enforced by network policy and workload identity.

## Allowed-request sequence

1. Validate schema and timestamp.
2. Verify agent identity token.
3. Resolve or create the action by idempotency key.
4. Fetch trusted payment, customer and refundable-amount context from the mock bank.
5. Check fleet and agent control state.
6. Ask OPA for the decision using current policy data.
7. If denied, persist denial and return.
8. If held, persist the hold and return an approval reference.
9. If allowed, atomically reserve every applicable budget and persist the transition.
10. Sign a short-lived permit containing the reservation and control epochs.
11. Recheck and consume the permit immediately before execution.
12. Call the private mock bank without holding a database transaction open.
13. Verify the bank-signed result.
14. Commit, release or retain the reservation based on the outcome.
15. Persist all lifecycle events and return the receipt reference.

## Approval sequence

1. Approver opens a held action.
2. Approver approves or denies with a reason.
3. On approval, MandateGuard rechecks identity status, controls, active policy and budgets.
4. If still valid, the normal reserve/permit/execute path continues.
5. Approval never bypasses limits or an active halt.

## Revocation and halt

The database stores a monotonically increasing control epoch.

- Revoking an agent increments its epoch and marks it revoked.
- Fleet halt increments the fleet epoch and marks global halt active.
- Permits contain both epochs.
- The broker and mock bank reject stale epochs.

The prototype measures the time from committed halt to the first consistently denied new request. It does not claim to cancel a refund already committed by the mock bank.

## Budget transaction boundary

Reservation of the customer, agent and fleet dimensions occurs in one PostgreSQL transaction. Rows are locked in a deterministic order to avoid races and reduce deadlock risk.

The invariant is:

```text
committed_usage + active_reservations <= configured_limit
```

for every applicable scope and window.

No database transaction remains open while calling OPA or the mock bank.

## Audit design

Each lifecycle event uses canonical serialization and contains:

- Sequence number
- Previous event hash
- Event hash
- Action/correlation ID
- Event type
- Safe event payload
- Timestamp
- Actor identity
- Policy and control versions where relevant

Periodic checkpoints sign the current sequence, event hash and event count. Checkpoints are exported separately from ordinary event rows in the prototype.

This detects edits relative to a trusted checkpoint. It does not make the database physically immutable.

## Shadow replay

Candidate policies never affect live decisions. The replay service evaluates saved historical request snapshots against both active and candidate policy versions and stores a difference report. Activation requires an operator action and preserves the prior version for rollback.

Budgets and downstream execution are not changed during replay.

## Deployment model

The prototype uses Docker Compose on one machine. The production diagram may show replicated brokers and policy sidecars, but claims and measurements will explicitly apply only to the local prototype.
