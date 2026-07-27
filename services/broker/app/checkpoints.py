"""Signed audit checkpoints (Milestone 5).

A checkpoint is a signed manifest over every audit stream's current
(last_sequence, last_event_hash). Verifying a checkpoint replays each
covered stream's event chain from the start and confirms both that every
stored event_hash still matches its recomputed digest and that the chain
still ends at the hash the checkpoint captured -- so any edit or deletion of
a historical audit_events row is detectable relative to the checkpoint, even
though ordinary appends after the checkpoint are expected and not tampering.
"""

import base64
import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from sqlalchemy import text
from sqlalchemy.orm import Session

from . import config
from .models import AuditCheckpoint, AuditCheckpointItem

_PRIVATE_KEY = (
    serialization.load_pem_private_key(Path(config.AUDIT_CHECKPOINT_KEY_PATH).read_bytes(), password=None)
    if config.AUDIT_CHECKPOINT_KEY_PATH
    else None
)


def _canonical(document: dict) -> bytes:
    return json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")


def create_checkpoint(session: Session) -> AuditCheckpoint:
    rows = session.execute(
        text("SELECT stream_id, last_sequence, last_event_hash FROM broker.audit_stream_heads ORDER BY stream_id")
    ).all()
    manifest = {
        "streams": [
            {"stream_id": r.stream_id, "last_sequence": r.last_sequence, "last_event_hash": r.last_event_hash}
            for r in rows
        ]
    }
    manifest_hash = hashlib.sha256(_canonical(manifest)).hexdigest()
    signature_b64 = base64.b64encode(_PRIVATE_KEY.sign(_canonical(manifest))).decode("ascii")

    checkpoint = AuditCheckpoint(
        id=uuid.uuid4(),
        manifest=manifest,
        manifest_hash=manifest_hash,
        signature_b64=signature_b64,
        key_id=config.AUDIT_CHECKPOINT_KEY_ID,
        created_at=datetime.now(timezone.utc),
    )
    session.add(checkpoint)
    session.flush()

    for stream in manifest["streams"]:
        session.add(
            AuditCheckpointItem(
                id=uuid.uuid4(),
                checkpoint_id=checkpoint.id,
                stream_id=stream["stream_id"],
                last_sequence=stream["last_sequence"],
                last_event_hash=stream["last_event_hash"],
            )
        )
    return checkpoint


def verify_checkpoint(session: Session, checkpoint: AuditCheckpoint) -> dict:
    signature_valid = False
    if _PRIVATE_KEY is not None:
        public_key: Ed25519PublicKey = _PRIVATE_KEY.public_key()
        try:
            public_key.verify(base64.b64decode(checkpoint.signature_b64), _canonical(checkpoint.manifest))
            signature_valid = True
        except (InvalidSignature, ValueError):
            signature_valid = False

    manifest_hash_valid = hashlib.sha256(_canonical(checkpoint.manifest)).hexdigest() == checkpoint.manifest_hash

    stream_results = []
    all_chains_intact = True
    for stream in checkpoint.manifest["streams"]:
        stream_id = stream["stream_id"]
        events = session.execute(
            text(
                """
                SELECT sequence, previous_hash, event_hash, event_type, actor, payload
                FROM broker.audit_events
                WHERE stream_id = :stream_id AND sequence <= :last_sequence
                ORDER BY sequence
                """
            ),
            {"stream_id": stream_id, "last_sequence": stream["last_sequence"]},
        ).all()

        previous_hash = None
        chain_intact = True
        for event in events:
            canonical_payload = json.dumps(event.payload, sort_keys=True, separators=(",", ":"), default=str)
            digest_input = "|".join(
                [stream_id, str(event.sequence), previous_hash or "", event.event_type, event.actor, canonical_payload]
            )
            recomputed = hashlib.sha256(digest_input.encode("utf-8")).hexdigest()
            if event.previous_hash != previous_hash or recomputed != event.event_hash:
                chain_intact = False
                break
            previous_hash = event.event_hash

        chain_intact = chain_intact and previous_hash == stream["last_event_hash"]
        all_chains_intact = all_chains_intact and chain_intact
        stream_results.append({"stream_id": stream_id, "chain_intact": chain_intact})

    return {
        "checkpoint_id": str(checkpoint.id),
        "signature_valid": signature_valid,
        "manifest_hash_valid": manifest_hash_valid,
        "tampered": not (signature_valid and manifest_hash_valid and all_chains_intact),
        "streams": stream_results,
    }
