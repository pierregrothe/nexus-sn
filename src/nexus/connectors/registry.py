# nexus/connectors/registry.py
# ConnectorRegistry: discovers and manages loaded connectors.
# Author: Pierre Grothe
# Date: 2026-05-07

"""ConnectorRegistry: runtime connector management."""

import logging
from typing import Any

from nexus.connectors.base import ConnectorProtocol, Tool, ToolResult

log = logging.getLogger(__name__)

__all__ = ["ConnectorRegistry"]


class ConnectorRegistry:
    """Manages all active connectors and their tools.

    Connectors are registered at startup. The registry merges their
    tool lists for the Anthropic API call.
    """

    def __init__(self) -> None:
        """Initialize empty connector registry."""
        self._connectors: dict[str, ConnectorProtocol] = {}

    def register(self, connector: ConnectorProtocol) -> None:
        """Register a connector.

        Args:
            connector: A ConnectorProtocol implementation.
        """
        self._connectors[connector.name] = connector
        log.info("connector registered: name=%s tools=%d", connector.name, len(connector.tools()))

    def all_tools(self) -> list[Tool]:
        """Return the merged tool list from all registered connectors.

        Returns:
            All tools from all connectors, deduplicated by name.
        """
        seen: set[str] = set()
        tools: list[Tool] = []
        for connector in self._connectors.values():
            for tool in connector.tools():
                if tool.name not in seen:
                    tools.append(tool)
                    seen.add(tool.name)
        return tools

    async def call(self, tool_name: str, **kwargs: Any) -> ToolResult:
        """Route a tool call to the appropriate connector.

        Args:
            tool_name: The tool to call.
            **kwargs: Tool parameters.

        Returns:
            ToolResult from the owning connector.

        Raises:
            KeyError: When no registered connector owns the tool.
        """
        for connector in self._connectors.values():
            for tool in connector.tools():
                if tool.name == tool_name:
                    return await connector.call(tool_name, **kwargs)
        raise KeyError(f"No connector handles tool: {tool_name!r}")

    def connector_names(self) -> list[str]:
        """Return the names of all registered connectors.

        Returns:
            List of connector name strings.
        """
        return list(self._connectors.keys())
