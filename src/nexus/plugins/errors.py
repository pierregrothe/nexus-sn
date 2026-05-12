# src/nexus/plugins/errors.py
# Error types raised by the plugins layer.
# Author: Pierre Grothe
# Date: 2026-05-11
"""Error types for the plugins layer."""

__all__ = [
    "AdvisoryOverrideError",
    "PluginAdvisoryDataError",
    "PluginBaselineNotFoundError",
    "PluginImpactError",
    "PluginScanError",
]


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


class AdvisoryOverrideError(Exception):
    """Raised by the CLI override commands on user-input failure.

    Attributes:
        plugin_id: Plugin identifier referenced by the failed command.
        advisory_type: Advisory type referenced by the failed command.
        details: Finding details string referenced by the failed command.
        reason_code: One of ``no_matching_finding``, ``duplicate``, ``not_found``.
    """

    def __init__(
        self,
        plugin_id: str,
        advisory_type: str,
        details: str,
        reason_code: str,
    ) -> None:
        """Store the identifiers and reason code alongside the message."""
        self.plugin_id = plugin_id
        self.advisory_type = advisory_type
        self.details = details
        self.reason_code = reason_code
        super().__init__(
            f"override {reason_code} for plugin={plugin_id} "
            f"type={advisory_type} details={details!r}"
        )


class PluginBaselineNotFoundError(Exception):
    """Raised when nexus plugins drift runs without a saved baseline.

    The profile has no ``plugins.baseline.json``. User must run
    ``nexus plugins drift --ack`` to mark the current snapshot as the
    baseline first.

    Args:
        profile: Instance profile that is missing a baseline.
    """

    def __init__(self, profile: str) -> None:
        """Store the profile name and a human-readable message."""
        super().__init__(f"no plugin baseline saved for profile: {profile}")
        self.profile = profile
