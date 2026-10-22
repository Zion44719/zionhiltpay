"""
Ledger service — the single place in the codebase allowed to move money.

Every balance change happens as a *balanced* set of ledger_entries tied to
one transactions row: total debits == total credits, always, enforced here.
No other service should mutate `accounts.balance` directly.

Convention used throughout ZionhiltPay:
  - DEBIT  a wallet  => money LEAVES that wallet
  - CREDIT a wallet   => money ENTERS that wallet
(This mirrors how the platform, not the customer, reads its own books —
 asset accounts increase on debit from the platform's ledger perspective
 is avoided here in favor of the simpler mental model: debit = decrease
 for wallet-type accounts, credit = increase. This is documented and
 applied consistently by `apply_entry` below.)
"""
import uuid
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account, AccountType
from app.models.transaction import Transaction, LedgerEntry, TransactionType, TransactionStatus
from app.core.security import generate_reference


class InsufficientFundsError(Exception):
    pass


class LedgerImbalanceError(Exception):
    pass


def q2(value) -> Decimal:
    """Round to 2 decimal places, bankers-safe for currency math."""
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


async def get_or_create_account(
    db: AsyncSession, account_type: AccountType, user_id: Optional[uuid.UUID] = None, currency: str = "NGN"
) -> Account:
    stmt = select(Account).where(
        Account.account_type == account_type,
        Account.user_id == user_id,
        Account.currency == currency,
    )
    result = await db.execute(stmt)
    account = result.scalar_one_or_none()
    if account is None:
        account = Account(
            user_id=user_id,
            account_type=account_type,
            currency=currency,
            balance=Decimal("0.00"),
            is_platform_account=(user_id is None),
        )
        db.add(account)
        await db.flush()
    return account


class LedgerService:
    """
    Usage:
        ledger = LedgerService(db)
        txn = await ledger.start_transaction(type=..., initiator_user_id=..., amount=...)
        await ledger.post(txn, account=from_acct, direction="D", amount=amount)
        await ledger.post(txn, account=to_acct, direction="C", amount=amount)
        await ledger.finalize(txn)   # verifies balance, marks completed
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self._pending_sum: dict[uuid.UUID, Decimal] = {}

    async def start_transaction(
        self,
        type: TransactionType,
        initiator_user_id: Optional[uuid.UUID] = None,
        counterparty_user_id: Optional[uuid.UUID] = None,
        amount: Decimal = Decimal("0.00"),
        fee_amount: Decimal = Decimal("0.00"),
        reward_amount: Decimal = Decimal("0.00"),
        insurance_contribution: Decimal = Decimal("0.00"),
        currency: str = "NGN",
        narration: Optional[str] = None,
        gateway_reference: Optional[str] = None,
        ip_address: Optional[str] = None,
        device_fingerprint: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> Transaction:
        txn = Transaction(
            reference=generate_reference(),
            initiator_user_id=initiator_user_id,
            counterparty_user_id=counterparty_user_id,
            type=type,
            status=TransactionStatus.processing,
            amount=q2(amount),
            fee_amount=q2(fee_amount),
            reward_amount=q2(reward_amount),
            insurance_contribution=q2(insurance_contribution),
            currency=currency,
            narration=narration,
            gateway_reference=gateway_reference,
            ip_address=ip_address,
            device_fingerprint=device_fingerprint,
            meta=metadata or {},
        )
        self.db.add(txn)
        await self.db.flush()
        self._pending_sum[txn.id] = Decimal("0.00")
        return txn

    async def post(self, txn: Transaction, account: Account, direction: str, amount) -> LedgerEntry:
        """Post a single leg. direction: 'D' (decrease) or 'C' (increase)."""
        amount = q2(amount)
        if amount <= 0:
            raise ValueError("Ledger entry amount must be positive")

        current_balance = Decimal(str(account.balance))
        if direction == "D":
            new_balance = current_balance - amount
            if new_balance < 0 and account.account_type == AccountType.user_wallet:
                raise InsufficientFundsError(f"Insufficient balance in account {account.id}")
            self._pending_sum[txn.id] = self._pending_sum.get(txn.id, Decimal("0.00")) - amount
        elif direction == "C":
            new_balance = current_balance + amount
            self._pending_sum[txn.id] = self._pending_sum.get(txn.id, Decimal("0.00")) + amount
        else:
            raise ValueError("direction must be 'D' or 'C'")

        account.balance = new_balance
        entry = LedgerEntry(
            transaction_id=txn.id,
            account_id=account.id,
            direction=direction,
            amount=amount,
            balance_after=new_balance,
        )
        self.db.add(entry)
        await self.db.flush()
        return entry

    async def finalize(self, txn: Transaction) -> Transaction:
        """Verify the transaction's entries balance to zero (debits == credits),
        then mark it completed. Raises LedgerImbalanceError otherwise."""
        net = self._pending_sum.get(txn.id, Decimal("0.00"))
        if net != Decimal("0.00"):
            raise LedgerImbalanceError(
                f"Transaction {txn.reference} does not balance (net={net}). Rolling back."
            )
        from datetime import datetime, timezone
        txn.status = TransactionStatus.completed
        txn.completed_at = datetime.now(timezone.utc)
        await self.db.flush()
        return txn

    async def fail(self, txn: Transaction, reason: str = "") -> Transaction:
        txn.status = TransactionStatus.failed
        if reason:
            txn.meta = {**(txn.meta or {}), "failure_reason": reason}
        await self.db.flush()
        return txn
