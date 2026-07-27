# MVP Product Contract

## Product promise

MandateGuard ensures that no simulated financial agent can execute a refund without authenticated identity, an allowed mandate, available financial exposure, a valid one-use permit, and a complete execution record.

## Primary user

A bank AI-platform or risk-control operator responsible for supervising autonomous agents.

Secondary users are human approvers, auditors and agent developers.

## Supported financial action

The MVP implements one action deeply:

```text
refund_payment(payment_id, amount_minor, currency, reason_code)
```

`amount_minor` is an integer in the currency's smallest unit. For USD, `10000` means `$100.00`.

The agent does not supply the customer identity or the refundable balance. MandateGuard obtains both from the trusted mock bank using the payment ID.

## Simulated actors

| Actor | Intended mandate | Demo purpose |
|---|---|---|
| `refund-agent-v1` | Refund eligible card payments within limits | Normal traffic |
| `travel-agent-v1` | Travel actions only; no refund permission | Out-of-mandate denial |
| `rogue-refund-agent-v1` | Starts with refund permission, then behaves maliciously | Burst, bypass and replay demonstrations |
| Operator | Observe, revoke, halt and propose rules | Incident response |
| Approver | Approve or deny held actions | Human oversight |
| Auditor | Search and verify receipts | Evidence review |

## Request contract

Every request must include:

- A signed, short-lived agent identity token
- A globally unique idempotency key
- Action name
- Payment ID
- Amount in integer minor units
- ISO currency code
- Business reason code
- Request timestamp

The server derives the agent identity from the verified token and the customer from trusted payment data. It never trusts caller-supplied identity fields.

## Decision outcomes

### `ALLOW`

The request satisfies policy and budgets. MandateGuard reserves exposure and proceeds toward execution.

### `DENY`

The request is forbidden or unsafe. Nothing is reserved or executed.

### `HOLD_FOR_APPROVAL`

The request may be legitimate but requires a human. Nothing executes until an approver acts; policy and budgets are checked again at approval time.

## Separate lifecycles

Action, reservation and permit states are intentionally separate. Combining them would hide important failure cases.

### Action

```text
RECEIVED
├── DENIED
├── HELD
│   ├── DENIED_BY_APPROVER
│   └── BUDGET_RESERVED
└── BUDGET_RESERVED
    └── PERMIT_ISSUED
        └── EXECUTING
            ├── SUCCEEDED
            ├── FAILED
            └── UNKNOWN
                ├── RECONCILED_SUCCEEDED
                └── RECONCILED_FAILED
```

Every transition is explicit, validated and appended to the audit history.

### Reservation

```text
RESERVED
├── COMMITTED
├── RELEASED
└── UNKNOWN
    ├── COMMITTED after reconciliation
    └── RELEASED after reconciliation
```

An unknown external outcome keeps consuming capacity until reconciliation proves whether execution occurred.

### Permit

```text
ISSUED
├── CONSUMED
├── CANCELLED
└── EXPIRED
```

## Financial limits

The MVP enforces all applicable limits together:

- Per-action maximum
- Per-customer rolling or daily exposure
- Per-agent rolling or daily exposure
- Fleet-wide rolling or daily exposure
- Refund-count velocity per minute

Elevated-risk mode applies a configurable multiplier and may change an otherwise allowed request into a hold or denial.

Final demo values will be seed data, not hard-coded business logic.

## Action Permit

An Action Permit is a signed, short-lived, one-use authorization bound to:

- Agent identity and deployment version
- Action
- Payment and customer
- Exact amount and currency
- Request and reservation IDs
- Policy version
- Control/revocation epoch
- Issued-at and expiry times
- Unique nonce

Changing any bound field invalidates the permit. The mock bank records nonce consumption transactionally so the same permit cannot execute twice.

## Execution Receipt

The receipt connects the complete lifecycle:

- Authenticated identity
- Original request digest and safe display fields
- Policy decision, reason and version
- Budget reservation
- Approval decision, if any
- Permit digest and nonce
- Mock-bank outcome
- Mock-bank signed execution assertion
- Budget commit, release or reconciliation
- Relevant operator actions
- Audit-chain position and signed checkpoint reference

The MVP calls this record tamper-evident, not immutable.

## Operator capabilities

- View live requests and their reasons
- View customer, agent and fleet exposure
- Approve or deny held requests
- Revoke or restore one agent
- Enter or leave elevated-risk mode
- Halt all new money-changing actions
- Resume after recording a reason
- Create, simulate, activate and roll back rule versions
- Search, export and verify an execution receipt

## Measured success criteria

- All defined policy cases return the expected outcome.
- No budget overshoot under the concurrency test.
- Direct mock-bank calls are rejected.
- Changed, expired and replayed permits are rejected.
- Duplicate idempotency keys execute at most once.
- All new money-changing requests are denied within the measured halt propagation bound.
- Every executed mock-bank action has a complete receipt.
- Protected audit edits are detected.
- Candidate-policy replay produces a clear impact difference before activation.

## Explicit non-goals

- Real American Express or banking integration
- Real customer data
- Fraud detection
- Prompt-injection prevention
- Learned anomaly detection
- Production multi-region availability
- Production hardware-backed keys
- Foreign-exchange conversion or cross-currency shared limits
- Undoing an action that already completed before a halt
