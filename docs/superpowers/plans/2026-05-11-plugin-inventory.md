# Plugin Inventory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship sub-project A of the plugin management roadmap: a read-only `nexus plugins` sub-app backed by a new `src/nexus/plugins/` layer that scans `v_plugin` + `sys_store_app`, dedupes into a frozen `PluginInventory`, persists alongside the existing instance snapshot, and renders through the `nexus.ui` component library.

**Architecture:** New layer `src/nexus/plugins/` sits alongside `capture/` and `assessment/`. `PluginScanner` runs concurrently with the existing `InstanceScanner.scan()` inside `nexus instance refresh`. Results are stored in `instances/<profile>/plugins.json`. CLI commands resolve the instance via the existing `_resolve_profile` helper and render through `DataTable` / `KeyValuePanel` / `Notice` / `Hint` / `CommandGuide`.

**Tech Stack:** Python 3.14, Poetry, httpx (async), Pydantic v2 (frozen models), Typer, Rich (via `nexus.ui`), PyYAML, pytest.

**Spec:** `docs/superpowers/specs/2026-05-11-plugin-inventory-design.md`

---

## File structure

New files:

```
src/nexus/plugins/
  __init__.py                          -- public re-exports
  models.py                            -- PluginInfo, PluginInventory, ProductFamily
  errors.py                            -- PluginScanError
  scanner.py                           -- PluginScanner (async)
  product_families.py                  -- loader + product_family_for()
  product_families.yaml                -- curated plugin_id -> family mapping

tests/
  test_plugins_models.py
  test_plugins_errors.py
  test_plugins_product_families.py
  test_plugins_scanner.py
  test_cli_plugins.py

tests/fakes/
  fake_plugin_data.py                  -- canned v_plugin + sys_store_app rows
```

Modified files:

```
src/nexus/instances/models.py          -- SnapshotCounts.plugins: int = 0
src/nexus/instances/registry.py        -- load_plugin_inventory + save_plugin_inventory
src/nexus/cli.py                       -- plugins_app + 4 commands
.ratchet.json                          -- new module baselines
```

---

## Task 1: Pydantic models

**Files:**
- Create: `src/nexus/plugins/models.py`
- Test: `tests/test_plugins_models.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_plugins_models.py
# Tests for the plugins layer Pydantic models.
# Author: Pierre Grothe
# Date: 2026-05-11
"""Tests for PluginInfo, PluginInventory, and ProductFamily."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from nexus.plugins.models import PluginInfo, PluginInventory, ProductFamily

__all__: list[str] = []


def _info(**overrides: object) -> PluginInfo:
    defaults: dict[str, object] = {
        "plugin_id": "com.snc.incident",
        "name": "Incident Management",
        "version": "1.0.0",
        "state": "active",
        "source": "servicenow",
        "product_family": "ITSM",
        "depends_on": (),
        "sys_id": "abc123",
        "installed_at": None,
    }
    defaults.update(overrides)
    return PluginInfo(**defaults)  # type: ignore[arg-type]


def test_product_family_includes_all_curated_families() -> None:
    for name in (
        "ITSM", "ITOM", "ITAM", "SPM", "CSM", "HRSD",
        "FSM", "GRC", "IRM", "SecOps", "Platform", "Uncategorized",
    ):
        assert any(f.value == name for f in ProductFamily)


def test_plugin_info_construction_with_required_fields() -> None:
    info = _info()
    assert info.plugin_id == "com.snc.incident"
    assert info.state == "active"


def test_plugin_info_is_frozen() -> None:
    info = _info()
    with pytest.raises(ValidationError):
        info.name = "renamed"


def test_plugin_info_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        PluginInfo.model_validate({**_info().model_dump(), "extra": "x"})


def test_plugin_info_rejects_unknown_state() -> None:
    with pytest.raises(ValidationError):
        _info(state="unknown")


def test_plugin_info_rejects_unknown_source() -> None:
    with pytest.raises(ValidationError):
        _info(source="vendor")


def test_plugin_inventory_holds_captured_at_and_plugins() -> None:
    now = datetime.now(UTC)
    inv = PluginInventory(
        captured_at=now, sn_version="Xanadu", plugins=(_info(),)
    )
    assert inv.captured_at == now
    assert inv.plugins[0].plugin_id == "com.snc.incident"


def test_plugin_inventory_is_frozen() -> None:
    inv = PluginInventory(
        captured_at=datetime.now(UTC), sn_version="Xanadu", plugins=()
    )
    with pytest.raises(ValidationError):
        inv.sn_version = "Yokohama"


def test_plugin_inventory_round_trips_through_json() -> None:
    inv = PluginInventory(
        captured_at=datetime.now(UTC), sn_version="Xanadu", plugins=(_info(),)
    )
    re = PluginInventory.model_validate_json(inv.model_dump_json())
    assert re == inv
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_plugins_models.py -v`
Expected: FAIL on missing module.

- [ ] **Step 3: Implement models**

```python
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
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/test_plugins_models.py -v`
Expected: 9 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/nexus/plugins/models.py tests/test_plugins_models.py
git commit -m "feat(plugins): add PluginInfo/PluginInventory/ProductFamily models"
```

---

## Task 2: PluginScanError

**Files:**
- Create: `src/nexus/plugins/errors.py`
- Test: `tests/test_plugins_errors.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_plugins_errors.py
# Tests for the plugins layer error hierarchy.
# Author: Pierre Grothe
# Date: 2026-05-11
"""Tests for PluginScanError."""

import pytest

from nexus.plugins.errors import PluginScanError

__all__: list[str] = []


def test_plugin_scan_error_holds_reason_and_status() -> None:
    err = PluginScanError("v_plugin", 403)
    assert "v_plugin" in str(err)
    assert "403" in str(err)


def test_plugin_scan_error_is_raisable() -> None:
    with pytest.raises(PluginScanError):
        raise PluginScanError("sys_store_app", 500)
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_plugins_errors.py -v`
Expected: FAIL on missing module.

- [ ] **Step 3: Implement errors**

```python
# src/nexus/plugins/errors.py
# Error types raised by the plugins layer.
# Author: Pierre Grothe
# Date: 2026-05-11
"""PluginScanError extends NexusError for SN-side scan failures."""

from nexus.errors import NexusError

__all__ = ["PluginScanError"]


class PluginScanError(NexusError):
    """Raised when neither v_plugin nor sys_store_app is readable.

    Args:
        table: Last table attempted before the scan was abandoned.
        status_code: HTTP status returned by ServiceNow.
    """

    def __init__(self, table: str, status_code: int) -> None:
        """See class docstring."""
        super().__init__(
            f"Plugin scan failed: HTTP {status_code} reading {table}"
        )
        self.table = table
        self.status_code = status_code
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/test_plugins_errors.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/nexus/plugins/errors.py tests/test_plugins_errors.py
git commit -m "feat(plugins): add PluginScanError"
```

---

## Task 3: Product-family YAML

**Files:**
- Create: `src/nexus/plugins/product_families.yaml`

- [ ] **Step 1: Write the YAML**

```yaml
# src/nexus/plugins/product_families.yaml
# Curated mapping of ServiceNow plugin IDs to product families.
# Author: Pierre Grothe
# Date: 2026-05-11
#
# Keys are plugin_id values seen in v_plugin.id or sys_store_app.scope.
# Values must match one of the ProductFamily enum names exactly.
# Unknown plugin IDs fall through to ``Uncategorized`` in code.

# ITSM
"com.snc.incident":                    ITSM
"com.snc.problem":                     ITSM
"com.snc.change_management":           ITSM
"com.snc.change_request_calendar":     ITSM
"com.snc.service_catalog":             ITSM
"com.snc.knowledge":                   ITSM
"com.snc.knowledge_advanced":          ITSM
"com.snc.itil":                        ITSM

# ITOM
"com.snc.discovery":                   ITOM
"com.snc.event_management":            ITOM
"com.snc.cmdb":                        ITOM
"com.snc.service_mapping":             ITOM
"com.snc.cloud_management":            ITOM
"com.snc.itom_licensing":              ITOM
"com.snc.health_log_analytics":        ITOM

# ITAM
"com.snc.asset_management":            ITAM
"com.snc.software_asset_management":   ITAM
"com.snc.hardware_asset_management":   ITAM
"com.snc.contract_management":         ITAM

# SPM
"com.snc.financial_planning":          SPM
"com.snc.demand_management":           SPM
"com.snc.project_management":          SPM
"com.snc.resource_management":         SPM
"com.snc.agile":                       SPM
"com.snc.test_management":             SPM

# CSM
"sn_customerservice":                  CSM
"com.snc.customerservice":             CSM
"sn_csm_customer_portal":              CSM
"sn_omnichannel":                      CSM

# HRSD
"sn_hr_core":                          HRSD
"sn_hr_lifecycle_events":              HRSD
"sn_hr_case_management":               HRSD
"sn_hr_employee_service_center":       HRSD

# FSM
"sn_fsm":                              FSM
"sn_fsm_dispatch":                     FSM

# GRC
"com.sn_grc":                          GRC
"com.snc.audit":                       GRC
"com.snc.policy_compliance":           GRC

# IRM
"sn_irm_core":                         IRM
"sn_irm_risk":                         IRM
"sn_irm_advanced_risk":                IRM

# SecOps
"sn_si":                               SecOps
"sn_vul":                              SecOps
"sn_ti":                               SecOps
"com.snc.threat_intelligence":         SecOps

# Platform
"com.servicenow.dashboards":           Platform
"com.snc.performance_analytics":       Platform
"com.snc.platform_security":           Platform
"com.snc.notification":                Platform
"com.snc.virtualagent":                Platform
"com.snc.ai_search":                   Platform
"com.snc.now_assist":                  Platform
```

- [ ] **Step 2: Commit**

```bash
git add src/nexus/plugins/product_families.yaml
git commit -m "feat(plugins): add curated product-family map (50 entries)"
```

---

## Task 4: Product-family loader

**Files:**
- Create: `src/nexus/plugins/product_families.py`
- Test: `tests/test_plugins_product_families.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_plugins_product_families.py
# Tests for the product-family YAML loader.
# Author: Pierre Grothe
# Date: 2026-05-11
"""Tests for product_family_for() and load_product_families()."""

from nexus.plugins.models import ProductFamily
from nexus.plugins.product_families import (
    load_product_families,
    product_family_for,
)

__all__: list[str] = []


def test_load_product_families_returns_non_empty_mapping() -> None:
    mapping = load_product_families()
    assert len(mapping) >= 40


def test_load_product_families_values_are_valid_product_family_members() -> None:
    mapping = load_product_families()
    valid = {f.value for f in ProductFamily}
    for plugin_id, family in mapping.items():
        assert family in valid, f"{plugin_id!r} maps to invalid family {family!r}"


def test_load_product_families_has_no_duplicate_keys() -> None:
    """YAML load already deduplicates, but assert no keys collide post-load."""
    mapping = load_product_families()
    assert len(mapping) == len({k.lower() for k in mapping})


def test_product_family_for_known_id_returns_curated_family() -> None:
    assert product_family_for("com.snc.incident") == ProductFamily.ITSM
    assert product_family_for("sn_hr_core") == ProductFamily.HRSD


def test_product_family_for_unknown_id_returns_uncategorized() -> None:
    assert product_family_for("x_company_app") == ProductFamily.UNCATEGORIZED


def test_product_family_for_empty_string_returns_uncategorized() -> None:
    assert product_family_for("") == ProductFamily.UNCATEGORIZED
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_plugins_product_families.py -v`
Expected: FAIL on missing module.

- [ ] **Step 3: Implement loader**

```python
# src/nexus/plugins/product_families.py
# Loader for the curated plugin_id -> ProductFamily mapping.
# Author: Pierre Grothe
# Date: 2026-05-11
"""product_family_for: O(1) lookup against product_families.yaml."""

from functools import cache
from pathlib import Path

import yaml

from nexus.plugins.models import ProductFamily

__all__ = ["load_product_families", "product_family_for"]

_YAML_PATH = Path(__file__).parent / "product_families.yaml"


@cache
def load_product_families() -> dict[str, str]:
    """Read product_families.yaml once and cache the mapping.

    Returns:
        ``plugin_id -> ProductFamily.value`` mapping. Values are validated
        against the ``ProductFamily`` enum so a typo in the YAML fails at
        load time rather than silently mis-tagging plugins.

    Raises:
        ValueError: When a YAML value is not a valid ProductFamily name.
    """
    raw: dict[str, str] = yaml.safe_load(_YAML_PATH.read_text(encoding="utf-8")) or {}
    valid_values = {f.value for f in ProductFamily}
    for plugin_id, family in raw.items():
        if family not in valid_values:
            raise ValueError(
                f"Invalid product family {family!r} for {plugin_id!r} "
                f"in product_families.yaml"
            )
    return raw


def product_family_for(plugin_id: str) -> ProductFamily:
    """Return the curated ProductFamily for a plugin, or UNCATEGORIZED.

    Args:
        plugin_id: SN plugin identifier (v_plugin.id or sys_store_app.scope).

    Returns:
        ProductFamily enum member.
    """
    family_value = load_product_families().get(plugin_id)
    if family_value is None:
        return ProductFamily.UNCATEGORIZED
    return ProductFamily(family_value)
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/test_plugins_product_families.py -v`
Expected: 6 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/nexus/plugins/product_families.py tests/test_plugins_product_families.py
git commit -m "feat(plugins): add product_family_for loader with YAML validation"
```

---

## Task 5: Fake plugin data

**Files:**
- Create: `tests/fakes/fake_plugin_data.py`

- [ ] **Step 1: Write the fake data module**

```python
# tests/fakes/fake_plugin_data.py
# Canned SN Table API rows for v_plugin and sys_store_app.
# Author: Pierre Grothe
# Date: 2026-05-11
"""Canned plugin rows used by PluginScanner tests.

Covers the cases the scanner must handle:
- An ITSM plugin present in both tables (dedup case).
- An ITOM plugin present only in v_plugin (legacy-only).
- A Store app present only in sys_store_app (third-party vendor).
- A custom scoped app whose scope starts with x_ (source=custom).
- An inactive plugin (state=inactive).
- A plugin not in the curated YAML (product_family=Uncategorized).
"""

__all__ = ["V_PLUGIN_ROWS", "SYS_STORE_APP_ROWS"]


V_PLUGIN_ROWS: list[dict[str, object]] = [
    {
        "sys_id": "abc111",
        "id": "com.snc.incident",
        "name": "Incident Management",
        "version": "1.2.3",
        "active": "true",
        "dependencies": "",
        "installed_on": "2024-01-15 12:00:00",
    },
    {
        "sys_id": "abc222",
        "id": "com.snc.discovery",
        "name": "Discovery",
        "version": "2.0.0",
        "active": "true",
        "dependencies": "com.snc.cmdb",
        "installed_on": "2024-02-20 09:30:00",
    },
    {
        "sys_id": "abc333",
        "id": "com.snc.legacy_only",
        "name": "Legacy Plugin",
        "version": "0.5.0",
        "active": "false",
        "dependencies": "",
        "installed_on": "",
    },
]


SYS_STORE_APP_ROWS: list[dict[str, object]] = [
    {
        "sys_id": "abc111",
        "scope": "com.snc.incident",
        "name": "Incident Management",
        "version": "1.2.3",
        "active": "true",
        "vendor": "ServiceNow",
        "dependencies": "",
        "sys_created_on": "2024-01-15 12:00:00",
    },
    {
        "sys_id": "store001",
        "scope": "com.acme.helper",
        "name": "Acme Helper",
        "version": "3.1.0",
        "active": "true",
        "vendor": "Acme Corp",
        "dependencies": "",
        "sys_created_on": "2024-03-01 10:00:00",
    },
    {
        "sys_id": "custom001",
        "scope": "x_company_app",
        "name": "Internal Company App",
        "version": "0.1.0",
        "active": "true",
        "vendor": "",
        "dependencies": "",
        "sys_created_on": "2024-04-05 16:45:00",
    },
]
```

- [ ] **Step 2: Commit**

```bash
git add tests/fakes/fake_plugin_data.py
git commit -m "test(plugins): add canned v_plugin and sys_store_app rows"
```

---

## Task 6: PluginScanner

**Files:**
- Create: `src/nexus/plugins/scanner.py`
- Test: `tests/test_plugins_scanner.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_plugins_scanner.py
# Tests for the async PluginScanner.
# Author: Pierre Grothe
# Date: 2026-05-11
"""Tests for PluginScanner.scan() against canned table data."""

import asyncio

import httpx
import pytest

from nexus.plugins.errors import PluginScanError
from nexus.plugins.scanner import PluginScanner
from tests.fakes.fake_plugin_data import SYS_STORE_APP_ROWS, V_PLUGIN_ROWS

__all__: list[str] = []


def _transport_for(
    v_plugin_status: int = 200,
    store_status: int = 200,
    v_plugin_rows: list[dict[str, object]] | None = None,
    store_rows: list[dict[str, object]] | None = None,
) -> httpx.MockTransport:
    """Build a transport that serves both tables with the given rows/status."""
    v_rows = v_plugin_rows if v_plugin_rows is not None else V_PLUGIN_ROWS
    s_rows = store_rows if store_rows is not None else SYS_STORE_APP_ROWS

    def handler(req: httpx.Request) -> httpx.Response:
        if "v_plugin" in req.url.path:
            return httpx.Response(v_plugin_status, json={"result": v_rows})
        if "sys_store_app" in req.url.path:
            return httpx.Response(store_status, json={"result": s_rows})
        return httpx.Response(404, json={"result": []})

    return httpx.MockTransport(handler)


async def _scan(transport: httpx.MockTransport) -> object:
    scanner = PluginScanner(transport=transport)
    return await scanner.scan(
        url="https://dev.service-now.com", token="t", sn_version="Xanadu"
    )


def test_scan_returns_inventory_with_captured_at_and_sn_version() -> None:
    inv = asyncio.run(_scan(_transport_for()))
    assert inv.sn_version == "Xanadu"
    assert inv.captured_at is not None


def test_scan_dedupes_plugin_present_in_both_tables() -> None:
    inv = asyncio.run(_scan(_transport_for()))
    incidents = [p for p in inv.plugins if p.plugin_id == "com.snc.incident"]
    assert len(incidents) == 1


def test_scan_marks_servicenow_vendor_as_servicenow_source() -> None:
    inv = asyncio.run(_scan(_transport_for()))
    incident = next(p for p in inv.plugins if p.plugin_id == "com.snc.incident")
    assert incident.source == "servicenow"


def test_scan_marks_third_party_vendor_as_store_source() -> None:
    inv = asyncio.run(_scan(_transport_for()))
    helper = next(p for p in inv.plugins if p.plugin_id == "com.acme.helper")
    assert helper.source == "store"


def test_scan_marks_x_scope_as_custom_source() -> None:
    inv = asyncio.run(_scan(_transport_for()))
    custom = next(p for p in inv.plugins if p.plugin_id == "x_company_app")
    assert custom.source == "custom"


def test_scan_maps_active_true_to_state_active() -> None:
    inv = asyncio.run(_scan(_transport_for()))
    incident = next(p for p in inv.plugins if p.plugin_id == "com.snc.incident")
    assert incident.state == "active"


def test_scan_maps_active_false_to_state_inactive() -> None:
    inv = asyncio.run(_scan(_transport_for()))
    legacy = next(p for p in inv.plugins if p.plugin_id == "com.snc.legacy_only")
    assert legacy.state == "inactive"


def test_scan_resolves_curated_product_family_for_known_plugin() -> None:
    inv = asyncio.run(_scan(_transport_for()))
    incident = next(p for p in inv.plugins if p.plugin_id == "com.snc.incident")
    assert incident.product_family == "ITSM"


def test_scan_resolves_uncategorized_for_unknown_plugin() -> None:
    inv = asyncio.run(_scan(_transport_for()))
    helper = next(p for p in inv.plugins if p.plugin_id == "com.acme.helper")
    assert helper.product_family == "Uncategorized"


def test_scan_parses_comma_separated_dependencies() -> None:
    inv = asyncio.run(_scan(_transport_for()))
    discovery = next(p for p in inv.plugins if p.plugin_id == "com.snc.discovery")
    assert discovery.depends_on == ("com.snc.cmdb",)


def test_scan_falls_back_to_store_when_v_plugin_unreadable() -> None:
    """403 on v_plugin should not abort; sys_store_app rows still return."""
    inv = asyncio.run(_scan(_transport_for(v_plugin_status=403)))
    ids = {p.plugin_id for p in inv.plugins}
    assert "com.acme.helper" in ids


def test_scan_falls_back_to_v_plugin_when_store_unreadable() -> None:
    inv = asyncio.run(_scan(_transport_for(store_status=403)))
    ids = {p.plugin_id for p in inv.plugins}
    assert "com.snc.discovery" in ids


def test_scan_raises_plugin_scan_error_when_both_tables_fail() -> None:
    with pytest.raises(PluginScanError):
        asyncio.run(
            _scan(_transport_for(v_plugin_status=500, store_status=500))
        )
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_plugins_scanner.py -v`
Expected: FAIL on missing module.

- [ ] **Step 3: Implement scanner**

```python
# src/nexus/plugins/scanner.py
# Async REST scanner that builds a PluginInventory from v_plugin + sys_store_app.
# Author: Pierre Grothe
# Date: 2026-05-11
"""PluginScanner: concurrent reads of v_plugin and sys_store_app with dedup."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import httpx

from nexus.plugins.errors import PluginScanError
from nexus.plugins.models import PluginInfo, PluginInventory
from nexus.plugins.product_families import product_family_for

__all__ = ["PluginScanner"]

log = logging.getLogger(__name__)

_V_PLUGIN_FIELDS = "sys_id,id,name,version,active,dependencies,installed_on"
_STORE_FIELDS = "sys_id,scope,name,version,active,vendor,dependencies,sys_created_on"
_PAGE_LIMIT = 200
_SERVICENOW_VENDORS = {"ServiceNow", "Service-now.com", "servicenow"}
_CUSTOM_SCOPE_PREFIXES = ("x_", "u_")


class PluginScanner:
    """Reads v_plugin and sys_store_app concurrently and merges into one inventory.

    Args:
        transport: Optional httpx transport for tests. Omit in production.
    """

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        """See class docstring."""
        self._transport = transport

    async def scan(self, url: str, token: str, sn_version: str) -> PluginInventory:
        """Capture the full plugin inventory.

        Args:
            url: Instance base URL.
            token: OAuth bearer token.
            sn_version: SN release name copied verbatim into the inventory.

        Returns:
            PluginInventory with deduped plugins from both tables.

        Raises:
            PluginScanError: When both source tables return non-200 responses.
        """
        async with httpx.AsyncClient(
            base_url=url,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=30.0,
            transport=self._transport,
        ) as client:
            v_rows, v_err = await self._fetch(client, "v_plugin", _V_PLUGIN_FIELDS)
            s_rows, s_err = await self._fetch(client, "sys_store_app", _STORE_FIELDS)

        if v_err is not None and s_err is not None:
            raise PluginScanError(s_err[0], s_err[1])

        by_id: dict[str, PluginInfo] = {}
        for row in v_rows:
            info = self._from_v_plugin(row)
            by_id[info.plugin_id] = info
        for row in s_rows:
            info = self._from_store(row)
            # sys_store_app wins on conflict because it carries vendor.
            by_id[info.plugin_id] = info

        return PluginInventory(
            captured_at=datetime.now(UTC),
            sn_version=sn_version,
            plugins=tuple(by_id.values()),
        )

    async def _fetch(
        self, client: httpx.AsyncClient, table: str, fields: str
    ) -> tuple[list[dict[str, object]], tuple[str, int] | None]:
        """Fetch one table; return ([], (table, status)) on non-200."""
        resp = await client.get(
            f"/api/now/table/{table}",
            params={"sysparm_fields": fields, "sysparm_limit": _PAGE_LIMIT},
        )
        if resp.status_code != 200:
            log.warning("plugin scan: %s returned HTTP %d", table, resp.status_code)
            return [], (table, resp.status_code)
        rows: list[dict[str, object]] = resp.json().get("result", [])
        return rows, None

    def _from_v_plugin(self, row: dict[str, object]) -> PluginInfo:
        plugin_id = str(row.get("id", ""))
        return PluginInfo(
            plugin_id=plugin_id,
            name=str(row.get("name", plugin_id)),
            version=str(row.get("version", "")),
            state="active" if _truthy(row.get("active")) else "inactive",
            source=_source_for(plugin_id, vendor=""),
            product_family=product_family_for(plugin_id).value,
            depends_on=_parse_deps(row.get("dependencies", "")),
            sys_id=str(row.get("sys_id", "")),
            installed_at=_parse_dt(row.get("installed_on", "")),
        )

    def _from_store(self, row: dict[str, object]) -> PluginInfo:
        plugin_id = _scope_value(row.get("scope", ""))
        vendor = str(row.get("vendor", ""))
        return PluginInfo(
            plugin_id=plugin_id,
            name=str(row.get("name", plugin_id)),
            version=str(row.get("version", "")),
            state="active" if _truthy(row.get("active")) else "inactive",
            source=_source_for(plugin_id, vendor=vendor),
            product_family=product_family_for(plugin_id).value,
            depends_on=_parse_deps(row.get("dependencies", "")),
            sys_id=str(row.get("sys_id", "")),
            installed_at=_parse_dt(row.get("sys_created_on", "")),
        )


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("true", "1", "yes")
    return bool(value)


def _scope_value(value: object) -> str:
    """sys_store_app.scope can be either a string or a {value, display_value} dict."""
    if isinstance(value, dict):
        return str(value.get("value", ""))
    return str(value)


def _source_for(plugin_id: str, vendor: str) -> str:
    if plugin_id.startswith(_CUSTOM_SCOPE_PREFIXES):
        return "custom"
    if vendor and vendor not in _SERVICENOW_VENDORS:
        return "store"
    return "servicenow"


def _parse_deps(value: object) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(part.strip() for part in str(value).split(",") if part.strip())


def _parse_dt(value: object) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(str(value), "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    except ValueError:
        return None
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/test_plugins_scanner.py -v`
Expected: 13 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/nexus/plugins/scanner.py tests/test_plugins_scanner.py
git commit -m "feat(plugins): add PluginScanner with dedup and source derivation"
```

---

## Task 7: Plugins package init

**Files:**
- Create: `src/nexus/plugins/__init__.py`

- [ ] **Step 1: Write the package init**

```python
# src/nexus/plugins/__init__.py
# Public re-exports for the plugins layer.
# Author: Pierre Grothe
# Date: 2026-05-11
"""nexus.plugins: read-only plugin inventory layer.

Exports the data models, scanner, error type, and product-family lookup.
The layer imports from cache/, config/, and connectors/ only -- never up.
"""

from nexus.plugins.errors import PluginScanError
from nexus.plugins.models import PluginInfo, PluginInventory, ProductFamily
from nexus.plugins.product_families import product_family_for
from nexus.plugins.scanner import PluginScanner

__all__ = [
    "PluginInfo",
    "PluginInventory",
    "PluginScanError",
    "PluginScanner",
    "ProductFamily",
    "product_family_for",
]
```

- [ ] **Step 2: Verify import surface**

Run: `python -c "from nexus.plugins import PluginInfo, PluginInventory, PluginScanError, PluginScanner, ProductFamily, product_family_for; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add src/nexus/plugins/__init__.py
git commit -m "feat(plugins): expose public API from nexus.plugins"
```

---

## Task 8: SnapshotCounts.plugins field

**Files:**
- Modify: `src/nexus/instances/models.py`
- Test: `tests/test_instances_models.py`

- [ ] **Step 1: Inspect current model**

Run: `grep -n "class SnapshotCounts" src/nexus/instances/models.py`

Expected: locates the existing class with ai_skills / flows / business_rules / script_includes fields.

- [ ] **Step 2: Write the failing test**

Append to `tests/test_instances_models.py`:

```python
def test_snapshot_counts_plugins_defaults_to_zero() -> None:
    from nexus.instances.models import SnapshotCounts
    counts = SnapshotCounts()
    assert counts.plugins == 0


def test_snapshot_counts_plugins_round_trips() -> None:
    from nexus.instances.models import SnapshotCounts
    counts = SnapshotCounts(plugins=42)
    re = SnapshotCounts.model_validate_json(counts.model_dump_json())
    assert re.plugins == 42
```

- [ ] **Step 3: Run tests to verify failure**

Run: `pytest tests/test_instances_models.py -v -k snapshot_counts_plugins`
Expected: FAIL on missing field.

- [ ] **Step 4: Add the field**

In `src/nexus/instances/models.py`, inside `class SnapshotCounts`, add a fifth field:

```python
    plugins: Annotated[int, Field(ge=0)] = 0
```

- [ ] **Step 5: Run tests to verify pass**

Run: `pytest tests/test_instances_models.py -v -k snapshot_counts`
Expected: all snapshot_counts tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/nexus/instances/models.py tests/test_instances_models.py
git commit -m "feat(instances): add SnapshotCounts.plugins field"
```

---

## Task 9: Registry plugin inventory persistence

**Files:**
- Modify: `src/nexus/instances/registry.py`
- Test: `tests/test_instances_registry.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_instances_registry.py`:

```python
def test_load_plugin_inventory_returns_none_when_file_missing(
    tmp_path: Path,
) -> None:
    from nexus.plugins.models import PluginInventory  # noqa: F401
    from nexus.instances.registry import InstanceRegistry
    registry = InstanceRegistry(tmp_path)
    (tmp_path / "dev" ).mkdir()
    assert registry.load_plugin_inventory("dev") is None


def test_save_and_load_plugin_inventory_round_trips(tmp_path: Path) -> None:
    from datetime import UTC, datetime
    from nexus.plugins.models import PluginInfo, PluginInventory
    from nexus.instances.registry import InstanceRegistry
    (tmp_path / "dev").mkdir()
    registry = InstanceRegistry(tmp_path)
    inv = PluginInventory(
        captured_at=datetime.now(UTC),
        sn_version="Xanadu",
        plugins=(
            PluginInfo(
                plugin_id="com.snc.incident",
                name="Incident",
                version="1.0",
                state="active",
                source="servicenow",
                product_family="ITSM",
                depends_on=(),
                sys_id="abc",
                installed_at=None,
            ),
        ),
    )
    registry.save_plugin_inventory("dev", inv)
    loaded = registry.load_plugin_inventory("dev")
    assert loaded == inv


def test_load_plugin_inventory_raises_when_profile_missing(tmp_path: Path) -> None:
    from nexus.instances.errors import InstanceNotFoundError
    from nexus.instances.registry import InstanceRegistry
    registry = InstanceRegistry(tmp_path)
    with pytest.raises(InstanceNotFoundError):
        registry.load_plugin_inventory("nonexistent")
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_instances_registry.py -v -k plugin_inventory`
Expected: FAIL on missing methods.

- [ ] **Step 3: Implement persistence**

In `src/nexus/instances/registry.py`:

After `_SNAPSHOT = "snapshot.json"` line, add:

```python
_PLUGIN_INVENTORY = "plugins.json"
```

Add this method to `InstanceRegistry` after `save_snapshot`:

```python
    def load_plugin_inventory(self, profile: str) -> "PluginInventory | None":
        """Read plugins.json for a profile if it exists.

        Args:
            profile: Profile name.

        Returns:
            PluginInventory or None if the profile has no plugin scan yet.

        Raises:
            InstanceNotFoundError: If the profile directory does not exist.
        """
        from nexus.plugins.models import PluginInventory

        profile_dir = self._dir(profile)
        if not profile_dir.exists():
            raise InstanceNotFoundError(profile)
        inv_file = profile_dir / _PLUGIN_INVENTORY
        if not inv_file.exists():
            return None
        return PluginInventory.model_validate_json(inv_file.read_text(encoding="utf-8"))

    def save_plugin_inventory(
        self, profile: str, inventory: "PluginInventory"
    ) -> None:
        """Atomically write plugins.json for a profile.

        Args:
            profile: Profile name.
            inventory: PluginInventory to persist.

        Raises:
            InstanceNotFoundError: If the profile directory does not exist.
        """
        profile_dir = self._dir(profile)
        if not profile_dir.exists():
            raise InstanceNotFoundError(profile)
        inv_file = profile_dir / _PLUGIN_INVENTORY
        fd, tmp = tempfile.mkstemp(dir=profile_dir, suffix=".tmp")
        try:
            with open(fd, "w", encoding="utf-8") as f:
                f.write(inventory.model_dump_json(indent=2))
            Path(tmp).replace(inv_file)
        except OSError:
            Path(tmp).unlink(missing_ok=True)
            raise
```

Also add the `TYPE_CHECKING` block near the top of the file (right after `from pydantic import ValidationError`):

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nexus.plugins.models import PluginInventory
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/test_instances_registry.py -v -k plugin_inventory`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/nexus/instances/registry.py tests/test_instances_registry.py
git commit -m "feat(instances): persist plugin inventory next to artifact snapshot"
```

---

## Task 10: Integrate plugin scan into nexus instance refresh

**Files:**
- Modify: `src/nexus/cli.py` (`instance_refresh` function)
- Test: `tests/test_cli_instance.py`

- [ ] **Step 1: Read the current instance_refresh**

Run: `grep -n "def instance_refresh" src/nexus/cli.py`

Locate and read the function (around line 830-860).

- [ ] **Step 2: Write the failing test**

Append to `tests/test_cli_instance.py`:

```python
def test_instance_refresh_with_unknown_profile_still_returns_nonzero() -> None:
    """Regression: this already passes, included as a guard while changing
    instance_refresh internals."""


# Placeholder -- the real test for plugin scanning is covered by
# test_plugins_scanner.py at the unit level. Integration here would
# require a running SN instance.
```

- [ ] **Step 3: Modify `instance_refresh`**

In `src/nexus/cli.py`, at the top of file imports, add (alphabetically):

```python
from nexus.plugins import PluginScanError, PluginScanner
```

Replace the body of `instance_refresh` to scan plugins concurrently with the artifact snapshot. Find the existing block:

```python
    console.print(Notice.info(f"Capturing snapshot from {profile!r}..."))
    try:
        snapshot = asyncio.run(InstanceScanner().scan(meta.url, token, meta.sn_version))
    except SnapshotError as exc:
        err_console.print(Notice.error(str(exc)))
        raise typer.Exit(1) from exc

    registry.save_snapshot(profile, snapshot)
    c = snapshot.counts
    registry.save(meta.model_copy(update={"token_expires_at": new_expiry, "snapshot_counts": c}))
```

Replace with:

```python
    console.print(Notice.info(f"Capturing snapshot from {profile!r}..."))

    async def _run() -> tuple[object, object | None]:
        scanner = InstanceScanner()
        plugin_scanner = PluginScanner()
        snapshot_task = scanner.scan(meta.url, token, meta.sn_version)
        plugin_task = plugin_scanner.scan(meta.url, token, meta.sn_version)
        results = await asyncio.gather(
            snapshot_task, plugin_task, return_exceptions=True
        )
        snap_result, plugin_result = results
        if isinstance(snap_result, BaseException):
            raise snap_result
        if isinstance(plugin_result, PluginScanError):
            err_console.print(Notice.warn(f"Plugin scan failed: {plugin_result}"))
            return snap_result, None
        if isinstance(plugin_result, BaseException):
            raise plugin_result
        return snap_result, plugin_result

    try:
        snapshot, plugin_inventory = asyncio.run(_run())
    except SnapshotError as exc:
        err_console.print(Notice.error(str(exc)))
        raise typer.Exit(1) from exc

    registry.save_snapshot(profile, snapshot)
    if plugin_inventory is not None:
        registry.save_plugin_inventory(profile, plugin_inventory)
    c = snapshot.counts
    plugin_count = len(plugin_inventory.plugins) if plugin_inventory else 0
    counts = c.model_copy(update={"plugins": plugin_count})
    registry.save(
        meta.model_copy(
            update={"token_expires_at": new_expiry, "snapshot_counts": counts}
        )
    )
```

- [ ] **Step 4: Run tests to verify nothing broke**

Run: `pytest tests/test_cli_instance.py -v`
Expected: all existing tests PASS.

- [ ] **Step 5: Lint and type-check**

Run:
```
ruff check src/nexus/cli.py
pyright src/nexus/cli.py
mypy src/nexus/cli.py
```
Expected: all clean.

- [ ] **Step 6: Commit**

```bash
git add src/nexus/cli.py tests/test_cli_instance.py
git commit -m "feat(cli): run plugin scan concurrently with instance refresh"
```

---

## Task 11: nexus plugins list command

**Files:**
- Modify: `src/nexus/cli.py`
- Test: `tests/test_cli_plugins.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_cli_plugins.py
# Tests for the nexus plugins sub-app.
# Author: Pierre Grothe
# Date: 2026-05-11
"""Tests for nexus plugins list / info / export."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from nexus.cache import clear_cache
from nexus.cli import app
from nexus.config.paths import NexusPaths
from nexus.instances.models import InstanceMeta
from nexus.plugins.models import PluginInfo, PluginInventory

__all__: list[str] = []


def _meta(profile: str = "dev") -> InstanceMeta:
    return InstanceMeta.create(
        profile=profile,
        url=f"https://{profile}.service-now.com",
        username="admin",
        client_id="cid",
        sn_version="Xanadu",
        sn_build="04-01-2025_1200",
        instance_name=profile,
        token_expires_in=1800,
    )


def _info(
    plugin_id: str,
    *,
    product: str = "ITSM",
    source: str = "servicenow",
    state: str = "active",
) -> PluginInfo:
    return PluginInfo(
        plugin_id=plugin_id,
        name=plugin_id,
        version="1.0",
        state=state,
        source=source,
        product_family=product,
        depends_on=(),
        sys_id=plugin_id,
        installed_at=None,
    )


def _seed(tmp_path: Path, profile: str, plugins: tuple[PluginInfo, ...]) -> None:
    profile_dir = tmp_path / "instances" / profile
    profile_dir.mkdir(parents=True, exist_ok=True)
    (profile_dir / "meta.json").write_text(
        _meta(profile).model_dump_json(indent=2), encoding="utf-8"
    )
    inv = PluginInventory(
        captured_at=datetime.now(UTC), sn_version="Xanadu", plugins=plugins
    )
    (profile_dir / "plugins.json").write_text(
        inv.model_dump_json(indent=2), encoding="utf-8"
    )


@pytest.fixture
def runner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> CliRunner:
    monkeypatch.setenv("NEXUS_CONFIG_PATH", str(tmp_path / "config.yaml"))
    clear_cache(NexusPaths.from_env)
    return CliRunner()


def test_plugins_list_shows_all_plugins_for_default_instance(
    runner: CliRunner, tmp_path: Path
) -> None:
    _seed(
        tmp_path,
        "dev",
        (_info("com.snc.incident"), _info("com.snc.discovery", product="ITOM")),
    )
    result = runner.invoke(app, ["instance", "use", "dev"])
    assert result.exit_code == 0
    result = runner.invoke(app, ["plugins", "list"])
    assert result.exit_code == 0
    assert "com.snc.incident" in result.output
    assert "com.snc.discovery" in result.output


def test_plugins_list_filters_by_product(runner: CliRunner, tmp_path: Path) -> None:
    _seed(
        tmp_path,
        "dev",
        (_info("com.snc.incident"), _info("com.snc.discovery", product="ITOM")),
    )
    runner.invoke(app, ["instance", "use", "dev"])
    result = runner.invoke(app, ["plugins", "list", "--product", "ITSM"])
    assert "com.snc.incident" in result.output
    assert "com.snc.discovery" not in result.output


def test_plugins_list_filters_by_source(runner: CliRunner, tmp_path: Path) -> None:
    _seed(
        tmp_path,
        "dev",
        (
            _info("com.snc.incident"),
            _info("com.acme.helper", source="store", product="Uncategorized"),
        ),
    )
    runner.invoke(app, ["instance", "use", "dev"])
    result = runner.invoke(app, ["plugins", "list", "--source", "store"])
    assert "com.acme.helper" in result.output
    assert "com.snc.incident" not in result.output


def test_plugins_list_filters_by_state(runner: CliRunner, tmp_path: Path) -> None:
    _seed(
        tmp_path,
        "dev",
        (_info("com.snc.incident"), _info("com.snc.legacy", state="inactive")),
    )
    runner.invoke(app, ["instance", "use", "dev"])
    result = runner.invoke(app, ["plugins", "list", "--state", "inactive"])
    assert "com.snc.legacy" in result.output
    assert "com.snc.incident" not in result.output


def test_plugins_list_warns_when_no_inventory(
    runner: CliRunner, tmp_path: Path
) -> None:
    profile_dir = tmp_path / "instances" / "dev"
    profile_dir.mkdir(parents=True)
    (profile_dir / "meta.json").write_text(
        _meta("dev").model_dump_json(indent=2), encoding="utf-8"
    )
    runner.invoke(app, ["instance", "use", "dev"])
    result = runner.invoke(app, ["plugins", "list"])
    assert "nexus instance refresh" in result.output
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_cli_plugins.py -v`
Expected: FAIL on missing `plugins` sub-app.

- [ ] **Step 3: Add plugins sub-app and list command**

In `src/nexus/cli.py`:

Add to imports:
```python
from nexus.plugins.models import PluginInfo, ProductFamily
```

After the existing `capture_app = typer.Typer(...)` line, add:

```python
plugins_app = typer.Typer(name="plugins", help="Inspect the plugin inventory of registered instances.")
app.add_typer(plugins_app)

_PLUGINS_HELP = [
    ("list", "Show all plugins with optional --product / --source / --state filters"),
    ("info <plugin_id>", "Show full details and dependencies for one plugin"),
    ("export", "Write the inventory to YAML or CSV"),
]
```

After the `instance_register` function ends and before `@capture_app.callback`, add the list command:

```python
def _plugins_for(profile: str) -> tuple[InstanceMeta, tuple[PluginInfo, ...]] | None:
    """Resolve a profile and return its plugin inventory, or None when missing."""
    registry, meta = _resolve_profile(profile)
    inv = registry.load_plugin_inventory(meta.profile)
    if inv is None:
        return None
    return meta, inv.plugins


@plugins_app.command("list")
def plugins_list(
    instance: Annotated[
        str, typer.Option("--instance", help="Instance profile (default: configured default)")
    ] = "",
    product: Annotated[
        str, typer.Option("--product", help="Filter by product family (e.g. ITSM)")
    ] = "",
    source: Annotated[
        str, typer.Option("--source", help="Filter by source (servicenow|store|custom)")
    ] = "",
    state: Annotated[
        str, typer.Option("--state", help="Filter by state (active|inactive)")
    ] = "",
) -> None:
    """Show all plugins installed on the resolved instance."""
    resolved = _plugins_for(instance)
    if resolved is None:
        console.print(Notice.warn("Plugin inventory empty."))
        console.print(Hint(label="Refresh", command="nexus instance refresh"))
        return
    _, plugins = resolved
    if product:
        plugins = tuple(p for p in plugins if p.product_family == product)
    if source:
        plugins = tuple(p for p in plugins if p.source == source)
    if state:
        plugins = tuple(p for p in plugins if p.state == state)
    if not plugins:
        console.print(Notice.info("No plugins match the requested filters."))
        return
    rows: list[list[RenderableType]] = [
        [
            p.plugin_id,
            p.name,
            p.version,
            StatusBadge.ok(p.state) if p.state == "active" else StatusBadge.warn(p.state),
            p.source,
            p.product_family,
        ]
        for p in sorted(plugins, key=lambda x: (x.product_family, x.plugin_id))
    ]
    console.print(
        DataTable(
            title="Plugins",
            columns=[
                DataColumn(header="Plugin ID", width=32),
                DataColumn(header="Name", width=24),
                DataColumn(header="Version", width=10),
                DataColumn(header="State", width=10),
                DataColumn(header="Source", width=11),
                DataColumn(header="Product", width=14),
            ],
            rows=rows,
        )
    )
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/test_cli_plugins.py -v -k list`
Expected: 5 PASS.

- [ ] **Step 5: Lint and type-check**

Run:
```
ruff check src/nexus/cli.py tests/test_cli_plugins.py
pyright src/nexus/cli.py tests/test_cli_plugins.py
mypy src/nexus/cli.py tests/test_cli_plugins.py
```
Expected: all clean.

- [ ] **Step 6: Commit**

```bash
git add src/nexus/cli.py tests/test_cli_plugins.py
git commit -m "feat(cli): add nexus plugins list with product/source/state filters"
```

---

## Task 12: nexus plugins info command

**Files:**
- Modify: `src/nexus/cli.py`
- Modify: `tests/test_cli_plugins.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_cli_plugins.py`:

```python
def test_plugins_info_renders_full_metadata(
    runner: CliRunner, tmp_path: Path
) -> None:
    _seed(
        tmp_path,
        "dev",
        (
            PluginInfo(
                plugin_id="com.snc.discovery",
                name="Discovery",
                version="2.0",
                state="active",
                source="servicenow",
                product_family="ITOM",
                depends_on=("com.snc.cmdb",),
                sys_id="abc",
                installed_at=None,
            ),
        ),
    )
    runner.invoke(app, ["instance", "use", "dev"])
    result = runner.invoke(app, ["plugins", "info", "com.snc.discovery"])
    assert result.exit_code == 0
    assert "com.snc.discovery" in result.output
    assert "Discovery" in result.output
    assert "ITOM" in result.output
    assert "com.snc.cmdb" in result.output


def test_plugins_info_with_unknown_plugin_exits_nonzero(
    runner: CliRunner, tmp_path: Path
) -> None:
    _seed(tmp_path, "dev", (_info("com.snc.incident"),))
    runner.invoke(app, ["instance", "use", "dev"])
    result = runner.invoke(app, ["plugins", "info", "com.snc.missing"])
    assert result.exit_code != 0
    assert "com.snc.missing" in result.output
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_cli_plugins.py -v -k info`
Expected: FAIL on missing command.

- [ ] **Step 3: Add the info command**

In `src/nexus/cli.py`, after `plugins_list`, add:

```python
@plugins_app.command("info")
def plugins_info(
    plugin_id: str,
    instance: Annotated[
        str, typer.Option("--instance", help="Instance profile (default: configured default)")
    ] = "",
) -> None:
    """Show full details and direct dependencies for one plugin."""
    resolved = _plugins_for(instance)
    if resolved is None:
        console.print(Notice.warn("Plugin inventory empty."))
        console.print(Hint(label="Refresh", command="nexus instance refresh"))
        raise typer.Exit(1)
    _, plugins = resolved
    plugin = next((p for p in plugins if p.plugin_id == plugin_id), None)
    if plugin is None:
        err_console.print(Notice.error(f"Plugin {plugin_id!r} not found in inventory."))
        raise typer.Exit(1)
    console.print(
        KeyValuePanel(
            title=plugin.name,
            rows=[
                KvRow(label="Plugin ID", value=plugin.plugin_id),
                KvRow(label="Version", value=plugin.version),
                KvRow(
                    label="State",
                    value=(
                        StatusBadge.ok(plugin.state) if plugin.state == "active"
                        else StatusBadge.warn(plugin.state)
                    ),
                ),
                KvRow(label="Source", value=plugin.source),
                KvRow(label="Product family", value=plugin.product_family),
                KvRow(label="sys_id", value=plugin.sys_id),
                KvRow(
                    label="Installed at",
                    value=(
                        plugin.installed_at.strftime("%Y-%m-%d %H:%M UTC")
                        if plugin.installed_at else "-"
                    ),
                ),
            ],
        )
    )
    if plugin.depends_on:
        console.print(
            Hint(
                label="Depends on",
                command=", ".join(plugin.depends_on),
            )
        )
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/test_cli_plugins.py -v -k info`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/nexus/cli.py tests/test_cli_plugins.py
git commit -m "feat(cli): add nexus plugins info"
```

---

## Task 13: nexus plugins export command

**Files:**
- Modify: `src/nexus/cli.py`
- Modify: `tests/test_cli_plugins.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_cli_plugins.py`:

```python
def test_plugins_export_yaml_round_trips_through_plugin_inventory(
    runner: CliRunner, tmp_path: Path
) -> None:
    _seed(tmp_path, "dev", (_info("com.snc.incident"),))
    runner.invoke(app, ["instance", "use", "dev"])
    out_file = tmp_path / "out.yaml"
    result = runner.invoke(
        app,
        ["plugins", "export", "--format", "yaml", "--out", str(out_file)],
    )
    assert result.exit_code == 0
    content = out_file.read_text(encoding="utf-8")
    assert "com.snc.incident" in content
    assert "Plugins:" in content or "plugins:" in content


def test_plugins_export_csv_emits_one_row_per_plugin(
    runner: CliRunner, tmp_path: Path
) -> None:
    _seed(
        tmp_path,
        "dev",
        (_info("com.snc.incident"), _info("com.snc.problem")),
    )
    runner.invoke(app, ["instance", "use", "dev"])
    out_file = tmp_path / "out.csv"
    result = runner.invoke(
        app,
        ["plugins", "export", "--format", "csv", "--out", str(out_file)],
    )
    assert result.exit_code == 0
    lines = out_file.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3  # header + 2 rows
    assert lines[0].startswith("plugin_id,")


def test_plugins_export_rejects_unknown_format(
    runner: CliRunner, tmp_path: Path
) -> None:
    _seed(tmp_path, "dev", (_info("com.snc.incident"),))
    runner.invoke(app, ["instance", "use", "dev"])
    result = runner.invoke(
        app,
        ["plugins", "export", "--format", "xml", "--out", str(tmp_path / "x")],
    )
    assert result.exit_code != 0
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_cli_plugins.py -v -k export`
Expected: FAIL on missing command.

- [ ] **Step 3: Add the export command**

Add to `src/nexus/cli.py` imports:

```python
import csv
```

After `plugins_info`, add:

```python
_PLUGIN_CSV_FIELDS = (
    "plugin_id", "name", "version", "state", "source",
    "product_family", "sys_id", "installed_at",
)


@plugins_app.command("export")
def plugins_export(
    instance: Annotated[
        str, typer.Option("--instance", help="Instance profile (default: configured default)")
    ] = "",
    fmt: Annotated[
        str, typer.Option("--format", help="Output format (yaml|csv)")
    ] = "yaml",
    out: Annotated[
        str, typer.Option("--out", help="Output file path (default: plugins.<ext>)")
    ] = "",
) -> None:
    """Write the plugin inventory to a YAML or CSV file."""
    if fmt not in ("yaml", "csv"):
        err_console.print(Notice.error(f"Unknown format {fmt!r}; use yaml or csv."))
        raise typer.Exit(1)
    resolved = _plugins_for(instance)
    if resolved is None:
        console.print(Notice.warn("Plugin inventory empty."))
        console.print(Hint(label="Refresh", command="nexus instance refresh"))
        raise typer.Exit(1)
    _, plugins = resolved
    path = Path(out) if out else Path(f"plugins.{fmt}")
    if fmt == "yaml":
        payload = {
            "plugins": [
                {
                    field: getattr(p, field)
                    if field != "installed_at"
                    else (p.installed_at.isoformat() if p.installed_at else None)
                    for field in _PLUGIN_CSV_FIELDS
                }
                for p in plugins
            ]
        }
        path.write_text(_yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    else:
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(_PLUGIN_CSV_FIELDS)
            for p in plugins:
                writer.writerow(
                    [
                        p.plugin_id,
                        p.name,
                        p.version,
                        p.state,
                        p.source,
                        p.product_family,
                        p.sys_id,
                        p.installed_at.isoformat() if p.installed_at else "",
                    ]
                )
    console.print(Notice.info(f"Wrote {len(plugins)} plugins to {path}"))
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/test_cli_plugins.py -v -k export`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/nexus/cli.py tests/test_cli_plugins.py
git commit -m "feat(cli): add nexus plugins export with yaml/csv formats"
```

---

## Task 14: plugins_app callback (no-arg behaviour)

**Files:**
- Modify: `src/nexus/cli.py`
- Modify: `tests/test_cli_plugins.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cli_plugins.py`:

```python
def test_plugins_no_subcommand_shows_list_and_command_guide(
    runner: CliRunner, tmp_path: Path
) -> None:
    _seed(tmp_path, "dev", (_info("com.snc.incident"),))
    runner.invoke(app, ["instance", "use", "dev"])
    result = runner.invoke(app, ["plugins"])
    assert result.exit_code == 0
    assert "com.snc.incident" in result.output
    assert "nexus plugins" in result.output  # CommandGuide title
    assert "list" in result.output
    assert "info" in result.output
    assert "export" in result.output
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_cli_plugins.py -v -k no_subcommand`
Expected: FAIL.

- [ ] **Step 3: Add the callback**

In `src/nexus/cli.py`, after the `plugins_app = typer.Typer(...)` definition and before `plugins_list`, add:

```python
@plugins_app.callback(invoke_without_command=True)
def plugins_callback(ctx: typer.Context) -> None:
    """Show the plugin inventory and the available subcommands."""
    if ctx.invoked_subcommand is not None:
        return
    plugins_list()  # default flags: empty strings, no filtering
    console.print(CommandGuide(app_name="nexus plugins", items=_PLUGINS_HELP))
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/test_cli_plugins.py -v -k no_subcommand`
Expected: PASS.

- [ ] **Step 5: Run the full plugins test file**

Run: `pytest tests/test_cli_plugins.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add src/nexus/cli.py tests/test_cli_plugins.py
git commit -m "feat(cli): plugins_app callback shows list + CommandGuide"
```

---

## Task 15: Final verification and ratchet refresh

**Files:**
- Modify: `.ratchet.json`

- [ ] **Step 1: Run full quality suite**

Run:
```
ruff check src/nexus tests
black --check src/nexus tests
pyright src/nexus tests
mypy src/nexus
pytest --ignore=tests/test_updater_runner.py -q
```
Expected: all clean except the 4 known pre-existing failures.

If black fails, run `black src/nexus tests` and commit the formatting separately.

- [ ] **Step 2: Generate fresh coverage**

Run:
```
pytest --ignore=tests/test_updater_runner.py --cov=nexus --cov-report=json --cov-fail-under=0 -q --no-header --tb=no
```

- [ ] **Step 3: Update .ratchet.json**

Inspect coverage.json for the new modules:

```python
python -c "
import json
data = json.loads(open('coverage.json').read())
for k, v in sorted(data['files'].items()):
    nk = k.replace('\\\\', '/')
    if '/nexus/plugins/' in nk or 'instances/registry.py' in nk or 'instances/scanner.py' in nk or 'instances/models.py' in nk or 'cli.py' in nk:
        s = v['summary']
        rel = nk[nk.index('nexus/'):]
        mod = rel.replace('/', '.').removesuffix('.py')
        print(f'{mod}: covered={s[\"covered_lines\"]} total={s[\"num_statements\"]}')
"
```

Update `.ratchet.json` with the printed `covered_lines` / `total_lines` for:
- `nexus.cli` (now larger)
- `nexus.instances.models` (added plugins field)
- `nexus.instances.registry` (added two methods)
- `nexus.plugins.__init__`
- `nexus.plugins.errors`
- `nexus.plugins.models`
- `nexus.plugins.product_families`
- `nexus.plugins.scanner`

Pre-existing baselines must only be raised, never lowered (ratchet invariant).

- [ ] **Step 4: Verify ratchet still passes**

Run: `pytest --ignore=tests/test_updater_runner.py -q --tb=no | tail`

Expected: same 4 pre-existing failures, all new tests pass.

- [ ] **Step 5: Smoke render the new commands**

Run:
```
PYTHONIOENCODING=utf-8 .venv/Scripts/nexus plugins --help
PYTHONIOENCODING=utf-8 .venv/Scripts/nexus plugins list --help
PYTHONIOENCODING=utf-8 .venv/Scripts/nexus plugins info --help
PYTHONIOENCODING=utf-8 .venv/Scripts/nexus plugins export --help
```

Expected: each prints help text without traceback.

- [ ] **Step 6: Commit**

```bash
git add .ratchet.json
git commit -m "chore: refresh ratchet baselines for the plugins layer"
```

- [ ] **Step 7: Verify branch state**

Run: `git log --oneline main..HEAD | head -20`

Expected: 14 new commits (one per task plus the final ratchet commit) on top of the existing branch.

---

## Final self-review

Coverage of spec sections:

- Goal -- Task 1-14 collectively deliver the read-only plugin inventory CLI.
- Layer placement -- Task 1, 2, 4, 6, 7 create `src/nexus/plugins/`.
- Data source (v_plugin + sys_store_app, dedupe) -- Task 6.
- Pydantic models -- Task 1.
- Product-family curation -- Task 3, 4.
- Integration with instance refresh -- Task 8, 9, 10.
- CLI surface -- Task 11, 12, 13, 14.
- Reuse from existing layers -- Tasks 10-14 use `_resolve_profile`, `nexus.ui` components.
- Errors -- Task 2.
- Testing strategy -- Each task has TDD red/green pairs; Task 5 ships the canned fake data.
- File layout -- File-structure section above matches the spec's file layout.
- Out of scope -- explicitly deferred and not introduced.

Type consistency check:

- `PluginInfo` field names (`plugin_id`, `state`, `source`, `product_family`,
  `depends_on`, `installed_at`) are identical in every task.
- `PluginInventory.plugins` is `tuple[PluginInfo, ...]` everywhere.
- `ProductFamily` enum values match the YAML payload values exactly
  (e.g. ``"ITSM"``, ``"SecOps"``, ``"Uncategorized"``).
- `PluginScanner.scan(url, token, sn_version)` signature matches the
  `InstanceScanner.scan` signature used in Task 10's gather call.
- `InstanceRegistry.load_plugin_inventory` and `save_plugin_inventory`
  signatures match between Task 9 and Task 10.

No placeholders, no "TBD", no "similar to Task N" shortcuts. Each step shows
exact code or the exact command. Plan is ready for execution.
