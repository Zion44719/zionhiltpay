import uuid
from datetime import datetime

from sqlalchemy import String, SmallInteger, Numeric, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class Loan(Base):
    __tablename__ = "loans"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    reference: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    principal: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    interest: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    total_due: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    principal_repaid: Mapped[float] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    interest_repaid: Mapped[float] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    tenor_days: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    interest_rate_30d: Mapped[float] = mapped_column(Numeric(6, 4), nullable=False)      # rate in force when taken
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)    # active | repaid
    disbursed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
