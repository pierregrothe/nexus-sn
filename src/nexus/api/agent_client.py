# src/nexus/api/agent_client.py
# AgentClient: async LLM client backed by claude-agent-sdk.
# Author: Pierre Grothe
# Date: 2026-05-08
"""AgentClient: routes LLM calls through claude-agent-sdk.

Auth is handled internally by claude-agent-sdk's session_resume:
  - ANTHROPIC_API_KEY env var
  - CLAUDE_CODE_OAUTH_TOKEN env var
  - $CLAUDE_CONFIG_DIR/.credentials.json (or ~/.claude/.credentials.json)
  - macOS Keychain "Claude Code-credentials"

NEXUS callers do not pass credentials. They construct AgentClient() and call
await client.complete(prompt, ...).
"""

from typing import Protocol

from claude_agent_sdk import ClaudeAgentOptions, query
from claude_agent_sdk.types import AssistantMessage, ResultMessage, TextBlock

from nexus.api.errors import AnthropicError

__all__ = ["AgentClient", "AgentClientProtocol"]


class AgentClientProtocol(Protocol):
    """Async LLM client interface for NEXUS agents and CLI commands.

    Implementations route LLM calls through claude-agent-sdk, which handles
    authentication automatically. Agents and CLI commands type-hint against
    this Protocol so they can accept FakeAgentClient in tests.
    """

    async def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        model: str | None = None,
        max_turns: int = 1,
    ) -> str:
        """Send a prompt and return the final assistant text.

        Args:
            prompt: User-facing prompt sent to the agent.
            system: Optional system prompt prepended by Agent SDK.
            model: Optional model ID. If None, Agent SDK picks the default.
            max_turns: Maximum agent turns (tool-call rounds). Default 1.

        Returns:
            Concatenated text from all AssistantMessage TextBlocks.

        Raises:
            AnthropicError: When the underlying API returns an error.
        """
        ...


class AgentClient:
    """LLM client backed by claude-agent-sdk."""

    async def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        model: str | None = None,
        max_turns: int = 1,
    ) -> str:
        """See AgentClientProtocol.complete."""
        options = ClaudeAgentOptions(
            system_prompt=system,
            model=model,
            max_turns=max_turns,
        )
        text_parts: list[str] = []
        result_message: ResultMessage | None = None
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        text_parts.append(block.text)
            elif isinstance(message, ResultMessage):
                result_message = message
        if result_message is not None and result_message.is_error:
            raise AnthropicError(0, result_message.result or "agent sdk error")
        return "".join(text_parts)
