# src/nexus/plugins/dependencies.py
# DependencyEntry model + helper for SN pre-flight dependency cascade checks.
# Author: Pierre Grothe
# Date: 2026-05-14

"""Pre-flight dependency cascade via /api/sn_appclient/appmanager/dependencies."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, cast

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from nexus.connectors.servicenow.protocol import ServiceNowClientProtocol

__all__ = ["DependencyEntry", "fetch_dependencies"]

_FROZEN = ConfigDict(frozen=True, strict=True, extra="forbid")


class DependencyEntry(BaseModel):
    """One row from SN's appmanager/dependencies response.

    Field names match the ServiceNow JSON exactly except for the JSON
    field "Id" which is normalised to lowercase ``id`` here, and
    "minVersion" which is normalised to ``min_version``.

    Attributes:
        id: Display name (SN sends as "Id").
        orig_string: Scope:version string from SN, e.g. "sn_si:13.9.23".
        type: "Application" or "Plugin".
        min_version: Minimum version required.
        source_app_id: SN sys_id of the dependency.
        installed: Whether the dependency is already installed.
        active: Whether the dependency is currently active.
        hide_on_ui: SN flag indicating the row is internal.
        status: Human-readable status (e.g. "Will be Updated").
        status_value: Enum-like value (e.g. "will_be_updated").
        order: SN render order.
        link: SN navigation link.
        has_license: License presence flag.
        is_allowed_install: Whether install is permitted.
    """

    model_config = _FROZEN

    id: str
    orig_string: str
    type: Literal["Application", "Plugin"]
    min_version: str
    source_app_id: str
    installed: bool
    active: bool
    hide_on_ui: bool
    status: str
    status_value: str
    order: int
    link: str
    has_license: bool
    is_allowed_install: bool

    @classmethod
    def from_sn(cls, raw: dict[str, object]) -> DependencyEntry:
        """Build from the raw SN dict (handles 'Id' -> 'id' and 'minVersion' -> 'min_version')."""
        type_raw = raw.get("type", "Plugin")
        type_value: Literal["Application", "Plugin"]
        if type_raw == "Application":
            type_value = "Application"
        else:
            type_value = "Plugin"
        return cls(
            id=str(raw.get("Id", "")),
            orig_string=str(raw.get("orig_string", "")),
            type=type_value,
            min_version=str(raw.get("minVersion", "")),
            source_app_id=str(raw.get("source_app_id", "")),
            installed=bool(raw.get("installed", False)),
            active=bool(raw.get("active", False)),
            hide_on_ui=bool(raw.get("hide_on_ui", False)),
            status=str(raw.get("status", "")),
            status_value=str(raw.get("status_value", "")),
            order=int(cast(int, raw.get("order", 0)) or 0),
            link=str(raw.get("link", "")),
            has_license=bool(raw.get("has_license", False)),
            is_allowed_install=bool(raw.get("is_allowed_install", False)),
        )


async def fetch_dependencies(
    client: ServiceNowClientProtocol,
    plugin_id: str,
    version: str | None = None,
) -> tuple[DependencyEntry, ...]:
    """Pre-flight SN dependency cascade for a plugin install/upgrade.

    Args:
        client: ServiceNow client conforming to the protocol.
        plugin_id: Canonical plugin identifier (e.g. "sn_si").
        version: Target version, or None for "latest".

    Returns:
        Tuple of typed DependencyEntry objects, in SN's render order.
    """
    raw_rows = await client.appmanager_dependencies(plugin_id, version)
    return tuple(DependencyEntry.from_sn(row) for row in raw_rows)
