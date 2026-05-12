# Plugin Advisories Design

Date: 2026-05-11
Status: approved, ready for implementation plan
Sub-project D1 of the plugin management roadmap.

## Goal

Surface health and risk findings on a captured plugin inventory by
checking each plugin against three curated advisory data sources:
end-of-life status, known CVEs, and a vendor license policy. Emit
findings through a single CLI command (`nexus plugins advisories`)
with optional filters for advisory type and severity.

This is the first slice of the larger "Health and Risk" sub-project (D).
The remaining slices -- impact analysis (D2) and orphan + drift
detection (D3) -- are deferred to separate specs.

## Non-goals

- **Auto-remediation.** NEXUS does not deactivate, update, or replace
  plugins based on findings. Findings are informational.
- **Live advisory feeds.** No network calls to NVD, Snyk, SN Security
  Advisories, or any external service. v1 ships with curated YAML data
  refreshed when NEXUS itself is upgraded.
- **License-model traversal.** SN's `sys_store_app.license_model`
  is a sys_id reference; resolving it requires per-plugin REST calls
  and yields unreliable strings. v1 uses vendor name as the license
  signal because that is the actually-queryable field.
- **CI gating.** v1 always exits 0. A `--strict` flag for CI
  integration is a deferred follow-up.
- **Editing the curated data files.** Users update the lists by
  upgrading the `nexus-sn` package. User-managed overrides may follow
  in a later sub-project if demand warrants.

## Architecture

### Layer placement

Inside the existing `nexus.plugins` layer. No new layer, no upward
imports. `advisories.py` imports only from `nexus.plugins.models`,
stdlib, `packaging.specifiers`, and `yaml`.

```
src/nexus/plugins/advisories.py             -- NEW: loaders + compute_advisories()
src/nexus/plugins/data/eol.yaml             -- NEW: curated EOL list
src/nexus/plugins/data/cves.yaml            -- NEW: curated CVE list
src/nexus/plugins/data/licenses.yaml        -- NEW: vendor allow/forbid policy
src/nexus/plugins/models.py                 -- MODIFY: add vendor field +
                                               AdvisoryFinding / AdvisorySet /
                                               Severity / AdvisoryType
src/nexus/plugins/scanner.py                -- MODIFY: populate vendor from
                                               sys_store_app row
src/nexus/plugins/errors.py                 -- MODIFY: add PluginAdvisoryDataError
src/nexus/plugins/__init__.py               -- MODIFY: re-export new symbols
src/nexus/cli.py                            -- MODIFY: add `advisories` subcommand
```

### Data shapes

The three bundled YAML files use the shapes below.

**`src/nexus/plugins/data/eol.yaml`** -- top-level list:

```yaml
- plugin_id: com.acme.legacy
  status: end_of_life        # end_of_life | deprecated
  effective: 2024-12-31      # ISO date
  replacement: com.acme.modern   # optional
  notes: Replaced by com.acme.modern
```

**`src/nexus/plugins/data/cves.yaml`** -- top-level list:

```yaml
- cve_id: CVE-2024-1234
  plugin_id: com.snc.cms
  severity: high             # critical | high | medium | low
  affected_versions: ">=1.0,<2.2.1"   # PEP 440 SpecifierSet syntax
  fixed_in: "2.2.1"
  summary: XSS in CMS portal
```

**`src/nexus/plugins/data/licenses.yaml`** -- top-level dict:

```yaml
allowed_vendors:
  - ServiceNow
  - Service-now.com
forbidden_vendors:
  - Sketchy Vendor LLC
```

All three files SHIP populated with a conservative initial dataset that
the test suite exercises. The initial dataset will be a token sample
(approximately 5 entries each); the data files are expected to grow
over time as NEXUS maintainers track ServiceNow security advisories
and EOL announcements.

### Pydantic models (added to `models.py`)

```python
class Severity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class AdvisoryType(StrEnum):
    EOL = "eol"
    CVE = "cve"
    LICENSE = "license"


class AdvisoryFinding(BaseModel):
    """One advisory hit on one plugin."""

    model_config = _FROZEN

    plugin_id: str
    plugin_name: str
    plugin_version: str
    advisory_type: AdvisoryType
    severity: Severity
    summary: str       # one-line headline shown in table
    details: str       # CVE id / EOL date / vendor name


class AdvisorySet(BaseModel):
    """All findings produced by one advisory scan."""

    model_config = _FROZEN

    findings: tuple[AdvisoryFinding, ...]
```

`_FROZEN` is the existing module-level `ConfigDict(frozen=True,
strict=True, extra="forbid")` already used by `PluginInfo` /
`PluginInventory`.

### PluginInfo extension

Add one field with a backwards-compatible default:

```python
class PluginInfo(BaseModel):
    ...existing fields...
    vendor: str = ""        # NEW. "" means unknown (e.g. v_plugin-only).
```

Default of `""` keeps existing `plugins.json` snapshots from
sub-projects A/B/C loadable without re-capture. The license checker
treats `""` as "no signal" and emits no finding -- empty vendor is a
data absence, not a policy violation (see severity rules below).

### Scanner change

In `src/nexus/plugins/scanner.py::_from_store`:

```python
return PluginInfo(
    ...existing fields...,
    vendor=vendor,         # already in scope: vendor = str(row.get("vendor", ""))
    latest_version=str(row.get("latest_version", "")) or None,
)
```

`_from_v_plugin` leaves `vendor` at the `""` default; the v_plugin
table does not expose a vendor field.

### compute_advisories pure function

`src/nexus/plugins/advisories.py`:

```python
def compute_advisories(
    inventory: PluginInventory,
    db: AdvisoryDatabase,
) -> AdvisorySet:
    """Cross-check inventory against three curated advisory tables.

    Args:
        inventory: Plugin inventory captured by sub-project A.
        db: Pre-loaded advisory database.

    Returns:
        AdvisorySet sorted by (severity desc, plugin_id asc).
    """
    findings: list[AdvisoryFinding] = []
    for plugin in inventory.plugins:
        findings.extend(_check_eol(plugin, db.eol))
        findings.extend(_check_cves(plugin, db.cves))
        findings.extend(_check_license(plugin, db.licenses))
    findings.sort(key=lambda f: (_SEV_ORDER[f.severity], f.plugin_id))
    return AdvisorySet(findings=tuple(findings))
```

`_SEV_ORDER` is `{CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3}`.

### Severity derivation rules

| Source | Condition | Severity |
|---|---|---|
| EOL | `effective` is in the past | `high` |
| EOL | `effective` is in the future, `status == end_of_life` | `medium` |
| EOL | `status == deprecated` (regardless of date) | `medium` |
| CVE | Plugin version inside `affected_versions` SpecifierSet | copied verbatim from YAML |
| License | Vendor empty (no signal) | (no finding) |
| License | Vendor in `forbidden_vendors` | `high` |
| License | Vendor in `allowed_vendors` | (no finding) |
| License | Vendor non-empty, absent from both lists, allow-list non-empty | `medium` |
| License | Vendor non-empty, absent from both lists, allow-list empty | (no finding) |

"Past" is computed against `datetime.now(UTC).date()` at command-entry
time. The EOL table itself uses naive ISO dates because the EOL event
is calendar-day granularity, not instant granularity.

### AdvisoryDatabase loader

```python
class AdvisoryDatabase(BaseModel):
    """Loaded contents of the three bundled YAML files."""

    model_config = _FROZEN

    eol: tuple[EolEntry, ...]
    cves: tuple[CveEntry, ...]
    licenses: LicensePolicy

    @classmethod
    def load(cls) -> "AdvisoryDatabase":
        """Read the three YAMLs bundled with the package.

        Returns:
            Parsed AdvisoryDatabase ready for compute_advisories().

        Raises:
            PluginAdvisoryDataError: If any file is missing, malformed,
                or fails schema validation. Wraps the underlying
                yaml/Pydantic/Specifier error.
        """
```

`EolEntry`, `CveEntry`, `LicensePolicy` are private Pydantic models
in `advisories.py` (frozen, strict, extra forbidden). `CveEntry`
validates that `affected_versions` parses as a `SpecifierSet` at load
time; the parsed object is stored on the model via a computed property
so per-call re-parsing is avoided.

YAML is read via `importlib.resources.files("nexus.plugins.data")`,
matching how `product_families.yaml` is loaded today.

### CLI surface

```
nexus plugins advisories [--instance PROFILE]
                         [--type eol|cve|license]
                         [--severity critical|high|medium|low]
```

- `--instance` resolves the profile (same as B/C).
- `--type` filters to one advisory type. Default empty string = all.
- `--severity` filters to findings at or above the given severity
  (critical > high > medium > low). Default empty string = all.
- Exit code: always 0 in v1.

Behaviour:

- Empty inventory or unknown profile -> `Notice.warn` / `Notice.error`
  + appropriate Hint + `typer.Exit(1)` (mirrors B/C).
- Data files corrupted -> `Notice.error("Advisory data corrupted:
  <reason>")` + `typer.Exit(1)`.
- Zero findings after filtering -> `Notice.info("No advisories
  found.")` and return.
- One or more findings:
  - Render one `DataTable` per non-empty type, in the order EOL ->
    CVE -> License. Each table sorted by (severity desc, plugin_id
    asc).
  - Trailing `Notice.info` shows the total count and per-severity
    breakdown: `f"{n} advisory finding(s): {critical} critical,
    {high} high, {medium} medium, {low} low."`

DataTable columns per type:

| Type | Columns |
|---|---|
| EOL | Plugin ID, Name, Version, Severity, Effective, Replacement |
| CVE | Plugin ID, Name, Version, CVE, Severity, Fixed in, Summary |
| License | Plugin ID, Name, Version, Vendor, Severity |

### Reuse from existing layers

- `PluginInventory` / `PluginInfo` -- consumed unchanged structurally.
- `InstanceRegistry.load_plugin_inventory` -- single read per profile.
- `_resolve_profile`, `_load_inventory_or_exit` -- existing helpers in
  `cli.py` from sub-project B; reused.
- `DataTable`, `DataColumn`, `Notice` -- already exported from
  `nexus.ui`.
- `packaging.specifiers.SpecifierSet`, `packaging.version.parse` --
  already transitive deps from sub-project B.
- `yaml.safe_load` -- already used by `product_families.py`.

### Errors / edge cases

- **Unknown profile:** `InstanceNotFoundError` caught by
  `_resolve_profile`, surfaced as `Notice.error` + `typer.Exit(1)`.
- **Missing inventory:** `Notice.warn` + Hint + exit 1.
- **Data file missing or malformed:** `PluginAdvisoryDataError` ->
  `Notice.error` + exit 1.
- **Malformed CVE SpecifierSet in YAML:** caught at load time via
  Pydantic `@field_validator`; wrapped in `PluginAdvisoryDataError`.
- **Plugin version unparseable for CVE check:** `packaging.version.
  InvalidVersion` is caught in `_check_cves`; that plugin/CVE pair is
  skipped with a DEBUG log; no finding emitted. Other CVE entries for
  the same plugin are still evaluated.
- **`--severity` flag with no matching findings:** filter yields zero
  -> "No advisories found." message.
- **`--type` flag combined with `--severity`:** both applied; same
  zero-finding behavior.

## Testing strategy

All tests use real fakes (project no-mocks rule). Test names follow
`test_<function>_<scenario>`. Every test file gets the required
4-line header.

### `tests/test_plugins_advisories.py` (new)

EOL checker:
- `test_check_eol_flags_past_effective_date_as_high`
- `test_check_eol_flags_future_effective_date_as_medium`
- `test_check_eol_flags_deprecated_as_medium`
- `test_check_eol_returns_empty_when_plugin_absent_from_table`

CVE checker:
- `test_check_cves_flags_matching_version_in_range`
- `test_check_cves_skips_version_above_range`
- `test_check_cves_skips_version_below_range`
- `test_check_cves_returns_multiple_findings_for_multiple_cves`
- `test_check_cves_skips_unparseable_plugin_version`

License checker:
- `test_check_license_flags_forbidden_vendor_as_high`
- `test_check_license_flags_unknown_vendor_as_medium`
- `test_check_license_skips_allowed_vendor`
- `test_check_license_skips_empty_vendor_when_allow_list_empty`

Database loader:
- `test_load_database_reads_three_bundled_yamls`
- `test_load_database_raises_on_malformed_yaml`
- `test_load_database_raises_on_invalid_cve_specifier`

Orchestrator:
- `test_compute_advisories_returns_empty_set_when_no_findings`
- `test_compute_advisories_aggregates_all_three_checker_outputs`
- `test_compute_advisories_sorts_findings_by_severity_then_plugin_id`

### `tests/test_plugins_models.py` (append)

- `test_advisory_finding_accepts_all_required_fields`
- `test_advisory_set_is_frozen`
- `test_plugin_info_accepts_vendor_field`
- `test_plugin_info_defaults_vendor_to_empty_string`

### `tests/test_plugins_scanner.py` (append)

- `test_scan_populates_vendor_from_store_row`
- `test_scan_leaves_vendor_empty_for_v_plugin_only_record`

### `tests/test_cli_plugins_advisories.py` (new)

- `test_advisories_renders_three_sections_when_findings_in_each`
- `test_advisories_prints_no_findings_when_clean`
- `test_advisories_filters_by_type_when_type_flag_provided`
- `test_advisories_filters_by_severity_when_severity_flag_provided`
- `test_advisories_renders_per_severity_counts_in_trailing_notice`
- `test_advisories_warns_when_inventory_missing`
- `test_advisories_errors_when_data_files_corrupted`

### Test fakes

`tests/fakes/fake_plugin_data.py` gets a `vendor` populated on one
store row.

New `tests/fakes/fake_advisory_data.py` exposes in-memory
`AdvisoryDatabase` factories so unit tests bypass the YAML loader.

## File layout

New files:

```
src/nexus/plugins/advisories.py
src/nexus/plugins/data/eol.yaml
src/nexus/plugins/data/cves.yaml
src/nexus/plugins/data/licenses.yaml
tests/test_plugins_advisories.py
tests/test_cli_plugins_advisories.py
tests/fakes/fake_advisory_data.py
```

Modified files:

```
src/nexus/plugins/models.py            -- add vendor field to PluginInfo;
                                          add AdvisoryFinding, AdvisorySet,
                                          Severity, AdvisoryType
src/nexus/plugins/scanner.py           -- populate vendor from sys_store_app
src/nexus/plugins/errors.py            -- add PluginAdvisoryDataError
src/nexus/plugins/__init__.py          -- re-export new symbols
src/nexus/cli.py                       -- add `advisories` subcommand;
                                          update _PLUGINS_HELP
tests/fakes/fake_plugin_data.py        -- add vendor to one store row
tests/test_plugins_models.py           -- 4 new tests
tests/test_plugins_scanner.py          -- 2 new tests
pyproject.toml                         -- add `pluginmgmt-data` package include
.ratchet.json                          -- new module baselines + cli.py bump
```

## Risks

- **Curated data drifts from reality.** The CVE list and EOL list
  reflect what NEXUS maintainers know on the day they cut a release.
  Stale data is the dominant failure mode. Mitigation: ship a small
  initial dataset, document the update cadence in CONTRIBUTING, and
  add the per-instance override path in a later sub-project if user
  demand materializes.
- **Vendor strings vary in SN.** "ServiceNow" vs "Service-now.com" vs
  "servicenow" are all observed. The allow-list explicitly includes
  all known variants; the `_check_license` function does
  case-sensitive exact match on the trimmed vendor string (no
  normalization). False positives surface as "unknown vendor" medium
  findings, which is the desired conservative behavior.
- **`affected_versions` SpecifierSet authoring errors.** A typo in a
  YAML entry breaks `AdvisoryDatabase.load()` and renders the entire
  command non-functional. Mitigation: schema-validate at load time so
  the failure is immediate; tests cover the load-failure path.
- **Adding `vendor` to PluginInfo requires re-running `nexus instance
  refresh`** for the field to populate from existing snapshots. The
  default of `""` keeps old snapshots loadable. Behaviour for unrefreshed
  snapshots: vendor is empty everywhere, so license findings degrade
  gracefully to "no findings" rather than firing false positives.

## Out of scope (deferred)

- **Live advisory sync.** Out of scope; v1 ships curated YAMLs only.
- **CI gating / `--strict` flag.** Out of scope; v1 always exits 0.
- **User-managed override files.** Out of scope; user updates via
  package upgrade.
- **License-model traversal.** Vendor name is the v1 signal; chasing
  `license_model` sys_ids is unreliable and N+1-heavy.
- **JSON output.** Out of scope; the Rich-rendered tables are the v1
  surface. A `--format json` flag may follow if scripting demand
  materializes.

## Open questions

None remain after the brainstorm. CLI shape (single subcommand +
filters), data file shape (three bundled YAMLs), CVE matching
(PEP 440 SpecifierSet), license policy shape (allow/forbid vendor
lists with unknown=medium), and severity derivation rules were all
resolved before this spec was written.
