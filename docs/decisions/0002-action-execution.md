# Decision 0002: Broker-Executed Actions and One-Use Permits

Status: accepted

Date: 2026-07-27

## Decision

MandateGuard will not return a reusable “allowed” boolean to an agent. It will reserve exposure, issue a short-lived one-use permit and execute the downstream refund through the broker. The mock bank independently verifies the permit and consumes its nonce.

## Reason

A voluntary permission check can be bypassed, replayed or followed by a changed action. Binding approval to exact parameters and enforcing it at the downstream boundary makes the governance claim demonstrable.

## Consequences

- The broker is part of the execution path.
- Availability failures for money-changing actions fail closed.
- Permit signing, expiry, nonce consumption and idempotency require explicit tests.
- A production design would require replicated enforcement and protected keys, but those are outside the MVP.
