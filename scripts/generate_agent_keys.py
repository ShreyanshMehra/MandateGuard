"""Generate a development Ed25519 keypair for a MandateGuard agent identity.

The private key is a local development secret only (see HANDOFF.md section 14
-- prototype keys, not hardware-backed identity). It is written under
secrets/dev/, which is gitignored, and must never be committed. The public
key is printed so it can be pasted into the baseline seed migration.

Usage:
    python scripts/generate_agent_keys.py <agent_id> <key_id>
"""

import base64
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

SECRETS_DIR = Path(__file__).resolve().parent.parent / "secrets" / "dev"


def main() -> None:
    if len(sys.argv) != 3:
        print(__doc__)
        raise SystemExit(2)

    agent_id, key_id = sys.argv[1], sys.argv[2]
    SECRETS_DIR.mkdir(parents=True, exist_ok=True)

    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_raw = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )

    safe_key_id = key_id.replace(":", "_").replace("/", "_")
    key_path = SECRETS_DIR / f"{agent_id}__{safe_key_id}.pem"
    key_path.write_bytes(private_pem)

    print(f"Private key written to {key_path}")
    print(f"agent_id: {agent_id}")
    print(f"key_id:   {key_id}")
    print(f"public_key_b64: {base64.b64encode(public_raw).decode('ascii')}")


if __name__ == "__main__":
    main()
