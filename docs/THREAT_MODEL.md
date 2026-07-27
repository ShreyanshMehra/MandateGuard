# MVP Threat Model

## Security objective

Contain the financial damage a compromised, buggy or over-authorized agent can cause, while producing evidence of every decision and actual execution.

MandateGuard does not claim to prevent an agent from being compromised. It limits what a compromised agent can successfully do.

## Trust boundaries

1. **Untrusted agent boundary:** all agent input, including IDs and reasons, is untrusted.
2. **Operator boundary:** operator actions require authenticated roles and are audited.
3. **MandateGuard boundary:** the broker is the only component allowed to request mock-bank execution.
4. **Policy boundary:** OPA provides decisions but does not authenticate callers, reserve money or execute refunds.
5. **Database boundary:** PostgreSQL is the source of truth for limits, reservations, action state and nonce consumption.
6. **Mock-bank boundary:** the mock bank independently verifies execution authorization and idempotency.

## Threats and controls

| Threat | Control | Demonstration or test | Honest limitation |
|---|---|---|---|
| Caller lies about its agent ID | Signed short-lived identity token; identity derived from verified claims | Forged and expired tokens are rejected | Prototype keys are software-managed |
| Agent calls the bank directly | Mock bank accepts broker authentication plus a valid permit only | Rogue direct call is rejected | Production would use workload identity, mTLS and network policy |
| Agent changes amount after approval or invents a customer | Customer comes from bank data; permit binds exact action fields and signature | Modified request fails verification | Does not validate real-world entitlement beyond seeded data |
| Permit is reused | Broker consumes once before execution; mock bank also enforces unique permit and request IDs | Second use is rejected | Cross-region nonce consistency is out of scope |
| Duplicate client retry creates two refunds | Unique idempotency key returns the original action/result | Concurrent duplicate test executes once | Unknown external outcomes still require reconciliation |
| Parallel requests exceed a limit | One database transaction locks/checks/reserves every applicable limit | Concurrent split-refund test shows zero overshoot | Single PostgreSQL deployment only |
| Agent splits one large refund into many small refunds | Customer/agent/fleet exposure plus rolling count limit | Burst triggers hold/deny despite each action being small | Rules are deterministic, not learned |
| Revoked agent uses a previously issued permit | Short permit lifetime and control epoch rechecked before execution | Old permit after revoke is rejected | Cannot undo a completed refund |
| Fleet halt races with active work | Halt epoch committed centrally; pre-execution recheck; fail closed | Measured last allow and first denial during load | A downstream request already accepted may finish |
| Malicious operator expands authority | Role checks, recorded reason, versioned rules, shadow replay and approval for activation | Unauthorized role and unapproved activation tests | Full enterprise identity governance is out of scope |
| Operator accidentally publishes a bad rule | Candidate replay, impact report, explicit activation and rollback | Historical traffic shows decision differences | Historical traffic cannot predict every future request |
| Database history is edited | Canonical event hashes and separately signed checkpoints | Mutation causes verification failure | Software-held signing key is not third-party attestation |
| Audit service is unavailable | Money-changing action fails closed unless durable lifecycle event is stored | Simulated persistence failure denies execution | Availability trade-off is intentional |
| OPA is unavailable | Fail closed for new money-changing actions | OPA outage integration test | No last-known-good degraded mode in MVP |
| Mock bank times out | Mark action `UNKNOWN`; do not blindly retry; reconcile by idempotency key | Timeout scenario later resolves once | Real bank reconciliation is simulated |
| Sensitive information leaks in logs | Store safe fields and digests; separate public reason code from operator detail | Log-shape tests | Formal privacy review is out of scope |

## Failure rules

- Identity verification failure: deny.
- Policy service unavailable: deny money-changing actions.
- Budget database unavailable: deny money-changing actions.
- Durable audit append failure: do not execute.
- Mock-bank timeout: mark `UNKNOWN`, retain reservation and reconcile.
- Duplicate idempotency key: return original state/result.
- Stale control epoch: reject the permit.
- Invalid state transition: reject and append an internal security event when possible.

## Claims we will not make

- “Instantly stops everything.” We will report a measured bound for new requests.
- “Immutable audit log.” We will say tamper-evident with signed checkpoints.
- “Prevents prompt injection.” It limits the resulting authority and exposure.
- “Production-ready banking security.” It is a defensible proof of concept.
- “AI detects rogue behavior.” The MVP uses transparent limits and circuit breakers.
