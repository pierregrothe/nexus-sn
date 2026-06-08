# NEXUS -- Schema Mindmap (AI-enriched table catalog) Design

Date: 2026-06-08
Author: Pierre Grothe

## Overview

A second output mode for the `nexus.schema` layer: `nexus schema mindmap <area>`.
Where `nexus schema erd` answers "how are these tables related" (reference
edges, cardinality), the mindmap answers "which table stores what" -- a
business-domain-grouped catalog with a plain-English "Stores X" description per
table, rendered as a Mermaid `mindmap` plus a grouped Markdown list.

Driver: case CS9240769 (RONA). The customer's reference artifact is a community
blog mind map of the BCM tables (grouped Core / Planning / Approvals / Exercise
/ Impact Analysis, each table with a one-line purpose). The ERD is the technical
answer to his Document Designer question; the mindmap is the always-current,
any-product equivalent of the blog screenshot he works from daily.

### What the schema cannot supply (validated 2026-06-08)

A live probe of `sys_documentation` for GRC tables found table-level rows carry
only `label` / `plural` (e.g. "Content configuration") -- **no purpose text** --
and only 7 of 75 field rows had any hint text. ServiceNow does not ship the
"Stores X" descriptions the blog has; its author wrote them. Therefore:

- **Descriptions are AI-generated**, grounded on each table's real columns
  (already captured by `SchemaDiscoverer`: field names, labels, reference
  targets) plus the sparse `sys_documentation` field hints where present. The
  AI infers purpose from actual structure -- grounded, not invented.
- **Domain clustering is AI-driven** (approach A): the same batched call assigns
  every table to a named business domain. Reproduces the blog's semantic
  grouping for any product with zero per-area configuration.

---

## Layer Position

Extends the existing layer-5 `nexus.schema` package. New dependency: the `api`
layer's `AgentClientProtocol` (Claude via claude-agent-sdk). Enrichment reads
`sys_documentation` through the existing `ServiceNowClient`. All discovery reuses
the existing `SchemaDiscoverer` unchanged.

```
connectors (ServiceNowClient) + api (AgentClient)
      -> schema.SchemaDiscoverer  (existing, unchanged)
      -> schema.TableEnricher     (new; sys_documentation + AgentClient)
      -> schema.MindmapEmitter    (new; catalog -> Markdown)
      -> schema.SchemaCartographer.build_mindmap / render_mindmap (new methods)
      -> cli: nexus schema mindmap
```

---

## Module Layout

```
src/nexus/schema/
  catalog.py          -- new: TableDescription, Domain, MindmapCatalog (frozen Pydantic)
  enricher.py         -- new: TableEnricher (sys_documentation fetch + AI clustering/describe)
  mindmap_emitter.py  -- new: MindmapEmitter (MindmapCatalog -> Markdown)
  engine.py           -- modify: SchemaCartographer gains agent_client + build_mindmap/render_mindmap
  protocol.py         -- modify: SchemaProtocol gains build_mindmap/render_mindmap
  __init__.py         -- modify: export MindmapCatalog

src/nexus/cli/
  commands_schema.py  -- modify: add `nexus schema mindmap` command
  views.py            -- modify: _build_schema_cartographer also constructs AgentClient()

tests/schema/
  test_table_enricher_*.py
  test_mindmap_emitter_*.py
  test_schema_mindmap_engine.py
  test_schema_cartographer.py        -- modify: 3 existing ctor sites pass FakeAgentClient
  fakes/fake_schema_cartographer.py  -- modify: implement build_mindmap/render_mindmap
tests/cli/
  test_commands_schema.py  -- add mindmap command test
```

Adding a required `agent_client` to `SchemaCartographer.__init__` changes its
construction contract. Per the no-backward-compat rule, every call site is
updated in one pass (no optional shim): the CLI builder, the 3 existing engine
tests, and `FakeSchemaCartographer` (which must also satisfy the two new
`SchemaProtocol` methods).

---

## Data Models (catalog.py)

All frozen: `ConfigDict(frozen=True, strict=True, extra="forbid")`.

```python
class TableDescription(BaseModel):
    table: str            # "sn_bcp_plan"
    label: str            # "Plan" (from the schema)
    description: str      # AI "Stores X" one-liner
    source: str           # "ai" (reserved for future "doc")

class Domain(BaseModel):
    name: str             # AI-assigned, e.g. "Plan Management"
    tables: tuple[TableDescription, ...]

class MindmapCatalog(BaseModel):
    instance_id: str
    area_key: str
    generated_at: datetime           # UTC
    display: str                     # area display name, mindmap root label
    domains: tuple[Domain, ...]
```

---

## TableEnricher (enricher.py)

```python
class TableEnricher:
    def __init__(self, client: ServiceNowClientProtocol, agent_client: AgentClientProtocol) -> None: ...
    async def enrich(self, graph: SchemaGraph, *, display: str) -> MindmapCatalog: ...
```

Algorithm:

1. **In-scope tables** = `[t for t in graph.tables if not t.is_neighbor]`.
2. **Field hints** (grounding): one batched query
   `sys_documentation?nameIN{tables}^elementISNOTEMPTY^hintISNOTEMPTY`
   -> `{(table, element): hint}`. Sparse; tolerated empty.
3. **Build the prompt** -- a compact, deterministic description of every table:
   name, label, scope, and its fields (element, column_label, reference_target,
   plus any hint). Ask Claude to return ONLY JSON of the shape:
   ```json
   {"domains": [{"name": "...", "tables": [{"table": "...", "description": "..."}]}]}
   ```
   System prompt fixes the contract: cluster ALL tables into business domains
   named like a ServiceNow architect would; one-line "Stores X" per table
   grounded in the listed columns; never invent tables; output JSON only.
4. **One `agent_client.complete(prompt, system=...)` call** for the whole area.
5. **Parse**: extract the JSON object from the response (first `{` .. matching
   last `}`), `json.loads`, then map onto `MindmapCatalog` (joining the AI's
   per-table description back to the discovered `label`). `source="ai"`.
6. **Resilience fallback**: if the call raises (`AnthropicError`) or the JSON is
   missing / unparseable / fails validation, log a WARNING and build a fallback
   catalog -- one `Domain` per scope key, each table described by its label.
   The command never hard-fails on AI issues.

Non-determinism is contained here: production descriptions vary run-to-run
(acceptable for prose); tests inject `FakeAgentClient(canned_response=<json>)`.

---

## MindmapEmitter (mindmap_emitter.py)

`render(catalog: MindmapCatalog) -> str` produces one Markdown document:

1. Title + provenance (`instance`, `area`, `generated_at`).
2. A Mermaid `mindmap` block: `root((<display>))`, one branch per domain, one
   leaf per table labelled `"<label> -- <table>"`.
3. A grouped catalog (the blog's content): per domain a `## <name>` heading, then
   one bullet per table: `**<label>** [<table>]: <description>`.

Example shape:

```
mindmap
  root((Business Continuity Management))
    Plan Management
      Plan -- sn_bcp_plan
      Plan task -- sn_bcp_plan_task
    Impact Analysis
      Impact analysis -- sn_bia_analysis
```

---

## SchemaCartographer changes (engine.py)

`__init__` gains a required keyword-only `agent_client: AgentClientProtocol`
(constructed once; unused by the ERD paths, which is free). Two methods:

```python
async def build_mindmap(self, instance_id: str, area_key: str) -> MindmapCatalog:
    graph = await self._discoverer.discover(instance_id, area_key)
    return await self._enricher.enrich(graph, display=self._areas[area_key].display)

def render_mindmap(self, catalog: MindmapCatalog) -> str:
    return self._mindmap_emitter.render(catalog)
```

`SchemaProtocol` gains both signatures. `_build_schema_cartographer` in
`cli/views.py` constructs `AgentClient()` (no args; SDK handles auth) and passes
it. v1 does not cache the catalog -- one batched AI call per `mindmap`
invocation is cheap; disk caching/diff is a noted fast-follow.

---

## CLI

```
nexus schema mindmap <area> [--profile alectri] [-o <path.md>]
    -- discover -> AI enrich -> render the Markdown mindmap.
    -- default output: docs/mindmaps/<area>-<instance>.md
```

Mirrors `nexus schema erd` (Typer + nexus_progress + asyncio.run). The progress
line notes the AI step ("Describing N tables on <instance>...").

---

## Error Handling

- AI failure / bad JSON -> fallback catalog (scope-grouped, label descriptions) +
  WARNING. Never aborts (reuses the SchemaError hierarchy only for area/scope
  errors from the discoverer).
- Empty area (no scopes) -> ScopeNotFoundError, as today.
- `sys_documentation` absent / unreadable -> empty hints; AI grounds on fields.

---

## Testing Strategy

TDD, no mocks. `FakeServiceNowClient` seeds `sys_scope`/`sys_db_object`/
`sys_dictionary`/`sys_documentation`; `FakeAgentClient(canned_response=...)`
returns a fixed JSON catalog. 100% line coverage; mypy + pyright strict 0; ruff
+ black clean.

```
test_enrich_builds_catalog_from_ai_json
test_enrich_joins_ai_description_to_discovered_label
test_enrich_includes_sys_documentation_hints_in_prompt
test_enrich_falls_back_to_scope_grouping_on_ai_error
test_enrich_falls_back_on_unparseable_json
test_mindmap_emitter_renders_mindmap_block
test_mindmap_emitter_renders_grouped_catalog
test_build_mindmap_discovers_then_enriches
test_render_mindmap_returns_markdown
test_schema_mindmap_writes_markdown_file   (CLI, injected FakeSchemaCartographer)
```

Full enforcement per CLAUDE.md (frozen Pydantic, file headers, `__all__`,
absolute imports, Google docstrings, ratchet entries, `/primer sync`).

---

## The Deliverable for Luc

`nexus schema mindmap bcm --profile alectri` regenerates his blog screenshot --
a domain-grouped BCM table catalog with current descriptions -- and
`nexus schema mindmap doc-designer` gives the same view for the product his P2 is
about, neither of which exists today. Paired with the ERDs (relationships), Luc
gets both halves: what each table stores, and how they connect.

---

## Deferred (fast-follow)

- Catalog disk caching + `nexus schema mindmap --from-archive` for free re-renders.
- `source="doc"` tagging if a future SN release ships table-purpose text.
- Mermaid mindmap split for very large areas (BCM ~36 tables renders fine).

---

## Open Questions (non-blocking)

1. **JSON extraction robustness.** Claude is instructed to emit JSON only; the
   parser still strips to the outermost `{...}` to tolerate stray prose. If a
   model wraps JSON in a ```json fence, the strip handles it.
2. **Model choice.** Default (let the SDK pick) for v1; a `--model` flag is a
   trivial later add if a cheaper/faster tier suffices for description work.
