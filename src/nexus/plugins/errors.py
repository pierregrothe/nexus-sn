# src/nexus/plugins/errors.py
# Error types raised by the plugins layer.
# Author: Pierre Grothe
# Date: 2026-05-11
"""PluginScanError for SN-side plugin scan failures."""

__all__ = ["PluginScanError"]


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
