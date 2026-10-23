import re
import uuid
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, EmailStr, field_validator, model_validator, ConfigDict

from app.core import identity as idt


class RegisterRequest(BaseModel):
    full_name: str
    username: str
    email: EmailStr
    phone_number: str
    password: str
    id_type: Literal["national_id", "drivers_license"]
    id_number: str
    consent_id_processing: bool
    preferred_otp_channel: str = "email"  # 'email' or 'sms'

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, v: str) -> str:
        v = " ".join(v.split())
        if not 2 <= len(v) <= 150:
            raise ValueError("Please enter your full name")
        return v

    @field_validator("username")
    @classmethod
    def validate_username_field(cls, v: str) -> str:
        return idt.validate_username(v)

    @field_validator("email")
    @classmethod
    def lower_email(cls, v: str) -> str:
        return idt.normalize_email(str(v))

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        phone = idt.normalize_phone(v)
        if phone is None:
            raise ValueError(
                "Enter a valid phone number, e.g. 08012345678 or +2348012345678 "
                "(numbers from other countries must start with + and the country code)"
            )
        return phone

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not re.search(r"[0-9]", v):
            raise ValueError("Password must contain at least one digit")
        return v

    @field_validator("consent_id_processing")
    @classmethod
    def require_consent(cls, v: bool) -> bool:
        if v is not True:
            raise ValueError("You must consent to ZionhiltPay processing your ID for identity verification")
        return v

    @field_validator("preferred_otp_channel")
    @classmethod
    def validate_channel(cls, v: str) -> str:
        if v not in ("email", "sms"):
            raise ValueError("preferred_otp_channel must be 'email' or 'sms'")
        return v

    @model_validator(mode="after")
    def normalise_id_number(self):
        self.id_number = idt.normalize_id_number(self.id_type, self.id_number)
        return self


class RegisterResponse(BaseModel):
    message: str
    user_id: uuid.UUID
    otp_channel: str
    email: str
    phone_number: str
    username: str
    account_number: str


class _OTPTarget(BaseModel):
    email: str | None = None
    phone_number: str | None = None

    @field_validator("email")
    @classmethod
    def _lower_email(cls, v):
        return idt.normalize_email(v) if v else v

    @field_validator("phone_number")
    @classmethod
    def _norm_phone(cls, v):
        return (idt.normalize_phone(v) or v) if v else v


class VerifyOTPRequest(_OTPTarget):
    purpose: str
    code: str


class ResendOTPRequest(_OTPTarget):
    purpose: str
    channel: str | None = None  # override preferred channel if provided


class LoginRequest(BaseModel):
    """`identifier` may be an account number, username, email or phone number.
    `email` is accepted as a legacy alias so older clients keep working."""
    identifier: str | None = None
    email: str | None = None
    password: str

    @model_validator(mode="after")
    def need_identifier(self):
        self.identifier = (self.identifier or self.email or "").strip()
        if not self.identifier:
            raise ValueError("Enter your account number, username, email or phone number")
        return self


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user_id: uuid.UUID
    role: str
    pin_set: bool


class RefreshRequest(BaseModel):
    refresh_token: str


class SetPinRequest(BaseModel):
    pin: str
    confirm_pin: str

    @field_validator("pin")
    @classmethod
    def validate_pin(cls, v: str) -> str:
        if not re.fullmatch(r"^\d{4,6}$", v):
            raise ValueError("PIN must be 4-6 digits")
        return v


class VerifyPinRequest(BaseModel):
    pin: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    full_name: str
    email: str
    phone_number: str
    role: str
    email_verified: bool
    phone_verified: bool
    pin_set: bool
    kyc_level: int
    is_active: bool
    is_frozen: bool
    username: str | None = None
    account_number: str | None = None
    kyc_status: str = "not_submitted"
    id_type: str | None = None
    id_number_last4: str | None = None  # the only part of the ID number any API ever returns
    account_tier: int = 1
    has_photo: bool = False
    created_at: datetime | None = None
