# src/nexus/plugins/models.py
# Pydantic models for the ServiceNow plugin inventory layer.
# Author: Pierre Grothe
# Date: 2026-05-11
"""PluginInfo, PluginInventory, ProductFamily."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict

from nexus.config.types import UtcDatetime

__all__ = ["PluginInfo", "PluginInventory", "ProductFamily"]

_FROZEN = ConfigDict(frozen=True, strict=True, extra="forbid")


class ProductFamily(StrEnum):
    """ServiceNow product taxonomy used by the inventory filter."""

    ITSM = "ITSM"
    ITOM = "ITOM"
    ITAM = "ITAM"
    SPM = "SPM"
    CSM = "CSM"
    HRSD = "HRSD"
    FSM = "FSM"
    GRC = "GRC"
    IRM = "IRM"
    SEC_OPS = "SecOps"
    PLATFORM = "Platform"
    UNCATEGORIZED = "Uncategorized"


class PluginInfo(BaseModel):
    """One plugin's static metadata on an instance.

    Attributes:
        plugin_id: Canonical SN plugin identifier (e.g. ``com.snc.incident``).
        name: Display name from sys_store_app.name or v_plugin.name.
        version: Currently installed version string.
        state: ``active`` if activated, ``inactive`` otherwise.
        source: Origin of the plugin record.
        product_family: Curated product family or ``Uncategorized``.
        depends_on: Direct plugin dependencies (no traversal at this layer).
        sys_id: SN record sys_id.
        installed_at: Activation timestamp; ``None`` if never activated.
        latest_version: The newest available version per ``sys_store_app``;
            ``None`` for v_plugin-only records (core SN plugins) and for
            store apps where the field is empty.
    """

    model_config = _FROZEN

    plugin_id: str
    name: str
    version: str
    state: Literal["active", "inactive"]
    source: Literal["servicenow", "store", "custom"]
    product_family: str
    depends_on: tuple[str, ...]
    sys_id: str
    installed_at: UtcDatetime | None
    latest_version: str | None = None


class PluginInventory(BaseModel):
    """Plugin inventory captured from one instance at a single moment.

    Attributes:
        captured_at: When the scan ran (UTC).
        sn_version: SN release name at scan time, copied from InstanceMeta.
        plugins: All plugins discovered on the instance.
    """

    model_config = _FROZEN

    captured_at: UtcDatetime
    sn_version: str
    plugins: tuple[PluginInfo, ...]
