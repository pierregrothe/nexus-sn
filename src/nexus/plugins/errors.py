# src/nexus/plugins/errors.py
# Error types raised by the plugins layer.
# Author: Pierre Grothe
# Date: 2026-05-11
"""Error types for the plugins layer."""

__all__ = ["PluginAdvisoryDataError", "PluginImpactError", "PluginScanError"]


class PluginScanError(Exception):
    """Raised when neither v_plugin nor sys_store_app is readable.

    Args:
        table: Last table attempted before the scan was abandoned.
        status_code: HTTP status returned by ServiceNow.
    """

    def __init__(self, table: str, status_code: int) -> None:
        """Store the offending table and HTTP status alongside the message."""
        super().__init__(f"Plugin scan failed: HTTP {status_code} reading {table}")
        self.table = table
        self.status_code = status_code


class PluginAdvisoryDataError(Exception):
    """Raised when a bundled advisory YAML file is unreadable or invalid.

    The original yaml/Pydantic/Specifier error message is preserved in the
    exception message.

    Args:
        message: Human-readable description of what failed.
    """

    def __init__(self, message: str) -> None:
        """Store the reason message."""
        super().__init__(message)


class PluginImpactError(Exception):
    """Raised when the impact target is not in the captured inventory.

    Args:
        plugin_id: The unknown plugin identifier.
    """

    def __init__(self, plugin_id: str) -> None:
        """Store the unknown plugin id."""
        super().__init__(f"plugin not found in inventory: {plugin_id}")
        self.plugin_id = plugin_id
