# nexus/connectors/base.py
# ConnectorProtocol: interface every connector must implement.
# Author: Pierre Grothe
# Date: 2026-05-07

"""Base types for the connector plugin system."""

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

__all__ = ["ConnectorProtocol", "Tool", "ToolResult"]


@dataclass(slots=True, frozen=True)
class Tool:
    """A tool exposed by a connector.

    Attributes:
        name: Unique tool identifier, e.g. "sn_create_incident".
        description: Human-readable description for the LLM.
        parameters: JSON Schema dict for the tool's input parameters.
        connector: Name of the connector that owns this tool.
    """

    name: str
    description: str
    parameters: dict[str, Any]
    connector: str


@dataclass(slots=True)
class ToolResult:
    """Result from executing a connector tool.

    Attributes:
        tool_name: The tool that was called.
        success: True when the call succeeded.
        data: The returned data on success.
        error: Error message on failure.
    """

    tool_name: str
    success: bool
    data: dict[str, Any] | None = None
    error: str | None = None


@runtime_checkable
class ConnectorProtocol(Protocol):
    """Interface that every connector must implement.

    A connector registers its tools with the ToolRegistry and handles
    calls to those tools. The ServiceNow REST connector is built-in.
    Additional connectors (Value Melody, SSC, etc.) are optional plugins.
    """

    @property
    def name(self) -> str:
        """Unique connector identifier, e.g. 'servicenow'."""
        ...

    def tools(self) -> list[Tool]:
        """Return the list of tools this connector exposes.

        Returns:
            Tool definitions suitable for passing to the Anthropic API.
        """
        ...

    async def call(self, tool_name: str, **kwargs: Any) -> ToolResult:
        """Execute a tool call.

        Args:
            tool_name: The tool to call.
            **kwargs: Tool-specific parameters.

        Returns:
            ToolResult with success/failure status and data.
        """
        ...
