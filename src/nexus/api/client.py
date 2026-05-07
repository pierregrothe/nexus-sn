# nexus/api/client.py
# Anthropic SDK wrapper with prompt caching and MCP tool injection.
# Author: Pierre Grothe
# Date: 2026-05-07
"""AnthropicClient: wraps anthropic.Anthropic with caching and retry."""

import logging
from typing import Any

import anthropic

from nexus.capabilities.registry import CapabilitySet

log = logging.getLogger(__name__)

__all__ = ["AnthropicClient"]

_DEFAULT_MODEL = "claude-opus-4-5"
_MAX_RETRIES = 3


class AnthropicClient:
    """Anthropic API wrapper with prompt caching and capability-aware tools.

    Args:
        api_key: Claude Enterprise API key.
        capabilities: Session capability set from startup probe.
        model: Model ID to use for all completions.
    """

    def __init__(
        self,
        api_key: str,
        capabilities: CapabilitySet,
        model: str = _DEFAULT_MODEL,
    ) -> None:
        self._client = anthropic.Anthropic(api_key=api_key, max_retries=_MAX_RETRIES)
        self._capabilities = capabilities
        self._model = model
        log.info("AnthropicClient initialised: model=%s", model)

    def complete(
        self,
        messages: list[dict[str, Any]],
        system: str,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 8192,
    ) -> Any:
        """Send a completion request with prompt caching enabled.

        Args:
            messages: Conversation history.
            system: System prompt (cached on first call per session).
            tools: Tool definitions to inject.
            max_tokens: Maximum tokens in the response.

        Returns:
            Raw anthropic Message response.
        """
        log.debug("completion request: model=%s messages=%d", self._model, len(messages))
        return self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=messages,
            tools=tools or [],
        )
