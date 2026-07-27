-- Reset local dev/test state to a fresh-seed baseline so the acceptance
-- test suites (tests/test_refund_intake.py, tests/test_budget_execution.py)
-- can be re-run repeatedly against the same running stack. Milestone 4
-- execution actually mutates bank balances and consumes budget, unlike the
-- Milestone 3 no-op path, so re-running tests without this reset would see
-- shrinking refundable balances and accumulating budget usage across runs.
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
    broker.action_requests
    CASCADE;

UPDATE broker.audit_stream_heads SET last_sequence = 0, last_event_hash = NULL;

UPDATE bank.payments SET refundable_remaining_minor = original_amount_minor;
