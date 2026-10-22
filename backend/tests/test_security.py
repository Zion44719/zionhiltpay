"""
Unit tests for core/security.py.
Run with: pytest tests/test_security.py -v
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from jose import jwt

from app.core.security import (
    hash_password, verify_password,
    hash_pin, verify_pin,
    generate_otp_code, hash_otp, verify_otp,
    create_access_token, decode_token,
    generate_reference,
)
from app.core.config import settings


def test_password_hash_roundtrip():
    hashed = hash_password("StrongPass123")
    assert hashed != "StrongPass123"
    assert verify_password("StrongPass123", hashed)
    assert not verify_password("WrongPass123", hashed)


def test_pin_hash_roundtrip():
    pin_hash = hash_pin("1234")
    assert verify_pin("1234", pin_hash)
    assert not verify_pin("4321", pin_hash)


def test_otp_generation_and_hash_verify():
    code = generate_otp_code(6)
    assert len(code) == 6
    assert code.isdigit()
    h = hash_otp(code)
    assert verify_otp(code, h)
    assert not verify_otp("000000" if code != "000000" else "111111", h)


def test_access_token_roundtrip():
    token = create_access_token(subject="user-123", role="user")
    payload = decode_token(token)
    assert payload["sub"] == "user-123"
    assert payload["role"] == "user"
    assert payload["type"] == "access"


def test_transaction_reference_format():
    ref = generate_reference()
    assert ref.startswith("ZHP-")
    parts = ref.split("-")
    assert len(parts) == 3
    assert len(parts[1]) == 8  # YYYYMMDD
    assert len(parts[2]) == 8  # hex token
