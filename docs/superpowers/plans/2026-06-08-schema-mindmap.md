# Schema Mindmap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `nexus schema mindmap <area>` -- an AI-enriched, business-domain-grouped table catalog (Mermaid `mindmap` + grouped Markdown), the "which table stores what" companion to the existing ERD.

**Architecture:** Extends `nexus.schema`. Reuses `SchemaDiscoverer` unchanged. A new `TableEnricher` makes one batched `AgentClient` call (cluster into domains + write "Stores X" descriptions, grounded on the discovered fields + sparse `sys_documentation` hints); a new `MindmapEmitter` renders the catalog. `SchemaCartographer` gains an injected `AgentClient` and `build_mindmap`/`render_mindmap`.

**Tech Stack:** Python 3.14, Pydantic v2 (frozen+strict), Typer, pytest, existing `ServiceNowClientProtocol`/`FakeServiceNowClient` + `AgentClientProtocol`/`FakeAgentClient`.

**Spec:** `docs/superpowers/specs/2026-06-08-schema-mindmap-design.md`.

**Grounded facts:**
- `AgentClient()` takes no args (SDK handles auth); `complete(prompt, *, system, model, max_turns) -> str`. Raises `nexus.api.errors.AnthropicError(status_code: int, message: str)`.
- `FakeAgentClient` (dataclass) fields: `canned_response: str = "ok"`, `side_effect: BaseException | None`, `calls: list`. Same `complete` signature.
- `sys_documentation` carries only `label`/`plural` at table level and sparse field `hint`s -- so descriptions are AI-generated, grounded on real fields + any hints.
- `SchemaGraph.tables` is `tuple[TableDef, ...]`; `TableDef` has `name, label, scope, super_class, is_neighbor, fields` (`tuple[FieldDef,...]`); `FieldDef` has `name, label, type, reference_target, mandatory`.
- `SchemaCartographer.__init__(self, client, areas=DEFAULT_AREAS, *, archive_root, clock=...)`. Adding a required `agent_client` updates all call sites (no shim).

**Conventions (hooks enforce):** ASCII only; 4-line header (`# <path>` / desc / `# Author: Pierre Grothe` / `# Date: 2026-06-08`); Google docstrings; `__all__`; absolute imports; `from __future__ import annotations`; frozen+strict Pydantic; `datetime.now(UTC)`; no mocks; `test_<func>_<scenario>`; no `# type: ignore`; no bare except; no deferred imports. Run tests: `poetry run pytest <path> -v` (addopts gives `--timeout`; coverage is opt-in).

---

### Task 1: Catalog models

**Files:**
- Create: `src/nexus/schema/catalog.py`
- Test: `tests/schema/test_catalog_models.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/schema/test_catalog_models.py
# Tests for mindmap catalog Pydantic models.
# Author: Pierre Grothe
# Date: 2026-06-08
"""Verify catalog models are frozen and reject extras."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from nexus.schema.catalog import Domain, MindmapCatalog, TableDescription


def _catalog() -> MindmapCatalog:
    return MindmapCatalog(
        instance_id="alectri",
        area_key="bcm",
        generated_at=datetime(2026, 6, 8, tzinfo=UTC),
        display="Business Continuity Management",
        domains=(
            Domain(
                name="Plan Management",
                tables=(
                    TableDescription(
                        table="sn_bcp_plan", label="Plan",
                        description="Stores BC plans.", source="ai",
                    ),
                ),
            ),
        ),
    )


def test_mindmap_catalog_round_trips_through_json() -> None:
    catalog = _catalog()
    assert MindmapCatalog.model_validate_json(catalog.model_dump_json()) == catalog


def test_table_description_is_frozen() -> None:
    desc = TableDescription(table="t", label="T", description="d", source="ai")
    with pytest.raises(ValidationError):
        setattr(desc, "description", "other")


def test_domain_rejects_extra_field() -> None:
    with pytest.raises(ValidationError):
        Domain(name="X", tables=(), bogus=1)  # type: ignore[call-arg]
```

(Use `setattr`/extra-kwarg forms -- no `# type: ignore` in src; in this test the
inline ignore on the deliberate extra-kwarg line is acceptable, but if the
pre-edit hook blocks it, build the kwargs via `Domain(**{"name": "X", "tables": (), "bogus": 1})`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/schema/test_catalog_models.py -v`
Expected: FAIL with `ModuleNotFoundError: nexus.schema.catalog`

- [ ] **Step 3: Write the implementation**

```python
# src/nexus/schema/catalog.py
# Frozen Pydantic models for the AI-enriched mindmap catalog.
# Author: Pierre Grothe
# Date: 2026-06-08
"""TableDescription, Domain, and the MindmapCatalog aggregate."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

__all__ = ["Domain", "MindmapCatalog", "TableDescription"]

_CONFIG = ConfigDict(frozen=True, strict=True, extra="forbid")


class TableDescription(BaseModel):
    """One table's catalog entry.

    Args:
        table: Table API name.
        label: Table label (from the schema).
        description: One-line "Stores X" purpose.
        source: Where the description came from ("ai" or "label").
    """

    model_config = _CONFIG
    table: str
    label: str
    description: str
    source: str


class Domain(BaseModel):
    """A named business-domain grouping of tables.

    Args:
        name: Domain name (e.g. "Plan Management").
        tables: The tables in this domain.
    """

    model_config = _CONFIG
    name: str
    tables: tuple[TableDescription, ...]


class MindmapCatalog(BaseModel):
    """The full AI-enriched catalog for one area.

    Args:
        instance_id: Source instance profile name.
        area_key: Area key the catalog was built for.
        generated_at: UTC generation timestamp.
        display: Area display name (the mindmap root label).
        domains: The business domains and their tables.
    """

    model_config = _CONFIG
    instance_id: str
    area_key: str
    generated_at: datetime
    display: str
    domains: tuple[Domain, ...]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/schema/test_catalog_models.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/nexus/schema/catalog.py tests/schema/test_catalog_models.py
git commit -m "feat(schema): mindmap catalog models"
```

---

### Task 2: MindmapEmitter

**Files:**
- Create: `src/nexus/schema/mindmap_emitter.py`
- Test: `tests/schema/test_mindmap_emitter.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/schema/test_mindmap_emitter.py
# Tests for the Mermaid mindmap emitter.
# Author: Pierre Grothe
# Date: 2026-06-08
"""Emitter renders a mindmap block + grouped catalog."""

from datetime import UTC, datetime

from nexus.schema.catalog import Domain, MindmapCatalog, TableDescription
from nexus.schema.mindmap_emitter import MindmapEmitter


def _catalog() -> MindmapCatalog:
    return MindmapCatalog(
        instance_id="alectri",
        area_key="bcm",
        generated_at=datetime(2026, 6, 8, tzinfo=UTC),
        display="Business Continuity Management",
        domains=(
            Domain(
                name="Plan Management",
                tables=(
                    TableDescription(
                        table="sn_bcp_plan", label="Plan",
                        description="Stores BC plans and recovery objectives.", source="ai",
                    ),
                ),
            ),
        ),
    )


def test_render_contains_mermaid_mindmap_block() -> None:
    out = MindmapEmitter().render(_catalog())
    assert "```mermaid" in out
    assert "mindmap" in out
    assert "root((Business Continuity Management))" in out


def test_render_mindmap_leaf_shows_label_and_table() -> None:
    out = MindmapEmitter().render(_catalog())
    assert "Plan -- sn_bcp_plan" in out


def test_render_grouped_catalog_has_domain_and_description() -> None:
    out = MindmapEmitter().render(_catalog())
    assert "## Plan Management" in out
    assert "**Plan** [sn_bcp_plan]: Stores BC plans and recovery objectives." in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/schema/test_mindmap_emitter.py -v`
Expected: FAIL with `ModuleNotFoundError: nexus.schema.mindmap_emitter`

- [ ] **Step 3: Write the implementation**

```python
# src/nexus/schema/mindmap_emitter.py
# Renders a MindmapCatalog to Markdown with a Mermaid mindmap.
# Author: Pierre Grothe
# Date: 2026-06-08
"""MindmapEmitter: MindmapCatalog -> Markdown (mindmap block + grouped catalog)."""

from __future__ import annotations

from nexus.schema.catalog import MindmapCatalog

__all__ = ["MindmapEmitter"]


class MindmapEmitter:
    """Renders a MindmapCatalog to a Markdown mindmap document."""

    def render(self, catalog: MindmapCatalog) -> str:
        """Render the catalog.

        Args:
            catalog: The enriched catalog to render.

        Returns:
            Markdown with a Mermaid ``mindmap`` block and a grouped catalog list.
        """
        lines: list[str] = [
            f"# Schema mindmap: {catalog.area_key}",
            "",
            f"Instance: `{catalog.instance_id}`  |  generated: {catalog.generated_at.isoformat()}",
            "",
            "```mermaid",
            "mindmap",
            f"  root(({catalog.display}))",
        ]
        for domain in catalog.domains:
            lines.append(f"    {domain.name}")
            for table in domain.tables:
                lines.append(f"      {table.label} -- {table.table}")
        lines.append("```")
        lines.append("")
        for domain in catalog.domains:
            lines.append(f"## {domain.name}")
            lines.append("")
            for table in domain.tables:
                lines.append(f"- **{table.label}** [{table.table}]: {table.description}")
            lines.append("")
        return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/schema/test_mindmap_emitter.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/nexus/schema/mindmap_emitter.py tests/schema/test_mindmap_emitter.py
git commit -m "feat(schema): Mermaid mindmap emitter"
```

---

### Task 3: TableEnricher (core)

**Files:**
- Create: `src/nexus/schema/enricher.py`
- Test: `tests/schema/test_table_enricher.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/schema/test_table_enricher.py
# Tests for TableEnricher against fakes.
# Author: Pierre Grothe
# Date: 2026-06-08
"""Enricher turns a SchemaGraph + AI JSON into a MindmapCatalog."""

from datetime import UTC, datetime

import pytest

from nexus.api.errors import AnthropicError
from nexus.schema.enricher import TableEnricher
from nexus.schema.models import FieldDef, SchemaGraph, TableDef
from tests.fakes.fake_agent_client import FakeAgentClient
from tests.fakes.fake_sn_client import FakeServiceNowClient

_AI_JSON = (
    '{"domains":[{"name":"Plan Management","tables":'
    '[{"table":"sn_bcp_plan","description":"Stores BC plans."}]}]}'
)


def _graph() -> SchemaGraph:
    return SchemaGraph(
        instance_id="alectri",
        area_key="bcm",
        discovered_at=datetime(2026, 6, 8, tzinfo=UTC),
        scope_keys=("sn_bcp",),
        tables=(
            TableDef(
                name="sn_bcp_plan", label="Plan", scope="sn_bcp",
                fields=(FieldDef(name="plan_owner", label="Plan owner", type="reference",
                                 reference_target="sys_user"),),
            ),
        ),
        reference_edges=(),
        inheritance_edges=(),
        relationship_edges=(),
    )


def _enricher(sn: FakeServiceNowClient, ai: FakeAgentClient) -> TableEnricher:
    return TableEnricher(sn, ai, clock=lambda: datetime(2026, 6, 8, tzinfo=UTC))


@pytest.mark.asyncio
async def test_enrich_builds_catalog_from_ai_json() -> None:
    enricher = _enricher(FakeServiceNowClient(), FakeAgentClient(canned_response=_AI_JSON))
    catalog = await enricher.enrich(_graph(), display="BCM")
    assert catalog.domains[0].name == "Plan Management"
    assert catalog.domains[0].tables[0].description == "Stores BC plans."


@pytest.mark.asyncio
async def test_enrich_joins_ai_description_to_discovered_label() -> None:
    enricher = _enricher(FakeServiceNowClient(), FakeAgentClient(canned_response=_AI_JSON))
    catalog = await enricher.enrich(_graph(), display="BCM")
    assert catalog.domains[0].tables[0].label == "Plan"  # from the graph, not the AI


@pytest.mark.asyncio
async def test_enrich_includes_sys_documentation_hints_in_prompt() -> None:
    sn = FakeServiceNowClient(
        {"sys_documentation": [{"name": "sn_bcp_plan", "element": "plan_owner",
                                "hint": "The accountable plan owner."}]}
    )
    ai = FakeAgentClient(canned_response=_AI_JSON)
    await _enricher(sn, ai).enrich(_graph(), display="BCM")
    assert "The accountable plan owner." in str(ai.calls[0]["prompt"])


@pytest.mark.asyncio
async def test_enrich_falls_back_to_scope_grouping_on_ai_error() -> None:
    ai = FakeAgentClient(side_effect=AnthropicError(0, "boom"))
    catalog = await _enricher(FakeServiceNowClient(), ai).enrich(_graph(), display="BCM")
    assert catalog.domains[0].name == "sn_bcp"
    assert catalog.domains[0].tables[0].description == "Plan"  # label fallback


@pytest.mark.asyncio
async def test_enrich_falls_back_on_unparseable_json() -> None:
    ai = FakeAgentClient(canned_response="sorry, no JSON here")
    catalog = await _enricher(FakeServiceNowClient(), ai).enrich(_graph(), display="BCM")
    assert catalog.domains[0].name == "sn_bcp"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run pytest tests/schema/test_table_enricher.py -v`
Expected: FAIL with `ModuleNotFoundError: nexus.schema.enricher`

- [ ] **Step 3: Write the implementation**

```python
# src/nexus/schema/enricher.py
# AI-enriches a SchemaGraph into a domain-grouped MindmapCatalog.
# Author: Pierre Grothe
# Date: 2026-06-08
"""TableEnricher: sys_documentation hints + one batched AgentClient call."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Mapping
from datetime import UTC, datetime

from pydantic import ValidationError

from nexus.api.agent_client import AgentClientProtocol
from nexus.api.errors import AnthropicError
from nexus.connectors.servicenow.protocol import ServiceNowClientProtocol
from nexus.schema.catalog import Domain, MindmapCatalog, TableDescription
from nexus.schema.discoverer import cell
from nexus.schema.models import SchemaGraph, TableDef

log = logging.getLogger(__name__)

__all__ = ["TableEnricher"]

_IN_BATCH = 50
_SYSTEM = (
    "You are a ServiceNow data-model architect. Given tables with their fields, "
    "group EVERY table into business domains and write a one-line 'Stores X' "
    "description for each, grounded ONLY in the listed columns. Never invent "
    "tables. Respond with JSON only (no prose) of the exact shape: "
    '{"domains":[{"name":"<domain>","tables":[{"table":"<name>","description":"<text>"}]}]}'
)


class TableEnricher:
    """Builds a MindmapCatalog from a SchemaGraph using Claude.

    Args:
        client: Open ServiceNow client (read-only; used for sys_documentation).
        agent_client: LLM client for clustering + descriptions.
        clock: UTC clock (injectable for tests).
    """

    def __init__(
        self,
        client: ServiceNowClientProtocol,
        agent_client: AgentClientProtocol,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        """Initialize with a client, agent client, and clock."""
        self._client = client
        self._agent = agent_client
        self._clock = clock

    async def enrich(self, graph: SchemaGraph, *, display: str) -> MindmapCatalog:
        """Cluster the area's tables into domains with AI descriptions.

        Args:
            graph: The discovered schema graph.
            display: Area display name (the mindmap root label).

        Returns:
            A MindmapCatalog. Falls back to scope-grouping if the AI call fails.
        """
        in_scope = [t for t in graph.tables if not t.is_neighbor]
        label_by_name = {t.name: t.label for t in in_scope}
        hints = await self._fetch_hints([t.name for t in in_scope])
        prompt = self._build_prompt(in_scope, hints)
        try:
            raw = await self._agent.complete(prompt, system=_SYSTEM)
            return self._parse(raw, label_by_name, graph, display)
        except (AnthropicError, ValueError) as exc:
            log.warning("mindmap AI enrichment failed (%s); using fallback", exc)
            return self._fallback(in_scope, graph, display)

    async def _fetch_hints(self, table_names: list[str]) -> dict[tuple[str, str], str]:
        """Fetch sparse field-level hint text for grounding.

        Args:
            table_names: In-scope table names.

        Returns:
            Mapping of (table, element) to hint text.
        """
        hints: dict[tuple[str, str], str] = {}
        uniq = sorted(set(table_names))
        for i in range(0, len(uniq), _IN_BATCH):
            batch = uniq[i : i + _IN_BATCH]
            rows = await self._client.list_records(
                "sys_documentation",
                query=f"nameIN{','.join(batch)}^elementISNOTEMPTY^hintISNOTEMPTY",
                fields="name,element,hint",
                limit=5000,
            )
            for r in rows:
                hints[(cell(r, "name"), cell(r, "element"))] = cell(r, "hint")
        return hints

    def _build_prompt(
        self, tables: list[TableDef], hints: Mapping[tuple[str, str], str]
    ) -> str:
        """Render a deterministic prompt describing every table and its fields."""
        blocks: list[str] = []
        for t in sorted(tables, key=lambda x: x.name):
            field_lines: list[str] = []
            for f in t.fields:
                ref = f" -> {f.reference_target}" if f.reference_target else ""
                hint = hints.get((t.name, f.name), "")
                hint_txt = f"  ({hint})" if hint else ""
                field_lines.append(f"    - {f.name}: {f.label}{ref}{hint_txt}")
            fields = "\n".join(field_lines) or "    (no custom fields)"
            blocks.append(f"TABLE {t.name} [{t.label}] scope={t.scope}\n{fields}")
        return "Tables:\n\n" + "\n\n".join(blocks)

    def _parse(
        self,
        raw: str,
        label_by_name: Mapping[str, str],
        graph: SchemaGraph,
        display: str,
    ) -> MindmapCatalog:
        """Parse the AI JSON into a MindmapCatalog.

        Raises:
            ValueError: If the response has no JSON object or a malformed shape.
        """
        start, end = raw.find("{"), raw.rfind("}")
        if start == -1 or end < start:
            raise ValueError("no JSON object in AI response")
        try:
            obj = json.loads(raw[start : end + 1])
            domains = tuple(
                Domain(
                    name=str(d["name"]),
                    tables=tuple(
                        TableDescription(
                            table=str(t["table"]),
                            label=label_by_name.get(str(t["table"]), str(t["table"])),
                            description=str(t["description"]),
                            source="ai",
                        )
                        for t in d["tables"]
                    ),
                )
                for d in obj["domains"]
            )
        except (KeyError, TypeError, ValidationError) as exc:
            raise ValueError(f"malformed mindmap JSON: {exc}") from exc
        return MindmapCatalog(
            instance_id=graph.instance_id,
            area_key=graph.area_key,
            generated_at=self._clock(),
            display=display,
            domains=domains,
        )

    def _fallback(
        self, tables: list[TableDef], graph: SchemaGraph, display: str
    ) -> MindmapCatalog:
        """Build a scope-grouped, label-described catalog when the AI is unavailable."""
        by_scope: dict[str, list[TableDef]] = {}
        for t in tables:
            by_scope.setdefault(t.scope, []).append(t)
        domains = tuple(
            Domain(
                name=scope,
                tables=tuple(
                    TableDescription(table=t.name, label=t.label, description=t.label, source="label")
                    for t in tabs
                ),
            )
            for scope, tabs in sorted(by_scope.items())
        )
        return MindmapCatalog(
            instance_id=graph.instance_id,
            area_key=graph.area_key,
            generated_at=self._clock(),
            display=display,
            domains=domains,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run pytest tests/schema/test_table_enricher.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Verify 100% coverage**

Run: `poetry run pytest tests/schema/test_table_enricher.py --cov=nexus.schema.enricher --cov-report=term-missing -q`
Expected: `nexus/schema/enricher.py` at 100%. If a line is uncovered, add a focused test (e.g. a table with no fields exercises the `(no custom fields)` branch -- add it if missing).

- [ ] **Step 6: Commit**

```bash
git add src/nexus/schema/enricher.py tests/schema/test_table_enricher.py
git commit -m "feat(schema): TableEnricher (AI cluster + describe, grounded)"
```

---

### Task 4: Engine + protocol + exports + existing-test updates

**Files:**
- Modify: `src/nexus/schema/engine.py`
- Modify: `src/nexus/schema/protocol.py`
- Modify: `src/nexus/schema/__init__.py`
- Modify: `tests/schema/test_schema_cartographer.py` (3 ctor sites)
- Test: `tests/schema/test_schema_mindmap_engine.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/schema/test_schema_mindmap_engine.py
# Tests for SchemaCartographer mindmap methods.
# Author: Pierre Grothe
# Date: 2026-06-08
"""Engine discovers then enriches into a catalog and renders it."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from nexus.schema.areas import SchemaArea, ScopeRef
from nexus.schema.engine import SchemaCartographer
from tests.fakes.fake_agent_client import FakeAgentClient
from tests.fakes.fake_sn_client import FakeServiceNowClient

_AREAS = {"dd": SchemaArea(key="dd", display="DD", scopes=(ScopeRef("sn_grc_doc_design", "DD"),))}
_AI_JSON = (
    '{"domains":[{"name":"Core","tables":[{"table":"t1","description":"Stores t1."}]}]}'
)


def _seed() -> dict[str, list[dict[str, object]]]:
    return {
        "sys_scope": [{"sys_id": "SCID", "scope": "sn_grc_doc_design"}],
        "sys_db_object": [
            {"sys_id": "T1", "name": "t1", "label": "T1", "super_class": "",
             "sys_scope": {"link": "x", "value": "SCID"}},
        ],
        "sys_dictionary": [],
        "sys_relationship": [],
        "sys_documentation": [],
    }


def _engine(tmp_path: Path) -> SchemaCartographer:
    return SchemaCartographer(
        FakeServiceNowClient(_seed()),
        areas=_AREAS,
        archive_root=tmp_path,
        agent_client=FakeAgentClient(canned_response=_AI_JSON),
        clock=lambda: datetime(2026, 6, 8, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_build_mindmap_discovers_then_enriches(tmp_path: Path) -> None:
    catalog = await _engine(tmp_path).build_mindmap("alectri", "dd")
    assert catalog.display == "DD"
    assert catalog.domains[0].tables[0].description == "Stores t1."


@pytest.mark.asyncio
async def test_render_mindmap_returns_markdown(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    catalog = await engine.build_mindmap("alectri", "dd")
    assert "mindmap" in engine.render_mindmap(catalog)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/schema/test_schema_mindmap_engine.py -v`
Expected: FAIL (SchemaCartographer has no `agent_client` param / `build_mindmap`)

- [ ] **Step 3: Modify `src/nexus/schema/engine.py`**

Add imports (alphabetical within the first-party group):
```python
from nexus.api.agent_client import AgentClientProtocol
from nexus.schema.catalog import MindmapCatalog
from nexus.schema.enricher import TableEnricher
from nexus.schema.mindmap_emitter import MindmapEmitter
```

Change `__init__` to accept `agent_client` (required, keyword-only) and build the
enricher + mindmap emitter. The new signature and body:
```python
    def __init__(
        self,
        client: ServiceNowClientProtocol,
        areas: Mapping[str, SchemaArea] = DEFAULT_AREAS,
        *,
        archive_root: Path,
        agent_client: AgentClientProtocol,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        """Initialize the cartographer and its components."""
        self._discoverer = SchemaDiscoverer(client, areas, clock)
        self._reader = SchemaArchiveReader()
        self._emitter = MermaidErdEmitter()
        self._enricher = TableEnricher(client, agent_client, clock)
        self._mindmap_emitter = MindmapEmitter()
        self._areas = areas
        self._archive_root = archive_root
```
(Add `self._areas = areas` -- the engine needs the registry to read `area.display`.)

Add two methods (after `render_erd`):
```python
    async def build_mindmap(self, instance_id: str, area_key: str) -> MindmapCatalog:
        """Discover an area and AI-enrich it into a MindmapCatalog.

        Args:
            instance_id: Registered instance profile name.
            area_key: Key into the area registry.

        Returns:
            The enriched MindmapCatalog.
        """
        graph = await self._discoverer.discover(instance_id, area_key)
        return await self._enricher.enrich(graph, display=self._areas[area_key].display)

    def render_mindmap(self, catalog: MindmapCatalog) -> str:
        """Render a MindmapCatalog to Markdown.

        Args:
            catalog: The catalog to render.

        Returns:
            The Markdown mindmap document.
        """
        return self._mindmap_emitter.render(catalog)
```

- [ ] **Step 4: Modify `src/nexus/schema/protocol.py`**

Add `from nexus.schema.catalog import MindmapCatalog` and two protocol methods:
```python
    async def build_mindmap(self, instance_id: str, area_key: str) -> MindmapCatalog:
        """Discover an area and AI-enrich it into a MindmapCatalog."""
        ...

    def render_mindmap(self, catalog: MindmapCatalog) -> str:
        """Render a MindmapCatalog to Markdown."""
        ...
```

- [ ] **Step 5: Modify `src/nexus/schema/__init__.py`**

Add `from nexus.schema.catalog import MindmapCatalog` and add `"MindmapCatalog"` to
`__all__` (sorted).

- [ ] **Step 6: Update the 3 existing engine ctor sites in `tests/schema/test_schema_cartographer.py`**

That file's `_engine(tmp_path)` helper constructs `SchemaCartographer(...)`. Add
`agent_client=FakeAgentClient()` to the call and import the fake at the top:
```python
from tests.fakes.fake_agent_client import FakeAgentClient
```
The `_engine` builder becomes:
```python
def _engine(tmp_path: Path) -> SchemaCartographer:
    return SchemaCartographer(
        FakeServiceNowClient(_seed()),
        areas=_AREAS,
        archive_root=tmp_path,
        agent_client=FakeAgentClient(),
        clock=lambda: datetime(2026, 6, 8, tzinfo=UTC),
    )
```
(If any of the 3 tests construct the engine inline instead of via `_engine`, add
`agent_client=FakeAgentClient()` there too. Grep the file for `SchemaCartographer(` to find all sites.)

- [ ] **Step 7: Run tests**

Run: `poetry run pytest tests/schema/test_schema_mindmap_engine.py tests/schema/test_schema_cartographer.py -v`
Expected: PASS (2 new + the existing engine tests).

- [ ] **Step 8: Commit**

```bash
git add src/nexus/schema/engine.py src/nexus/schema/protocol.py src/nexus/schema/__init__.py tests/schema/test_schema_cartographer.py tests/schema/test_schema_mindmap_engine.py
git commit -m "feat(schema): SchemaCartographer build_mindmap/render_mindmap"
```

---

### Task 5: FakeSchemaCartographer mindmap methods

**Files:**
- Modify: `tests/schema/fakes/fake_schema_cartographer.py`
- Test: `tests/schema/test_fake_schema_cartographer.py` (add 1 test)

- [ ] **Step 1: Write the failing test (append to the existing file)**

```python
def test_fake_build_mindmap_returns_canned_catalog() -> None:
    from datetime import UTC, datetime

    from nexus.schema.catalog import Domain, MindmapCatalog, TableDescription

    catalog = MindmapCatalog(
        instance_id="alectri", area_key="bcm",
        generated_at=datetime(2026, 6, 8, tzinfo=UTC), display="BCM",
        domains=(Domain(name="Core", tables=(
            TableDescription(table="t", label="T", description="Stores t.", source="ai"),)),),
    )
    fake = FakeSchemaCartographer(_graph(), catalog=catalog)
    assert "mindmap" in fake.render_mindmap(catalog)
```

(Use the existing `_graph()` helper in that test file. The async `build_mindmap`
returns the canned catalog -- a dedicated async test is optional; the render test
plus the CLI test in Task 6 cover the surface.)

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/schema/test_fake_schema_cartographer.py -v`
Expected: FAIL (FakeSchemaCartographer has no `catalog` kwarg / `render_mindmap`)

- [ ] **Step 3: Modify `tests/schema/fakes/fake_schema_cartographer.py`**

Add a `catalog` field and the two methods. Add imports
`from nexus.schema.catalog import MindmapCatalog` at the top. Change the
constructor to accept an optional canned catalog, and add:
```python
    def __init__(self, graph: SchemaGraph, catalog: MindmapCatalog | None = None) -> None:
        """Initialize with the canned graph and optional catalog."""
        self._graph = graph
        self._catalog = catalog

    async def build_mindmap(self, instance_id: str, area_key: str) -> MindmapCatalog:
        """Return the canned catalog (raises if none was provided)."""
        del instance_id, area_key
        if self._catalog is None:
            raise ValueError("FakeSchemaCartographer was created without a catalog")
        return self._catalog

    def render_mindmap(self, catalog: MindmapCatalog) -> str:
        """Return a trivial Markdown stub mentioning the area key."""
        return f"# {catalog.area_key}\n\nmindmap"
```
(Keep the existing `discover`/`save_archive`/`load_archive`/`render_erd`/
`__aenter__`/`__aexit__`. The existing tests construct `FakeSchemaCartographer(_graph())`
-- the new `catalog=None` default keeps them working.)

- [ ] **Step 4: Run tests**

Run: `poetry run pytest tests/schema/test_fake_schema_cartographer.py -v`
Expected: PASS (existing + 1 new).

- [ ] **Step 5: Commit**

```bash
git add tests/schema/fakes/fake_schema_cartographer.py tests/schema/test_fake_schema_cartographer.py
git commit -m "test(schema): FakeSchemaCartographer mindmap methods"
```

---

### Task 6: CLI `nexus schema mindmap`

**Files:**
- Modify: `src/nexus/cli/views.py` (`_build_schema_cartographer` constructs AgentClient)
- Modify: `src/nexus/cli/commands_schema.py` (add the `mindmap` command)
- Test: `tests/cli/test_commands_schema.py` (add 1 test)

- [ ] **Step 1: Write the failing test (append to `tests/cli/test_commands_schema.py`)**

```python
def test_schema_mindmap_writes_markdown_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from datetime import UTC, datetime

    from nexus.schema.catalog import Domain, MindmapCatalog, TableDescription

    catalog = MindmapCatalog(
        instance_id="alectri", area_key="doc-designer",
        generated_at=datetime(2026, 6, 8, tzinfo=UTC), display="Document Designer",
        domains=(Domain(name="Core", tables=(
            TableDescription(table="t", label="T", description="Stores t.", source="ai"),)),),
    )
    fake = FakeSchemaCartographer(_graph(), catalog=catalog)
    monkeypatch.setattr(
        commands_schema, "_build_schema_cartographer", lambda _profile: (fake, fake)
    )
    out = tmp_path / "mm.md"
    result = CliRunner().invoke(
        app, ["schema", "mindmap", "doc-designer", "--profile", "alectri", "-o", str(out)]
    )
    assert result.exit_code == 0, result.stdout
    assert out.is_file()
    assert "mindmap" in out.read_text(encoding="utf-8")
```

(The existing test file already imports `commands_schema`, `app`,
`FakeSchemaCartographer`, `_graph`, `CliRunner`, `pytest`, `Path`. If `_graph()`
there does not yet build a `SchemaGraph` the fake accepts, reuse the existing one.)

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/cli/test_commands_schema.py::test_schema_mindmap_writes_markdown_file -v`
Expected: FAIL (no `mindmap` command)

- [ ] **Step 3: Modify `src/nexus/cli/views.py`**

Add `from nexus.api.agent_client import AgentClient` (alphabetical -- it sorts
before `nexus.capture`). Change `_build_schema_cartographer` to pass an
`AgentClient()`:
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
    cartographer = SchemaCartographer(
        client=client,
        archive_root=NexusPaths.from_env().schema_dir,
        agent_client=AgentClient(),
    )
    return cartographer, client
```

- [ ] **Step 4: Modify `src/nexus/cli/commands_schema.py`**

Add the `mindmap` command after `schema_erd`:
```python
@schema_app.command("mindmap")
def schema_mindmap(
    area: Annotated[str, typer.Argument(help="Area key (see `nexus schema areas`)")],
    profile: Annotated[str, typer.Option(help="Instance profile name")] = "",
    output: Annotated[
        Path | None, typer.Option("-o", "--output", help="Output Markdown path")
    ] = None,
) -> None:
    """Reverse-engineer an area and write an AI-described mindmap catalog."""

    async def _run() -> Path:
        cartographer, client = _build_schema_cartographer(profile)
        resolved = profile or _config_default()
        with nexus_progress(console) as progress:
            progress.add_task(f"Describing {area} on {resolved}...", total=None)
            async with client:
                catalog = await cartographer.build_mindmap(resolved, area)
        markdown = cartographer.render_mindmap(catalog)
        dest = output or Path(f"{area}-{resolved}-mindmap.md")
        dest.write_text(markdown, encoding="utf-8")
        return dest

    written = asyncio.run(_run())
    console.print(f"Wrote mindmap to {written}")
```

- [ ] **Step 5: Run tests**

Run: `poetry run pytest tests/cli/test_commands_schema.py -v`
Expected: PASS (existing areas/erd tests + the new mindmap test).

- [ ] **Step 6: Verify commands_schema coverage**

Run: `poetry run pytest tests/cli/test_commands_schema.py --cov=nexus.cli.commands_schema --cov-report=term-missing -q`
Expected: 100% (report any uncovered line).

- [ ] **Step 7: Commit**

```bash
git add src/nexus/cli/views.py src/nexus/cli/commands_schema.py tests/cli/test_commands_schema.py
git commit -m "feat(cli): nexus schema mindmap command"
```

---

### Task 7: Quality gate, ratchet, live mindmaps, primer

**Files:**
- Modify: `.ratchet.json` (add `nexus.schema.catalog`, `nexus.schema.enricher`, `nexus.schema.mindmap_emitter`; update `nexus.schema.engine`)
- Create: `docs/mindmaps/*.md` (generated)
- Modify: `.primer/active.md` (`/primer sync`)

- [ ] **Step 1: Full quality suite**

Run: `poetry run ruff check src/ tests/ && poetry run black --check src/ tests/ && poetry run mypy src/nexus/ && poetry run pyright src/nexus/schema src/nexus/cli && poetry run pytest tests/schema tests/cli -q`
Expected: ruff 0, black clean, mypy 0, pyright 0, all tests pass. Fix at root cause (no `# type: ignore`).

- [ ] **Step 2: 100% coverage for the new modules**

Run: `poetry run pytest tests/schema tests/cli --cov=nexus.schema --cov-report=term-missing -q`
Expected: `catalog`, `enricher`, `mindmap_emitter`, `engine` at 100% (protocol excluded). Add focused tests for any gap.

- [ ] **Step 3: Update `.ratchet.json`**

Run a scoped coverage JSON and add/refresh entries:
```bash
poetry run pytest tests/schema --cov=nexus.schema --cov-report=json:.cov.json -o addopts="" -q
```
Then add `"nexus.schema.catalog"`, `"nexus.schema.enricher"`,
`"nexus.schema.mindmap_emitter"` and refresh `"nexus.schema.engine"` in
`.ratchet.json` (covered_lines/total_lines from `.cov.json`). Delete `.cov.json`.
Validate: `python -c "import json; json.load(open('.ratchet.json'))"`.

- [ ] **Step 4: Generate the live deliverables**

Run: `poetry run nexus schema mindmap bcm --profile alectri -o docs/mindmaps/bcm-alectri.md`
and repeat for `doc-designer` and `cmdb-bcm`. (Live AI call against the instance.)
Read `docs/mindmaps/bcm-alectri.md` and confirm it shows domains + "Stores X"
descriptions resembling the blog.

- [ ] **Step 5: Commit + primer sync**

```bash
git add .ratchet.json docs/mindmaps/
git commit -m "chore(schema): ratchet entries + generated mindmaps"
```
Then run `/primer sync` to update `.primer/active.md`.

---

## Self-Review

- **Spec coverage:** catalog models (T1), MindmapEmitter (T2), TableEnricher with AI cluster + describe + sys_documentation hints + fallback (T3), engine build_mindmap/render_mindmap + protocol + exports + call-site updates (T4), fake (T5), CLI + AgentClient wiring (T6), enforcement + ratchet + live run + primer (T7). All spec sections map to a task.
- **Placeholder scan:** none -- every code step is complete.
- **Type consistency:** `MindmapCatalog(instance_id, area_key, generated_at, display, domains)`, `Domain(name, tables)`, `TableDescription(table, label, description, source)`, `TableEnricher(client, agent_client, clock).enrich(graph, *, display)`, `SchemaCartographer(..., *, archive_root, agent_client, clock).build_mindmap/render_mindmap` -- identical across tasks. `cell` reused from `discoverer`. `AnthropicError(status_code, message)` and `FakeAgentClient(canned_response=, side_effect=)` match the grounded shapes.
