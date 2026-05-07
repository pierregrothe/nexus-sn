# nexus/connectors/servicenow/connector.py
# ConnectorProtocol implementation for the ServiceNow REST API.
# Author: Pierre Grothe
# Date: 2026-05-07

"""ServiceNowConnector: adapts ServiceNowClient to the ConnectorProtocol."""

import logging
from typing import Any

from nexus.connectors.base import ConnectorProtocol, Tool, ToolResult
from nexus.connectors.servicenow.client import ServiceNowClient

log = logging.getLogger(__name__)

__all__ = ["ServiceNowConnector"]


class ServiceNowConnector:
    """ConnectorProtocol implementation backed by the ServiceNow REST API.

    Args:
        client: Initialised ServiceNowClient.
    """

    def __init__(self, client: ServiceNowClient) -> None:
        self._client = client

    @property
    def name(self) -> str:
        """Return the connector identifier."""
        return "servicenow"

    def tools(self) -> list[Tool]:
        """Return the list of ServiceNow tools.

        Returns:
            Tool definitions for query, create, update, delete operations.
        """
        return [
            Tool(
                name="sn_query_table",
                description="Query a ServiceNow table with optional filters.",
                parameters={
                    "type": "object",
                    "properties": {
                        "table": {"type": "string"},
                        "query": {"type": "string", "default": ""},
                        "limit": {"type": "integer", "default": 10},
                        "fields": {"type": "string", "default": ""},
                    },
                    "required": ["table"],
                },
                connector=self.name,
            ),
            Tool(
                name="sn_create_record",
                description="Create a new record in a ServiceNow table.",
                parameters={
                    "type": "object",
                    "properties": {
                        "table": {"type": "string"},
                        "data": {"type": "object"},
                    },
                    "required": ["table", "data"],
                },
                connector=self.name,
            ),
            Tool(
                name="sn_update_record",
                description="Update an existing ServiceNow record by sys_id.",
                parameters={
                    "type": "object",
                    "properties": {
                        "table": {"type": "string"},
                        "sys_id": {"type": "string"},
                        "data": {"type": "object"},
                    },
                    "required": ["table", "sys_id", "data"],
                },
                connector=self.name,
            ),
            Tool(
                name="sn_delete_record",
                description="Delete a ServiceNow record by sys_id.",
                parameters={
                    "type": "object",
                    "properties": {
                        "table": {"type": "string"},
                        "sys_id": {"type": "string"},
                    },
                    "required": ["table", "sys_id"],
                },
                connector=self.name,
            ),
        ]

    async def call(self, tool_name: str, **kwargs: Any) -> ToolResult:
        """Execute a ServiceNow tool call.

        Args:
            tool_name: The tool to call.
            **kwargs: Tool parameters.

        Returns:
            ToolResult with success status and returned data.
        """
        log.debug("SN connector call: tool=%s", tool_name)
        match tool_name:
            case "sn_query_table":
                records = await self._client.query_table(**kwargs)
                return ToolResult(tool_name=tool_name, success=True, data={"records": records})
            case "sn_create_record":
                record = await self._client.create_record(**kwargs)
                return ToolResult(tool_name=tool_name, success=True, data=record)
            case "sn_update_record":
                record = await self._client.update_record(**kwargs)
                return ToolResult(tool_name=tool_name, success=True, data=record)
            case "sn_delete_record":
                await self._client.delete_record(**kwargs)
                return ToolResult(tool_name=tool_name, success=True)
            case _:
                return ToolResult(
                    tool_name=tool_name,
                    success=False,
                    error=f"Unknown tool: {tool_name!r}",
                )


# Satisfy the Protocol check at import time.
_: ConnectorProtocol = ServiceNowConnector.__new__(ServiceNowConnector)
