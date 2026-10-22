import uuid
from datetime import datetime
from pydantic import BaseModel, field_validator, ConfigDict


class WalletBalanceOut(BaseModel):
    account_number: str | None = None
    wallet_balance: float
    reward_balance: float
    insurance_balance: float
    currency: str = "NGN"


class DepositRequest(BaseModel):
    amount: float
    narration: str | None = None

    @field_validator("amount")
    @classmethod
    def positive_amount(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Amount must be greater than zero")
        if v > 5_000_000:
            raise ValueError("Amount exceeds maximum single deposit limit")
        return round(v, 2)


class TransferRequest(BaseModel):
    recipient_identifier: str  # email or phone number
    amount: float
    pin: str
    narration: str | None = None

    @field_validator("amount")
    @classmethod
    def positive_amount(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Amount must be greater than zero")
        return round(v, 2)


class WithdrawRequest(BaseModel):
    amount: float
    pin: str
    bank_account_number: str
    bank_code: str
    narration: str | None = None

    @field_validator("amount")
    @classmethod
    def positive_amount(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Amount must be greater than zero")
        return round(v, 2)

    @field_validator("bank_account_number")
    @classmethod
    def validate_acct(cls, v: str) -> str:
        if not v.isdigit() or len(v) != 10:
            raise ValueError("bank_account_number must be exactly 10 digits (NUBAN)")
        return v


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    reference: str
    type: str
    status: str
    amount: float
    fee_amount: float
    reward_amount: float
    insurance_contribution: float
    currency: str
    narration: str | None
    created_at: datetime
    completed_at: datetime | None


class TransactionListOut(BaseModel):
    items: list[TransactionOut]
    total: int
    page: int
    page_size: int
