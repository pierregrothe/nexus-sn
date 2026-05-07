# nexus/api/tool_registry.py
# Maps tool names to Anthropic-format tool definitions.
# Author: Pierre Grothe
# Date: 2026-05-07
"""ToolRegistry: builds the tool list passed to the Anthropic API."""

import logging
from typing import Any

from nexus.connectors.registry import ConnectorRegistry

log = logging.getLogger(__name__)

__all__ = ["ToolRegistry"]


class ToolRegistry:
    """Converts connector tools to Anthropic API tool format.

    Args:
        connectors: Registry of active connectors.
    """

    def __init__(self, connectors: ConnectorRegistry) -> None:
        self._connectors = connectors

    def as_anthropic_tools(self) -> list[dict[str, Any]]:
        """Return all connector tools in Anthropic API format.

        Returns:
            List of tool dicts with name, description, and input_schema.
        """
        tools = []
        for tool in self._connectors.all_tools():
            tools.append({
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.parameters,
            })
        log.debug("tool registry: %d tools assembled", len(tools))
        return tools
