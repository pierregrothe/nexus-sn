# Capture Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `nexus.capture` -- a bidirectional ServiceNow configuration transport layer that scans live instances into YAML archives (custom elements only) and injects archives into target update sets.

**Architecture:** A dedicated layer between `connectors/` and `assessment/`, exposing a single `CaptureProtocol`. `CaptureEngine` wires together `ScopeDiscoverer`, `ConfigFetcher`, `ArchiveWriter`/`ArchiveReader`, `UpdateSetXmlBuilder`, and `UpdateSetWriter`. CLI, TUI, and Web UI bind to the protocol. All table queries include `sys_customer_update=true` to exclude OOTB records.

**Tech Stack:** Python 3.14+, Pydantic v2 (frozen + strict + no-extra), httpx (via ServiceNowClient), PyYAML, xml.etree.ElementTree, Typer (CLI), pytest + `tmp_path` (tests)

**Key codebase facts (read before implementing):**
- `NexusError` does NOT exist. `SNClientError(Exception)` and `AuthError(Exception)` extend `Exception` directly. `CaptureError` does the same.
- `ServiceNowClient.query_table` caps at 100 records (`min(limit, 100)`). Capture needs a new `list_records()` method without this cap.
- CLI uses `typer.Typer` (not Click). Async operations are wrapped in `asyncio.run()` inside sync typer callbacks.
- `FakeServiceNowClient` ignores query strings -- tests seed tables with exactly the expected records.

---

## File Map

**New files:**
```
src/nexus/capture/__init__.py
src/nexus/capture/errors.py
src/nexus/capture/models.py
src/nexus/capture/tables.py
src/nexus/capture/protocol.py
src/nexus/capture/scope.py
src/nexus/capture/fetcher.py
src/nexus/capture/archive.py
src/nexus/capture/xml_builder.py
src/nexus/capture/update_set.py
src/nexus/capture/engine.py
tests/capture/__init__.py
tests/capture/test_errors.py
tests/capture/test_models.py
tests/capture/test_scope_discoverer.py
tests/capture/test_config_fetcher.py
tests/capture/test_archive.py
tests/capture/test_xml_builder.py
tests/capture/test_update_set_writer.py
tests/capture/test_capture_engine.py
tests/capture/fakes/__init__.py
tests/capture/fakes/fake_capture_engine.py
```

**Modified files:**
```
src/nexus/config/paths.py          -- add archives_dir property + ensure_dirs entry
src/nexus/connectors/servicenow/client.py  -- add list_records() + count_records()
tests/fakes/fake_sn_client.py      -- add list_records() + count_records()
src/nexus/cli.py                   -- add capture_app Typer group
.ratchet.json                      -- add capture module baselines
.primer/roadmap.md                 -- move capture to foundation
.primer/active.md                  -- update focus
```

---

## Task 1: NexusPaths.archives_dir + CaptureError hierarchy

**Files:**
- Modify: `src/nexus/config/paths.py`
- Create: `src/nexus/capture/errors.py`
- Create: `tests/capture/__init__.py` (empty)
- Create: `tests/capture/test_errors.py`

- [ ] **Step 1.1: Add `archives_dir` property to NexusPaths**

In `src/nexus/config/paths.py`, add after the `instances_dir` property and inside `ensure_dirs`:

```python
@property
def archives_dir(self) -> Path:
    """Local capture archives root."""
    return self.root / "archives"
```

In `ensure_dirs`, add `self.archives_dir` to the tuple:
```python
def ensure_dirs(self) -> None:
    """Create all runtime directories if they do not exist."""
    for path in (
        self.root,
        self.templates_dir,
        self.reports_dir,
        self.jobs_dir,
        self.logs_dir,
        self.cache_dir,
        self.instances_dir,
        self.archives_dir,      # <-- add this line
    ):
        path.mkdir(parents=True, exist_ok=True)
    log.debug("runtime directories ensured under %s", self.root)
```

- [ ] **Step 1.2: Write failing test for archives_dir**

Create `tests/capture/__init__.py` (empty file).

Create `tests/capture/test_errors.py`:
```python
# tests/capture/test_errors.py
# Tests for the capture layer error hierarchy.
# Author: Pierre Grothe
# Date: 2026-05-09

from pathlib import Path

from nexus.capture.errors import (
    ArchiveCorruptError,
    CaptureError,
    ScopeNotFoundError,
    TableUnavailableError,
    UpdateSetError,
)


def test_scope_not_found_error_is_capture_error() -> None:
    err = ScopeNotFoundError(scope_id="abc123", instance_id="dev")
    assert isinstance(err, CaptureError)
    assert err.scope_id == "abc123"
    assert err.instance_id == "dev"
    assert "abc123" in str(err)


def test_table_unavailable_error_is_capture_error() -> None:
    err = TableUnavailableError(table="ai_skill", instance_id="dev")
    assert isinstance(err, CaptureError)
    assert err.table == "ai_skill"


def test_archive_corrupt_error_is_capture_error() -> None:
    err = ArchiveCorruptError(archive_dir=Path("/tmp/missing"))
    assert isinstance(err, CaptureError)
    assert err.archive_dir == Path("/tmp/missing")


def test_update_set_error_is_capture_error() -> None:
    err = UpdateSetError(
        update_set_name="NEXUS-capture",
        instance_id="dev",
        failed_record_sys_id="abc",
        failed_table="ai_skill",
    )
    assert isinstance(err, CaptureError)
    assert err.failed_table == "ai_skill"
```

- [ ] **Step 1.3: Run test to verify it fails**

```bash
pytest tests/capture/test_errors.py -v
```
Expected: `ModuleNotFoundError: No module named 'nexus.capture'`

- [ ] **Step 1.4: Create errors.py**

```python
# src/nexus/capture/errors.py
# Capture layer error hierarchy.
# Author: Pierre Grothe
# Date: 2026-05-09

"""Typed exceptions for the capture layer."""

from pathlib import Path

__all__ = [
    "CaptureError",
    "ScopeNotFoundError",
    "TableUnavailableError",
    "ArchiveCorruptError",
    "UpdateSetError",
]


class CaptureError(Exception):
    """Base class for all capture layer errors."""


class ScopeNotFoundError(CaptureError):
    """Requested application scope not found on the instance."""

    def __init__(self, scope_id: str, instance_id: str) -> None:
        """Initialize with scope and instance identifiers."""
        super().__init__(f"Scope {scope_id!r} not found on {instance_id!r}")
        self.scope_id = scope_id
        self.instance_id = instance_id


class TableUnavailableError(CaptureError):
    """Table returned HTTP 400/404 -- absent on this instance (e.g. PDI)."""

    def __init__(self, table: str, instance_id: str) -> None:
        """Initialize with table name and instance identifier."""
        super().__init__(f"Table {table!r} unavailable on {instance_id!r}")
        self.table = table
        self.instance_id = instance_id


class ArchiveCorruptError(CaptureError):
    """Archive manifest missing or YAML invalid."""

    def __init__(self, archive_dir: Path) -> None:
        """Initialize with archive directory path."""
        super().__init__(f"Archive corrupt or missing manifest: {archive_dir}")
        self.archive_dir = archive_dir


class UpdateSetError(CaptureError):
    """Failed to inject a record into the target update set."""

    def __init__(
        self,
        update_set_name: str,
        instance_id: str,
        failed_record_sys_id: str,
        failed_table: str,
    ) -> None:
        """Initialize with update set and record identifiers."""
        super().__init__(
            f"Failed to inject {failed_table}/{failed_record_sys_id} "
            f"into update set {update_set_name!r} on {instance_id!r}"
        )
        self.update_set_name = update_set_name
        self.instance_id = instance_id
        self.failed_record_sys_id = failed_record_sys_id
        self.failed_table = failed_table
```

Also create `src/nexus/capture/__init__.py` (empty for now -- filled in Task 10):
```python
# src/nexus/capture/__init__.py
# NEXUS capture layer -- bidirectional SN config transport.
# Author: Pierre Grothe
# Date: 2026-05-09
```

- [ ] **Step 1.5: Run tests to verify they pass**

```bash
pytest tests/capture/test_errors.py -v
```
Expected: 4 tests PASS

- [ ] **Step 1.6: Commit**

```bash
git add src/nexus/config/paths.py src/nexus/capture/__init__.py \
        src/nexus/capture/errors.py tests/capture/__init__.py \
        tests/capture/test_errors.py
git commit -m "feat(capture): add archives_dir to NexusPaths and CaptureError hierarchy"
```

---

## Task 2: Data models + table manifest

**Files:**
- Create: `src/nexus/capture/models.py`
- Create: `src/nexus/capture/tables.py`
- Create: `tests/capture/test_models.py`

- [ ] **Step 2.1: Write failing tests for models and table manifest**

Create `tests/capture/test_models.py`:
```python
# tests/capture/test_models.py
# Tests for capture layer data models.
# Author: Pierre Grothe
# Date: 2026-05-09

from datetime import UTC, datetime
from pathlib import Path

import pytest

from nexus.capture.models import (
    ArchiveManifest,
    CaptureResult,
    ConfigRecord,
    ScopeEntry,
    ScopeManifest,
    SnRefField,
    UpdateSetRef,
)
from nexus.capture.tables import (
    AI_AUTOMATION,
    DEFAULT_TABLE_GROUPS,
    RelatedTable,
    TableGroup,
    TableSpec,
)

NOW = datetime.now(UTC)


def test_scope_entry_constructs_with_table_counts() -> None:
    entry = ScopeEntry(
        sys_id="scope001",
        name="NowAssist HRSD",
        scope="x_snc_nowassist_hrsd",
        version="1.0.0",
        vendor="ServiceNow",
        table_counts={"ai_skill": 3, "sys_hub_flow": 8},
    )
    assert entry.table_counts["ai_skill"] == 3


def test_scope_manifest_contains_entries() -> None:
    entry = ScopeEntry(
        sys_id="s1", name="App", scope="x_app", version="1", vendor="SN",
        table_counts={},
    )
    manifest = ScopeManifest(
        instance_id="dev", captured_at=NOW, scopes=(entry,)
    )
    assert len(manifest.scopes) == 1


def test_config_record_plain_string_field() -> None:
    record = ConfigRecord(
        sys_id="r1",
        table="ai_skill",
        scope_sys_id="s1",
        scope_name="x_app",
        captured_at=NOW,
        fields={"name": "My Skill", "active": "true"},
        parent_sys_id=None,
    )
    assert record.fields["name"] == "My Skill"


def test_config_record_ref_field() -> None:
    ref: SnRefField = {"value": "sys_id_abc", "display_value": "Global"}
    record = ConfigRecord(
        sys_id="r1",
        table="ai_skill",
        scope_sys_id="s1",
        scope_name="x_app",
        captured_at=NOW,
        fields={"sys_scope": ref},
        parent_sys_id=None,
    )
    assert record.fields["sys_scope"] == ref


def test_capture_result_by_table_groups_correctly() -> None:
    r1 = ConfigRecord(
        sys_id="r1", table="ai_skill", scope_sys_id="s1", scope_name="x",
        captured_at=NOW, fields={}, parent_sys_id=None,
    )
    r2 = ConfigRecord(
        sys_id="r2", table="sys_hub_flow", scope_sys_id="s1", scope_name="x",
        captured_at=NOW, fields={}, parent_sys_id=None,
    )
    r3 = ConfigRecord(
        sys_id="r3", table="ai_skill", scope_sys_id="s1", scope_name="x",
        captured_at=NOW, fields={}, parent_sys_id=None,
    )
    result = CaptureResult(
        instance_id="dev", captured_at=NOW, scope_ids=("s1",),
        table_group="ai_automation", records=(r1, r2, r3),
    )
    by_table = result.by_table()
    assert len(by_table["ai_skill"]) == 2
    assert len(by_table["sys_hub_flow"]) == 1


def test_ai_automation_group_contains_expected_tables() -> None:
    names = {spec.name for spec in AI_AUTOMATION.tables}
    assert "ai_skill" in names
    assert "sys_hub_flow" in names
    assert "sys_hub_action_type_definition" in names


def test_table_spec_related_table_has_join_field() -> None:
    flow_spec = next(s for s in AI_AUTOMATION.tables if s.name == "sys_hub_flow")
    assert any(r.join_field == "flow" for r in flow_spec.related)


def test_default_table_groups_contains_ai_automation() -> None:
    assert "ai_automation" in DEFAULT_TABLE_GROUPS
```

- [ ] **Step 2.2: Run test to verify it fails**

```bash
pytest tests/capture/test_models.py -v
```
Expected: `ModuleNotFoundError: No module named 'nexus.capture.models'`

- [ ] **Step 2.3: Create models.py**

```python
# src/nexus/capture/models.py
# Data models for the capture layer.
# Author: Pierre Grothe
# Date: 2026-05-09

"""Pydantic models and type aliases for ServiceNow configuration capture."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TypedDict

from pydantic import BaseModel, ConfigDict

__all__ = [
    "SnRefField",
    "SnFieldValue",
    "SnRecord",
    "ScopeEntry",
    "ScopeManifest",
    "ConfigRecord",
    "CaptureResult",
    "ArchiveManifest",
    "UpdateSetRef",
]


class SnRefField(TypedDict):
    """ServiceNow reference field with both sys_id value and display label."""

    value: str
    display_value: str


type SnFieldValue = str | SnRefField
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
    captured_at: datetime
    scopes: tuple[ScopeEntry, ...]


class ConfigRecord(BaseModel):
    """One captured record from a ServiceNow table."""

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    sys_id: str
    table: str
    scope_sys_id: str
    scope_name: str
    captured_at: datetime
    fields: SnRecord
    parent_sys_id: str | None = None


class CaptureResult(BaseModel):
    """Full result of a capture operation across one or more scopes."""

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    instance_id: str
    captured_at: datetime
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
    captured_at: datetime
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
```

- [ ] **Step 2.4: Create tables.py**

```python
# src/nexus/capture/tables.py
# Pluggable table manifest registry for the capture layer.
# Author: Pierre Grothe
# Date: 2026-05-09

"""Table groups and specs defining which SN tables belong to each config domain."""

from dataclasses import dataclass

__all__ = [
    "RelatedTable",
    "TableSpec",
    "TableGroup",
    "AI_AUTOMATION",
    "DEFAULT_TABLE_GROUPS",
]


@dataclass(slots=True, frozen=True)
class RelatedTable:
    """A child table fetched together with its parent record.

    Args:
        name: Table API name of the child table.
        join_field: Field on the child table that references the parent sys_id.
    """

    name: str
    join_field: str


@dataclass(slots=True, frozen=True)
class TableSpec:
    """One table included in a capture group.

    Args:
        name: Table API name, e.g. "ai_skill".
        display: Human-readable label for CLI output.
        scope_field: Field on this table carrying the application scope ref.
        related: Child tables fetched in the same pass as this table's records.
        key_fields: Fields to include in the archive record summary.
    """

    name: str
    display: str
    scope_field: str = "sys_scope"
    related: tuple[RelatedTable, ...] = ()
    key_fields: tuple[str, ...] = ("sys_id", "name", "sys_scope")


@dataclass(slots=True, frozen=True)
class TableGroup:
    """A named collection of TableSpecs forming one config domain.

    Args:
        key: Machine-readable identifier used in CLI and archive manifests.
        display: Human-readable label for CLI output.
        tables: The tables belonging to this group.
    """

    key: str
    display: str
    tables: tuple[TableSpec, ...]


AI_AUTOMATION: TableGroup = TableGroup(
    key="ai_automation",
    display="AI & Automation",
    tables=(
        TableSpec(
            name="ai_skill",
            display="NowAssist Skills",
        ),
        TableSpec(
            name="sys_hub_flow",
            display="Flows & Subflows",
            related=(
                RelatedTable(name="sys_hub_flow_input", join_field="flow"),
                RelatedTable(name="sys_hub_flow_logic", join_field="flow"),
            ),
        ),
        TableSpec(
            name="sys_hub_action_type_definition",
            display="IntegrationHub Actions",
        ),
        TableSpec(
            name="virtual_agent_conversation_topic",
            display="Virtual Agent Topics",
            related=(RelatedTable(name="sn_va_topic_block", join_field="topic"),),
        ),
        TableSpec(
            name="sys_ai_agent",
            display="AI Agents",
            related=(RelatedTable(name="sys_ai_agent_capability", join_field="agent"),),
        ),
    ),
)

DEFAULT_TABLE_GROUPS: dict[str, TableGroup] = {
    AI_AUTOMATION.key: AI_AUTOMATION,
}
```

- [ ] **Step 2.5: Run tests**

```bash
pytest tests/capture/test_models.py -v
```
Expected: all 7 tests PASS

- [ ] **Step 2.6: Commit**

```bash
git add src/nexus/capture/models.py src/nexus/capture/tables.py \
        tests/capture/test_models.py
git commit -m "feat(capture): data models, SnRecord type alias, and AI_AUTOMATION table manifest"
```

---

## Task 3: CaptureProtocol

**Files:**
- Create: `src/nexus/capture/protocol.py`

- [ ] **Step 3.1: Create protocol.py**

This is a structural `Protocol`. mypy/pyright verify conformance -- no runtime tests needed.

```python
# src/nexus/capture/protocol.py
# Public protocol surface for the capture layer.
# Author: Pierre Grothe
# Date: 2026-05-09

"""CaptureProtocol: the interface CLI, TUI, and Web UI bind to."""

from pathlib import Path
from typing import Protocol

from nexus.capture.models import (
    ArchiveManifest,
    CaptureResult,
    ScopeManifest,
    UpdateSetRef,
)

__all__ = ["CaptureProtocol"]


class CaptureProtocol(Protocol):
    """Bidirectional ServiceNow configuration transport."""

    async def discover_scopes(
        self,
        instance_id: str,
        table_group: str = "ai_automation",
    ) -> ScopeManifest:
        """Discover all application scopes on the instance with per-table counts.

        Args:
            instance_id: Registered instance profile name.
            table_group: Which table group to count records for.

        Returns:
            ScopeManifest listing all scopes and per-table record counts.
        """

    async def capture(
        self,
        instance_id: str,
        scope_ids: list[str],
        table_group: str = "ai_automation",
    ) -> CaptureResult:
        """Fetch all custom configurations in the given scopes from a live instance.

        Tables that return HTTP 400/404 are skipped with a warning.

        Args:
            instance_id: Registered instance profile name.
            scope_ids: sys_id values of application scopes to capture.
            table_group: Which table group to scan.

        Returns:
            CaptureResult with all matching records.
        """

    def save_archive(
        self,
        result: CaptureResult,
        dest: Path | None = None,
    ) -> ArchiveManifest:
        """Serialize a CaptureResult to YAML on disk.

        Args:
            result: The result to persist.
            dest: Archive root directory. Defaults to
                  ~/.nexus/archives/{instance_id}/{timestamp}/.

        Returns:
            ArchiveManifest with archive location and record count.
        """

    def load_archive(self, manifest_path: Path) -> CaptureResult:
        """Deserialize a previously saved archive into a CaptureResult.

        Args:
            manifest_path: Path to manifest.yaml inside an archive directory.

        Returns:
            CaptureResult reconstructed from YAML.

        Raises:
            ArchiveCorruptError: If the manifest is missing or YAML is invalid.
        """

    async def push_to_update_set(
        self,
        result: CaptureResult,
        instance_id: str,
        update_set_name: str,
    ) -> UpdateSetRef:
        """Inject all records from a CaptureResult into an update set.

        Creates the update set if it does not exist. Reuses an in-progress
        update set with the same name if one is found.

        Args:
            result: CaptureResult to deploy.
            instance_id: Target registered instance profile.
            update_set_name: Name for the update set on the target.

        Returns:
            UpdateSetRef for the created or updated update set.

        Raises:
            UpdateSetError: If any record injection fails (fails fast).
        """
```

- [ ] **Step 3.2: Commit**

```bash
git add src/nexus/capture/protocol.py
git commit -m "feat(capture): CaptureProtocol structural interface"
```

---

## Task 4: ServiceNowClient extensions

The existing `query_table` caps at 100 records. Capture needs unlimited pagination and aggregate counts.

**Files:**
- Modify: `src/nexus/connectors/servicenow/client.py`
- Modify: `tests/fakes/fake_sn_client.py`

- [ ] **Step 4.1: Write failing tests for the new client methods**

Create `tests/connectors/test_servicenow_client_extensions.py`:

```python
# tests/connectors/test_servicenow_client_extensions.py
# Tests for list_records and count_records on ServiceNowClient.
# Author: Pierre Grothe
# Date: 2026-05-09

import pytest

from tests.fakes.fake_sn_client import FakeServiceNowClient


@pytest.mark.asyncio
async def test_list_records_returns_all_records_without_cap() -> None:
    records = [{"sys_id": str(i), "name": f"Record {i}"} for i in range(150)]
    client = FakeServiceNowClient(initial_records={"ai_skill": records})
    async with client:
        result = await client.list_records("ai_skill", limit=150, offset=0)
    assert len(result) == 150


@pytest.mark.asyncio
async def test_list_records_respects_offset() -> None:
    records = [{"sys_id": str(i)} for i in range(10)]
    client = FakeServiceNowClient(initial_records={"ai_skill": records})
    async with client:
        page1 = await client.list_records("ai_skill", limit=5, offset=0)
        page2 = await client.list_records("ai_skill", limit=5, offset=5)
    assert [r["sys_id"] for r in page1] == [str(i) for i in range(5)]
    assert [r["sys_id"] for r in page2] == [str(i) for i in range(5, 10)]


@pytest.mark.asyncio
async def test_count_records_returns_total() -> None:
    records = [{"sys_id": str(i)} for i in range(7)]
    client = FakeServiceNowClient(initial_records={"ai_skill": records})
    async with client:
        count = await client.count_records("ai_skill")
    assert count == 7


@pytest.mark.asyncio
async def test_count_records_on_empty_table_returns_zero() -> None:
    client = FakeServiceNowClient()
    async with client:
        count = await client.count_records("ai_skill")
    assert count == 0
```

- [ ] **Step 4.2: Run to verify failure**

```bash
pytest tests/connectors/test_servicenow_client_extensions.py -v
```
Expected: `AttributeError: 'FakeServiceNowClient' object has no attribute 'list_records'`

- [ ] **Step 4.3: Add list_records and count_records to FakeServiceNowClient**

In `tests/fakes/fake_sn_client.py`, add after the existing `query_table` method:

```python
async def list_records(
    self,
    table: str,
    query: str = "",
    limit: int = 1000,
    offset: int = 0,
    fields: str = "",
    display_value: str = "false",
) -> list[dict[str, Any]]:
    """Return a page of records from the in-memory table.

    Args:
        table: Table name.
        query: Ignored in fake -- returns all records in page window.
        limit: Maximum records to return.
        offset: Starting record index.
        fields: Ignored in fake.
        display_value: Ignored in fake.

    Returns:
        List of record dicts for the requested page.
    """
    all_records = self._tables.get(table, [])
    return all_records[offset : offset + limit]

async def count_records(self, table: str, query: str = "") -> int:
    """Return the total count of records in the table.

    Args:
        table: Table name.
        query: Ignored in fake -- counts all records.

    Returns:
        Total record count.
    """
    return len(self._tables.get(table, []))
```

- [ ] **Step 4.4: Add list_records and count_records to ServiceNowClient**

In `src/nexus/connectors/servicenow/client.py`, add after `query_table`:

```python
_STATS_API_BASE = "/api/now/stats"

async def list_records(
    self,
    table: str,
    query: str = "",
    limit: int = 1000,
    offset: int = 0,
    fields: str = "",
    display_value: str = "false",
) -> list[dict[str, Any]]:
    """Query a ServiceNow table with full pagination support.

    Unlike query_table, this method applies no cap on limit and supports
    offset-based pagination for iterating over large result sets.

    Args:
        table: Table API name.
        query: Encoded query string.
        limit: Maximum records to return per page.
        offset: Record index to start from (0-based).
        fields: Comma-separated field names to return.
        display_value: "true", "false", or "all" (value + display_value pairs).

    Returns:
        List of record dicts for the requested page.
    """
    params: dict[str, str | int] = {
        "sysparm_limit": limit,
        "sysparm_offset": offset,
        "sysparm_display_value": display_value,
    }
    if query:
        params["sysparm_query"] = query
    if fields:
        params["sysparm_fields"] = fields
    response = await self._get(f"{_TABLE_API_BASE}/{table}", params=params)
    return list(response.get("result", []))

async def count_records(self, table: str, query: str = "") -> int:
    """Return the total count of records matching the query via the Aggregate API.

    Args:
        table: Table API name.
        query: Encoded query string.

    Returns:
        Total matching record count.
    """
    params: dict[str, str] = {"sysparm_count": "true"}
    if query:
        params["sysparm_query"] = query
    response = await self._get(f"{_STATS_API_BASE}/{table}", params=params)
    count_str = response.get("result", {}).get("stats", {}).get("count", "0")
    return int(count_str)
```

Note: `_STATS_API_BASE` is a module-level constant. Add it near `_TABLE_API_BASE`.

- [ ] **Step 4.5: Run tests**

```bash
pytest tests/connectors/test_servicenow_client_extensions.py -v
```
Expected: 4 tests PASS

- [ ] **Step 4.6: Run full suite to check no regressions**

```bash
pytest -x -q
```
Expected: all existing tests PASS

- [ ] **Step 4.7: Commit**

```bash
git add src/nexus/connectors/servicenow/client.py \
        tests/fakes/fake_sn_client.py \
        tests/connectors/test_servicenow_client_extensions.py
git commit -m "feat(connectors): add list_records() + count_records() for capture layer"
```

---

## Task 5: ScopeDiscoverer

**Files:**
- Create: `src/nexus/capture/scope.py`
- Create: `tests/capture/test_scope_discoverer.py`

- [ ] **Step 5.1: Write failing tests**

Create `tests/capture/test_scope_discoverer.py`:

```python
# tests/capture/test_scope_discoverer.py
# Tests for ScopeDiscoverer.
# Author: Pierre Grothe
# Date: 2026-05-09

import pytest

from tests.fakes.fake_sn_client import FakeServiceNowClient
from nexus.capture.scope import ScopeDiscoverer
from nexus.capture.tables import DEFAULT_TABLE_GROUPS

_SCOPE_ROW = {
    "sys_id": "scope001",
    "name": "NowAssist HRSD",
    "scope": "x_snc_nowassist_hrsd",
    "version": "1.0.0",
    "vendor": "ServiceNow",
}


@pytest.mark.asyncio
async def test_discover_scopes_returns_manifest_with_counts() -> None:
    client = FakeServiceNowClient(
        initial_records={
            "sys_scope": [_SCOPE_ROW],
            "ai_skill": [{"sys_id": "s1"}, {"sys_id": "s2"}],
            "sys_hub_flow": [{"sys_id": "f1"}],
        }
    )
    discoverer = ScopeDiscoverer(client, DEFAULT_TABLE_GROUPS)
    async with client:
        manifest = await discoverer.discover("dev-instance", "ai_automation")

    assert manifest.instance_id == "dev-instance"
    assert len(manifest.scopes) == 1
    scope = manifest.scopes[0]
    assert scope.sys_id == "scope001"
    assert scope.scope == "x_snc_nowassist_hrsd"
    assert scope.table_counts["ai_skill"] == 2
    assert scope.table_counts["sys_hub_flow"] == 1


@pytest.mark.asyncio
async def test_discover_scopes_with_empty_instance_returns_empty_manifest() -> None:
    client = FakeServiceNowClient(initial_records={"sys_scope": []})
    discoverer = ScopeDiscoverer(client, DEFAULT_TABLE_GROUPS)
    async with client:
        manifest = await discoverer.discover("dev-instance", "ai_automation")

    assert manifest.instance_id == "dev-instance"
    assert len(manifest.scopes) == 0


@pytest.mark.asyncio
async def test_discover_scopes_skips_table_not_in_group() -> None:
    client = FakeServiceNowClient(
        initial_records={"sys_scope": [_SCOPE_ROW]}
    )
    discoverer = ScopeDiscoverer(client, DEFAULT_TABLE_GROUPS)
    async with client:
        manifest = await discoverer.discover("dev-instance", "ai_automation")

    scope = manifest.scopes[0]
    # Tables not seeded return zero -- not missing from counts
    assert scope.table_counts.get("ai_skill", 0) == 0
```

- [ ] **Step 5.2: Run to verify failure**

```bash
pytest tests/capture/test_scope_discoverer.py -v
```
Expected: `ModuleNotFoundError: No module named 'nexus.capture.scope'`

- [ ] **Step 5.3: Implement ScopeDiscoverer**

```python
# src/nexus/capture/scope.py
# Discovers application scopes on a ServiceNow instance.
# Author: Pierre Grothe
# Date: 2026-05-09

"""ScopeDiscoverer: queries sys_scope and counts records per table per scope."""

import logging
from datetime import UTC, datetime

from nexus.capture.models import ScopeEntry, ScopeManifest
from nexus.capture.tables import TableGroup
from nexus.connectors.servicenow.client import ServiceNowClient

log = logging.getLogger(__name__)

__all__ = ["ScopeDiscoverer"]

_SCOPE_FIELDS = "sys_id,name,scope,version,vendor"
_SCOPE_PAGE = 500


class ScopeDiscoverer:
    """Discovers application scopes and counts custom records per table.

    Args:
        client: Open ServiceNowClient for the target instance.
        table_groups: Mapping of group key to TableGroup.
    """

    def __init__(
        self,
        client: ServiceNowClient,
        table_groups: dict[str, TableGroup],
    ) -> None:
        """Initialize with an open client and the table group registry."""
        self._client = client
        self._groups = table_groups

    async def discover(self, instance_id: str, table_group: str) -> ScopeManifest:
        """Return all application scopes with custom record counts.

        Args:
            instance_id: Registered instance profile name (used in manifest).
            table_group: Key into DEFAULT_TABLE_GROUPS to count records for.

        Returns:
            ScopeManifest with one ScopeEntry per discovered scope.
        """
        group = self._groups[table_group]
        raw_scopes = await self._client.list_records(
            "sys_scope",
            fields=_SCOPE_FIELDS,
            limit=_SCOPE_PAGE,
        )
        log.info("discovered %d scopes on %s", len(raw_scopes), instance_id)

        entries: list[ScopeEntry] = []
        for row in raw_scopes:
            scope_sys_id = str(row.get("sys_id", ""))
            counts: dict[str, int] = {}
            for spec in group.tables:
                query = f"sys_customer_update=true^sys_scope={scope_sys_id}"
                counts[spec.name] = await self._client.count_records(
                    spec.name, query=query
                )
            entries.append(
                ScopeEntry(
                    sys_id=scope_sys_id,
                    name=str(row.get("name", "")),
                    scope=str(row.get("scope", "")),
                    version=str(row.get("version", "")),
                    vendor=str(row.get("vendor", "")),
                    table_counts=counts,
                )
            )

        return ScopeManifest(
            instance_id=instance_id,
            captured_at=datetime.now(UTC),
            scopes=tuple(entries),
        )
```

- [ ] **Step 5.4: Run tests**

```bash
pytest tests/capture/test_scope_discoverer.py -v
```
Expected: 3 tests PASS

- [ ] **Step 5.5: Commit**

```bash
git add src/nexus/capture/scope.py tests/capture/test_scope_discoverer.py
git commit -m "feat(capture): ScopeDiscoverer with sys_customer_update filter"
```

---

## Task 6: ConfigFetcher

**Files:**
- Create: `src/nexus/capture/fetcher.py`
- Create: `tests/capture/test_config_fetcher.py`

- [ ] **Step 6.1: Write failing tests**

Create `tests/capture/test_config_fetcher.py`:

```python
# tests/capture/test_config_fetcher.py
# Tests for ConfigFetcher.
# Author: Pierre Grothe
# Date: 2026-05-09

import pytest
from datetime import UTC, datetime

from tests.fakes.fake_sn_client import FakeServiceNowClient
from nexus.capture.fetcher import ConfigFetcher
from nexus.capture.tables import DEFAULT_TABLE_GROUPS

_SCOPE_ID = "scope001"
_NOW = datetime.now(UTC)


def _skill(sys_id: str) -> dict:
    return {"sys_id": sys_id, "name": f"Skill {sys_id}", "sys_scope": _SCOPE_ID,
            "sys_customer_update": "true"}


def _flow(sys_id: str) -> dict:
    return {"sys_id": sys_id, "name": f"Flow {sys_id}", "sys_scope": _SCOPE_ID,
            "sys_customer_update": "true"}


def _logic(sys_id: str, flow_id: str) -> dict:
    return {"sys_id": sys_id, "flow": flow_id, "sys_scope": _SCOPE_ID,
            "sys_customer_update": "true"}


@pytest.mark.asyncio
async def test_fetch_records_returns_config_records_for_scope() -> None:
    client = FakeServiceNowClient(initial_records={
        "ai_skill": [_skill("s1"), _skill("s2")],
    })
    fetcher = ConfigFetcher(client, DEFAULT_TABLE_GROUPS)
    async with client:
        records = await fetcher.fetch(
            instance_id="dev", scope_ids=[_SCOPE_ID], table_group="ai_automation"
        )

    skill_records = [r for r in records if r.table == "ai_skill"]
    assert len(skill_records) == 2
    assert {r.sys_id for r in skill_records} == {"s1", "s2"}


@pytest.mark.asyncio
async def test_fetch_records_includes_related_records() -> None:
    client = FakeServiceNowClient(initial_records={
        "sys_hub_flow": [_flow("f1")],
        "sys_hub_flow_logic": [_logic("l1", "f1"), _logic("l2", "f1")],
    })
    fetcher = ConfigFetcher(client, DEFAULT_TABLE_GROUPS)
    async with client:
        records = await fetcher.fetch(
            instance_id="dev", scope_ids=[_SCOPE_ID], table_group="ai_automation"
        )

    logic_records = [r for r in records if r.table == "sys_hub_flow_logic"]
    assert len(logic_records) == 2
    assert all(r.parent_sys_id == "f1" for r in logic_records)


@pytest.mark.asyncio
async def test_fetch_records_unavailable_table_returns_empty_and_continues() -> None:
    # FakeServiceNowClient returns [] for unknown tables -- simulates unavailable
    client = FakeServiceNowClient(initial_records={
        "ai_skill": [_skill("s1")],
        # sys_hub_flow not seeded -> returns [] (simulates 400/404 being caught)
    })
    fetcher = ConfigFetcher(client, DEFAULT_TABLE_GROUPS)
    async with client:
        records = await fetcher.fetch(
            instance_id="dev", scope_ids=[_SCOPE_ID], table_group="ai_automation"
        )

    tables_seen = {r.table for r in records}
    assert "ai_skill" in tables_seen
    assert "sys_hub_flow" not in tables_seen


@pytest.mark.asyncio
async def test_fetch_records_paginates_large_result_set() -> None:
    skills = [_skill(str(i)) for i in range(25)]
    client = FakeServiceNowClient(initial_records={"ai_skill": skills})
    fetcher = ConfigFetcher(client, DEFAULT_TABLE_GROUPS, page_size=10)
    async with client:
        records = await fetcher.fetch(
            instance_id="dev", scope_ids=[_SCOPE_ID], table_group="ai_automation"
        )

    skill_records = [r for r in records if r.table == "ai_skill"]
    assert len(skill_records) == 25
```

- [ ] **Step 6.2: Run to verify failure**

```bash
pytest tests/capture/test_config_fetcher.py -v
```
Expected: `ModuleNotFoundError: No module named 'nexus.capture.fetcher'`

- [ ] **Step 6.3: Implement ConfigFetcher**

```python
# src/nexus/capture/fetcher.py
# Paginates the ServiceNow Table API to capture custom configuration records.
# Author: Pierre Grothe
# Date: 2026-05-09

"""ConfigFetcher: fetches custom records per scope+table with pagination."""

import logging
from datetime import UTC, datetime

from nexus.capture.models import ConfigRecord
from nexus.capture.tables import RelatedTable, TableGroup, TableSpec
from nexus.connectors.servicenow.client import ServiceNowClient
from nexus.connectors.servicenow.errors import SNClientError

log = logging.getLogger(__name__)

__all__ = ["ConfigFetcher"]

_DEFAULT_PAGE_SIZE = 1000


class ConfigFetcher:
    """Fetches custom records for a given scope and table group.

    All queries include sys_customer_update=true to exclude OOTB records.

    Args:
        client: Open ServiceNowClient for the source instance.
        table_groups: Mapping of group key to TableGroup.
        page_size: Records per paginated request.
    """

    def __init__(
        self,
        client: ServiceNowClient,
        table_groups: dict[str, TableGroup],
        page_size: int = _DEFAULT_PAGE_SIZE,
    ) -> None:
        """Initialize with client, table registry, and pagination size."""
        self._client = client
        self._groups = table_groups
        self._page_size = page_size

    async def fetch(
        self,
        instance_id: str,
        scope_ids: list[str],
        table_group: str,
    ) -> list[ConfigRecord]:
        """Fetch all custom records for the given scopes.

        Args:
            instance_id: Instance profile name used in ConfigRecord metadata.
            scope_ids: Application scope sys_ids to capture.
            table_group: Key into the table group registry.

        Returns:
            Flat list of ConfigRecord (root records and related records).
        """
        group = self._groups[table_group]
        now = datetime.now(UTC)
        all_records: list[ConfigRecord] = []

        for scope_sys_id in scope_ids:
            for spec in group.tables:
                root_records = await self._fetch_table(
                    spec, scope_sys_id, instance_id, now
                )
                all_records.extend(root_records)

                for related in spec.related:
                    for root in root_records:
                        child_records = await self._fetch_related(
                            related, root.sys_id, scope_sys_id, instance_id, now
                        )
                        all_records.extend(child_records)

        return all_records

    async def _fetch_table(
        self,
        spec: TableSpec,
        scope_sys_id: str,
        instance_id: str,
        now: datetime,
    ) -> list[ConfigRecord]:
        query = f"sys_customer_update=true^{spec.scope_field}={scope_sys_id}"
        raw = await self._fetch_all_pages(spec.name, query)
        records = []
        for row in raw:
            sys_id = str(row.get("sys_id", ""))
            records.append(
                ConfigRecord(
                    sys_id=sys_id,
                    table=spec.name,
                    scope_sys_id=scope_sys_id,
                    scope_name=str(row.get("sys_scope", scope_sys_id)),
                    captured_at=now,
                    fields=row,  # type: ignore[arg-type]
                    parent_sys_id=None,
                )
            )
        log.info(
            "captured %d records from %s (scope=%s)", len(records), spec.name, scope_sys_id
        )
        return records

    async def _fetch_related(
        self,
        related: RelatedTable,
        parent_sys_id: str,
        scope_sys_id: str,
        instance_id: str,
        now: datetime,
    ) -> list[ConfigRecord]:
        query = f"sys_customer_update=true^{related.join_field}={parent_sys_id}"
        raw = await self._fetch_all_pages(related.name, query)
        return [
            ConfigRecord(
                sys_id=str(row.get("sys_id", "")),
                table=related.name,
                scope_sys_id=scope_sys_id,
                scope_name=str(row.get("sys_scope", scope_sys_id)),
                captured_at=now,
                fields=row,  # type: ignore[arg-type]
                parent_sys_id=parent_sys_id,
            )
            for row in raw
        ]

    async def _fetch_all_pages(self, table: str, query: str) -> list[dict]:
        try:
            total = await self._client.count_records(table, query=query)
        except SNClientError as exc:
            if exc.status_code in (400, 404):
                log.warning("table %s unavailable (HTTP %s) -- skipping", table, exc.status_code)
                return []
            raise

        all_rows: list[dict] = []
        offset = 0
        while offset < total:
            try:
                page = await self._client.list_records(
                    table,
                    query=query,
                    limit=self._page_size,
                    offset=offset,
                    display_value="all",
                )
            except SNClientError as exc:
                if exc.status_code in (400, 404):
                    log.warning("table %s unavailable (HTTP %s) -- skipping", table, exc.status_code)
                    return all_rows
                raise
            all_rows.extend(page)
            offset += self._page_size

        return all_rows
```

Note: The `# type: ignore[arg-type]` on `fields=row` is temporary. The fake returns `dict[str, Any]` but `ConfigRecord.fields` expects `SnRecord`. In production, the `display_value=all` response from the real client returns the correct shape. Remove the ignore once the client's return type is tightened.

- [ ] **Step 6.4: Run tests**

```bash
pytest tests/capture/test_config_fetcher.py -v
```
Expected: 4 tests PASS

- [ ] **Step 6.5: Commit**

```bash
git add src/nexus/capture/fetcher.py tests/capture/test_config_fetcher.py
git commit -m "feat(capture): ConfigFetcher with pagination, related tables, custom-only filter"
```

---

## Task 7: ArchiveWriter + ArchiveReader

**Files:**
- Create: `src/nexus/capture/archive.py`
- Create: `tests/capture/test_archive.py`

- [ ] **Step 7.1: Write failing tests**

Create `tests/capture/test_archive.py`:

```python
# tests/capture/test_archive.py
# Tests for ArchiveWriter and ArchiveReader.
# Author: Pierre Grothe
# Date: 2026-05-09

from datetime import UTC, datetime
from pathlib import Path

import pytest

from nexus.capture.archive import ArchiveReader, ArchiveWriter
from nexus.capture.errors import ArchiveCorruptError
from nexus.capture.models import CaptureResult, ConfigRecord, SnRefField

_NOW = datetime(2026, 5, 9, 14, 0, 0, tzinfo=UTC)


def _make_result(tmp_path: Path) -> CaptureResult:
    ref: SnRefField = {"value": "global", "display_value": "Global"}
    r1 = ConfigRecord(
        sys_id="abc123",
        table="ai_skill",
        scope_sys_id="scope001",
        scope_name="x_app",
        captured_at=_NOW,
        fields={"name": "My Skill", "sys_scope": ref},
        parent_sys_id=None,
    )
    r2 = ConfigRecord(
        sys_id="def456",
        table="sys_hub_flow",
        scope_sys_id="scope001",
        scope_name="x_app",
        captured_at=_NOW,
        fields={"name": "My Flow"},
        parent_sys_id=None,
    )
    r3 = ConfigRecord(
        sys_id="ghi789",
        table="sys_hub_flow_logic",
        scope_sys_id="scope001",
        scope_name="x_app",
        captured_at=_NOW,
        fields={"name": "Step 1"},
        parent_sys_id="def456",
    )
    return CaptureResult(
        instance_id="dev-instance",
        captured_at=_NOW,
        scope_ids=("scope001",),
        table_group="ai_automation",
        records=(r1, r2, r3),
    )


def test_archive_writer_creates_manifest_yaml(tmp_path: Path) -> None:
    result = _make_result(tmp_path)
    writer = ArchiveWriter(archive_root=tmp_path)
    manifest = writer.write(result)

    assert manifest.record_count == 3
    assert manifest.instance_id == "dev-instance"
    assert (manifest.archive_dir / "manifest.yaml").exists()


def test_archive_writer_creates_per_record_yaml(tmp_path: Path) -> None:
    result = _make_result(tmp_path)
    writer = ArchiveWriter(archive_root=tmp_path)
    manifest = writer.write(result)

    archive = manifest.archive_dir
    assert (archive / "ai_skill" / "abc123.yaml").exists()
    assert (archive / "sys_hub_flow" / "def456.yaml").exists()


def test_archive_writer_nests_related_records_under_parent(tmp_path: Path) -> None:
    result = _make_result(tmp_path)
    writer = ArchiveWriter(archive_root=tmp_path)
    manifest = writer.write(result)

    # Related record nested under parent sys_id directory
    nested = manifest.archive_dir / "sys_hub_flow" / "def456" / "sys_hub_flow_logic" / "ghi789.yaml"
    assert nested.exists()


def test_archive_reader_roundtrip_preserves_all_fields(tmp_path: Path) -> None:
    result = _make_result(tmp_path)
    writer = ArchiveWriter(archive_root=tmp_path)
    manifest = writer.write(result)

    reader = ArchiveReader()
    loaded = reader.read(manifest.archive_dir / "manifest.yaml")

    assert loaded.instance_id == result.instance_id
    assert len(loaded.records) == len(result.records)
    skill = next(r for r in loaded.records if r.table == "ai_skill")
    assert skill.sys_id == "abc123"
    assert skill.fields["name"] == "My Skill"
    assert skill.fields["sys_scope"] == {"value": "global", "display_value": "Global"}


def test_archive_reader_corrupt_manifest_raises(tmp_path: Path) -> None:
    bad_dir = tmp_path / "bad_archive"
    bad_dir.mkdir()
    with pytest.raises(ArchiveCorruptError):
        ArchiveReader().read(bad_dir / "manifest.yaml")
```

- [ ] **Step 7.2: Run to verify failure**

```bash
pytest tests/capture/test_archive.py -v
```
Expected: `ModuleNotFoundError: No module named 'nexus.capture.archive'`

- [ ] **Step 7.3: Implement archive.py**

```python
# src/nexus/capture/archive.py
# YAML archive writer and reader for captured ServiceNow configurations.
# Author: Pierre Grothe
# Date: 2026-05-09

"""ArchiveWriter and ArchiveReader for persisting CaptureResult to YAML."""

import logging
from datetime import UTC, datetime
from pathlib import Path

import yaml

from nexus.capture.errors import ArchiveCorruptError
from nexus.capture.models import ArchiveManifest, CaptureResult, ConfigRecord

log = logging.getLogger(__name__)

__all__ = ["ArchiveWriter", "ArchiveReader"]

_FORMAT_VERSION = "1.0"


class ArchiveWriter:
    """Serializes a CaptureResult to a YAML directory structure.

    Args:
        archive_root: Root directory under which per-instance archives are written.
    """

    def __init__(self, archive_root: Path) -> None:
        """Initialize with the root directory for all archives."""
        self._root = archive_root

    def write(self, result: CaptureResult, dest: Path | None = None) -> ArchiveManifest:
        """Write a CaptureResult to disk as YAML files.

        Args:
            result: The capture result to persist.
            dest: Optional override for the archive directory.

        Returns:
            ArchiveManifest with location and record count.
        """
        if dest is None:
            timestamp = result.captured_at.strftime("%Y%m%d-%H%M%S")
            dest = self._root / result.instance_id / timestamp
        dest.mkdir(parents=True, exist_ok=True)

        for record in result.records:
            self._write_record(record, dest)

        manifest = ArchiveManifest(
            format_version=_FORMAT_VERSION,
            instance_id=result.instance_id,
            captured_at=result.captured_at,
            scope_ids=result.scope_ids,
            table_group=result.table_group,
            record_count=len(result.records),
            archive_dir=dest,
        )
        manifest_path = dest / "manifest.yaml"
        manifest_path.write_text(
            yaml.safe_dump(manifest.model_dump(mode="json"), sort_keys=False),
            encoding="utf-8",
        )
        log.info("archive written: %s (%d records)", dest, manifest.record_count)
        return manifest

    def _write_record(self, record: ConfigRecord, archive_dir: Path) -> None:
        if record.parent_sys_id is None:
            record_dir = archive_dir / record.table
        else:
            record_dir = archive_dir / record.table.rsplit("_", 1)[0] \
                         / record.parent_sys_id / record.table
            # Derive parent table from related table naming is fragile; use the
            # ConfigRecord's own table path so nesting is explicit.
            record_dir = archive_dir
            for r in _find_parent_path(record, archive_dir):
                record_dir = r
            record_dir = record_dir / record.table
        record_dir.mkdir(parents=True, exist_ok=True)
        record_path = record_dir / f"{record.sys_id}.yaml"
        record_path.write_text(
            yaml.safe_dump(record.model_dump(mode="json"), sort_keys=False),
            encoding="utf-8",
        )
```

The parent path derivation above is getting complex. Use a simpler, explicit approach:

```python
# src/nexus/capture/archive.py
# YAML archive writer and reader for captured ServiceNow configurations.
# Author: Pierre Grothe
# Date: 2026-05-09

"""ArchiveWriter and ArchiveReader for persisting CaptureResult to YAML."""

import logging
from pathlib import Path

import yaml

from nexus.capture.errors import ArchiveCorruptError
from nexus.capture.models import ArchiveManifest, CaptureResult, ConfigRecord

log = logging.getLogger(__name__)

__all__ = ["ArchiveWriter", "ArchiveReader"]

_FORMAT_VERSION = "1.0"


class ArchiveWriter:
    """Serializes a CaptureResult to a YAML directory structure.

    Args:
        archive_root: Root directory under which per-instance archives are written.
    """

    def __init__(self, archive_root: Path) -> None:
        """Initialize with the root directory for all archives."""
        self._root = archive_root

    def write(self, result: CaptureResult, dest: Path | None = None) -> ArchiveManifest:
        """Write a CaptureResult to disk as YAML files.

        Args:
            result: The capture result to persist.
            dest: Optional override for the archive directory.

        Returns:
            ArchiveManifest with location and record count.
        """
        if dest is None:
            timestamp = result.captured_at.strftime("%Y%m%d-%H%M%S")
            dest = self._root / result.instance_id / timestamp
        dest.mkdir(parents=True, exist_ok=True)

        # Build a lookup of sys_id -> (table, directory) for parent resolution
        root_dirs: dict[str, tuple[str, Path]] = {}
        root_records = [r for r in result.records if r.parent_sys_id is None]
        child_records = [r for r in result.records if r.parent_sys_id is not None]

        for record in root_records:
            record_dir = dest / record.table
            record_dir.mkdir(parents=True, exist_ok=True)
            _write_yaml(record, record_dir / f"{record.sys_id}.yaml")
            root_dirs[record.sys_id] = (record.table, record_dir)

        for record in child_records:
            if record.parent_sys_id and record.parent_sys_id in root_dirs:
                parent_table, parent_dir = root_dirs[record.parent_sys_id]
                child_dir = parent_dir / record.parent_sys_id / record.table
            else:
                child_dir = dest / record.table
            child_dir.mkdir(parents=True, exist_ok=True)
            _write_yaml(record, child_dir / f"{record.sys_id}.yaml")

        manifest = ArchiveManifest(
            format_version=_FORMAT_VERSION,
            instance_id=result.instance_id,
            captured_at=result.captured_at,
            scope_ids=result.scope_ids,
            table_group=result.table_group,
            record_count=len(result.records),
            archive_dir=dest,
        )
        (dest / "manifest.yaml").write_text(
            yaml.safe_dump(manifest.model_dump(mode="json"), sort_keys=False),
            encoding="utf-8",
        )
        log.info("archive written: %s (%d records)", dest, manifest.record_count)
        return manifest


class ArchiveReader:
    """Deserializes a YAML archive back into a CaptureResult."""

    def read(self, manifest_path: Path) -> CaptureResult:
        """Read an archive from disk.

        Args:
            manifest_path: Path to manifest.yaml inside an archive directory.

        Returns:
            CaptureResult reconstructed from YAML.

        Raises:
            ArchiveCorruptError: If the manifest is missing or YAML is invalid.
        """
        if not manifest_path.exists():
            raise ArchiveCorruptError(archive_dir=manifest_path.parent)
        try:
            raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
            manifest = ArchiveManifest.model_validate(raw)
        except Exception as exc:
            raise ArchiveCorruptError(archive_dir=manifest_path.parent) from exc

        archive_dir = manifest_path.parent
        records: list[ConfigRecord] = []
        for yaml_path in sorted(archive_dir.rglob("*.yaml")):
            if yaml_path.name == "manifest.yaml":
                continue
            try:
                data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
                records.append(ConfigRecord.model_validate(data))
            except Exception as exc:
                log.warning("skipping corrupt record %s: %s", yaml_path, exc)

        return CaptureResult(
            instance_id=manifest.instance_id,
            captured_at=manifest.captured_at,
            scope_ids=manifest.scope_ids,
            table_group=manifest.table_group,
            records=tuple(records),
        )


def _write_yaml(record: ConfigRecord, path: Path) -> None:
    path.write_text(
        yaml.safe_dump(record.model_dump(mode="json"), sort_keys=False),
        encoding="utf-8",
    )
```

- [ ] **Step 7.4: Run tests**

```bash
pytest tests/capture/test_archive.py -v
```
Expected: 5 tests PASS

- [ ] **Step 7.5: Commit**

```bash
git add src/nexus/capture/archive.py tests/capture/test_archive.py
git commit -m "feat(capture): ArchiveWriter and ArchiveReader with nested related record layout"
```

---

## Task 8: UpdateSetXmlBuilder

**Files:**
- Create: `src/nexus/capture/xml_builder.py`
- Create: `tests/capture/test_xml_builder.py`

- [ ] **Step 8.1: Write failing tests**

Create `tests/capture/test_xml_builder.py`:

```python
# tests/capture/test_xml_builder.py
# Tests for UpdateSetXmlBuilder.
# Author: Pierre Grothe
# Date: 2026-05-09

import xml.etree.ElementTree as ET
from datetime import UTC, datetime

from nexus.capture.models import ConfigRecord, SnRefField
from nexus.capture.xml_builder import UpdateSetXmlBuilder

_NOW = datetime(2026, 5, 9, tzinfo=UTC)


def _record(fields: dict) -> ConfigRecord:
    return ConfigRecord(
        sys_id="abc123",
        table="ai_skill",
        scope_sys_id="scope001",
        scope_name="x_app",
        captured_at=_NOW,
        fields=fields,
        parent_sys_id=None,
    )


def test_xml_builder_output_parses_as_valid_xml() -> None:
    builder = UpdateSetXmlBuilder()
    xml_str = builder.build(_record({"name": "My Skill"}))
    root = ET.fromstring(xml_str)  # raises if invalid
    assert root is not None


def test_xml_builder_outer_element_has_correct_table_and_sys_id() -> None:
    builder = UpdateSetXmlBuilder()
    xml_str = builder.build(_record({"name": "My Skill"}))
    root = ET.fromstring(xml_str)
    assert root.tag == "record_update"
    assert root.attrib["table"] == "ai_skill"
    assert root.attrib["sys_id"] == "abc123"


def test_xml_builder_inner_element_named_after_table_with_action() -> None:
    builder = UpdateSetXmlBuilder()
    xml_str = builder.build(_record({"name": "My Skill"}))
    root = ET.fromstring(xml_str)
    inner = root.find("ai_skill")
    assert inner is not None
    assert inner.attrib["action"] == "INSERT_OR_UPDATE"


def test_xml_builder_plain_string_field_produces_text_element() -> None:
    builder = UpdateSetXmlBuilder()
    xml_str = builder.build(_record({"name": "My Skill"}))
    root = ET.fromstring(xml_str)
    name_el = root.find("ai_skill/name")
    assert name_el is not None
    assert name_el.text == "My Skill"


def test_xml_builder_ref_field_includes_display_value_attribute() -> None:
    ref: SnRefField = {"value": "global", "display_value": "Global"}
    builder = UpdateSetXmlBuilder()
    xml_str = builder.build(_record({"sys_scope": ref}))
    root = ET.fromstring(xml_str)
    scope_el = root.find("ai_skill/sys_scope")
    assert scope_el is not None
    assert scope_el.text == "global"
    assert scope_el.attrib["display_value"] == "Global"
```

- [ ] **Step 8.2: Run to verify failure**

```bash
pytest tests/capture/test_xml_builder.py -v
```
Expected: `ModuleNotFoundError: No module named 'nexus.capture.xml_builder'`

- [ ] **Step 8.3: Implement xml_builder.py**

```python
# src/nexus/capture/xml_builder.py
# Converts captured ConfigRecords to ServiceNow update set XML payloads.
# Author: Pierre Grothe
# Date: 2026-05-09

"""UpdateSetXmlBuilder: generates SN sys_update_xml payload per ConfigRecord."""

import xml.etree.ElementTree as ET
from typing import cast

from nexus.capture.models import ConfigRecord, SnRefField

__all__ = ["UpdateSetXmlBuilder"]


class UpdateSetXmlBuilder:
    """Converts a ConfigRecord to a ServiceNow update set XML payload string.

    The output format matches what ServiceNow's sys_update_xml table expects
    in its payload field:

        <record_update table="{table}" sys_id="{sys_id}">
          <{table} action="INSERT_OR_UPDATE">
            <field_name>value</field_name>
            <ref_field display_value="Label">sys_id</ref_field>
          </{table}>
        </record_update>
    """

    def build(self, record: ConfigRecord) -> str:
        """Generate the XML payload for one ConfigRecord.

        Args:
            record: The captured record to serialize.

        Returns:
            XML string suitable for the sys_update_xml.payload field.
        """
        outer = ET.Element(
            "record_update",
            attrib={"table": record.table, "sys_id": record.sys_id},
        )
        inner = ET.SubElement(
            outer,
            record.table,
            attrib={"action": "INSERT_OR_UPDATE"},
        )
        for field_name, field_value in record.fields.items():
            el = ET.SubElement(inner, field_name)
            if isinstance(field_value, dict):
                ref = cast(SnRefField, field_value)
                el.text = ref["value"]
                el.set("display_value", ref["display_value"])
            else:
                el.text = str(field_value) if field_value is not None else ""

        return ET.tostring(outer, encoding="unicode", xml_declaration=False)
```

- [ ] **Step 8.4: Run tests**

```bash
pytest tests/capture/test_xml_builder.py -v
```
Expected: 5 tests PASS

- [ ] **Step 8.5: Commit**

```bash
git add src/nexus/capture/xml_builder.py tests/capture/test_xml_builder.py
git commit -m "feat(capture): UpdateSetXmlBuilder generates SN update set XML payloads"
```

---

## Task 9: UpdateSetWriter

**Files:**
- Create: `src/nexus/capture/update_set.py`
- Create: `tests/capture/test_update_set_writer.py`

- [ ] **Step 9.1: Write failing tests**

Create `tests/capture/test_update_set_writer.py`:

```python
# tests/capture/test_update_set_writer.py
# Tests for UpdateSetWriter.
# Author: Pierre Grothe
# Date: 2026-05-09

import pytest
from datetime import UTC, datetime

from tests.fakes.fake_sn_client import FakeServiceNowClient
from nexus.capture.update_set import UpdateSetWriter
from nexus.capture.xml_builder import UpdateSetXmlBuilder
from nexus.capture.errors import UpdateSetError
from nexus.capture.models import CaptureResult, ConfigRecord

_NOW = datetime(2026, 5, 9, tzinfo=UTC)


def _result(records: list[ConfigRecord]) -> CaptureResult:
    return CaptureResult(
        instance_id="dev",
        captured_at=_NOW,
        scope_ids=("scope001",),
        table_group="ai_automation",
        records=tuple(records),
    )


def _record(sys_id: str) -> ConfigRecord:
    return ConfigRecord(
        sys_id=sys_id, table="ai_skill", scope_sys_id="scope001",
        scope_name="x_app", captured_at=_NOW, fields={"name": f"Skill {sys_id}"},
        parent_sys_id=None,
    )


@pytest.mark.asyncio
async def test_update_set_writer_creates_set_when_not_found() -> None:
    client = FakeServiceNowClient()
    writer = UpdateSetWriter(client, UpdateSetXmlBuilder())
    async with client:
        ref = await writer.push(
            _result([_record("r1")]), "dev", "NEXUS-test"
        )

    assert ref.name == "NEXUS-test"
    assert ref.record_count == 1
    assert len(client._tables.get("sys_update_xml", [])) == 1


@pytest.mark.asyncio
async def test_update_set_writer_reuses_existing_in_progress_set() -> None:
    existing_set = {"sys_id": "existing001", "name": "NEXUS-test", "state": "in progress"}
    client = FakeServiceNowClient(initial_records={"sys_update_set": [existing_set]})
    writer = UpdateSetWriter(client, UpdateSetXmlBuilder())
    async with client:
        ref = await writer.push(
            _result([_record("r1")]), "dev", "NEXUS-test"
        )

    assert ref.sys_id == "existing001"
    assert len(client._tables.get("sys_update_set", [])) == 1  # no new set created


@pytest.mark.asyncio
async def test_update_set_writer_sets_correct_record_count() -> None:
    client = FakeServiceNowClient()
    writer = UpdateSetWriter(client, UpdateSetXmlBuilder())
    async with client:
        ref = await writer.push(
            _result([_record("r1"), _record("r2"), _record("r3")]),
            "dev", "NEXUS-test",
        )

    assert ref.record_count == 3
```

- [ ] **Step 9.2: Run to verify failure**

```bash
pytest tests/capture/test_update_set_writer.py -v
```
Expected: `ModuleNotFoundError: No module named 'nexus.capture.update_set'`

- [ ] **Step 9.3: Implement update_set.py**

```python
# src/nexus/capture/update_set.py
# Injects captured configs into a ServiceNow update set via the Table API.
# Author: Pierre Grothe
# Date: 2026-05-09

"""UpdateSetWriter: creates or reuses a sys_update_set and injects records."""

import logging

from nexus.capture.errors import UpdateSetError
from nexus.capture.models import CaptureResult, UpdateSetRef
from nexus.capture.xml_builder import UpdateSetXmlBuilder
from nexus.connectors.servicenow.client import ServiceNowClient
from nexus.connectors.servicenow.errors import SNClientError

log = logging.getLogger(__name__)

__all__ = ["UpdateSetWriter"]


class UpdateSetWriter:
    """Pushes a CaptureResult into a ServiceNow update set.

    Args:
        client: Open ServiceNowClient for the target instance.
        builder: XML builder for generating update set payloads.
    """

    def __init__(
        self,
        client: ServiceNowClient,
        builder: UpdateSetXmlBuilder,
    ) -> None:
        """Initialize with an open client and XML builder."""
        self._client = client
        self._builder = builder

    async def push(
        self,
        result: CaptureResult,
        instance_id: str,
        update_set_name: str,
    ) -> UpdateSetRef:
        """Inject all records into a new or existing in-progress update set.

        Args:
            result: CaptureResult to deploy.
            instance_id: Target instance profile name.
            update_set_name: Name for the update set.

        Returns:
            UpdateSetRef for the created or reused update set.

        Raises:
            UpdateSetError: If any record injection fails.
        """
        update_set_sys_id = await self._get_or_create_update_set(update_set_name)
        count = 0
        for record in result.records:
            payload = self._builder.build(record)
            try:
                await self._client.create_record(
                    "sys_update_xml",
                    data={
                        "update_set": update_set_sys_id,
                        "name": f"{record.table}_{record.sys_id}",
                        "type": record.table,
                        "payload": payload,
                        "action": "INSERT_OR_UPDATE",
                    },
                )
                count += 1
            except SNClientError as exc:
                raise UpdateSetError(
                    update_set_name=update_set_name,
                    instance_id=instance_id,
                    failed_record_sys_id=record.sys_id,
                    failed_table=record.table,
                ) from exc

        log.info(
            "injected %d records into update set %r on %s",
            count, update_set_name, instance_id,
        )
        return UpdateSetRef(
            sys_id=update_set_sys_id,
            name=update_set_name,
            state="in progress",
            record_count=count,
            instance_id=instance_id,
        )

    async def _get_or_create_update_set(self, name: str) -> str:
        existing = await self._client.query_table(
            "sys_update_set",
            query=f"name={name}^state=in progress",
            limit=1,
        )
        if existing:
            sys_id = str(existing[0].get("sys_id", ""))
            log.info("reusing existing update set %r (%s)", name, sys_id)
            return sys_id

        created = await self._client.create_record(
            "sys_update_set",
            data={"name": name, "state": "in progress"},
        )
        sys_id = str(created.get("sys_id", ""))
        log.info("created update set %r (%s)", name, sys_id)
        return sys_id
```

- [ ] **Step 9.4: Run tests**

```bash
pytest tests/capture/test_update_set_writer.py -v
```
Expected: 3 tests PASS

- [ ] **Step 9.5: Commit**

```bash
git add src/nexus/capture/update_set.py tests/capture/test_update_set_writer.py
git commit -m "feat(capture): UpdateSetWriter creates/reuses update set and injects records"
```

---

## Task 10: CaptureEngine + __init__

**Files:**
- Create: `src/nexus/capture/engine.py`
- Modify: `src/nexus/capture/__init__.py`
- Create: `tests/capture/test_capture_engine.py`

- [ ] **Step 10.1: Write failing integration test**

Create `tests/capture/test_capture_engine.py`:

```python
# tests/capture/test_capture_engine.py
# Integration tests for CaptureEngine using all fakes.
# Author: Pierre Grothe
# Date: 2026-05-09

import pytest
from datetime import UTC, datetime
from pathlib import Path

from tests.fakes.fake_sn_client import FakeServiceNowClient
from nexus.capture.engine import CaptureEngine
from nexus.capture.tables import DEFAULT_TABLE_GROUPS

_SCOPE_ROW = {
    "sys_id": "scope001",
    "name": "NowAssist HRSD",
    "scope": "x_snc_nowassist_hrsd",
    "version": "1.0.0",
    "vendor": "SN",
}

_SKILL = {
    "sys_id": "skill001",
    "name": "My Skill",
    "sys_scope": "scope001",
    "sys_customer_update": "true",
}


@pytest.mark.asyncio
async def test_capture_engine_discover_returns_scope_manifest() -> None:
    client = FakeServiceNowClient(
        initial_records={"sys_scope": [_SCOPE_ROW], "ai_skill": [_SKILL]}
    )
    engine = CaptureEngine(client=client, archive_root=Path("/tmp/nexus-test"))
    async with client:
        manifest = await engine.discover_scopes("dev", "ai_automation")

    assert len(manifest.scopes) == 1
    assert manifest.scopes[0].scope == "x_snc_nowassist_hrsd"


@pytest.mark.asyncio
async def test_capture_engine_capture_returns_result(tmp_path: Path) -> None:
    client = FakeServiceNowClient(
        initial_records={"sys_scope": [_SCOPE_ROW], "ai_skill": [_SKILL]}
    )
    engine = CaptureEngine(client=client, archive_root=tmp_path)
    async with client:
        result = await engine.capture("dev", ["scope001"], "ai_automation")

    skill_records = [r for r in result.records if r.table == "ai_skill"]
    assert len(skill_records) == 1
    assert skill_records[0].sys_id == "skill001"


def test_capture_engine_save_and_load_roundtrip(tmp_path: Path) -> None:
    from datetime import UTC, datetime
    from nexus.capture.models import CaptureResult, ConfigRecord

    now = datetime.now(UTC)
    record = ConfigRecord(
        sys_id="r1", table="ai_skill", scope_sys_id="s1",
        scope_name="x_app", captured_at=now, fields={"name": "Skill"},
        parent_sys_id=None,
    )
    result = CaptureResult(
        instance_id="dev", captured_at=now, scope_ids=("s1",),
        table_group="ai_automation", records=(record,),
    )
    client = FakeServiceNowClient()
    engine = CaptureEngine(client=client, archive_root=tmp_path)

    manifest = engine.save_archive(result)
    loaded = engine.load_archive(manifest.archive_dir / "manifest.yaml")

    assert len(loaded.records) == 1
    assert loaded.records[0].sys_id == "r1"
```

- [ ] **Step 10.2: Run to verify failure**

```bash
pytest tests/capture/test_capture_engine.py -v
```
Expected: `ModuleNotFoundError: No module named 'nexus.capture.engine'`

- [ ] **Step 10.3: Implement engine.py**

```python
# src/nexus/capture/engine.py
# CaptureEngine: orchestrates all capture layer components.
# Author: Pierre Grothe
# Date: 2026-05-09

"""CaptureEngine: concrete implementation of CaptureProtocol."""

import logging
from pathlib import Path

from nexus.capture.archive import ArchiveReader, ArchiveWriter
from nexus.capture.fetcher import ConfigFetcher
from nexus.capture.models import (
    ArchiveManifest,
    CaptureResult,
    ScopeManifest,
    UpdateSetRef,
)
from nexus.capture.scope import ScopeDiscoverer
from nexus.capture.tables import DEFAULT_TABLE_GROUPS, TableGroup
from nexus.capture.update_set import UpdateSetWriter
from nexus.capture.xml_builder import UpdateSetXmlBuilder
from nexus.connectors.servicenow.client import ServiceNowClient

log = logging.getLogger(__name__)

__all__ = ["CaptureEngine"]


class CaptureEngine:
    """Bidirectional ServiceNow configuration transport.

    Implements CaptureProtocol. Wires ScopeDiscoverer, ConfigFetcher,
    ArchiveWriter/Reader, and UpdateSetWriter. Callers inject a
    ServiceNowClient; the engine never constructs one itself.

    Args:
        client: Open ServiceNowClient for the source/target instance.
        archive_root: Root directory for local YAML archives.
        table_groups: Table group registry (defaults to DEFAULT_TABLE_GROUPS).
    """

    def __init__(
        self,
        client: ServiceNowClient,
        archive_root: Path,
        table_groups: dict[str, TableGroup] | None = None,
    ) -> None:
        """Initialize all internal components with the provided dependencies."""
        groups = table_groups or DEFAULT_TABLE_GROUPS
        self._discoverer = ScopeDiscoverer(client, groups)
        self._fetcher = ConfigFetcher(client, groups)
        self._writer = ArchiveWriter(archive_root)
        self._reader = ArchiveReader()
        self._usw = UpdateSetWriter(client, UpdateSetXmlBuilder())

    async def discover_scopes(
        self,
        instance_id: str,
        table_group: str = "ai_automation",
    ) -> ScopeManifest:
        """Discover all application scopes on the instance with per-table counts.

        Args:
            instance_id: Registered instance profile name.
            table_group: Which table group to count records for.

        Returns:
            ScopeManifest listing all scopes and per-table record counts.
        """
        return await self._discoverer.discover(instance_id, table_group)

    async def capture(
        self,
        instance_id: str,
        scope_ids: list[str],
        table_group: str = "ai_automation",
    ) -> CaptureResult:
        """Fetch all custom configurations in the given scopes.

        Args:
            instance_id: Registered instance profile name.
            scope_ids: Application scope sys_ids to capture.
            table_group: Which table group to scan.

        Returns:
            CaptureResult with all matching records.
        """
        records = await self._fetcher.fetch(instance_id, scope_ids, table_group)
        from datetime import UTC, datetime

        return CaptureResult(
            instance_id=instance_id,
            captured_at=datetime.now(UTC),
            scope_ids=tuple(scope_ids),
            table_group=table_group,
            records=tuple(records),
        )

    def save_archive(
        self,
        result: CaptureResult,
        dest: Path | None = None,
    ) -> ArchiveManifest:
        """Serialize a CaptureResult to YAML on disk.

        Args:
            result: The capture result to persist.
            dest: Override for the archive directory.

        Returns:
            ArchiveManifest with location and record count.
        """
        return self._writer.write(result, dest)

    def load_archive(self, manifest_path: Path) -> CaptureResult:
        """Deserialize a previously saved archive into a CaptureResult.

        Args:
            manifest_path: Path to manifest.yaml inside an archive directory.

        Returns:
            CaptureResult reconstructed from YAML.

        Raises:
            ArchiveCorruptError: If the manifest is missing or YAML is invalid.
        """
        return self._reader.read(manifest_path)

    async def push_to_update_set(
        self,
        result: CaptureResult,
        instance_id: str,
        update_set_name: str,
    ) -> UpdateSetRef:
        """Inject all records from a CaptureResult into an update set.

        Args:
            result: CaptureResult to deploy.
            instance_id: Target instance profile name.
            update_set_name: Name for the update set.

        Returns:
            UpdateSetRef for the created or reused update set.

        Raises:
            UpdateSetError: If any record injection fails.
        """
        return await self._usw.push(result, instance_id, update_set_name)
```

- [ ] **Step 10.4: Update __init__.py**

```python
# src/nexus/capture/__init__.py
# NEXUS capture layer -- bidirectional SN config transport.
# Author: Pierre Grothe
# Date: 2026-05-09

"""Bidirectional ServiceNow configuration transport.

Public API: CaptureEngine (concrete) and CaptureProtocol (interface).
All other symbols are implementation details.
"""

from nexus.capture.engine import CaptureEngine
from nexus.capture.errors import (
    ArchiveCorruptError,
    CaptureError,
    ScopeNotFoundError,
    TableUnavailableError,
    UpdateSetError,
)
from nexus.capture.models import (
    ArchiveManifest,
    CaptureResult,
    ConfigRecord,
    ScopeEntry,
    ScopeManifest,
    UpdateSetRef,
)
from nexus.capture.protocol import CaptureProtocol

__all__ = [
    "CaptureEngine",
    "CaptureProtocol",
    "CaptureError",
    "ScopeNotFoundError",
    "TableUnavailableError",
    "ArchiveCorruptError",
    "UpdateSetError",
    "ScopeEntry",
    "ScopeManifest",
    "ConfigRecord",
    "CaptureResult",
    "ArchiveManifest",
    "UpdateSetRef",
]
```

- [ ] **Step 10.5: Run tests**

```bash
pytest tests/capture/ -v
```
Expected: all capture tests PASS

- [ ] **Step 10.6: Run full suite**

```bash
pytest -x -q
```
Expected: all tests PASS

- [ ] **Step 10.7: Commit**

```bash
git add src/nexus/capture/engine.py src/nexus/capture/__init__.py \
        tests/capture/test_capture_engine.py
git commit -m "feat(capture): CaptureEngine orchestrates full bidirectional pipeline"
```

---

## Task 11: FakeCaptureEngine

**Files:**
- Create: `tests/capture/fakes/__init__.py`
- Create: `tests/capture/fakes/fake_capture_engine.py`

- [ ] **Step 11.1: Create FakeCaptureEngine**

Create `tests/capture/fakes/__init__.py` (empty).

Create `tests/capture/fakes/fake_capture_engine.py`:

```python
# tests/capture/fakes/fake_capture_engine.py
# In-memory fake for CaptureProtocol used in CLI and TUI tests.
# Author: Pierre Grothe
# Date: 2026-05-09

"""FakeCaptureEngine: canned responses for CaptureProtocol consumers."""

from datetime import UTC, datetime
from pathlib import Path

from nexus.capture.models import (
    ArchiveManifest,
    CaptureResult,
    ConfigRecord,
    ScopeEntry,
    ScopeManifest,
    UpdateSetRef,
)

__all__ = ["FakeCaptureEngine"]

_NOW = datetime(2026, 5, 9, 14, 0, 0, tzinfo=UTC)


class FakeCaptureEngine:
    """In-memory substitute for CaptureEngine in CLI and TUI tests.

    Preload ``scope_manifest``, ``capture_result``, and ``update_set_ref``
    attributes to control what each method returns.
    """

    def __init__(self) -> None:
        """Initialize with default empty responses."""
        self.scope_manifest = ScopeManifest(
            instance_id="fake-instance",
            captured_at=_NOW,
            scopes=(),
        )
        self.capture_result = CaptureResult(
            instance_id="fake-instance",
            captured_at=_NOW,
            scope_ids=(),
            table_group="ai_automation",
            records=(),
        )
        self.archive_manifest = ArchiveManifest(
            format_version="1.0",
            instance_id="fake-instance",
            captured_at=_NOW,
            scope_ids=(),
            table_group="ai_automation",
            record_count=0,
            archive_dir=Path("/tmp/fake-archive"),
        )
        self.update_set_ref = UpdateSetRef(
            sys_id="fake-us-001",
            name="NEXUS-fake",
            state="in progress",
            record_count=0,
            instance_id="fake-instance",
        )

    async def discover_scopes(
        self, instance_id: str, table_group: str = "ai_automation"
    ) -> ScopeManifest:
        """Return the preset scope manifest."""
        return self.scope_manifest

    async def capture(
        self, instance_id: str, scope_ids: list[str], table_group: str = "ai_automation"
    ) -> CaptureResult:
        """Return the preset capture result."""
        return self.capture_result

    def save_archive(
        self, result: CaptureResult, dest: Path | None = None
    ) -> ArchiveManifest:
        """Return the preset archive manifest without writing to disk."""
        return self.archive_manifest

    def load_archive(self, manifest_path: Path) -> CaptureResult:
        """Return the preset capture result without reading from disk."""
        return self.capture_result

    async def push_to_update_set(
        self, result: CaptureResult, instance_id: str, update_set_name: str
    ) -> UpdateSetRef:
        """Return the preset update set ref without making SN calls."""
        return self.update_set_ref
```

- [ ] **Step 11.2: Commit**

```bash
git add tests/capture/fakes/__init__.py tests/capture/fakes/fake_capture_engine.py
git commit -m "test(capture): FakeCaptureEngine for CLI and TUI tests"
```

---

## Task 12: nexus capture CLI commands

**Files:**
- Modify: `src/nexus/cli.py`

- [ ] **Step 12.1: Add capture_app Typer group and discover subcommand**

In `src/nexus/cli.py`, after the `instance_app = typer.Typer(...)` line, add:

```python
from nexus.capture import CaptureEngine
from nexus.capture.tables import DEFAULT_TABLE_GROUPS

capture_app = typer.Typer(name="capture", help="Capture and deploy ServiceNow configurations.")
app.add_typer(capture_app)
```

Then add a helper to build a `CaptureEngine` (reuses the existing `_instance_registry()` pattern):

```python
def _capture_engine(instance_id: str) -> tuple[CaptureEngine, ServiceNowClient]:
    """Build a CaptureEngine for the given registered instance.

    Args:
        instance_id: Profile name from InstanceRegistry.

    Returns:
        Tuple of (CaptureEngine, open ServiceNowClient).

    Note:
        Caller is responsible for entering the client as an async context manager.
    """
    registry = _instance_registry()
    meta = registry.get(instance_id)
    if meta is None:
        err_console.print(f"Instance {instance_id!r} not registered.")
        err_console.print("  Register one: nexus instance register <profile>")
        raise typer.Exit(1)
    client = ServiceNowClient(
        instance_url=meta.instance_url,
        username=meta.username,
        password=_get_password(meta),
    )
    paths = NexusPaths.from_env()
    engine = CaptureEngine(client=client, archive_root=paths.archives_dir)
    return engine, client
```

Note: `_get_password` needs to retrieve the stored OAuth or password credential.
Look at how `instance_connect` does it in the existing CLI and replicate the same pattern.
Specifically, use `SNAuth` or the instance registry's stored credential mechanism.

- [ ] **Step 12.2: Add the four capture subcommands**

Add after the `_capture_engine` helper:

```python
@capture_app.command("discover")
def capture_discover(
    instance: Annotated[str, typer.Argument(help="Instance profile name")],
    group: Annotated[str, typer.Option(help="Table group")] = "ai_automation",
) -> None:
    """Discover application scopes on an instance and show per-table counts."""

    async def _run() -> None:
        engine, client = _capture_engine(instance)
        async with client:
            manifest = await engine.discover_scopes(instance, group)

        if not manifest.scopes:
            console.print("No application scopes found.")
            return

        table = Table(title=f"Scopes on {instance}")
        table.add_column("Name")
        table.add_column("Scope Key")
        group_obj = DEFAULT_TABLE_GROUPS.get(group)
        if group_obj:
            for spec in group_obj.tables:
                table.add_column(spec.display, justify="right")
        for scope in manifest.scopes:
            row = [scope.name, scope.scope]
            if group_obj:
                for spec in group_obj.tables:
                    row.append(str(scope.table_counts.get(spec.name, 0)))
            table.add_row(*row)
        console.print(table)

    asyncio.run(_run())


@capture_app.command("pull")
def capture_pull(
    instance: Annotated[str, typer.Argument(help="Instance profile name")],
    scope: Annotated[list[str], typer.Option(help="Scope sys_id or name (repeatable)")],
    group: Annotated[str, typer.Option(help="Table group")] = "ai_automation",
) -> None:
    """Capture custom configurations for selected scopes to a local archive."""

    async def _run() -> None:
        engine, client = _capture_engine(instance)
        async with client:
            result = await engine.capture(instance, scope, group)
        manifest = engine.save_archive(result)
        console.print(f"Captured {manifest.record_count} records.")
        console.print(f"Archive: {manifest.archive_dir}")

    asyncio.run(_run())


@capture_app.command("list")
def capture_list(
    instance: Annotated[str | None, typer.Argument(help="Filter by instance")] = None,
) -> None:
    """List local capture archives."""
    paths = NexusPaths.from_env()
    archives_root = paths.archives_dir
    if not archives_root.exists():
        console.print("No archives found.")
        return

    table = Table(title="Local Archives")
    table.add_column("Instance")
    table.add_column("Timestamp")
    table.add_column("Records", justify="right")
    table.add_column("Path")

    import yaml
    for manifest_path in sorted(archives_root.rglob("manifest.yaml")):
        try:
            raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
            inst = raw.get("instance_id", "?")
            if instance and inst != instance:
                continue
            table.add_row(
                inst,
                raw.get("captured_at", "?")[:19],
                str(raw.get("record_count", 0)),
                str(manifest_path.parent),
            )
        except Exception:
            continue
    console.print(table)


@capture_app.command("push")
def capture_push(
    archive: Annotated[str, typer.Argument(help="Path to archive directory")],
    instance: Annotated[str, typer.Argument(help="Target instance profile")],
    update_set: Annotated[str, typer.Option(help="Update set name")] = "NEXUS-capture",
) -> None:
    """Push a local archive into an update set on the target instance."""

    async def _run() -> None:
        from pathlib import Path as _Path
        engine, client = _capture_engine(instance)
        manifest_path = _Path(archive) / "manifest.yaml"
        result = engine.load_archive(manifest_path)
        async with client:
            ref = await engine.push_to_update_set(result, instance, update_set)
        console.print(f"Injected {ref.record_count} records into update set {ref.name!r}.")
        console.print(f"Update set sys_id: {ref.sys_id}")

    asyncio.run(_run())
```

- [ ] **Step 12.3: Run full suite to check no regressions**

```bash
pytest -x -q
```
Expected: all tests PASS (CLI commands are not unit-tested here -- they are thin wrappers over the tested engine)

- [ ] **Step 12.4: Smoke test CLI help**

```bash
python -m nexus capture --help
python -m nexus capture discover --help
python -m nexus capture pull --help
python -m nexus capture list --help
python -m nexus capture push --help
```
Expected: all four subcommands appear with correct descriptions and arguments.

- [ ] **Step 12.5: Commit**

```bash
git add src/nexus/cli.py
git commit -m "feat(cli): nexus capture subcommands -- discover, pull, list, push"
```

---

## Task 13: Ratchet + primer update

**Files:**
- Modify: `.ratchet.json`
- Modify: `.primer/roadmap.md`
- Modify: `.primer/active.md`

- [ ] **Step 13.1: Run coverage to get capture module baselines**

```bash
pytest --cov=nexus.capture --cov-report=json -q
python -c "
import json, pathlib
cov = json.loads(pathlib.Path('coverage.json').read_text())
for mod, data in sorted(cov['files'].items()):
    if 'capture' in mod:
        covered = data['summary']['covered_lines']
        total = data['summary']['num_statements']
        print(f'  \"nexus.{mod.replace(\"/\",\".\").replace(\"src.\",\"\").replace(\".py\",\"\")}\": {{\"covered_lines\": {covered}, \"total_lines\": {total}}}')
"
```

- [ ] **Step 13.2: Add capture modules to .ratchet.json**

Open `.ratchet.json` and add entries for all capture modules under `"modules"`:

```json
"nexus.capture": {"covered_lines": <N>, "total_lines": <M>},
"nexus.capture.errors": {"covered_lines": <N>, "total_lines": <M>},
"nexus.capture.models": {"covered_lines": <N>, "total_lines": <M>},
"nexus.capture.tables": {"covered_lines": <N>, "total_lines": <M>},
"nexus.capture.protocol": {"covered_lines": <N>, "total_lines": <M>},
"nexus.capture.scope": {"covered_lines": <N>, "total_lines": <M>},
"nexus.capture.fetcher": {"covered_lines": <N>, "total_lines": <M>},
"nexus.capture.archive": {"covered_lines": <N>, "total_lines": <M>},
"nexus.capture.xml_builder": {"covered_lines": <N>, "total_lines": <M>},
"nexus.capture.update_set": {"covered_lines": <N>, "total_lines": <M>},
"nexus.capture.engine": {"covered_lines": <N>, "total_lines": <M>},
```

Replace `<N>` and `<M>` with the actual values from the coverage output above.

- [ ] **Step 13.3: Update .primer/roadmap.md**

Replace the roadmap content with:

```markdown
# Roadmap

## Foundation [done]
- [x] Config, auth, capabilities layers
- [x] ServiceNow REST connector + error hierarchy
- [x] ConnectorProtocol plugin system
- [x] Instance management (register, connect, refresh, list, delete, use + OAuth auto-provisioning)
- [x] CLI skeleton (all commands wired)
- [x] CI/CD: lint, tests, release, template validation
- [x] AgentClient backed by claude-agent-sdk
- [x] nexus status command
- [x] nexus.capture layer (ScopeDiscoverer, ConfigFetcher, ArchiveWriter/Reader,
      UpdateSetXmlBuilder, UpdateSetWriter, CaptureEngine)
- [x] nexus capture command (discover, pull, list, push)

## 2026.05 -- Setup + Sync [active]
- [ ] nexus setup command -- credential wizard, config write, initial sync
- [ ] GitHubSync -- manifest fetch + template download
- [ ] TemplateRegistry -- list and get from local cache

## 2026.06 -- Assessment [planned]
- [ ] RuleEngine + AssessmentReporter (consuming CaptureResult)
- [ ] nexus assess command
- [ ] Gate 1 readiness check + Gate 2 validation check

## 2026.06 -- Template Library [planned]
- [ ] NowAssistSkill + Workflow Pydantic schemas
- [ ] First 3+ community templates in templates/
- [ ] Template apply engine (ApplyEngine)

## 2026.07 -- Agent Specialists [planned]
- [ ] 8 domain specialist agents implemented
- [ ] ExecutionContext enrichment from enterprise MCP
- [ ] Multi-step orchestration via Planner + Dispatcher
- [ ] Rollback manager for failed deployments

## 2026.08 -- Distribution [planned]
- [ ] 100% line coverage, mypy strict, ruff 0 violations
- [ ] README + getting started documentation
- [ ] PyPI publish (nexus-sn)

## Backlog
- [ ] NiceGUI web interface (nexus[ui] optional extra)
- [ ] Knowledge mastery KB (206 ServiceNow product docs)
- [ ] MCPProbe real endpoint URLs
- [ ] JIRA, GitHub, Confluence connectors
- [ ] Extend capture to DEVELOPER_PLATFORM table group
      (business rules, script includes, ACLs, scheduled jobs)
```

- [ ] **Step 13.4: Update .primer/active.md**

Replace the "Current focus" and "Focus returns to MVP build order" sections:

```markdown
## Current focus

nexus.capture layer shipped. Bidirectional SN config transport:
- discover scopes, pull custom configs to YAML archive, push archive to update set.
- sys_customer_update=true filter excludes all OOTB elements from capture.
- AI_AUTOMATION table group: ai_skill, sys_hub_flow, sys_hub_action_type_definition,
  virtual_agent_conversation_topic, sys_ai_agent (with related tables).

Focus moves to Setup + Sync:
  Step 2: nexus setup command -- credential wizard, config write, initial sync
  Step 3: GitHubSync.fetch_manifest() + download_changed()
  Step 4: TemplateRegistry.list() + get()
```

- [ ] **Step 13.5: Run full suite one final time**

```bash
pytest -q
```
Expected: all tests PASS (count will be higher than 296 -- capture tests added)

- [ ] **Step 13.6: Commit**

```bash
git add .ratchet.json .primer/roadmap.md .primer/active.md
git commit -m "chore: update ratchet baselines and primer after capture layer"
```

---

## Self-Review

**Spec coverage check:**

| Spec section | Covered by task |
|---|---|
| Layer position (connectors -> capture -> assessment) | Task 10 engine imports |
| Module layout (11 files) | Tasks 1-11 |
| RelatedTable with join_field (open question 1) | Task 2 tables.py |
| sys_customer_update=true (custom-only) | Tasks 5 + 6 queries |
| ScopeDiscoverer | Task 5 |
| ConfigFetcher + pagination | Task 6 |
| ArchiveWriter/Reader + nested layout | Task 7 |
| UpdateSetXmlBuilder | Task 8 |
| UpdateSetWriter create/reuse | Task 9 |
| CaptureEngine DI pattern | Task 10 |
| FakeCaptureEngine | Task 11 |
| nexus capture CLI 4 subcommands | Task 12 |
| Ratchet + roadmap update | Task 13 |

**Gaps found and addressed:**
- `_capture_engine` helper in Task 12 references `_get_password(meta)`. The existing CLI uses the instance registry and `SNOAuthClient` for token retrieval. At implementation time, follow the same pattern used in `instance_connect` to get the OAuth token. This is an intentional implementation note, not a placeholder.
- `# type: ignore[arg-type]` on `fields=row` in fetcher.py: temporary. The real client's `list_records` returns `list[dict[str, Any]]`. At implementation time, verify if the pre-edit hook blocks this -- if so, introduce a local `SnRecord` cast helper.

**Type consistency:** All method names match across tasks (e.g., `discover_scopes`, `push_to_update_set`, `save_archive`, `load_archive`). `CaptureEngine` method signatures match `CaptureProtocol`.
