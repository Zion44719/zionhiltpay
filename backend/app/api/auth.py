from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy import select, or_, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.config import settings
from app.core.limiter import limiter
from app.core import identity as idt
from app.core.crypto import encrypt_id, id_fingerprint
from app.core.security import (
    hash_password, verify_password, hash_pin, verify_pin,
    create_access_token, create_refresh_token, hash_refresh_token, decode_token,
)
from app.models.user import User, OTPChannel
from app.models.otp import OTPPurpose
from app.models.token import RefreshToken
from app.models.account import Account, AccountType
from app.schemas.auth import (
    RegisterRequest, VerifyOTPRequest, ResendOTPRequest, LoginRequest,
    TokenResponse, RefreshRequest, SetPinRequest, VerifyPinRequest, UserOut, RegisterResponse,
)
from app.services.otp_service import OTPService
from app.services.ledger import get_or_create_account
from app.services.audit import log_action
from app.api.deps import get_current_user, get_client_ip

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Verified against on unknown identifiers so response time does not reveal whether an account exists.
_DUMMY_PASSWORD_HASH = hash_password("not-a-real-password-zhp")


@router.get("/username-available")
@limiter.limit(settings.RATE_LIMIT_LOOKUP)
async def username_available(request: Request, username: str, db: AsyncSession = Depends(get_db)):
    try:
        u = idt.validate_username(username)
    except ValueError as exc:
        return {"available": False, "reason": str(exc)}
    taken = (await db.execute(select(User.id).where(User.username == u))).first()
    return {"available": taken is None, "reason": "That username is already taken" if taken else None}


@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=RegisterResponse)
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def register(request: Request, payload: RegisterRequest, db: AsyncSession = Depends(get_db)):
    dup = await db.execute(
        select(User.id).where(
            or_(func.lower(User.email) == payload.email,
                User.phone_number.in_(idt.phone_lookup_variants(payload.phone_number)))
        )
    )
    if dup.first():
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email or phone number already exists")
    if (await db.execute(select(User.id).where(User.username == payload.username))).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "That username is already taken")

    fingerprint = id_fingerprint(payload.id_type, payload.id_number)
    if (await db.execute(select(User.id).where(User.id_type == payload.id_type, User.id_number_hash == fingerprint))).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "This ID number is already linked to an account")

    id_ciphertext = encrypt_id(payload.id_number)
    user = None
    for _ in range(5):
        user = User(
            full_name=payload.full_name,
            username=payload.username,
            email=payload.email,
            phone_number=payload.phone_number,
            password_hash=hash_password(payload.password),
            preferred_otp_channel=OTPChannel(payload.preferred_otp_channel),
            account_number=idt.generate_account_number(),
            id_type=payload.id_type,
            id_number_enc=id_ciphertext,
            id_number_hash=fingerprint,
            id_number_last4=payload.id_number[-4:],
            id_submitted_at=datetime.now(timezone.utc),
            kyc_status="submitted",
        )
        db.add(user)
        try:
            await db.flush()
            break
        except IntegrityError as exc:
            await db.rollback()
            if "uq_users_account_number" in str(exc.orig):
                continue  # random 10-digit number collided: draw another
            raise HTTPException(status.HTTP_409_CONFLICT, "An account with these details already exists")
    else:  # pragma: no cover
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Could not allocate an account number, please retry")

    # Provision the user's three ledger accounts up front.
    await get_or_create_account(db, AccountType.user_wallet, user.id)
    await get_or_create_account(db, AccountType.user_reward, user.id)
    await get_or_create_account(db, AccountType.user_insurance, user.id)

    otp_service = OTPService(db)
    channel = OTPChannel(payload.preferred_otp_channel)
    await otp_service.issue(
        purpose=OTPPurpose.registration,
        channel=channel,
        email=payload.email if channel == OTPChannel.email else None,
        phone=payload.phone_number if channel == OTPChannel.sms else None,
        user_id=user.id,
    )

    # Audit trail records THAT an ID was submitted, never the number itself.
    await log_action(db, "USER_REGISTERED", actor_user_id=str(user.id), actor_role=user.role,
                      entity_type="user", entity_id=str(user.id), ip_address=get_client_ip(request),
                      details={"id_type": payload.id_type, "kyc_status": "submitted"})
    await db.commit()

    return RegisterResponse(
        message=f"Registration successful. An OTP has been sent via {channel.value}.",
        user_id=user.id,
        otp_channel=channel.value,
        email=user.email,
        phone_number=user.phone_number,
        username=user.username,
        account_number=user.account_number,
    )


@router.post("/otp/verify")
@limiter.limit(settings.RATE_LIMIT_OTP)
async def verify_otp_endpoint(request: Request, payload: VerifyOTPRequest, db: AsyncSession = Depends(get_db)):
    if not payload.email and not payload.phone_number:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "email or phone_number is required")

    try:
        purpose = OTPPurpose(payload.purpose)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid OTP purpose")

    otp = await OTPService(db).check(purpose=purpose, code=payload.code, email=payload.email, phone=payload.phone_number)
    if otp is None:
        await db.commit()  # persist the failed-attempt counter before answering with an error
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired OTP code")

    user = await db.get(User, otp.user_id) if otp.user_id else None
    if user and purpose == OTPPurpose.registration:
        # Only the channel that actually received (and proved) the code becomes verified.
        if otp.channel == OTPChannel.email:
            user.email_verified = True
        else:
            user.phone_verified = True

    await log_action(db, "OTP_VERIFIED", actor_user_id=str(user.id) if user else None,
                      entity_type="otp", ip_address=get_client_ip(request),
                      details={"purpose": purpose.value})
    await db.commit()

    return {"message": "OTP verified successfully", "verified": True}


@router.post("/otp/resend")
@limiter.limit(settings.RATE_LIMIT_OTP)
async def resend_otp(request: Request, payload: ResendOTPRequest, db: AsyncSession = Depends(get_db)):
    if not payload.email and not payload.phone_number:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "email or phone_number is required")

    try:
        purpose = OTPPurpose(payload.purpose)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid OTP purpose")

    user = None
    if payload.email:
        result = await db.execute(select(User).where(func.lower(User.email) == payload.email))
        user = result.scalar_one_or_none()
    elif payload.phone_number:
        result = await db.execute(select(User).where(User.phone_number.in_(idt.phone_lookup_variants(payload.phone_number))))
        user = result.scalar_one_or_none()

    channel = OTPChannel(payload.channel) if payload.channel else (user.preferred_otp_channel if user else OTPChannel.email)

    otp_service = OTPService(db)
    await otp_service.issue(
        purpose=purpose,
        channel=channel,
        email=payload.email if channel == OTPChannel.email else None,
        phone=payload.phone_number if channel == OTPChannel.sms else None,
        user_id=user.id if user else None,
    )
    await db.commit()
    return {"message": f"OTP resent via {channel.value}"}


@router.post("/login", response_model=TokenResponse)
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def login(request: Request, payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    kind, value = idt.classify_identifier(payload.identifier)
    lookup = {
        "email": lambda: func.lower(User.email) == value,
        "account_number": lambda: User.account_number == value,
        "phone": lambda: User.phone_number.in_(idt.phone_lookup_variants(value)),
        "username": lambda: User.username == value,
    }.get(kind)
    user = None
    if lookup is not None:
        user = (await db.execute(select(User).where(lookup()))).scalar_one_or_none()

    generic_error = "Invalid login details or password"
    if user is None:
        verify_password(payload.password, _DUMMY_PASSWORD_HASH)  # equalise timing
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, generic_error)
    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, generic_error)

    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account is deactivated")
    if user.is_frozen:
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"Account is frozen: {user.freeze_reason or 'contact support'}")
    if not (user.email_verified or user.phone_verified):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Please verify your account via OTP before logging in")

    access_token = create_access_token(subject=str(user.id), role=user.role.value)
    raw_refresh, refresh_hash, expires_at = create_refresh_token(subject=str(user.id))

    db.add(RefreshToken(
        user_id=user.id,
        token_hash=refresh_hash,
        expires_at=expires_at,
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    ))

    user.last_login_at = datetime.now(timezone.utc)
    user.last_login_ip = get_client_ip(request)

    await log_action(db, "LOGIN_SUCCESS", actor_user_id=str(user.id), actor_role=user.role,
                      entity_type="user", entity_id=str(user.id), ip_address=get_client_ip(request))
    await db.commit()

    return TokenResponse(
        access_token=access_token,
        refresh_token=raw_refresh,
        user_id=user.id,
        role=user.role.value,
        pin_set=user.pin_set,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(payload: RefreshRequest, db: AsyncSession = Depends(get_db)):
    try:
        decoded = decode_token(payload.refresh_token)
    except Exception:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token")

    if decoded.get("type") != "refresh":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token type")

    token_hash = hash_refresh_token(payload.refresh_token)
    result = await db.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    stored = result.scalar_one_or_none()

    if stored is None or stored.revoked or stored.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token is invalid, expired, or revoked")

    user_result = await db.execute(select(User).where(User.id == stored.user_id))
    user = user_result.scalar_one_or_none()
    if user is None or not user.is_active or user.is_frozen:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account is not eligible for token refresh")

    # Rotate: revoke old, issue new
    stored.revoked = True
    new_access = create_access_token(subject=str(user.id), role=user.role.value)
    new_raw_refresh, new_hash, new_expires = create_refresh_token(subject=str(user.id))
    new_token_row = RefreshToken(user_id=user.id, token_hash=new_hash, expires_at=new_expires)
    db.add(new_token_row)
    await db.flush()
    stored.replaced_by = new_token_row.id

    await db.commit()

    return TokenResponse(
        access_token=new_access,
        refresh_token=new_raw_refresh,
        user_id=user.id,
        role=user.role.value,
        pin_set=user.pin_set,
    )


@router.post("/logout")
async def logout(payload: RefreshRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    token_hash = hash_refresh_token(payload.refresh_token)
    result = await db.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash, RefreshToken.user_id == user.id))
    stored = result.scalar_one_or_none()
    if stored:
        stored.revoked = True
    await log_action(db, "LOGOUT", actor_user_id=str(user.id), actor_role=user.role)
    await db.commit()
    return {"message": "Logged out successfully"}


@router.post("/pin/set")
async def set_pin(request: Request, payload: SetPinRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    if payload.pin != payload.confirm_pin:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "PIN and confirmation PIN do not match")
    if payload.pin in ("0000", "1234", "1111", "123456", "000000"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Chosen PIN is too weak/common, please choose another")

    user.pin_hash = hash_pin(payload.pin)
    user.pin_set = True
    user.pin_failed_attempts = 0
    user.pin_locked_until = None

    await log_action(db, "PIN_SET", actor_user_id=str(user.id), actor_role=user.role,
                      entity_type="user", entity_id=str(user.id), ip_address=get_client_ip(request))
    await db.commit()
    return {"message": "Transaction PIN set successfully"}


@router.post("/pin/verify")
async def verify_pin_endpoint(request: Request, payload: VerifyPinRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    if not user.pin_set or not user.pin_hash:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No PIN has been set for this account")

    if user.pin_locked_until and user.pin_locked_until.replace(tzinfo=timezone.utc) > datetime.now(timezone.utc):
        raise HTTPException(status.HTTP_423_LOCKED, f"PIN is locked until {user.pin_locked_until.isoformat()} due to repeated failures")

    if not verify_pin(payload.pin, user.pin_hash):
        user.pin_failed_attempts += 1
        if user.pin_failed_attempts >= settings.PIN_MAX_FAILED_ATTEMPTS:
            user.pin_locked_until = datetime.now(timezone.utc) + timedelta(minutes=settings.PIN_LOCK_MINUTES)
            await log_action(db, "PIN_LOCKED", actor_user_id=str(user.id), actor_role=user.role,
                              ip_address=get_client_ip(request),
                              details={"failed_attempts": user.pin_failed_attempts})
        await db.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Incorrect PIN")

    user.pin_failed_attempts = 0
    await db.commit()
    return {"message": "PIN verified", "valid": True}


@router.get("/me", response_model=UserOut)
async def get_me(user: User = Depends(get_current_user)):
    return user
