# MVP Data Model

Use UUID primary keys, UTC timestamps, integer minor units and explicit state enums. One PostgreSQL instance contains separate `broker` and `bank` schemas with different owning roles.

## Broker schema

### Identity and controls

`agents`

- Token subject, name, type and deployment version
- `ACTIVE` or `REVOKED`
- Monotonic agent epoch
- Status reason and operator metadata

`agent_credentials`

- Agent ID, key ID, public key and validity window

`operator_users`

- Email, password hash, role (`OPERATOR` or `APPROVER`) and active status

`governance_state`

- Singleton row
- `RUNNING` or `HALTED`
- `NORMAL` or `ELEVATED` risk mode
- Active policy version
- Monotonic global control epoch
- Last actor, reason and time

`control_actions`

- Idempotent record of halt, resume, risk, revoke, restore, activate and rollback commands
- Before/after snapshots and required reason

### Policy

`policy_versions`

- Version number, base version and checksum
- `DRAFT`, `CANDIDATE`, `APPROVED`, `ACTIVE` or `RETIRED`
- Versioned JSON configuration
- Creator and separate approver metadata

`policy_limits`

- Scope: action, customer, agent or fleet
- Metric: amount or count
- Window and currency
- Normal and elevated caps
- Overflow behavior: deny or hold

### Actions and approvals

`action_requests`

- Agent and idempotency key
- Canonical request hash
- Trusted payment/customer context
- Amount, currency and reason code
- Action state and policy decision
- Public reason and operator explanation
- Policy, risk and epoch snapshots
- Unique `(agent_id, idempotency_key)`

`policy_evaluations`

- Initial or approval-recheck phase
- Exact input snapshot and output
- Decision, reasons, version and measured latency

`approvals`

- One decision per held request
- Approver, reason, idempotency key and timestamp

### Financial exposure

`budget_locks`

- Semantic lock row for each applicable scope/metric/currency
- Locked in deterministic key order during reservation

`budget_reservations`

- One per action
- Amount and `RESERVED`, `COMMITTED`, `RELEASED` or `UNKNOWN` state
- Relevant timestamps and resolution reason

`reservation_allocations`

- Reservation units allocated to customer, agent and fleet scopes
- Amount and velocity metrics
- Effective time for rolling-window calculations

`velocity_events`

- Unique action event for rolling count limits

The safety invariant for every scope is:

```text
committed usage in window + active/unknown reservations <= effective cap
```

### Permits and outcomes

`action_permits`

- Unique JTI, action, reservation and attempt
- Token/payload hashes only; never expose the reusable token in receipts
- Policy and epoch snapshots
- `ISSUED`, `CONSUMED`, `CANCELLED` or `EXPIRED`
- Unique JTI and request/attempt constraints

`execution_receipts`

- One signed receipt document per terminal action
- Document hash, signature, key ID and schema version

### Audit

`audit_stream_heads`

- Last sequence and hash per action or control stream

`audit_events`

- Stream sequence, previous hash and event hash
- Actor, event type, safe payload and correlation IDs
- Inserted in the same transaction as the state mutation it describes

`audit_checkpoints` and `audit_checkpoint_items`

- Signed manifest over protected event hashes
- Exported separately from normal event rows

### Shadow replay

`policy_replay_runs`

- Candidate, baseline, selected time range, filters and run status
- Summary decision and exposure deltas

`policy_replay_results`

- One baseline/candidate comparison per historical action
- Stable ordering and reason differences

Replay is read-only: it cannot create reservations, permits, refunds or live audit events.

## Bank schema

`payments`

- Payment, trusted customer, currency, original amount and refundable remaining amount

`permit_uses`

- Unique permit JTI and request ID
- Token/body hashes, use time and result

`refunds`

- Unique request ID and permit JTI
- Payment, amount, currency, bank transaction ID and definitive status

`bank_operation_events`

- Internal append-only bank lifecycle records used to produce the signed execution assertion

## Core uniqueness constraints

```text
action_requests(agent_id, idempotency_key)
budget_reservations(action_id)
action_permits(jti)
action_permits(action_id, attempt_number)
refunds(request_id)
refunds(permit_jti)
velocity_events(scope, scope_id, action_id)
```

## Transaction rule

No transaction stays open during an OPA or mock-bank HTTP request. Intake, policy persistence, reservation, permit consumption, bank mutation, finalization and reconciliation each use separate short transactions with explicit idempotency.
