from sqlalchemy import BigInteger, Text
from sqlalchemy.dialects.postgresql import UUID
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
