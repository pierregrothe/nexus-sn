# Plugin Advisories Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `nexus plugins advisories`, a CLI command that joins a captured plugin inventory against three curated YAML data files (EOL, CVE, license) and renders the resulting findings as Rich DataTables.

**Architecture:** Pure-function design matching sub-projects B and C. New `nexus.plugins.advisories` module owns the data models (`AdvisoryFinding`, `AdvisorySet`, `Severity`, `AdvisoryType`), three per-type checker functions, a `compute_advisories` orchestrator, and an `AdvisoryDatabase` loader. `PluginInfo` gets one new field (`vendor`); the scanner populates it from `sys_store_app.vendor`. A new `nexus plugins advisories` subcommand wires the pieces together.

**Tech Stack:** Python 3.14, Pydantic v2 (frozen+strict+extra=forbid), `packaging.specifiers.SpecifierSet`, `packaging.version.parse`, `yaml.safe_load`, `importlib.resources`, Typer, Rich. Tests use real fakes (no mocks).

**Branch:** `feat/plugins-advisories` (stacked on PR #13 -- `feat/plugins-update-detection`).

**Spec:** `docs/superpowers/specs/2026-05-11-plugin-advisories-design.md`

---

## File Map

**Create:**
- `src/nexus/plugins/advisories.py` -- loaders, checkers, orchestrator
- `src/nexus/plugins/data/eol.yaml` -- curated EOL list
- `src/nexus/plugins/data/cves.yaml` -- curated CVE list
- `src/nexus/plugins/data/licenses.yaml` -- vendor allow/forbid policy
- `tests/test_plugins_advisories.py`
- `tests/test_cli_plugins_advisories.py`
- `tests/fakes/fake_advisory_data.py`

**Modify:**
- `src/nexus/plugins/models.py` -- add `vendor` to PluginInfo; add Severity, AdvisoryType, AdvisoryFinding, AdvisorySet
- `src/nexus/plugins/scanner.py` -- populate vendor in `_from_store`
- `src/nexus/plugins/errors.py` -- add PluginAdvisoryDataError
- `src/nexus/plugins/__init__.py` -- re-export new symbols
- `src/nexus/cli.py` -- new `advisories` subcommand + update `_PLUGINS_HELP`
- `tests/fakes/fake_plugin_data.py` -- already has vendor on store rows (no edit needed)
- `tests/test_plugins_models.py` -- 4 new tests
- `tests/test_plugins_scanner.py` -- 2 new tests
- `pyproject.toml` -- ensure `src/nexus/plugins/data/*.yaml` ships in the wheel
- `.ratchet.json` -- new module baselines + cli.py bump

---

## Task 1: Severity / AdvisoryType enums + AdvisoryFinding / AdvisorySet

**Files:**
- Modify: `src/nexus/plugins/models.py`
- Test: `tests/test_plugins_models.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_plugins_models.py`:

```python
from nexus.plugins.models import (
    AdvisoryFinding,
    AdvisorySet,
    AdvisoryType,
    Severity,
)


def test_severity_has_four_levels():
    assert {s.value for s in Severity} == {"critical", "high", "medium", "low"}


def test_advisory_type_has_three_categories():
    assert {t.value for t in AdvisoryType} == {"eol", "cve", "license"}


def test_advisory_finding_accepts_all_required_fields():
    finding = AdvisoryFinding(
        plugin_id="com.x",
        plugin_name="X",
        plugin_version="1.0",
        advisory_type=AdvisoryType.CVE,
        severity=Severity.HIGH,
        summary="XSS",
        details="CVE-2024-1",
    )
    assert finding.advisory_type is AdvisoryType.CVE
    assert finding.severity is Severity.HIGH


def test_advisory_set_is_frozen():
    s = AdvisorySet(findings=())
    try:
        s.findings = (None,)  # type: ignore[misc]
    except Exception:
        return
    raise AssertionError("AdvisorySet must be frozen")
```

NOTE: Remove the `# type: ignore[misc]` before committing -- the project bans type-ignore everywhere. Use `setattr(s, "findings", (None,))` instead:

```python
def test_advisory_set_is_frozen():
    s = AdvisorySet(findings=())
    raised = False
    try:
        setattr(s, "findings", (None,))
    except Exception:
        raised = True
    assert raised, "AdvisorySet must be frozen"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_plugins_models.py -v -k "severity or advisory_type or advisory_finding or advisory_set"`

Expected: FAIL with ImportError (symbols not yet defined).

- [ ] **Step 3: Add the four types to `src/nexus/plugins/models.py`**

Update the imports at the top (already has `StrEnum`, `Literal`, `BaseModel`, `ConfigDict`).

Append below the `PluginInventory` definition:

```python
class Severity(StrEnum):
    """Normalized severity for advisory findings."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class AdvisoryType(StrEnum):
    """The three advisory categories surfaced by ``nexus plugins advisories``."""

    EOL = "eol"
    CVE = "cve"
    LICENSE = "license"


class AdvisoryFinding(BaseModel):
    """One advisory hit on one plugin.

    Attributes:
        plugin_id: SN plugin identifier.
        plugin_name: Display name copied from the inventory.
        plugin_version: Installed version copied from the inventory.
        advisory_type: Which checker produced this finding.
        severity: Normalized severity.
        summary: One-line headline rendered as a table cell.
        details: Type-specific detail (CVE id, EOL date, vendor name).
    """

    model_config = _FROZEN

    plugin_id: str
    plugin_name: str
    plugin_version: str
    advisory_type: AdvisoryType
    severity: Severity
    summary: str
    details: str


class AdvisorySet(BaseModel):
    """All findings produced by one advisory scan over an inventory.

    Attributes:
        findings: All findings, ordered by ``(severity desc, plugin_id asc)``.
    """

    model_config = _FROZEN

    findings: tuple[AdvisoryFinding, ...]
```

Update `__all__` at the top of the file:

```python
__all__ = [
    "AdvisoryFinding",
    "AdvisorySet",
    "AdvisoryType",
    "PluginInfo",
    "PluginInventory",
    "ProductFamily",
    "Severity",
]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_plugins_models.py -v -k "severity or advisory_type or advisory_finding or advisory_set"`

Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/nexus/plugins/models.py tests/test_plugins_models.py
git commit -m "feat(plugins): add Severity, AdvisoryType, AdvisoryFinding, AdvisorySet models"
```

---

## Task 2: vendor field on PluginInfo

**Files:**
- Modify: `src/nexus/plugins/models.py:54-65` (PluginInfo)
- Test: `tests/test_plugins_models.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_plugins_models.py`:

```python
def test_plugin_info_accepts_vendor_field():
    info = PluginInfo(
        plugin_id="com.x",
        name="X",
        version="1.0",
        state="active",
        source="store",
        product_family="ITSM",
        depends_on=(),
        sys_id="abc",
        installed_at=None,
        vendor="Acme Corp",
    )
    assert info.vendor == "Acme Corp"


def test_plugin_info_defaults_vendor_to_empty_string():
    info = PluginInfo(
        plugin_id="com.x",
        name="X",
        version="1.0",
        state="active",
        source="servicenow",
        product_family="ITSM",
        depends_on=(),
        sys_id="abc",
        installed_at=None,
    )
    assert info.vendor == ""
```

`PluginInfo` is already imported in this test file from earlier tasks.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_plugins_models.py -v -k "plugin_info_accepts_vendor or plugin_info_defaults_vendor"`

Expected: FAIL with `vendor` unrecognized field error from Pydantic (`extra="forbid"`).

- [ ] **Step 3: Add `vendor` field to PluginInfo**

In `src/nexus/plugins/models.py`, update PluginInfo. Add `vendor: str = ""` after `latest_version`:

```python
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
        vendor: Publisher name from ``sys_store_app.vendor``. Empty string
            for v_plugin-only records or when the field is absent.
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
    vendor: str = ""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_plugins_models.py -v`

Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/nexus/plugins/models.py tests/test_plugins_models.py
git commit -m "feat(plugins): add vendor field to PluginInfo"
```

---

## Task 3: Scanner populates vendor from sys_store_app

**Files:**
- Modify: `src/nexus/plugins/scanner.py:116-131` (`_from_store`)
- Test: `tests/test_plugins_scanner.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_plugins_scanner.py`:

```python
import asyncio
import httpx

from nexus.plugins.scanner import PluginScanner
from tests.fakes.fake_plugin_data import SYS_STORE_APP_ROWS, V_PLUGIN_ROWS


def _scan_with_fakes() -> tuple[object, ...]:
    """Run PluginScanner against canned fake rows and return plugins."""

    def handler(request: httpx.Request) -> httpx.Response:
        if "v_plugin" in str(request.url):
            return httpx.Response(200, json={"result": V_PLUGIN_ROWS})
        return httpx.Response(200, json={"result": SYS_STORE_APP_ROWS})

    transport = httpx.MockTransport(handler)
    scanner = PluginScanner(transport=transport)
    inv = asyncio.run(scanner.scan("https://x.example", "tok", "Washington"))
    return tuple(inv.plugins)


def test_scan_populates_vendor_from_store_row():
    plugins = _scan_with_fakes()
    acme = next(p for p in plugins if p.plugin_id == "com.acme.helper")
    assert acme.vendor == "Acme Corp"


def test_scan_leaves_vendor_empty_for_v_plugin_only_record():
    plugins = _scan_with_fakes()
    legacy = next(p for p in plugins if p.plugin_id == "com.snc.legacy_only")
    assert legacy.vendor == ""
```

NOTE on imports: `tests/test_plugins_scanner.py` may already define a helper that wraps the scanner against fakes. If it does, reuse that helper instead of declaring `_scan_with_fakes`. Inspect the file first; only add what's not already there.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_plugins_scanner.py -v -k "vendor"`

Expected: FAIL -- `acme.vendor == "Acme Corp"` fails because the scanner does not yet set the field (PluginInfo's default `""` is used).

- [ ] **Step 3: Update `_from_store` in `src/nexus/plugins/scanner.py`**

Locate the `_from_store` method (currently around line 116). Add `vendor=vendor` to the PluginInfo constructor call. The `vendor` local is already in scope:

```python
def _from_store(self, row: dict[str, object]) -> PluginInfo:
    """Build a PluginInfo from a sys_store_app row."""
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
        latest_version=str(row.get("latest_version", "")) or None,
        vendor=vendor,
    )
```

`_from_v_plugin` is unchanged -- it relies on the new `""` default.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_plugins_scanner.py -v`

Expected: All scanner tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/nexus/plugins/scanner.py tests/test_plugins_scanner.py
git commit -m "feat(plugins): populate vendor from sys_store_app in scanner"
```

---

## Task 4: PluginAdvisoryDataError

**Files:**
- Modify: `src/nexus/plugins/errors.py`
- Test: `tests/test_plugins_advisories.py` (new file)

- [ ] **Step 1: Create test file with file header and failing test**

Create `tests/test_plugins_advisories.py`:

```python
# tests/test_plugins_advisories.py
# Tests for the plugin advisories layer.
# Author: Pierre Grothe
# Date: 2026-05-11
"""Tests for src/nexus/plugins/advisories.py and PluginAdvisoryDataError."""

import pytest

from nexus.plugins.errors import PluginAdvisoryDataError


def test_plugin_advisory_data_error_carries_reason():
    err = PluginAdvisoryDataError("eol.yaml: parse failed")
    assert str(err) == "eol.yaml: parse failed"


def test_plugin_advisory_data_error_is_exception_subclass():
    assert issubclass(PluginAdvisoryDataError, Exception)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_plugins_advisories.py -v`

Expected: FAIL with `ImportError: cannot import name 'PluginAdvisoryDataError'`.

- [ ] **Step 3: Add PluginAdvisoryDataError to `src/nexus/plugins/errors.py`**

Append:

```python
class PluginAdvisoryDataError(Exception):
    """Raised when one of the bundled advisory YAML files is unreadable or invalid.

    Wraps the underlying yaml/Pydantic/Specifier error message in its message.
    """

    def __init__(self, message: str) -> None:
        """Store the reason message."""
        super().__init__(message)
```

Update `__all__`:

```python
__all__ = ["PluginAdvisoryDataError", "PluginScanError"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_plugins_advisories.py -v`

Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/nexus/plugins/errors.py tests/test_plugins_advisories.py
git commit -m "feat(plugins): add PluginAdvisoryDataError"
```

---

## Task 5: EolEntry + _check_eol

**Files:**
- Create: `src/nexus/plugins/advisories.py`
- Modify: `tests/test_plugins_advisories.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_plugins_advisories.py`:

```python
from datetime import UTC, date, datetime

from nexus.plugins.advisories import EolEntry, _check_eol
from nexus.plugins.models import AdvisoryType, PluginInfo, Severity


def _info(plugin_id: str = "com.x", version: str = "1.0") -> PluginInfo:
    return PluginInfo(
        plugin_id=plugin_id,
        name="X",
        version=version,
        state="active",
        source="store",
        product_family="ITSM",
        depends_on=(),
        sys_id="abc",
        installed_at=None,
        vendor="Acme Corp",
    )


def test_check_eol_flags_past_effective_date_as_high():
    table = {
        "com.x": EolEntry(
            plugin_id="com.x",
            status="end_of_life",
            effective=date(2020, 1, 1),
            replacement="com.y",
            notes="replaced",
        ),
    }
    findings = _check_eol(_info(), table, today=date(2026, 5, 11))
    assert len(findings) == 1
    assert findings[0].severity is Severity.HIGH
    assert findings[0].advisory_type is AdvisoryType.EOL
    assert findings[0].details == "End-of-life 2020-01-01; replacement: com.y"


def test_check_eol_flags_future_effective_date_as_medium():
    table = {
        "com.x": EolEntry(
            plugin_id="com.x",
            status="end_of_life",
            effective=date(2099, 1, 1),
            replacement=None,
            notes="",
        ),
    }
    findings = _check_eol(_info(), table, today=date(2026, 5, 11))
    assert findings[0].severity is Severity.MEDIUM


def test_check_eol_flags_deprecated_as_medium():
    table = {
        "com.x": EolEntry(
            plugin_id="com.x",
            status="deprecated",
            effective=date(2020, 1, 1),
            replacement=None,
            notes="",
        ),
    }
    findings = _check_eol(_info(), table, today=date(2026, 5, 11))
    assert findings[0].severity is Severity.MEDIUM


def test_check_eol_returns_empty_when_plugin_absent_from_table():
    findings = _check_eol(_info(), {}, today=date(2026, 5, 11))
    assert findings == ()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_plugins_advisories.py -v -k "eol"`

Expected: FAIL with `ImportError` -- `advisories` module does not exist.

- [ ] **Step 3: Create `src/nexus/plugins/advisories.py`**

```python
# src/nexus/plugins/advisories.py
# EOL / CVE / license advisory checkers and loaders.
# Author: Pierre Grothe
# Date: 2026-05-11
"""Plugin advisory layer: EOL, CVE, and license findings."""

from __future__ import annotations

import logging
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict

from nexus.plugins.models import AdvisoryFinding, AdvisoryType, PluginInfo, Severity

__all__ = [
    "EolEntry",
    "_check_eol",
]

log = logging.getLogger(__name__)

_FROZEN = ConfigDict(frozen=True, strict=True, extra="forbid")


class EolEntry(BaseModel):
    """One row of the curated EOL table.

    Attributes:
        plugin_id: SN plugin identifier this entry applies to.
        status: ``end_of_life`` or ``deprecated``.
        effective: Calendar date the status takes effect.
        replacement: Optional successor plugin id.
        notes: Free-form maintainer note rendered into ``details``.
    """

    model_config = _FROZEN

    plugin_id: str
    status: Literal["end_of_life", "deprecated"]
    effective: date
    replacement: str | None = None
    notes: str = ""


def _check_eol(
    plugin: PluginInfo,
    table: dict[str, EolEntry],
    *,
    today: date,
) -> tuple[AdvisoryFinding, ...]:
    """Produce zero or one AdvisoryFinding for plugin's EOL status.

    Args:
        plugin: The plugin to evaluate.
        table: ``plugin_id -> EolEntry`` lookup.
        today: Reference date for past/future comparison. Injected so
            tests are deterministic.

    Returns:
        Tuple of at most one AdvisoryFinding.
    """
    entry = table.get(plugin.plugin_id)
    if entry is None:
        return ()
    if entry.status == "end_of_life" and entry.effective <= today:
        severity = Severity.HIGH
    else:
        severity = Severity.MEDIUM
    summary = (
        f"End-of-life {entry.effective.isoformat()}"
        if entry.status == "end_of_life"
        else f"Deprecated (effective {entry.effective.isoformat()})"
    )
    details_parts = [f"End-of-life {entry.effective.isoformat()}"] if entry.status == "end_of_life" else [f"Deprecated {entry.effective.isoformat()}"]
    if entry.replacement:
        details_parts.append(f"replacement: {entry.replacement}")
    return (
        AdvisoryFinding(
            plugin_id=plugin.plugin_id,
            plugin_name=plugin.name,
            plugin_version=plugin.version,
            advisory_type=AdvisoryType.EOL,
            severity=severity,
            summary=summary,
            details="; ".join(details_parts),
        ),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_plugins_advisories.py -v -k "eol"`

Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/nexus/plugins/advisories.py tests/test_plugins_advisories.py
git commit -m "feat(plugins): add EolEntry and _check_eol"
```

---

## Task 6: CveEntry + _check_cves

**Files:**
- Modify: `src/nexus/plugins/advisories.py`
- Modify: `tests/test_plugins_advisories.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_plugins_advisories.py`:

```python
from nexus.plugins.advisories import CveEntry, _check_cves


def _cve(cve_id: str, plugin_id: str, severity: Severity, spec: str, fixed_in: str = "") -> CveEntry:
    return CveEntry(
        cve_id=cve_id,
        plugin_id=plugin_id,
        severity=severity,
        affected_versions=spec,
        fixed_in=fixed_in,
        summary=f"Issue {cve_id}",
    )


def test_check_cves_flags_matching_version_in_range():
    table = {"com.x": (_cve("CVE-1", "com.x", Severity.HIGH, ">=1.0,<2.0", "2.0"),)}
    findings = _check_cves(_info(version="1.5"), table)
    assert len(findings) == 1
    assert findings[0].advisory_type is AdvisoryType.CVE
    assert findings[0].severity is Severity.HIGH
    assert "CVE-1" in findings[0].details


def test_check_cves_skips_version_above_range():
    table = {"com.x": (_cve("CVE-1", "com.x", Severity.HIGH, ">=1.0,<2.0"),)}
    findings = _check_cves(_info(version="2.5"), table)
    assert findings == ()


def test_check_cves_skips_version_below_range():
    table = {"com.x": (_cve("CVE-1", "com.x", Severity.HIGH, ">=1.0,<2.0"),)}
    findings = _check_cves(_info(version="0.9"), table)
    assert findings == ()


def test_check_cves_returns_multiple_findings_for_multiple_cves():
    table = {
        "com.x": (
            _cve("CVE-1", "com.x", Severity.HIGH, ">=1.0"),
            _cve("CVE-2", "com.x", Severity.CRITICAL, ">=1.0"),
        ),
    }
    findings = _check_cves(_info(version="1.5"), table)
    assert {f.details.split(":")[0].strip() for f in findings} == {"CVE-1", "CVE-2"}


def test_check_cves_skips_unparseable_plugin_version():
    table = {"com.x": (_cve("CVE-1", "com.x", Severity.HIGH, ">=1.0"),)}
    findings = _check_cves(_info(version="not-a-version-string!!!"), table)
    assert findings == ()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_plugins_advisories.py -v -k "cves"`

Expected: FAIL -- `CveEntry` / `_check_cves` not defined.

- [ ] **Step 3: Add CveEntry and _check_cves to `src/nexus/plugins/advisories.py`**

Add these imports at the top:

```python
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, parse as parse_version
from pydantic import field_validator
```

Append to the module body:

```python
class CveEntry(BaseModel):
    """One row of the curated CVE table.

    Attributes:
        cve_id: e.g. ``CVE-2024-1234``.
        plugin_id: SN plugin identifier this CVE affects.
        severity: Verbatim from the YAML.
        affected_versions: PEP 440 SpecifierSet string.
        fixed_in: Version string where the issue is resolved; empty if none.
        summary: One-line headline.
    """

    model_config = _FROZEN

    cve_id: str
    plugin_id: str
    severity: Severity
    affected_versions: str
    fixed_in: str = ""
    summary: str

    @field_validator("affected_versions")
    @classmethod
    def _validate_specifier(cls, value: str) -> str:
        """Reject malformed specifier strings at load time."""
        try:
            SpecifierSet(value)
        except InvalidSpecifier as exc:
            raise ValueError(f"invalid SpecifierSet: {value!r}: {exc}") from exc
        return value


def _check_cves(
    plugin: PluginInfo,
    table: dict[str, tuple[CveEntry, ...]],
) -> tuple[AdvisoryFinding, ...]:
    """Produce zero or more AdvisoryFindings for known CVEs against the plugin.

    Args:
        plugin: The plugin to evaluate.
        table: ``plugin_id -> tuple of CveEntry`` lookup.

    Returns:
        Tuple of AdvisoryFindings, one per matching CVE.
    """
    entries = table.get(plugin.plugin_id, ())
    if not entries:
        return ()
    try:
        version = parse_version(plugin.version)
    except InvalidVersion:
        log.debug(
            "advisories: skipping CVE check for %s -- unparseable version %r",
            plugin.plugin_id,
            plugin.version,
        )
        return ()
    findings: list[AdvisoryFinding] = []
    for entry in entries:
        if version not in SpecifierSet(entry.affected_versions):
            continue
        details = f"{entry.cve_id}: affected {entry.affected_versions}"
        if entry.fixed_in:
            details += f"; fixed in {entry.fixed_in}"
        findings.append(
            AdvisoryFinding(
                plugin_id=plugin.plugin_id,
                plugin_name=plugin.name,
                plugin_version=plugin.version,
                advisory_type=AdvisoryType.CVE,
                severity=entry.severity,
                summary=entry.summary,
                details=details,
            )
        )
    return tuple(findings)
```

Extend `__all__`:

```python
__all__ = [
    "CveEntry",
    "EolEntry",
    "_check_cves",
    "_check_eol",
]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_plugins_advisories.py -v -k "cves"`

Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/nexus/plugins/advisories.py tests/test_plugins_advisories.py
git commit -m "feat(plugins): add CveEntry and _check_cves with PEP 440 matching"
```

---

## Task 7: LicensePolicy + _check_license

**Files:**
- Modify: `src/nexus/plugins/advisories.py`
- Modify: `tests/test_plugins_advisories.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_plugins_advisories.py`:

```python
from nexus.plugins.advisories import LicensePolicy, _check_license


def test_check_license_flags_forbidden_vendor_as_high():
    policy = LicensePolicy(
        allowed_vendors=("ServiceNow",),
        forbidden_vendors=("Sketchy LLC",),
    )
    plugin = _info()  # vendor="Acme Corp" -- not forbidden
    sketchy = PluginInfo(**{**plugin.model_dump(), "vendor": "Sketchy LLC"})
    findings = _check_license(sketchy, policy)
    assert len(findings) == 1
    assert findings[0].severity is Severity.HIGH
    assert "Sketchy LLC" in findings[0].details


def test_check_license_flags_unknown_vendor_as_medium():
    policy = LicensePolicy(
        allowed_vendors=("ServiceNow",),
        forbidden_vendors=(),
    )
    findings = _check_license(_info(), policy)  # vendor="Acme Corp" -- unknown
    assert len(findings) == 1
    assert findings[0].severity is Severity.MEDIUM


def test_check_license_skips_allowed_vendor():
    policy = LicensePolicy(
        allowed_vendors=("Acme Corp",),
        forbidden_vendors=(),
    )
    findings = _check_license(_info(), policy)
    assert findings == ()


def test_check_license_skips_empty_vendor_when_allow_list_empty():
    policy = LicensePolicy(allowed_vendors=(), forbidden_vendors=())
    no_vendor = PluginInfo(**{**_info().model_dump(), "vendor": ""})
    findings = _check_license(no_vendor, policy)
    assert findings == ()


def test_check_license_skips_empty_vendor_when_allow_list_non_empty():
    policy = LicensePolicy(allowed_vendors=("ServiceNow",), forbidden_vendors=())
    no_vendor = PluginInfo(**{**_info().model_dump(), "vendor": ""})
    findings = _check_license(no_vendor, policy)
    assert findings == ()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_plugins_advisories.py -v -k "license"`

Expected: FAIL -- `LicensePolicy` / `_check_license` undefined.

- [ ] **Step 3: Add LicensePolicy and _check_license**

Append to `src/nexus/plugins/advisories.py`:

```python
class LicensePolicy(BaseModel):
    """Vendor allow / forbid lists.

    Attributes:
        allowed_vendors: Vendors that always pass the license check.
        forbidden_vendors: Vendors that always trigger a high-severity finding.
    """

    model_config = _FROZEN

    allowed_vendors: tuple[str, ...]
    forbidden_vendors: tuple[str, ...]


def _check_license(
    plugin: PluginInfo,
    policy: LicensePolicy,
) -> tuple[AdvisoryFinding, ...]:
    """Produce zero or one AdvisoryFinding for the plugin's vendor.

    Args:
        plugin: The plugin to evaluate.
        policy: Allow / forbid lists.

    Returns:
        Tuple of at most one AdvisoryFinding.
    """
    vendor = plugin.vendor
    if not vendor:
        return ()
    if vendor in policy.forbidden_vendors:
        severity = Severity.HIGH
        summary = "Forbidden vendor"
    elif vendor in policy.allowed_vendors:
        return ()
    elif policy.allowed_vendors:
        severity = Severity.MEDIUM
        summary = "Vendor not in allow-list"
    else:
        return ()
    return (
        AdvisoryFinding(
            plugin_id=plugin.plugin_id,
            plugin_name=plugin.name,
            plugin_version=plugin.version,
            advisory_type=AdvisoryType.LICENSE,
            severity=severity,
            summary=summary,
            details=f"vendor: {vendor}",
        ),
    )
```

Extend `__all__`:

```python
__all__ = [
    "CveEntry",
    "EolEntry",
    "LicensePolicy",
    "_check_cves",
    "_check_eol",
    "_check_license",
]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_plugins_advisories.py -v -k "license"`

Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/nexus/plugins/advisories.py tests/test_plugins_advisories.py
git commit -m "feat(plugins): add LicensePolicy and _check_license"
```

---

## Task 8: Curated YAML data + AdvisoryDatabase loader

**Files:**
- Create: `src/nexus/plugins/data/eol.yaml`
- Create: `src/nexus/plugins/data/cves.yaml`
- Create: `src/nexus/plugins/data/licenses.yaml`
- Modify: `src/nexus/plugins/advisories.py`
- Modify: `tests/test_plugins_advisories.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Create the three curated YAML files**

`src/nexus/plugins/data/eol.yaml`:

```yaml
# src/nexus/plugins/data/eol.yaml
# Curated end-of-life and deprecated plugin list.
# Author: Pierre Grothe
# Date: 2026-05-11
#
# Each entry: plugin_id, status (end_of_life|deprecated), effective (ISO date),
#   optional replacement plugin_id, optional notes.
- plugin_id: com.snc.ess
  status: end_of_life
  effective: 2024-12-31
  replacement: com.snc.now_experience
  notes: ESS portal retired in Vancouver release.
- plugin_id: com.snc.legacy_change_calendar
  status: deprecated
  effective: 2024-06-30
  replacement: com.snc.change_request_calendar
  notes: Use the modern Change Calendar.
- plugin_id: com.snc.mobile_classic
  status: end_of_life
  effective: 2023-11-30
  replacement: com.snc.now_mobile_app
  notes: Classic mobile retired; switch to Now Mobile.
```

`src/nexus/plugins/data/cves.yaml`:

```yaml
# src/nexus/plugins/data/cves.yaml
# Curated CVE entries that affect specific ServiceNow plugin versions.
# Author: Pierre Grothe
# Date: 2026-05-11
#
# Each entry: cve_id, plugin_id, severity (critical|high|medium|low),
#   affected_versions (PEP 440 SpecifierSet), optional fixed_in, summary.
- cve_id: CVE-2024-EXAMPLE-1
  plugin_id: com.snc.cms
  severity: high
  affected_versions: ">=1.0,<2.2.1"
  fixed_in: "2.2.1"
  summary: Example reflected XSS in CMS portal renderer.
- cve_id: CVE-2024-EXAMPLE-2
  plugin_id: com.snc.knowledge
  severity: medium
  affected_versions: "<3.0.0"
  fixed_in: "3.0.0"
  summary: Example authorization bypass on draft articles.
```

`src/nexus/plugins/data/licenses.yaml`:

```yaml
# src/nexus/plugins/data/licenses.yaml
# Curated vendor allow/forbid policy for plugins.
# Author: Pierre Grothe
# Date: 2026-05-11
#
# Vendor strings are matched verbatim against PluginInfo.vendor.
# Empty vendor strings never produce findings.
allowed_vendors:
  - ServiceNow
  - Service-now.com
  - servicenow
forbidden_vendors: []
```

- [ ] **Step 2: Ensure data files ship with the wheel**

In `pyproject.toml`, locate the package-data / poetry packages declaration. NEXUS uses Poetry; the section that controls included non-Python files is `[tool.poetry]` with `include = [...]`. Confirm the existing `product_families.yaml` already ships, and add the new directory.

Read the existing `pyproject.toml` first to see the convention. The minimal addition needed is:

```toml
[tool.poetry]
# ... existing fields ...
include = [
    { path = "src/nexus/plugins/data/*.yaml", format = ["sdist", "wheel"] },
]
```

If `include` already lists `product_families.yaml`, add the new pattern alongside it. **Do not** overwrite the existing include list -- merge into it.

If `product_families.yaml` is being picked up automatically (Poetry includes package-adjacent data by default), the new files in `src/nexus/plugins/data/` should also ship without modification. Verify by running `poetry build && unzip -l dist/*.whl | grep data` after the implementation is complete; only add `include` rules if the build output is missing the files.

- [ ] **Step 3: Write failing AdvisoryDatabase loader tests**

Append to `tests/test_plugins_advisories.py`:

```python
import pytest

from nexus.plugins.advisories import AdvisoryDatabase
from nexus.plugins.errors import PluginAdvisoryDataError


def test_load_database_reads_three_bundled_yamls():
    db = AdvisoryDatabase.load()
    # Each shipped YAML has at least one entry per the seed data above.
    assert len(db.eol) >= 1
    assert len(db.cves) >= 1
    assert "ServiceNow" in db.licenses.allowed_vendors


def test_load_database_raises_on_malformed_yaml(tmp_path, monkeypatch):
    bad = tmp_path / "eol.yaml"
    bad.write_text(": : :\n", encoding="utf-8")
    monkeypatch.setattr(
        "nexus.plugins.advisories._data_path", lambda name: tmp_path / name
    )
    # Other two files still need to exist; copy in valid stubs.
    (tmp_path / "cves.yaml").write_text("[]\n", encoding="utf-8")
    (tmp_path / "licenses.yaml").write_text(
        "allowed_vendors: []\nforbidden_vendors: []\n", encoding="utf-8"
    )
    with pytest.raises(PluginAdvisoryDataError):
        AdvisoryDatabase.load()


def test_load_database_raises_on_invalid_cve_specifier(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "nexus.plugins.advisories._data_path", lambda name: tmp_path / name
    )
    (tmp_path / "eol.yaml").write_text("[]\n", encoding="utf-8")
    (tmp_path / "cves.yaml").write_text(
        "- cve_id: CVE-X\n"
        "  plugin_id: com.x\n"
        "  severity: high\n"
        "  affected_versions: 'not a valid specifier'\n"
        "  summary: bad\n",
        encoding="utf-8",
    )
    (tmp_path / "licenses.yaml").write_text(
        "allowed_vendors: []\nforbidden_vendors: []\n", encoding="utf-8"
    )
    with pytest.raises(PluginAdvisoryDataError):
        AdvisoryDatabase.load()
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `pytest tests/test_plugins_advisories.py -v -k "load_database"`

Expected: FAIL -- AdvisoryDatabase undefined.

- [ ] **Step 5: Implement AdvisoryDatabase in `src/nexus/plugins/advisories.py`**

Add these imports near the top of the file:

```python
from pathlib import Path

import yaml

from nexus.plugins.errors import PluginAdvisoryDataError
```

Add a module-level helper and the `AdvisoryDatabase` class. Place the helper above the class:

```python
def _data_path(name: str) -> Path:
    """Return the path to a bundled advisory YAML file.

    Args:
        name: Filename within ``src/nexus/plugins/data/``.

    Returns:
        Absolute path to the bundled YAML.
    """
    return Path(__file__).parent / "data" / name


class AdvisoryDatabase(BaseModel):
    """Loaded contents of the three bundled advisory YAML files.

    Attributes:
        eol: ``plugin_id -> EolEntry`` lookup.
        cves: ``plugin_id -> tuple of CveEntry`` lookup.
        licenses: Vendor allow/forbid policy.
    """

    model_config = _FROZEN

    eol: dict[str, EolEntry]
    cves: dict[str, tuple[CveEntry, ...]]
    licenses: LicensePolicy

    @classmethod
    def load(cls) -> "AdvisoryDatabase":
        """Read the three bundled YAML files and validate them.

        Returns:
            Parsed AdvisoryDatabase.

        Raises:
            PluginAdvisoryDataError: If any file is missing, malformed,
                or fails schema validation.
        """
        try:
            eol_raw = yaml.safe_load(_data_path("eol.yaml").read_text(encoding="utf-8")) or []
            cves_raw = yaml.safe_load(_data_path("cves.yaml").read_text(encoding="utf-8")) or []
            licenses_raw = (
                yaml.safe_load(_data_path("licenses.yaml").read_text(encoding="utf-8")) or {}
            )
            eol_entries = [EolEntry.model_validate(row) for row in eol_raw]
            cve_entries = [CveEntry.model_validate(row) for row in cves_raw]
            licenses = LicensePolicy.model_validate(
                {
                    "allowed_vendors": tuple(licenses_raw.get("allowed_vendors", []) or []),
                    "forbidden_vendors": tuple(licenses_raw.get("forbidden_vendors", []) or []),
                }
            )
        except Exception as exc:
            raise PluginAdvisoryDataError(f"failed to load advisory data: {exc}") from exc

        eol_by_id: dict[str, EolEntry] = {e.plugin_id: e for e in eol_entries}
        cves_by_id: dict[str, tuple[CveEntry, ...]] = {}
        for entry in cve_entries:
            cves_by_id.setdefault(entry.plugin_id, ())
            cves_by_id[entry.plugin_id] = cves_by_id[entry.plugin_id] + (entry,)
        return cls(eol=eol_by_id, cves=cves_by_id, licenses=licenses)
```

Extend `__all__`:

```python
__all__ = [
    "AdvisoryDatabase",
    "CveEntry",
    "EolEntry",
    "LicensePolicy",
    "_check_cves",
    "_check_eol",
    "_check_license",
]
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_plugins_advisories.py -v -k "load_database"`

Expected: 3 PASS.

- [ ] **Step 7: Commit**

```bash
git add src/nexus/plugins/data/ src/nexus/plugins/advisories.py tests/test_plugins_advisories.py pyproject.toml
git commit -m "feat(plugins): add AdvisoryDatabase loader with bundled YAML data"
```

---

## Task 9: compute_advisories orchestrator

**Files:**
- Modify: `src/nexus/plugins/advisories.py`
- Modify: `tests/test_plugins_advisories.py`
- Create: `tests/fakes/fake_advisory_data.py`

- [ ] **Step 1: Create `tests/fakes/fake_advisory_data.py`**

```python
# tests/fakes/fake_advisory_data.py
# In-memory AdvisoryDatabase factory for unit tests.
# Author: Pierre Grothe
# Date: 2026-05-11
"""Build canned AdvisoryDatabase instances without touching the bundled YAMLs."""

from datetime import date

from nexus.plugins.advisories import (
    AdvisoryDatabase,
    CveEntry,
    EolEntry,
    LicensePolicy,
)
from nexus.plugins.models import Severity

__all__ = ["make_advisory_database"]


def make_advisory_database() -> AdvisoryDatabase:
    """Build a fixed AdvisoryDatabase with one entry per advisory type."""
    eol = {
        "com.legacy": EolEntry(
            plugin_id="com.legacy",
            status="end_of_life",
            effective=date(2020, 1, 1),
            replacement="com.modern",
            notes="",
        ),
    }
    cves = {
        "com.cms": (
            CveEntry(
                cve_id="CVE-9999-1",
                plugin_id="com.cms",
                severity=Severity.HIGH,
                affected_versions=">=1.0,<2.0",
                fixed_in="2.0",
                summary="Example XSS",
            ),
        ),
    }
    licenses = LicensePolicy(
        allowed_vendors=("ServiceNow",),
        forbidden_vendors=("Sketchy LLC",),
    )
    return AdvisoryDatabase(eol=eol, cves=cves, licenses=licenses)
```

- [ ] **Step 2: Write failing tests**

Append to `tests/test_plugins_advisories.py`:

```python
from nexus.plugins.advisories import compute_advisories
from nexus.plugins.models import PluginInventory
from datetime import datetime
from tests.fakes.fake_advisory_data import make_advisory_database


def _inventory(*plugins: PluginInfo) -> PluginInventory:
    return PluginInventory(
        captured_at=datetime(2026, 5, 11, tzinfo=UTC),
        sn_version="Washington",
        plugins=plugins,
    )


def test_compute_advisories_returns_empty_set_when_no_findings():
    db = make_advisory_database()
    inv = _inventory(_info("com.unaffected", "1.0"))
    result = compute_advisories(inv, db, today=date(2026, 5, 11))
    assert result.findings == ()


def test_compute_advisories_aggregates_all_three_checker_outputs():
    db = make_advisory_database()
    inv = _inventory(
        # vendor not in policy.allowed_vendors -> medium license finding
        PluginInfo(**{**_info("com.cms", "1.5").model_dump(), "vendor": "Unknown"}),
        _info("com.legacy", "1.0"),
    )
    result = compute_advisories(inv, db, today=date(2026, 5, 11))
    types = {f.advisory_type for f in result.findings}
    assert types == {AdvisoryType.EOL, AdvisoryType.CVE, AdvisoryType.LICENSE}


def test_compute_advisories_sorts_findings_by_severity_then_plugin_id():
    db = make_advisory_database()
    inv = _inventory(
        # com.cms produces a HIGH CVE finding
        PluginInfo(**{**_info("com.cms", "1.5").model_dump(), "vendor": "ServiceNow"}),
        # com.legacy is HIGH EOL (effective 2020-01-01, in the past)
        _info("com.legacy", "1.0"),
    )
    result = compute_advisories(inv, db, today=date(2026, 5, 11))
    severities = [f.severity for f in result.findings]
    assert severities == sorted(
        severities,
        key=lambda s: ["critical", "high", "medium", "low"].index(s.value),
    )
    # Same-severity ties broken by plugin_id asc:
    same_severity = [f for f in result.findings if f.severity is Severity.HIGH]
    plugin_ids = [f.plugin_id for f in same_severity]
    assert plugin_ids == sorted(plugin_ids)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_plugins_advisories.py -v -k "compute_advisories"`

Expected: FAIL -- `compute_advisories` undefined.

- [ ] **Step 4: Implement compute_advisories**

Append to `src/nexus/plugins/advisories.py`:

```python
from nexus.plugins.models import AdvisorySet, PluginInventory

_SEV_ORDER: dict[Severity, int] = {
    Severity.CRITICAL: 0,
    Severity.HIGH: 1,
    Severity.MEDIUM: 2,
    Severity.LOW: 3,
}


def compute_advisories(
    inventory: PluginInventory,
    db: AdvisoryDatabase,
    *,
    today: date,
) -> AdvisorySet:
    """Cross-check inventory against three curated advisory tables.

    Args:
        inventory: Plugin inventory captured by sub-project A.
        db: Pre-loaded advisory database.
        today: Reference date for EOL past/future comparison. Injected
            so callers can pin it; in production the CLI passes
            ``datetime.now(UTC).date()``.

    Returns:
        AdvisorySet sorted by (severity desc, plugin_id asc).
    """
    findings: list[AdvisoryFinding] = []
    for plugin in inventory.plugins:
        findings.extend(_check_eol(plugin, db.eol, today=today))
        findings.extend(_check_cves(plugin, db.cves))
        findings.extend(_check_license(plugin, db.licenses))
    findings.sort(key=lambda f: (_SEV_ORDER[f.severity], f.plugin_id))
    return AdvisorySet(findings=tuple(findings))
```

Extend `__all__`:

```python
__all__ = [
    "AdvisoryDatabase",
    "CveEntry",
    "EolEntry",
    "LicensePolicy",
    "_check_cves",
    "_check_eol",
    "_check_license",
    "compute_advisories",
]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_plugins_advisories.py -v`

Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/nexus/plugins/advisories.py tests/test_plugins_advisories.py tests/fakes/fake_advisory_data.py
git commit -m "feat(plugins): add compute_advisories orchestrator"
```

---

## Task 10: Public re-exports

**Files:**
- Modify: `src/nexus/plugins/__init__.py`
- Test: ad-hoc import check

- [ ] **Step 1: Add a failing import test**

Append to `tests/test_plugins_advisories.py`:

```python
def test_public_api_reexports_advisories_symbols():
    import nexus.plugins as pkg

    expected = {
        "AdvisoryDatabase",
        "AdvisoryFinding",
        "AdvisorySet",
        "AdvisoryType",
        "PluginAdvisoryDataError",
        "Severity",
        "compute_advisories",
    }
    assert expected.issubset(set(pkg.__all__))
    for name in expected:
        assert hasattr(pkg, name), f"missing re-export: {name}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_plugins_advisories.py::test_public_api_reexports_advisories_symbols -v`

Expected: FAIL.

- [ ] **Step 3: Update `src/nexus/plugins/__init__.py`**

```python
# src/nexus/plugins/__init__.py
# Public re-exports for the plugins layer.
# Author: Pierre Grothe
# Date: 2026-05-11
"""nexus.plugins: read-only plugin inventory layer.

Exports the data models, scanner, error types, product-family lookup,
the cross-instance diff/promote helpers, the update-detection filter,
and the advisory checkers (EOL, CVE, license).
"""

from nexus.plugins.advisories import AdvisoryDatabase, compute_advisories
from nexus.plugins.diff import (
    PluginDiff,
    PluginDiffEntry,
    PromoteAction,
    PromotionPlan,
    compute_diff,
    project_to_promote_plan,
)
from nexus.plugins.errors import PluginAdvisoryDataError, PluginScanError
from nexus.plugins.models import (
    AdvisoryFinding,
    AdvisorySet,
    AdvisoryType,
    PluginInfo,
    PluginInventory,
    ProductFamily,
    Severity,
)
from nexus.plugins.product_families import product_family_for
from nexus.plugins.scanner import PluginScanner
from nexus.plugins.updates import plugins_with_updates

__all__ = [
    "AdvisoryDatabase",
    "AdvisoryFinding",
    "AdvisorySet",
    "AdvisoryType",
    "PluginAdvisoryDataError",
    "PluginDiff",
    "PluginDiffEntry",
    "PluginInfo",
    "PluginInventory",
    "PluginScanError",
    "PluginScanner",
    "ProductFamily",
    "PromoteAction",
    "PromotionPlan",
    "Severity",
    "compute_advisories",
    "compute_diff",
    "plugins_with_updates",
    "product_family_for",
    "project_to_promote_plan",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_plugins_advisories.py::test_public_api_reexports_advisories_symbols -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/nexus/plugins/__init__.py tests/test_plugins_advisories.py
git commit -m "feat(plugins): expose advisories layer"
```

---

## Task 11: CLI `nexus plugins advisories` command

**Files:**
- Modify: `src/nexus/cli.py`
- Create: `tests/test_cli_plugins_advisories.py`

- [ ] **Step 1: Write failing CLI tests**

Create `tests/test_cli_plugins_advisories.py`:

```python
# tests/test_cli_plugins_advisories.py
# CLI tests for `nexus plugins advisories`.
# Author: Pierre Grothe
# Date: 2026-05-11
"""Tests for the advisories subcommand in src/nexus/cli.py."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from nexus.cli import app
from nexus.plugins.models import PluginInfo, PluginInventory

runner = CliRunner()


def _make_inventory_file(
    tmp_path: Path,
    plugins: tuple[PluginInfo, ...],
) -> Path:
    """Write a plugin inventory JSON in the layout the registry expects."""
    # Reuse the same helper machinery as tests for sub-projects B/C.
    # In the actual test file, import or replicate that helper. The CLI
    # advisories command goes through _load_inventory_or_exit, which
    # delegates to InstanceRegistry.load_plugin_inventory.
    raise NotImplementedError("Use the same fixture pattern as tests for sub-projects B/C.")


# NOTE: The runner.invoke calls below assume a registered profile and a
# captured inventory. Mirror the fixtures used in
# tests/test_cli_plugins_updates.py -- they already build a temp config
# dir + InstanceRegistry seeded with a profile and an inventory.


def test_advisories_renders_three_sections_when_findings_in_each(seeded_profile):
    """seeded_profile: pytest fixture (mirror from test_cli_plugins_updates.py)
    that returns a profile name backed by an inventory containing one EOL,
    one CVE-affected, and one unknown-vendor plugin."""
    result = runner.invoke(
        app,
        ["plugins", "advisories", "--instance", seeded_profile],
    )
    assert result.exit_code == 0
    assert "EOL" in result.stdout
    assert "CVE" in result.stdout
    assert "License" in result.stdout
    assert "advisory finding" in result.stdout.lower()


def test_advisories_prints_no_findings_when_clean(seeded_clean_profile):
    result = runner.invoke(
        app,
        ["plugins", "advisories", "--instance", seeded_clean_profile],
    )
    assert result.exit_code == 0
    assert "No advisories found" in result.stdout


def test_advisories_filters_by_type_when_type_flag_provided(seeded_profile):
    result = runner.invoke(
        app,
        ["plugins", "advisories", "--instance", seeded_profile, "--type", "cve"],
    )
    assert result.exit_code == 0
    assert "CVE" in result.stdout
    assert "EOL" not in result.stdout


def test_advisories_filters_by_severity_when_severity_flag_provided(seeded_profile):
    result = runner.invoke(
        app,
        ["plugins", "advisories", "--instance", seeded_profile, "--severity", "high"],
    )
    assert result.exit_code == 0
    # Medium findings (e.g. unknown-vendor license) must be filtered out.
    assert "Vendor not in allow-list" not in result.stdout


def test_advisories_renders_per_severity_counts_in_trailing_notice(seeded_profile):
    result = runner.invoke(
        app,
        ["plugins", "advisories", "--instance", seeded_profile],
    )
    assert result.exit_code == 0
    assert "critical" in result.stdout.lower()
    assert "high" in result.stdout.lower()


def test_advisories_warns_when_inventory_missing(profile_without_inventory):
    result = runner.invoke(
        app,
        ["plugins", "advisories", "--instance", profile_without_inventory],
    )
    assert result.exit_code == 1
    assert "Refresh" in result.stdout or "refresh" in result.stdout


def test_advisories_errors_when_data_files_corrupted(seeded_profile, monkeypatch):
    def _raise_load() -> object:
        from nexus.plugins.errors import PluginAdvisoryDataError

        raise PluginAdvisoryDataError("simulated corruption")

    monkeypatch.setattr("nexus.cli.AdvisoryDatabase.load", staticmethod(_raise_load))
    result = runner.invoke(
        app,
        ["plugins", "advisories", "--instance", seeded_profile],
    )
    assert result.exit_code == 1
    assert "Advisory data corrupted" in result.stdout
```

IMPORTANT for the implementer: Inspect `tests/test_cli_plugins_updates.py` first. It already establishes the fixture pattern (`seeded_profile`, `seeded_clean_profile`, `profile_without_inventory`) and the helpers that write a `plugins.json` under the right registry path. Reuse those fixtures via `conftest.py` (move to conftest if they live inside the updates test file). Do not re-invent the seed scaffolding.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cli_plugins_advisories.py -v`

Expected: FAIL -- `advisories` subcommand not registered.

- [ ] **Step 3: Add the advisories subcommand to `src/nexus/cli.py`**

Add this import near the other `nexus.plugins` imports at the top:

```python
from nexus.plugins.advisories import AdvisoryDatabase, compute_advisories
from nexus.plugins.errors import PluginAdvisoryDataError
from nexus.plugins.models import AdvisoryFinding, AdvisorySet, AdvisoryType, Severity
```

Update `_PLUGINS_HELP` to include the new command:

```python
_PLUGINS_HELP = [
    ("list", "Show all plugins with optional --product / --source / --state filters"),
    ("info <plugin_id>", "Show full details and dependencies for one plugin"),
    ("export", "Write the inventory to YAML or CSV"),
    ("diff <a> <b>", "Show cross-instance plugin differences"),
    ("promote <src> --to <dst>", "Write an action plan to make <dst> match <src>"),
    ("updates", "Show plugins with newer versions available"),
    ("advisories", "Show EOL / CVE / license findings"),
]
```

Add module-level helpers below the existing `_diff_status_badge` helper (or any analogous spot near other plugins helpers):

```python
_SEVERITY_ORDER: tuple[Severity, ...] = (
    Severity.CRITICAL,
    Severity.HIGH,
    Severity.MEDIUM,
    Severity.LOW,
)


def _severity_at_or_above(floor: Severity) -> set[Severity]:
    """Return the set of severities >= ``floor`` in the canonical ordering."""
    idx = _SEVERITY_ORDER.index(floor)
    return set(_SEVERITY_ORDER[: idx + 1])


def _advisories_table(
    title: str,
    columns: tuple[DataColumn, ...],
    rows: list[list[RenderableType]],
) -> DataTable:
    """Render one advisories DataTable section."""
    return DataTable(title=title, columns=list(columns), rows=rows)
```

Append the command at the end of the plugins commands block (after `plugins_updates`):

```python
@plugins_app.command("advisories")
def plugins_advisories(
    instance: Annotated[
        str,
        typer.Option(
            "--instance",
            help="Instance profile (default: configured default)",
        ),
    ] = "",
    advisory_type: Annotated[
        str,
        typer.Option(
            "--type",
            help="Filter to one advisory type: eol, cve, or license.",
        ),
    ] = "",
    severity: Annotated[
        str,
        typer.Option(
            "--severity",
            help="Show only findings at or above this severity (critical|high|medium|low).",
        ),
    ] = "",
) -> None:
    """Show EOL / CVE / license findings for plugins on an instance."""
    meta, inventory = _load_inventory_or_exit(instance)
    try:
        db = AdvisoryDatabase.load()
    except PluginAdvisoryDataError as exc:
        console.print(Notice.error(f"Advisory data corrupted: {exc}"))
        raise typer.Exit(1) from exc

    today = datetime.now(UTC).date()
    result = compute_advisories(inventory, db, today=today)
    findings = result.findings

    if advisory_type:
        try:
            wanted_type = AdvisoryType(advisory_type)
        except ValueError as exc:
            console.print(Notice.error(f"Unknown --type: {advisory_type}"))
            raise typer.Exit(1) from exc
        findings = tuple(f for f in findings if f.advisory_type is wanted_type)

    if severity:
        try:
            floor = Severity(severity)
        except ValueError as exc:
            console.print(Notice.error(f"Unknown --severity: {severity}"))
            raise typer.Exit(1) from exc
        keep = _severity_at_or_above(floor)
        findings = tuple(f for f in findings if f.severity in keep)

    if not findings:
        console.print(Notice.info("No advisories found."))
        return

    _render_advisory_sections(findings)
    _render_advisory_summary(findings)


def _render_advisory_sections(findings: tuple[AdvisoryFinding, ...]) -> None:
    """Render one DataTable per non-empty advisory type."""
    by_type: dict[AdvisoryType, list[AdvisoryFinding]] = {
        AdvisoryType.EOL: [],
        AdvisoryType.CVE: [],
        AdvisoryType.LICENSE: [],
    }
    for finding in findings:
        by_type[finding.advisory_type].append(finding)

    if by_type[AdvisoryType.EOL]:
        rows = [
            [f.plugin_id, f.plugin_name, f.plugin_version, f.severity.value, f.details]
            for f in by_type[AdvisoryType.EOL]
        ]
        console.print(
            DataTable(
                title="EOL plugins",
                columns=[
                    DataColumn(header="Plugin ID", width=32),
                    DataColumn(header="Name", width=20),
                    DataColumn(header="Version", width=12),
                    DataColumn(header="Severity", width=10),
                    DataColumn(header="Details", width=42),
                ],
                rows=rows,
            )
        )
    if by_type[AdvisoryType.CVE]:
        rows = [
            [f.plugin_id, f.plugin_name, f.plugin_version, f.severity.value, f.details, f.summary]
            for f in by_type[AdvisoryType.CVE]
        ]
        console.print(
            DataTable(
                title="CVE advisories",
                columns=[
                    DataColumn(header="Plugin ID", width=28),
                    DataColumn(header="Name", width=18),
                    DataColumn(header="Version", width=10),
                    DataColumn(header="Severity", width=10),
                    DataColumn(header="CVE / range", width=32),
                    DataColumn(header="Summary", width=28),
                ],
                rows=rows,
            )
        )
    if by_type[AdvisoryType.LICENSE]:
        rows = [
            [f.plugin_id, f.plugin_name, f.plugin_version, f.severity.value, f.details]
            for f in by_type[AdvisoryType.LICENSE]
        ]
        console.print(
            DataTable(
                title="License findings",
                columns=[
                    DataColumn(header="Plugin ID", width=32),
                    DataColumn(header="Name", width=20),
                    DataColumn(header="Version", width=12),
                    DataColumn(header="Severity", width=10),
                    DataColumn(header="Details", width=42),
                ],
                rows=rows,
            )
        )


def _render_advisory_summary(findings: tuple[AdvisoryFinding, ...]) -> None:
    """Print the trailing per-severity count notice."""
    counts = {s: 0 for s in _SEVERITY_ORDER}
    for f in findings:
        counts[f.severity] += 1
    parts = [f"{counts[s]} {s.value}" for s in _SEVERITY_ORDER]
    console.print(
        Notice.info(f"{len(findings)} advisory finding(s): {', '.join(parts)}.")
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_cli_plugins_advisories.py -v`

Expected: All tests pass.

- [ ] **Step 5: Smoke-render the help**

Run: `python -m nexus plugins advisories --help`

Expected: Help text shows `--instance`, `--type`, `--severity` options.

- [ ] **Step 6: Commit**

```bash
git add src/nexus/cli.py tests/test_cli_plugins_advisories.py
git commit -m "feat(cli): add nexus plugins advisories with type and severity filters"
```

---

## Task 12: Black + ratchet refresh

**Files:**
- Modify: `.ratchet.json`

- [ ] **Step 1: Run black on all changed files**

Run: `black src/nexus/plugins/ src/nexus/cli.py tests/test_plugins_advisories.py tests/test_cli_plugins_advisories.py tests/fakes/fake_advisory_data.py`

Expected: any reformatting applied silently.

- [ ] **Step 2: Run the full quality gate**

Run, in order:
- `ruff check src tests` -> Expected: 0 violations
- `mypy src/nexus/` -> Expected: 0 errors
- `pyright src/nexus/` -> Expected: 0 errors
- `pytest` -> Expected: all new tests pass; 4 pre-existing failures unchanged

- [ ] **Step 3: Measure new coverage baselines**

Run: `pytest --cov=src/nexus --cov-report=json`

Look up the new lines/covered counts for:
- `nexus.plugins.advisories`
- `nexus.plugins.errors`
- `nexus.plugins.models`
- `nexus.plugins.scanner`
- `nexus.cli`

- [ ] **Step 4: Update `.ratchet.json`**

Update or insert these keys with the freshly measured values. Do not change unrelated keys.

```jsonc
{
  ...
  "modules": {
    ...
    "nexus.cli": {"covered_lines": <new>, "total_lines": <new>},
    "nexus.plugins.advisories": {"covered_lines": <new>, "total_lines": <new>},
    "nexus.plugins.errors": {"covered_lines": <new>, "total_lines": <new>},
    "nexus.plugins.models": {"covered_lines": <new>, "total_lines": <new>},
    "nexus.plugins.scanner": {"covered_lines": <new>, "total_lines": <new>},
    ...
  }
}
```

Ratchet rule: `covered_lines` must be >= the previous value for each module; `total_lines` reflects the new module size. Bumps are normal when adding code; the ratchet enforces that coverage never decreases.

- [ ] **Step 5: Commit**

```bash
git add .ratchet.json src/nexus/ tests/
git commit -m "chore(plugins): black formatting + refresh ratchet for advisories layer"
```

- [ ] **Step 6: Push and open PR**

```bash
git push -u origin feat/plugins-advisories
gh pr create --base feat/plugins-update-detection --title "feat(plugins): D1 advisories (EOL + CVE + license)" --body "$(cat <<'EOF'
## Summary
- Curated YAML data files (EOL, CVE, vendor license policy) ship with the package.
- New `nexus.plugins.advisories` module with three checker functions and a `compute_advisories` orchestrator.
- `PluginInfo` gets a `vendor` field, populated by the scanner from `sys_store_app.vendor`.
- New `nexus plugins advisories` CLI command with `--type` and `--severity` filters.

Sub-project D1 of plugin management. Stacked on PR #13 (`feat/plugins-update-detection`).

Spec: docs/superpowers/specs/2026-05-11-plugin-advisories-design.md

## Test plan
- [x] `pytest tests/test_plugins_advisories.py -v` (new module unit tests)
- [x] `pytest tests/test_cli_plugins_advisories.py -v` (CLI tests)
- [x] `pytest` (full suite green except 4 pre-existing failures)
- [x] ruff / black / mypy / pyright clean
- [x] `python -m nexus plugins advisories --help` smoke render

EOF
)"
```

---

## Self-Review Summary

**Spec coverage:**
- Severity / AdvisoryType / AdvisoryFinding / AdvisorySet -> Task 1
- vendor field on PluginInfo -> Task 2
- Scanner populates vendor -> Task 3
- PluginAdvisoryDataError -> Task 4
- EolEntry + _check_eol with past/future date severity -> Task 5
- CveEntry + _check_cves with PEP 440 + unparseable-version skip -> Task 6
- LicensePolicy + _check_license with all five severity rules -> Task 7
- Curated YAML seed data + AdvisoryDatabase loader + pyproject.toml include -> Task 8
- compute_advisories with severity-then-plugin_id sort -> Task 9
- Public re-exports -> Task 10
- CLI command with --type / --severity filters + corrupted-data error path -> Task 11
- Black, full quality gate, ratchet refresh, PR -> Task 12

All spec sections traced to a task. No gaps.

**Placeholder scan:** Searched for "TBD", "TODO", "implement later", "etc." -- none found in plan body. The fixture references in Task 11 deliberately point to the existing pattern in `tests/test_cli_plugins_updates.py` rather than repeating fixture code that lives in another file.

**Type consistency:** All type signatures consistent across tasks. `compute_advisories(inventory, db, *, today=date)` matches Task 5's `_check_eol(plugin, table, *, today=date)`. AdvisoryDatabase fields (`eol: dict[str, EolEntry]`, `cves: dict[str, tuple[CveEntry, ...]]`, `licenses: LicensePolicy`) consistent between Task 8 definition and Task 9 usage. AdvisorySet shape (`findings: tuple[AdvisoryFinding, ...]`) consistent throughout.
