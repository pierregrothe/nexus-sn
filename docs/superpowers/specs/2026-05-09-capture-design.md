# NEXUS -- Instance Configuration Capture Design

Date: 2026-05-09
Author: Pierre Grothe

## Overview

The `nexus.capture` layer provides bidirectional configuration transport between
ServiceNow instances: scan a live instance into a local YAML archive, and push
that archive into a target update set for deployment or migration. It is the
foundation for assessment (what is on the instance), archiving (snapshot for
audit), and deployment (copy configs between instances).

The layer exposes a single `CaptureProtocol` that CLI, TUI, and Web UI all bind
to. The concrete `CaptureEngine` is constructed once and injected wherever needed.

---

## Roadmap Position

Capture moves into the foundation tier alongside instance management. Without it,
assessment has nothing to scan, and deployment has nothing to push.

Updated build order:

```
[done]  Foundation: config, auth, capabilities, connectors, instance management,
        AgentClient, nexus status, CI/CD

[next]  nexus.capture layer  <-- this spec
        - ScopeDiscoverer + ConfigFetcher (AI/automation surface)
        - ArchiveWriter/Reader (YAML on disk)
        - UpdateSetXmlBuilder + UpdateSetWriter
        - nexus capture command (discover, pull, push, list)

[then]  nexus setup command + GitHubSync + TemplateRegistry

[then]  Assessment: RuleEngine + AssessmentReporter consuming capture output
```

---

## Layer Position

```
cache -> config -> auth -> capabilities -> api -> connectors
      -> capture                                    ^-- uses ServiceNowClient
      -> assessment   (read-only analysis of CaptureResult)
      -> execution    (reads archives, writes update sets)
      -> cli / tui / web ui (bind to CaptureProtocol only)
```

`nexus.capture` imports: `connectors` (ServiceNowClient), `config` (NexusPaths),
`cache` (decorator). It has no knowledge of assessment rules, agent orchestration,
or CLI rendering.

---

## Module Layout

```
src/nexus/capture/
  __init__.py          -- exports CaptureProtocol, CaptureEngine, models
  protocol.py          -- CaptureProtocol (structural Protocol)
  tables.py            -- TableSpec, TableGroup, AI_AUTOMATION, DEFAULT_TABLE_GROUPS
  scope.py             -- ScopeDiscoverer
  fetcher.py           -- ConfigFetcher
  models.py            -- all Pydantic models + SnRecord type alias
  archive.py           -- ArchiveWriter, ArchiveReader
  xml_builder.py       -- UpdateSetXmlBuilder
  update_set.py        -- UpdateSetWriter
  engine.py            -- CaptureEngine (implements CaptureProtocol)
  errors.py            -- CaptureError hierarchy

tests/capture/
  test_scope_discoverer_*.py
  test_config_fetcher_*.py
  test_archive_writer_*.py
  test_xml_builder_*.py
  test_update_set_writer_*.py
  fakes/
    fake_capture_engine.py   -- FakeCaptureEngine implements CaptureProtocol
```

---

## Table Manifest

The manifest is a pluggable registry of which tables belong to which configuration
group. It is not Pydantic -- it is pure frozen dataclasses so it is cheap to
construct and easy to extend.

```python
# capture/tables.py

@dataclass(slots=True, frozen=True)
class TableSpec:
    name: str                          # "ai_skill"
    display: str                       # "NowAssist Skills"
    scope_field: str = "sys_scope"     # field carrying the app scope ref
    related_tables: tuple[str, ...] = ()   # child tables pulled with parent
    key_fields: tuple[str, ...] = ("sys_id", "name", "sys_scope")

@dataclass(slots=True, frozen=True)
class TableGroup:
    key: str                           # "ai_automation"
    display: str                       # "AI & Automation"
    tables: tuple[TableSpec, ...]

AI_AUTOMATION = TableGroup(
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
            related_tables=("sys_hub_flow_input", "sys_hub_flow_logic"),
        ),
        TableSpec(
            name="sys_hub_action_type_definition",
            display="IntegrationHub Actions",
        ),
        TableSpec(
            name="virtual_agent_conversation_topic",
            display="Virtual Agent Topics",
            related_tables=("sn_va_topic_block",),
        ),
        TableSpec(
            name="sys_ai_agent",
            display="AI Agents",
            related_tables=("sys_ai_agent_capability",),
        ),
    ),
)

DEFAULT_TABLE_GROUPS: dict[str, TableGroup] = {
    AI_AUTOMATION.key: AI_AUTOMATION,
}
```

Adding a new group (e.g., `DEVELOPER_PLATFORM` with business rules, script
includes, ACLs) is one new `TableGroup` constant and one entry in
`DEFAULT_TABLE_GROUPS`. No engine changes required.

---

## Data Models

### Type aliases for raw ServiceNow data

ServiceNow REST (`sysparm_display_value=all`) returns reference fields as
`{"value": "sys_id_string", "display_value": "Human Name"}`. Plain fields
return as strings.

```python
# capture/models.py

class SnRefField(TypedDict):
    value: str
    display_value: str

type SnFieldValue = str | SnRefField
type SnRecord = dict[str, SnFieldValue]
```

No `dict[str, Any]` appears anywhere in the capture layer.

### Scope discovery

```python
class ScopeEntry(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")
    sys_id: str
    name: str                      # "NowAssist HR Service Delivery"
    scope: str                     # "x_snc_nowassist_hrsd"
    version: str
    vendor: str
    table_counts: dict[str, int]   # {"ai_skill": 3, "sys_hub_flow": 8}

class ScopeManifest(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")
    instance_id: str
    captured_at: datetime          # UTC
    scopes: tuple[ScopeEntry, ...]
```

### Config capture

```python
class ConfigRecord(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")
    sys_id: str
    table: str
    scope_sys_id: str
    scope_name: str
    captured_at: datetime          # UTC
    fields: SnRecord               # full Table API response row (display_value=all)
    parent_sys_id: str | None = None   # set for related records; None for root records

class CaptureResult(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")
    instance_id: str
    captured_at: datetime          # UTC
    scope_ids: tuple[str, ...]
    table_group: str               # "ai_automation"
    records: tuple[ConfigRecord, ...]

    def by_table(self) -> dict[str, tuple[ConfigRecord, ...]]:
        """Group records by table name."""
```

### Archive + update set

```python
class ArchiveManifest(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")
    format_version: str            # "1.0" -- for future migration
    instance_id: str
    captured_at: datetime          # UTC
    scope_ids: tuple[str, ...]
    table_group: str
    record_count: int
    archive_dir: Path

class UpdateSetRef(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")
    sys_id: str
    name: str
    state: str                     # "in progress" | "complete" | "ignore"
    record_count: int
    instance_id: str
```

---

## Protocol Surface

```python
# capture/protocol.py

class CaptureProtocol(Protocol):

    async def discover_scopes(
        self,
        instance_id: str,
        table_group: str = "ai_automation",
    ) -> ScopeManifest:
        """Discover all application scopes on the instance with record counts.

        Args:
            instance_id: Registered instance profile name.
            table_group: Which table group to count records for.

        Returns:
            ScopeManifest listing all scopes and per-table counts.
        """

    async def capture(
        self,
        instance_id: str,
        scope_ids: list[str],
        table_group: str = "ai_automation",
    ) -> CaptureResult:
        """Fetch all configurations in the given scopes from a live instance.

        Args:
            instance_id: Registered instance profile name.
            scope_ids: sys_id values of application scopes to capture.
            table_group: Which table group to scan.

        Returns:
            CaptureResult with all records. Tables returning 400/404 are skipped.
        """

    def save_archive(
        self,
        result: CaptureResult,
        dest: Path | None = None,
    ) -> ArchiveManifest:
        """Serialize a CaptureResult to YAML on disk.

        Args:
            result: The result to persist.
            dest: Root directory for the archive. Defaults to
                  ~/.nexus/archives/{instance_id}/{timestamp}/.

        Returns:
            ArchiveManifest with location and record count.
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
        """Inject all records from a CaptureResult into a target update set.

        Creates the update set if it does not exist. Reuses an in-progress
        update set with the same name if one is found.

        Args:
            result: CaptureResult to deploy (from live capture or archive).
            instance_id: Target registered instance profile.
            update_set_name: Name for the update set on the target instance.

        Returns:
            UpdateSetRef describing the created or updated update set.

        Raises:
            UpdateSetError: If any record fails to inject (fails fast).
        """
```

---

## Bidirectional Pipeline

### Capture direction (instance -> archive)

```
1. ScopeDiscoverer
   GET /api/now/table/sys_scope
     ?sysparm_fields=sys_id,name,scope,version,vendor
     &sysparm_limit=500
   For each scope x table:
   GET /api/now/stats/{table}
     ?sysparm_query=sys_scope={scope_sys_id}
     &sysparm_count=true
   -> ScopeManifest  (shown to user; user selects scope_ids)

2. ConfigFetcher  (per selected scope x TableSpec)
   GET /api/now/table/{table}
     ?sysparm_query=sys_scope={scope_id}
     &sysparm_display_value=all
     &sysparm_limit=1000
     &sysparm_offset=N        -- paginate using X-Total-Count response header
   HTTP 400/404 -> TableUnavailableError caught; zero records, continue
   For each related_table in TableSpec.related_tables:
     GET /api/now/table/{related_table}
       ?sysparm_query=parent={sys_id}^ORflow={sys_id}
       &sysparm_display_value=all
   -> list[ConfigRecord]

3. ArchiveWriter
   Creates directory: ~/.nexus/archives/{instance_id}/{YYYYMMDD-HHMMSS}/
   Writes per-record YAML: {table}/{sys_id}.yaml
   Related records nested: {parent_table}/{parent_sys_id}/{related_table}/{sys_id}.yaml
   Writes: manifest.yaml
   -> ArchiveManifest
```

### Deploy direction (archive -> update set on target instance)

```
1. ArchiveReader
   Reads manifest.yaml -> validates format_version
   Reads each {table}/{sys_id}.yaml -> ConfigRecord
   -> CaptureResult

2. UpdateSetXmlBuilder  (per ConfigRecord)
   Generates SN update set XML payload:

   <record_update table="{table}" sys_id="{sys_id}">
     <{table} action="INSERT_OR_UPDATE">
       <!-- plain string field -->
       <name>{value}</name>
       <!-- SnRefField: sys_id as text, display_value as attribute -->
       <sys_scope display_value="{scope.display_value}">{scope.value}</sys_scope>
     </{table}>
   </record_update>

   Built with xml.etree.ElementTree. Never string concatenation.

3. UpdateSetWriter
   GET /api/now/table/sys_update_set
     ?sysparm_query=name={name}^state=in progress
   If none found:
     POST /api/now/table/sys_update_set {name, state: "in progress"}
   For each ConfigRecord:
     POST /api/now/table/sys_update_xml
       {update_set: sys_id,
        name: "{table}_{record_sys_id}",
        type: "{table}",
        payload: "<record_update .../>",
        action: "INSERT_OR_UPDATE"}
   Failure on any record -> UpdateSetError (fail fast, do not partial-apply)
   -> UpdateSetRef
```

---

## Archive Format (on-disk)

```
~/.nexus/archives/
  {instance_id}/
    {YYYYMMDD-HHMMSS}/
      manifest.yaml
      ai_skill/
        {sys_id}.yaml
      sys_hub_flow/
        {sys_id}.yaml
        sys_hub_flow_logic/
          {child_sys_id}.yaml
      sys_hub_action_type_definition/
        {sys_id}.yaml
      virtual_agent_conversation_topic/
        {sys_id}.yaml
        sn_va_topic_block/
          {child_sys_id}.yaml
      sys_ai_agent/
        {sys_id}.yaml
        sys_ai_agent_capability/
          {child_sys_id}.yaml
```

`manifest.yaml` schema:

```yaml
format_version: "1.0"
instance_id: dev-instance
captured_at: "2026-05-09T14:23:00Z"
scope_ids:
  - abc123def456
table_group: ai_automation
record_count: 47
```

Each `{sys_id}.yaml` stores all fields from the Table API response as-is.
`SnRefField` values are written as a YAML mapping `{value: ..., display_value: ...}`.

---

## CaptureEngine

The concrete implementation. All internal components are constructed in `__init__`
and not exposed publicly. Callers depend only on `CaptureProtocol`.

```python
# capture/engine.py

class CaptureEngine:
    def __init__(
        self,
        client: ServiceNowClient,
        registry: InstanceRegistry,
        table_groups: Mapping[str, TableGroup] = DEFAULT_TABLE_GROUPS,
        archive_root: Path | None = None,
    ) -> None:
        self._discoverer = ScopeDiscoverer(client)
        self._fetcher = ConfigFetcher(client, table_groups)
        self._writer = ArchiveWriter(archive_root or NexusPaths().archives_dir)
        self._reader = ArchiveReader()
        self._xml = UpdateSetXmlBuilder()
        self._usw = UpdateSetWriter(client)
        self._registry = registry
```

`CaptureEngine` is instantiated once in `cli.py` and passed down via DI. The TUI
and Web UI construct it the same way.

---

## Error Hierarchy

```python
# capture/errors.py

class CaptureError(NexusError): ...

class ScopeNotFoundError(CaptureError):    # requested scope absent on instance
    scope_id: str
    instance_id: str

class TableUnavailableError(CaptureError): # HTTP 400/404 on table (e.g. PDI)
    table: str
    instance_id: str

class ArchiveCorruptError(CaptureError):   # manifest missing or YAML invalid
    archive_dir: Path

class UpdateSetError(CaptureError):        # injection failure on target
    update_set_name: str
    instance_id: str
    failed_record_sys_id: str
    failed_table: str
```

Resilience contract:
- `TableUnavailableError` is non-fatal during `capture()`. The fetcher logs
  WARNING, records zero entries, continues. Matches the existing
  `InstanceScanner` resilience pattern.
- `ScopeNotFoundError` is fatal -- stops capture immediately.
- `UpdateSetError` is fatal -- partial update set injection is not recoverable,
  so the writer fails fast rather than leaving the target in an unknown state.

---

## Testing Strategy

Three fake boundaries. All fakes live in `tests/capture/fakes/`.

**FakeServiceNowClient** (extends existing `tests/fakes/fake_sn_client.py`):
Adds scope and aggregate responses. Preloaded with fixture data per test.

**FakeCaptureEngine** (new, implements `CaptureProtocol`):
Used by CLI and TUI tests to avoid any SN dependency. Returns canned
`ScopeManifest`, `CaptureResult`, `ArchiveManifest`, `UpdateSetRef`.

**`tmp_path` for ArchiveWriter/Reader tests**:
Real YAML writes to pytest's temporary directory. No mocking of file I/O.

Test naming follows project convention (`test_<function>_<scenario>`):

```
test_discover_scopes_returns_manifest_with_counts
test_discover_scopes_with_empty_instance_returns_empty_manifest
test_discover_scopes_unavailable_table_excluded_from_counts

test_fetch_records_paginates_large_result_set
test_fetch_records_unavailable_table_returns_empty_records
test_fetch_records_includes_related_tables_for_parent

test_archive_writer_writes_manifest_and_per_record_yaml
test_archive_reader_roundtrip_preserves_all_fields
test_archive_reader_corrupt_manifest_raises_archive_corrupt_error

test_xml_builder_plain_string_field_produces_text_element
test_xml_builder_ref_field_includes_display_value_attribute
test_xml_builder_output_parses_as_valid_xml

test_update_set_writer_creates_set_when_not_found
test_update_set_writer_reuses_existing_in_progress_set
test_update_set_writer_partial_failure_raises_update_set_error
```

`xml_builder` tests assert structure via `xml.etree.ElementTree.fromstring()`.
Never string comparison or regex on XML output.

---

## CLI Command Surface

```
nexus capture discover <instance>
    -- discover all application scopes, display with per-table counts
    -- output: table of scope name | scope key | ai_skill | sys_hub_flow | ...

nexus capture pull <instance> --scope <name_or_sys_id> [--scope ...] [--group ai_automation]
    -- fetch configs for selected scopes, write archive to ~/.nexus/archives/
    -- output: progress bar per table, summary with archive path

nexus capture list [<instance>]
    -- list local archives (all instances or one)
    -- output: table of instance | timestamp | scopes | record count | path

nexus capture push <archive_path> <target_instance> [--update-set <name>]
    -- inject archive into a new or existing update set on target
    -- output: progress per record, UpdateSetRef summary
```

All four subcommands bind to `CaptureProtocol`. The TUI and Web UI expose the
same four operations through their own presentation layers.

---

## Open Questions (non-blocking)

1. **Related table parent field varies by table.** `sys_hub_flow_logic` uses
   `flow`; others may use `parent` or a custom field. The `TableSpec` may need
   a `related_field: str = "parent"` attribute to specify the join field per
   related table.

2. **Large flow XML payloads.** `sys_hub_flow_logic` records for complex flows
   can be several hundred KB of XML stored in a `conditions` or `script` field.
   Pagination and timeout values for the fetcher may need tuning.

3. **Update set scope assignment.** When creating `sys_update_set`, the
   `application` field should match the captured scope. For multi-scope captures,
   one update set per scope or one combined set is a deployment decision deferred
   to the `push` command options.
