"""Agent identity verification.

Per docs/THREAT_MODEL.md, all agent input including its claimed identity is
untrusted until a signed, short-lived Ed25519 token is verified against the
public key on file for that key ID. Any failure here is an authentication
failure (401), not a policy decision -- the agent's status (ACTIVE/REVOKED)
is still forwarded to OPA as an authenticated fact so revocation is enforced
as an auditable policy decision rather than a silent auth rejection.
"""

import base64
import uuid
from datetime import datetime, timezone

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

import hmac

from .config import MAX_AGENT_TOKEN_TTL_SECONDS, OPERATOR_TOKEN
from .models import Agent, AgentCredential


def _unauthorized(message: str) -> HTTPException:
    return HTTPException(
        status_code=401,
        detail={
            "error": {
                "code": "AGENT_IDENTITY_INVALID",
                "message": message,
                "correlation_id": str(uuid.uuid4()),
            }
        },
    )


def extract_bearer_token(authorization_header: str | None) -> str:
    if not authorization_header or not authorization_header.startswith("Bearer "):
        raise _unauthorized("Missing or malformed Authorization header.")
    token = authorization_header[len("Bearer "):].strip()
    if not token:
        raise _unauthorized("Missing bearer token.")
    return token


def verify_agent_token(token: str, session: Session) -> Agent:
    try:
        header = jwt.get_unverified_header(token)
    except jwt.InvalidTokenError:
        raise _unauthorized("Token could not be parsed.")

    key_id = header.get("kid")
    if not key_id:
        raise _unauthorized("Token is missing a key ID.")

    row = session.execute(
        select(AgentCredential, Agent)
        .join(Agent, Agent.id == AgentCredential.agent_id)
        .where(AgentCredential.key_id == key_id)
    ).first()
    if row is None:
        raise _unauthorized("Unknown signing key.")
    credential, agent = row

    now = datetime.now(timezone.utc)
    if credential.valid_from > now:
        raise _unauthorized("Signing key is not yet valid.")
    if credential.valid_until is not None and credential.valid_until < now:
        raise _unauthorized("Signing key has expired.")

    try:
        public_key = Ed25519PublicKey.from_public_bytes(base64.b64decode(credential.public_key_b64))
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    except (ValueError, TypeError):
        raise _unauthorized("Signing key on file is invalid.")

    try:
        payload = jwt.decode(
            token,
            key=public_pem,
            algorithms=["EdDSA"],
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.InvalidTokenError:
        raise _unauthorized("Token signature or claims are invalid.")

    if payload.get("sub") != agent.token_subject:
        raise _unauthorized("Token subject does not match the signing key's owner.")

    issued_at = payload["iat"]
    expires_at = payload["exp"]
    if expires_at - issued_at > MAX_AGENT_TOKEN_TTL_SECONDS:
        raise _unauthorized("Token lifetime exceeds the maximum allowed for agent identity.")

    return agent


def require_operator(operator_token: str | None) -> str:
    """Dev-only operator authentication: a shared bearer secret, mirroring the
    broker/bank service-token pattern. Real operator login (email/password,
    per docs/DATA_MODEL.md `operator_users`) is part of the Milestone 6
    dashboard; this is a stand-in so governance endpoints are still gated."""
    if not OPERATOR_TOKEN or not operator_token or not hmac.compare_digest(operator_token, OPERATOR_TOKEN):
        raise HTTPException(
            status_code=401,
            detail={
                "error": {
                    "code": "OPERATOR_TOKEN_INVALID",
                    "message": "Missing or invalid operator token.",
                    "correlation_id": str(uuid.uuid4()),
                }
            },
        )
    return "operator"
