"""
Identity helpers: account numbers, usernames, phone/email normalisation, ID-number validation,
and detection of what kind of identifier a person typed at login / when sending money.

Everything here is pure (no database), so it is easy to test exhaustively.
"""
import re
import secrets
from typing import Optional

ID_TYPES = ("national_id", "drivers_license")
ID_TYPE_LABELS = {"national_id": "National ID (NIN)", "drivers_license": "Driver's license"}

RESERVED_USERNAMES = {
    "admin", "administrator", "root", "support", "help", "system", "official", "staff",
    "security", "billing", "api", "www", "mod", "moderator", "null", "undefined", "me", "you",
}
RESERVED_USERNAME_PREFIXES = ("zionhilt",)

USERNAME_RE = re.compile(r"^[a-z][a-z0-9_]{2,19}$")


# ---------------------------------------------------------------------------
# Account numbers: 10 digits, last digit is a Luhn check digit
# ---------------------------------------------------------------------------
def luhn_check_digit(payload: str) -> str:
    """Check digit that makes payload+digit pass the Luhn test."""
    total = 0
    for i, ch in enumerate(reversed(payload)):
        d = int(ch)
        if i % 2 == 0:  # double every second digit, starting from the rightmost payload digit
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return str((10 - total % 10) % 10)


def is_valid_account_number(value: str) -> bool:
    return bool(re.fullmatch(r"\d{10}", value or "")) and luhn_check_digit(value[:-1]) == value[-1]


def generate_account_number() -> str:
    """Random (non-sequential, so not enumerable) 10-digit number with a check digit.
    Uniqueness is guaranteed by a database unique index; callers retry on collision."""
    body = str(secrets.randbelow(9) + 1) + "".join(str(secrets.randbelow(10)) for _ in range(8))
    return body + luhn_check_digit(body)


# ---------------------------------------------------------------------------
# Email / phone / username
# ---------------------------------------------------------------------------
def normalize_email(value: str) -> str:
    return (value or "").strip().lower()


def normalize_phone(raw: Optional[str]) -> Optional[str]:
    """Return E.164 (+<digits>) or None if the input isn't a recognisable phone number.

    Accepts Nigerian local format (08012345678), 234-prefixed (2348012345678) and any
    international number written with a leading '+'. A bare 10-digit number is NOT accepted
    as a phone number: it would be indistinguishable from an account number.
    """
    s = re.sub(r"[\s\-().]", "", raw or "")
    if re.fullmatch(r"0\d{10}", s):
        return "+234" + s[1:]
    if re.fullmatch(r"234\d{10}", s):
        return "+" + s
    if re.fullmatch(r"\+\d{10,15}", s):
        return s
    return None


def phone_lookup_variants(phone: str) -> list[str]:
    """Stored values may predate normalisation and lack the '+'; match both."""
    return [phone, phone.lstrip("+")]


def validate_username(raw: str) -> str:
    """Return the normalised (lower-case) username or raise ValueError with a user-facing message."""
    u = (raw or "").strip().lower()
    if not USERNAME_RE.fullmatch(u):
        raise ValueError(
            "Username must be 3-20 characters, start with a letter, and use only letters, digits or underscores"
        )
    if u in RESERVED_USERNAMES or u.startswith(RESERVED_USERNAME_PREFIXES):
        raise ValueError("That username is reserved. Please choose another")
    return u


# ---------------------------------------------------------------------------
# Government ID numbers (format checks only - see README: this is NOT verification)
# ---------------------------------------------------------------------------
def normalize_id_number(id_type: str, raw: str) -> str:
    s = re.sub(r"[\s\-/]", "", raw or "").upper()
    if id_type == "national_id":
        if not re.fullmatch(r"\d{11}", s):
            raise ValueError("National ID (NIN) must be exactly 11 digits")
    elif id_type == "drivers_license":
        if not re.fullmatch(r"[A-Z0-9]{8,20}", s) or not re.search(r"\d", s):
            raise ValueError("Driver's license number must be 8-20 letters/digits and include at least one digit")
    else:
        raise ValueError("ID type must be national_id or drivers_license")
    if len(set(s)) == 1:
        raise ValueError("That ID number doesn't look valid")
    return s


def mask_id_number(last4: Optional[str]) -> str:
    return f"••••{last4}" if last4 else "—"


# ---------------------------------------------------------------------------
# What did the person type? (login + recipient lookup)
# ---------------------------------------------------------------------------
def classify_identifier(raw: str) -> tuple[str, str]:
    """Return (kind, normalised_value). kind is one of:
    email | account_number | phone | username | unknown
    """
    s = (raw or "").strip()
    if not s:
        return "unknown", ""
    if "@" in s:
        return "email", normalize_email(s)
    compact = re.sub(r"[\s\-().]", "", s)
    if re.fullmatch(r"\d{10}", compact) and is_valid_account_number(compact):
        return "account_number", compact
    phone = normalize_phone(compact)
    if phone:
        return "phone", phone
    if USERNAME_RE.fullmatch(s.lower()):
        return "username", s.lower()
    return "unknown", s


def mask_name(full_name: str) -> str:
    """'Ada Lovelace' -> 'Ada L.'  Enough to confirm a recipient, not enough to harvest names."""
    parts = (full_name or "").split()
    if not parts:
        return "—"
    if len(parts) == 1:
        return parts[0]
    return f"{parts[0]} {parts[-1][0].upper()}."
