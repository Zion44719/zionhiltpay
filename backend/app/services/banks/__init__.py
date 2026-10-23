"""
Bank directory + account-name lookup ("name enquiry") for transfers to other Nigerian banks.

Two providers sit behind one interface:
  mock      (default) a built-in sample bank list and deterministic fake account names, so the whole flow
            works offline. The names are made up.
  paystack  the live bank list and real account-name resolution through Paystack's API
            (set BANK_PROVIDER=paystack and PAYSTACK_SECRET_KEY).
The money movement itself is still done by the mock payment gateway (see services/payment_gateway.py):
a live payout needs a provider payout API plus webhooks and reconciliation, which is a separate piece of work.
"""
from typing import Optional, Protocol

from app.core.config import settings


class BankError(Exception):
    pass


class AccountNotFound(BankError):
    pass


class ProviderUnavailable(BankError):
    pass


class BankProvider(Protocol):
    mode: str

    async def list_banks(self) -> list[dict]: ...
    async def resolve_account(self, bank_code: str, account_number: str) -> dict: ...


_provider: Optional[BankProvider] = None


def get_bank_provider() -> BankProvider:
    global _provider
    if _provider is None:
        if settings.BANK_PROVIDER == "paystack":
            from app.services.banks.paystack import PaystackBankProvider
            _provider = PaystackBankProvider()
        else:
            from app.services.banks.mock import MockBankProvider
            _provider = MockBankProvider()
    return _provider


def set_bank_provider(provider: Optional[BankProvider]) -> None:
    """Swap the provider (tests use this); None resets to the configured one."""
    global _provider
    _provider = provider
