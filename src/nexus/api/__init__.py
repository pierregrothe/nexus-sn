# src/nexus/api/__init__.py
# Anthropic API layer public exports.
# Author: Pierre Grothe
# Date: 2026-05-07
"""Anthropic API client with prompt caching and tool registry."""

from nexus.api.client import AnthropicClient, AnthropicClientProtocol, ModelTier
from nexus.api.errors import AnthropicError
from nexus.api.logging_config import configure_logging
from nexus.api.tool_registry import ToolRegistry

__all__ = [
    "AnthropicClient",
    "AnthropicClientProtocol",
    "AnthropicError",
    "ModelTier",
    "ToolRegistry",
    "configure_logging",
]
