-- Reset local dev/test state to a fresh-seed baseline so the acceptance test
-- suites (tests/test_refund_intake.py, tests/test_budget_execution.py,
-- tests/test_governance_workflows.py) can be re-run repeatedly against the
-- same running stack. Milestone 4 execution actually mutates bank balances
-- and consumes budget, unlike the Milestone 3 no-op path, and Milestone 5
-- control actions mutate agent/governance state, so re-running tests without
-- this reset would see shrinking balances, accumulating budget usage, and
-- agents/fleet left revoked or halted by an interrupted test run.
-- Dev/test convenience only -- never run against a real environment.

TRUNCATE
    bank.bank_operation_events,
    bank.refunds,
    bank.permit_uses,
    broker.execution_receipts,
    broker.action_permits,
    broker.reservation_allocations,
    broker.budget_reservations,
    broker.budget_locks,
    broker.policy_evaluations,
    broker.audit_events,
    broker.action_requests,
    broker.control_actions,
    broker.audit_checkpoints,
    broker.audit_checkpoint_items
    CASCADE;

UPDATE broker.audit_stream_heads SET last_sequence = 0, last_event_hash = NULL;

UPDATE bank.payments SET refundable_remaining_minor = original_amount_minor;

-- Restore each agent's originally-seeded status (database/migrations/versions/0002_...)
-- rather than blanket-activating everyone: revoked-demo-agent-v1 is seeded
-- REVOKED on purpose for Milestone 3's revoked-agent acceptance test.
UPDATE broker.agents SET status = 'ACTIVE', status_reason = NULL, epoch = 0
WHERE token_subject != 'revoked-demo-agent-v1';
UPDATE broker.agents SET status = 'REVOKED', status_reason = 'Seeded as revoked for Milestone 3 acceptance testing', epoch = 0
WHERE token_subject = 'revoked-demo-agent-v1';

UPDATE broker.governance_state SET run_state = 'RUNNING', risk_mode = 'NORMAL', epoch = 0, last_actor = NULL, last_reason = NULL;
