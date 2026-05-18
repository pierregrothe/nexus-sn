# Story 07: nexus templates command (DataTable + no-cache Hint)

Status: backlog
Spec-Clarity: high
Depends-On: 04

## Story

As a NEXUS user,
I want `nexus templates` to either show the cached catalog as a table
or tell me to run `nexus sync` if I haven't,
so that I can browse what templates are available without crashing
when no prior sync has run.

## Acceptance Criteria

AC1 (no cache):
**Given** no `manifest.json` exists under `paths.templates_dir`
**When** I run `nexus templates`
**Then** stdout shows `Hint(label="No catalog cached",
command="nexus sync")` and exit 0. Nothing else.

AC2 (cache present, empty):
**Given** a cached manifest with `templates=()`
**When** I run `nexus templates`
**Then** stdout shows `Notice.info("Catalog is empty.")` with a
footer "synced N ago via owner/name@main".

AC3 (cache present, populated):
**Given** a cached manifest with 3 entries (varied template_type)
**When** I run `nexus templates`
**Then** stdout shows a `DataTable` with columns Name / Type /
Version / Path, one row per entry, sorted by name; followed by a
footer "synced N ago via owner/name@main" via the existing
`humanize_age` helper.

AC4 (replaces the stub):
**Given** the stub `def templates_cmd()` at
`src/nexus/cli/commands_top.py:146-149`
**When** the new command lands
**Then** the stub is removed and the new command (in
`commands_sync.py` or `commands_templates.py` -- implementer's
choice; co-locate with `sync` for one-file simplicity) is the only
`@app.command("templates")`.

AC5 (help text):
**Given** `help_text.py` has a stub entry for `templates`
**When** the new entry lands
**Then** the description matches actual behavior ("show cached
template catalog"); no "(stub)" suffix.

## Must NOT

- Must NOT trigger a sync if the cache is missing. The command is
  read-only; sync is its own command.
- Must NOT re-validate the cached manifest beyond what
  `TemplateRegistry.load_manifest` does.
- Must NOT crash on a missing-cache state. AC1 enforces.

## Tasks / Subtasks

- [ ] Append `@app.command("templates")` to
      `src/nexus/cli/commands_sync.py` (single-file approach -- the
      two commands share the cache and are naturally co-located)
  - [ ] `_templates_main(*, paths, registry, console_out) -> int`
        that renders or hints
- [ ] Edit `src/nexus/cli/commands_top.py` to remove the
      `templates_cmd` stub
- [ ] Edit `src/nexus/cli/help_text.py` -- update the `templates`
      entry
- [ ] Tests in `tests/test_cli_templates.py`
  - [ ] `test_templates_prints_hint_when_cache_missing`
  - [ ] `test_templates_prints_empty_notice_when_catalog_has_no_entries`
  - [ ] `test_templates_prints_datatable_with_entries`
  - [ ] `test_templates_footer_shows_synced_age_and_source`

## Existing Code

- Reuse `DataTable` from `nexus.ui` (already used by `nexus instance
  list`).
- Reuse `humanize_age` (used by `nexus plugins outdated`).
- Reuse `TemplateRegistry.load_manifest` from story 04.

## Dev Notes

### Modules Affected

- `src/nexus/cli/commands_sync.py` (append `templates` command)
- `src/nexus/cli/commands_top.py` (remove stub)
- `src/nexus/cli/help_text.py` (entry update)
- `tests/test_cli_templates.py` (new)

### Testing Approach

- Build a populated `tmp_path/templates/manifest.json` via the real
  `TemplateRegistry.save_manifest(...)` then exercise the command.
- Capture console output to a StringIO via `Console(file=..., ...)`.

### Conventions

- Mirror the table rendering style of `nexus instance list` /
  `nexus plugins outdated`.

## References

- Brainstorming: Recommendation 5 + adversarial-review item 4
- Precedent: `src/nexus/cli/commands_instance.py:instance_list` (table
  pattern) and `nexus plugins outdated` (age footer pattern)
