"""Mint a short-lived Ed25519-signed agent token for local testing.

In production an agent mints its own token from a key it holds; this script
stands in for that during development, signing with a private key generated
by scripts/generate_agent_keys.py (see secrets/dev/, gitignored).

Usage:
    python scripts/mint_agent_token.py <agent_id> <key_id> [ttl_seconds]
"""

import sys
import time
import uuid
from pathlib import Path

import jwt

SECRETS_DIR = Path(__file__).resolve().parent.parent / "secrets" / "dev"


def main() -> None:
    if len(sys.argv) not in (3, 4):
        print(__doc__)
        raise SystemExit(2)

    agent_id, key_id = sys.argv[1], sys.argv[2]
    ttl_seconds = int(sys.argv[3]) if len(sys.argv) == 4 else 120

    safe_key_id = key_id.replace(":", "_").replace("/", "_")
    key_path = SECRETS_DIR / f"{agent_id}__{safe_key_id}.pem"
    private_key_pem = key_path.read_bytes()

    now = int(time.time())
    token = jwt.encode(
        {"sub": agent_id, "iat": now, "exp": now + ttl_seconds, "jti": str(uuid.uuid4())},
        key=private_key_pem,
        algorithm="EdDSA",
        headers={"kid": key_id},
    )
    print(token)


if __name__ == "__main__":
    main()
