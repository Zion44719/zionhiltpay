from datetime import datetime

from sqlalchemy import SmallInteger, Numeric, DateTime, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class PlatformConfig(Base):
    """Single-row table holding live-tunable platform economics & fraud thresholds."""
    __tablename__ = "platform_config"
    __table_args__ = (CheckConstraint("id = 1", name="single_row"),)

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, default=1)
    reward_rate: Mapped[float] = mapped_column(Numeric(6, 4), default=0.0050, nullable=False)
    insurance_contribution_rate: Mapped[float] = mapped_column(Numeric(6, 4), default=0.0100, nullable=False)
    transaction_fee_rate: Mapped[float] = mapped_column(Numeric(6, 4), default=0.0150, nullable=False)
    withdrawal_fee_flat: Mapped[float] = mapped_column(Numeric(18, 2), default=25.00, nullable=False)
    max_daily_transfer_default: Mapped[float] = mapped_column(Numeric(18, 2), default=50000.00, nullable=False)
    fraud_velocity_window_minutes: Mapped[int] = mapped_column(SmallInteger, default=10, nullable=False)
    fraud_velocity_max_txns: Mapped[int] = mapped_column(SmallInteger, default=6, nullable=False)
    fraud_large_amount_threshold: Mapped[float] = mapped_column(Numeric(18, 2), default=200000.00, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
