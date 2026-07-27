"""Milestone 3 initial schema: identity, governance, policy, action intake and audit.

Scope is intentionally limited to what Milestone 3 (identity, policy and
action intake) needs, per HANDOFF.md section 11. Budget, permit, receipt,
approval, control-action, checkpoint and shadow-replay tables from
docs/DATA_MODEL.md are added in the migrations that implement them
(Milestone 4 and later) rather than created unused here.

Revision ID: 0001
Revises:
Create Date: 2026-07-27
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.execute("CREATE TYPE broker.agent_status AS ENUM ('ACTIVE', 'REVOKED')")
    op.execute("CREATE TYPE broker.governance_run_state AS ENUM ('RUNNING', 'HALTED')")
    op.execute("CREATE TYPE broker.risk_mode AS ENUM ('NORMAL', 'ELEVATED')")
    op.execute(
        "CREATE TYPE broker.policy_version_status AS ENUM "
        "('DRAFT', 'CANDIDATE', 'APPROVED', 'ACTIVE', 'RETIRED')"
    )
    op.execute(
        "CREATE TYPE broker.action_state AS ENUM ("
        "'RECEIVED', 'DENIED', 'HELD', 'BUDGET_RESERVED', 'PERMIT_ISSUED', "
        "'EXECUTING', 'SUCCEEDED', 'FAILED', 'UNKNOWN', "
        "'RECONCILED_SUCCEEDED', 'RECONCILED_FAILED')"
    )
    op.execute("CREATE TYPE broker.policy_decision AS ENUM ('ALLOW', 'DENY', 'HOLD')")
    op.execute(
        "CREATE TYPE broker.evaluation_phase AS ENUM ('INITIAL', 'APPROVAL_RECHECK')"
    )

    agent_status = pg.ENUM(name="agent_status", schema="broker", create_type=False)
    governance_run_state = pg.ENUM(
        name="governance_run_state", schema="broker", create_type=False
    )
    risk_mode = pg.ENUM(name="risk_mode", schema="broker", create_type=False)
    policy_version_status = pg.ENUM(
        name="policy_version_status", schema="broker", create_type=False
    )
    action_state = pg.ENUM(name="action_state", schema="broker", create_type=False)
    policy_decision = pg.ENUM(name="policy_decision", schema="broker", create_type=False)
    evaluation_phase = pg.ENUM(
        name="evaluation_phase", schema="broker", create_type=False
    )

    op.create_table(
        "agents",
        sa.Column(
            "id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("token_subject", sa.Text(), nullable=False, unique=True),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("agent_type", sa.Text(), nullable=False, server_default="refund_agent"),
        sa.Column("deployment_version", sa.Text(), nullable=True),
        sa.Column("status", agent_status, nullable=False, server_default="ACTIVE"),
        sa.Column("status_reason", sa.Text(), nullable=True),
        sa.Column("epoch", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        schema="broker",
    )

    op.create_table(
        "agent_credentials",
        sa.Column(
            "id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column(
            "agent_id", pg.UUID(as_uuid=True),
            sa.ForeignKey("broker.agents.id"), nullable=False,
        ),
        sa.Column("key_id", sa.Text(), nullable=False, unique=True),
        sa.Column("public_key_b64", sa.Text(), nullable=False),
        sa.Column("algorithm", sa.Text(), nullable=False, server_default="EdDSA"),
        sa.Column("valid_from", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("valid_until", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        schema="broker",
    )

    op.create_table(
        "policy_versions",
        sa.Column(
            "id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("version_number", sa.Integer(), nullable=False, unique=True),
        sa.Column("base_version_number", sa.Integer(), nullable=True),
        sa.Column("checksum", sa.Text(), nullable=False),
        sa.Column("status", policy_version_status, nullable=False, server_default="DRAFT"),
        sa.Column("config", pg.JSONB(), nullable=False),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.Column("approved_by", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("approved_at", sa.TIMESTAMP(timezone=True), nullable=True),
        schema="broker",
    )

    op.create_table(
        "governance_state",
        sa.Column("id", sa.Boolean(), primary_key=True, server_default=sa.text("true")),
        sa.Column("run_state", governance_run_state, nullable=False, server_default="RUNNING"),
        sa.Column("risk_mode", risk_mode, nullable=False, server_default="NORMAL"),
        sa.Column(
            "active_policy_version_id", pg.UUID(as_uuid=True),
            sa.ForeignKey("broker.policy_versions.id"), nullable=True,
        ),
        sa.Column("epoch", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("last_actor", sa.Text(), nullable=True),
        sa.Column("last_reason", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("id", name="governance_state_singleton"),
        schema="broker",
    )

    op.create_table(
        "action_requests",
        sa.Column(
            "id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column(
            "agent_id", pg.UUID(as_uuid=True),
            sa.ForeignKey("broker.agents.id"), nullable=False,
        ),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("canonical_request_hash", sa.Text(), nullable=False),
        sa.Column("payment_id", sa.Text(), nullable=False),
        sa.Column("customer_id", sa.Text(), nullable=True),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.Text(), nullable=False),
        sa.Column("reason_code", sa.Text(), nullable=True),
        sa.Column("state", action_state, nullable=False, server_default="RECEIVED"),
        sa.Column("decision", policy_decision, nullable=True),
        sa.Column("public_reason_code", sa.Text(), nullable=True),
        sa.Column("operator_explanation", sa.Text(), nullable=True),
        sa.Column(
            "policy_version_id", pg.UUID(as_uuid=True),
            sa.ForeignKey("broker.policy_versions.id"), nullable=True,
        ),
        sa.Column("risk_mode_snapshot", risk_mode, nullable=True),
        sa.Column("control_epoch_snapshot", sa.BigInteger(), nullable=True),
        sa.Column("agent_epoch_snapshot", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("agent_id", "idempotency_key"),
        schema="broker",
    )

    op.create_table(
        "policy_evaluations",
        sa.Column(
            "id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column(
            "action_id", pg.UUID(as_uuid=True),
            sa.ForeignKey("broker.action_requests.id"), nullable=False,
        ),
        sa.Column("phase", evaluation_phase, nullable=False, server_default="INITIAL"),
        sa.Column("input_snapshot", pg.JSONB(), nullable=False),
        sa.Column("output_snapshot", pg.JSONB(), nullable=False),
        sa.Column("decision", policy_decision, nullable=False),
        sa.Column("reason_code", sa.Text(), nullable=True),
        sa.Column(
            "policy_version_id", pg.UUID(as_uuid=True),
            sa.ForeignKey("broker.policy_versions.id"), nullable=True,
        ),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        schema="broker",
    )

    op.create_table(
        "audit_stream_heads",
        sa.Column("stream_id", sa.Text(), primary_key=True),
        sa.Column("last_sequence", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("last_event_hash", sa.Text(), nullable=True),
        schema="broker",
    )

    op.create_table(
        "audit_events",
        sa.Column(
            "id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column(
            "stream_id", sa.Text(),
            sa.ForeignKey("broker.audit_stream_heads.stream_id"), nullable=False,
        ),
        sa.Column("sequence", sa.BigInteger(), nullable=False),
        sa.Column("previous_hash", sa.Text(), nullable=True),
        sa.Column("event_hash", sa.Text(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("correlation_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("payload", pg.JSONB(), nullable=False),
        sa.Column(
            "policy_version_id", pg.UUID(as_uuid=True),
            sa.ForeignKey("broker.policy_versions.id"), nullable=True,
        ),
        sa.Column("control_epoch_snapshot", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("stream_id", "sequence"),
        schema="broker",
    )

    op.create_table(
        "payments",
        sa.Column(
            "id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("payment_id", sa.Text(), nullable=False, unique=True),
        sa.Column("customer_id", sa.Text(), nullable=False),
        sa.Column("currency", sa.Text(), nullable=False),
        sa.Column("original_amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("refundable_remaining_minor", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        schema="bank",
    )

    op.execute("GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA broker TO mandateguard_broker")
    op.execute("GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA bank TO mandateguard_bank")


def downgrade() -> None:
    op.drop_table("payments", schema="bank")
    op.drop_table("audit_events", schema="broker")
    op.drop_table("audit_stream_heads", schema="broker")
    op.drop_table("policy_evaluations", schema="broker")
    op.drop_table("action_requests", schema="broker")
    op.drop_table("governance_state", schema="broker")
    op.drop_table("policy_versions", schema="broker")
    op.drop_table("agent_credentials", schema="broker")
    op.drop_table("agents", schema="broker")

    for enum_name in (
        "evaluation_phase",
        "policy_decision",
        "action_state",
        "policy_version_status",
        "risk_mode",
        "governance_run_state",
        "agent_status",
    ):
        op.execute(f"DROP TYPE broker.{enum_name}")
