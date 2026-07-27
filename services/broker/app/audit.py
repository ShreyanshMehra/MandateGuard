"""Append-only, hash-chained audit events (docs/ARCHITECTURE.md "Audit
design"). Each event links to the previous event's hash within its stream so
edits are detectable relative to a trusted checkpoint. Checkpoint signing and
verification tooling are added in Milestone 5; this module only maintains the
chain invariant on every insert.
"""

import hashlib
import json
import uuid

from sqlalchemy import text
from sqlalchemy.orm import Session


def append_audit_event(
    session: Session,
    *,
    stream_id: str,
    event_type: str,
    actor: str,
    payload: dict,
    correlation_id: uuid.UUID | None = None,
    policy_version_id: uuid.UUID | None = None,
    control_epoch_snapshot: int | None = None,
) -> uuid.UUID:
    session.execute(
        text(
            "INSERT INTO broker.audit_stream_heads (stream_id) VALUES (:stream_id) "
            "ON CONFLICT (stream_id) DO NOTHING"
        ),
        {"stream_id": stream_id},
    )
    head = session.execute(
        text(
            "SELECT last_sequence, last_event_hash FROM broker.audit_stream_heads "
            "WHERE stream_id = :stream_id FOR UPDATE"
        ),
        {"stream_id": stream_id},
    ).one()

    next_sequence = head.last_sequence + 1
    canonical_payload = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    digest_input = "|".join(
        [stream_id, str(next_sequence), head.last_event_hash or "", event_type, actor, canonical_payload]
    )
    event_hash = hashlib.sha256(digest_input.encode("utf-8")).hexdigest()
    event_id = uuid.uuid4()

    session.execute(
        text(
            """
            INSERT INTO broker.audit_events
                (id, stream_id, sequence, previous_hash, event_hash, event_type, actor,
                 correlation_id, payload, policy_version_id, control_epoch_snapshot)
            VALUES
                (:id, :stream_id, :sequence, :previous_hash, :event_hash, :event_type, :actor,
                 :correlation_id, CAST(:payload AS JSONB), :policy_version_id, :control_epoch_snapshot)
            """
        ),
        {
            "id": event_id,
            "stream_id": stream_id,
            "sequence": next_sequence,
            "previous_hash": head.last_event_hash,
            "event_hash": event_hash,
            "event_type": event_type,
            "actor": actor,
            "correlation_id": correlation_id,
            "payload": canonical_payload,
            "policy_version_id": policy_version_id,
            "control_epoch_snapshot": control_epoch_snapshot,
        },
    )
    session.execute(
        text(
            "UPDATE broker.audit_stream_heads SET last_sequence = :sequence, last_event_hash = :event_hash "
            "WHERE stream_id = :stream_id"
        ),
        {"sequence": next_sequence, "event_hash": event_hash, "stream_id": stream_id},
    )
    return event_id
