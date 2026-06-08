# Schema Cartographer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a read-only `nexus.schema` layer that reverse-engineers a live ServiceNow data dictionary (scopes -> tables -> fields/reference edges -> inheritance) into a Mermaid ERD, exposed via `nexus schema` CLI commands.

**Architecture:** A layer-5 package mirroring `capture/`: pure-dataclass `areas` registry, frozen Pydantic `models`, a `SchemaDiscoverer` that queries `sys_scope`/`sys_db_object`/`sys_dictionary`/`sys_relationship` through the existing `ServiceNowClient`, a JSON archive, a `MermaidErdEmitter`, and a `SchemaCartographer` engine behind `SchemaProtocol`. CLI binds only to the protocol.

**Tech Stack:** Python 3.14, Pydantic v2 (frozen+strict), Typer, pytest, the existing `ServiceNowClientProtocol` + `FakeServiceNowClient`.

**Spec:** `docs/superpowers/specs/2026-06-08-schema-cartographer-design.md` (validated against live `alectri`, 2026-06-08).

**Key validated facts the code depends on:**
- Table API reference cells are dicts: `{"link"|"display_value", "value"}`. Normalize every cell through `cell(row, key)` -> takes `["value"]` if dict, else str.
- `sys_dictionary.reference.value` is the **target table name** directly (no sys_id lookup). A non-empty `reference` cell == a reference field.
- `sys_db_object.super_class.value` is a **sys_id**; resolve against the table set + a `sys_idIN` follow-up.
- `sys_relationship` columns are `apply_to` / `query_from`.
- `FakeServiceNowClient.list_records` **ignores `query`** (returns all seeded rows for a table). Tests seed exactly the expected return set; the discoverer derives scope membership from each row's `sys_scope` field, not from query filtering.

**Conventions (enforced by hooks):** file headers, Google docstrings, `__all__`, absolute imports, `from __future__ import annotations`, frozen+strict Pydantic (`ConfigDict(frozen=True, strict=True, extra="forbid")`), `datetime.now(UTC)`, no mocks, test names `test_<func>_<scenario>`. Activate the venv once: `source .venv/bin/activate`.

---

### Task 1: Error hierarchy

**Files:**
- Create: `src/nexus/schema/__init__.py` (empty placeholder for now)
- Create: `src/nexus/schema/errors.py`
- Test: `tests/schema/test_schema_errors.py`

- [ ] **Step 1: Create the package marker**

```python
# src/nexus/schema/__init__.py
# Schema cartography layer: reverse-engineer a live SN data dictionary into an ERD.
# Author: Pierre Grothe
# Date: 2026-06-08
"""nexus.schema -- ServiceNow data-dictionary cartographer."""

__all__: list[str] = []
```

- [ ] **Step 2: Write the failing test**

```python
# tests/schema/test_schema_errors.py
# Tests for the schema layer error hierarchy.
# Author: Pierre Grothe
# Date: 2026-06-08
"""Verify schema error types carry their context attributes."""

from pathlib import Path

from nexus.schema.errors import (
    AreaNotFoundError,
    SchemaArchiveError,
    SchemaError,
    ScopeNotFoundError,
)


def test_area_not_found_error_carries_area_key() -> None:
    err = AreaNotFoundError("doc-designer")
    assert isinstance(err, SchemaError)
    assert err.area_key == "doc-designer"


def test_scope_not_found_error_carries_context() -> None:
    err = ScopeNotFoundError("sn_bcm,sn_bcp", "alectri")
    assert isinstance(err, SchemaError)
    assert err.scopes == "sn_bcm,sn_bcp"
    assert err.instance_id == "alectri"


def test_schema_archive_error_carries_path() -> None:
    err = SchemaArchiveError(Path("/tmp/x.json"))
    assert isinstance(err, SchemaError)
    assert err.path == Path("/tmp/x.json")
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/schema/test_schema_errors.py -v`
Expected: FAIL with `ModuleNotFoundError: nexus.schema.errors`

- [ ] **Step 4: Write the implementation**

```python
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
        """Initialize with the unknown area key."""
        super().__init__(f"Unknown schema area {area_key!r}")
        self.area_key = area_key


class ScopeNotFoundError(SchemaError):
    """None of an area's scopes resolved on the instance."""

    def __init__(self, scopes: str, instance_id: str) -> None:
        """Initialize with the comma-joined scope keys and instance id."""
        super().__init__(f"No scopes {scopes!r} found on {instance_id!r}")
        self.scopes = scopes
        self.instance_id = instance_id


class SchemaArchiveError(SchemaError):
    """Schema snapshot JSON is missing or invalid."""

    def __init__(self, path: Path) -> None:
        """Initialize with the offending archive path."""
        super().__init__(f"Schema archive missing or invalid: {path}")
        self.path = path
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/schema/test_schema_errors.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: Commit**

```bash
git add src/nexus/schema/__init__.py src/nexus/schema/errors.py tests/schema/test_schema_errors.py
git commit -m "feat(schema): error hierarchy"
```

---

### Task 2: Area registry

**Files:**
- Create: `src/nexus/schema/areas.py`
- Test: `tests/schema/test_schema_areas.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/schema/test_schema_areas.py
# Tests for the schema area registry.
# Author: Pierre Grothe
# Date: 2026-06-08
"""Verify seeded areas expose the validated scopes."""

from nexus.schema.areas import DEFAULT_AREAS, DOC_DESIGNER, SchemaArea, ScopeRef


def test_default_areas_contains_three_seeded_areas() -> None:
    assert set(DEFAULT_AREAS) == {"doc-designer", "bcm", "cmdb-bcm"}


def test_doc_designer_scopes_are_validated_set() -> None:
    keys = [s.scope for s in DOC_DESIGNER.scopes]
    assert keys == ["sn_grc_doc_design", "sn_grc_rel_config"]


def test_schema_area_default_neighbor_hops_is_one() -> None:
    area = SchemaArea(key="x", display="X", scopes=(ScopeRef("a", "A"),))
    assert area.neighbor_hops == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/schema/test_schema_areas.py -v`
Expected: FAIL with `ModuleNotFoundError: nexus.schema.areas`

- [ ] **Step 3: Write the implementation**

```python
# src/nexus/schema/areas.py
# Pluggable registry of schema areas (scope groups) to map.
# Author: Pierre Grothe
# Date: 2026-06-08
"""SchemaArea registry: which SN application scopes form each cartography area."""

from dataclasses import dataclass

__all__ = [
    "BCM",
    "CMDB_BCM",
    "DEFAULT_AREAS",
    "DOC_DESIGNER",
    "SchemaArea",
    "ScopeRef",
]


@dataclass(slots=True, frozen=True)
class ScopeRef:
    """One application scope included in an area.

    Args:
        scope: The sys_scope.scope key, e.g. "sn_grc_doc_design".
        label: Human-readable product label.
    """

    scope: str
    label: str


@dataclass(slots=True, frozen=True)
class SchemaArea:
    """A named group of scopes to reverse-engineer together.

    Args:
        key: Machine-readable area key used in CLI and archives.
        display: Human-readable label.
        scopes: Scopes whose tables form the area.
        neighbor_hops: How many reference/inheritance hops outside the scopes
            to pull in as bridge nodes.
    """

    key: str
    display: str
    scopes: tuple[ScopeRef, ...]
    neighbor_hops: int = 1


DOC_DESIGNER = SchemaArea(
    key="doc-designer",
    display="Document Designer",
    scopes=(
        ScopeRef("sn_grc_doc_design", "Document Designer with Word"),
        ScopeRef("sn_grc_rel_config", "Data Relationships Framework"),
    ),
)

BCM = SchemaArea(
    key="bcm",
    display="Business Continuity Management",
    scopes=(
        ScopeRef("sn_bcm", "BCM Core"),
        ScopeRef("sn_bcm_lite", "BCM User Lite"),
        ScopeRef("sn_bcm_map", "Crisis Map"),
        ScopeRef("sn_bcp", "Business Continuity Planning"),
    ),
)

CMDB_BCM = SchemaArea(
    key="cmdb-bcm",
    display="CMDB <-> BCM bridge",
    scopes=(
        ScopeRef("sn_bcm", "BCM Core"),
        ScopeRef("sn_bcp", "Business Continuity Planning"),
    ),
)

DEFAULT_AREAS: dict[str, SchemaArea] = {a.key: a for a in (DOC_DESIGNER, BCM, CMDB_BCM)}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/schema/test_schema_areas.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/nexus/schema/areas.py tests/schema/test_schema_areas.py
git commit -m "feat(schema): area registry with validated scopes"
```

---

### Task 3: Data models

**Files:**
- Create: `src/nexus/schema/models.py`
- Test: `tests/schema/test_schema_models.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/schema/test_schema_models.py
# Tests for schema Pydantic models.
# Author: Pierre Grothe
# Date: 2026-06-08
"""Verify model immutability and the cross_scope_edges helper."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from nexus.schema.models import ReferenceEdge, SchemaGraph, TableDef


def _graph() -> SchemaGraph:
    return SchemaGraph(
        instance_id="alectri",
        area_key="doc-designer",
        discovered_at=datetime(2026, 6, 8, tzinfo=UTC),
        scope_keys=("sn_grc_doc_design",),
        tables=(TableDef(name="t", label="T", scope="sn_grc_doc_design"),),
        reference_edges=(
            ReferenceEdge(from_table="a", field="f1", to_table="b", cross_scope=False),
            ReferenceEdge(from_table="a", field="f2", to_table="z", cross_scope=True),
        ),
        inheritance_edges=(),
        relationship_edges=(),
    )


def test_schema_graph_cross_scope_edges_filters_to_cross_scope() -> None:
    edges = _graph().cross_scope_edges()
    assert [e.field for e in edges] == ["f2"]


def test_table_def_is_frozen() -> None:
    table = TableDef(name="t", label="T", scope="s")
    with pytest.raises(ValidationError):
        table.name = "other"  # type: ignore[misc]


def test_reference_edge_rejects_extra_field() -> None:
    with pytest.raises(ValidationError):
        ReferenceEdge(from_table="a", field="f", to_table="b", cross_scope=False, bogus=1)  # type: ignore[call-arg]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/schema/test_schema_models.py -v`
Expected: FAIL with `ModuleNotFoundError: nexus.schema.models`

- [ ] **Step 3: Write the implementation**

```python
# src/nexus/schema/models.py
# Frozen Pydantic models for the schema cartography graph.
# Author: Pierre Grothe
# Date: 2026-06-08
"""TableDef, FieldDef, edge models, and the SchemaGraph aggregate."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

__all__ = [
    "FieldDef",
    "InheritanceEdge",
    "ReferenceEdge",
    "RelationshipEdge",
    "SchemaGraph",
    "TableDef",
]

_CONFIG = ConfigDict(frozen=True, strict=True, extra="forbid")


class FieldDef(BaseModel):
    """One column on a table.

    Args:
        name: Field (element) name.
        label: Column label.
        type: "reference" for reference fields, "field" otherwise.
        reference_target: Target table name for reference fields, else None.
        mandatory: Whether the field is mandatory.
    """

    model_config = _CONFIG
    name: str
    label: str
    type: str
    reference_target: str | None = None
    mandatory: bool = False


class TableDef(BaseModel):
    """One table in the area (in-scope or a pulled-in neighbor).

    Args:
        name: Table API name.
        label: Table label.
        scope: Owning scope key, or "" for a neighbor.
        super_class: Parent table name (inheritance), or None.
        is_neighbor: True when pulled in via an edge rather than a scope.
        fields: The table's fields (empty for neighbors).
    """

    model_config = _CONFIG
    name: str
    label: str
    scope: str
    super_class: str | None = None
    is_neighbor: bool = False
    fields: tuple[FieldDef, ...] = ()


class ReferenceEdge(BaseModel):
    """A reference-field edge from one table to another.

    Args:
        from_table: Table carrying the reference field.
        field: The reference field element name.
        to_table: Target table name.
        cross_scope: True when from/to live in different scopes.
    """

    model_config = _CONFIG
    from_table: str
    field: str
    to_table: str
    cross_scope: bool


class InheritanceEdge(BaseModel):
    """A table-inheritance (extends) edge.

    Args:
        table: The child table.
        extends: The parent (super_class) table name.
        cross_scope: True when child/parent live in different scopes.
    """

    model_config = _CONFIG
    table: str
    extends: str
    cross_scope: bool


class RelationshipEdge(BaseModel):
    """A defined sys_relationship related-list edge.

    Args:
        name: Relationship name.
        apply_to: Parent table (the table the related list shows on).
        query_from: Related table.
    """

    model_config = _CONFIG
    name: str
    apply_to: str
    query_from: str


class SchemaGraph(BaseModel):
    """The full reverse-engineered graph for one area.

    Args:
        instance_id: Source instance profile name.
        area_key: Area key the graph was built for.
        discovered_at: UTC discovery timestamp.
        scope_keys: Scopes that resolved on the instance.
        tables: All tables (in-scope + neighbors).
        reference_edges: Reference-field edges.
        inheritance_edges: super_class edges.
        relationship_edges: Defined sys_relationship edges.
    """

    model_config = _CONFIG
    instance_id: str
    area_key: str
    discovered_at: datetime
    scope_keys: tuple[str, ...]
    tables: tuple[TableDef, ...]
    reference_edges: tuple[ReferenceEdge, ...]
    inheritance_edges: tuple[InheritanceEdge, ...]
    relationship_edges: tuple[RelationshipEdge, ...]

    def cross_scope_edges(self) -> tuple[ReferenceEdge, ...]:
        """Return reference edges that bridge two scopes."""
        return tuple(e for e in self.reference_edges if e.cross_scope)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/schema/test_schema_models.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/nexus/schema/models.py tests/schema/test_schema_models.py
git commit -m "feat(schema): frozen Pydantic graph models"
```

---

### Task 4: NexusPaths.schema_dir

**Files:**
- Modify: `src/nexus/config/paths.py:100-138` (add property + ensure_dirs entry)
- Test: `tests/config/test_paths_schema_dir.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/config/test_paths_schema_dir.py
# Tests for NexusPaths.schema_dir.
# Author: Pierre Grothe
# Date: 2026-06-08
"""Verify schema_dir resolves and is created by ensure_dirs."""

from pathlib import Path

from nexus.config.paths import NexusPaths


def test_schema_dir_is_under_root(tmp_path: Path) -> None:
    paths = NexusPaths(root=tmp_path)
    assert paths.schema_dir == tmp_path / "schema"


def test_ensure_dirs_creates_schema_dir(tmp_path: Path) -> None:
    paths = NexusPaths(root=tmp_path)
    paths.ensure_dirs()
    assert paths.schema_dir.is_dir()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/config/test_paths_schema_dir.py -v`
Expected: FAIL with `AttributeError: 'NexusPaths' object has no attribute 'schema_dir'`

- [ ] **Step 3: Add the property after `archives_dir` (line 104)**

```python
    @property
    def schema_dir(self) -> Path:
        """Local schema cartography snapshots root."""
        return self.root / "schema"
```

- [ ] **Step 4: Add `self.schema_dir` to the `ensure_dirs` tuple**

In `ensure_dirs`, add `self.schema_dir,` after `self.archives_dir,`:

```python
        for path in (
            self.root,
            self.templates_dir,
            self.reports_dir,
            self.jobs_dir,
            self.logs_dir,
            self.cache_dir,
            self.instances_dir,
            self.archives_dir,
            self.schema_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/config/test_paths_schema_dir.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Commit**

```bash
git add src/nexus/config/paths.py tests/config/test_paths_schema_dir.py
git commit -m "feat(config): NexusPaths.schema_dir"
```

---

### Task 5: SchemaDiscoverer (core)

**Files:**
- Create: `src/nexus/schema/discoverer.py`
- Test: `tests/schema/test_schema_discoverer.py`

The discoverer derives scope membership from each row's `sys_scope` (the fake ignores `query`). Tests seed `sys_scope`, `sys_db_object`, `sys_dictionary`, `sys_relationship` tables.

- [ ] **Step 1: Write the failing tests**

```python
# tests/schema/test_schema_discoverer.py
# Tests for SchemaDiscoverer against the FakeServiceNowClient.
# Author: Pierre Grothe
# Date: 2026-06-08
"""Discovery transforms seeded dictionary rows into a SchemaGraph."""

from datetime import UTC, datetime

import pytest

from nexus.schema.areas import SchemaArea, ScopeRef
from nexus.schema.discoverer import SchemaDiscoverer, cell
from nexus.schema.errors import AreaNotFoundError, ScopeNotFoundError
from tests.fakes.fake_sn_client import FakeServiceNowClient

_AREA = SchemaArea(key="dd", display="DD", scopes=(ScopeRef("sn_grc_doc_design", "DD"),))
_AREAS = {"dd": _AREA}


def _ref(value: str) -> dict[str, str]:
    return {"link": f"x/{value}", "value": value}


def _seed() -> dict[str, list[dict[str, object]]]:
    return {
        "sys_scope": [{"sys_id": "SCID", "scope": "sn_grc_doc_design"}],
        "sys_db_object": [
            {
                "sys_id": "T1",
                "name": "sn_grc_doc_design_data_rel_mapping",
                "label": "Content configuration",
                "super_class": "",
                "sys_scope": _ref("SCID"),
            },
            {
                "sys_id": "T2",
                "name": "sn_grc_doc_design_data_relationship",
                "label": "Data relationship",
                "super_class": "",
                "sys_scope": _ref("SCID"),
            },
            # Out-of-scope parent table, seeded so super_class resolves to a name.
            {"sys_id": "TASK", "name": "task", "label": "Task", "super_class": "",
             "sys_scope": _ref("GLOBAL")},
        ],
        "sys_dictionary": [
            {"name": "sn_grc_doc_design_data_rel_mapping", "element": "data_relationship",
             "column_label": "Data relationship", "reference": _ref("sn_grc_doc_design_data_relationship"),
             "mandatory": "true"},
            {"name": "sn_grc_doc_design_data_relationship", "element": "name",
             "column_label": "Name", "reference": "", "mandatory": "false"},
        ],
        "sys_relationship": [
            {"name": "rel", "apply_to": _ref("sn_grc_doc_design_data_relationship"),
             "query_from": _ref("sn_grc_doc_design_data_rel_mapping")},
        ],
    }


def _disc(seed: dict[str, list[dict[str, object]]]) -> SchemaDiscoverer:
    return SchemaDiscoverer(
        FakeServiceNowClient(seed),
        areas=_AREAS,
        clock=lambda: datetime(2026, 6, 8, tzinfo=UTC),
    )


def test_cell_extracts_value_from_reference_dict() -> None:
    assert cell({"f": {"link": "x", "value": "abc"}}, "f") == "abc"


def test_cell_returns_plain_string() -> None:
    assert cell({"f": "plain"}, "f") == "plain"


def test_cell_missing_key_returns_empty() -> None:
    assert cell({}, "f") == ""


@pytest.mark.asyncio
async def test_discover_unknown_area_raises() -> None:
    with pytest.raises(AreaNotFoundError):
        await _disc(_seed()).discover("alectri", "nope")


@pytest.mark.asyncio
async def test_discover_no_scope_resolves_raises() -> None:
    seed = _seed()
    seed["sys_scope"] = []
    with pytest.raises(ScopeNotFoundError):
        await _disc(seed).discover("alectri", "dd")


@pytest.mark.asyncio
async def test_discover_builds_reference_edge_with_target_name() -> None:
    graph = await _disc(_seed()).discover("alectri", "dd")
    edge = next(e for e in graph.reference_edges if e.field == "data_relationship")
    assert edge.from_table == "sn_grc_doc_design_data_rel_mapping"
    assert edge.to_table == "sn_grc_doc_design_data_relationship"
    assert edge.cross_scope is False


@pytest.mark.asyncio
async def test_discover_classifies_in_scope_tables_only() -> None:
    graph = await _disc(_seed()).discover("alectri", "dd")
    in_scope = {t.name for t in graph.tables if not t.is_neighbor}
    assert in_scope == {
        "sn_grc_doc_design_data_rel_mapping",
        "sn_grc_doc_design_data_relationship",
    }


@pytest.mark.asyncio
async def test_discover_sets_discovered_at_from_clock() -> None:
    graph = await _disc(_seed()).discover("alectri", "dd")
    assert graph.discovered_at == datetime(2026, 6, 8, tzinfo=UTC)


@pytest.mark.asyncio
async def test_discover_builds_relationship_edge() -> None:
    graph = await _disc(_seed()).discover("alectri", "dd")
    assert graph.relationship_edges[0].name == "rel"


@pytest.mark.asyncio
async def test_discover_inheritance_edge_marks_neighbor_parent() -> None:
    seed = _seed()
    # Make the data_relationship table extend the out-of-scope `task` table.
    for row in seed["sys_db_object"]:
        if row["name"] == "sn_grc_doc_design_data_relationship":
            row["super_class"] = _ref("TASK")
    graph = await _disc(seed).discover("alectri", "dd")
    inh = next(e for e in graph.inheritance_edges if e.table == "sn_grc_doc_design_data_relationship")
    assert inh.extends == "task"
    assert inh.cross_scope is True
    assert any(t.name == "task" and t.is_neighbor for t in graph.tables)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/schema/test_schema_discoverer.py -v`
Expected: FAIL with `ModuleNotFoundError: nexus.schema.discoverer`

- [ ] **Step 3: Write the implementation**

```python
# src/nexus/schema/discoverer.py
# Reverse-engineers a live SN data dictionary into a SchemaGraph.
# Author: Pierre Grothe
# Date: 2026-06-08
"""SchemaDiscoverer: sys_scope -> sys_db_object -> sys_dictionary / sys_relationship."""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from datetime import UTC, datetime

from nexus.connectors.servicenow.protocol import ServiceNowClientProtocol
from nexus.schema.areas import DEFAULT_AREAS, SchemaArea
from nexus.schema.errors import AreaNotFoundError, ScopeNotFoundError
from nexus.schema.models import (
    FieldDef,
    InheritanceEdge,
    ReferenceEdge,
    RelationshipEdge,
    SchemaGraph,
    TableDef,
)

log = logging.getLogger(__name__)

__all__ = ["SchemaDiscoverer", "cell"]

_IN_BATCH = 40
_OUT = "__out"  # sentinel scope for tables outside the area


def cell(row: Mapping[str, object], key: str) -> str:
    """Extract a Table API cell's scalar value.

    Reference cells are dicts (``{"link"|"display_value", "value"}``); take
    ``value``. Plain scalars return as a string. Missing keys return "".

    Args:
        row: A Table API result row.
        key: Column name.

    Returns:
        The scalar value (sys_id or table name for references), else "".
    """
    raw = row.get(key)
    if isinstance(raw, dict):
        return str(raw.get("value", ""))
    return "" if raw is None else str(raw)


class SchemaDiscoverer:
    """Builds a SchemaGraph for one area from a live instance.

    Args:
        client: Open ServiceNow client (read-only Table API).
        areas: Area registry keyed by area key.
        clock: Callable returning the current UTC time (injectable for tests).
    """

    def __init__(
        self,
        client: ServiceNowClientProtocol,
        areas: Mapping[str, SchemaArea] = DEFAULT_AREAS,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        """Initialize with a client, area registry, and clock."""
        self._client = client
        self._areas = areas
        self._clock = clock

    async def discover(self, instance_id: str, area_key: str) -> SchemaGraph:
        """Reverse-engineer the data dictionary for one area.

        Args:
            instance_id: Registered instance profile name.
            area_key: Key into the area registry.

        Returns:
            A SchemaGraph of tables and reference/inheritance/relationship edges.

        Raises:
            AreaNotFoundError: If area_key is unknown.
            ScopeNotFoundError: If none of the area's scopes resolve.
        """
        if area_key not in self._areas:
            raise AreaNotFoundError(area_key)
        area = self._areas[area_key]
        scope_keys = [s.scope for s in area.scopes]

        scope_rows = await self._client.list_records(
            "sys_scope", query=f"scopeIN{','.join(scope_keys)}", fields="sys_id,scope", limit=200
        )
        key_by_id = {cell(r, "sys_id"): cell(r, "scope") for r in scope_rows if cell(r, "sys_id")}
        present = set(key_by_id.values())
        for missing in (k for k in scope_keys if k not in present):
            log.warning("scope %r absent on %s -- skipping", missing, instance_id)
        if not key_by_id:
            raise ScopeNotFoundError(",".join(scope_keys), instance_id)

        # In-scope tables: membership derived from each row's sys_scope.
        db_rows = await self._batched_in(
            "sys_db_object", "sys_scope", list(key_by_id),
            fields="sys_id,name,label,super_class,sys_scope",
        )
        name_by_id: dict[str, str] = {}
        label_by_name: dict[str, str] = {}
        meta: dict[str, tuple[str, str]] = {}  # name -> (scope_key, super_id)
        for r in db_rows:
            name = cell(r, "name")
            scope_id = cell(r, "sys_scope")
            if not name or scope_id not in key_by_id:
                continue
            name_by_id[cell(r, "sys_id")] = name
            label_by_name[name] = cell(r, "label")
            meta[name] = (key_by_id[scope_id], cell(r, "super_class"))
        in_scope = sorted(meta)

        # Resolve super_class parent sys_ids to names (+ labels).
        parent_ids = sorted({s for _, s in meta.values() if s and s not in name_by_id})
        if parent_ids:
            for r in await self._batched_in(
                "sys_db_object", "sys_id", parent_ids, fields="sys_id,name,label"
            ):
                pname = cell(r, "name")
                name_by_id[cell(r, "sys_id")] = pname
                label_by_name.setdefault(pname, cell(r, "label"))

        # Fields + reference edges.
        dict_rows = await self._batched_in(
            "sys_dictionary", "name", in_scope,
            fields="name,element,column_label,reference,mandatory", suffix="^elementISNOTEMPTY",
        )
        fields_by: dict[str, list[FieldDef]] = {}
        ref_edges: list[ReferenceEdge] = []
        for r in dict_rows:
            tname = cell(r, "name")
            elem = cell(r, "element")
            if tname not in meta or not elem:
                continue
            ref = cell(r, "reference")  # reference.value IS the target table name
            fields_by.setdefault(tname, []).append(
                FieldDef(
                    name=elem,
                    label=cell(r, "column_label"),
                    type="reference" if ref else "field",
                    reference_target=ref or None,
                    mandatory=cell(r, "mandatory") == "true",
                )
            )
            if ref:
                cross = meta[tname][0] != meta.get(ref, (_OUT, ""))[0]
                ref_edges.append(
                    ReferenceEdge(from_table=tname, field=elem, to_table=ref, cross_scope=cross)
                )

        # Inheritance edges + neighbor collection.
        inh_edges: list[InheritanceEdge] = []
        neighbors: set[str] = set()
        for name, (scope_key, super_id) in meta.items():
            parent = name_by_id.get(super_id, "")
            if not parent:
                continue
            cross = scope_key != meta.get(parent, (_OUT, ""))[0]
            inh_edges.append(InheritanceEdge(table=name, extends=parent, cross_scope=cross))
            if parent not in meta:
                neighbors.add(parent)
        neighbors.update(e.to_table for e in ref_edges if e.to_table not in meta)

        tables: list[TableDef] = [
            TableDef(
                name=name,
                label=label_by_name.get(name, name),
                scope=scope_key,
                super_class=name_by_id.get(super_id) or None,
                is_neighbor=False,
                fields=tuple(fields_by.get(name, ())),
            )
            for name, (scope_key, super_id) in meta.items()
        ]
        tables.extend(
            TableDef(name=nb, label=label_by_name.get(nb, nb), scope="", is_neighbor=True)
            for nb in sorted(neighbors)
        )

        rel_rows = await self._client.list_records(
            "sys_relationship",
            query=f"apply_toIN{','.join(in_scope)}^ORquery_fromIN{','.join(in_scope)}",
            fields="name,apply_to,query_from",
            limit=2000,
        )
        rel_edges = [
            RelationshipEdge(
                name=cell(r, "name"), apply_to=cell(r, "apply_to"), query_from=cell(r, "query_from")
            )
            for r in rel_rows
            if cell(r, "name")
        ]

        return SchemaGraph(
            instance_id=instance_id,
            area_key=area_key,
            discovered_at=self._clock(),
            scope_keys=tuple(sorted(present)),
            tables=tuple(tables),
            reference_edges=tuple(ref_edges),
            inheritance_edges=tuple(inh_edges),
            relationship_edges=tuple(rel_edges),
        )

    async def _batched_in(
        self,
        table: str,
        field: str,
        values: list[str],
        *,
        fields: str,
        suffix: str = "",
    ) -> list[dict[str, object]]:
        """Run ``{field}IN{batch}`` queries in batches of _IN_BATCH.

        Args:
            table: Table to query.
            field: Field for the IN clause.
            values: Values to batch.
            fields: Comma-separated fields to return.
            suffix: Extra encoded-query fragment appended to each batch query.

        Returns:
            Concatenated rows across all batches.
        """
        rows: list[dict[str, object]] = []
        uniq = sorted({v for v in values if v})
        for i in range(0, len(uniq), _IN_BATCH):
            batch = uniq[i : i + _IN_BATCH]
            rows.extend(
                await self._client.list_records(
                    table, query=f"{field}IN{','.join(batch)}{suffix}", fields=fields, limit=5000
                )
            )
        return rows
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/schema/test_schema_discoverer.py -v`
Expected: PASS (11 passed)

- [ ] **Step 5: Commit**

```bash
git add src/nexus/schema/discoverer.py tests/schema/test_schema_discoverer.py
git commit -m "feat(schema): SchemaDiscoverer with validated cell normalization"
```

---

### Task 6: JSON archive

**Files:**
- Create: `src/nexus/schema/archive.py`
- Test: `tests/schema/test_schema_archive.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/schema/test_schema_archive.py
# Tests for the schema JSON archive round-trip.
# Author: Pierre Grothe
# Date: 2026-06-08
"""Writer + reader preserve the SchemaGraph; bad input raises."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from nexus.schema.archive import SchemaArchiveReader, SchemaArchiveWriter
from nexus.schema.errors import SchemaArchiveError
from nexus.schema.models import SchemaGraph, TableDef


def _graph() -> SchemaGraph:
    return SchemaGraph(
        instance_id="alectri",
        area_key="doc-designer",
        discovered_at=datetime(2026, 6, 8, 12, tzinfo=UTC),
        scope_keys=("sn_grc_doc_design",),
        tables=(TableDef(name="t", label="T", scope="sn_grc_doc_design"),),
        reference_edges=(),
        inheritance_edges=(),
        relationship_edges=(),
    )


def test_write_then_read_roundtrips_graph(tmp_path: Path) -> None:
    path = SchemaArchiveWriter(tmp_path).write(_graph())
    loaded = SchemaArchiveReader().read(path)
    assert loaded == _graph()


def test_write_places_file_under_instance_dir(tmp_path: Path) -> None:
    path = SchemaArchiveWriter(tmp_path).write(_graph())
    assert path.parent == tmp_path / "alectri"
    assert path.suffix == ".json"


def test_read_missing_file_raises_archive_error(tmp_path: Path) -> None:
    with pytest.raises(SchemaArchiveError):
        SchemaArchiveReader().read(tmp_path / "nope.json")


def test_read_invalid_json_raises_archive_error(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(SchemaArchiveError):
        SchemaArchiveReader().read(bad)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/schema/test_schema_archive.py -v`
Expected: FAIL with `ModuleNotFoundError: nexus.schema.archive`

- [ ] **Step 3: Write the implementation**

```python
# src/nexus/schema/archive.py
# JSON snapshot writer/reader for SchemaGraph.
# Author: Pierre Grothe
# Date: 2026-06-08
"""Persist and reload SchemaGraph snapshots under the schema archive root."""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from nexus.schema.errors import SchemaArchiveError
from nexus.schema.models import SchemaGraph

__all__ = ["SchemaArchiveReader", "SchemaArchiveWriter"]


class SchemaArchiveWriter:
    """Writes SchemaGraph snapshots as JSON under a root directory.

    Args:
        root: Archive root (e.g. NexusPaths.schema_dir).
    """

    def __init__(self, root: Path) -> None:
        """Initialize with the archive root."""
        self._root = root

    def write(self, graph: SchemaGraph) -> Path:
        """Serialize a graph to ``{root}/{instance}/{area}-{ts}.json``.

        Args:
            graph: The graph to persist.

        Returns:
            Path to the written JSON file.
        """
        stamp = graph.discovered_at.strftime("%Y%m%d-%H%M%S")
        dest_dir = self._root / graph.instance_id
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{graph.area_key}-{stamp}.json"
        dest.write_text(graph.model_dump_json(indent=2), encoding="utf-8")
        return dest


class SchemaArchiveReader:
    """Reads SchemaGraph snapshots back from JSON."""

    def read(self, path: Path) -> SchemaGraph:
        """Deserialize a snapshot.

        Args:
            path: Path to a snapshot JSON file.

        Returns:
            The reconstructed SchemaGraph.

        Raises:
            SchemaArchiveError: If the file is missing or invalid.
        """
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise SchemaArchiveError(path) from exc
        try:
            return SchemaGraph.model_validate_json(raw)
        except ValidationError as exc:
            raise SchemaArchiveError(path) from exc
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/schema/test_schema_archive.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/nexus/schema/archive.py tests/schema/test_schema_archive.py
git commit -m "feat(schema): JSON archive writer/reader"
```

---

### Task 7: MermaidErdEmitter

**Files:**
- Create: `src/nexus/schema/erd.py`
- Test: `tests/schema/test_schema_erd.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/schema/test_schema_erd.py
# Tests for the Mermaid ERD emitter.
# Author: Pierre Grothe
# Date: 2026-06-08
"""Emitter renders edges with correct cardinality and a bridge section."""

from datetime import UTC, datetime

from nexus.schema.erd import MermaidErdEmitter
from nexus.schema.models import FieldDef, ReferenceEdge, SchemaGraph, TableDef


def _graph() -> SchemaGraph:
    return SchemaGraph(
        instance_id="alectri",
        area_key="doc-designer",
        discovered_at=datetime(2026, 6, 8, tzinfo=UTC),
        scope_keys=("sn_grc_doc_design",),
        tables=(
            TableDef(
                name="content_config",
                label="Content configuration",
                scope="sn_grc_doc_design",
                fields=(FieldDef(name="data_relationship", label="Data rel", type="reference"),),
            ),
            TableDef(name="data_relationship", label="Data relationship", scope="sn_grc_doc_design"),
            TableDef(name="sn_data_registry_relationship", label="Registry", scope="", is_neighbor=True),
        ),
        reference_edges=(
            ReferenceEdge(from_table="content_config", field="data_relationship",
                          to_table="data_relationship", cross_scope=False),
            ReferenceEdge(from_table="data_relationship", field="data_registry",
                          to_table="sn_data_registry_relationship", cross_scope=True),
        ),
        inheritance_edges=(),
        relationship_edges=(),
    )


def test_render_contains_mermaid_erdiagram_block() -> None:
    out = MermaidErdEmitter().render(_graph())
    assert "```mermaid" in out
    assert "erDiagram" in out


def test_render_reference_edge_renders_many_to_one() -> None:
    out = MermaidErdEmitter().render(_graph())
    assert 'content_config }o--|| data_relationship : "data_relationship"' in out


def test_render_cross_scope_bridge_section_lists_cross_scope_edges() -> None:
    out = MermaidErdEmitter().render(_graph())
    assert "## Cross-scope bridges" in out
    assert "data_relationship.data_registry -> sn_data_registry_relationship" in out


def test_render_field_appendix_lists_table_fields() -> None:
    out = MermaidErdEmitter().render(_graph())
    assert "## Fields" in out
    assert "data_relationship" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/schema/test_schema_erd.py -v`
Expected: FAIL with `ModuleNotFoundError: nexus.schema.erd`

- [ ] **Step 3: Write the implementation**

```python
# src/nexus/schema/erd.py
# Renders a SchemaGraph to a Markdown + Mermaid erDiagram document.
# Author: Pierre Grothe
# Date: 2026-06-08
"""MermaidErdEmitter: SchemaGraph -> Markdown with a Mermaid erDiagram."""

from __future__ import annotations

from nexus.schema.models import SchemaGraph

__all__ = ["MermaidErdEmitter"]


class MermaidErdEmitter:
    """Renders a SchemaGraph to a single-diagram Markdown ERD document."""

    def render(self, graph: SchemaGraph) -> str:
        """Render the full Markdown document.

        Args:
            graph: The graph to render.

        Returns:
            A Markdown string with a Mermaid erDiagram, a cross-scope bridge
            list, and a per-table field appendix.
        """
        lines: list[str] = [
            f"# Schema ERD: {graph.area_key}",
            "",
            f"Instance: `{graph.instance_id}`  |  scopes: {', '.join(graph.scope_keys)}",
            f"Discovered: {graph.discovered_at.isoformat()}",
            "",
            "```mermaid",
            "erDiagram",
        ]
        for edge in graph.reference_edges:
            lines.append(f'    {edge.from_table} }}o--|| {edge.to_table} : "{edge.field}"')
        for inh in graph.inheritance_edges:
            lines.append(f'    {inh.extends} ||--|| {inh.table} : "extends"')
        lines.append("```")
        lines.append("")

        lines.append("## Cross-scope bridges")
        lines.append("")
        bridges = graph.cross_scope_edges()
        if bridges:
            for e in bridges:
                lines.append(f"- `{e.from_table}.{e.field}` -> `{e.to_table}`")
        else:
            lines.append("- (none)")
        lines.append("")

        lines.append("## Fields")
        lines.append("")
        for table in graph.tables:
            if table.is_neighbor:
                continue
            lines.append(f"### {table.name} -- {table.label}")
            lines.append("")
            lines.append("| Field | Type | References |")
            lines.append("| --- | --- | --- |")
            for fld in table.fields:
                lines.append(f"| {fld.name} | {fld.type} | {fld.reference_target or ''} |")
            lines.append("")
        return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/schema/test_schema_erd.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/nexus/schema/erd.py tests/schema/test_schema_erd.py
git commit -m "feat(schema): Mermaid ERD emitter"
```

---

### Task 8: SchemaProtocol + SchemaCartographer engine

**Files:**
- Create: `src/nexus/schema/protocol.py`
- Create: `src/nexus/schema/engine.py`
- Test: `tests/schema/test_schema_cartographer.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/schema/test_schema_cartographer.py
# Tests for the SchemaCartographer engine.
# Author: Pierre Grothe
# Date: 2026-06-08
"""Engine wires discover -> archive -> render through one object."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from nexus.schema.areas import SchemaArea, ScopeRef
from nexus.schema.engine import SchemaCartographer
from tests.fakes.fake_sn_client import FakeServiceNowClient

_AREAS = {"dd": SchemaArea(key="dd", display="DD", scopes=(ScopeRef("sn_grc_doc_design", "DD"),))}


def _seed() -> dict[str, list[dict[str, object]]]:
    return {
        "sys_scope": [{"sys_id": "SCID", "scope": "sn_grc_doc_design"}],
        "sys_db_object": [
            {"sys_id": "T1", "name": "t1", "label": "T1", "super_class": "",
             "sys_scope": {"link": "x", "value": "SCID"}},
        ],
        "sys_dictionary": [],
        "sys_relationship": [],
    }


def _engine(tmp_path: Path) -> SchemaCartographer:
    return SchemaCartographer(
        FakeServiceNowClient(_seed()),
        areas=_AREAS,
        archive_root=tmp_path,
        clock=lambda: datetime(2026, 6, 8, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_discover_then_save_then_load_roundtrips(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    graph = await engine.discover("alectri", "dd")
    path = engine.save_archive(graph)
    assert engine.load_archive(path) == graph


@pytest.mark.asyncio
async def test_render_erd_returns_markdown(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    graph = await engine.discover("alectri", "dd")
    assert "erDiagram" in engine.render_erd(graph)


@pytest.mark.asyncio
async def test_save_archive_default_dest_uses_archive_root(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    graph = await engine.discover("alectri", "dd")
    path = engine.save_archive(graph)
    assert tmp_path in path.parents
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/schema/test_schema_cartographer.py -v`
Expected: FAIL with `ModuleNotFoundError: nexus.schema.engine`

- [ ] **Step 3: Write the protocol**

```python
# src/nexus/schema/protocol.py
# Structural protocol the CLI binds to for schema cartography.
# Author: Pierre Grothe
# Date: 2026-06-08
"""SchemaProtocol: the surface CLI/TUI depend on (not the concrete engine)."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from nexus.schema.models import SchemaGraph

__all__ = ["SchemaProtocol"]


class SchemaProtocol(Protocol):
    """Discover, persist, and render schema graphs."""

    async def discover(self, instance_id: str, area_key: str) -> SchemaGraph:
        """Reverse-engineer one area into a SchemaGraph."""
        ...

    def save_archive(self, graph: SchemaGraph, dest: Path | None = None) -> Path:
        """Persist a graph as JSON; return the written path."""
        ...

    def load_archive(self, path: Path) -> SchemaGraph:
        """Load a graph snapshot from JSON."""
        ...

    def render_erd(self, graph: SchemaGraph) -> str:
        """Render a graph to Markdown + Mermaid."""
        ...
```

- [ ] **Step 4: Write the engine**

```python
# src/nexus/schema/engine.py
# Concrete SchemaCartographer wiring discoverer + archive + emitter.
# Author: Pierre Grothe
# Date: 2026-06-08
"""SchemaCartographer: implements SchemaProtocol over a live client."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path

from nexus.connectors.servicenow.protocol import ServiceNowClientProtocol
from nexus.schema.areas import DEFAULT_AREAS, SchemaArea
from nexus.schema.archive import SchemaArchiveReader, SchemaArchiveWriter
from nexus.schema.discoverer import SchemaDiscoverer
from nexus.schema.erd import MermaidErdEmitter
from nexus.schema.models import SchemaGraph

__all__ = ["SchemaCartographer"]


class SchemaCartographer:
    """Wires discovery, archiving, and ERD rendering behind one object.

    Args:
        client: Open ServiceNow client.
        areas: Area registry.
        archive_root: Root for JSON snapshots (defaults to schema_dir at save time).
        clock: UTC clock (injectable for tests).
    """

    def __init__(
        self,
        client: ServiceNowClientProtocol,
        areas: Mapping[str, SchemaArea] = DEFAULT_AREAS,
        archive_root: Path | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        """Initialize the cartographer and its components."""
        self._discoverer = SchemaDiscoverer(client, areas, clock)
        self._reader = SchemaArchiveReader()
        self._emitter = MermaidErdEmitter()
        self._archive_root = archive_root

    async def discover(self, instance_id: str, area_key: str) -> SchemaGraph:
        """Reverse-engineer one area into a SchemaGraph."""
        return await self._discoverer.discover(instance_id, area_key)

    def save_archive(self, graph: SchemaGraph, dest: Path | None = None) -> Path:
        """Persist a graph as JSON under dest or the archive root.

        Args:
            graph: The graph to persist.
            dest: Optional override root; falls back to the configured root or
                ``NexusPaths.schema_dir``.

        Returns:
            Path to the written JSON file.
        """
        root = dest or self._archive_root
        if root is None:
            from nexus.config.paths import NexusPaths

            root = NexusPaths.from_env().schema_dir
        return SchemaArchiveWriter(root).write(graph)

    def load_archive(self, path: Path) -> SchemaGraph:
        """Load a graph snapshot from JSON."""
        return self._reader.read(path)

    def render_erd(self, graph: SchemaGraph) -> str:
        """Render a graph to Markdown + Mermaid."""
        return self._emitter.render(graph)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/schema/test_schema_cartographer.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: Commit**

```bash
git add src/nexus/schema/protocol.py src/nexus/schema/engine.py tests/schema/test_schema_cartographer.py
git commit -m "feat(schema): SchemaProtocol + SchemaCartographer engine"
```

---

### Task 9: Package exports

**Files:**
- Modify: `src/nexus/schema/__init__.py`
- Test: `tests/schema/test_schema_exports.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/schema/test_schema_exports.py
# Tests that the schema package re-exports its public API.
# Author: Pierre Grothe
# Date: 2026-06-08
"""Verify top-level imports resolve."""

from nexus.schema import (
    DEFAULT_AREAS,
    SchemaCartographer,
    SchemaGraph,
    SchemaProtocol,
)


def test_public_symbols_importable() -> None:
    assert "doc-designer" in DEFAULT_AREAS
    assert SchemaCartographer is not None
    assert SchemaGraph is not None
    assert SchemaProtocol is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/schema/test_schema_exports.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Replace the package marker with real exports**

```python
# src/nexus/schema/__init__.py
# Schema cartography layer: reverse-engineer a live SN data dictionary into an ERD.
# Author: Pierre Grothe
# Date: 2026-06-08
"""nexus.schema -- ServiceNow data-dictionary cartographer."""

from nexus.schema.areas import DEFAULT_AREAS, SchemaArea, ScopeRef
from nexus.schema.engine import SchemaCartographer
from nexus.schema.models import SchemaGraph
from nexus.schema.protocol import SchemaProtocol

__all__ = [
    "DEFAULT_AREAS",
    "SchemaArea",
    "SchemaCartographer",
    "SchemaGraph",
    "SchemaProtocol",
    "ScopeRef",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/schema/test_schema_exports.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add src/nexus/schema/__init__.py tests/schema/test_schema_exports.py
git commit -m "feat(schema): package exports"
```

---

### Task 10: FakeSchemaCartographer (for CLI tests)

**Files:**
- Create: `tests/schema/fakes/__init__.py`
- Create: `tests/schema/fakes/fake_schema_cartographer.py`
- Test: `tests/schema/test_fake_schema_cartographer.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/schema/test_fake_schema_cartographer.py
# Tests for the FakeSchemaCartographer test double.
# Author: Pierre Grothe
# Date: 2026-06-08
"""Verify the fake returns its canned graph and round-trips."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from nexus.schema.models import SchemaGraph, TableDef
from tests.schema.fakes.fake_schema_cartographer import FakeSchemaCartographer


def _graph() -> SchemaGraph:
    return SchemaGraph(
        instance_id="alectri",
        area_key="doc-designer",
        discovered_at=datetime(2026, 6, 8, tzinfo=UTC),
        scope_keys=("sn_grc_doc_design",),
        tables=(TableDef(name="t", label="T", scope="sn_grc_doc_design"),),
        reference_edges=(),
        inheritance_edges=(),
        relationship_edges=(),
    )


@pytest.mark.asyncio
async def test_fake_discover_returns_canned_graph() -> None:
    fake = FakeSchemaCartographer(_graph())
    assert await fake.discover("alectri", "doc-designer") == _graph()


def test_fake_render_erd_returns_string() -> None:
    fake = FakeSchemaCartographer(_graph())
    assert "doc-designer" in fake.render_erd(_graph())


def test_fake_save_and_load_roundtrips(tmp_path: Path) -> None:
    fake = FakeSchemaCartographer(_graph())
    path = fake.save_archive(_graph(), dest=tmp_path)
    assert fake.load_archive(path) == _graph()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/schema/test_fake_schema_cartographer.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Create the package marker and the fake**

```python
# tests/schema/fakes/__init__.py
# Test doubles for the schema layer.
# Author: Pierre Grothe
# Date: 2026-06-08
"""Fakes implementing SchemaProtocol for CLI/engine tests."""

__all__: list[str] = []
```

```python
# tests/schema/fakes/fake_schema_cartographer.py
# In-memory SchemaProtocol fake for CLI tests.
# Author: Pierre Grothe
# Date: 2026-06-08
"""FakeSchemaCartographer: canned-graph substitute for SchemaCartographer."""

from pathlib import Path

from nexus.schema.models import SchemaGraph

__all__ = ["FakeSchemaCartographer"]


class FakeSchemaCartographer:
    """Returns a canned SchemaGraph and round-trips it through JSON.

    Args:
        graph: The graph returned by discover() and persisted by save_archive().
    """

    def __init__(self, graph: SchemaGraph) -> None:
        """Initialize with the canned graph."""
        self._graph = graph

    async def discover(self, instance_id: str, area_key: str) -> SchemaGraph:
        """Return the canned graph regardless of inputs."""
        del instance_id, area_key
        return self._graph

    def save_archive(self, graph: SchemaGraph, dest: Path | None = None) -> Path:
        """Write the graph JSON under dest (defaults to cwd) and return the path."""
        root = dest or Path.cwd()
        root.mkdir(parents=True, exist_ok=True)
        path = root / f"{graph.area_key}.json"
        path.write_text(graph.model_dump_json(indent=2), encoding="utf-8")
        return path

    def load_archive(self, path: Path) -> SchemaGraph:
        """Reload a graph snapshot from JSON."""
        return SchemaGraph.model_validate_json(path.read_text(encoding="utf-8"))

    def render_erd(self, graph: SchemaGraph) -> str:
        """Return a trivial Markdown stub mentioning the area key."""
        return f"# {graph.area_key}\n\nerDiagram"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/schema/test_fake_schema_cartographer.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add tests/schema/fakes/ tests/schema/test_fake_schema_cartographer.py
git commit -m "test(schema): FakeSchemaCartographer for CLI tests"
```

---

### Task 11: CLI `nexus schema` commands

**Files:**
- Modify: `src/nexus/cli/apps.py:21-50` (add `schema_app`)
- Modify: `src/nexus/cli/views.py:43-74` (add `_build_schema_cartographer`)
- Create: `src/nexus/cli/commands_schema.py`
- Modify: `src/nexus/cli/__init__.py` (import the new command module so decorators register)
- Test: `tests/cli/test_commands_schema.py`

- [ ] **Step 1: Register `schema_app` in apps.py**

Add to `__all__`: `"schema_app",`. After the `capture_app` wiring (line 39), add:

```python
schema_app = typer.Typer(name="schema", help="Reverse-engineer SN table schemas into ERDs.")
app.add_typer(schema_app)
```

- [ ] **Step 2: Add `_build_schema_cartographer` to views.py**

Add `"_build_schema_cartographer",` to `__all__`, import `SchemaCartographer`
(`from nexus.schema import SchemaCartographer`), and add:

```python
def _build_schema_cartographer(profile: str) -> tuple[SchemaCartographer, ServiceNowClient]:
    """Build a SchemaCartographer for the given registered instance profile.

    Args:
        profile: Instance profile name from InstanceRegistry.

    Returns:
        Tuple of (SchemaCartographer, ServiceNowClient).

    Raises:
        typer.Exit: With code 1 if the profile is not registered or expired.
    """
    _, meta, token, _ = _acquire_token(profile)
    client = ServiceNowClient(instance_url=meta.url, token=token)
    cartographer = SchemaCartographer(client=client, archive_root=NexusPaths.from_env().schema_dir)
    return cartographer, client
```

- [ ] **Step 3: Write the failing test**

```python
# tests/cli/test_commands_schema.py
# Tests for the `nexus schema` CLI commands.
# Author: Pierre Grothe
# Date: 2026-06-08
"""areas lists the registry; erd writes a Markdown file via an injected fake."""

from datetime import UTC, datetime
from pathlib import Path

from typer.testing import CliRunner

from nexus.cli.apps import app
from nexus.schema.models import SchemaGraph, TableDef
from tests.schema.fakes.fake_schema_cartographer import FakeSchemaCartographer


def _graph() -> SchemaGraph:
    return SchemaGraph(
        instance_id="alectri",
        area_key="doc-designer",
        discovered_at=datetime(2026, 6, 8, tzinfo=UTC),
        scope_keys=("sn_grc_doc_design",),
        tables=(TableDef(name="t", label="T", scope="sn_grc_doc_design"),),
        reference_edges=(),
        inheritance_edges=(),
        relationship_edges=(),
    )


def test_schema_areas_lists_registered_areas() -> None:
    result = CliRunner().invoke(app, ["schema", "areas"])
    assert result.exit_code == 0
    assert "doc-designer" in result.stdout


def test_schema_erd_writes_markdown_file(tmp_path: Path, monkeypatch) -> None:
    import nexus.cli.commands_schema as mod

    fake = FakeSchemaCartographer(_graph())
    monkeypatch.setattr(
        mod, "_build_schema_cartographer", lambda profile: (fake, fake)
    )
    out = tmp_path / "erd.md"
    result = CliRunner().invoke(
        app, ["schema", "erd", "doc-designer", "--profile", "alectri", "-o", str(out)]
    )
    assert result.exit_code == 0, result.stdout
    assert out.is_file()
    assert "erDiagram" in out.read_text(encoding="utf-8")
```

Note: `FakeSchemaCartographer` doubles as both cartographer and client here; add
`async def __aenter__`/`__aexit__` to it (Step 5) so `async with client` works.

- [ ] **Step 4: Run test to verify it fails**

Run: `pytest tests/cli/test_commands_schema.py -v`
Expected: FAIL with `ModuleNotFoundError: nexus.cli.commands_schema`

- [ ] **Step 5: Add async-context methods to the fake**

In `tests/schema/fakes/fake_schema_cartographer.py`, add:

```python
    async def __aenter__(self) -> "FakeSchemaCartographer":
        """Support `async with` so the fake doubles as the client."""
        return self

    async def __aexit__(self, *_: object) -> None:
        """No-op async context exit."""
```

- [ ] **Step 6: Write the command module**

```python
# src/nexus/cli/commands_schema.py
# Typer command bodies for the `nexus schema` sub-app.
# Author: Pierre Grothe
# Date: 2026-06-08
"""`nexus schema` commands: areas, discover, erd."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

import typer

from nexus.cli.apps import schema_app
from nexus.cli.auth import config_default as _config_default
from nexus.cli.console import console
from nexus.cli.views import _build_schema_cartographer
from nexus.schema.areas import DEFAULT_AREAS
from nexus.ui import nexus_progress

__all__: list[str] = []


@schema_app.command("areas")
def schema_areas() -> None:
    """List the registered schema areas and their scopes."""
    for key, area in DEFAULT_AREAS.items():
        scopes = ", ".join(s.scope for s in area.scopes)
        console.print(f"{key}  --  {area.display}  ({scopes})")


@schema_app.command("erd")
def schema_erd(
    area: Annotated[str, typer.Argument(help="Area key (see `nexus schema areas`)")],
    profile: Annotated[str, typer.Option(help="Instance profile name")] = "",
    output: Annotated[
        Path | None, typer.Option("-o", "--output", help="Output Markdown path")
    ] = None,
) -> None:
    """Reverse-engineer an area and write a Markdown ERD."""

    async def _run() -> Path:
        cartographer, client = _build_schema_cartographer(profile)
        resolved = profile or _config_default()
        with nexus_progress(console) as progress:
            progress.add_task(f"Mapping {area} on {resolved}...", total=None)
            async with client:
                graph = await cartographer.discover(resolved, area)
        markdown = cartographer.render_erd(graph)
        dest = output or Path(f"{area}-{resolved}.md")
        dest.write_text(markdown, encoding="utf-8")
        return dest

    written = asyncio.run(_run())
    console.print(f"Wrote ERD to {written}")
```

- [ ] **Step 7: Import the module in `cli/__init__.py`**

Find where the other `commands_*` modules are imported in `src/nexus/cli/__init__.py` (search for `commands_capture`) and add alongside them:

```python
from nexus.cli import commands_schema as _commands_schema  # noqa: F401
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `pytest tests/cli/test_commands_schema.py -v`
Expected: PASS (2 passed)

- [ ] **Step 9: Commit**

```bash
git add src/nexus/cli/apps.py src/nexus/cli/views.py src/nexus/cli/commands_schema.py src/nexus/cli/__init__.py tests/cli/test_commands_schema.py
git commit -m "feat(cli): nexus schema areas/erd commands"
```

---

### Task 12: Quality gate, ratchet, primer sync

**Files:**
- Modify: `.ratchet.json` (add `nexus.schema.*` entries)
- Modify: `.primer/active.md` (via `/primer sync`)

- [ ] **Step 1: Run the full quality suite**

Run: `source .venv/bin/activate && ruff check src/ tests/ && black --check src/ tests/ && mypy src/nexus/ && pyright src/nexus/ && pytest`
Expected: ruff 0, black clean, mypy 0, pyright 0, all tests pass.
Fix any violations at the root (no `# type: ignore`, no `# noqa` beyond the established F401 import-for-registration pattern).

- [ ] **Step 2: Confirm 100% line coverage for the new layer**

Run: `pytest --cov=nexus.schema --cov-report=term-missing tests/schema/`
Expected: `nexus/schema/*` at 100%. Add focused tests for any missed lines.

- [ ] **Step 3: Update the ratchet**

Run the project's coverage/ratchet refresh (the post-edit hook tracks this; if a
manual refresh script exists, run it). Ensure `.ratchet.json` contains entries for
`nexus.schema.discoverer`, `nexus.schema.engine`, `nexus.schema.archive`,
`nexus.schema.erd`, `nexus.schema.models`, `nexus.schema.areas`,
`nexus.schema.errors`, `nexus.schema.protocol` with `covered_lines == total_lines`.

- [ ] **Step 4: Run the live deliverable (manual verification)**

Run: `python -m nexus schema erd doc-designer --profile alectri -o docs/erd/doc-designer-alectri.md`
Expected: a Markdown ERD whose Mermaid block shows
`content_config ... -> data_relationship` and whose "Cross-scope bridges" lists
`data_relationship.data_registry -> sn_data_registry_relationship`. Repeat for
`bcm` and `cmdb-bcm`. (Read-only against the live instance.)

- [ ] **Step 5: Primer sync + commit**

```bash
git add .ratchet.json docs/erd/
git commit -m "chore(schema): ratchet entries + generated ERDs"
```

Then run `/primer sync` to update `.primer/active.md` with the shipped epic.

---

## Self-Review

- **Spec coverage:** areas registry (Task 2), models incl. RelationshipEdge + cross_scope_edges (Task 3), schema_dir (Task 4), discoverer with validated normalization (Task 5), JSON archive (Task 6), Mermaid ERD + cross-scope bridges + appendix (Task 7), protocol + engine (Task 8), exports (Task 9), fake (Task 10), CLI areas/erd (Task 11), enforcement + live run (Task 12). The spec's `nexus schema discover`/`list` subcommands are folded into `erd` (discovers fresh) + `areas` for v1; if standalone `discover`/`list` are wanted, add them mirroring Task 11 (non-blocking).
- **Placeholder scan:** none -- every code step is complete.
- **Type consistency:** `cell()` signature, `SchemaGraph` field names, `ReferenceEdge(from_table, field, to_table, cross_scope)`, `SchemaCartographer(client, areas, archive_root, clock)`, and the protocol methods are identical across tasks.
