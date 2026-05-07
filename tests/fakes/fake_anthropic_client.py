# tests/fakes/fake_anthropic_client.py
# Fake AnthropicClient for use in tests.
# Author: Pierre Grothe
# Date: 2026-05-07
"""FakeAnthropicClient: implements AnthropicClientProtocol with canned responses."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from anthropic.types import MessageParam, ToolParam

__all__ = ["CANNED_MESSAGE", "FakeAnthropicClient"]

CANNED_MESSAGE = SimpleNamespace(
    content=[SimpleNamespace(type="text", text="ok")],
    stop_reason="end_turn",
    usage=SimpleNamespace(
        input_tokens=10,
        output_tokens=5,
        cache_creation_input_tokens=0,
        cache_read_input_tokens=0,
    ),
)


@dataclass(slots=True)
class FakeAnthropicClient:
    """Test double for AnthropicClientProtocol.

    Returns CANNED_MESSAGE on every complete() call and records all
    call arguments in self.calls for assertion in tests.
    """

    calls: list[dict[str, Any]] = field(default_factory=list)

    def complete(
        self,
        messages: list[MessageParam],
        system: str,
        tools: list[ToolParam] | None = None,
        max_tokens: int = 8192,
    ) -> object:
        """Record call arguments and return CANNED_MESSAGE.

        Args:
            messages: Conversation history passed by the caller.
            system: System prompt passed by the caller.
            tools: Tool definitions passed by the caller.
            max_tokens: Max tokens requested by the caller.

        Returns:
            CANNED_MESSAGE (SimpleNamespace). Not anthropic.types.Message --
            callers should use the fake only via AnthropicClientProtocol.
        """
        self.calls.append({
            "messages": messages,
            "system": system,
            "tools": tools,
            "max_tokens": max_tokens,
        })
        return CANNED_MESSAGE
