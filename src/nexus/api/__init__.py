# src/nexus/api/__init__.py
# Anthropic API layer public exports.
# Author: Pierre Grothe
# Date: 2026-05-07
"""LLM client layer backed by claude-agent-sdk."""

from nexus.api.agent_client import AgentClient, AgentClientProtocol
from nexus.api.errors import AnthropicError
from nexus.api.logging_config import configure_logging

__all__ = [
    "AgentClient",
    "AgentClientProtocol",
    "AnthropicError",
    "configure_logging",
]
