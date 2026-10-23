"""NUBAN check digit, verified against the worked examples published by the CBN."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest
from app.core import nuban


def test_cbn_published_example_1_first_bank():
    # CBN NUBAN standard: First Bank (011), serial 000001457 -> 0000014579
    assert nuban.make_account_number("011", "000001457") == "0000014579"
    assert nuban.is_valid_nuban("011", "0000014579") is True


def test_cbn_published_example_2_check_digit_zero():
    # CBN NUBAN standard: First Bank (011), serial 000000022 -> check digit 0 (10 maps to 0)
    assert nuban.make_account_number("011", "000000022") == "0000000220"


def test_cbn_published_example_3_microfinance_five_digit_code():
    # CBN NUBAN standard: OFI code 50547 (-> 950547), serial 000021457 -> 0000214579
    assert nuban.institution_code_6("50547") == "950547"
    assert nuban.make_account_number("50547", "000021457") == "0000214579"


def test_wrong_bank_or_typo_is_rejected():
    good = nuban.random_account_number("058")
    assert nuban.is_valid_nuban("058", good) is True
    for pos in range(10):                       # every single-digit typo is caught
        for d in "0123456789":
            if d != good[pos]:
                assert nuban.is_valid_nuban("058", good[:pos] + d + good[pos + 1:]) is False


def test_uncheckable_codes_return_none_not_false():
    assert nuban.is_valid_nuban("999992", "0123456789") is None      # 6-digit fintech code: cannot be checked
    assert nuban.is_valid_nuban("abc", "0123456789") is None


def test_malformed_account_numbers():
    assert nuban.is_valid_nuban("011", "12345") is False
    assert nuban.is_valid_nuban("011", "01234567ab") is False


def test_candidate_banks_includes_the_real_bank_and_few_others():
    banks = [{"name": n, "code": c} for n, c in [("Access", "044"), ("GTBank", "058"), ("First", "011"), ("UBA", "033"),
             ("Zenith", "057"), ("Kuda", "50211"), ("OPay", "999992"), ("Wema", "035")]]
    acct = nuban.make_account_number("058", "123456789")
    names = [b["name"] for b in nuban.candidate_banks(acct, banks)]
    assert "GTBank" in names and "OPay" not in names and len(names) <= 4
    assert nuban.candidate_banks("12345", banks) == []
