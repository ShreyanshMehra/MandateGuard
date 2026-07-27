# MandateGuard refund policy

This directory contains the stateless OPA decision layer for the MVP's only
money-changing action, `refund_payment`.

## Decision contract

Query:

```text
data.mandateguard.refund.decision
```

Every evaluation returns exactly one outcome:

- `ALLOW` — policy checks pass; the broker must atomically reserve every listed
  budget scope before issuing a one-use permit.
- `HOLD` — a human with the returned approval role must review the request. No
  budget is reserved while held; policy and budgets must be checked again after
  approval.
- `DENY` — nothing may be reserved, permitted, or executed.

The `reason_code` and `public_explanation` are safe stable client fields.
`operator_explanation` is detailed operational context and should not be exposed
to an untrusted agent without redaction.

OPA does **not** authenticate tokens, reserve budgets, halt the fleet, issue
permits, or execute refunds. The broker supplies verified identity/control state
as input and enforces returned obligations. PostgreSQL remains the source of
truth for mutable exposure.

## Input example

```json
{
  "agent": {
    "id": "refund-agent-v1",
    "authenticated": true,
    "status": "ACTIVE"
  },
  "request": {
    "action": "refund_payment",
    "payment_id": "payment-demo-001",
    "customer_id": "customer-demo-001",
    "amount_minor": 5000,
    "currency": "USD"
  },
  "context": {
    "risk_mode": "NORMAL"
  }
}
```

`amount_minor` must be a positive whole number. In USD, `5000` means `$50.00`.
Only `NORMAL` and `ELEVATED` risk modes are accepted.

## Versioned configuration

`policy_config.json` is the runnable example configuration. Its root becomes
`data.mandateguard.config`. `schema_version` protects the evaluator/config
contract, while `policy_version` identifies the business rule version in every
decision and eventual execution receipt.

Threshold semantics are exact:

- amount `<= approval_threshold_minor`: `ALLOW`
- amount `> approval_threshold_minor` and `<= hard_max_minor`: `HOLD`
- amount `> hard_max_minor`: `DENY`

Do not put mutable budget usage into this JSON file. The broker checks and
reserves customer, agent, and fleet exposure transactionally after policy
evaluation.

## Run tests with OPA 1.17

From the repository root, with a local OPA binary:

```powershell
opa test .\policies -v
```

Or with Docker (works without installing OPA):

```powershell
docker run --rm -v "${PWD}:/workspace" -w /workspace openpolicyagent/opa:1.17.0-static test ./policies -v
```

Expected summary:

```text
PASS: 22/22
```

## Evaluate an input file

If `request.json` contains the example input:

```powershell
opa eval --data .\policies --input .\request.json "data.mandateguard.refund.decision"
```

Docker equivalent:

```powershell
docker run --rm -v "${PWD}:/workspace" -w /workspace openpolicyagent/opa:1.17.0-static eval --data ./policies --input ./request.json "data.mandateguard.refund.decision"
```
