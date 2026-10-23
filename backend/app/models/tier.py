import uuid
from datetime import datetime

from sqlalchemy import String, SmallInteger, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class TierRequest(Base):
    """A customer's request to move up an account tier. BVN is encrypted like ID numbers."""
    __tablename__ = "tier_requests"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    target_tier: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)     # draft | pending | approved | rejected
    bvn_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    bvn_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    bvn_last4: Mapped[str | None] = mapped_column(String(4), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    document_file: Mapped[str | None] = mapped_column(String(64), nullable=True)        # file name only
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    edit_count: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)    # edits made AFTER submitting
