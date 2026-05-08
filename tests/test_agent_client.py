# tests/test_agent_client.py
# Tests for the AgentClient and FakeAgentClient.
# Author: Pierre Grothe
# Date: 2026-05-08
"""Tests for nexus.api.agent_client."""

import pytest

from nexus.api.agent_client import AgentClient, AgentClientProtocol
from nexus.api.errors import AnthropicError
from tests.fakes.fake_agent_client import FakeAgentClient


async def test_fake_agent_client_records_calls() -> None:
    client = FakeAgentClient()
    result = await client.complete("hello", system="You are terse.")
    assert result == "ok"
    assert client.calls == [
        {"prompt": "hello", "system": "You are terse.", "model": None, "max_turns": 1},
    ]


async def test_fake_agent_client_returns_canned_response() -> None:
    client = FakeAgentClient(canned_response="custom")
    assert await client.complete("anything") == "custom"


async def test_fake_agent_client_raises_side_effect() -> None:
    client = FakeAgentClient(side_effect=AnthropicError(429, "rate limit"))
    with pytest.raises(AnthropicError):
        await client.complete("hello")


async def test_fake_agent_client_records_all_options() -> None:
    client = FakeAgentClient()
    await client.complete("p", system="s", model="claude-sonnet-4-6", max_turns=5)
    assert client.calls[0] == {
        "prompt": "p",
        "system": "s",
        "model": "claude-sonnet-4-6",
        "max_turns": 5,
    }


def test_agent_client_protocol_satisfied_by_real_client() -> None:
    """Static check: AgentClient structurally implements AgentClientProtocol."""
    client: AgentClientProtocol = AgentClient()
    assert callable(client.complete)


def test_agent_client_protocol_satisfied_by_fake() -> None:
    """Static check: FakeAgentClient structurally implements AgentClientProtocol."""
    fake: AgentClientProtocol = FakeAgentClient()
    assert callable(fake.complete)
