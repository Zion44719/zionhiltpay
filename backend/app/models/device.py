import uuid
from datetime import datetime

from sqlalchemy import String, Numeric, DateTime, Enum, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base
import enum


class DeviceType(str, enum.Enum):
    phone = "phone"
    laptop = "laptop"
    tablet = "tablet"
    other = "other"


class DeviceStatus(str, enum.Enum):
    active = "active"
    lost = "lost"
    stolen = "stolen"
    damaged = "damaged"
    claim_paid = "claim_paid"
    inactive = "inactive"


class Device(Base):
    """
    Insurance-eligible device belonging to a user.

    NOTE (v1.1 roadmap): `mac_address`, `last_seen_at`, and `last_seen_location`
    are already modeled so that MAC-address based tracking can be switched on
    in v1.1 without a schema migration. They are inert in v1.0.
    """
    __tablename__ = "devices"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    device_type: Mapped[DeviceType] = mapped_column(Enum(DeviceType, name="device_type"), nullable=False)
    brand: Mapped[str | None] = mapped_column(String(80), nullable=True)
    model: Mapped[str | None] = mapped_column(String(80), nullable=True)
    serial_number: Mapped[str | None] = mapped_column(String(120), nullable=True)
    mac_address: Mapped[str | None] = mapped_column(String(17), nullable=True)  # v1.1
    estimated_value: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    insured_value: Mapped[float] = mapped_column(Numeric(18, 2), default=0.00, nullable=False)
    status: Mapped[DeviceStatus] = mapped_column(Enum(DeviceStatus, name="device_status"), default=DeviceStatus.active, nullable=False)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # v1.1
    last_seen_location: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # v1.1
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class InsuranceClaim(Base):
    __tablename__ = "insurance_claims"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    device_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("devices.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    claim_type: Mapped[str] = mapped_column(String(20), nullable=False)  # lost, stolen, damaged
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_amount: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    approved_amount: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="submitted", nullable=False)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
