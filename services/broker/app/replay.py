"""Candidate policy shadow replay (Milestone 5).

Re-evaluates historical decisions against a candidate configuration by
replaying each action's exact original OPA input (stored verbatim in
`policy_evaluations.input_snapshot`) with `override_config` set to the
candidate, using the real Rego rules -- not a reimplementation -- so the
comparison is exact. This is strictly read-only: it only ever calls OPA and
writes to the dedicated `policy_replay_runs`/`policy_replay_results` tables;
it never creates reservations, permits, refunds or live audit events, and
never touches `action_requests` (docs/DATA_MODEL.md "Shadow replay").
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from .clients import OpaUnavailableError, evaluate_refund_policy
from .models import PolicyReplayResult, PolicyReplayRun

REPLAY_LIMIT = 500


def run_replay(
    session: Session,
    *,
    candidate_config: dict,
    from_time: datetime | None,
    to_time: datetime | None,
    actor: str,
) -> PolicyReplayRun:
    rows = session.execute(
        text(
            """
            SELECT pe.action_id, pe.input_snapshot, pe.decision AS baseline_decision, pe.reason_code AS baseline_reason_code
            FROM broker.policy_evaluations pe
            JOIN broker.action_requests ar ON ar.id = pe.action_id
            WHERE pe.phase = 'INITIAL'
              AND (CAST(:from_time AS timestamptz) IS NULL OR ar.created_at >= CAST(:from_time AS timestamptz))
              AND (CAST(:to_time AS timestamptz) IS NULL OR ar.created_at <= CAST(:to_time AS timestamptz))
            ORDER BY ar.created_at
            LIMIT :limit
            """
        ),
        {"from_time": from_time, "to_time": to_time, "limit": REPLAY_LIMIT},
    ).all()

    run_id = uuid.uuid4()
    results: list[PolicyReplayResult] = []
    changed_count = 0
    status = "COMPLETED"
    summary: dict = {}

    try:
        for row in rows:
            candidate_input = dict(row.input_snapshot)
            candidate_input["override_config"] = candidate_config
            result = evaluate_refund_policy(candidate_input)
            candidate_decision = result["outcome"]
            candidate_reason_code = result["reason_code"]
            changed = candidate_decision != row.baseline_decision or candidate_reason_code != row.baseline_reason_code
            if changed:
                changed_count += 1
            results.append(
                PolicyReplayResult(
                    id=uuid.uuid4(),
                    run_id=run_id,
                    action_id=row.action_id,
                    baseline_decision=row.baseline_decision,
                    candidate_decision=candidate_decision,
                    baseline_reason_code=row.baseline_reason_code,
                    candidate_reason_code=candidate_reason_code,
                    changed=changed,
                )
            )
        summary = {"evaluated": len(results), "changed": changed_count, "unchanged": len(results) - changed_count}
    except OpaUnavailableError as exc:
        status = "FAILED"
        summary = {"error": str(exc), "evaluated": len(results)}
        results = []

    run = PolicyReplayRun(
        id=run_id,
        candidate_config=candidate_config,
        baseline_policy_version_id=None,
        from_time=from_time,
        to_time=to_time,
        status=status,
        summary=summary,
        created_by=actor,
        created_at=datetime.now(timezone.utc),
    )
    session.add(run)
    session.flush()  # ensure the parent run row exists before its FK-dependent results
    for result in results:
        session.add(result)
    return run
