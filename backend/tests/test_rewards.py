"""
Unit tests for services/rewards.py — pure-function fee split logic.
Run with: pytest tests/test_rewards.py -v
"""
import sys, os
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.rewards import compute_fee_split


def test_basic_split_sums_correctly():
    split = compute_fee_split(
        amount=Decimal("10000.00"),
        fee_rate=Decimal("0.0150"),
        reward_rate=Decimal("0.0050"),
        insurance_rate=Decimal("0.0100"),
    )
    # fee = 10000 * 0.015 = 150.00
    assert split.fee_amount == Decimal("150.00")
    # reward = 10000 * 0.005 = 50.00
    assert split.reward_amount == Decimal("50.00")
    # insurance = fee * 0.01 = 1.50
    assert split.insurance_contribution == Decimal("1.50")
    # platform_net = fee - reward - insurance
    assert split.platform_net == split.fee_amount - split.reward_amount - split.insurance_contribution
    assert split.platform_net >= Decimal("0.00")


def test_split_never_exceeds_fee_collected():
    # Deliberately pathological rates where reward+insurance would exceed fee
    split = compute_fee_split(
        amount=Decimal("1000.00"),
        fee_rate=Decimal("0.0010"),   # tiny fee
        reward_rate=Decimal("0.0500"),  # huge reward rate
        insurance_rate=Decimal("0.5000"),
    )
    assert split.reward_amount + split.insurance_contribution <= split.fee_amount
    assert split.platform_net >= Decimal("0.00")


def test_flat_fee_withdrawal_style():
    split = compute_fee_split(
        amount=Decimal("5000.00"),
        fee_rate=Decimal("0"),
        reward_rate=Decimal("0.0025"),
        insurance_rate=Decimal("0.0100"),
        flat_fee=Decimal("25.00"),
    )
    assert split.fee_amount == Decimal("25.00")
    assert split.reward_amount == Decimal("12.50")
    assert split.insurance_contribution == Decimal("0.25")


def test_zero_amount_produces_zero_split():
    split = compute_fee_split(
        amount=Decimal("0.00"),
        fee_rate=Decimal("0.015"),
        reward_rate=Decimal("0.005"),
        insurance_rate=Decimal("0.01"),
    )
    assert split.fee_amount == Decimal("0.00")
    assert split.reward_amount == Decimal("0.00")
    assert split.insurance_contribution == Decimal("0.00")
    assert split.platform_net == Decimal("0.00")
