import uuid
from datetime import datetime

from sqlalchemy import String, Boolean, SmallInteger, DateTime, Enum, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base
from app.models.user import OTPChannel
import enum


class OTPPurpose(str, enum.Enum):
    registration = "registration"
    login = "login"
    pin_reset = "pin_reset"
    password_reset = "password_reset"
    transaction = "transaction"


class OTPCode(Base):
    __tablename__ = "otp_codes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    target_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    target_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    channel: Mapped[OTPChannel] = mapped_column(Enum(OTPChannel, name="otp_channel"), nullable=False)
    purpose: Mapped[OTPPurpose] = mapped_column(Enum(OTPPurpose, name="otp_purpose"), nullable=False)
    code_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    attempts: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(SmallInteger, default=5, nullable=False)
    consumed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
