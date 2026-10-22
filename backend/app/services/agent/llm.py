"""
Thin async client for the Anthropic Messages API (tool use).

The API key lives only on the backend. The frontend never talks to Anthropic
directly — it calls /api/agent/*, which runs the agent loop server-side.
"""
import httpx

from app.core.config import settings


class AgentUnavailable(Exception):
    """Agent is not configured, or the upstream model call failed."""


def agent_enabled() -> bool:
    return bool(settings.ANTHROPIC_API_KEY)


async def create_message(system: str, messages: list[dict], tools: list[dict]) -> dict:
    if not agent_enabled():
        raise AgentUnavailable("AI agent is not configured (ANTHROPIC_API_KEY is not set).")

    body = {
        "model": settings.AGENT_MODEL,
        "max_tokens": settings.AGENT_MAX_TOKENS,
        "system": system,
        "messages": messages,
    }
    if tools:
        body["tools"] = tools

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{settings.ANTHROPIC_BASE_URL.rstrip('/')}/v1/messages",
                headers={
                    "x-api-key": settings.ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json=body,
            )
    except httpx.HTTPError as exc:
        raise AgentUnavailable(f"Could not reach the AI service: {exc.__class__.__name__}") from exc

    if resp.status_code != 200:
        # Don't leak upstream error bodies (could echo request content) to end users.
        raise AgentUnavailable(f"AI service returned HTTP {resp.status_code}.")
    return resp.json()
