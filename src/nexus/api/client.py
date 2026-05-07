# src/nexus/api/client.py
# Anthropic SDK wrapper with prompt caching and MCP tool injection.
# Author: Pierre Grothe
# Date: 2026-05-07
"""AnthropicClient: wraps anthropic.Anthropic with caching, model auto-discovery, and retry."""

import logging
import os
import re
from collections.abc import Iterable
from datetime import datetime
from enum import StrEnum
from typing import Protocol

import anthropic
from anthropic.types import MessageParam, ToolParam

from nexus.api.errors import AnthropicError
from nexus.auth.errors import AuthError
from nexus.capabilities.registry import CapabilitySet

log = logging.getLogger(__name__)

__all__ = ["AnthropicClient", "AnthropicClientProtocol", "ModelTier"]

_MAX_RETRIES = 3
_DATE_RE = re.compile(r"-\d{8}$")


class ModelTier(StrEnum):
    """Model capability tier.

    Agents declare their tier requirement; they never reference a specific
    model version string. The actual model ID is resolved at AnthropicClient
    init via auto-discovery from client.models.list().
    """

    STANDARD = "standard"
    POWERFUL = "powerful"
    FAST = "fast"


_TIER_FAMILY: dict[ModelTier, str] = {
    ModelTier.STANDARD: "claude-sonnet-",
    ModelTier.POWERFUL: "claude-opus-",
    ModelTier.FAST: "claude-haiku-",
}

_TIER_DEFAULTS: dict[ModelTier, str] = {
    ModelTier.STANDARD: "claude-sonnet-4-6",
    ModelTier.POWERFUL: "claude-opus-4-7",
    ModelTier.FAST: "claude-haiku-4-5",
}

_TIER_ENV: dict[ModelTier, str] = {
    ModelTier.STANDARD: "NEXUS_MODEL_STANDARD",
    ModelTier.POWERFUL: "NEXUS_MODEL_POWERFUL",
    ModelTier.FAST: "NEXUS_MODEL_FAST",
}


class _ModelInfo(Protocol):
    """Minimal interface for a single model entry from models.list()."""

    id: str
    created_at: datetime


class _ModelsList(Protocol):
    """Minimal duck-typed interface for the models listing accessor."""

    def list(self) -> Iterable[_ModelInfo]:
        """Return available model entries."""
        ...


class _ModelDiscoveryClient(Protocol):
    """Duck-typed interface required by _discover_model."""

    @property
    def models(self) -> _ModelsList:
        """Provide models.list() access."""
        ...


def _discover_model(client: _ModelDiscoveryClient, tier: ModelTier) -> str:
    """Return the newest available model ID for the given tier.

    Resolution order: env var override, auto-discover via API, hardcoded fallback.

    Args:
        client: anthropic.Anthropic instance (or duck-typed fake for tests).
        tier: Desired model capability tier.

    Returns:
        Model ID string suitable for the messages.create() call.
    """
    env_val = os.environ.get(_TIER_ENV[tier])
    if env_val:
        return env_val
    prefix = _TIER_FAMILY[tier]
    try:
        candidates = sorted(
            [
                m
                for m in client.models.list()
                if m.id.startswith(prefix) and not _DATE_RE.search(m.id) and "preview" not in m.id
            ],
            key=lambda m: m.created_at,
            reverse=True,
        )
        if candidates:
            return str(candidates[0].id)
    except Exception:
        log.warning("model discovery failed for tier=%s; using fallback", tier)
    return _TIER_DEFAULTS[tier]


class AnthropicClientProtocol(Protocol):
    """Interface for the Anthropic API client.

    All agents and CLI commands type-hint against this Protocol.
    FakeAnthropicClient in tests/fakes/ implements it for tests.
    """

    def complete(
        self,
        messages: list[MessageParam],
        system: str,
        tools: list[ToolParam] | None = None,
        max_tokens: int = 8192,
    ) -> anthropic.types.Message:
        """Send a completion request.

        Args:
            messages: Conversation history.
            system: System prompt text.
            tools: Anthropic-format tool definitions.
            max_tokens: Maximum tokens in the response.

        Returns:
            Raw anthropic.types.Message response.
        """
        ...


class AnthropicClient:
    """Anthropic API wrapper with prompt caching and capability-aware tools.

    Args:
        api_key: Claude Enterprise API key.
        capabilities: Session capability set from startup probe.
        tier: Model capability tier (default STANDARD).
        _sdk_client: Injectable anthropic.Anthropic instance (tests only).
    """

    def __init__(
        self,
        api_key: str,
        capabilities: CapabilitySet,
        tier: ModelTier = ModelTier.STANDARD,
        _sdk_client: anthropic.Anthropic | None = None,
    ) -> None:
        """Initialize with API key, capabilities, and model tier."""
        self._client = _sdk_client or anthropic.Anthropic(api_key=api_key, max_retries=_MAX_RETRIES)
        self._capabilities = capabilities
        self._model = _discover_model(self._client, tier)
        log.info("AnthropicClient initialised: tier=%s model=%s", tier, self._model)

    def complete(
        self,
        messages: list[MessageParam],
        system: str,
        tools: list[ToolParam] | None = None,
        max_tokens: int = 8192,
    ) -> anthropic.types.Message:
        """Send a completion request with prompt caching enabled.

        The system prompt is wrapped with cache_control ephemeral on every call
        to enable cross-turn caching when the system prompt is identical.

        Args:
            messages: Conversation history.
            system: System prompt text (cached per session).
            tools: Anthropic-format tool definitions.
            max_tokens: Maximum tokens in the response.

        Returns:
            Raw anthropic.types.Message response.

        Raises:
            AuthError: When the API key is invalid or expired.
            AnthropicError: For other API status errors (4xx/5xx).
        """
        log.debug("completion: model=%s messages=%d", self._model, len(messages))
        try:
            msg = self._client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                system=[
                    {
                        "type": "text",
                        "text": system,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=messages,
                tools=tools or [],
            )
        except anthropic.AuthenticationError as exc:
            raise AuthError(
                "anthropic",
                "api_key",
                "Run 'nexus setup' to reconfigure your API key",
            ) from exc
        except anthropic.APIStatusError as exc:
            raise AnthropicError(exc.status_code, str(exc)) from exc
        u = msg.usage
        log.info(
            "completion done: in=%d out=%d cache_write=%d cache_read=%d model=%s",
            u.input_tokens,
            u.output_tokens,
            getattr(u, "cache_creation_input_tokens", 0),
            getattr(u, "cache_read_input_tokens", 0),
            self._model,
        )
        return msg
