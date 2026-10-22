"""Unit tests for core/identity.py and core/crypto.py (no database needed)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from app.core import identity as idt
from app.core import crypto


def test_luhn_known_vector():
    # the classic Luhn example: 7992739871 -> check digit 3
    assert idt.luhn_check_digit("7992739871") == "3"


def test_generated_account_numbers_are_valid_and_look_right():
    seen = set()
    for _ in range(2000):
        n = idt.generate_account_number()
        assert len(n) == 10 and n.isdigit() and n[0] != "0"
        assert idt.is_valid_account_number(n)
        seen.add(n)
    assert len(seen) > 1990  # random, not sequential (collisions are astronomically rare)


def test_single_digit_typo_is_always_caught():
    n = idt.generate_account_number()
    for pos in range(10):
        for d in "0123456789":
            if d != n[pos]:
                typo = n[:pos] + d + n[pos + 1:]
                assert not idt.is_valid_account_number(typo), (n, typo)


@pytest.mark.parametrize("raw,expected", [
    ("08012345678", "+2348012345678"),
    ("0801 234 5678", "+2348012345678"),
    ("2348012345678", "+2348012345678"),
    ("+2348012345678", "+2348012345678"),
    ("+14155550123", "+14155550123"),
    ("1234567890", None),        # bare 10 digits: ambiguous with an account number
    ("12345", None),
    ("not a phone", None),
    ("", None),
])
def test_normalize_phone(raw, expected):
    assert idt.normalize_phone(raw) == expected


@pytest.mark.parametrize("raw,ok", [
    ("ada", True), ("Ada_Lovelace", True), ("a1_b2", True),
    ("ab", False), ("1ada", False), ("ada lovelace", False), ("ada-l", False),
    ("a" * 21, False), ("admin", False), ("ZionhiltCEO", False), ("support", False),
])
def test_username_rules(raw, ok):
    if ok:
        assert idt.validate_username(raw) == raw.strip().lower()
    else:
        with pytest.raises(ValueError):
            idt.validate_username(raw)


def test_id_number_rules():
    assert idt.normalize_id_number("national_id", "123 4567 8901") == "12345678901"
    for bad in ("1234567890", "123456789012", "abcdefghijk", "00000000000", ""):
        with pytest.raises(ValueError):
            idt.normalize_id_number("national_id", bad)
    assert idt.normalize_id_number("drivers_license", "abc-12345-aa") == "ABC12345AA"
    for bad in ("short1", "ABCDEFGHIJ", "A" * 30, "11111111"):
        with pytest.raises(ValueError):
            idt.normalize_id_number("drivers_license", bad)
    with pytest.raises(ValueError):
        idt.normalize_id_number("passport", "A12345678")


def test_classify_identifier():
    acct = idt.generate_account_number()
    assert idt.classify_identifier(acct) == ("account_number", acct)
    assert idt.classify_identifier(f" {acct[:5]} {acct[5:]} ") == ("account_number", acct)
    assert idt.classify_identifier("Ada@Example.COM") == ("email", "ada@example.com")
    assert idt.classify_identifier("08012345678") == ("phone", "+2348012345678")
    assert idt.classify_identifier("+2348012345678") == ("phone", "+2348012345678")
    assert idt.classify_identifier("Ada_L") == ("username", "ada_l")
    bad_acct = acct[:-1] + str((int(acct[-1]) + 1) % 10)
    assert idt.classify_identifier(bad_acct)[0] == "unknown"   # fails check digit, not a phone
    assert idt.classify_identifier("")[0] == "unknown"
    assert idt.classify_identifier("!!")[0] == "unknown"


def test_mask_name():
    assert idt.mask_name("Ada Lovelace") == "Ada L."
    assert idt.mask_name("Oni Oluwafemi Dare") == "Oni D."
    assert idt.mask_name("Cher") == "Cher"


def test_encryption_roundtrip_and_fingerprint():
    ct = crypto.encrypt_id("12345678901")
    assert "12345678901" not in ct
    assert crypto.decrypt_id(ct) == "12345678901"
    assert crypto.encrypt_id("12345678901") != ct           # random IV: ciphertexts differ
    fp = crypto.id_fingerprint("national_id", "12345678901")
    assert fp == crypto.id_fingerprint("national_id", "12345678901")           # deterministic
    assert fp != crypto.id_fingerprint("drivers_license", "12345678901")       # scoped by type
    assert "12345678901" not in fp and len(fp) == 64


def test_wrong_key_cannot_decrypt(monkeypatch):
    from app.core.config import settings
    ct = crypto.encrypt_id("12345678901")
    monkeypatch.setattr(settings, "DATA_ENCRYPTION_KEY", __import__("cryptography.fernet", fromlist=["Fernet"]).Fernet.generate_key().decode())
    with pytest.raises(ValueError):
        crypto.decrypt_id(ct)


def test_malformed_key_is_reported(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "DATA_ENCRYPTION_KEY", "not-a-real-key")
    with pytest.raises(ValueError):
        crypto.validate_encryption_key()
