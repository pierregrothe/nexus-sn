# nexus/connectors/__init__.py
# Connector layer public exports.
# Author: Pierre Grothe
# Date: 2026-05-07

"""Connector plugin system. ServiceNow REST is the built-in connector."""

from nexus.connectors.base import ConnectorProtocol, ToolResult
from nexus.connectors.registry import ConnectorRegistry

__all__ = ["ConnectorProtocol", "ToolResult", "ConnectorRegistry"]
