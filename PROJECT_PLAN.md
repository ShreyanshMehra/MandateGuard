# MandateGuard Prototype Build Plan

## Goal

Build a reliable, visually clear prototype proving that financial AI agents cannot bypass permissions, exceed shared spending limits, replay an approval, or hide what actually happened.

The prototype is complete only when a judge can watch a refund travel from request to decision to real change in the mock bank, then inspect proof of every step.

## Final prototype in plain language

1. Simulated agents request refunds.
2. MandateGuard verifies which agent is calling.
3. Configurable rules return `ALLOW`, `DENY`, or `HOLD_FOR_APPROVAL`.
4. MandateGuard reserves the required financial limit before execution.
5. An allowed request receives a signed, short-lived, one-use Action Permit.
6. The mock bank accepts requests only from MandateGuard and only with a valid permit.
7. Successful refunds consume the reservation; definite failures release it.
8. Every stage is recorded in a verifiable Execution Receipt.
9. Operators can approve held requests, revoke an agent, tighten limits, or halt the fleet.
10. Candidate rules can be tested against historical requests before activation.

## Planned project structure

```text
MandateGuard/
├── frontend/             Operator dashboard
├── services/
│   ├── broker/           Main MandateGuard service
│   ├── mock-bank/        Fake refund system
│   └── agent-simulator/  Normal and hostile test agents
├── policies/             OPA rules and rule tests
├── database/             Schema and seed data
├── tests/                Unit, integration, security and load tests
├── docs/                 Architecture, threat model and demo script
├── docker-compose.yml    Starts the complete prototype
├── README.md
└── PROJECT_PLAN.md
```

## Exact implementation sequence

### Step 1 — Freeze the product contract

Write down exactly what the first version supports:

- One financial action: `refund_payment`.
- Three simulated agents: normal refund agent, travel agent and rogue refund agent.
- Three outcomes: allow, deny and hold for approval.
- Four spending-limit levels: single action, customer, agent and fleet.
- One rolling speed limit, such as refunds per minute.
- One elevated-risk mode that immediately tightens limits.
- One operator role and one approver role for the prototype.

Also define the action states:

```text
RECEIVED
→ HELD or DENIED
→ BUDGET_RESERVED
→ EXECUTING
→ COMMITTED, RELEASED or UNKNOWN
→ RECONCILED when necessary
```

Acceptance check: every demo event must fit one of these states, with no vague “approved but unknown” gap.

### Step 2 — Define threats and safety promises

Create a short threat model covering:

- Fake agent identity
- Direct bypass of MandateGuard
- Changed amount after approval
- Reused Action Permit
- Duplicate retry
- Many simultaneous requests exceeding a shared limit
- Stale permission after revocation
- Malicious or mistaken operator
- Edited or deleted history
- Rule service, database or mock-bank failure

For each threat, document the prevention, the visible test and the honest limitation.

Acceptance check: every important safety claim in the presentation must have a corresponding automated or live test.

### Step 3 — Scaffold the runnable system

Create one Docker Compose setup containing:

- React dashboard
- FastAPI MandateGuard broker
- OPA rule checker
- PostgreSQL database
- Private mock-bank service
- Agent simulator

Add health checks and one command to start everything.

Acceptance check: a fresh machine can run the stack from the README without manually installing each service.

### Step 4 — Build the database safely

Create tables for:

- Agent identities and status
- Rule versions
- Spending limits and current usage
- Budget reservations
- Action requests and their lifecycle
- One-use permits
- Human approvals
- Operator actions
- Audit events and signed checkpoints
- Mock-bank transactions

Store money as whole cents, never decimal floating-point numbers. Add unique request IDs so retries cannot create a second refund.

Acceptance check: duplicate requests return the original result and concurrent requests cannot overspend.

### Step 5 — Authenticate agents

Give every simulated agent a short-lived signed identity token. MandateGuard must verify the signature, expiry, agent identity and deployment version.

Acceptance check: missing, forged and expired identities are rejected before policy or budget evaluation.

### Step 6 — Implement configurable rules

Use OPA rules to evaluate:

- Agent identity and status
- Requested action
- Customer/account scope
- Amount and currency
- Time and rolling activity
- Current risk mode
- Active rule version

Return a decision, safe public reason code and detailed operator explanation. Rules deny by default.

Acceptance check: rule tests cover allowed, denied and held requests, including unexpected input.

### Step 7 — Implement atomic financial limits

In one database transaction:

1. Lock every relevant limit.
2. Check the single-action, customer, agent and fleet availability.
3. Check the rolling speed limit.
4. Reserve the amount across every applicable level.
5. Record the reservation and decision.

After the mock bank responds, commit or release the reservation. Mark timeouts as `UNKNOWN` and reconcile them rather than blindly retrying.

Acceptance check: when twenty requests race against a fixed fleet limit, exactly the affordable set succeeds and total usage never exceeds the limit.

### Step 8 — Create one-use Action Permits

For an allowed action, create a digitally signed permit binding:

- Agent
- Action
- Customer/payment
- Exact amount and currency
- Request and reservation IDs
- Rule version
- Revocation version
- Expiry time
- Unique one-use number

Acceptance check: changed, expired, revoked and replayed permits are rejected.

### Step 9 — Enforce the permit at the mock bank

The mock bank must not trust agents. It accepts refund commands only from the MandateGuard broker and verifies the permit before changing its ledger.

Acceptance check: a rogue agent calling the mock bank directly is visibly rejected, proving that the gate cannot be bypassed voluntarily.

### Step 10 — Add approval and emergency controls

Implement:

- Held-request approval or denial
- Revoke or restore one agent
- Elevated-risk mode
- Fleet-wide halt
- Controlled resume with a recorded reason

Recheck revocation immediately before execution. Clearly state that the halt blocks new actions; it cannot undo a refund that already finished.

Acceptance check: under continuous load, the dashboard measures and shows the final allowed action and the first denied action after halt.

### Step 11 — Build complete evidence receipts

Record the entire lifecycle:

- Request received
- Identity result
- Rule decision and version
- Budget reservation
- Human approval, if any
- Permit creation and consumption
- Mock-bank result
- Budget commit, release or reconciliation
- Revocations, rule changes and operator actions

Link records with canonical hashes and periodically sign a checkpoint stored separately from ordinary rows.

Acceptance check: editing, deleting or reordering a protected record causes verification to fail. The UI must call this tamper-evident, not immutable.

### Step 12 — Add policy shadow replay

Allow an operator to create a candidate rule version and replay previous requests against it without affecting real decisions.

Show:

- Previously allowed requests that would become denied or held
- Previously denied requests that would become allowed
- Expected financial exposure change
- Breakdown by reason and agent

Only an approved candidate can become active, and the previous version remains available for rollback.

Acceptance check: the demo can compare two versions and activate the safer rule without restarting services.

### Step 13 — Build the operator dashboard

Create focused screens for:

1. Fleet status, active rule version and emergency controls
2. Live request feed with allow/deny/hold and reasons
3. Agent, customer and fleet limit usage
4. Held approvals
5. Agent details and revocation
6. Rule shadow-replay comparison
7. Searchable evidence receipts and verification

Acceptance check: the complete judged demonstration can be performed from the dashboard without using a terminal.

### Step 14 — Create deterministic demonstration scenarios

Provide buttons or a scripted runner for:

1. Successful normal refund
2. High-value refund held for approval
3. Out-of-permission request denied
4. Direct mock-bank bypass rejected
5. Concurrent split-refund burst stopped by shared limits
6. Risk mode tightening limits
7. Fleet halt during active traffic
8. Duplicate request handled once
9. Permit replay rejected
10. Audit tampering detected
11. Candidate rule shadow replay

Random background traffic may be added later, but the core demo must be repeatable.

Acceptance check: reset and replay produces the same important results every time.

### Step 15 — Test and measure honestly

Automate tests for policy correctness, authentication, permit validation, idempotency, concurrent budgets, halt behavior, audit verification and service failures.

Measure:

- Correct allow/deny/hold result rate for the test suite
- Zero budget overshoot under concurrency
- p50, p95 and p99 total decision time
- p99 fleet-halt propagation time
- Percentage of executed actions with complete receipts
- Time required to find and export one incident

Acceptance check: every number shown in the deck comes from a saved, repeatable test—not an invented estimate.

### Step 16 — Polish and package the prototype

- Improve error messages and empty/loading states.
- Remove hard-coded secrets.
- Add reset and seed commands.
- Add an architecture diagram and plain-language README.
- Confirm the complete stack works offline after images are available.
- Run the demonstration repeatedly and fix unstable steps.

Acceptance check: another person can clone, start, understand and demonstrate the project using only the README.

### Step 17 — Produce the competition material

After the prototype is stable:

- Write the mandatory project description.
- Create a 10–12 slide main deck plus appendix.
- Put working-prototype proof near the beginning.
- Record a 90–120 second deterministic walkthrough.
- Include measured results, limitations and the exact business value.
- Submit early, then use later submissions only for verified improvements.

## Build order by priority

### Must work

1. Authenticated refund request
2. Allow/deny/hold rules
3. Atomic limit reservation
4. Broker-only mock-bank execution
5. One-use permit
6. Emergency halt and revocation
7. Complete execution receipt
8. Automated adversarial tests

### Strong differentiators

1. Hierarchical rolling exposure limits
2. Policy shadow replay
3. Measured concurrent-budget correctness
4. Measured halt propagation

### Only after the core is excellent

- Additional financial actions
- Real LLM-driven agent
- Learned anomaly detection
- Redis, Kafka, Kubernetes or cloud deployment

## Proposed calendar

- **Jul 27–29:** product contract, threat model, architecture and scaffold
- **Jul 30–Aug 5:** identity, policy, database, budgets, permits and mock bank
- **Aug 6–10:** approvals, emergency controls, receipts and shadow replay
- **Aug 11–14:** dashboard and deterministic demo
- **Aug 15–18:** adversarial tests, concurrency testing and measurements
- **Aug 19–22:** project description, deck, video and rehearsal
- **Aug 23:** target first complete submission
- **Aug 24–25:** buffer for verified fixes only

## Working rule for the build

We will implement one step at a time and run its acceptance check before moving forward. A polished screen will never be used to hide an unverified safety claim.
