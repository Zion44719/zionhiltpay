"""Transfers to other Nigerian banks: bank list, account-name lookup, and the transfer itself."""
import re
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_client_ip, get_current_user
from app.api.wallet import _require_pin_ok
from app.core import nuban
from app.core.config import settings
from app.core.database import get_db
from app.core.limiter import limiter
from app.models.user import User
from app.schemas.wallet import TransactionOut
from app.services.banks import AccountNotFound, ProviderUnavailable, get_bank_provider
from app.services.ledger import q2
from app.services.payouts import perform_bank_payout

router = APIRouter(prefix="/api/banks", tags=["banks"])

_ACCOUNT_RE = re.compile(r"^\d{10}$")
_REF_RE = re.compile(r"^[A-Za-z0-9_\-]{8,64}$")


class BankTransferRequest(BaseModel):
    bank_code: str
    account_number: str
    amount: float
    pin: str
    narration: str | None = None
    client_reference: str | None = None   # a random id the app generates once per form: makes retries safe

    @field_validator("account_number")
    @classmethod
    def _acct(cls, v: str) -> str:
        v = (v or "").strip()
        if not _ACCOUNT_RE.fullmatch(v):
            raise ValueError("Account number must be exactly 10 digits")
        return v

    @field_validator("bank_code")
    @classmethod
    def _bank(cls, v: str) -> str:
        v = (v or "").strip()
        if not v.isdigit() or not 3 <= len(v) <= 6:
            raise ValueError("Invalid bank")
        return v

    @field_validator("amount")
    @classmethod
    def _amount(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Amount must be greater than zero")
        return round(v, 2)

    @field_validator("client_reference")
    @classmethod
    def _ref(cls, v):
        if v is not None and not _REF_RE.fullmatch(v):
            raise ValueError("client_reference must be 8-64 letters, digits, - or _")
        return v

    @field_validator("narration")
    @classmethod
    def _narr(cls, v):
        return v.strip()[:120] if v else v


async def _banks_or_503() -> list[dict]:
    try:
        return await get_bank_provider().list_banks()
    except ProviderUnavailable as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"The bank list is unavailable right now. {exc}")


async def _resolve(bank_code: str, account_number: str) -> dict:
    """Validate, then resolve. The server is authoritative about the account name: the client's copy is never trusted."""
    if not _ACCOUNT_RE.fullmatch(account_number or ""):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Account number must be exactly 10 digits")
    banks = await _banks_or_503()
    bank = next((b for b in banks if b["code"] == bank_code), None)
    if bank is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown bank")
    if nuban.is_valid_nuban(bank_code, account_number) is False:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"That account number doesn't look right for {bank['name']}. Check the number and the bank.")
    try:
        found = await get_bank_provider().resolve_account(bank_code, account_number)
    except AccountNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "We couldn't find an account with those details")
    except ProviderUnavailable:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Account lookup is unavailable right now. Please try again shortly.")
    return {"account_name": found["account_name"], "account_number": account_number,
            "bank_code": bank_code, "bank_name": bank["name"]}


@router.get("")
async def list_banks(user: User = Depends(get_current_user)):
    provider = get_bank_provider()
    banks = await _banks_or_503()
    out = {
        "mode": provider.mode,
        "banks": [{"name": b["name"], "code": b["code"], "checkable": nuban.institution_code_6(b["code"]) is not None} for b in banks],
    }
    if hasattr(provider, "demo_accounts"):
        out["demo_accounts"] = provider.demo_accounts()
    return out


@router.get("/suggest")
@limiter.limit(settings.RATE_LIMIT_LOOKUP)
async def suggest_banks(request: Request, account_number: str, user: User = Depends(get_current_user)):
    """Which banks could this account number belong to? (CBN NUBAN check digit.) Usually 2 to 4 banks."""
    if not _ACCOUNT_RE.fullmatch((account_number or "").strip()):
        return {"banks": []}
    banks = await _banks_or_503()
    return {"banks": [{"name": b["name"], "code": b["code"]} for b in nuban.candidate_banks(account_number.strip(), banks)]}


@router.get("/resolve")
@limiter.limit(settings.RATE_LIMIT_LOOKUP)
async def resolve_account(request: Request, bank_code: str, account_number: str, user: User = Depends(get_current_user)):
    """Name enquiry: who owns this account? Shown to the sender before they enter their PIN."""
    return await _resolve(bank_code.strip(), account_number.strip())


@router.post("/transfer", status_code=status.HTTP_201_CREATED)
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def bank_transfer(request: Request, payload: BankTransferRequest, db: AsyncSession = Depends(get_db),
                        user: User = Depends(get_current_user)):
    _require_pin_ok(user, payload.pin)
    beneficiary = await _resolve(payload.bank_code, payload.account_number)
    name, bank_name = beneficiary["account_name"], beneficiary["bank_name"]
    txn, replayed = await perform_bank_payout(
        db, user=user, amount=q2(Decimal(str(payload.amount))), bank_code=payload.bank_code,
        account_number=payload.account_number,
        narration=payload.narration or f"Transfer to {name} ({bank_name})",
        meta={"kind": "bank_transfer", "beneficiary_name": name, "bank_name": bank_name,
              "bank_code": payload.bank_code, "account_last4": payload.account_number[-4:]},
        ip=get_client_ip(request), audit_name="BANK_TRANSFER", client_reference=payload.client_reference,
    )
    out = TransactionOut.model_validate(txn).model_dump(mode="json")
    out.update({"beneficiary_name": name, "bank_name": bank_name, "account_last4": payload.account_number[-4:], "replayed": replayed})
    return out
