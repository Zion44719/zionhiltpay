"""
OTP service — generation, channel-based delivery (email/SMS), and verification.

Delivery providers are pluggable:
  EMAIL_PROVIDER=console -> prints to server logs (default/dev, no setup needed)
  EMAIL_PROVIDER=smtp    -> sends real email via SMTP creds in .env
  SMS_PROVIDER=console   -> prints to server logs (default/dev, no setup needed)
  SMS_PROVIDER=termii    -> sends real SMS via Termii (good NG number coverage)
  SMS_PROVIDER=twilio    -> sends real SMS via Twilio

In production, set real provider credentials in the environment — never
commit them. If a real provider is configured but the send itself fails
(bad credentials, network issue, etc.), we log the failure AND still write
the code to the console so you're never locked out while debugging — but
the person will not have actually received anything on their device.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from sqlalchemy import select, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import identity as idt
from app.core.config import settings
from app.core.security import generate_otp_code, hash_otp, verify_otp
from app.models.otp import OTPCode, OTPPurpose
from app.models.user import OTPChannel

logger = logging.getLogger("zionhiltpay.otp")


def _otp_email_body(code: str, purpose: str) -> tuple[str, str]:
    subject = f"Your ZionhiltPay verification code: {code}"
    body = (
        f"Your ZionhiltPay verification code is: {code}\n\n"
        f"This code expires in {settings.OTP_EXPIRE_MINUTES} minutes and is for: {purpose}.\n"
        f"If you didn't request this, you can safely ignore this email."
    )
    return subject, body


async def _send_smtp_email(to_email: str, subject: str, body: str) -> None:
    """Real SMTP send via aiosmtplib, using creds from settings."""
    import aiosmtplib
    from email.message import EmailMessage

    msg = EmailMessage()
    msg["From"] = settings.EMAIL_FROM
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)

    await aiosmtplib.send(
        msg,
        hostname=settings.SMTP_HOST,
        port=settings.SMTP_PORT,
        username=settings.SMTP_USER or None,
        password=settings.SMTP_PASSWORD or None,
        start_tls=True,
    )


async def _deliver_email(to_email: str, code: str, purpose: str) -> None:
    subject, body = _otp_email_body(code, purpose)

    if settings.EMAIL_PROVIDER == "smtp":
        if not settings.SMTP_HOST:
            logger.warning(
                "EMAIL_PROVIDER=smtp but SMTP_HOST is not set — falling back to console logging. "
                "Set SMTP_HOST/SMTP_USER/SMTP_PASSWORD in your .env to send real email."
            )
        else:
            try:
                await _send_smtp_email(to_email, subject, body)
                logger.info("Sent OTP email to %s via SMTP (%s)", to_email, settings.SMTP_HOST)
                return
            except Exception as exc:  # noqa: BLE001 — never let notification failure break auth
                logger.error("SMTP send to %s failed: %s. Falling back to console logging.", to_email, exc)

    # console fallback (default provider, or SMTP misconfigured/failed)
    if settings.APP_ENV == "production":
        logger.error("OTP email to %s could NOT be delivered and the code is withheld from logs in production.", to_email)
        return
    logger.info("[EMAIL OTP] To: %s | Purpose: %s | Code: %s (expires in %s min)",
                to_email, purpose, code, settings.OTP_EXPIRE_MINUTES)


async def _send_termii_sms(to_phone: str, message: str) -> None:
    """Real SMS send via Termii (https://termii.com) — strong Nigerian number coverage."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            "https://api.ng.termii.com/api/sms/send",
            json={
                "to": to_phone,
                "from": settings.SMS_SENDER_ID,
                "sms": message,
                "type": "plain",
                "channel": "generic",
                "api_key": settings.SMS_API_KEY,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        if str(data.get("code")) not in ("ok", "200"):
            raise RuntimeError(f"Termii rejected the send: {data}")


async def _send_twilio_sms(to_phone: str, message: str) -> None:
    """Real SMS send via Twilio. Expects SMS_API_KEY formatted as 'ACCOUNT_SID:AUTH_TOKEN:FROM_NUMBER'."""
    try:
        account_sid, auth_token, from_number = settings.SMS_API_KEY.split(":")
    except ValueError:
        raise RuntimeError(
            "For SMS_PROVIDER=twilio, SMS_API_KEY must be 'ACCOUNT_SID:AUTH_TOKEN:FROM_NUMBER'"
        )
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json",
            data={"To": to_phone, "From": from_number, "Body": message},
            auth=(account_sid, auth_token),
        )
        resp.raise_for_status()


async def _deliver_sms(to_phone: str, code: str, purpose: str) -> None:
    message = f"Your ZionhiltPay verification code is {code}. Expires in {settings.OTP_EXPIRE_MINUTES} min. Do not share this code."

    if settings.SMS_PROVIDER in ("termii", "twilio"):
        if not settings.SMS_API_KEY:
            logger.warning(
                "SMS_PROVIDER=%s but SMS_API_KEY is not set — falling back to console logging. "
                "Set SMS_API_KEY in your .env to send real SMS.", settings.SMS_PROVIDER
            )
        else:
            try:
                if settings.SMS_PROVIDER == "termii":
                    await _send_termii_sms(to_phone, message)
                else:
                    await _send_twilio_sms(to_phone, message)
                logger.info("Sent OTP SMS to %s via %s", to_phone, settings.SMS_PROVIDER)
                return
            except Exception as exc:  # noqa: BLE001 — never let notification failure break auth
                logger.error("%s SMS send to %s failed: %s. Falling back to console logging.",
                             settings.SMS_PROVIDER, to_phone, exc)

    # console fallback (default provider, or real send misconfigured/failed)
    if settings.APP_ENV == "production":
        logger.error("OTP SMS to %s could NOT be delivered and the code is withheld from logs in production.", to_phone)
        return
    logger.info("[SMS OTP] To: %s | Purpose: %s | Code: %s (expires in %s min)",
                to_phone, purpose, code, settings.OTP_EXPIRE_MINUTES)


class OTPService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def issue(
        self,
        purpose: OTPPurpose,
        channel: OTPChannel,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        user_id=None,
    ) -> OTPCode:
        code = generate_otp_code(settings.OTP_LENGTH)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.OTP_EXPIRE_MINUTES)

        otp = OTPCode(
            user_id=user_id,
            target_email=email,
            target_phone=phone,
            channel=channel,
            purpose=purpose,
            code_hash=hash_otp(code),
            max_attempts=settings.OTP_MAX_ATTEMPTS,
            expires_at=expires_at,
        )
        self.db.add(otp)
        await self.db.flush()

        if channel == OTPChannel.email and email:
            await _deliver_email(email, code, purpose.value)
        elif channel == OTPChannel.sms and phone:
            await _deliver_sms(phone, code, purpose.value)
        else:
            raise ValueError("No valid delivery target for chosen OTP channel")

        return otp

    async def check(
        self,
        purpose: OTPPurpose,
        code: str,
        email: Optional[str] = None,
        phone: Optional[str] = None,
    ) -> Optional[OTPCode]:
        """Return the OTP row if `code` is right, else None.

        An OTP is stored against ONE target (the email or the phone it was sent to), so a caller that
        supplies both identifiers must match on either, never both. A wrong guess is counted on the row
        (the caller must commit so the count survives the error response).
        """
        targets = []
        if email:
            targets.append(func.lower(OTPCode.target_email) == email.lower())
        if phone:
            targets.append(OTPCode.target_phone.in_(idt.phone_lookup_variants(phone)))
        if not targets:
            return None

        stmt = (
            select(OTPCode)
            .where(OTPCode.purpose == purpose, OTPCode.consumed.is_(False), or_(*targets))
            .order_by(OTPCode.created_at.desc())
            .limit(1)
        )
        otp = (await self.db.execute(stmt)).scalar_one_or_none()
        if otp is None:
            return None
        if otp.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
            return None
        if otp.attempts >= otp.max_attempts:
            return None  # locked: request a new code

        otp.attempts += 1
        if not verify_otp(code, otp.code_hash):
            await self.db.flush()
            return None

        otp.consumed = True
        await self.db.flush()
        return otp

    async def verify(self, purpose: OTPPurpose, code: str, email: Optional[str] = None, phone: Optional[str] = None) -> bool:
        return await self.check(purpose, code, email=email, phone=phone) is not None
