# src/nexus/plugins/errors.py
# Error types raised by the plugins layer.
# Author: Pierre Grothe
# Date: 2026-05-11
"""Error types for the plugins layer."""

__all__ = [
    "AdvisoryOverrideError",
    "BaselineNotFoundError",
    "InvalidBaselineNameError",
    "PluginAdvisoryDataError",
    "PluginBaselineNotFoundError",
    "PluginBatchError",
    "PluginExecutionError",
    "PluginImpactError",
    "PluginNotFoundError",
    "PluginProgressError",
    "PluginScanError",
    "PluginTimeoutError",
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


class InvalidBaselineNameError(ValueError):
    """Raised when a baseline name fails the safe-filename validation.

    Attributes:
        name: The invalid baseline name as supplied by the caller.
    """

    def __init__(self, name: str) -> None:
        """Store the invalid name and a human-readable message."""
        self.name = name
        super().__init__(
            f"invalid baseline name {name!r} -- " "must match ^[a-z0-9][a-z0-9_-]{0,62}$"
        )


class BaselineNotFoundError(Exception):
    """Raised when a named baseline file does not exist on disk.

    Attributes:
        profile: Instance profile name.
        name: Baseline name that was requested.
    """

    def __init__(self, profile: str, name: str) -> None:
        """Store the profile and baseline name alongside the message."""
        self.profile = profile
        self.name = name
        super().__init__(f"no baseline named {name!r} for profile={profile!r}")


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


class PluginExecutionError(Exception):
    """Base class for plugin execution failures."""


class PluginProgressError(PluginExecutionError):
    """Raised when SN's progress endpoint reports a terminal failure state.

    Attributes:
        tracker_id: The sn_appclient tracker GUID.
        sn_status: SN's numeric status string (e.g. "3" for Failed).
        error_message: SN's error message field.
    """

    def __init__(self, tracker_id: str, sn_status: str, error_message: str) -> None:
        """Store tracker ID, status, and error message alongside the message."""
        super().__init__(f"plugin operation failed: {error_message} (status={sn_status})")
        self.tracker_id = tracker_id
        self.sn_status = sn_status
        self.error_message = error_message


class PluginTimeoutError(PluginExecutionError):
    """Raised when progress polling exceeds the configured timeout.

    Attributes:
        tracker_id: The sn_appclient tracker GUID.
        elapsed_s: Seconds elapsed before timeout.
    """

    def __init__(self, tracker_id: str, elapsed_s: float) -> None:
        """Store tracker ID and elapsed time alongside the message."""
        super().__init__(f"plugin operation timed out after {elapsed_s:.0f}s")
        self.tracker_id = tracker_id
        self.elapsed_s = elapsed_s


class PluginNotFoundError(PluginExecutionError):
    """Raised when the requested plugin_id is not in the loaded inventory.

    Attributes:
        plugin_id: The unknown plugin identifier.
    """

    def __init__(self, plugin_id: str) -> None:
        """Store the unknown plugin ID alongside the message."""
        super().__init__(f"plugin not found in inventory: {plugin_id}")
        self.plugin_id = plugin_id


class PluginBatchError(PluginExecutionError):
    """Raised when the multipart batch envelope itself is malformed.

    Attributes:
        batch_response: The raw response fragment for debugging.
    """

    def __init__(self, batch_response: str) -> None:
        """Store the batch response fragment alongside the message."""
        super().__init__("malformed batch response from ServiceNow")
        self.batch_response = batch_response
