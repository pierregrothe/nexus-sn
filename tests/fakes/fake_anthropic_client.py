# tests/fakes/fake_anthropic_client.py
# Fake AnthropicClient for use in tests.
# Author: Pierre Grothe
# Date: 2026-05-07
"""FakeAnthropicClient: implements AnthropicClientProtocol with canned responses."""

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

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
        messages: list[dict[str, Any]],
        system: str,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 8192,
    ) -> object:
        """Record call arguments and return CANNED_MESSAGE.

        Args:
            messages: Conversation history passed by the caller.
            system: System prompt passed by the caller.
            tools: Tool definitions passed by the caller.
            max_tokens: Max tokens requested by the caller.

        Returns:
            CANNED_MESSAGE, a minimal Message-like namespace object.
        """
        self.calls.append({"messages": messages, "system": system, "tools": tools})
        return CANNED_MESSAGE
