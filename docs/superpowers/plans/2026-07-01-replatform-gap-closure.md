# Replatform Gap Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the gap between what `nexus assess inventory` / `nexus assess migration` cover today (custom-scoped AI & Automation artifacts, one flat Uncategorized bucket) and what a large-enterprise replatform (the acquisition-onto-clean-instance pattern) actually needs: developer-platform artifact coverage, global-scope visibility, per-application checklist grouping, and count-honest diffing at bank scale.

**Architecture:** All work stays inside the existing replatform vertical (`src/nexus/capture/tables.py`, `src/nexus/replatform/`, `src/nexus/cli/commands_assess_replatform.py`). The classifier and diff remain pure, deterministic, LLM-free functions; the live lister remains the only I/O seam and stays `pragma: no cover` with its new logic extracted into testable pure helpers. No new subsystem, no schema changes outside `UseCaseInventory` gaining one defaulted field.

**Tech Stack:** Python 3.14 (Poetry, in-project `.venv`), Typer CLI, Pydantic v2 (frozen+strict+extra=forbid), pytest with fakes (no mocks), mypy strict + pyright strict, ruff + black.

## Global Constraints

- Python pinned `>=3.14,<3.15` (pyproject.toml); PEP 758 unparenthesized multi-except is required style
- Line length 100; black + ruff zero violations; mypy strict + pyright strict 0 errors; no `# type: ignore`
- No mocks -- fakes in `tests/fakes/` only; test naming `test_<function>_<scenario>`
- 100% line coverage ratchet (`.ratchet.json`) -- every new logic line needs a test; live-I/O functions carry `# pragma: no cover` and stay logic-thin
- All Pydantic models `ConfigDict(frozen=True, strict=True, extra="forbid")`
- Absolute imports only; module-level `__all__`; Google docstrings; ASCII only
- Every new Python file starts with the 4-line header (path, description, `Author: Pierre Grothe`, `Date: 2026-07-01`)
- Hooks: PreToolUse blocks anti-patterns; PostToolUse runs ruff+mypy after every edit -- expect them to fire
- Run the full suite between tasks; never commit red. Baseline: 1835 passed, 3 skipped (2026-07-01)

## Context (why each task exists)

Verified findings from the 2026-07-01 assessment:

1. `diff.py` keys targets in a plain dict: duplicate natural keys silently drop
   EXTRA items and can double-count DONE (diff.py:47-59,81-83). No test covers
   collisions. At bank scale ("Copy of Copy of..." naming) this will occur.
2. Unnamed artifacts fall back to sys_id key segments (classifier.py:58-60) and
   can never match cross-instance -- silent permanent TODO+EXTRA pairs.
3. Absent tables are skipped at debug level only
   (commands_assess_replatform.py:249-256) -- a thin listing understates TODO
   counts with no visible warning.
4. All custom scopes collapse to one "Uncategorized" bucket because the catalog
   only maps out-of-box scopes (classifier.py:55-56); the live alectri proof run
   shows 558 artifacts under a single heading.
5. Coverage is exactly one table group (AI_AUTOMATION, 5 tables) and only
   x_/u_ scopes; business rules, script includes, client scripts, UI
   policies/actions, ACLs, scheduled jobs, classic workflows, and ALL
   global-scope customization are invisible (tables.py:66-101,
   commands_assess_replatform.py:54,214-218).

Call-site audit (grep, 2026-07-01): `DEFAULT_TABLE_GROUPS` is consumed by
`capture/engine.py`, `capture/protocol.py`, `cli/commands_capture.py`, and the
replatform lister. Engine and capture CLI default to `AI_AUTOMATION.key`
explicitly, so registering a second group is non-breaking for them (and makes
`nexus capture pull --group developer_platform` work for free).

## File Structure

- Modify: `src/nexus/replatform/diff.py` -- multiset target matching (Task 1)
- Modify: `src/nexus/replatform/reporter.py` -- unnamed-artifact warning (Task 2)
- Modify: `src/nexus/replatform/models.py` -- `UseCaseInventory.skipped_tables` (Task 3)
- Modify: `src/nexus/replatform/classifier.py` -- skipped-tables passthrough (Task 3), app-name domains (Task 4), overrides (Task 5)
- Create: `src/nexus/replatform/domain_map.py` -- YAML scope->domain loader (Task 5)
- Modify: `src/nexus/capture/tables.py` -- `TableSpec.name_field`, `DEVELOPER_PLATFORM` group (Task 6)
- Modify: `src/nexus/cli/commands_assess_replatform.py` -- warnings (Task 3), CLI options, multi-group lister, pure helpers (Tasks 5-7)
- Modify: `tests/fakes/replatform.py` -- `names` and `skipped_tables` params
- Test: `tests/test_replatform_diff.py`, `tests/test_replatform_reporter.py`, `tests/test_replatform_classifier.py`, `tests/test_replatform_domain_map.py` (new), `tests/capture/test_tables.py` (new if absent), `tests/cli/test_assess_replatform_cmd.py`

Branch first: `git checkout -b feat/2026.07-replatform-coverage` off `main`.

---

### Task 1: Multiset diff matching (duplicate natural keys)

**Files:**
- Modify: `src/nexus/replatform/diff.py:46-83`
- Test: `tests/test_replatform_diff.py`

**Interfaces:**
- Consumes: `WorkflowRef`, `UseCase`, `UseCaseInventory`, `ChecklistItem`, `ChecklistStatus`, `ChecklistKind`, `MigrationChecklist` from `nexus.replatform.models` (unchanged).
- Produces: `build_checklist(source, target, aliases=()) -> MigrationChecklist` -- signature unchanged; semantics now multiset: each source occurrence of a key consumes at most one target occurrence; unconsumed target occurrences each surface as EXTRA.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_replatform_diff.py`:

```python
def test_build_checklist_duplicate_source_names_each_need_a_target() -> None:
    dup_a = make_workflow_ref(scope="x_app", name="Duplicate")
    dup_b = make_workflow_ref(scope="x_app", name="  duplicate ")
    source = make_use_case_inventory(
        profile="old", use_cases=(make_use_case(key="x_app", workflows=(dup_a, dup_b)),)
    )
    target = make_use_case_inventory(
        profile="new", use_cases=(make_use_case(key="x_app", workflows=(dup_a,)),)
    )
    checklist = build_checklist(source, target)
    uc = _item(checklist.items, key="x_app", kind=ChecklistKind.USE_CASE)
    assert uc.status is ChecklistStatus.PARTIAL
    assert uc.built_count == 1
    assert uc.total_count == 2


def test_build_checklist_duplicate_target_names_surface_unmatched_extra() -> None:
    dup = make_workflow_ref(scope="x_app", name="Duplicate")
    source = make_use_case_inventory(
        profile="old", use_cases=(make_use_case(key="x_app", workflows=(dup,)),)
    )
    target = make_use_case_inventory(
        profile="new", use_cases=(make_use_case(key="x_app", workflows=(dup, dup)),)
    )
    checklist = build_checklist(source, target)
    extras = [i for i in checklist.items if i.status is ChecklistStatus.EXTRA]
    assert len(extras) == 1


def test_build_checklist_all_duplicate_targets_extra_when_source_missing() -> None:
    dup = make_workflow_ref(scope="x_app", name="Duplicate")
    source = make_use_case_inventory(
        profile="old", use_cases=(make_use_case(key="x_app", workflows=()),)
    )
    target = make_use_case_inventory(
        profile="new", use_cases=(make_use_case(key="x_app", workflows=(dup, dup)),)
    )
    checklist = build_checklist(source, target)
    extras = [i for i in checklist.items if i.status is ChecklistStatus.EXTRA]
    assert len(extras) == 2
```

(`make_workflow_ref` normalizes the name into the key, so "Duplicate" and
"  duplicate " produce the identical natural key -- that is the collision.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_replatform_diff.py -v`
Expected: the first test FAILS with `built_count == 2` (double-count), the second with `len(extras) == 0` (dropped EXTRA), the third with `len(extras) == 1`.

- [ ] **Step 3: Rewrite the matching core**

In `src/nexus/replatform/diff.py`, replace the body of `build_checklist` between `new_to_old = ...` and `items.sort(...)` with:

```python
    new_to_old = {new: old for old, new in aliases}
    target_by_key: dict[str, list[tuple[UseCase, WorkflowRef]]] = {}
    for use_case in target.use_cases:
        for workflow in use_case.workflows:
            target_by_key.setdefault(_remap(workflow, new_to_old), []).append(
                (use_case, workflow)
            )
    # Multiset semantics: each source occurrence consumes at most one target
    # occurrence, so duplicate names neither drop EXTRA rows nor double-count DONE.
    unmatched = {key: len(entries) for key, entries in target_by_key.items()}

    items: list[ChecklistItem] = []
    for use_case in source.use_cases:
        built = 0
        for workflow in use_case.workflows:
            present = unmatched.get(workflow.key, 0) > 0
            if present:
                unmatched[workflow.key] -= 1
                built += 1
            items.append(
                _workflow_item(
                    workflow,
                    use_case,
                    ChecklistStatus.DONE if present else ChecklistStatus.TODO,
                )
            )
        total = len(use_case.workflows)
        items.append(
            ChecklistItem(
                key=use_case.key,
                name=use_case.name,
                domain=use_case.domain,
                use_case_key=use_case.key,
                kind=ChecklistKind.USE_CASE,
                status=_rollup_status(built, total),
                built_count=built,
                total_count=total,
            )
        )

    for key, entries in target_by_key.items():
        for use_case, workflow in entries[len(entries) - unmatched[key] :]:
            items.append(_workflow_item(workflow, use_case, ChecklistStatus.EXTRA))
```

The `source_keys` set is removed (delete it completely -- no leftovers). Update
the `build_checklist` docstring Returns/behavior sentence to mention multiset
matching of duplicate keys.

- [ ] **Step 4: Run the module tests, then the full suite**

Run: `.venv/Scripts/python -m pytest tests/test_replatform_diff.py -v`
Expected: PASS (all pre-existing tests must also still pass -- single-occurrence behavior is unchanged).
Run: `.venv/Scripts/python -m pytest -q`
Expected: 1838 passed (baseline +3), 3 skipped.

- [ ] **Step 5: Commit**

```bash
git add src/nexus/replatform/diff.py tests/test_replatform_diff.py
git commit -m "fix(replatform): multiset natural-key matching in checklist diff"
```

---

### Task 2: Unnamed-artifact warning in the reporter

**Files:**
- Modify: `src/nexus/replatform/reporter.py`
- Test: `tests/test_replatform_reporter.py`

**Interfaces:**
- Consumes: `MigrationChecklist`, `ChecklistKind` (unchanged), `Notice` from `nexus.ui.components`.
- Produces: module constant `UNNAMED_NOTICE: str` (format template with `{count}`), exported via `__all__`. Render behavior: any checklist containing WORKFLOW items with an empty `name` prints/embeds one warning with the count, in plain, rich, and markdown outputs.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_replatform_reporter.py` (reuse the existing `_ctx` helper; add `WorkflowRef` to the `nexus.replatform.models` import line):

```python
def _unnamed_checklist() -> MigrationChecklist:
    unnamed = WorkflowRef(
        key="x_app|sys_hub_flow|0a1b2c3d4e5f", name="", type="sys_hub_flow", scope="x_app"
    )
    source = make_use_case_inventory(
        profile="old", use_cases=(make_use_case(key="x_app", workflows=(unnamed,)),)
    )
    target = make_use_case_inventory(
        profile="new", use_cases=(make_use_case(key="x_app", workflows=()),)
    )
    return build_checklist(source, target)


def test_render_checklist_plain_warns_on_unnamed_artifacts() -> None:
    buf = StringIO()
    render_checklist(_unnamed_checklist(), _ctx(RenderProfile.PLAIN, buf))
    assert "unnamed artifact" in buf.getvalue()


def test_render_checklist_rich_warns_on_unnamed_artifacts() -> None:
    buf = StringIO()
    render_checklist(_unnamed_checklist(), _ctx(RenderProfile.RICH, buf))
    assert "unnamed artifact" in buf.getvalue()


def test_write_markdown_warns_on_unnamed_artifacts(tmp_path: Path) -> None:
    out = tmp_path / "checklist.md"
    write_markdown(_unnamed_checklist(), out)
    assert "unnamed artifact" in out.read_text(encoding="utf-8")


def test_write_markdown_omits_unnamed_warning_when_all_named(tmp_path: Path) -> None:
    out = tmp_path / "checklist.md"
    write_markdown(_partial_checklist(), out)
    assert "unnamed artifact" not in out.read_text(encoding="utf-8")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_replatform_reporter.py -v`
Expected: 4 new tests FAIL ("unnamed artifact" not found); the omit-test passes vacuously -- keep it, it guards the guard.

- [ ] **Step 3: Implement the warning**

In `src/nexus/replatform/reporter.py`:

Add below `EMPTY_SOURCE_NOTICE` and extend `__all__` with `"UNNAMED_NOTICE"`:

```python
UNNAMED_NOTICE = (
    "{count} unnamed artifact(s) have no stable natural key and cannot be "
    "matched across instances -- they always render as TODO on the source "
    "and EXTRA on the target"
)


def _unnamed_count(checklist: MigrationChecklist) -> int:
    """Count WORKFLOW items whose artifact carries no display name."""
    return sum(
        1 for item in checklist.items if item.kind is ChecklistKind.WORKFLOW and not item.name
    )
```

In `_render_plain`, after the `EMPTY_SOURCE_NOTICE` block:

```python
    unnamed = _unnamed_count(checklist)
    if unnamed:
        ctx.console.print(UNNAMED_NOTICE.format(count=unnamed), highlight=False)
```

In `_render_rich`, after the header Notice block:

```python
    unnamed = _unnamed_count(checklist)
    if unnamed:
        ctx.console.print(Notice.warn(UNNAMED_NOTICE.format(count=unnamed)))
```

In `_markdown`, after the empty-source warning lines:

```python
    unnamed = _unnamed_count(checklist)
    if unnamed:
        lines.extend([f"> WARNING: {UNNAMED_NOTICE.format(count=unnamed)}", ""])
```

- [ ] **Step 4: Run tests**

Run: `.venv/Scripts/python -m pytest tests/test_replatform_reporter.py -q && .venv/Scripts/python -m pytest -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/nexus/replatform/reporter.py tests/test_replatform_reporter.py
git commit -m "feat(replatform): warn when unnamed artifacts cannot match cross-instance"
```

---

### Task 3: Skipped-table transparency

**Files:**
- Modify: `src/nexus/replatform/models.py` (UseCaseInventory)
- Modify: `src/nexus/replatform/classifier.py` (passthrough kwarg)
- Modify: `src/nexus/cli/commands_assess_replatform.py` (collect + display)
- Modify: `tests/fakes/replatform.py` (`skipped_tables` param)
- Test: `tests/test_replatform_classifier.py`, `tests/cli/test_assess_replatform_cmd.py`

**Interfaces:**
- Produces: `UseCaseInventory.skipped_tables: tuple[str, ...] = ()` (new defaulted field, sorted); `classify(..., skipped_tables: tuple[str, ...] = ())` keyword; `run_inventory` / `run_migration` print a `warning: tables absent on <profile>: ...` line when non-empty.
- Consumes: the live lister's 400/404 skip branch (commands_assess_replatform.py:249-256) now records `spec.name` instead of only debug-logging.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_replatform_classifier.py`:

```python
def test_classify_records_skipped_tables_sorted() -> None:
    scopes = make_scope_manifest(scopes={"s1": "x_acme_app"}, captured_at=_TS)
    catalog = make_schema_catalog(scope_to_product={})
    capture = make_capture_result(records=())
    inv = classify(
        (capture,), scopes, catalog, profile="prod", skipped_tables=("sys_ai_agent", "ai_skill")
    )
    assert inv.skipped_tables == ("ai_skill", "sys_ai_agent")
```

Append to `tests/cli/test_assess_replatform_cmd.py` (reuse that file's existing
RenderContext/console builder if one exists; otherwise copy the `_ctx` helper
from `tests/test_replatform_reporter.py`):

```python
def test_run_inventory_warns_on_skipped_tables() -> None:
    buf = StringIO()
    ctx = _ctx(RenderProfile.PLAIN, buf)
    inv = make_use_case_inventory(profile="dev", skipped_tables=("ai_skill",))
    collaborators = ReplatformCollaborators(build_inventory=lambda _p: inv)
    code = run_inventory(profile="dev", out=None, render_context=ctx, collaborators=collaborators)
    assert code == 0
    assert "tables absent on dev" in buf.getvalue()
    assert "ai_skill" in buf.getvalue()


def test_run_migration_warns_on_skipped_tables_per_side() -> None:
    buf = StringIO()
    ctx = _ctx(RenderProfile.PLAIN, buf)
    by_profile = {
        "old": make_use_case_inventory(profile="old", skipped_tables=("ai_skill",)),
        "new": make_use_case_inventory(profile="new", use_cases=()),
    }
    collaborators = ReplatformCollaborators(build_inventory=lambda p: by_profile[p])
    code = run_migration(
        from_profile="old",
        to_profile="new",
        aliases=(),
        out=None,
        render_context=ctx,
        collaborators=collaborators,
    )
    assert code == 0
    assert "tables absent on old" in buf.getvalue()
```

- [ ] **Step 2: Extend the fake, run tests to verify they fail**

In `tests/fakes/replatform.py`, add the parameter to `make_use_case_inventory`:

```python
def make_use_case_inventory(
    *,
    profile: str = "dev",
    captured_at: datetime = _DEFAULT_TS,
    coverage: tuple[str, ...] = ("ai_automation",),
    use_cases: tuple[UseCase, ...] | None = None,
    skipped_tables: tuple[str, ...] = (),
) -> UseCaseInventory:
    """Build a UseCaseInventory with one default use case when none are supplied."""
    cases = use_cases if use_cases is not None else (make_use_case(),)
    return UseCaseInventory(
        profile=profile,
        captured_at=captured_at,
        coverage=coverage,
        use_cases=cases,
        skipped_tables=skipped_tables,
    )
```

Run: `.venv/Scripts/python -m pytest tests/test_replatform_classifier.py tests/cli/test_assess_replatform_cmd.py -v`
Expected: FAIL -- `UseCaseInventory` has no field `skipped_tables`, `classify` has no such kwarg.

- [ ] **Step 3: Implement model + classifier + CLI display**

`src/nexus/replatform/models.py`, `UseCaseInventory` -- add after `use_cases` (and document in the class docstring Attributes):

```python
    skipped_tables: tuple[str, ...] = ()
```

`src/nexus/replatform/classifier.py`, `classify` -- add keyword parameter and
pass it through (document in Args):

```python
def classify(
    captures: tuple[CaptureResult, ...],
    scopes: ScopeManifest,
    catalog: SchemaProductCatalog,
    *,
    profile: str,
    skipped_tables: tuple[str, ...] = (),
) -> UseCaseInventory:
```

and in the return statement:

```python
    return UseCaseInventory(
        profile=profile,
        captured_at=scopes.captured_at,
        coverage=tuple(sorted(coverage)),
        use_cases=use_cases,
        skipped_tables=tuple(sorted(skipped_tables)),
    )
```

`src/nexus/cli/commands_assess_replatform.py`:

In `run_inventory`, after the coverage print loop:

```python
    if inventory.skipped_tables:
        render_context.console.print(
            f"warning: tables absent on {profile}: {', '.join(inventory.skipped_tables)}"
            " -- inventory excludes them",
            highlight=False,
        )
```

In `run_migration`, after building `source` and `target` and before `build_checklist`:

```python
    for inventory in (source, target):
        if inventory.skipped_tables:
            render_context.console.print(
                f"warning: tables absent on {inventory.profile}: "
                f"{', '.join(inventory.skipped_tables)} -- checklist excludes them",
                highlight=False,
            )
```

In `_list_artifacts_live`: initialize `skipped: list[str] = []` next to
`records`, and in the `except SNClientError` branch append the table name
before the debug log:

```python
                        skipped.append(spec.name)
                        log.debug("replatform: skipping absent table %s: %s", spec.name, exc)
```

Change its return to `tuple[ScopeManifest, CaptureResult, tuple[str, ...]]`
returning `manifest, capture, tuple(skipped)`, and in `_build_live_inventory`:

```python
    manifest, capture, skipped = asyncio.run(_list_artifacts_live(profile))
    catalog = ProductRegistry(paths.schema_dir).load_catalog()
    return classify((capture,), manifest, catalog, profile=profile, skipped_tables=skipped)
```

- [ ] **Step 4: Run tests**

Run: `.venv/Scripts/python -m pytest tests/test_replatform_classifier.py tests/cli/test_assess_replatform_cmd.py tests/test_replatform_models.py -q && .venv/Scripts/python -m pytest -q`
Expected: all PASS (the defaulted field keeps every existing construction site valid).

- [ ] **Step 5: Commit**

```bash
git add src/nexus/replatform/models.py src/nexus/replatform/classifier.py src/nexus/cli/commands_assess_replatform.py tests/fakes/replatform.py tests/test_replatform_classifier.py tests/cli/test_assess_replatform_cmd.py
git commit -m "feat(replatform): surface absent tables instead of silent debug-level skip"
```

---

### Task 4: Per-application domains (kill the Uncategorized collapse)

**Files:**
- Modify: `src/nexus/replatform/classifier.py`
- Modify: `tests/fakes/replatform.py` (`names` param on `make_scope_manifest`)
- Test: `tests/test_replatform_classifier.py`

**Interfaces:**
- Consumes: `ScopeEntry.name` (application display name) from the ScopeManifest -- already populated by `ScopeDiscoverer` (capture/scope.py:139-151).
- Produces: domain resolution precedence inside `classify`: catalog product name (OOB scopes) > scope display name (custom apps) > `"Uncategorized"` (unresolvable scope only). One use case per resulting domain, exactly as today.

Behavior change note: the existing test
`test_classify_buckets_custom_scope_as_uncategorized` asserts the OLD collapse
behavior and must be REPLACED (not kept) -- a custom scope present in the
manifest now groups under its app display name.

- [ ] **Step 1: Extend the fake**

In `tests/fakes/replatform.py`, change `make_scope_manifest`:

```python
def make_scope_manifest(
    *,
    scopes: dict[str, str],
    names: dict[str, str] | None = None,
    instance_id: str = "dev",
    captured_at: datetime = _DEFAULT_TS,
) -> ScopeManifest:
    """Build a ScopeManifest from a ``sys_id -> technical-scope-key`` mapping.

    Args:
        scopes: Mapping of scope sys_id to technical scope key.
        names: Optional mapping of scope sys_id to display name; entries
            default to the scope key when absent.
        instance_id: Manifest instance profile.
        captured_at: Manifest capture timestamp.
    """
    entries = tuple(
        ScopeEntry(
            sys_id=sys_id,
            name=(names or {}).get(sys_id, scope_key),
            scope=scope_key,
            version="1.0",
            vendor="test",
            table_counts={},
        )
        for sys_id, scope_key in scopes.items()
    )
    return ScopeManifest(instance_id=instance_id, captured_at=captured_at, scopes=entries)
```

- [ ] **Step 2: Write the failing tests**

In `tests/test_replatform_classifier.py`, DELETE
`test_classify_buckets_custom_scope_as_uncategorized` and add:

```python
def test_classify_names_custom_scope_domain_after_app_display_name() -> None:
    scopes = make_scope_manifest(
        scopes={"s1": "x_acme_app"}, names={"s1": "Acme Field Service"}, captured_at=_TS
    )
    catalog = make_schema_catalog(scope_to_product={})
    capture = make_capture_result(
        records=(
            make_config_record(
                sys_id="r1",
                table="ai_skill",
                scope_sys_id="s1",
                scope_name="Acme",
                fields={"name": "Greeting"},
            ),
        ),
    )
    inv = classify((capture,), scopes, catalog, profile="prod")
    assert len(inv.use_cases) == 1
    assert inv.use_cases[0].domain == "Acme Field Service"
    assert inv.use_cases[0].workflows[0].key == "x_acme_app|ai_skill|greeting"


def test_classify_catalog_domain_wins_over_app_display_name() -> None:
    scopes = make_scope_manifest(
        scopes={"s1": "sn_hamp"}, names={"s1": "HAM Store App"}, captured_at=_TS
    )
    catalog = make_schema_catalog(scope_to_product={"sn_hamp": "Hardware Asset Management"})
    capture = make_capture_result(
        records=(
            make_config_record(
                sys_id="r1", table="sys_hub_flow", scope_sys_id="s1", fields={"name": "A"}
            ),
        ),
    )
    inv = classify((capture,), scopes, catalog, profile="prod")
    assert inv.use_cases[0].domain == "Hardware Asset Management"


def test_classify_buckets_unresolvable_scope_as_uncategorized() -> None:
    scopes = make_scope_manifest(scopes={}, captured_at=_TS)
    catalog = make_schema_catalog(scope_to_product={})
    capture = make_capture_result(
        records=(
            make_config_record(
                sys_id="r1",
                table="ai_skill",
                scope_sys_id="ghost",
                scope_name="",
                fields={"name": "Greeting"},
            ),
        ),
    )
    inv = classify((capture,), scopes, catalog, profile="prod")
    assert inv.use_cases[0].domain == "Uncategorized"
```

- [ ] **Step 3: Run tests to verify the new ones fail**

Run: `.venv/Scripts/python -m pytest tests/test_replatform_classifier.py -v`
Expected: the first new test FAILS with domain == "Uncategorized"; the second and third pass already (guard tests) -- keep them.

- [ ] **Step 4: Implement domain resolution in classify**

In `src/nexus/replatform/classifier.py`, replace the two lookup dicts and the
per-record scope/domain resolution:

```python
    sys_to_entry = {entry.sys_id: entry for entry in scopes.scopes}
    scope_key_to_name = {entry.scope: entry.name for entry in scopes.scopes}
    scope_to_domain = {
        scope.key: product.name for product in catalog.products for scope in product.scopes
    }
```

and inside the record loop:

```python
        for record in capture.records:
            entry = sys_to_entry.get(record.scope_sys_id)
            scope_key = entry.scope if entry is not None else record.scope_name
            app_name = entry.name if entry is not None else scope_key_to_name.get(scope_key, "")
            domain = scope_to_domain.get(scope_key) or app_name or _UNCATEGORIZED
```

(The rest of the loop body -- name extraction, key segment, WorkflowRef, and
the by_domain/evidence bookkeeping -- is unchanged.) Update the module
docstring sentence "Custom scopes absent from the catalog collapse to the
Uncategorized domain" to: "Custom scopes absent from the catalog group under
their application display name; only unresolvable scopes fall back to
Uncategorized." Update the `classify` docstring's `catalog` Args line the same
way.

- [ ] **Step 5: Run tests and the full suite**

Run: `.venv/Scripts/python -m pytest tests/test_replatform_classifier.py -q && .venv/Scripts/python -m pytest -q`
Expected: all PASS. (Other classifier tests assert workflow keys, not domains, and are unaffected; grep `Uncategorized` across tests/ to confirm no other assertion depends on the collapse.)

- [ ] **Step 6: Commit**

```bash
git add src/nexus/replatform/classifier.py tests/fakes/replatform.py tests/test_replatform_classifier.py
git commit -m "feat(replatform): group custom scopes by app display name, not Uncategorized"
```

---

### Task 5: Consultant-supplied domain map (`--domain-map`)

**Files:**
- Create: `src/nexus/replatform/domain_map.py`
- Modify: `src/nexus/replatform/classifier.py` (overrides kwarg)
- Modify: `src/nexus/cli/commands_assess_replatform.py` (CLI option + wiring)
- Test: `tests/test_replatform_domain_map.py` (new), `tests/test_replatform_classifier.py`

**Interfaces:**
- Produces: `load_domain_map(path: Path) -> dict[str, str]` raising `ValueError` on malformed input; `classify(..., overrides: dict[str, str] | None = None)` with precedence overrides > catalog > app name > Uncategorized; `--domain-map <path>` option on both `assess inventory` and `assess migration`.
- Consumes: Task 4's domain resolution chain.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_replatform_domain_map.py`:

```python
# tests/test_replatform_domain_map.py
# Tests for the scope->domain YAML overlay loader.
# Author: Pierre Grothe
# Date: 2026-07-01

"""Behavioral tests for nexus.replatform.domain_map.load_domain_map."""

from pathlib import Path

import pytest

from nexus.replatform.domain_map import load_domain_map

__all__: list[str] = []


def test_load_domain_map_parses_flat_mapping(tmp_path: Path) -> None:
    path = tmp_path / "map.yaml"
    path.write_text("x_acme_hr: HR\nx_acme_kyc: Lending Ops\n", encoding="utf-8")
    assert load_domain_map(path) == {"x_acme_hr": "HR", "x_acme_kyc": "Lending Ops"}


def test_load_domain_map_rejects_non_mapping(tmp_path: Path) -> None:
    path = tmp_path / "map.yaml"
    path.write_text("- just\n- a list\n", encoding="utf-8")
    with pytest.raises(ValueError, match="mapping of scope -> domain"):
        load_domain_map(path)


def test_load_domain_map_rejects_non_string_values(tmp_path: Path) -> None:
    path = tmp_path / "map.yaml"
    path.write_text("x_acme_hr: 42\n", encoding="utf-8")
    with pytest.raises(ValueError, match="string scopes to string domains"):
        load_domain_map(path)
```

Append to `tests/test_replatform_classifier.py`:

```python
def test_classify_domain_map_overrides_catalog() -> None:
    scopes = make_scope_manifest(scopes={"s1": "sn_hamp"}, captured_at=_TS)
    catalog = make_schema_catalog(scope_to_product={"sn_hamp": "Hardware Asset Management"})
    capture = make_capture_result(
        records=(
            make_config_record(
                sys_id="r1", table="sys_hub_flow", scope_sys_id="s1", fields={"name": "A"}
            ),
        ),
    )
    inv = classify(
        (capture,), scopes, catalog, profile="prod", overrides={"sn_hamp": "Asset Ops"}
    )
    assert inv.use_cases[0].domain == "Asset Ops"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_replatform_domain_map.py tests/test_replatform_classifier.py -v`
Expected: FAIL -- module `nexus.replatform.domain_map` does not exist; `classify` has no `overrides` kwarg.

- [ ] **Step 3: Implement loader and classifier kwarg**

Create `src/nexus/replatform/domain_map.py`:

```python
# src/nexus/replatform/domain_map.py
# Load a user-supplied scope->domain mapping for the replatform classifier.
# Author: Pierre Grothe
# Date: 2026-07-01

"""YAML loader for engagement-supplied scope-to-domain overrides.

A domain map lets a consultant group custom scopes under business domains
("HR", "Lending Ops") without waiting for catalog entries or AI enrichment:

    x_acme_hr_onboard: HR
    x_acme_kyc: Lending Ops
"""

from pathlib import Path

import yaml

__all__ = ["load_domain_map"]


def load_domain_map(path: Path) -> dict[str, str]:
    """Load and validate a flat ``scope_key: domain`` YAML mapping.

    Args:
        path: YAML file containing the mapping.

    Returns:
        The parsed scope-to-domain mapping.

    Raises:
        ValueError: When the document is not a flat string-to-string mapping.
        OSError: When the file cannot be read.
    """
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"domain map {path} must be a mapping of scope -> domain")
    result: dict[str, str] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise ValueError(f"domain map {path} must map string scopes to string domains")
        result[key] = value
    return result
```

In `classify`, add the kwarg (document in Args) and fold it into the Task 4
precedence chain:

```python
    *,
    profile: str,
    skipped_tables: tuple[str, ...] = (),
    overrides: dict[str, str] | None = None,
```

```python
    override_map = overrides or {}
```

```python
            domain = (
                override_map.get(scope_key)
                or scope_to_domain.get(scope_key)
                or app_name
                or _UNCATEGORIZED
            )
```

- [ ] **Step 4: Wire the CLI option**

In `src/nexus/cli/commands_assess_replatform.py`:

Imports: add `from nexus.replatform.domain_map import load_domain_map`.

Add a shared parser helper next to `parse_scope_aliases`:

```python
def parse_domain_map(raw: str) -> dict[str, str] | None:
    """Load ``--domain-map`` when given, translating errors to CLI errors.

    Args:
        raw: Path string from the CLI ("" when the option was omitted).

    Returns:
        The parsed overrides, or None when no map was supplied.

    Raises:
        typer.BadParameter: When the file is missing or malformed.
    """
    if not raw:
        return None
    try:
        return load_domain_map(Path(raw))
    except ValueError, OSError as exc:
        raise typer.BadParameter(str(exc)) from exc
```

Thread overrides through the production wiring:

```python
def default_replatform_collaborators(  # pragma: no cover -- production wiring
    paths: NexusPaths,
    *,
    overrides: dict[str, str] | None = None,
) -> ReplatformCollaborators:
    """Production wire-up: build inventories from live capture + the catalog."""

    def build(profile: str) -> UseCaseInventory:
        return _build_live_inventory(profile, paths, overrides=overrides)

    return ReplatformCollaborators(build_inventory=build)
```

`_build_live_inventory` gains `*, overrides: dict[str, str] | None = None` and
passes `overrides=overrides` to `classify`. Both Typer commands gain:

```python
    domain_map: Annotated[
        str,
        typer.Option(
            "--domain-map", help="YAML file mapping scope keys to business domains"
        ),
    ] = "",
```

and construct collaborators via
`default_replatform_collaborators(paths, overrides=parse_domain_map(domain_map))`.

Add a parser test to `tests/cli/test_assess_replatform_cmd.py`:

```python
def test_parse_domain_map_returns_none_when_omitted() -> None:
    assert parse_domain_map("") is None


def test_parse_domain_map_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(typer.BadParameter):
        parse_domain_map(str(tmp_path / "absent.yaml"))
```

- [ ] **Step 5: Run tests**

Run: `.venv/Scripts/python -m pytest tests/test_replatform_domain_map.py tests/test_replatform_classifier.py tests/cli/test_assess_replatform_cmd.py -q && .venv/Scripts/python -m pytest -q`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add src/nexus/replatform/domain_map.py src/nexus/replatform/classifier.py src/nexus/cli/commands_assess_replatform.py tests/test_replatform_domain_map.py tests/test_replatform_classifier.py tests/cli/test_assess_replatform_cmd.py
git commit -m "feat(replatform): --domain-map scope->domain overlay for engagement grouping"
```

---

### Task 6: DEVELOPER_PLATFORM table group + multi-group inventory

**Files:**
- Modify: `src/nexus/capture/tables.py` (TableSpec.name_field, new group)
- Modify: `src/nexus/cli/commands_assess_replatform.py` (multi-group lister, `--group`, pure helpers)
- Modify: `src/nexus/replatform/classifier.py` (docstring only)
- Test: `tests/capture/test_tables.py` (create if absent), `tests/cli/test_assess_replatform_cmd.py`

**Interfaces:**
- Produces: `TableSpec.name_field: str = "name"`; `DEVELOPER_PLATFORM: TableGroup` (key `"developer_platform"`) registered in `DEFAULT_TABLE_GROUPS`; helpers `resolve_groups(raw: list[str]) -> tuple[TableGroup, ...]` and `_merge_manifests(manifests: tuple[ScopeManifest, ...]) -> ScopeManifest` in `commands_assess_replatform.py`; `--group` (repeatable) on both assess subcommands, default = all registered groups.
- Consumes: `ScopeDiscoverer.discover(profile, group.key)` per group (unchanged); Task 3's skipped-tables plumbing (skips now accumulate across groups).
- Non-breaking by audit: `capture/engine.py` and `cli/commands_capture.py` default to `AI_AUTOMATION.key` explicitly; registering the new group additionally enables `nexus capture discover/pull --group developer_platform` with zero further changes.

- [ ] **Step 1: Write the failing registry tests**

Create (or extend) `tests/capture/test_tables.py`:

```python
# tests/capture/test_tables.py
# Tests for the capture table-group registry.
# Author: Pierre Grothe
# Date: 2026-07-01

"""Registry-shape tests for nexus.capture.tables."""

from nexus.capture.tables import AI_AUTOMATION, DEFAULT_TABLE_GROUPS, DEVELOPER_PLATFORM

__all__: list[str] = []


def test_default_table_groups_registers_both_groups() -> None:
    assert DEFAULT_TABLE_GROUPS == {
        AI_AUTOMATION.key: AI_AUTOMATION,
        DEVELOPER_PLATFORM.key: DEVELOPER_PLATFORM,
    }


def test_developer_platform_covers_core_config_tables() -> None:
    names = {spec.name for spec in DEVELOPER_PLATFORM.tables}
    assert {
        "sys_script",
        "sys_script_include",
        "sys_script_client",
        "sys_ui_policy",
        "sys_ui_action",
        "sys_security_acl",
        "sysauto_script",
        "wf_workflow",
    } <= names


def test_table_spec_name_field_defaults_to_name() -> None:
    assert all(spec.name_field == "name" for spec in AI_AUTOMATION.tables)


def test_ui_policy_spec_names_by_short_description() -> None:
    spec = next(s for s in DEVELOPER_PLATFORM.tables if s.name == "sys_ui_policy")
    assert spec.name_field == "short_description"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/capture/test_tables.py -v`
Expected: FAIL -- `DEVELOPER_PLATFORM` and `name_field` do not exist.

- [ ] **Step 3: Implement the registry extension**

In `src/nexus/capture/tables.py`:

Add to `TableSpec` (docstring Args too):

```python
    name_field: str = "name"
```

Add after `AI_AUTOMATION` and register (extend `__all__` with `"DEVELOPER_PLATFORM"`):

```python
# Identity note: sys_security_acl rows share `name` across operations
# (read/write ACLs on one resource). The replatform diff matches keys as a
# multiset, so per-name counts stay honest even without an operation suffix.
DEVELOPER_PLATFORM: TableGroup = TableGroup(
    key="developer_platform",
    display="Developer Platform",
    tables=(
        TableSpec(name="sys_script", display="Business Rules"),
        TableSpec(name="sys_script_include", display="Script Includes"),
        TableSpec(name="sys_script_client", display="Client Scripts"),
        TableSpec(
            name="sys_ui_policy",
            display="UI Policies",
            name_field="short_description",
            key_fields=("sys_id", "short_description", "sys_scope"),
        ),
        TableSpec(name="sys_ui_action", display="UI Actions"),
        TableSpec(name="sys_security_acl", display="Access Controls"),
        TableSpec(name="sysauto_script", display="Scheduled Script Jobs"),
        TableSpec(name="wf_workflow", display="Classic Workflows"),
    ),
)

DEFAULT_TABLE_GROUPS: dict[str, TableGroup] = {
    AI_AUTOMATION.key: AI_AUTOMATION,
    DEVELOPER_PLATFORM.key: DEVELOPER_PLATFORM,
}
```

- [ ] **Step 4: Write the failing helper tests**

Append to `tests/cli/test_assess_replatform_cmd.py`:

```python
def test_resolve_groups_defaults_to_all_registered_groups() -> None:
    groups = resolve_groups([])
    assert tuple(g.key for g in groups) == ("ai_automation", "developer_platform")


def test_resolve_groups_rejects_unknown_key() -> None:
    with pytest.raises(typer.BadParameter, match="unknown table group"):
        resolve_groups(["nope"])


def test_merge_manifests_unions_scopes_by_sys_id() -> None:
    ts = datetime(2026, 7, 1, 12, 0, 0, tzinfo=UTC)
    a = make_scope_manifest(scopes={"s1": "x_app"}, captured_at=ts)
    b = make_scope_manifest(scopes={"s1": "x_app", "s2": "x_other"}, captured_at=ts)
    merged = _merge_manifests((a, b))
    assert tuple(e.sys_id for e in merged.scopes) == ("s1", "s2")
```

Run: `.venv/Scripts/python -m pytest tests/cli/test_assess_replatform_cmd.py -v`
Expected: FAIL -- `resolve_groups` / `_merge_manifests` do not exist.

- [ ] **Step 5: Implement the multi-group lister**

In `src/nexus/cli/commands_assess_replatform.py`:

Imports: replace the tables import with
`from nexus.capture.tables import DEFAULT_TABLE_GROUPS, TableGroup, TableSpec`
and add `ScopeEntry` to the capture models import.

Add the pure helpers (NOT `pragma: no cover` -- they are unit-tested):

```python
def resolve_groups(raw: list[str]) -> tuple[TableGroup, ...]:
    """Resolve ``--group`` values against the registry; empty means all groups.

    Args:
        raw: Group keys from the CLI.

    Returns:
        The selected TableGroups in registry order (or CLI order when given).

    Raises:
        typer.BadParameter: When a key is not a registered table group.
    """
    if not raw:
        return tuple(DEFAULT_TABLE_GROUPS.values())
    unknown = [key for key in raw if key not in DEFAULT_TABLE_GROUPS]
    if unknown:
        raise typer.BadParameter(
            f"unknown table group(s): {', '.join(unknown)}; "
            f"valid: {', '.join(DEFAULT_TABLE_GROUPS)}"
        )
    return tuple(DEFAULT_TABLE_GROUPS[key] for key in raw)


def _merge_manifests(manifests: tuple[ScopeManifest, ...]) -> ScopeManifest:
    """Union per-group ScopeManifests by scope sys_id.

    Args:
        manifests: One manifest per discovered table group (at least one).

    Returns:
        A manifest whose scopes are the by-sys_id union, table counts merged,
        sorted by sys_id for stable output.
    """
    by_id: dict[str, ScopeEntry] = {}
    for manifest in manifests:
        for entry in manifest.scopes:
            existing = by_id.get(entry.sys_id)
            if existing is None:
                by_id[entry.sys_id] = entry
            else:
                merged = dict(existing.table_counts) | dict(entry.table_counts)
                by_id[entry.sys_id] = existing.model_copy(update={"table_counts": merged})
    first = manifests[0]
    return ScopeManifest(
        instance_id=first.instance_id,
        captured_at=first.captured_at,
        scopes=tuple(sorted(by_id.values(), key=lambda entry: entry.sys_id)),
    )
```

Rework `_list_artifacts_live` (still `pragma: no cover`) to
`(profile: str, groups: tuple[TableGroup, ...])` returning
`tuple[ScopeManifest, tuple[CaptureResult, ...], tuple[str, ...]]`: wrap the
existing discover+list body in `for group in groups:`, using `group.key` /
`group.tables` instead of `AI_AUTOMATION.*`, using
`fields=f"sys_id,{spec.name_field},{spec.scope_field}"` and
`fields={"name": _ref_value(row.get(spec.name_field))}` in the record builder,
collecting one `CaptureResult` per group (records list reset per group,
`table_group=group.key`), accumulating `skipped` across groups, and returning
`_merge_manifests(tuple(manifests)), tuple(captures), tuple(skipped)`.
Update the module constant comment (`# Page size for listing artifacts per
covered table.`) and the function docstring to say "covered table groups"
instead of AI_AUTOMATION.

`_build_live_inventory` gains `groups: tuple[TableGroup, ...]` and calls
`classify(captures, manifest, catalog, profile=profile, skipped_tables=skipped,
overrides=overrides)`. `default_replatform_collaborators` gains
`groups: tuple[TableGroup, ...]` and both Typer commands gain:

```python
    group: Annotated[
        list[str] | None,
        typer.Option("--group", help="Restrict to table group(s) (repeatable; default: all)"),
    ] = None,
```

wired as `default_replatform_collaborators(paths, groups=resolve_groups(group or []), overrides=parse_domain_map(domain_map))`.

In `src/nexus/replatform/classifier.py`, update the `captures` Args line:
plural captures are now real ("one CaptureResult per covered table group").

- [ ] **Step 6: Run tests and the full suite**

Run: `.venv/Scripts/python -m pytest tests/capture/test_tables.py tests/cli/test_assess_replatform_cmd.py -q && .venv/Scripts/python -m pytest -q`
Expected: all PASS. Also verify capture CLI still defaults cleanly:
`.venv/Scripts/nexus capture --help` renders and `nexus capture discover --help` shows `--group` default `ai_automation`.

- [ ] **Step 7: Commit**

```bash
git add src/nexus/capture/tables.py src/nexus/cli/commands_assess_replatform.py src/nexus/replatform/classifier.py tests/capture/test_tables.py tests/cli/test_assess_replatform_cmd.py
git commit -m "feat(replatform): developer_platform table group + multi-group inventory"
```

---

### Task 7: Global-scope customer artifacts

**Files:**
- Modify: `src/nexus/cli/commands_assess_replatform.py` (query builder + global pass)
- Modify: `src/nexus/replatform/reporter.py` (EMPTY_SOURCE_NOTICE wording)
- Test: `tests/cli/test_assess_replatform_cmd.py`, `tests/test_replatform_classifier.py`

**Interfaces:**
- Produces: `_scope_query(spec: TableSpec, scope_csv: str, *, customer_only: bool) -> str` (pure, tested); the live lister issues a second per-table pass for the `global` scope filtered by `sys_customer_update=true`, so customer-created or customer-modified global artifacts enter the inventory. Classifier needs no change: Task 4 names the domain from the global ScopeEntry's display name ("Global").
- Consumes: `ScopeDiscoverer` already surfaces the global scope when it has `sys_customer_update=true` records (scope.py:84-103 filters on exactly that flag).

- [ ] **Step 1: Write the failing tests**

Append to `tests/cli/test_assess_replatform_cmd.py`:

```python
def test_scope_query_plain_for_custom_scopes() -> None:
    spec = TableSpec(name="sys_script", display="Business Rules")
    assert _scope_query(spec, "a,b", customer_only=False) == "sys_scopeINa,b"


def test_scope_query_appends_customer_filter_for_global() -> None:
    spec = TableSpec(name="sys_script", display="Business Rules")
    assert (
        _scope_query(spec, "g1", customer_only=True)
        == "sys_scopeINg1^sys_customer_update=true"
    )
```

Append to `tests/test_replatform_classifier.py`:

```python
def test_classify_groups_global_scope_under_its_display_name() -> None:
    scopes = make_scope_manifest(
        scopes={"g1": "global"}, names={"g1": "Global"}, captured_at=_TS
    )
    catalog = make_schema_catalog(scope_to_product={})
    capture = make_capture_result(
        records=(
            make_config_record(
                sys_id="r1",
                table="sys_script",
                scope_sys_id="g1",
                fields={"name": "Incident autoclose"},
            ),
        ),
    )
    inv = classify((capture,), scopes, catalog, profile="prod")
    assert inv.use_cases[0].domain == "Global"
    assert inv.use_cases[0].workflows[0].key == "global|sys_script|incident autoclose"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/cli/test_assess_replatform_cmd.py tests/test_replatform_classifier.py -v`
Expected: `_scope_query` tests FAIL (missing function); the classifier test passes already after Task 4 -- keep it as the behavioral guard for this feature.

- [ ] **Step 3: Implement the query builder and global pass**

In `src/nexus/cli/commands_assess_replatform.py` add (pure, tested):

```python
def _scope_query(spec: TableSpec, scope_csv: str, *, customer_only: bool) -> str:
    """Build the per-table listing query for a set of scope sys_ids.

    Args:
        spec: Table being listed.
        scope_csv: Comma-joined scope sys_ids.
        customer_only: Restrict to customer-created/modified records -- used
            for the global scope, where OOB records vastly outnumber custom.

    Returns:
        An encoded sysparm query string.
    """
    query = f"{spec.scope_field}IN{scope_csv}"
    if customer_only:
        query += "^sys_customer_update=true"
    return query
```

In the lister loop, replace the single custom-scope pass: compute

```python
            custom_ids = [
                entry.sys_id
                for entry in manifest.scopes
                if entry.scope.startswith(_CUSTOM_PREFIXES)
            ]
            global_ids = [
                entry.sys_id for entry in manifest.scopes if entry.scope == "global"
            ]
```

and for each table run up to two passes --
`(custom_ids, customer_only=False)` and `(global_ids, customer_only=True)`,
skipping a pass when its id list is empty -- both using
`query=_scope_query(spec, ",".join(ids), customer_only=...)` through the same
pagination/skip logic (extract the existing paginated per-query listing into a
small inner coroutine so the two passes share it). Record
`scope_ids=tuple(custom_ids + global_ids)` on each group's `CaptureResult`.
Update the comment above the filter ("A replatform checklist cares about
CUSTOM scoped apps...") to mention the global customer-update pass.

In `src/nexus/replatform/reporter.py`, update the constant text:

```python
EMPTY_SOURCE_NOTICE = (
    "source inventory is empty -- coverage spans the configured table groups "
    "for custom scopes and customer-updated global artifacts; a clean "
    "checklist is not proof that nothing needs migrating"
)
```

(Reporter tests assert via the constant, so they keep passing; grep tests/ for
the old literal string to confirm nothing hardcodes it.)

- [ ] **Step 4: Run tests**

Run: `.venv/Scripts/python -m pytest tests/cli/test_assess_replatform_cmd.py tests/test_replatform_classifier.py tests/test_replatform_reporter.py -q && .venv/Scripts/python -m pytest -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/nexus/cli/commands_assess_replatform.py src/nexus/replatform/reporter.py tests/cli/test_assess_replatform_cmd.py tests/test_replatform_classifier.py
git commit -m "feat(replatform): include customer-updated global-scope artifacts"
```

---

### Task 8: Live validation, proof-pack refresh, docs sync

No TDD cycle -- this is the verification gate against real instances plus
documentation truth-sync. Requires fresh OAuth tokens for the `alectri` and
`retail` profiles (`nexus instance list` must show both non-expired).

- [ ] **Step 1: Full quality gates**

Run: `.venv/Scripts/python -m pytest -q && .venv/Scripts/ruff check src tests && .venv/Scripts/mypy src/nexus/ && .venv/Scripts/pyright src/nexus/ && .venv/Scripts/black --check src tests`
Expected: suite green, 0 violations, 0 errors. `.ratchet.json` coverage must not decrease.

- [ ] **Step 2: Live smoke against the proof pair**

```bash
.venv/Scripts/nexus assess inventory alectri --out artifacts/replatform-proof/inventory-alectri-v2.json
.venv/Scripts/nexus assess inventory retail --out artifacts/replatform-proof/inventory-retail-v2.json
.venv/Scripts/nexus assess migration --from alectri --to retail --out artifacts/replatform-proof/replatform-checklist-v2.md
```

Expected against the 2026-06-30 baseline (558/553 artifacts, 553 DONE / 5 TODO
/ 0 EXTRA, single Uncategorized bucket, ~10s per command):
- Artifact counts INCREASE (developer_platform + global coverage) -- record the new numbers.
- The checklist shows one section per custom application display name plus a "Global" section; "Uncategorized" appears only if a scope is genuinely unresolvable.
- Runtime stays acceptable (target < 60s per command; 13 tables + a global pass vs 5 tables before). If it exceeds that, note it -- do NOT silently reduce coverage.
- Spot-check 2 new-coverage items (one business rule, one global artifact) against raw REST (`/api/now/table/sys_script?...`) exactly as verification-summary.md did on 2026-06-30.

- [ ] **Step 3: Exercise the new flags live**

```bash
.venv/Scripts/nexus assess inventory alectri --group ai_automation
.venv/Scripts/nexus assess migration --from alectri --to retail --group developer_platform
printf "x_acme_app: Field Ops\n" > /tmp/map.yaml && .venv/Scripts/nexus assess inventory alectri --domain-map /tmp/map.yaml
```

Expected: group restriction changes coverage lines accordingly; the domain map
regroups the mapped scope; a bad group key exits 2 with the BadParameter text.

- [ ] **Step 4: Refresh proof-pack + docs**

- Update `artifacts/replatform-proof/verification-summary.md` and `capability-sheet.md` with the v2 coverage list (13 tables, global scope) and new counts.
- README: update the `nexus assess` bullet in "What is implemented" and the quick-start comment to mention developer-platform + global coverage and `--group` / `--domain-map`.
- `.primer/roadmap.md`: tick the Replatform Checklist v1 items shipped in PRs #55/#56 and add this coverage extension under the milestone; run `/primer sync` so active.md / sprint-status.yaml stop claiming the epic is backlog.

- [ ] **Step 5: Commit and open the PR**

```bash
git add artifacts/replatform-proof README.md .primer
git commit -m "docs(replatform): v2 proof pack + coverage docs for developer platform and global scope"
git push -u origin feat/2026.07-replatform-coverage
gh pr create --title "feat(replatform): close coverage and grouping gaps (developer platform, global scope, per-app domains, multiset diff)" --fill
```

---

## Out of scope (deliberate, with reasons)

- **Offline `--from-archive` diff mode** -- blocked on archives not storing a ScopeManifest (Story 06 recon note); needs an archive-format change, own plan.
- **Execution side** (`capture push` Preview/Commit, ApplyEngine v2) -- blocked on the `sys_update_xml` ACL decision (four options, `.primer/decisions.md` 2026-05-19); needs an ADR before code.
- **AI enrichment / sub-clustering** -- depends on the 2026.07 Agent Specialists epic (all stub files today). This plan's per-app naming + `--domain-map` is the deterministic bridge until then.
- **Fuzzy/renamed-artifact matching** -- explicitly out per PRD-004; revisit only with real false-TODO data from an engagement.
- **Catalog items / CMDB / notifications coverage** -- identity semantics beyond a single name field (sc_cat_item display fidelity, cmdb data-vs-config) deserve their own design pass; do not bolt onto TableSpec.
- **CLI polish** (`nexus --version`, ~3s eager `claude_agent_sdk` import chain, unified compare-conventions) -- real, small, but separate PR; not a migration-capability gap.
- **Auth breadth** (client_credentials service accounts, least-privilege role doc) -- security-review workstream, not replatform code.

## Self-review notes

- Coverage of assessment gaps: collision bug -> Task 1; unnamed artifacts -> Task 2; silent skips -> Task 3; Uncategorized collapse -> Tasks 4-5; table/scope coverage -> Tasks 6-7; live proof + doc drift -> Task 8. UX/auth/execution gaps intentionally routed to Out of scope.
- Type threads checked: `classify` keyword order (`profile`, `skipped_tables`, `overrides`) is consistent across Tasks 3/5/6; `_list_artifacts_live` return evolves once in Task 3 (3-tuple) and once in Task 6 (captures tuple) -- Task 6's signature supersedes; implementers executing tasks out of order must land Task 3 before Task 6.
- `wf_workflow` / `sysauto_script` availability varies by instance; the 400/404 skip path plus Task 3's warning makes an absent table visible instead of silent -- verified live in Task 8 Step 2.
