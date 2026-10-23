from typing import Literal
import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class AdminUserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    full_name: str
    username: str | None = None
    account_number: str | None = None
    email: str
    phone_number: str
    role: str
    is_active: bool
    is_frozen: bool
    kyc_level: int
    kyc_status: str = "not_submitted"
    id_type: str | None = None
    id_number_last4: str | None = None  # the full number is only available via the audited reveal endpoint
    id_submitted_at: datetime | None = None
    account_tier: int = 1
    has_photo: bool = False
    created_at: datetime


class KycDecisionRequest(BaseModel):
    decision: Literal["verify", "reject"]
    note: str | None = None


class FreezeAccountRequest(BaseModel):
    reason: str


class ReviewClaimRequest(BaseModel):
    approve: bool
    approved_amount: float | None = None
    review_note: str | None = None


class ResolveFraudFlagRequest(BaseModel):
    resolution_note: str | None = None


class PlatformStatsOut(BaseModel):
    total_users: int
    active_users: int
    frozen_users: int
    total_wallet_balance: float
    total_reward_pool_liability: float
    total_insurance_pool_liability: float
    platform_revenue_balance: float
    total_transactions: int
    transactions_today: int
    open_fraud_flags: int
    pending_claims: int
    pending_tier_requests: int = 0
    loans_outstanding: float = 0.0
    active_loans: int = 0


class ConfigUpdateRequest(BaseModel):
    reward_rate: float | None = None
    insurance_contribution_rate: float | None = None
    transaction_fee_rate: float | None = None
    withdrawal_fee_flat: float | None = None
    fraud_velocity_window_minutes: int | None = None
    fraud_velocity_max_txns: int | None = None
    fraud_large_amount_threshold: float | None = None
