# src/nexus/capture/models.py
# Data models for the capture layer.
# Author: Pierre Grothe
# Date: 2026-05-09

"""Pydantic models and type aliases for ServiceNow configuration capture."""

from __future__ import annotations

from pathlib import Path
from typing import TypedDict

from pydantic import BaseModel, ConfigDict

from nexus.config.types import UtcDatetime

__all__ = [
    "ArchiveManifest",
    "CaptureResult",
    "ConfigRecord",
    "ScopeEntry",
    "ScopeManifest",
    "SnFieldValue",
    "SnRecord",
    "SnRefField",
    "UpdateSetRef",
]


class SnRefField(TypedDict):
    """ServiceNow reference field with both sys_id value and display label."""

    value: str
    display_value: str


type SnFieldValue = str | bool | int | float | None | SnRefField
type SnRecord = dict[str, SnFieldValue]


class ScopeEntry(BaseModel):
    """One application scope discovered on a ServiceNow instance."""

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    sys_id: str
    name: str
    scope: str
    version: str
    vendor: str
    table_counts: dict[str, int]


class ScopeManifest(BaseModel):
    """Full scope discovery result for a single instance."""

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    instance_id: str
    captured_at: UtcDatetime
    scopes: tuple[ScopeEntry, ...]


class ConfigRecord(BaseModel):
    """One captured record from a ServiceNow table."""

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    sys_id: str
    table: str
    scope_sys_id: str
    scope_name: str
    captured_at: UtcDatetime
    fields: SnRecord
    parent_sys_id: str | None = None


class CaptureResult(BaseModel):
    """Full result of a capture operation across one or more scopes."""

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    instance_id: str
    captured_at: UtcDatetime
    scope_ids: tuple[str, ...]
    table_group: str
    records: tuple[ConfigRecord, ...]

    def by_table(self) -> dict[str, tuple[ConfigRecord, ...]]:
        """Group records by table name.

        Returns:
            Mapping of table name to the records belonging to that table.
        """
        grouped: dict[str, list[ConfigRecord]] = {}
        for record in self.records:
            grouped.setdefault(record.table, []).append(record)
        return {table: tuple(recs) for table, recs in grouped.items()}


class ArchiveManifest(BaseModel):
    """Metadata about a saved YAML archive on disk."""

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    format_version: str
    instance_id: str
    captured_at: UtcDatetime
    scope_ids: tuple[str, ...]
    table_group: str
    record_count: int
    archive_dir: Path


class UpdateSetRef(BaseModel):
    """Reference to a ServiceNow update set after injection."""

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    sys_id: str
    name: str
    state: str
    record_count: int
    instance_id: str
