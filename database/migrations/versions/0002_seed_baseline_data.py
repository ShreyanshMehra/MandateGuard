"""Seed baseline governance state, active policy version, demo agents and
demo bank payments used by the Milestone 3 acceptance scenarios.

Idempotent: safe to run more than once (uses ON CONFLICT DO NOTHING /
DO UPDATE) even though the prototype only runs migrations once per
environment.

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-27
"""

import hashlib
import json
from pathlib import Path

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

POLICY_CONFIG_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent / "policies" / "policy_config.json"
)

# Public keys for the two Milestone 3 demo agents. Generated once via
# scripts/generate_agent_keys.py; the matching private keys live under
# secrets/dev/ (gitignored, local development only per HANDOFF.md section 14).
DEMO_AGENTS = [
    {
        "token_subject": "refund-agent-v1",
        "display_name": "Refund Agent v1 (demo)",
        "status": "ACTIVE",
        "key_id": "refund-agent-v1:dev-2026-07",
        "public_key_b64": "CK/DQnEP/7ZSnEutd+LJbIGjsQsDjckX9b6kepRbnbc=",
    },
    {
        "token_subject": "revoked-demo-agent-v1",
        "display_name": "Revoked Demo Agent (Milestone 3 fixture)",
        "status": "REVOKED",
        "key_id": "revoked-demo-agent-v1:dev-2026-07",
        "public_key_b64": "j3hjRyDZqo131soGcQl8Xm8Y7AOcz5yAhMvrDtCaxUE=",
    },
]

DEMO_PAYMENTS = [
    {
        "payment_id": "payment-demo-001",
        "customer_id": "customer-demo-001",
        "currency": "USD",
        "original_amount_minor": 50000,
        "refundable_remaining_minor": 50000,
    },
    {
        "payment_id": "payment-demo-002",
        "customer_id": "customer-demo-002",
        "currency": "USD",
        "original_amount_minor": 200000,
        "refundable_remaining_minor": 200000,
    },
    {
        "payment_id": "payment-demo-003",
        "customer_id": "customer-demo-999",
        "currency": "USD",
        "original_amount_minor": 10000,
        "refundable_remaining_minor": 10000,
    },
]


def upgrade() -> None:
    connection = op.get_bind()

    config_text = POLICY_CONFIG_PATH.read_text(encoding="utf-8")
    config_doc = json.loads(config_text)
    checksum = hashlib.sha256(config_text.encode("utf-8")).hexdigest()
    policy_version_number = 1

    policy_version_id = connection.execute(
        sa.text(
            """
            INSERT INTO broker.policy_versions
                (version_number, base_version_number, checksum, status, config, created_by, approved_by, approved_at)
            VALUES
                (:version_number, NULL, :checksum, 'ACTIVE', CAST(:config AS JSONB), 'seed-migration', 'seed-migration', now())
            ON CONFLICT (version_number) DO UPDATE SET checksum = EXCLUDED.checksum
            RETURNING id
            """
        ),
        {
            "version_number": policy_version_number,
            "checksum": checksum,
            "config": json.dumps(config_doc),
        },
    ).scalar_one()

    connection.execute(
        sa.text(
            """
            INSERT INTO broker.governance_state (id, run_state, risk_mode, active_policy_version_id, epoch, last_actor, last_reason)
            VALUES (true, 'RUNNING', 'NORMAL', :policy_version_id, 0, 'seed-migration', 'Initial Milestone 3 baseline')
            ON CONFLICT (id) DO UPDATE SET active_policy_version_id = EXCLUDED.active_policy_version_id
            """
        ),
        {"policy_version_id": policy_version_id},
    )

    for agent in DEMO_AGENTS:
        agent_id = connection.execute(
            sa.text(
                """
                INSERT INTO broker.agents (token_subject, display_name, agent_type, status, status_reason)
                VALUES (:token_subject, :display_name, 'refund_agent', CAST(:status AS broker.agent_status),
                        CASE WHEN :status = 'REVOKED' THEN 'Seeded as revoked for Milestone 3 acceptance testing' ELSE NULL END)
                ON CONFLICT (token_subject) DO UPDATE SET status = EXCLUDED.status
                RETURNING id
                """
            ),
            {
                "token_subject": agent["token_subject"],
                "display_name": agent["display_name"],
                "status": agent["status"],
            },
        ).scalar_one()

        connection.execute(
            sa.text(
                """
                INSERT INTO broker.agent_credentials (agent_id, key_id, public_key_b64, algorithm)
                VALUES (:agent_id, :key_id, :public_key_b64, 'EdDSA')
                ON CONFLICT (key_id) DO UPDATE SET public_key_b64 = EXCLUDED.public_key_b64
                """
            ),
            {
                "agent_id": agent_id,
                "key_id": agent["key_id"],
                "public_key_b64": agent["public_key_b64"],
            },
        )

    for payment in DEMO_PAYMENTS:
        connection.execute(
            sa.text(
                """
                INSERT INTO bank.payments
                    (payment_id, customer_id, currency, original_amount_minor, refundable_remaining_minor)
                VALUES
                    (:payment_id, :customer_id, :currency, :original_amount_minor, :refundable_remaining_minor)
                ON CONFLICT (payment_id) DO UPDATE SET
                    refundable_remaining_minor = EXCLUDED.refundable_remaining_minor
                """
            ),
            payment,
        )


def downgrade() -> None:
    connection = op.get_bind()
    for payment in DEMO_PAYMENTS:
        connection.execute(
            sa.text("DELETE FROM bank.payments WHERE payment_id = :payment_id"),
            {"payment_id": payment["payment_id"]},
        )
    for agent in DEMO_AGENTS:
        connection.execute(
            sa.text("DELETE FROM broker.agents WHERE token_subject = :token_subject"),
            {"token_subject": agent["token_subject"]},
        )
    connection.execute(sa.text("UPDATE broker.governance_state SET active_policy_version_id = NULL"))
    connection.execute(sa.text("DELETE FROM broker.policy_versions WHERE version_number = 1"))
