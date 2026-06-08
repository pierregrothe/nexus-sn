# NEXUS -- Schema Cartographer Design

Date: 2026-06-08
Author: Pierre Grothe

## Overview

The `nexus.schema` layer reverse-engineers a live ServiceNow instance's data
dictionary into an entity-relationship map (ERD). It answers a recurring
solution-consulting question: "which tables make up product X, and how are they
related?" -- the question the product documentation rarely answers directly.

Immediate driver: case CS9240769 (RONA Inc, P2). The customer (Luc Lalancette)
asked two things support deflected to the account team:

1. In a GRC **Document Designer** template configuration, what is the
   relationship between **Fields**, **Data Relationships**, and **Content
   Configuration**? The Yokohama GRC docs describe each in isolation, never how
   they wire together.
2. Is there an internal "mind map of tables" -- the way a community blog ERD
   maps **BCM** today -- for Document Designer, and for the **CMDB <-> BCM**
   relationship?

Both reduce to the same primitive: discover the tables in a set of application
scopes, extract the reference edges between them from `sys_dictionary`, capture
table-inheritance (`super_class`) edges that bridge scopes (this is how BCM
links to CMDB and the `task` tree), and render a legible ERD. The triad Luc is
confused about is exactly the reference edges among the Document Designer config
tables -- so the ERD plus a short narrative is a direct, evidenced answer.

This is v1: schema-level ERD only. A record-level "config trace" (walk a real
OOB template config's actual Field / Data Relationship / Content Configuration
records) is deferred to a fast-follow story -- see Deferred Work.

### Instance confirmation (2026-06-08, read-only probe)

Both registered profiles carry the products. Target is `alectri` (newer):

| Product | Scope | alectri | retail |
|---|---|---|---|
| Document Designer with Word | `sn_grc_doc_design` | v21.1.3 | v21.0.4 |
| Data Relationships Framework | `sn_grc_rel_config` | v10.0.0 | v10.0.0 |
| 360 Relationship Visualization | `sn_grc_360degree` | v22.0.0 | v22.0.0 |
| BCM Core / Lite / Crisis Map | `sn_bcm`, `sn_bcm_lite`, `sn_bcm_map` | v10.0.1 | v10.0.1 |
| Business Continuity Planning | `sn_bcp` | v10.0.2 | v9.1.2 |
| CMDB | `cmdb_ci` tree | present | present |

Discovery is by scope, not name prefix: Document Designer's physical tables live
under `sn_grc_doc_design` with non-obvious names, so a `sys_db_object` query
filtered by scope sys_id is the correct primitive.

### Validated against live `alectri` (2026-06-08)

A read-only probe ran the full pipeline (`sys_scope -> sys_db_object ->
sys_dictionary`) against the live instance and confirmed it works end to end:
50 tables across the target scopes, **94 reference edges (42 cross-scope)**, and
all `super_class` inheritance edges resolved. Ground-truth findings that shaped
this spec:

- **Document Designer triad wiring (the P2 answer), verified from real edges:**
  - `sn_grc_doc_design_template_config` -- Template configuration (root)
  - `sn_grc_doc_design_data_relationship` -- Data relationship
  - `sn_grc_doc_design_data_rel_mapping` -- **Content configuration**
  - `sn_grc_doc_design_data_column` -- Data column ("Fields")

  Edges: `data_rel_mapping.data_relationship -> data_relationship` and
  `data_rel_mapping.template_configuration -> template_config` (Content
  Configuration binds a Data Relationship into a Template -- it is the join);
  `data_rel_mapping.parent_relationship_mapping -> self` (nestable content
  blocks); `data_column.data_relationship_mapping -> data_rel_mapping` (Fields
  hang off a Content Configuration); `data_relationship.data_registry ->
  sn_data_registry_relationship` (bridge to the 360 Template Relationship
  Registry). So the real model is a three-level hierarchy
  (Template -> Content Config [-> Data Relationship] -> Fields), which
  **corrects** the customer's hypothesis that "Fields can be used alone."
- **CMDB <-> BCM bridge verified:** `sn_bcp_recovery_task.configuration_item ->
  cmdb_ci`; `sn_bcp_plan_task extends task`; BCP tables extend BCM tables
  (cross-scope inheritance).
- **Table API normalization (load-bearing):** reference fields always return
  dicts (`{link|display_value, value}`), even in default mode. Critically,
  `sys_dictionary.reference.value` is the **target table name directly** (no
  sys_id lookup), while `sys_db_object.super_class.value` is a **sys_id** that
  must be resolved against the table set. No `sysparm_display_value=all` is
  needed; reference fields are detected by a non-empty `reference` column.
- `sn_grc_360degree` and the BCM lite/map scopes have **zero own tables** (config
  lives elsewhere), so empty-scope handling must be non-fatal.

---

## Roadmap Position

```
[done]  Foundation: config, auth, capabilities, connectors, instance management
[done]  capture, assessment, template library (apply)
[next]  nexus.schema layer   <-- this spec  (epic 2026.06-schema-cartographer)
        - SchemaDiscoverer (sys_scope -> sys_db_object -> sys_dictionary / sys_relationship)
        - SchemaGraph models + JSON archive
        - MermaidErdEmitter (Markdown + Mermaid erDiagram)
        - nexus schema (discover, erd, list)
[then]  config-trace fast-follow: record-level OOB template walk-through
```

New ADR-025 records the layer decision. PRD-004 (optional) captures the
solution-consulting use case.

---

## Layer Position

```
cache -> config -> auth -> capabilities -> api -> connectors
      -> capture
      -> assessment
      -> schema       <-- this spec; uses ServiceNowClient (read-only)
      -> cli (binds to SchemaProtocol only)
```

`nexus.schema` imports `connectors` (ServiceNowClient), `config` (NexusPaths),
`cache`. It has no knowledge of assessment rules, capture archives, or CLI
rendering. It never writes to the instance -- all queries are GET.

---

## Module Layout

```
src/nexus/schema/
  __init__.py        -- exports SchemaProtocol, SchemaCartographer, models
  protocol.py        -- SchemaProtocol (structural Protocol)
  areas.py           -- ScopeRef, SchemaArea, DOC_DESIGNER, BCM, CMDB_BCM, DEFAULT_AREAS
  discoverer.py      -- SchemaDiscoverer
  models.py          -- TableDef, FieldDef, ReferenceEdge, InheritanceEdge,
                        RelationshipEdge, SchemaGraph (+ reuses capture SnRecord)
  archive.py         -- SchemaArchiveWriter, SchemaArchiveReader (JSON)
  erd.py             -- MermaidErdEmitter
  engine.py          -- SchemaCartographer (implements SchemaProtocol)
  errors.py          -- SchemaError hierarchy

tests/schema/
  test_schema_discoverer_*.py
  test_erd_emitter_*.py
  test_schema_archive_*.py
  test_schema_cartographer_*.py
  fakes/
    fake_schema_cartographer.py   -- implements SchemaProtocol for CLI tests
```

---

## Area Registry

Pure frozen dataclasses (the `capture/tables.py` pattern). One `SchemaArea`
per customer-facing question. Adding an area is one constant + one dict entry;
no engine change.

```python
# schema/areas.py

@dataclass(slots=True, frozen=True)
class ScopeRef:
    scope: str          # "sn_grc_doc_design"  (the sys_scope.scope key)
    label: str          # "Document Designer with Word"

@dataclass(slots=True, frozen=True)
class SchemaArea:
    key: str            # "doc-designer"
    display: str        # "Document Designer"
    scopes: tuple[ScopeRef, ...]
    neighbor_hops: int = 1   # include reference targets N hops outside the scopes

DOC_DESIGNER = SchemaArea(
    key="doc-designer",
    display="Document Designer",
    scopes=(
        ScopeRef("sn_grc_doc_design", "Document Designer with Word"),
        ScopeRef("sn_grc_rel_config", "Data Relationships Framework"),
    ),
    # sn_grc_360degree omitted: validated to own zero tables. The shared bridge
    # table sn_data_registry_relationship arrives via neighbor_hops=1.
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
    scopes=(ScopeRef("sn_bcm", "BCM Core"), ScopeRef("sn_bcp", "Business Continuity Planning")),
    neighbor_hops=1,   # pulls in cmdb_ci targets that BCM tables reference
)

DEFAULT_AREAS: dict[str, SchemaArea] = {a.key: a for a in (DOC_DESIGNER, BCM, CMDB_BCM)}
```

`neighbor_hops` keeps diagrams legible: render every table in the area's scopes,
plus tables 1 hop out along reference/inheritance edges (so CMDB and `task`
parents appear as bridge nodes without dragging in their entire subtree).

---

## Data Models

All Pydantic models: `ConfigDict(frozen=True, strict=True, extra="forbid")`.
Reuses the `SnRecord` / `SnRefField` type aliases already defined in
`capture/models.py` for raw Table API rows. No `dict[str, Any]`.

```python
# schema/models.py

class FieldDef(BaseModel):
    name: str               # element, e.g. "data_relationship"
    label: str              # column_label
    type: str               # internal_type display, e.g. "Reference", "String"
    reference_target: str | None = None   # target table for reference fields
    mandatory: bool = False

class TableDef(BaseModel):
    name: str               # "sn_grc_doc_..."
    label: str
    scope: str              # owning scope key (or "" for out-of-scope neighbor)
    super_class: str | None = None   # parent table name (inheritance)
    is_neighbor: bool = False         # pulled in via neighbor_hops, not in area scopes
    fields: tuple[FieldDef, ...] = ()

class ReferenceEdge(BaseModel):
    from_table: str
    field: str
    to_table: str
    cross_scope: bool       # True when from/to live in different scopes

class InheritanceEdge(BaseModel):
    table: str
    extends: str            # super_class
    cross_scope: bool

class RelationshipEdge(BaseModel):
    name: str               # sys_relationship.name
    apply_to: str           # parent table (validated column name)
    query_from: str         # related table (validated column name)

class SchemaGraph(BaseModel):
    instance_id: str
    area_key: str
    discovered_at: datetime          # UTC
    scope_keys: tuple[str, ...]
    tables: tuple[TableDef, ...]
    reference_edges: tuple[ReferenceEdge, ...]
    inheritance_edges: tuple[InheritanceEdge, ...]
    relationship_edges: tuple[RelationshipEdge, ...]

    def cross_scope_edges(self) -> tuple[ReferenceEdge, ...]:
        """Reference edges that bridge two scopes (the 'how are they linked' answer)."""
```

---

## Protocol Surface

```python
# schema/protocol.py

class SchemaProtocol(Protocol):

    async def discover(
        self,
        instance_id: str,
        area_key: str,
    ) -> SchemaGraph:
        """Reverse-engineer the data dictionary for one area into a SchemaGraph.

        Args:
            instance_id: Registered instance profile name.
            area_key: Key into DEFAULT_AREAS (e.g. "doc-designer").

        Returns:
            SchemaGraph with tables, fields, and reference/inheritance/relationship edges.
        """

    def save_archive(self, graph: SchemaGraph, dest: Path | None = None) -> Path:
        """Serialize a SchemaGraph to JSON. Defaults under ~/.nexus/schema/."""

    def load_archive(self, path: Path) -> SchemaGraph:
        """Deserialize a SchemaGraph JSON snapshot.

        Raises:
            SchemaArchiveError: If the file is missing or invalid.
        """

    def render_erd(self, graph: SchemaGraph) -> str:
        """Render a SchemaGraph to a Markdown + Mermaid erDiagram document."""
```

---

## Discovery Pipeline

All calls are GET, read-only, and tolerate per-table HTTP 400/404 the same way
`ScopeDiscoverer._safe_grouped_count` already does.

```
1. Resolve scope sys_ids
   GET /api/now/table/sys_scope
     ?sysparm_query=scopeIN{sn_grc_doc_design,sn_grc_rel_config}
     &sysparm_fields=sys_id,scope,name,version
   -> {scope_key: scope_sys_id}

   All Table API cells are normalized through one helper: a reference cell is a
   dict (`{link|display_value, value}`) -> take `value`; a scalar is a bare
   string. (Default mode; no `sysparm_display_value=all`.)

2. List tables in scope
   GET /api/now/table/sys_db_object
     ?sysparm_query=sys_scopeIN{scope_sys_ids}
     &sysparm_fields=name,label,super_class,sys_scope
   -> TableDef per row. super_class.value is a sys_db_object SYS_ID; resolve it
      to a table name against the discovered set (+ a follow-up sys_idIN query
      for parents outside the scopes) -> InheritanceEdge.

3. Fetch fields + reference targets  (batched by table name IN groups)
   GET /api/now/table/sys_dictionary
     ?sysparm_query=nameIN{table_names}^elementISNOTEMPTY
     &sysparm_fields=name,element,column_label,reference,mandatory
   -> FieldDef per row. A non-empty `reference` cell marks a reference field;
      reference.value is the target table NAME directly (no resolution) ->
      ReferenceEdge. (internal_type is not needed for edge detection.)

4. Defined relationships (related lists / M2M)
   GET /api/now/table/sys_relationship
     ?sysparm_query=apply_toIN{table_names}^ORquery_fromIN{table_names}
     &sysparm_fields=name,apply_to,query_from
   -> RelationshipEdge per row. (Validated column names: `apply_to`,
      `query_from` -- both reference cells, take `.value`.)

5. Neighbor expansion (neighbor_hops)
   For each reference_target / super_class not yet a TableDef, fetch its
   sys_db_object row (label, super_class) and mark is_neighbor=True. Repeat
   neighbor_hops times. Neighbor tables get a minimal FieldDef set (skip step 3)
   to keep the graph bounded.

   -> SchemaGraph
```

Reference edges from step 3 are the core of the ERD. Inheritance edges from step
2 are what surface the BCM -> CMDB / BCM -> task bridges Luc asked about.

---

## ERD Output Format

A single Markdown file per area. Structure:

1. Title + scope/version table + "discovered_at" provenance line.
2. A narrative section (hand-written for `doc-designer`; templated for the
   others) explaining the cross-scope edges in plain language.
3. One or more Mermaid `erDiagram` blocks. For areas above ~25 tables, the
   emitter splits into one diagram per scope plus a "bridge" diagram containing
   only cross-scope edges and their endpoints, so each renders legibly on GitHub
   and in VS Code.
4. A per-table field appendix (Markdown tables): field | type | references.

Mermaid example (shape):

```
erDiagram
    TEMPLATE_CONFIG  ||--o{ CONTENT_CONFIG : "template_configuration"
    CONTENT_CONFIG   }o--|| DATA_RELATIONSHIP : "data_relationship"
    CONTENT_CONFIG   ||--o{ DATA_COLUMN : "data_relationship_mapping"
    DATA_RELATIONSHIP }o--o| DATA_REGISTRY_RELATIONSHIP : "data_registry"
    DATA_COLUMN {
      string element
      string column_label
    }
```

(Shape matches the validated edges: Content Configuration is the join between a
Template Configuration and a Data Relationship; Data columns / "Fields" hang off
a Content Configuration; Data Relationship bridges to the shared registry.)

Cardinality heuristic: a reference field is the "many" side (`}o--||`) pointing
at its target's "one" side. Mandatory references render `}o--||`; optional
render `}o--o|`.

---

## SchemaCartographer (engine)

```python
# schema/engine.py

class SchemaCartographer:
    def __init__(
        self,
        client: ServiceNowClient,
        areas: Mapping[str, SchemaArea] = DEFAULT_AREAS,
        archive_root: Path | None = None,
    ) -> None:
        self._discoverer = SchemaDiscoverer(client, areas)
        self._writer = SchemaArchiveWriter(archive_root or NexusPaths.from_env().schema_dir)
        self._reader = SchemaArchiveReader()
        self._emitter = MermaidErdEmitter()
```

Constructed once in the CLI and injected. `NexusPaths` gains a `schema_dir`
property (`~/.nexus/schema/`), mirroring `archives_dir`.

---

## Error Hierarchy

```python
# schema/errors.py
# No shared NexusError base exists; each layer subclasses Exception directly
# (the capture/errors.py pattern).

class SchemaError(Exception): ...

class AreaNotFoundError(SchemaError):       # area_key not in registry
    area_key: str

class ScopeNotFoundError(SchemaError):      # a scope key absent on the instance
    scope: str
    instance_id: str

class SchemaArchiveError(SchemaError):      # JSON snapshot missing or invalid
    path: Path
```

Resilience: an absent scope is non-fatal -- the discoverer logs WARNING, drops
that scope, and continues (a PDI may lack one plugin). An area with zero
resolvable scopes raises `ScopeNotFoundError`. Per-table dictionary read failures
are logged and skipped, never fatal.

---

## Testing Strategy

TDD, no mocks. Fakes in `tests/schema/fakes/` and the existing
`tests/fakes/fake_sn_client.py` (already satisfies `ServiceNowClientProtocol`).

- **FakeServiceNowClient**: preload `sys_scope`, `sys_db_object`,
  `sys_dictionary`, `sys_relationship` fixture rows for a small synthetic
  Document-Designer-like schema (3 tables, 1 cross-scope edge, 1 inheritance edge).
- **FakeSchemaCartographer** (implements `SchemaProtocol`): canned `SchemaGraph`
  for CLI tests, zero SN dependency.
- **MermaidErdEmitter**: assert the rendered Mermaid parses to the expected
  edges by parsing the emitted text back into edge tuples (not raw string
  compare); assert the split-diagram threshold and the cross-scope bridge block.

Representative names:

```
test_discover_resolves_scope_sys_ids
test_discover_builds_reference_edge_from_dictionary
test_discover_marks_cross_scope_edge
test_discover_inheritance_edge_bridges_scope
test_discover_missing_scope_warns_and_continues
test_discover_neighbor_expansion_bounded_by_hops

test_erd_emitter_reference_edge_renders_many_to_one
test_erd_emitter_optional_reference_renders_optional_cardinality
test_erd_emitter_splits_large_area_into_per_scope_diagrams
test_erd_emitter_bridge_block_contains_only_cross_scope_edges

test_schema_archive_roundtrip_preserves_graph
test_schema_archive_missing_file_raises_archive_error
```

Full enforcement per CLAUDE.md: 100% line coverage, mypy + pyright strict 0
errors, ruff 0, ratchet held, file headers, `__all__`, frozen Pydantic, no
`# type: ignore`, absolute imports. `/primer sync` after the epic.

---

## CLI Command Surface

```
nexus schema areas
    -- list registered areas (key | display | scopes)

nexus schema discover <area> [--profile alectri]
    -- reverse-engineer the area, write JSON snapshot to ~/.nexus/schema/
    -- output: progress per scope/table, summary (tables, edges, cross-scope edges)

nexus schema erd <area> [--profile alectri] [-o <path.md>] [--from-archive <json>]
    -- render the ERD Markdown (discovers fresh, or re-renders a saved snapshot)
    -- default output: docs/erd/<area>-<instance>.md

nexus schema list
    -- list local schema snapshots (instance | area | timestamp | tables | path)
```

All subcommands bind to `SchemaProtocol`. Typer + progress-callback shape mirrors
`nexus capture`.

---

## The Deliverable for Luc

Running `nexus schema erd doc-designer --profile alectri` produces a Markdown
ERD whose edge block is the literal answer to the P2 -- and the validated wiring
gives a cleaner answer than the customer's hypothesis:

- **Content Configuration is the join.** It references both a Template
  Configuration (`template_configuration`) and a Data Relationship
  (`data_relationship`). This confirms Luc's hunch that Content Configuration and
  Data Relationships are coupled -- a Content Configuration selects a Data
  Relationship to drive a repeating content block, and attaches it to a template.
- **Fields are not standalone.** Data columns ("Fields") reference a Content
  Configuration (`data_relationship_mapping`), so they live *inside* a Content
  Configuration, not independently. This **corrects** Luc's assumption that Fields
  could be used without the other two: the real model is a three-level hierarchy
  Template -> Content Configuration [-> Data Relationship] -> Fields.
- **Data Relationships reach outward** to the shared `sn_data_registry_relationship`
  (the 360 Template Relationship Registry the support agent referenced).

On top of the generated ERD I write a short narrative -- the "how/why" the docs
omit -- which becomes the case reply. `nexus schema erd bcm` and
`nexus schema erd cmdb-bcm` produce the reusable "mind map" artifacts that replace
his community-blog screenshot, with the CMDB bridge surfaced via the validated
`sn_bcp_recovery_task.configuration_item -> cmdb_ci` reference and the
`sn_bcp_plan_task extends task` inheritance edge.

One narrative-step confirmation (not a code dependency): verify the UI "Fields"
tab maps to the `sn_grc_doc_design_data_column` table (vs. direct template
fields) before wording the case reply. The ERD itself is correct regardless.

---

## Deferred Work (fast-follow, not in v1)

- **Config-trace**: pick a real OOB Document Designer template config and walk its
  actual records (Template -> Fields -> Data Relationships -> Content Config),
  emitting an annotated worked example. Concrete record-level proof on top of the
  schema-level ERD. New discoverer mode + models; separate story.
- **Diff mode**: `nexus schema diff <area> <snapshotA> <snapshotB>` to track schema
  drift across releases.
- **Additional areas**: CSM, ITSM, HRSD table groups -- one `SchemaArea` each.

---

## Open Questions (non-blocking)

1. **Mermaid scale.** The validated target scopes are small (doc-designer ~14
   tables, BCM/BCP ~36), so the ~25-table split threshold is enough for v1. For
   future large areas the emitter may need a "core tables only" filter (tables
   that are reference targets of >= 2 others). Non-blocking for the seeded areas.
2. **Neighbor field depth.** Neighbor tables skip field fetch (step 3) to stay
   bounded; if the appendix needs neighbor fields, add a `--deep-neighbors` flag.
```

