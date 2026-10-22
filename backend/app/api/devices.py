from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.user import User
from app.models.device import Device, DeviceType, DeviceStatus, InsuranceClaim
from app.models.account import AccountType
from app.schemas.device import RegisterDeviceRequest, DeviceOut, FileClaimRequest, ClaimOut
from app.services.ledger import get_or_create_account
from app.services.audit import log_action
from app.api.deps import get_current_user, get_client_ip

router = APIRouter(prefix="/api/devices", tags=["devices"])

# Max share of a device's estimated value that the accrued insurance pool
# will ever be allowed to cover, to keep payouts proportionate.
MAX_COVERAGE_RATIO = 0.80


@router.post("", response_model=DeviceOut, status_code=status.HTTP_201_CREATED)
async def register_device(request: Request, payload: RegisterDeviceRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """
    Register a phone/laptop/etc. for device-insurance coverage.

    Coverage builds up automatically from the insurance_contribution portion
    of the user's transaction fees (see services/rewards.py) rather than a
    separate premium payment — spend on the platform, build device coverage.

    NOTE: MAC-address based loss/theft tracking is a v1.1 feature. The field
    exists on the model already; this endpoint accepts it as optional so the
    UI can start collecting it, but no tracking logic runs against it yet.
    """
    device = Device(
        user_id=user.id,
        device_type=DeviceType(payload.device_type),
        brand=payload.brand,
        model=payload.model,
        serial_number=payload.serial_number,
        estimated_value=payload.estimated_value,
        insured_value=0.00,
        status=DeviceStatus.active,
    )
    db.add(device)
    await db.flush()

    await log_action(db, "DEVICE_REGISTERED", actor_user_id=str(user.id), actor_role=user.role,
                      entity_type="device", entity_id=str(device.id), ip_address=get_client_ip(request),
                      details={"device_type": device.device_type.value, "estimated_value": float(device.estimated_value)})
    await db.commit()
    return device


@router.get("", response_model=list[DeviceOut])
async def list_devices(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    result = await db.execute(select(Device).where(Device.user_id == user.id).order_by(Device.registered_at.desc()))
    return result.scalars().all()


@router.get("/{device_id}", response_model=DeviceOut)
async def get_device(device_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    result = await db.execute(select(Device).where(Device.id == device_id, Device.user_id == user.id))
    device = result.scalar_one_or_none()
    if device is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found")
    return device


@router.post("/claims", response_model=ClaimOut, status_code=status.HTTP_201_CREATED)
async def file_claim(request: Request, payload: FileClaimRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    result = await db.execute(select(Device).where(Device.id == payload.device_id, Device.user_id == user.id))
    device = result.scalar_one_or_none()
    if device is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found")
    if device.status not in (DeviceStatus.active,):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Device is not eligible for a new claim (current status: {device.status.value})")

    insurance_account = await get_or_create_account(db, AccountType.user_insurance, user.id)
    max_payout = min(float(insurance_account.balance), float(device.estimated_value) * MAX_COVERAGE_RATIO)

    claim = InsuranceClaim(
        device_id=device.id,
        user_id=user.id,
        claim_type=payload.claim_type,
        description=payload.description,
        requested_amount=round(max_payout, 2),
        status="submitted",
    )
    db.add(claim)

    device.status = DeviceStatus(payload.claim_type) if payload.claim_type in ("lost", "stolen", "damaged") else device.status
    await db.flush()

    await log_action(db, "INSURANCE_CLAIM_FILED", actor_user_id=str(user.id), actor_role=user.role,
                      entity_type="insurance_claim", entity_id=str(claim.id), ip_address=get_client_ip(request),
                      details={"device_id": str(device.id), "claim_type": payload.claim_type})
    await db.commit()
    return claim


@router.get("/claims/mine", response_model=list[ClaimOut])
async def my_claims(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    result = await db.execute(select(InsuranceClaim).where(InsuranceClaim.user_id == user.id).order_by(InsuranceClaim.created_at.desc()))
    return result.scalars().all()
