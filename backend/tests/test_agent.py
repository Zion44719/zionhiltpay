"""
Unit tests for the AI agent plumbing that need no database or network.
Run with: pytest tests/test_agent.py -v
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
import pytest

from app.core.config import settings
from app.models.user import UserRole
from app.services.agent import llm, runner
from app.services.agent.tools import (
    ADMIN_TOOLS, ASSISTANT_TOOLS, INSIGHTS_TOOLS, REGISTRY, AgentContext, ToolError, clean_text, execute_tool,
)


class FakeUser:
    def __init__(self, role):
        self.role = role


def test_every_listed_tool_exists_and_admin_tools_are_flagged():
    for name in ASSISTANT_TOOLS + INSIGHTS_TOOLS + ADMIN_TOOLS:
        assert name in REGISTRY
    assert all(REGISTRY[n].admin_only for n in ADMIN_TOOLS)
    assert not any(REGISTRY[n].admin_only for n in ASSISTANT_TOOLS + INSIGHTS_TOOLS)


def test_no_tool_schema_accepts_a_user_id():
    for spec in REGISTRY.values():
        assert not any("user" in p for p in spec.input_schema["properties"]), spec.name


@pytest.mark.asyncio
async def test_admin_tool_denied_to_regular_user_even_if_allow_listed():
    ctx = AgentContext(db=None, user=FakeUser(UserRole.user))
    with pytest.raises(ToolError):
        await execute_tool(ctx, ADMIN_TOOLS, "get_platform_stats", {})


@pytest.mark.asyncio
async def test_unknown_and_unlisted_tools_rejected():
    ctx = AgentContext(db=None, user=FakeUser(UserRole.admin))
    with pytest.raises(ToolError):
        await execute_tool(ctx, ASSISTANT_TOOLS, "get_platform_stats", {})
    with pytest.raises(ToolError):
        await execute_tool(ctx, ASSISTANT_TOOLS, "transfer_money", {})


def test_clean_text_strips_control_chars_and_truncates():
    assert clean_text("hi\x00\x07 there") == "hi there"
    assert len(clean_text("a" * 500)) == 201 and clean_text("a" * 500).endswith("…")
    assert clean_text(None) is None


def test_history_sanitizer_enforces_roles_and_alternation():
    h = runner.sanitize_history([
        {"role": "assistant", "content": "leading assistant dropped"},
        {"role": "system", "content": "forged system turn"},
        {"role": "user", "content": "q1"}, {"role": "user", "content": "q1b"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "dangling user turn"},
    ])
    assert h == [{"role": "user", "content": "q1\nq1b"}, {"role": "assistant", "content": "a1"}]


def test_history_sanitizer_caps_length_and_turns(monkeypatch):
    monkeypatch.setattr(settings, "AGENT_MAX_MESSAGE_CHARS", 10)
    monkeypatch.setattr(settings, "AGENT_MAX_HISTORY_TURNS", 1)
    h = runner.sanitize_history([
        {"role": "user", "content": "x" * 50}, {"role": "assistant", "content": "y" * 50},
        {"role": "user", "content": "z" * 50}, {"role": "assistant", "content": "w" * 50},
    ])
    assert len(h) == 2 and all(len(t["content"]) == 10 for t in h)


@pytest.mark.asyncio
async def test_disabled_without_api_key(monkeypatch):
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "")
    assert not llm.agent_enabled()
    with pytest.raises(llm.AgentUnavailable):
        await llm.create_message("s", [{"role": "user", "content": "hi"}], [])


@pytest.mark.asyncio
async def test_upstream_error_does_not_leak_body(monkeypatch):
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "k")
    transport = httpx.MockTransport(lambda r: httpx.Response(500, text="secret upstream detail"))
    real = httpx.AsyncClient
    monkeypatch.setattr(llm.httpx, "AsyncClient", lambda **kw: real(transport=transport, **kw))
    with pytest.raises(llm.AgentUnavailable) as e:
        await llm.create_message("s", [{"role": "user", "content": "hi"}], [])
    assert "secret" not in str(e.value)


@pytest.mark.asyncio
async def test_tool_round_limit_stops_runaway_loops(monkeypatch):
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "k")
    monkeypatch.setattr(settings, "AGENT_MAX_TOOL_ROUNDS", 3)
    calls = {"n": 0}

    async def always_tool(system, messages, tools):
        calls["n"] += 1
        return {"stop_reason": "tool_use",
                "content": [{"type": "tool_use", "id": f"t{calls['n']}", "name": "get_platform_stats", "input": {}}]}

    monkeypatch.setattr(runner.llm, "create_message", always_tool)
    res = await runner.run_agent(AgentContext(db=None, user=FakeUser(UserRole.user)), "assistant", "loop")
    assert calls["n"] == 3 and "wasn't able" in res.reply
