"""
Read-only tools exposed to the AI agents.

Security model (important):
  * Every tool is READ-ONLY. No tool can move money, freeze accounts, approve
    claims, or change any state. Those actions stay behind PIN / admin flows.
  * Tools never accept a user id from the model. The acting user comes from the
    authenticated request (AgentContext), so the model cannot be talked into
    reading another customer's data.
  * Each agent run is given an explicit allow-list of tool names; anything else
    the model asks for is rejected, and admin-only tools are re-checked against
    the caller's role at execution time.
  * User-authored free text (transfer narrations, claim descriptions) is
    sanitized and truncated here, and the system prompts tell the model to
    treat it as untrusted data, never as instructions.
"""
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Awaitable, Callable

from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account, AccountType
from app.models.config import PlatformConfig
from app.models.device import Device, InsuranceClaim
from app.models.fraud import FraudFlag
from app.models.transaction import Transaction, TransactionStatus, TransactionType
from app.models.user import User, UserRole
from app.services.rewards import compute_fee_split


class ToolError(Exception):
    """Raised for bad tool input or a disallowed tool; reported back to the model."""


@dataclass
class AgentContext:
    db: AsyncSession
    user: User

    @property
    def is_admin(self) -> bool:
        return self.user.role in (UserRole.admin, UserRole.super_admin)


_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def clean_text(value: str | None, limit: int = 200) -> str | None:
    """Strip control characters and truncate user-authored text."""
    if value is None:
        return None
    value = _CONTROL.sub("", value).strip()
    return value[:limit] + ("…" if len(value) > limit else "")


def _f(x) -> float:
    return float(x or 0)


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _uuid(value: Any, label: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError):
        raise ToolError(f"{label} must be a valid UUID")


def _int(value: Any, default: int, lo: int, hi: int) -> int:
    try:
        n = int(value) if value is not None else default
    except (ValueError, TypeError):
        raise ToolError("Expected an integer argument")
    return max(lo, min(hi, n))


def _txn_view(t: Transaction, viewer_id: uuid.UUID) -> dict:
    is_initiator = t.initiator_user_id == viewer_id
    if is_initiator:
        direction = "in" if t.type.value in ("deposit", "insurance_claim_payout", "reward_credit") else "out"
    else:
        direction = "in"
    # Fee, cashback and insurance accrual belong to the initiator. A recipient
    # paid no fee and earned nothing from this transaction, so never show them
    # the sender's figures (privacy, and it would make the assistant misreport).
    return {
        "reference": t.reference,
        "type": t.type.value,
        "status": t.status.value,
        "direction": direction,
        "amount": _f(t.amount),
        "fee": _f(t.fee_amount) if is_initiator else 0.0,
        "reward_earned": _f(t.reward_amount) if is_initiator else 0.0,
        "insurance_accrued": _f(t.insurance_contribution) if is_initiator else 0.0,
        "narration": clean_text(t.narration),  # user-authored: untrusted
        "created_at": _iso(t.created_at),
    }


# ----------------------------------------------------------------------------
# Customer tools (scoped to the authenticated user)
# ----------------------------------------------------------------------------
async def get_balances(ctx: AgentContext, args: dict) -> dict:
    rows = (await ctx.db.execute(
        select(Account.account_type, Account.balance).where(Account.user_id == ctx.user.id)
    )).all()
    by_type = {r.account_type.value: _f(r.balance) for r in rows}
    return {
        "currency": "NGN",
        "wallet_balance": by_type.get("user_wallet", 0.0),
        "reward_balance": by_type.get("user_reward", 0.0),
        "device_insurance_balance": by_type.get("user_insurance", 0.0),
    }


async def list_recent_transactions(ctx: AgentContext, args: dict) -> dict:
    limit = _int(args.get("limit"), 10, 1, 20)
    stmt = select(Transaction).where(
        or_(Transaction.initiator_user_id == ctx.user.id, Transaction.counterparty_user_id == ctx.user.id)
    )
    ttype = args.get("type")
    if ttype:
        try:
            ttype = TransactionType(str(ttype))
        except ValueError:
            raise ToolError("type must be one of: " + ", ".join(t.value for t in TransactionType))
        stmt = stmt.where(Transaction.type == ttype)
    rows = (await ctx.db.execute(stmt.order_by(Transaction.created_at.desc()).limit(limit))).scalars().all()
    return {"transactions": [_txn_view(t, ctx.user.id) for t in rows]}


async def get_transaction(ctx: AgentContext, args: dict) -> dict:
    ref = str(args.get("reference", "")).strip()[:40]
    if not ref:
        raise ToolError("reference is required")
    t = (await ctx.db.execute(
        select(Transaction).where(
            Transaction.reference == ref,
            or_(Transaction.initiator_user_id == ctx.user.id, Transaction.counterparty_user_id == ctx.user.id),
        )
    )).scalar_one_or_none()
    if t is None:
        # Same answer whether it doesn't exist or belongs to someone else.
        raise ToolError("No transaction with that reference was found on this account")
    return _txn_view(t, ctx.user.id)


async def _config(db: AsyncSession) -> PlatformConfig:
    cfg = (await db.execute(select(PlatformConfig).where(PlatformConfig.id == 1))).scalar_one_or_none()
    return cfg or PlatformConfig()


async def explain_fee(ctx: AgentContext, args: dict) -> dict:
    try:
        amount = Decimal(str(args.get("amount")))
    except Exception:
        raise ToolError("amount must be a number")
    if amount <= 0 or amount > Decimal("100000000"):
        raise ToolError("amount must be positive")
    kind = args.get("kind", "transfer")
    if kind not in ("transfer", "withdrawal"):
        raise ToolError("kind must be 'transfer' or 'withdrawal'")

    cfg = await _config(ctx.db)
    if kind == "transfer":
        split = compute_fee_split(amount, Decimal(str(cfg.transaction_fee_rate)),
                                  Decimal(str(cfg.reward_rate)), Decimal(str(cfg.insurance_contribution_rate)))
    else:
        split = compute_fee_split(amount, Decimal("0"), Decimal(str(cfg.reward_rate)) / 2,
                                  Decimal(str(cfg.insurance_contribution_rate)), Decimal(str(cfg.withdrawal_fee_flat)))
    return {
        "kind": kind,
        "amount": _f(amount),
        "fee_charged": _f(split.fee_amount),
        "total_debited_from_wallet": _f(amount + split.fee_amount),
        "cashback_reward_to_user": _f(split.reward_amount),
        "device_insurance_contribution_to_user": _f(split.insurance_contribution),
        "platform_keeps": _f(split.platform_net),
    }


async def list_devices(ctx: AgentContext, args: dict) -> dict:
    rows = (await ctx.db.execute(
        select(Device).where(Device.user_id == ctx.user.id).order_by(Device.registered_at.desc()).limit(20)
    )).scalars().all()
    return {"devices": [{
        "device_type": d.device_type.value, "brand": clean_text(d.brand, 80), "model": clean_text(d.model, 80),
        "estimated_value": _f(d.estimated_value), "status": d.status.value, "registered_at": _iso(d.registered_at),
    } for d in rows]}


async def list_claims(ctx: AgentContext, args: dict) -> dict:
    rows = (await ctx.db.execute(
        select(InsuranceClaim).where(InsuranceClaim.user_id == ctx.user.id)
        .order_by(InsuranceClaim.created_at.desc()).limit(20)
    )).scalars().all()
    return {"claims": [{
        "claim_type": c.claim_type, "requested_amount": _f(c.requested_amount),
        "approved_amount": _f(c.approved_amount) if c.approved_amount is not None else None,
        "status": c.status, "created_at": _iso(c.created_at),
    } for c in rows]}


async def compute_spending_summary(db: AsyncSession, user_id: uuid.UUID, days: int) -> dict:
    """Deterministic aggregates. Also used directly by the insights endpoint so
    the numbers shown to the user never depend on model output."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    sent = (await db.execute(
        select(
            Transaction.type,
            func.count(Transaction.id),
            func.coalesce(func.sum(Transaction.amount), 0),
            func.coalesce(func.sum(Transaction.fee_amount), 0),
            func.coalesce(func.sum(Transaction.reward_amount), 0),
            func.coalesce(func.sum(Transaction.insurance_contribution), 0),
        ).where(
            Transaction.initiator_user_id == user_id,
            Transaction.status == TransactionStatus.completed,
            Transaction.created_at >= since,
        ).group_by(Transaction.type)
    )).all()
    by_type = {
        r[0].value: {"count": r[1], "total_amount": _f(r[2]), "fees": _f(r[3]),
                     "rewards": _f(r[4]), "insurance_accrued": _f(r[5])}
        for r in sent
    }
    recv = (await db.execute(
        select(func.count(Transaction.id), func.coalesce(func.sum(Transaction.amount), 0)).where(
            Transaction.counterparty_user_id == user_id,
            Transaction.status == TransactionStatus.completed,
            Transaction.created_at >= since,
        )
    )).one()
    return {
        "days": days,
        "by_type": by_type,
        "received_transfers": {"count": recv[0], "total_amount": _f(recv[1])},
        "total_fees_paid": round(sum(v["fees"] for v in by_type.values()), 2),
        "total_rewards_earned": round(sum(v["rewards"] for v in by_type.values()), 2),
        "total_insurance_accrued": round(sum(v["insurance_accrued"] for v in by_type.values()), 2),
    }


async def spending_summary(ctx: AgentContext, args: dict) -> dict:
    return await compute_spending_summary(ctx.db, ctx.user.id, _int(args.get("days"), 30, 1, 365))


# ----------------------------------------------------------------------------
# Admin tools (role re-checked at execution time)
# ----------------------------------------------------------------------------
async def get_platform_stats(ctx: AgentContext, args: dict) -> dict:
    db = ctx.db

    async def count(stmt):
        return (await db.execute(stmt)).scalar_one()

    async def acct_sum(t: AccountType):
        return _f((await db.execute(
            select(func.coalesce(func.sum(Account.balance), 0)).where(Account.account_type == t))).scalar_one())

    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    return {
        "total_users": await count(select(func.count(User.id))),
        "frozen_users": await count(select(func.count(User.id)).where(User.is_frozen.is_(True))),
        "total_wallet_balance": await acct_sum(AccountType.user_wallet),
        "reward_liability": await acct_sum(AccountType.user_reward),
        "insurance_liability": await acct_sum(AccountType.user_insurance),
        "platform_revenue": await acct_sum(AccountType.platform_revenue),
        "transactions_today": await count(select(func.count(Transaction.id)).where(Transaction.created_at >= today)),
        "open_fraud_flags": await count(select(func.count(FraudFlag.id)).where(FraudFlag.resolved.is_(False))),
        "pending_claims": await count(select(func.count(InsuranceClaim.id)).where(
            InsuranceClaim.status.in_(["submitted", "under_review"]))),
    }


async def list_open_fraud_flags(ctx: AgentContext, args: dict) -> dict:
    limit = _int(args.get("limit"), 10, 1, 25)
    rows = (await ctx.db.execute(
        select(FraudFlag).where(FraudFlag.resolved.is_(False)).order_by(FraudFlag.created_at.desc()).limit(limit)
    )).scalars().all()
    return {"open_flags": [{
        "flag_id": str(f.id), "rule_code": f.rule_code, "severity": f.severity.value,
        "user_id": str(f.user_id) if f.user_id else None,
        "transaction_id": str(f.transaction_id) if f.transaction_id else None,
        "details": f.details, "created_at": _iso(f.created_at),
    } for f in rows]}


async def _user_snapshot(db: AsyncSession, user_id: uuid.UUID) -> dict:
    u = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if u is None:
        return {"error": "user not found"}
    now = datetime.now(timezone.utc)
    since30 = now - timedelta(days=30)
    cnt, vol = (await db.execute(
        select(func.count(Transaction.id), func.coalesce(func.sum(Transaction.amount), 0)).where(
            Transaction.initiator_user_id == user_id, Transaction.created_at >= since30)
    )).one()
    flags_total = (await db.execute(select(func.count(FraudFlag.id)).where(FraudFlag.user_id == user_id))).scalar_one()
    flags_open = (await db.execute(select(func.count(FraudFlag.id)).where(
        FraudFlag.user_id == user_id, FraudFlag.resolved.is_(False)))).scalar_one()
    created = u.created_at if u.created_at.tzinfo else u.created_at.replace(tzinfo=timezone.utc)
    return {
        "account_age_days": round((now - created).total_seconds() / 86400, 1),
        "kyc_level": u.kyc_level, "is_frozen": u.is_frozen,
        "email_verified": u.email_verified, "phone_verified": u.phone_verified,
        "txn_count_30d": cnt, "txn_volume_30d": _f(vol),
        "fraud_flags_total": flags_total, "fraud_flags_open": flags_open,
    }


async def get_fraud_flag_context(ctx: AgentContext, args: dict) -> dict:
    fid = _uuid(args.get("flag_id"), "flag_id")
    flag = (await ctx.db.execute(select(FraudFlag).where(FraudFlag.id == fid))).scalar_one_or_none()
    if flag is None:
        raise ToolError("Fraud flag not found")
    out: dict = {"flag": {
        "rule_code": flag.rule_code, "severity": flag.severity.value, "details": flag.details,
        "resolved": flag.resolved, "created_at": _iso(flag.created_at)}}
    if flag.transaction_id:
        t = (await ctx.db.execute(select(Transaction).where(Transaction.id == flag.transaction_id))).scalar_one_or_none()
        if t:
            out["transaction"] = {
                "reference": t.reference, "type": t.type.value, "status": t.status.value,
                "amount": _f(t.amount), "narration": clean_text(t.narration),
                "created_at": _iso(t.created_at)}
    if flag.user_id:
        out["user"] = await _user_snapshot(ctx.db, flag.user_id)
        recent = (await ctx.db.execute(
            select(Transaction).where(Transaction.initiator_user_id == flag.user_id)
            .order_by(Transaction.created_at.desc()).limit(10))).scalars().all()
        out["recent_transactions"] = [
            {"type": t.type.value, "status": t.status.value, "amount": _f(t.amount), "created_at": _iso(t.created_at)}
            for t in recent]
    return out


async def get_claim_context(ctx: AgentContext, args: dict) -> dict:
    cid = _uuid(args.get("claim_id"), "claim_id")
    claim = (await ctx.db.execute(select(InsuranceClaim).where(InsuranceClaim.id == cid))).scalar_one_or_none()
    if claim is None:
        raise ToolError("Claim not found")
    device = (await ctx.db.execute(select(Device).where(Device.id == claim.device_id))).scalar_one_or_none()
    insurance_balance = (await ctx.db.execute(
        select(Account.balance).where(Account.user_id == claim.user_id,
                                      Account.account_type == AccountType.user_insurance))).scalar_one_or_none()
    prior = (await ctx.db.execute(select(func.count(InsuranceClaim.id)).where(
        InsuranceClaim.user_id == claim.user_id, InsuranceClaim.id != claim.id))).scalar_one()
    out = {
        "claim": {
            "claim_type": claim.claim_type, "status": claim.status,
            "description": clean_text(claim.description, 500),  # user-authored: untrusted
            "requested_amount": _f(claim.requested_amount), "created_at": _iso(claim.created_at)},
        "user_insurance_balance": _f(insurance_balance),
        "user_other_claims": prior,
        "user": await _user_snapshot(ctx.db, claim.user_id),
    }
    if device:
        reg = device.registered_at if device.registered_at.tzinfo else device.registered_at.replace(tzinfo=timezone.utc)
        cl = claim.created_at if claim.created_at.tzinfo else claim.created_at.replace(tzinfo=timezone.utc)
        out["device"] = {
            "device_type": device.device_type.value, "brand": clean_text(device.brand, 80),
            "model": clean_text(device.model, 80), "estimated_value": _f(device.estimated_value),
            "days_registered_before_claim": round((cl - reg).total_seconds() / 86400, 1)}
    return out


# ----------------------------------------------------------------------------
# Registry
# ----------------------------------------------------------------------------
@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict
    fn: Callable[[AgentContext, dict], Awaitable[dict]]
    admin_only: bool = False


def _schema(props: dict | None = None, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": props or {}, "required": required or []}


REGISTRY: dict[str, ToolSpec] = {s.name: s for s in [
    ToolSpec("get_balances", "Get the user's wallet, cashback reward, and device-insurance balances (NGN).",
             _schema(), get_balances),
    ToolSpec("list_recent_transactions", "List the user's most recent transactions, newest first.",
             _schema({"limit": {"type": "integer", "description": "1-20, default 10"},
                      "type": {"type": "string", "enum": ["deposit", "withdrawal", "transfer", "insurance_claim_payout"]}}),
             list_recent_transactions),
    ToolSpec("get_transaction", "Look up one of the user's transactions by its reference (e.g. ZHP-20260819-XXXXXXXX).",
             _schema({"reference": {"type": "string"}}, ["reference"]), get_transaction),
    ToolSpec("explain_fee", "Compute exactly what fee, cashback and insurance contribution a transfer or withdrawal of a given amount would produce, using the live platform rates.",
             _schema({"amount": {"type": "number"}, "kind": {"type": "string", "enum": ["transfer", "withdrawal"]}},
                     ["amount"]), explain_fee),
    ToolSpec("list_devices", "List the user's registered insurance devices.", _schema(), list_devices),
    ToolSpec("list_claims", "List the user's device insurance claims and their status.", _schema(), list_claims),
    ToolSpec("spending_summary", "Aggregate the user's completed activity over the last N days: totals by type, fees paid, rewards earned, insurance accrued, and transfers received.",
             _schema({"days": {"type": "integer", "description": "1-365, default 30"}}), spending_summary),
    ToolSpec("get_platform_stats", "Platform-wide stats: users, liabilities, revenue, open flags, pending claims.",
             _schema(), get_platform_stats, admin_only=True),
    ToolSpec("list_open_fraud_flags", "List unresolved fraud flags, newest first.",
             _schema({"limit": {"type": "integer"}}), list_open_fraud_flags, admin_only=True),
    ToolSpec("get_fraud_flag_context", "Get a fraud flag with its transaction, the user's account snapshot and recent activity.",
             _schema({"flag_id": {"type": "string"}}, ["flag_id"]), get_fraud_flag_context, admin_only=True),
    ToolSpec("get_claim_context", "Get an insurance claim with the device, the user's insurance balance, account snapshot and claim history.",
             _schema({"claim_id": {"type": "string"}}, ["claim_id"]), get_claim_context, admin_only=True),
]}

ASSISTANT_TOOLS = ["get_balances", "list_recent_transactions", "get_transaction", "explain_fee",
                   "list_devices", "list_claims", "spending_summary"]
INSIGHTS_TOOLS = ["get_balances", "spending_summary", "list_recent_transactions"]
ADMIN_TOOLS = ["get_platform_stats", "list_open_fraud_flags", "get_fraud_flag_context", "get_claim_context"]


def tool_schemas(names: list[str]) -> list[dict]:
    return [{"name": REGISTRY[n].name, "description": REGISTRY[n].description,
             "input_schema": REGISTRY[n].input_schema} for n in names]


async def execute_tool(ctx: AgentContext, allowed: list[str], name: str, args: dict) -> dict:
    spec = REGISTRY.get(name)
    if spec is None or name not in allowed:
        raise ToolError(f"Tool '{name}' is not available")
    if spec.admin_only and not ctx.is_admin:
        raise ToolError(f"Tool '{name}' is not available")
    if not isinstance(args, dict):
        raise ToolError("Tool arguments must be an object")
    async with ctx.db.begin_nested():
        return await spec.fn(ctx, args)
