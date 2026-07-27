"""Milestone 5 schema: governance workflows.

Adds control-action, approval, audit-checkpoint and policy-replay tables
from docs/DATA_MODEL.md needed for held-action approval/denial, agent
revoke/restore and fleet halt/resume/risk with epoch increments, signed
audit checkpoints, and read-only candidate-policy shadow replay.

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-27
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE TYPE broker.control_action_type AS ENUM "
        "('REVOKE_AGENT', 'RESTORE_AGENT', 'HALT', 'RESUME', 'SET_RISK_MODE')"
    )
    op.execute("CREATE TYPE broker.approval_decision AS ENUM ('APPROVED', 'DENIED')")
    op.execute("CREATE TYPE broker.replay_run_status AS ENUM ('COMPLETED', 'FAILED')")

    control_action_type = pg.ENUM(name="control_action_type", schema="broker", create_type=False)
    approval_decision = pg.ENUM(name="approval_decision", schema="broker", create_type=False)
    replay_run_status = pg.ENUM(name="replay_run_status", schema="broker", create_type=False)

    op.create_table(
        "control_actions",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("action_type", control_action_type, nullable=False),
        sa.Column("target", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.Text(), nullable=False, unique=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("before_snapshot", pg.JSONB(), nullable=False),
        sa.Column("after_snapshot", pg.JSONB(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        schema="broker",
    )

    op.create_table(
        "approvals",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "action_id", pg.UUID(as_uuid=True),
            sa.ForeignKey("broker.action_requests.id"), nullable=False, unique=True,
        ),
        sa.Column("approver", sa.Text(), nullable=False),
        sa.Column("decision", approval_decision, nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.Text(), nullable=False, unique=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        schema="broker",
    )

    op.create_table(
        "audit_checkpoints",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("manifest", pg.JSONB(), nullable=False),
        sa.Column("manifest_hash", sa.Text(), nullable=False),
        sa.Column("signature_b64", sa.Text(), nullable=False),
        sa.Column("key_id", sa.Text(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        schema="broker",
    )

    op.create_table(
        "audit_checkpoint_items",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "checkpoint_id", pg.UUID(as_uuid=True),
            sa.ForeignKey("broker.audit_checkpoints.id"), nullable=False,
        ),
        sa.Column("stream_id", sa.Text(), nullable=False),
        sa.Column("last_sequence", sa.BigInteger(), nullable=False),
        sa.Column("last_event_hash", sa.Text(), nullable=True),
        schema="broker",
    )

    op.create_table(
        "policy_replay_runs",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("candidate_config", pg.JSONB(), nullable=False),
        sa.Column(
            "baseline_policy_version_id", pg.UUID(as_uuid=True),
            sa.ForeignKey("broker.policy_versions.id"), nullable=True,
        ),
        sa.Column("from_time", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("to_time", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("status", replay_run_status, nullable=False),
        sa.Column("summary", pg.JSONB(), nullable=False),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        schema="broker",
    )

    op.create_table(
        "policy_replay_results",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "run_id", pg.UUID(as_uuid=True),
            sa.ForeignKey("broker.policy_replay_runs.id"), nullable=False,
        ),
        sa.Column(
            "action_id", pg.UUID(as_uuid=True),
            sa.ForeignKey("broker.action_requests.id"), nullable=False,
        ),
        sa.Column("baseline_decision", sa.Text(), nullable=False),
        sa.Column("candidate_decision", sa.Text(), nullable=False),
        sa.Column("baseline_reason_code", sa.Text(), nullable=True),
        sa.Column("candidate_reason_code", sa.Text(), nullable=True),
        sa.Column("changed", sa.Boolean(), nullable=False),
        schema="broker",
    )

    op.execute("GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA broker TO mandateguard_broker")


def downgrade() -> None:
    op.drop_table("policy_replay_results", schema="broker")
    op.drop_table("policy_replay_runs", schema="broker")
    op.drop_table("audit_checkpoint_items", schema="broker")
    op.drop_table("audit_checkpoints", schema="broker")
    op.drop_table("approvals", schema="broker")
    op.drop_table("control_actions", schema="broker")
    op.execute("DROP TYPE broker.replay_run_status")
    op.execute("DROP TYPE broker.approval_decision")
    op.execute("DROP TYPE broker.control_action_type")
