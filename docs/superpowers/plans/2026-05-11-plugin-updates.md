# Plugin Update Detection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship sub-project C of the plugin management roadmap: detect ServiceNow Store apps with newer versions available and surface them via a new `nexus plugins updates` command.

**Architecture:** Add one optional `latest_version: str | None = None` field to the existing `PluginInfo` model. Extend `PluginScanner._from_store` to read `sys_store_app.latest_version` from the SN Table API. One new pure-function module `src/nexus/plugins/updates.py` exposes `plugins_with_updates(inventory)` that returns plugins where the two versions differ. One new CLI command renders a DataTable and optionally writes a YAML queue.

**Tech Stack:** Python 3.14, Pydantic v2 (frozen), Typer, Rich (via `nexus.ui`), PyYAML, pytest.

**Spec:** `docs/superpowers/specs/2026-05-11-plugin-updates-design.md`

---

## File structure

New files:

```
src/nexus/plugins/updates.py            -- 1 pure function
tests/test_plugins_updates.py           -- unit tests for the function
tests/test_cli_plugins_updates.py       -- CliRunner integration tests
```

Modified files:

```
src/nexus/plugins/models.py             -- add latest_version field on PluginInfo
src/nexus/plugins/scanner.py            -- populate latest_version in _from_store
src/nexus/plugins/__init__.py           -- re-export plugins_with_updates
src/nexus/cli.py                        -- add updates subcommand;
                                           update _PLUGINS_HELP
tests/fakes/fake_plugin_data.py         -- add latest_version to one row
tests/test_plugins_models.py            -- 2 new tests for the new field
tests/test_plugins_scanner.py           -- 2 new tests for scanner population
.ratchet.json                           -- new module baseline + cli.py bump
```

---

## Task 1: Add latest_version field to PluginInfo

**Files:**
- Modify: `src/nexus/plugins/models.py`
- Modify: `tests/test_plugins_models.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_plugins_models.py`:

```python
def test_plugin_info_defaults_latest_version_to_none() -> None:
    info = _info()
    assert info.latest_version is None


def test_plugin_info_accepts_latest_version_field() -> None:
    info = _info(latest_version="2.0.0")
    assert info.latest_version == "2.0.0"
```

The existing `_info()` test helper passes a `defaults` dict to `PluginInfo.model_validate`. Both new tests assume `_info(latest_version=...)` propagates through the helper. No helper change required because the kwarg `latest_version` will be merged into `defaults` and `model_validate` accepts unknown-to-this-test fields when they match the model.

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_plugins_models.py::test_plugin_info_defaults_latest_version_to_none -v --no-cov`
Expected: PASS if `latest_version` field has been added; FAIL on `extra="forbid"` rejection if not.

Run: `pytest tests/test_plugins_models.py::test_plugin_info_accepts_latest_version_field -v --no-cov`
Expected: FAIL on `ValidationError: Extra inputs are not permitted` because PluginInfo currently has `extra="forbid"` and no `latest_version` field.

- [ ] **Step 3: Add the field to PluginInfo**

In `src/nexus/plugins/models.py`, find the existing `PluginInfo` definition:

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
```

Replace it with:

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
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/test_plugins_models.py -v --no-cov`
Expected: ALL existing model tests still pass plus the 2 new tests.

- [ ] **Step 5: Run linters**

```
ruff check src/nexus/plugins/models.py tests/test_plugins_models.py
pyright src/nexus/plugins/models.py tests/test_plugins_models.py
mypy src/nexus/plugins/models.py tests/test_plugins_models.py
```
Expected: all clean.

- [ ] **Step 6: Commit**

```bash
git add src/nexus/plugins/models.py tests/test_plugins_models.py
git commit -m "feat(plugins): add latest_version field to PluginInfo"
```

---

## Task 2: Read latest_version in PluginScanner

**Files:**
- Modify: `src/nexus/plugins/scanner.py`
- Modify: `tests/fakes/fake_plugin_data.py`
- Modify: `tests/test_plugins_scanner.py`

- [ ] **Step 1: Update the fake data**

Open `tests/fakes/fake_plugin_data.py` and find the `SYS_STORE_APP_ROWS` entry for `com.acme.helper`. Add `"latest_version": "3.2.0"` to that one row. The dict for that entry becomes:

```python
    {
        "sys_id": "store001",
        "scope": "com.acme.helper",
        "name": "Acme Helper",
        "version": "3.1.0",
        "active": "true",
        "vendor": "Acme Corp",
        "dependencies": "",
        "sys_created_on": "2024-03-01 10:00:00",
        "latest_version": "3.2.0",
    },
```

Leave the other store rows unchanged (no `latest_version` key) so the "absent" path is also covered.

- [ ] **Step 2: Write failing tests**

Append to `tests/test_plugins_scanner.py`:

```python
def test_scan_populates_latest_version_when_present() -> None:
    inv = asyncio.run(_scan(_transport_for()))
    helper = next(p for p in inv.plugins if p.plugin_id == "com.acme.helper")
    assert helper.latest_version == "3.2.0"


def test_scan_leaves_latest_version_none_when_field_absent() -> None:
    inv = asyncio.run(_scan(_transport_for()))
    incident = next(p for p in inv.plugins if p.plugin_id == "com.snc.incident")
    assert incident.latest_version is None
```

- [ ] **Step 3: Run tests to verify failure**

Run: `pytest tests/test_plugins_scanner.py -v --no-cov -k "latest_version"`
Expected: FAIL because `_from_store` does not yet read the field; both newly inserted plugins will have `latest_version=None`. The first test fails on `assert helper.latest_version == "3.2.0"` (it's None).

- [ ] **Step 4: Update _STORE_FIELDS**

In `src/nexus/plugins/scanner.py`, find:

```python
_STORE_FIELDS = "sys_id,scope,name,version,active,vendor,dependencies,sys_created_on"
```

Replace with:

```python
_STORE_FIELDS = (
    "sys_id,scope,name,version,latest_version,active,vendor,"
    "dependencies,sys_created_on"
)
```

- [ ] **Step 5: Populate latest_version in _from_store**

In `src/nexus/plugins/scanner.py`, find `_from_store`:

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
        )
```

Replace with:

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
        )
```

The `str(...) or None` pattern collapses missing key, empty string, and explicit None into a single `None` value. (v_plugin's `_from_v_plugin` is unchanged; PluginInfo's `latest_version=None` default applies there.)

- [ ] **Step 6: Run tests to verify pass**

Run: `pytest tests/test_plugins_scanner.py -v --no-cov`
Expected: 14 existing scanner tests still pass plus the 2 new tests = 16 total.

Note: the deduplication test (`test_scan_dedupes_plugin_present_in_both_tables`) still works -- `com.snc.incident` appears in both tables but only the store row is kept (dedup precedence), and the store row has no `latest_version`, so the dedup test's assertion `len(incidents) == 1` is unchanged.

- [ ] **Step 7: Run linters**

```
ruff check src/nexus/plugins/scanner.py tests/test_plugins_scanner.py tests/fakes/fake_plugin_data.py
pyright src/nexus/plugins/scanner.py tests/test_plugins_scanner.py
mypy src/nexus/plugins/scanner.py tests/test_plugins_scanner.py
```
Expected: all clean.

- [ ] **Step 8: Commit**

```bash
git add src/nexus/plugins/scanner.py tests/test_plugins_scanner.py tests/fakes/fake_plugin_data.py
git commit -m "feat(plugins): read sys_store_app.latest_version in scanner"
```

---

## Task 3: plugins_with_updates helper

**Files:**
- Create: `src/nexus/plugins/updates.py`
- Create: `tests/test_plugins_updates.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_plugins_updates.py
# Tests for the plugins_with_updates filter.
# Author: Pierre Grothe
# Date: 2026-05-11
"""Tests for plugins_with_updates."""

from datetime import UTC, datetime

from nexus.plugins.models import PluginInfo, PluginInventory
from nexus.plugins.updates import plugins_with_updates

__all__: list[str] = []


def _info(
    plugin_id: str,
    *,
    version: str = "1.0.0",
    latest_version: str | None = None,
    product_family: str = "ITSM",
) -> PluginInfo:
    return PluginInfo.model_validate(
        {
            "plugin_id": plugin_id,
            "name": plugin_id,
            "version": version,
            "state": "active",
            "source": "store",
            "product_family": product_family,
            "depends_on": (),
            "sys_id": f"sys-{plugin_id}",
            "installed_at": None,
            "latest_version": latest_version,
        }
    )


def _inventory(*plugins: PluginInfo) -> PluginInventory:
    return PluginInventory(
        captured_at=datetime.now(UTC),
        sn_version="Xanadu",
        plugins=plugins,
    )


def test_plugins_with_updates_filters_to_only_those_with_newer_latest() -> None:
    inv = _inventory(
        _info("com.acme.helper", version="3.0.0", latest_version="3.1.0"),
        _info("com.acme.other", version="1.0.0", latest_version="1.0.0"),
        _info("com.snc.incident", version="1.0.0", latest_version=None),
    )
    result = plugins_with_updates(inv)
    assert len(result) == 1
    assert result[0].plugin_id == "com.acme.helper"


def test_plugins_with_updates_skips_plugins_without_latest_version() -> None:
    inv = _inventory(
        _info("com.snc.incident", version="1.0.0", latest_version=None),
    )
    assert plugins_with_updates(inv) == ()


def test_plugins_with_updates_skips_plugins_at_latest_version() -> None:
    inv = _inventory(
        _info("com.acme.helper", version="3.1.0", latest_version="3.1.0"),
    )
    assert plugins_with_updates(inv) == ()


def test_plugins_with_updates_sorts_by_product_then_plugin_id() -> None:
    inv = _inventory(
        _info(
            "com.acme.helper",
            version="1.0.0", latest_version="2.0.0",
            product_family="Uncategorized",
        ),
        _info(
            "com.snc.problem",
            version="1.0.0", latest_version="2.0.0",
            product_family="ITSM",
        ),
        _info(
            "com.snc.incident",
            version="1.0.0", latest_version="2.0.0",
            product_family="ITSM",
        ),
    )
    result = plugins_with_updates(inv)
    ids = [p.plugin_id for p in result]
    assert ids == ["com.snc.incident", "com.snc.problem", "com.acme.helper"]
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_plugins_updates.py -v --no-cov`
Expected: FAIL on missing module `nexus.plugins.updates`.

- [ ] **Step 3: Implement the helper**

```python
# src/nexus/plugins/updates.py
# Update detection for plugin inventories.
# Author: Pierre Grothe
# Date: 2026-05-11
"""plugins_with_updates: filter an inventory down to plugins with a newer version."""

from nexus.plugins.models import PluginInfo, PluginInventory

__all__ = ["plugins_with_updates"]


def plugins_with_updates(inventory: PluginInventory) -> tuple[PluginInfo, ...]:
    """Return plugins whose ``latest_version`` differs from ``version``.

    Filters out:
        - Plugins without ``latest_version`` (typically v_plugin-only
          entries, i.e. core SN plugins).
        - Plugins where ``latest_version == version`` (up to date).

    Args:
        inventory: Plugin inventory captured from an instance.

    Returns:
        Plugins sorted by ``(product_family, plugin_id)`` for stable output.
    """
    updates = [
        p
        for p in inventory.plugins
        if p.latest_version is not None and p.latest_version != p.version
    ]
    updates.sort(key=lambda p: (p.product_family, p.plugin_id))
    return tuple(updates)
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/test_plugins_updates.py -v --no-cov`
Expected: 4 PASS.

- [ ] **Step 5: Run linters**

```
ruff check src/nexus/plugins/updates.py tests/test_plugins_updates.py
pyright src/nexus/plugins/updates.py tests/test_plugins_updates.py
mypy src/nexus/plugins/updates.py tests/test_plugins_updates.py
```
Expected: all clean.

- [ ] **Step 6: Commit**

```bash
git add src/nexus/plugins/updates.py tests/test_plugins_updates.py
git commit -m "feat(plugins): add plugins_with_updates filter"
```

---

## Task 4: Public re-export

**Files:**
- Modify: `src/nexus/plugins/__init__.py`

- [ ] **Step 1: Add the new name to the public API**

Read the current `src/nexus/plugins/__init__.py`. Update it to include `plugins_with_updates`:

```python
# src/nexus/plugins/__init__.py
# Public re-exports for the plugins layer.
# Author: Pierre Grothe
# Date: 2026-05-11
"""nexus.plugins: read-only plugin inventory layer.

Exports the data models, scanner, error type, product-family lookup,
the cross-instance diff/promote helpers, and the update-detection
filter.
"""

from nexus.plugins.diff import (
    PluginDiff,
    PluginDiffEntry,
    PromoteAction,
    PromotionPlan,
    compute_diff,
    project_to_promote_plan,
)
from nexus.plugins.errors import PluginScanError
from nexus.plugins.models import PluginInfo, PluginInventory, ProductFamily
from nexus.plugins.product_families import product_family_for
from nexus.plugins.scanner import PluginScanner
from nexus.plugins.updates import plugins_with_updates

__all__ = [
    "PluginDiff",
    "PluginDiffEntry",
    "PluginInfo",
    "PluginInventory",
    "PluginScanError",
    "PluginScanner",
    "ProductFamily",
    "PromoteAction",
    "PromotionPlan",
    "compute_diff",
    "plugins_with_updates",
    "product_family_for",
    "project_to_promote_plan",
]
```

- [ ] **Step 2: Verify import surface**

Run: `python -c "from nexus.plugins import plugins_with_updates; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Run linters**

```
ruff check src/nexus/plugins/__init__.py
pyright src/nexus/plugins/__init__.py
mypy src/nexus/plugins/__init__.py
```
Expected: all clean.

- [ ] **Step 4: Commit**

```bash
git add src/nexus/plugins/__init__.py
git commit -m "feat(plugins): expose plugins_with_updates"
```

---

## Task 5: nexus plugins updates CLI command

**Files:**
- Modify: `src/nexus/cli.py`
- Create: `tests/test_cli_plugins_updates.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_cli_plugins_updates.py
# Tests for the nexus plugins updates command.
# Author: Pierre Grothe
# Date: 2026-05-11
"""Tests for nexus plugins updates."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml as _yaml
from typer.testing import CliRunner

from nexus.cache import clear_cache
from nexus.cli import app
from nexus.config.paths import NexusPaths
from nexus.instances.models import InstanceMeta
from nexus.plugins.models import PluginInfo, PluginInventory

__all__: list[str] = []


def _meta(profile: str) -> InstanceMeta:
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
    version: str = "1.0.0",
    latest_version: str | None = None,
    product_family: str = "Uncategorized",
) -> PluginInfo:
    return PluginInfo.model_validate(
        {
            "plugin_id": plugin_id,
            "name": plugin_id,
            "version": version,
            "state": "active",
            "source": "store",
            "product_family": product_family,
            "depends_on": (),
            "sys_id": f"sys-{plugin_id}",
            "installed_at": None,
            "latest_version": latest_version,
        }
    )


def _seed(
    tmp_path: Path,
    profile: str,
    plugins: tuple[PluginInfo, ...] | None,
) -> None:
    profile_dir = tmp_path / "instances" / profile
    profile_dir.mkdir(parents=True, exist_ok=True)
    (profile_dir / "meta.json").write_text(
        _meta(profile).model_dump_json(indent=2), encoding="utf-8"
    )
    if plugins is not None:
        inv = PluginInventory(
            captured_at=datetime.now(UTC),
            sn_version="Xanadu",
            plugins=plugins,
        )
        (profile_dir / "plugins.json").write_text(
            inv.model_dump_json(indent=2), encoding="utf-8"
        )


@pytest.fixture
def runner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> CliRunner:
    monkeypatch.setenv("NEXUS_CONFIG_PATH", str(tmp_path / "config.yaml"))
    clear_cache(NexusPaths.from_env)
    return CliRunner()


def test_plugins_updates_renders_datatable_with_pending_updates(
    runner: CliRunner, tmp_path: Path
) -> None:
    _seed(
        tmp_path,
        "prod",
        (
            _info("com.acme.helper", version="3.0.0", latest_version="3.1.0"),
            _info("com.acme.other", version="2.0.0", latest_version="2.0.0"),
        ),
    )
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "updates"])
    assert result.exit_code == 0
    assert "com.acme.helper" in result.output
    assert "3.0.0" in result.output
    assert "3.1.0" in result.output
    assert "com.acme.other" not in result.output


def test_plugins_updates_prints_up_to_date_when_all_current(
    runner: CliRunner, tmp_path: Path
) -> None:
    _seed(
        tmp_path,
        "prod",
        (_info("com.acme.helper", version="3.1.0", latest_version="3.1.0"),),
    )
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "updates"])
    assert result.exit_code == 0
    assert "Up to date" in result.output


def test_plugins_updates_writes_yaml_when_queue_flag_provided(
    runner: CliRunner, tmp_path: Path
) -> None:
    _seed(
        tmp_path,
        "prod",
        (_info("com.acme.helper", version="3.0.0", latest_version="3.1.0"),),
    )
    runner.invoke(app, ["instance", "use", "prod"])
    out_file = tmp_path / "queue.yaml"
    result = runner.invoke(
        app, ["plugins", "updates", "--queue", str(out_file)]
    )
    assert result.exit_code == 0
    payload = _yaml.safe_load(out_file.read_text(encoding="utf-8"))
    assert payload["instance"] == "prod"
    assert payload["captured_at"]
    assert len(payload["updates"]) == 1
    update = payload["updates"][0]
    assert update["plugin_id"] == "com.acme.helper"
    assert update["current_version"] == "3.0.0"
    assert update["latest_version"] == "3.1.0"


def test_plugins_updates_does_not_write_yaml_when_queue_flag_omitted(
    runner: CliRunner, tmp_path: Path
) -> None:
    _seed(
        tmp_path,
        "prod",
        (_info("com.acme.helper", version="3.0.0", latest_version="3.1.0"),),
    )
    runner.invoke(app, ["instance", "use", "prod"])
    cwd_before = list(tmp_path.iterdir())
    runner.invoke(app, ["plugins", "updates"])
    cwd_after = list(tmp_path.iterdir())
    assert cwd_before == cwd_after


def test_plugins_updates_warns_when_inventory_missing(
    runner: CliRunner, tmp_path: Path
) -> None:
    _seed(tmp_path, "prod", None)
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "updates"])
    assert result.exit_code != 0
    assert "nexus instance refresh" in result.output


def test_plugins_updates_prints_pre_update_refresh_hint_when_queue_written(
    runner: CliRunner, tmp_path: Path
) -> None:
    _seed(
        tmp_path,
        "prod",
        (_info("com.acme.helper", version="3.0.0", latest_version="3.1.0"),),
    )
    runner.invoke(app, ["instance", "use", "prod"])
    out_file = tmp_path / "queue.yaml"
    result = runner.invoke(
        app, ["plugins", "updates", "--queue", str(out_file)]
    )
    assert "Before applying" in result.output
    assert "nexus instance refresh" in result.output
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_cli_plugins_updates.py -v --no-cov`
Expected: FAIL on missing `updates` subcommand.

- [ ] **Step 3: Extend _PLUGINS_HELP**

In `src/nexus/cli.py`, find the existing `_PLUGINS_HELP` list. Replace it with:

```python
_PLUGINS_HELP = [
    ("list", "Show all plugins with optional --product / --source / --state filters"),
    ("info <plugin_id>", "Show full details and dependencies for one plugin"),
    ("export", "Write the inventory to YAML or CSV"),
    ("diff <a> <b>", "Show cross-instance plugin differences"),
    ("promote <src> --to <dst>", "Write an action plan to make <dst> match <src>"),
    ("updates", "Show plugins with newer versions available"),
]
```

- [ ] **Step 4: Add updates import**

In `src/nexus/cli.py`, locate the existing `nexus.plugins` import block. Add `plugins_with_updates` to one of the import lines. The cleanest is to add a new line near the existing diff imports:

Existing:

```python
from nexus.plugins.diff import (
    PluginDiff,
    PluginDiffEntry,
    PromotionPlan,
    compute_diff,
    project_to_promote_plan,
)
```

Add immediately after it:

```python
from nexus.plugins.updates import plugins_with_updates
```

- [ ] **Step 5: Add the updates subcommand**

In `src/nexus/cli.py`, after the `plugins_promote` command (i.e., near the bottom of the `plugins_app` command definitions), add:

```python
@plugins_app.command("updates")
def plugins_updates(
    instance: Annotated[
        str,
        typer.Option(
            "--instance",
            help="Instance profile (default: configured default)",
        ),
    ] = "",
    queue: Annotated[
        str,
        typer.Option(
            "--queue",
            help="Write a YAML queue of pending updates to the given path.",
        ),
    ] = "",
) -> None:
    """Show plugins with newer versions available; optionally write a YAML queue."""
    meta, inventory = _load_inventory_or_exit(instance)
    pending = plugins_with_updates(inventory)
    if not pending:
        console.print(Notice.info("Up to date."))
        return
    rows: list[list[RenderableType]] = [
        [
            p.plugin_id,
            p.name,
            p.product_family,
            p.version,
            p.latest_version or "-",
        ]
        for p in pending
    ]
    console.print(
        DataTable(
            title="Updates available",
            columns=[
                DataColumn(header="Plugin ID", width=32),
                DataColumn(header="Name", width=20),
                DataColumn(header="Product", width=14),
                DataColumn(header="Current", width=12),
                DataColumn(header="Latest", width=12),
            ],
            rows=rows,
        )
    )
    console.print(Notice.info(f"{len(pending)} update(s) available."))
    if queue:
        payload: dict[str, object] = {
            "instance": meta.profile,
            "captured_at": inventory.captured_at.isoformat(),
            "updates": [
                {
                    "plugin_id": p.plugin_id,
                    "name": p.name,
                    "product_family": p.product_family,
                    "current_version": p.version,
                    "latest_version": p.latest_version,
                }
                for p in pending
            ],
        }
        Path(queue).write_text(_yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
        console.print(
            Hint(
                label="Before applying",
                command=f"nexus instance refresh {meta.profile}",
            )
        )
```

- [ ] **Step 6: Run tests to verify pass**

Run: `pytest tests/test_cli_plugins_updates.py -v --no-cov`
Expected: 6 PASS.

- [ ] **Step 7: No-regression check on the rest of the suite**

Run: `pytest tests/test_cli_instance.py tests/test_cli_plugins.py tests/test_cli_plugins_diff.py --no-cov -q`
Expected: existing pass-count unchanged from before this task.

- [ ] **Step 8: Run linters**

```
ruff check src/nexus/cli.py tests/test_cli_plugins_updates.py
pyright src/nexus/cli.py tests/test_cli_plugins_updates.py
mypy src/nexus/cli.py tests/test_cli_plugins_updates.py
```
Expected: all clean.

- [ ] **Step 9: Commit**

```bash
git add src/nexus/cli.py tests/test_cli_plugins_updates.py
git commit -m "feat(cli): add nexus plugins updates with optional YAML queue"
```

---

## Task 6: Final verification + ratchet refresh

**Files:**
- Modify: `.ratchet.json`

- [ ] **Step 1: Run full quality suite**

```
ruff check src/nexus tests
black --check src/nexus tests
pyright src/nexus
mypy src/nexus
pytest tests/ --ignore=tests/test_updater_runner.py --no-cov -q
```
Expected: all clean except the 4 known pre-existing failures (in CLAUDE.md / past commits).

If black flags any files, run `black src/nexus tests` and commit the formatting separately.

- [ ] **Step 2: Smoke-render the new command**

```
PYTHONIOENCODING=utf-8 .venv/Scripts/nexus plugins updates --help
```
Expected: help text renders without traceback, showing `--instance` and `--queue` options.

- [ ] **Step 3: Generate fresh coverage**

```
pytest tests/ --ignore=tests/test_updater_runner.py --cov=nexus --cov-report=json --cov-fail-under=0 -q --no-header --tb=no
```

- [ ] **Step 4: Inspect coverage of touched modules**

```
python -c "
import json
data = json.loads(open('coverage.json').read())
for k, v in sorted(data['files'].items()):
    nk = k.replace('\\\\', '/')
    if '/plugins/updates.py' in nk or '/plugins/__init__.py' in nk or '/plugins/scanner.py' in nk or '/plugins/models.py' in nk or '/nexus/cli.py' in nk:
        s = v['summary']
        rel = nk[nk.index('nexus/'):]
        mod = rel.replace('/', '.').removesuffix('.py')
        print(f'{mod}: covered={s[\"covered_lines\"]} total={s[\"num_statements\"]}')
"
```

- [ ] **Step 5: Update .ratchet.json**

Edit `.ratchet.json`:
- Bump `nexus.cli` to the new covered_lines / total_lines printed in Step 4.
- Bump `nexus.plugins.__init__` to the new covered_lines (it gained the `plugins_with_updates` import; total grows by 1).
- Bump `nexus.plugins.models` and `nexus.plugins.scanner` if their numbers grew. Coverage must not decrease for any module.
- Add a new entry `nexus.plugins.updates` with covered_lines / total_lines from Step 4.

Place the new `nexus.plugins.updates` entry alphabetically among the other `nexus.plugins.*` entries (between `scanner` and `__init__` works).

- [ ] **Step 6: Re-run the full suite to verify ratchet passes**

Run: `pytest tests/ --ignore=tests/test_updater_runner.py --no-cov -q`
Expected: same 4 pre-existing failures, all new tests pass.

- [ ] **Step 7: Commit**

```bash
git add .ratchet.json
git commit -m "chore(plugins): refresh ratchet for the updates layer"
```

- [ ] **Step 8: Verify branch state**

Run: `git log --oneline b34004b..HEAD`
Expected: 6 commits (one per task) on top of the spec commit on this branch.

---

## Self-review against spec

Spec section -> task mapping:

- "Layer placement" (one new file + 3 modify targets) -- Tasks 1-5.
- "Model change" (latest_version field with default None) -- Task 1.
- "Scanner change" (_STORE_FIELDS update + _from_store population) -- Task 2.
- "Pure function" (plugins_with_updates filter + sort) -- Task 3.
- "CLI surface" (updates subcommand, --instance, --queue) -- Task 5.
- "Queue YAML shape" (instance, captured_at, updates list with the 5 keys) -- Task 5 (payload dict construction).
- "Reuse from existing layers" (PluginInfo, _load_inventory_or_exit, _yaml, UI components) -- Tasks 2, 3, 5.
- "Errors / edge cases" (unknown profile, missing inventory, all up-to-date, no queue when omitted) -- Task 5 tests.
- "Testing strategy" (2 model tests, 2 scanner tests, 4 helper tests, 6 CLI tests = 14 new) -- Tasks 1, 2, 3, 5.
- "Out of scope" (triggering updates, release notes, rollback orchestration) -- not introduced.

Type-consistency check:

- `latest_version: str | None` field on PluginInfo is used identically in Task 1 (model), Task 2 (scanner population), Task 3 (filter), Task 5 (CLI rendering, YAML payload). No drift.
- `plugins_with_updates(inventory: PluginInventory) -> tuple[PluginInfo, ...]` signature matches between Task 3 (definition) and Task 5 (call).
- YAML payload keys (`instance`, `captured_at`, `updates`, plus `plugin_id`/`name`/`product_family`/`current_version`/`latest_version`) match between the spec, the Task 5 implementation, and the Task 5 CLI test assertions.
- `--queue` flag default value (`""`) and the empty-string `if queue:` gate in Task 5 are consistent with both the spec's "no file written when omitted" rule and the "does not write" CLI test.

Placeholder scan: none. Every step has either complete code or an exact command. No "TBD", no "similar to Task N".

Plan ready for execution.
