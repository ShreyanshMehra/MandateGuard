import uuid

from sqlalchemy import BigInteger, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = {"schema": "bank"}

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    payment_id: Mapped[str] = mapped_column(Text, unique=True)
    customer_id: Mapped[str] = mapped_column(Text)
    currency: Mapped[str] = mapped_column(Text)
    original_amount_minor: Mapped[int] = mapped_column(BigInteger)
    refundable_remaining_minor: Mapped[int] = mapped_column(BigInteger)


class PermitUse(Base):
    __tablename__ = "permit_uses"
    __table_args__ = {"schema": "bank"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    permit_jti: Mapped[str] = mapped_column(Text)
    request_id: Mapped[str] = mapped_column(Text)
    result: Mapped[str] = mapped_column(Text)


class Refund(Base):
    __tablename__ = "refunds"
    __table_args__ = {"schema": "bank"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    request_id: Mapped[str] = mapped_column(Text, unique=True)
    permit_jti: Mapped[str] = mapped_column(Text, unique=True)
    payment_id: Mapped[str] = mapped_column(Text)
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(Text)
    bank_transaction_id: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)


class BankOperationEvent(Base):
    __tablename__ = "bank_operation_events"
    __table_args__ = {"schema": "bank"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    request_id: Mapped[str] = mapped_column(Text)
    event_type: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSONB)
