# src/nexus/schema/errors.py
# Schema layer error hierarchy.
# Author: Pierre Grothe
# Date: 2026-06-08
"""Typed exceptions for the schema cartography layer.

No shared NexusError base exists; each layer subclasses Exception directly
(the capture/errors.py pattern).
"""

from pathlib import Path

__all__ = [
    "AreaNotFoundError",
    "SchemaArchiveError",
    "SchemaError",
    "ScopeNotFoundError",
]


class SchemaError(Exception):
    """Base class for all schema layer errors."""


class AreaNotFoundError(SchemaError):
    """Requested schema area key is not in the registry."""

    def __init__(self, area_key: str) -> None:
        """Initialize with the unknown area key.

        Args:
            area_key: The unrecognised area key.
        """
        super().__init__(f"Unknown schema area {area_key!r}")
        self.area_key = area_key


class ScopeNotFoundError(SchemaError):
    """None of an area's scopes resolved on the instance."""

    def __init__(self, scopes: list[str], instance_id: str) -> None:
        """Initialize with the scope keys and instance id.

        Args:
            scopes: The area's scope keys that failed to resolve.
            instance_id: The instance profile that was queried.
        """
        super().__init__(f"No scopes {scopes!r} found on {instance_id!r}")
        self.scopes = scopes
        self.instance_id = instance_id


class SchemaArchiveError(SchemaError):
    """Schema snapshot JSON is missing or invalid."""

    def __init__(self, path: Path) -> None:
        """Initialize with the offending archive path.

        Args:
            path: The archive file path that is missing or invalid.
        """
        super().__init__(f"Schema archive missing or invalid: {path}")
        self.path = path
