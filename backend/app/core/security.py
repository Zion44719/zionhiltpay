"""
Security primitives: password hashing, PIN hashing, JWT issuance/verification.

Design notes:
- Passwords and transaction PINs are hashed with bcrypt via passlib — never
  stored or logged in plaintext, never compared with '=='.
- Access tokens are short-lived (15 min default). Refresh tokens are stored
  hashed in the DB (refresh_tokens table) so they can be revoked/rotated.
- A PIN failure counter with lockout is enforced at the service layer using
  users.pin_failed_attempts / pin_locked_until.
"""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import jwt, JWTError
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
pin_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------
def hash_password(plain_password: str) -> str:
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    return pwd_context.verify(plain_password, password_hash)


# ---------------------------------------------------------------------------
# Transaction PIN hashing (kept cryptographically separate from login password)
# ---------------------------------------------------------------------------
def hash_pin(plain_pin: str) -> str:
    return pin_context.hash(f"zhp-pin::{plain_pin}")


def verify_pin(plain_pin: str, pin_hash: str) -> bool:
    return pin_context.verify(f"zhp-pin::{plain_pin}", pin_hash)


# ---------------------------------------------------------------------------
# OTP hashing (OTPs are short-lived but still never stored in plaintext)
# ---------------------------------------------------------------------------
def generate_otp_code(length: int = 6) -> str:
    return "".join(secrets.choice("0123456789") for _ in range(length))


def hash_otp(code: str) -> str:
    return hashlib.sha256(f"zhp-otp::{code}".encode()).hexdigest()


def verify_otp(code: str, code_hash: str) -> bool:
    return secrets.compare_digest(hash_otp(code), code_hash)


# ---------------------------------------------------------------------------
# JWT tokens
# ---------------------------------------------------------------------------
def create_access_token(subject: str, role: str, extra: Optional[dict] = None) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "role": role,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(subject: str) -> tuple[str, str, datetime]:
    """Returns (raw_token, token_hash, expires_at). Raw token is given to the
    client; only the hash is persisted server-side."""
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": subject,
        "type": "refresh",
        "jti": secrets.token_urlsafe(16),
        "iat": now,
        "exp": expires_at,
    }
    raw = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    return raw, token_hash, expires_at


def hash_refresh_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()


def decode_token(token: str) -> dict:
    """Raises jose.JWTError on invalid/expired token."""
    return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])


def generate_reference(prefix: str = "ZHP") -> str:
    """Human-friendly unique transaction reference, e.g. ZHP-20260818-9F3K2A7B"""
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    rand = secrets.token_hex(4).upper()
    return f"{prefix}-{today}-{rand}"
