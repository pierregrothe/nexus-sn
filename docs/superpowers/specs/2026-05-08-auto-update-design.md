# NEXUS Self-Update Design Spec

Date: 2026-05-08
Status: approved (brainstorming complete)
Author: Pierre Grothe

## Goal

NEXUS checks for new releases on GitHub at every launch, and auto-installs
them in-place (Claude Code-style). User runs `nexus apply foo`; NEXUS
silently checks GitHub, finds version `2026.06.0` available, downloads
the wheel, runs `pip install --upgrade <wheel>`, and re-execs the user's
command with the new code. Editable installs are detected and skipped
so this PR's author is unaffected during development.

## Why

The user's original request was three features (caching, tier detection,
auto-update). The first two shipped (ADR-017, ADR-018). Auto-update is
the last. The earlier deferral was correct -- there was no PyPI release
to update against. This PR closes that gap by:

1. Replacing the broken-by-default PyPI publish workflow with a
   GitHub-Releases-only workflow (no PYPI_TOKEN required).
2. Implementing the auto-update logic.
3. Cutting the first tagged release (`2026.05.1`) post-merge so
   subsequent versions have something to compare against.

The user explicitly chose every-launch + auto-install over safer
alternatives. This spec accepts that risk profile and designs for it.

## Architecture

### Module layout

```
src/nexus/updater/
  __init__.py           -- exports check_and_maybe_update, current_version,
                            is_editable_install
  errors.py             -- UpdaterError (single exception, never escapes runner)
  current.py            -- current_version() + is_editable_install()
  client.py             -- GitHubReleasesClient + ReleaseInfo
  installer.py          -- download_wheel() + pip_install_wheel()
  runner.py             -- check_and_maybe_update() -- the orchestrator

src/nexus/cli.py        -- @app.callback() invokes check_and_maybe_update
                            before every command; new `nexus update` command

.github/workflows/release.yml  -- rewritten: build wheel + gh release create
                                   (drops PyPI publish, drops PYPI_TOKEN)

tests/test_updater_*.py        -- 4 test files, ~25-30 tests
tests/fakes/fake_github_releases.py
```

### Layer placement

`updater/` is a Layer 7 module (above CLI in the dependency direction).
It depends on:
  - `cache/` (Layer 0) for the lockfile location resolution
  - `config/paths.py` for the cache directory
Imports nothing from agents/templates/assessment/etc. The CLI callback
in `cli.py` is the only consumer. Updates to `patterns.md` "Layer
dependency rule":

```
updater -> cache, config, capabilities  (Layer 7)
```

### Behavior summary

  - Every `nexus` invocation: one GitHub API call (3s timeout).
  - On new version: download wheel, pip install, os.execv to re-run.
  - On editable install: skip silently (DEBUG log).
  - On any failure: log and continue with current code. Never breaks
    the user's command.
  - Escape hatch: `NEXUS_AUTO_UPDATE=0` env var.
  - `nexus update [--check-only]` for explicit control.

## Components

### `current.py` -- version + editable detection

```python
def current_version() -> str | None:
    """Read the installed nexus-sn version via importlib.metadata.

    Returns None if the package isn't installed (e.g., running directly
    from a clone without `pip install`).
    """


def is_editable_install() -> bool:
    """True if NEXUS was installed via `pip install -e .` (PEP 660).

    Reads importlib.metadata.distribution("nexus-sn").origin.dir_info.editable.
    Returns False on any failure (package not installed, missing origin).
    """
```

`importlib.metadata` is stdlib; no new deps.

### `client.py` -- GitHub Releases API client

```python
@dataclass(slots=True, frozen=True)
class ReleaseInfo:
    """Subset of GitHub Releases API response we care about."""
    tag_name: str             # "2026.06.0"
    wheel_url: str | None     # browser_download_url of the .whl asset


class GitHubReleasesClient:
    """Tiny httpx client. Handles timeout + non-200 + rate-limit gracefully.

    Args:
        repo: "<owner>/<name>" string. Default "pierregrothe/nexus-sn".
        timeout_seconds: HTTP timeout. Default 3.0.
        httpx_client: Override the underlying client (for tests).
    """

    def __init__(
        self,
        *,
        repo: str = "pierregrothe/nexus-sn",
        timeout_seconds: float = 3.0,
        httpx_client: httpx.Client | None = None,
    ) -> None: ...

    def fetch_latest(self) -> ReleaseInfo | None:
        """GET /repos/{repo}/releases/latest.

        Returns None on:
          - network failure / timeout
          - non-200 status (404 means no releases yet, 403 is rate limit)
          - malformed JSON
          - missing tag_name
        Never raises.
        """
```

`httpx` is already a runtime dep.

### `installer.py` -- download + pip subprocess

```python
def download_wheel(url: str, *, dest_dir: Path) -> Path:
    """Stream the wheel to dest_dir/<filename-from-url>.

    Args:
        url: HTTPS wheel URL from the GitHub Releases API.
        dest_dir: Directory to write to (typically a tempfile.TemporaryDirectory).

    Returns:
        Local path to the downloaded wheel.

    Raises:
        UpdaterError: On network failure or non-200 response.
    """


def pip_install_wheel(wheel_path: Path) -> None:
    """Run subprocess: python -m pip install --upgrade <wheel_path>.

    Raises:
        UpdaterError: When pip exits non-zero. The captured stderr is
            included in the error message.
    """
```

### `runner.py` -- orchestration

```python
def check_and_maybe_update() -> None:
    """Entry point called by the CLI callback before every command.

    Returns silently in any of these cases (NEXUS continues running):
      - editable install detected
      - NEXUS_AUTO_UPDATE=0 in env
      - GitHub API call fails or times out
      - latest release has no wheel asset
      - current version >= latest version
      - install fails (logged at ERROR; never raised)
      - lockfile is held by another nexus process

    On successful install:
      - Prints "NEXUS updated <old> -> <new>"
      - Linux/macOS: os.execv(sys.argv[0], sys.argv) to re-run with new code
      - Windows: subprocess.run(sys.argv) + sys.exit(<child's exit code>)
        (os.execv on Windows has shell-prompt quirks)
    """
```

The runner acquires an exclusive flock on `~/.nexus/cache/update.lock`
before doing any update work. If the lock is held, the runner skips
silently (DEBUG log) -- the other invocation handles the update.

### `errors.py` -- `UpdaterError`

Single exception. Caught only by `runner.check_and_maybe_update()`.
Never escapes user-facing code.

### `cli.py` integration

Two changes to `cli.py`:

```python
@app.callback()
def main(
    log_level: Annotated[str, typer.Option("--log-level", envvar="NEXUS_LOG_LEVEL")] = "WARNING",
) -> None:
    """NEXUS -- ServiceNow AI architect agent."""
    _configure_logging(log_level)
    check_and_maybe_update()  # NEW


@app.command()
def update(
    check_only: Annotated[
        bool, typer.Option("--check-only", help="Only report; do not install")
    ] = False,
) -> None:
    """Manually check for updates (and install unless --check-only).

    The auto-update path runs on every command anyway; this command exists
    for explicit control: --check-only reports without installing, and
    plain `nexus update` forces a fresh check (bypassing the silent
    auto-update logic).
    """
```

## Data flow

### Happy path (new version)

1. User runs `nexus apply <template>`.
2. `@app.callback()` fires. `check_and_maybe_update()` runs.
3. is_editable_install() -> False; NEXUS_AUTO_UPDATE not "0".
4. Acquire flock on `~/.nexus/cache/update.lock`.
5. Read current version: "2026.05.1".
6. GET /repos/pierregrothe/nexus-sn/releases/latest -> ReleaseInfo("2026.06.0", "https://...whl").
7. packaging.version.parse("2026.06.0") > parse("2026.05.1") -> install.
8. Print "NEXUS updating 2026.05.1 -> 2026.06.0..."
9. download_wheel(url, dest_dir=tmpdir) -> /tmp/.../nexus_sn-2026.06.0-py3-none-any.whl
10. pip_install_wheel(path) -> subprocess pip install --upgrade
11. Release flock.
12. os.execv(sys.argv[0], sys.argv) -> process replaced with new code.
13. The new code's `apply()` handler runs with the user's argv.

### No-op path

After step 7, if version comparison is `<=`, runner releases the flock
and returns silently. The CLI command runs normally.

### Editable install path

Step 3 short-circuits. No network call, no log spam.

### Failure paths

| Failure | Behavior |
|---|---|
| GitHub API timeout (3s) | Skip; INFO log; continue. |
| GitHub returns non-200 | Skip; WARNING log; continue. |
| Latest release lacks wheel | Skip; WARNING log; continue. |
| download_wheel fails mid-stream | Delete temp file; ERROR log; continue. |
| pip install non-zero exit | ERROR log with stderr; continue. |
| os.execv fails (rare OSError) | ERROR log; sys.exit(0); user re-runs manually. |
| Lockfile held by another process | DEBUG log; skip; continue. |

### `nexus update --check-only`

```
update(check_only=True)
  - current = current_version()
  - latest = client.fetch_latest()
  - latest is None: print "Could not reach GitHub. No update info."; return
  - latest <= current: print f"Up to date ({current})"; return
  - print f"Update available: {current} -> {latest.tag_name}"
```

## Error handling and security

### HTTPS trust

NEXUS trusts api.github.com + objects.githubusercontent.com via httpx's
default TLS validation. Wheel URL comes from the GitHub API response,
which is itself fetched over HTTPS. No additional verification.

### Repo compromise

A malicious release pushed to the repo would auto-install. Mitigation
is repo-side (branch protection, required reviews on the workflow that
creates releases). Documented in ADR-020 as accepted risk.

### Wheel hash verification

Skipped for v1. HTTPS is sufficient against MITM; a compromised repo
publishes both the wheel and a matching hash, so verification only
catches network corruption (rare on HTTPS). Re-evaluate if a real
threat surfaces.

### Rollback

If the new version is broken:
1. `NEXUS_AUTO_UPDATE=0 nexus <command>` runs without checking.
2. `pip install nexus-sn==2026.05.1` (manual downgrade).
3. Pierre yanks the bad release on GitHub; auto-update sees the prior
   tag as latest.

`nexus update --pin <version>` is out of scope for v1.

### Permission issues

pip install needs write access. If it doesn't have it (e.g., system
Python without `--user`), pip exits non-zero -> caught as UpdaterError
-> log + continue. No sudo prompt.

### Cross-platform: Windows

`os.execv` on Windows has shell-prompt quirks. The runner detects
`sys.platform == "win32"` and uses `subprocess.run(sys.argv) +
sys.exit(child.returncode)` instead. Same UX from the user's perspective.

### Lockfile cleanup

`~/.nexus/cache/update.lock` is created on first use, never deleted.
The OS releases the file lock on process exit (no stale-lock recovery
needed).

### Malformed responses

`packaging.version.parse(latest.tag_name)` raises `InvalidVersion` on
non-PEP-440 tags. The runner catches this and skips with a WARNING log.
Future GitHub API changes that drop or rename the `tag_name` field are
also handled (None handling in `fetch_latest`).

## Testing

### Test files

```
tests/test_updater_current.py      -- ~5 tests
tests/test_updater_client.py       -- ~6 tests (httpx.MockTransport)
tests/test_updater_installer.py    -- ~5 tests (subprocess.run patched)
tests/test_updater_runner.py       -- ~10 tests (orchestration)
tests/fakes/fake_github_releases.py -- FakeGitHubReleasesClient
```

### Network isolation

`GitHubReleasesClient.__init__` takes `httpx_client: httpx.Client | None = None`.
Tests pass an `httpx.Client(transport=httpx.MockTransport(...))`.
Production passes None (default client built internally). Pattern matches
`ServiceNowClient` testing.

### Editable install detection tests

Three scenarios:
1. Editable: in dev env, `is_editable_install()` should return True
   directly. One integration test.
2. Wheel install: monkeypatch `importlib.metadata.distribution` to return
   a fake `Distribution` with `origin.dir_info.editable = False`.
3. Not installed: monkeypatch to raise `PackageNotFoundError`;
   `current_version()` returns None.

### Installer subprocess tests

`pip_install_wheel` calls `subprocess.run([sys.executable, "-m", "pip",
"install", "--upgrade", str(wheel_path)])`. Tests do NOT actually run
pip; instead, monkeypatch `subprocess.run` to return CompletedProcess
with the desired returncode + stderr. Verify call args.

This is the documented exception to the no-mocks rule (CLAUDE.md).

### Runner tests (highest value)

```python
def test_runner_skips_when_editable_install(...) -> None: ...
def test_runner_skips_when_env_var_disables(monkeypatch) -> None: ...
def test_runner_skips_when_github_api_fails(...) -> None: ...
def test_runner_skips_when_already_current(...) -> None: ...
def test_runner_installs_and_re_execs_when_newer_version(monkeypatch) -> None: ...
def test_runner_continues_when_install_fails(...) -> None: ...
def test_runner_skips_when_lockfile_held(...) -> None: ...
```

For re-exec: monkeypatch `os.execv` to record the args instead of
replacing the process; assert called with `(sys.argv[0], sys.argv)`.

For lockfile concurrency: simulate a held lock via fcntl.flock on a
temp file; verify the runner's lock acquisition skips gracefully.

### Coverage target

100% on `nexus.updater.*` per project gate. Test count: ~25-30.

### Manual verification (one-time)

The release pipeline change can't be unit-tested. Post-merge steps:

1. Tag `2026.05.1` on main: `git tag 2026.05.1 && git push --tags`.
2. Verify a GitHub Release is created with the wheel attached.
3. Install NEXUS from the wheel: `pip install <downloaded-wheel>`.
4. Run `nexus update --check-only`. Should report current = 2026.05.1.
5. Bump version in pyproject.toml, push tag `2026.05.2`. Run `nexus`
   from the wheel install. Should auto-update.

## Migration

### What ships

- `src/nexus/updater/` package (5 modules + `__init__.py`).
- CLI integration (callback hook + `nexus update` command).
- `release.yml` rewrite: GitHub Release creation, no PyPI.
- `packaging >= 23` declared explicitly in pyproject.toml.
- ADR-020, governance.md catalog row, decisions.md entry, ratchet.json
  baselines.
- First tagged release (post-merge manual step).

### Cutover

1. PR merges to main.
2. Pierre tags `2026.05.1`.
3. New release.yml runs; GitHub Release created with wheel.
4. Future PRs that bump pyproject.toml + tag will auto-create releases.
5. First non-Pierre install (via wheel) gets auto-update behavior.

### Backwards compatibility

Auto-updater only activates on non-editable installs. Pierre's
`pip install -e .` dev environment is unaffected.

### Out of scope

  - PyPI publication (separate PR if/when needed).
  - `nexus update --pin <version>` rollback support.
  - Wheel hash verification.
  - Pre-release / beta channels (only `releases/latest` is checked).
  - Per-version skip mechanism.
  - Background (non-blocking) update.
  - Telemetry on update events.

### Coverage ratchet

`.ratchet.json` gains entries for `nexus.updater`,
`nexus.updater.client`, `nexus.updater.current`, `nexus.updater.errors`,
`nexus.updater.installer`, `nexus.updater.runner` -- plus a small bump
on `nexus.cli`.

### Rollback for THIS PR

If the auto-updater itself is buggy:
- `git revert <PR-merge-commit>` on main.
- Cherry-pick the harmless parts (release.yml fix, packaging dep) into
  a follow-up PR.
