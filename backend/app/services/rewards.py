"""
Rewards & device-insurance economics.

Every fee-generating transaction (transfer, withdrawal) splits the platform
commission three ways:
  1. reward_amount           -> credited to the user's reward wallet (cashback)
  2. insurance_contribution  -> credited to the user's device-insurance pool
  3. remainder                -> platform revenue

This module only computes the split; `LedgerService` (via the wallet router)
performs the actual balanced postings.
"""
from decimal import Decimal
from dataclasses import dataclass

from app.services.ledger import q2


@dataclass
class FeeSplit:
    fee_amount: Decimal
    reward_amount: Decimal
    insurance_contribution: Decimal
    platform_net: Decimal


def compute_fee_split(
    amount: Decimal,
    fee_rate: Decimal,
    reward_rate: Decimal,
    insurance_rate: Decimal,
    flat_fee: Decimal = Decimal("0.00"),
) -> FeeSplit:
    """
    fee_amount = amount * fee_rate + flat_fee   (total commission charged)
    reward_amount = amount * reward_rate         (cashback to user, drawn from commission)
    insurance_contribution = fee_amount * insurance_rate  (into user's device-insurance pool)
    platform_net = fee_amount - reward_amount - insurance_contribution
    """
    amount = Decimal(str(amount))
    fee_amount = q2(amount * Decimal(str(fee_rate)) + Decimal(str(flat_fee)))
    reward_amount = q2(amount * Decimal(str(reward_rate)))
    insurance_contribution = q2(fee_amount * Decimal(str(insurance_rate)))

    # Guard: reward + insurance contribution should never exceed the fee collected
    if reward_amount + insurance_contribution > fee_amount:
        # Scale both down proportionally so the platform never pays out more
        # than it collected in commission.
        scale = fee_amount / (reward_amount + insurance_contribution) if (reward_amount + insurance_contribution) > 0 else Decimal("0")
        reward_amount = q2(reward_amount * scale)
        insurance_contribution = q2(insurance_contribution * scale)

    platform_net = q2(fee_amount - reward_amount - insurance_contribution)
    return FeeSplit(
        fee_amount=fee_amount,
        reward_amount=reward_amount,
        insurance_contribution=insurance_contribution,
        platform_net=platform_net,
    )
