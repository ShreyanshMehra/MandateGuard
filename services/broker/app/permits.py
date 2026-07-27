"""Ed25519 Action Permit signing and bank-result verification.

A permit is a short-lived, single-use, parameter-bound authorization for the
mock bank to apply exactly one refund (docs/DATA_MODEL.md "Permits and
outcomes"). The broker never lets the mock bank trust an unsigned claim, and
never trusts an unsigned bank result either -- both directions are verified
Ed25519 signatures using dev keys under secrets/dev/ (gitignored).
"""

import base64
import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from . import config
from .models import ActionPermit

_PRIVATE_KEY = (
    serialization.load_pem_private_key(Path(config.BROKER_PERMIT_KEY_PATH).read_bytes(), password=None)
    if config.BROKER_PERMIT_KEY_PATH
    else None
)

_BANK_RESULT_PUBLIC_KEY = (
    Ed25519PublicKey.from_public_bytes(base64.b64decode(config.BANK_RESULT_PUBLIC_KEY_B64))
    if config.BANK_RESULT_PUBLIC_KEY_B64
    else None
)


def issue_permit(
    *,
    action_id: uuid.UUID,
    reservation_id: uuid.UUID,
    payment_id: str,
    amount_minor: int,
    currency: str,
    attempt_number: int,
    policy_version_id,
    control_epoch_snapshot: int | None,
    agent_epoch_snapshot: int | None,
) -> tuple[ActionPermit, str]:
    jti = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=config.PERMIT_TTL_SECONDS)

    claims = {
        "jti": jti,
        "action_id": str(action_id),
        "payment_id": payment_id,
        "amount_minor": amount_minor,
        "currency": currency,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    payload_hash = hashlib.sha256(
        json.dumps(claims, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    token = jwt.encode(claims, key=_PRIVATE_KEY, algorithm="EdDSA", headers={"kid": config.BROKER_PERMIT_KEY_ID})

    permit = ActionPermit(
        id=uuid.uuid4(),
        jti=jti,
        action_id=action_id,
        reservation_id=reservation_id,
        attempt_number=attempt_number,
        status="ISSUED",
        payload_hash=payload_hash,
        policy_version_id=policy_version_id,
        control_epoch_snapshot=control_epoch_snapshot,
        agent_epoch_snapshot=agent_epoch_snapshot,
        expires_at=expires_at,
    )
    return permit, token


def verify_bank_result(document: dict, signature_b64: str) -> bool:
    if _BANK_RESULT_PUBLIC_KEY is None:
        return False
    canonical = json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
    try:
        _BANK_RESULT_PUBLIC_KEY.verify(base64.b64decode(signature_b64), canonical)
        return True
    except (InvalidSignature, ValueError):
        return False
