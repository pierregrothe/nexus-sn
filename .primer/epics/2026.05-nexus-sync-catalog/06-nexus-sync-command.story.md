# Story 06: nexus sync command (commands_sync.py)

Status: done
Spec-Clarity: high
Depends-On: 05

## Story

As a NEXUS user who has just finished `nexus setup`,
I want `nexus sync` to pull the template catalog into my local cache
and tell me how many templates are available,
so that I can immediately follow it with `nexus templates` to see
what's there.

## Acceptance Criteria

AC1 (no-config exit 1):
**Given** `~/.nexus/config.yaml` has `github_repo: ""`
**When** I run `nexus sync`
**Then** stderr shows
`Notice.error("Template registry not configured")` + a Hint pointing
at the config file and the exit code is 1.

AC2 (invalid-repo exit 1):
**Given** `github_repo: "https://github.com/owner/name"`
**When** I run `nexus sync`
**Then** stderr shows `Notice.error` containing the reason from
`InvalidGitHubRepoError` ("url not allowed") and exit 1.

AC3 (happy path exit 0):
**Given** the orchestrator returns `outcome="ok"` with a
`CachedManifest` whose wire has 3 entries
**When** the command runs
**Then** stdout shows `Notice.info("Synced 3 templates from
owner/name@main.")` and exit 0.

AC4 (empty catalog exit 0):
**Given** the orchestrator returns `outcome="ok"` with `templates=()`
**When** the command runs
**Then** stdout shows `Notice.info("Synced 0 templates from
owner/name@main.")` and exit 0.

AC5 (fetch-failed exit 1):
**Given** the orchestrator returns `outcome="fetch-failed",
reason="cache write failed: OSError"`
**When** the command runs
**Then** stderr shows the reason and exit 1.

AC6 (replaces the stub):
**Given** the stub at `src/nexus/cli/commands_top.py:139` (the old
`sync` def)
**When** the new module is imported in `cli/__init__.py`
**Then** the stub is removed and the new command is the only
`@app.command sync`.

AC7 (help text updated):
**Given** `src/nexus/cli/help_text.py` had a stub entry for sync
**When** the new entry lands
**Then** the description matches actual behavior ("pull template
catalog from GitHub"); no "(stub)" suffix.

## Must NOT

- Must NOT call `sys.exit` directly. Use `typer.Exit(1)` so Typer's
  context cleanup runs.
- Must NOT depend on the `nexus.cli.commands_setup` module (no
  cross-command imports).
- Must NOT log secrets / config payloads.
- Must NOT silently auto-create the cache directory if the user has
  not run `setup` yet -- if `paths.templates_dir.parent` does not
  exist, surface as a fetch-failed reason.

## Tasks / Subtasks

- [ ] Create `src/nexus/cli/commands_sync.py`
  - [ ] File header + docstrings + `__all__: list[str] = []`
  - [ ] `@app.command sync()` -- 5-line wrapper around `_sync_main`
  - [ ] `_sync_main(*, paths, config_manager, client, registry,
        console_out, console_err) -> int` returns 0/1
  - [ ] Build a `GitHubSync` instance, call `.run(...)`, match on
        outcome, render Notice/Hint
- [ ] Edit `src/nexus/cli/commands_top.py` to remove the stub `def
      sync` (story 5 of setup had the precedent)
- [ ] Edit `src/nexus/cli/__init__.py` to import `commands_sync` for
      decorator side-effects (mirror `commands_setup` line)
- [ ] Edit `src/nexus/cli/help_text.py:418-421` -- update the `sync`
      entry text
- [ ] Tests in `tests/test_cli_sync.py`
  - [ ] `test_sync_returns_1_when_github_repo_empty`
  - [ ] `test_sync_returns_1_when_github_repo_is_url`
  - [ ] `test_sync_returns_0_on_happy_path_and_writes_cache`
  - [ ] `test_sync_returns_0_on_empty_catalog`
  - [ ] `test_sync_returns_1_when_fetch_fails`
  - [ ] `test_sync_returns_1_when_registry_oserror_during_save`
  - [ ] `test_sync_prints_count_and_repo_in_summary`

## Existing Code

- Mirror `src/nexus/cli/commands_setup.py` (Typer wrapper + `_main`).
- Reuse `nexus.config.manager.ConfigManager` to read `github_repo` /
  `github_branch`.
- Reuse `nexus.config.paths.NexusPaths.from_env()`.

## Dev Notes

### Modules Affected

- `src/nexus/cli/commands_sync.py` (new)
- `src/nexus/cli/commands_top.py` (remove sync stub)
- `src/nexus/cli/__init__.py` (import side effect)
- `src/nexus/cli/help_text.py` (entry update)
- `tests/test_cli_sync.py` (new)

### Testing Approach

- Drive `_sync_main` directly with injected `GitHubTemplateClient`
  subclass + real `TemplateRegistry` under `tmp_path`.
- Use `Console(file=io.StringIO(), force_terminal=False)` to capture
  output for assertions on rendered messages.

### Conventions

- Mirror the setup-command testing approach exactly.

## References

- Brainstorming: Recommendation 4, Failure-mode table
- Precedent: `src/nexus/cli/commands_setup.py` + `tests/test_cli_setup.py`
