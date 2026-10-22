"""
AI agent endpoints. All agents are read-only; see services/agent/tools.py.
"""
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_client_ip, get_current_admin, get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.limiter import limiter
from app.models.device import InsuranceClaim
from app.models.fraud import FraudFlag
from app.models.user import User
from app.services.agent.llm import AgentUnavailable, agent_enabled
from app.services.agent.runner import run_agent
from app.services.agent.tools import AgentContext, compute_spending_summary
from app.services.audit import log_action

router = APIRouter(prefix="/api/agent", tags=["agent"])


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=4000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    history: list[Turn] = Field(default_factory=list, max_length=40)


class InsightsRequest(BaseModel):
    days: int = Field(default=30, ge=1, le=365)


class AgentReply(BaseModel):
    reply: str
    tools_used: list[str]


class InsightsReply(BaseModel):
    days: int
    summary: dict
    narrative: str | None = None  # None when the AI is disabled or unavailable


async def _run(request: Request, db: AsyncSession, user: User, kind: str, message: str,
               history: list[dict] | None, audit_action: str, extra: dict | None = None):
    if not agent_enabled():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "The AI assistant isn't enabled on this server.")
    try:
        result = await run_agent(AgentContext(db=db, user=user), kind, message, history)
    except AgentUnavailable as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))
    await log_action(
        db, audit_action, actor_user_id=str(user.id), actor_role=user.role,
        ip_address=get_client_ip(request),
        details={"agent": kind, "tools_used": result.tools_used, "message_chars": len(message), **(extra or {})},
    )
    await db.commit()
    return result


@router.get("/status")
async def agent_status(user: User = Depends(get_current_user)):
    return {"enabled": agent_enabled()}


@router.post("/chat", response_model=AgentReply)
@limiter.limit(settings.RATE_LIMIT_AGENT)
async def assistant_chat(request: Request, payload: ChatRequest,
                         db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    res = await _run(request, db, user, "assistant", payload.message,
                     [t.model_dump() for t in payload.history], "AGENT_ASSISTANT_CHAT")
    return AgentReply(reply=res.reply, tools_used=res.tools_used)


@router.post("/insights", response_model=InsightsReply)
@limiter.limit(settings.RATE_LIMIT_AGENT)
async def spending_insights(request: Request, payload: InsightsRequest,
                            db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    # Numbers are computed deterministically; the model only narrates them.
    summary = await compute_spending_summary(db, user.id, payload.days)
    try:
        res = await _run(request, db, user, "insights",
                         f"Summarize my activity for the last {payload.days} days.", None,
                         "AGENT_INSIGHTS", {"days": payload.days})
    except HTTPException as exc:
        if exc.status_code in (status.HTTP_502_BAD_GATEWAY, status.HTTP_503_SERVICE_UNAVAILABLE):
            # The numbers don't need the model, so still return them.
            return InsightsReply(days=payload.days, summary=summary, narrative=None)
        raise
    return InsightsReply(days=payload.days, summary=summary, narrative=res.reply)


@router.post("/admin/chat", response_model=AgentReply)
@limiter.limit(settings.RATE_LIMIT_AGENT)
async def admin_copilot_chat(request: Request, payload: ChatRequest,
                             db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    res = await _run(request, db, admin, "admin", payload.message,
                     [t.model_dump() for t in payload.history], "AGENT_ADMIN_CHAT")
    return AgentReply(reply=res.reply, tools_used=res.tools_used)


@router.post("/admin/fraud-flags/{flag_id}/triage", response_model=AgentReply)
@limiter.limit(settings.RATE_LIMIT_AGENT)
async def triage_fraud_flag(request: Request, flag_id: uuid.UUID,
                            db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    exists = (await db.execute(select(FraudFlag.id).where(FraudFlag.id == flag_id))).scalar_one_or_none()
    if exists is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Fraud flag not found")
    res = await _run(request, db, admin, "admin",
                     f"Triage fraud flag {flag_id}. Fetch its context and give your recommendation.",
                     None, "AGENT_FRAUD_TRIAGE", {"flag_id": str(flag_id)})
    return AgentReply(reply=res.reply, tools_used=res.tools_used)


@router.post("/admin/claims/{claim_id}/triage", response_model=AgentReply)
@limiter.limit(settings.RATE_LIMIT_AGENT)
async def triage_claim(request: Request, claim_id: uuid.UUID,
                       db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    exists = (await db.execute(select(InsuranceClaim.id).where(InsuranceClaim.id == claim_id))).scalar_one_or_none()
    if exists is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Claim not found")
    res = await _run(request, db, admin, "admin",
                     f"Triage insurance claim {claim_id}. Fetch its context and give your recommendation.",
                     None, "AGENT_CLAIM_TRIAGE", {"claim_id": str(claim_id)})
    return AgentReply(reply=res.reply, tools_used=res.tools_used)
