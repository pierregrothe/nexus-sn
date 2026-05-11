# Plugin Diff and Promote Design

Date: 2026-05-11
Status: approved, ready for implementation plan
Sub-project B of the plugin management roadmap (features B1 + B2; B3 deferred to D).

## Goal

Add two read-only cross-instance commands to NEXUS:

- `nexus plugins diff <a> <b>` -- side-by-side comparison of the plugin
  inventory between two registered instances.
- `nexus plugins promote <src> --to <dst>` -- generate an additive YAML
  action plan that, when followed manually in ServiceNow, brings ``dst``
  up to ``src``.

Both commands consume the ``plugins.json`` files produced by sub-project A
(``nexus instance refresh``). Neither command writes anything to a SN
instance -- promote is a documentation artifact, not an executable script.

## Non-goals

- Pre-deactivation impact analysis (feature B3). Moved to sub-project D
  (Health & Risk), where it joins the orphan / CVE / license checks that
  share the artifact-vs-plugin cross-reference machinery.
- Executing the promotion plan. ServiceNow does not expose a REST endpoint
  to activate or upgrade core plugins; the YAML is read by a human admin.
- Symmetric or three-way diff across more than two instances.
- Deactivation or downgrade actions in promote. ``promote`` is additive
  only (install + activate + upgrade); destructive actions show up in
  ``diff`` but are deliberately excluded from the action plan.

## Architecture

### Layer placement

One new file in the existing ``src/nexus/plugins/`` layer:

```
src/nexus/plugins/
  diff.py                  -- pure-function logic + Pydantic data shapes
                              for cross-instance comparison
```

No new layer; no upward imports.

### Pydantic models in ``diff.py``

```python
class PluginDiffEntry(BaseModel):
    """One row of a cross-instance plugin diff.

    Attributes:
        plugin_id: Canonical SN plugin identifier.
        name: Display name (from whichever inventory had the entry).
        product_family: Curated product family or ``Uncategorized``.
        status: Why this row appears in the diff.
        a_version: Version on instance A, or ``None`` if only_in_b.
        b_version: Version on instance B, or ``None`` if only_in_a.
        a_state: State on A, or ``None`` if only_in_b.
        b_state: State on B, or ``None`` if only_in_a.
    """
    model_config = _FROZEN

    plugin_id: str
    name: str
    product_family: str
    status: Literal[
        "only_in_a", "only_in_b", "version_mismatch", "state_mismatch"
    ]
    a_version: str | None
    b_version: str | None
    a_state: Literal["active", "inactive"] | None
    b_state: Literal["active", "inactive"] | None


class PluginDiff(BaseModel):
    """Full diff of two plugin inventories.

    Attributes:
        profile_a: Source instance profile name.
        profile_b: Target instance profile name.
        captured_at_a: When inventory A was captured (UTC).
        captured_at_b: When inventory B was captured (UTC).
        entries: All non-identical plugins in stable (product_family,
            plugin_id) order.
    """
    model_config = _FROZEN

    profile_a: str
    profile_b: str
    captured_at_a: UtcDatetime
    captured_at_b: UtcDatetime
    entries: tuple[PluginDiffEntry, ...]


class PromoteAction(BaseModel):
    """One step in a promotion plan.

    Attributes:
        action: ``install``, ``activate``, or ``upgrade``.
        plugin_id: Canonical SN plugin identifier.
        name: Display name from the source inventory.
        product_family: Curated product family.
        target_version: Version present on the source instance.
        current_version: Version present on the target instance, or
            ``None`` when the action is ``install``.
    """
    model_config = _FROZEN

    action: Literal["install", "activate", "upgrade"]
    plugin_id: str
    name: str
    product_family: str
    target_version: str
    current_version: str | None


class PromotionPlan(BaseModel):
    """Actions required to make ``target_profile`` match ``source_profile``.

    Attributes:
        source_profile: Profile the actions originate from.
        target_profile: Profile the actions are applied to.
        actions: All actions in stable (action_order, product_family,
            plugin_id) order, where ``install`` < ``activate`` < ``upgrade``.
    """
    model_config = _FROZEN

    source_profile: str
    target_profile: str
    actions: tuple[PromoteAction, ...]
```

### Pure functions in ``diff.py``

```python
def compute_diff(
    a: PluginInventory,
    b: PluginInventory,
    profile_a: str,
    profile_b: str,
) -> PluginDiff:
    """Compute the cross-instance plugin diff.

    Identical entries (same plugin_id, version, and state) are excluded.
    Entries are sorted by (product_family, plugin_id) for stable output.
    """


def project_to_promote_plan(diff: PluginDiff) -> PromotionPlan:
    """Project a diff into an additive set of install/activate/upgrade actions.

    Rules:
    - ``only_in_a`` -> ``install``.
    - ``state_mismatch`` where ``a_state=="active"`` and
      ``b_state=="inactive"`` -> ``activate``.
    - ``version_mismatch`` where ``a_version`` is strictly newer than
      ``b_version`` per ``packaging.version.parse`` -> ``upgrade``.
    - All other diff entries (deactivations, downgrades, only_in_b)
      are skipped.

    Actions are sorted by (install < activate < upgrade, product_family,
    plugin_id).
    """
```

Version comparison uses ``packaging.version.parse`` (already a transitive
dep via the existing ``nexus update`` command). When parsing fails for
either version string, the entry is reported as ``version_mismatch`` by
``compute_diff`` (best-effort string inequality) and skipped by
``project_to_promote_plan`` (safer to not auto-include unparseable
versions in an upgrade plan).

### CLI surface

A two-command extension of the existing ``plugins_app``:

```
nexus plugins diff <profile-a> <profile-b>
    [--status only_in_a|only_in_b|version_mismatch|state_mismatch]
                                      -- DataTable of differences
                                         with summary Notice underneath

nexus plugins promote <source> --to <target>
    [--out FILE]                      -- writes a YAML action plan
                                         default: promote-<src>-to-<dst>.yaml
                                         in cwd
```

Both commands resolve their profiles via the existing
``InstanceRegistry`` and surface ``InstanceNotFoundError`` as
``Notice.error`` + ``typer.Exit(1)``. When ``load_plugin_inventory``
returns ``None`` (profile registered but never refreshed since sub-project
A shipped), the command prints ``Notice.warn("Plugin inventory empty for
<profile>.")`` followed by ``Hint(label="Refresh", command=f"nexus
instance refresh {profile}")`` and exits 1.

### Promote YAML shape

```yaml
source_profile: prod
target_profile: dev
actions:
  install:
    - plugin_id: com.snc.discovery
      name: Discovery
      product_family: ITOM
      target_version: "2.0.0"
  activate:
    - plugin_id: com.snc.problem
      name: Problem Management
      product_family: ITSM
      target_version: "1.2.3"
  upgrade:
    - plugin_id: com.snc.incident
      name: Incident Management
      product_family: ITSM
      current_version: "1.2.0"
      target_version: "1.2.3"
```

Empty sections are emitted as ``[]`` for stability; a plan with zero
actions still produces a parseable file.

### Rendering for ``diff``

A ``DataTable`` titled ``"Plugins: <a> vs <b>"`` with columns:

- Plugin ID (width 32)
- Name (width 20)
- Product (width 14)
- Status (width 18; ``StatusBadge.ok`` for ``state_mismatch``,
  ``StatusBadge.warn`` for ``only_in_a`` / ``only_in_b``,
  ``StatusBadge.error`` for ``version_mismatch``)
- A version (width 10)
- B version (width 10)
- A state (width 9)
- B state (width 9)

A trailing ``Notice.info`` line summarises the counts per status. Empty
diff after filtering renders a single ``Notice.info("No differences
found.")``.

### Rendering for ``promote``

After writing the YAML, the command prints a ``KeyValuePanel`` titled
``"Promotion plan"`` with rows:

- Source: ``<source_profile>`` (captured ``<src.captured_at>`` UTC)
- Target: ``<target_profile>`` (captured ``<dst.captured_at>`` UTC)
- Install: ``<count>``
- Activate: ``<count>``
- Upgrade: ``<count>``
- Output: ``<path>``

When zero actions, the panel is suppressed and a single ``Notice.info``
prints: ``"Target <dst> already matches <src>. No actions written."``

### Layer reuse

- ``PluginInfo`` and ``PluginInventory`` -- consumed unchanged.
- ``InstanceRegistry.load_plugin_inventory`` -- single read per profile.
- ``_resolve_profile`` -- validate profile dirs exist before loading.
- ``DataTable`` / ``DataColumn`` / ``KeyValuePanel`` / ``KvRow`` /
  ``StatusBadge`` / ``Notice`` / ``Hint`` -- all already exported from
  ``nexus.ui``.
- ``packaging.version.parse`` -- already a transitive dependency.
- ``_yaml.safe_dump`` -- already used by ``nexus plugins export``.

### Error paths

- Unknown profile: ``InstanceNotFoundError`` is raised by
  ``_resolve_profile``. CLI catches it and exits with ``Notice.error``.
- Missing inventory: ``load_plugin_inventory`` returns ``None``. CLI
  prints the refresh ``Hint`` and exits 1.
- Both inventories missing: error reports both profiles in the message.
- Same source and target profile: ``Notice.warn("Source and target are
  the same profile.")`` and exits 1. (Avoids generating a useless empty
  plan.)
- Parseable but identical inventories: not an error; renders empty
  table or the "already matches" notice.

## Testing strategy

All tests use real fakes (project no-mocks rule).

### ``tests/test_plugins_diff.py`` (pure-function tests)

- ``test_compute_diff_returns_empty_for_identical_inventories``
- ``test_compute_diff_reports_only_in_a_when_a_has_extra_plugin``
- ``test_compute_diff_reports_only_in_b_when_b_has_extra_plugin``
- ``test_compute_diff_reports_version_mismatch``
- ``test_compute_diff_reports_state_mismatch``
- ``test_compute_diff_sorts_entries_by_product_then_plugin_id``
- ``test_project_to_promote_plan_includes_install_for_only_in_a``
- ``test_project_to_promote_plan_includes_activate_for_active_on_a_inactive_on_b``
- ``test_project_to_promote_plan_skips_deactivate_direction``
- ``test_project_to_promote_plan_includes_upgrade_when_a_version_newer``
- ``test_project_to_promote_plan_skips_downgrade_when_a_version_older``
- ``test_project_to_promote_plan_skips_only_in_b``
- ``test_project_to_promote_plan_sorts_install_then_activate_then_upgrade``
- ``test_project_to_promote_plan_handles_unparseable_versions_safely``

### ``tests/test_cli_plugins_diff.py`` (CliRunner integration)

- ``test_plugins_diff_renders_datatable_with_all_status_categories``
- ``test_plugins_diff_filters_by_status_flag``
- ``test_plugins_diff_warns_when_either_inventory_missing``
- ``test_plugins_diff_errors_when_profile_unknown``
- ``test_plugins_diff_with_identical_inventories_prints_no_differences``
- ``test_plugins_promote_writes_yaml_with_install_activate_upgrade_sections``
- ``test_plugins_promote_default_out_path_is_promote_src_to_dst_yaml``
- ``test_plugins_promote_with_zero_actions_prints_already_matches_notice``
- ``test_plugins_promote_rejects_same_source_and_target``
- ``test_plugins_promote_errors_when_either_inventory_missing``

Test naming follows ``test_<function>_<scenario>``.

## File layout

New files:

```
src/nexus/plugins/diff.py
tests/test_plugins_diff.py
tests/test_cli_plugins_diff.py
```

Modified files:

```
src/nexus/plugins/__init__.py    -- export PluginDiff, PluginDiffEntry,
                                     PromotionPlan, PromoteAction,
                                     compute_diff, project_to_promote_plan
src/nexus/cli.py                 -- add `diff` and `promote` subcommands
                                     to plugins_app, update _PLUGINS_HELP
.ratchet.json                    -- new module entries
```

## Risks

- **Version-string parsing.** ServiceNow plugin versions are not strictly
  semver. ``packaging.version.parse`` is liberal but can still raise
  ``InvalidVersion``. Mitigation: ``compute_diff`` falls back to string
  equality for mismatch detection; ``project_to_promote_plan`` skips
  unparseable upgrades rather than risk a bogus action.
- **Snapshot freshness drift.** If ``a`` and ``b`` were refreshed weeks
  apart, the diff reflects historical state. Mitigation: the diff
  panel/summary surfaces both ``captured_at`` timestamps so the user can
  judge freshness.
- **YAML stability.** ``_yaml.safe_dump(sort_keys=False)`` preserves the
  install / activate / upgrade section order, but within each section the
  ordering is `(product_family, plugin_id)`. Diff and promote produce
  byte-identical files for identical inputs, which makes snapshot tests
  feasible.

## Out of scope (deferred)

- Pre-deactivation impact analysis (B3).
- N-way diff across the whole instance fleet.
- Executing the promotion (no SN REST endpoint exists for core-plugin
  activation; Store apps would be a separate sub-project C concern).
- Plugin dependency-tree traversal across instances. Direct
  ``depends_on`` lists are already on ``PluginInfo`` and visible in
  ``nexus plugins info``; full traversal is not required for diff or
  promote.

## Open questions

None remain after the brainstorm. CLI shape (``promote <src> --to
<dst>``), YAML output format, additive-only promotion, and the B1+B2
scope split were all resolved before this spec was written.
