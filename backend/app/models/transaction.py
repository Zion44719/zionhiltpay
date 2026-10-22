import uuid
from datetime import datetime

from sqlalchemy import String, Numeric, DateTime, Enum, ForeignKey, Text, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base
import enum


class TransactionType(str, enum.Enum):
    deposit = "deposit"
    withdrawal = "withdrawal"
    transfer = "transfer"
    reward_credit = "reward_credit"
    insurance_contribution = "insurance_contribution"
    insurance_claim_payout = "insurance_claim_payout"
    fee = "fee"
    reversal = "reversal"


class TransactionStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"
    reversed = "reversed"
    flagged = "flagged"


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    reference: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    initiator_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    counterparty_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    type: Mapped[TransactionType] = mapped_column(Enum(TransactionType, name="transaction_type"), nullable=False)
    status: Mapped[TransactionStatus] = mapped_column(
        Enum(TransactionStatus, name="transaction_status"), default=TransactionStatus.pending, nullable=False
    )

    amount: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    fee_amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0.00, nullable=False)
    reward_amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0.00, nullable=False)
    insurance_contribution: Mapped[float] = mapped_column(Numeric(18, 2), default=0.00, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="NGN", nullable=False)

    narration: Mapped[str | None] = mapped_column(Text, nullable=True)
    gateway_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    meta: Mapped[dict] = mapped_column("metadata", JSONB, default=dict, nullable=False)

    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    device_fingerprint: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"
    __table_args__ = (CheckConstraint("direction IN ('D','C')", name="ck_ledger_direction"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transaction_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False)
    direction: Mapped[str] = mapped_column(String(1), nullable=False)  # 'D' or 'C'
    amount: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    balance_after: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
