"""Milestone 4 schema: atomic budgets, signed permits and bank execution.

Adds the financial-exposure and permit/outcome tables from
docs/DATA_MODEL.md needed to reserve budget atomically, issue single-use
permits and record bank execution outcomes. Velocity/count limits,
policy_limits-driven configurable caps, approvals-triggered re-reservation
and checkpoints remain deferred to Milestone 5 per HANDOFF.md; caps for this
milestone are read directly from the active policy version's config.

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-27
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE TYPE broker.budget_reservation_state AS ENUM "
        "('RESERVED', 'COMMITTED', 'RELEASED', 'UNKNOWN')"
    )
    op.execute("CREATE TYPE broker.permit_status AS ENUM ('ISSUED', 'CONSUMED', 'CANCELLED', 'EXPIRED')")

    reservation_state = pg.ENUM(name="budget_reservation_state", schema="broker", create_type=False)
    permit_status = pg.ENUM(name="permit_status", schema="broker", create_type=False)

    op.create_table(
        "budget_locks",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("scope_id", sa.Text(), nullable=False),
        sa.Column("window_start", sa.Date(), nullable=False),
        sa.Column("currency", sa.Text(), nullable=False),
        sa.UniqueConstraint("scope", "scope_id", "window_start", "currency"),
        schema="broker",
    )

    op.create_table(
        "budget_reservations",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "action_id", pg.UUID(as_uuid=True),
            sa.ForeignKey("broker.action_requests.id"), nullable=False, unique=True,
        ),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.Text(), nullable=False),
        sa.Column("state", reservation_state, nullable=False, server_default="RESERVED"),
        sa.Column("resolution_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("resolved_at", sa.TIMESTAMP(timezone=True), nullable=True),
        schema="broker",
    )

    op.create_table(
        "reservation_allocations",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "reservation_id", pg.UUID(as_uuid=True),
            sa.ForeignKey("broker.budget_reservations.id"), nullable=False,
        ),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("scope_id", sa.Text(), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("window_start", sa.Date(), nullable=False),
        schema="broker",
    )

    op.create_table(
        "action_permits",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("jti", sa.Text(), nullable=False, unique=True),
        sa.Column(
            "action_id", pg.UUID(as_uuid=True),
            sa.ForeignKey("broker.action_requests.id"), nullable=False,
        ),
        sa.Column(
            "reservation_id", pg.UUID(as_uuid=True),
            sa.ForeignKey("broker.budget_reservations.id"), nullable=False,
        ),
        sa.Column("attempt_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", permit_status, nullable=False, server_default="ISSUED"),
        sa.Column("payload_hash", sa.Text(), nullable=False),
        sa.Column(
            "policy_version_id", pg.UUID(as_uuid=True),
            sa.ForeignKey("broker.policy_versions.id"), nullable=True,
        ),
        sa.Column("control_epoch_snapshot", sa.BigInteger(), nullable=True),
        sa.Column("agent_epoch_snapshot", sa.BigInteger(), nullable=True),
        sa.Column("issued_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.UniqueConstraint("action_id", "attempt_number"),
        schema="broker",
    )

    op.create_table(
        "execution_receipts",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "action_id", pg.UUID(as_uuid=True),
            sa.ForeignKey("broker.action_requests.id"), nullable=False, unique=True,
        ),
        sa.Column("document", pg.JSONB(), nullable=False),
        sa.Column("document_hash", sa.Text(), nullable=False),
        sa.Column("signature_b64", sa.Text(), nullable=False),
        sa.Column("key_id", sa.Text(), nullable=False),
        sa.Column("schema_version", sa.Text(), nullable=False, server_default="1.0"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        schema="broker",
    )

    op.create_table(
        "permit_uses",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("permit_jti", sa.Text(), nullable=False),
        sa.Column("request_id", sa.Text(), nullable=False),
        sa.Column("result", sa.Text(), nullable=False),
        sa.Column("used_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("permit_jti", "request_id"),
        schema="bank",
    )

    op.create_table(
        "refunds",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("request_id", sa.Text(), nullable=False, unique=True),
        sa.Column("permit_jti", sa.Text(), nullable=False, unique=True),
        sa.Column("payment_id", sa.Text(), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.Text(), nullable=False),
        sa.Column("bank_transaction_id", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        schema="bank",
    )

    op.create_table(
        "bank_operation_events",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("request_id", sa.Text(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("payload", pg.JSONB(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        schema="bank",
    )

    op.execute("GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA broker TO mandateguard_broker")
    op.execute("GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA bank TO mandateguard_bank")


def downgrade() -> None:
    op.drop_table("bank_operation_events", schema="bank")
    op.drop_table("refunds", schema="bank")
    op.drop_table("permit_uses", schema="bank")
    op.drop_table("execution_receipts", schema="broker")
    op.drop_table("action_permits", schema="broker")
    op.drop_table("reservation_allocations", schema="broker")
    op.drop_table("budget_reservations", schema="broker")
    op.drop_table("budget_locks", schema="broker")
    op.execute("DROP TYPE broker.permit_status")
    op.execute("DROP TYPE broker.budget_reservation_state")
