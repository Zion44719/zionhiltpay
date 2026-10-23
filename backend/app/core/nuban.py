"""
NUBAN (Nigeria Uniform Bank Account Number) check digit, per the CBN standard.

A NUBAN is 9 serial digits + 1 check digit. The check digit is computed over a 15-digit string made of the
institution code (normalised to 6 digits) and the 9-digit serial number:
  - 3-digit bank code (e.g. 011)        -> '000' + code   = 000011
  - 5-digit microfinance/OFI code (50547) -> '9'   + code = 950547
weights 3 7 3 3 7 3 3 7 3 3 7 3 3 7 3, sum the products, check digit = (10 - sum mod 10) mod 10.

This lets us (a) catch a mistyped account number or the wrong bank before any money moves, and (b) suggest
which banks an account number could belong to when the person has typed only the number. Institutions that
use other code formats (many wallet-style fintechs) cannot be checked this way, and for those we say so.
"""
import secrets
from typing import Iterable, Optional

WEIGHTS = (3, 7, 3, 3, 7, 3, 3, 7, 3, 3, 7, 3, 3, 7, 3)


def institution_code_6(code: str) -> Optional[str]:
    """6-digit form of a CBN institution code, or None if the code isn't a checkable 3- or 5-digit code."""
    code = (code or "").strip()
    if not code.isdigit():
        return None
    if len(code) == 3:
        return "000" + code
    if len(code) == 5:
        return "9" + code
    return None


def check_digit(code6: str, serial9: str) -> str:
    digits = code6 + serial9
    total = sum(int(d) * w for d, w in zip(digits, WEIGHTS))
    return str((10 - total % 10) % 10)


def is_valid_nuban(institution_code: str, account_number: str) -> Optional[bool]:
    """True/False if the account number is (in)valid for that institution; None if it can't be checked."""
    code6 = institution_code_6(institution_code)
    if code6 is None:
        return None
    if not (account_number or "").isdigit() or len(account_number) != 10:
        return False
    return check_digit(code6, account_number[:9]) == account_number[9]


def candidate_banks(account_number: str, banks: Iterable[dict]) -> list[dict]:
    """Banks whose code makes this account number's check digit come out right.
    Usually 2 to 4 of them, never a certainty: the person (or a name lookup) confirms the final choice."""
    if not (account_number or "").isdigit() or len(account_number) != 10:
        return []
    return [b for b in banks if is_valid_nuban(b["code"], account_number) is True]


def make_account_number(institution_code: str, serial: str) -> str:
    """Build a valid NUBAN (used for demos and tests)."""
    code6 = institution_code_6(institution_code)
    if code6 is None:
        raise ValueError("Institution code must be 3 or 5 digits")
    serial9 = str(serial).zfill(9)
    if not serial9.isdigit() or len(serial9) != 9:
        raise ValueError("Serial must be up to 9 digits")
    return serial9 + check_digit(code6, serial9)


def random_account_number(institution_code: str) -> str:
    return make_account_number(institution_code, "".join(str(secrets.randbelow(10)) for _ in range(9)))
