import uuid
from datetime import datetime
from pydantic import BaseModel, field_validator, ConfigDict


class RegisterDeviceRequest(BaseModel):
    device_type: str  # phone | laptop | tablet | other
    brand: str | None = None
    model: str | None = None
    serial_number: str | None = None
    estimated_value: float

    @field_validator("estimated_value")
    @classmethod
    def positive_value(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("estimated_value must be greater than zero")
        return round(v, 2)

    @field_validator("device_type")
    @classmethod
    def valid_type(cls, v: str) -> str:
        if v not in ("phone", "laptop", "tablet", "other"):
            raise ValueError("device_type must be one of phone, laptop, tablet, other")
        return v


class DeviceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    device_type: str
    brand: str | None
    model: str | None
    serial_number: str | None
    mac_address: str | None
    estimated_value: float
    insured_value: float
    status: str
    registered_at: datetime


class FileClaimRequest(BaseModel):
    device_id: uuid.UUID
    claim_type: str  # lost | stolen | damaged
    description: str | None = None

    @field_validator("claim_type")
    @classmethod
    def valid_claim_type(cls, v: str) -> str:
        if v not in ("lost", "stolen", "damaged"):
            raise ValueError("claim_type must be one of lost, stolen, damaged")
        return v


class ClaimOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    device_id: uuid.UUID
    claim_type: str
    description: str | None
    requested_amount: float
    approved_amount: float | None
    status: str
    created_at: datetime
