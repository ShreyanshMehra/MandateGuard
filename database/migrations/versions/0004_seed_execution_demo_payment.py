"""Seed a payment dedicated to Milestone 4 execution tests.

payment-demo-002 is used by the Milestone 3 suite with fixed-balance
assumptions (e.g. a 150000 request must exceed its 200000 refundable
balance in a specific denial scenario). Milestone 4's tests actually
execute refunds and drain balances, so they get their own payment to avoid
cross-file interference when both suites run in the same session.

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-27
"""

from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

PAYMENT = {
    "payment_id": "payment-demo-004",
    "customer_id": "customer-demo-002",
    "currency": "USD",
    "original_amount_minor": 5000000,
    "refundable_remaining_minor": 5000000,
}


def upgrade() -> None:
    connection = op.get_bind()
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
        PAYMENT,
    )


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(sa.text("DELETE FROM bank.payments WHERE payment_id = :payment_id"), {"payment_id": PAYMENT["payment_id"]})
