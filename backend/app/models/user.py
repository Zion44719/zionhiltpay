import uuid
from datetime import datetime

from sqlalchemy import String, Boolean, SmallInteger, Numeric, DateTime, Enum, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base
import enum


class UserRole(str, enum.Enum):
    user = "user"
    admin = "admin"
    super_admin = "super_admin"


class OTPChannel(str, enum.Enum):
    email = "email"
    sms = "sms"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    phone_number: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole, name="user_role"), default=UserRole.user, nullable=False)

    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    phone_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    preferred_otp_channel: Mapped[OTPChannel] = mapped_column(
        Enum(OTPChannel, name="otp_channel"), default=OTPChannel.email, nullable=False
    )

    pin_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pin_set: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    pin_failed_attempts: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)
    pin_locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_frozen: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    freeze_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- identity (see app/core/identity.py, app/core/crypto.py) ---
    username: Mapped[str | None] = mapped_column(String(20), nullable=True)          # unique, lower-case
    account_number: Mapped[str | None] = mapped_column(String(10), nullable=True)    # unique, 10 digits + Luhn
    id_type: Mapped[str | None] = mapped_column(String(20), nullable=True)           # national_id | drivers_license
    id_number_enc: Mapped[str | None] = mapped_column(Text, nullable=True)           # Fernet ciphertext - never returned by any API
    id_number_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)    # keyed HMAC, enforces one-ID-one-account
    id_number_last4: Mapped[str | None] = mapped_column(String(4), nullable=True)    # for masked display only
    id_submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    kyc_status: Mapped[str] = mapped_column(String(20), default="not_submitted", nullable=False)  # not_submitted|submitted|verified|rejected
    kyc_reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    kyc_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    kyc_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    kyc_level: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)
    tier_daily_limit: Mapped[float] = mapped_column(Numeric(18, 2), default=50000.00, nullable=False)

    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
