import uuid
from datetime import datetime

from sqlalchemy import String, Boolean, Numeric, DateTime, Enum, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base
import enum


class AccountType(str, enum.Enum):
    user_wallet = "user_wallet"
    user_reward = "user_reward"
    user_insurance = "user_insurance"
    platform_revenue = "platform_revenue"
    platform_reward_pool = "platform_reward_pool"
    platform_insurance_pool = "platform_insurance_pool"
    external_gateway = "external_gateway"
    platform_loan_pool = "platform_loan_pool"


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (UniqueConstraint("user_id", "account_type", "currency", name="uq_account_user_type_currency"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    account_type: Mapped[AccountType] = mapped_column(Enum(AccountType, name="account_type"), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="NGN", nullable=False)
    balance: Mapped[float] = mapped_column(Numeric(18, 2), default=0.00, nullable=False)
    is_platform_account: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
