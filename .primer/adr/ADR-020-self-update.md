# ADR-020: NEXUS auto-update from GitHub Releases

**Status:** accepted
**Date:** 2026-05-08
**Enforcement:** none (architectural)

## Context

The user's original three-feature ask was caching, tier detection, and
auto-update (Claude-Code style). The first two shipped (ADR-017, ADR-018).
Auto-update was deferred initially because there was no PyPI release to
update against. This ADR closes that gap.

## Decision

Add a Layer 7 `src/nexus/updater/` package with focused modules:
  - errors.py: UpdaterError (single exception, never escapes the runner)
  - current.py: current_version + is_editable_install via importlib.metadata
  - client.py: GitHubReleasesClient (httpx-based, never raises)
  - installer.py: download_wheel + pip_install_wheel (subprocess pip)
  - runner.py: check_and_maybe_update orchestrator

The CLI callback (@app.callback) invokes check_and_maybe_update before
every command. On non-editable installs, the runner:
  1. Acquires an exclusive flock on ~/.nexus/cache/update.lock.
  2. Queries /repos/pierregrothe/nexus-sn/releases/latest.
  3. If a newer version is available, downloads the wheel.
  4. Runs `python -m pip install --upgrade <wheel>`.
  5. os.execv to re-run the user's command with the new code (Linux/macOS).
     subprocess.run + sys.exit on Windows (os.execv has shell quirks).

Editable installs (pip install -e .) skip silently. NEXUS_AUTO_UPDATE=0
also skips. Any failure (network, non-200, install error, lock held)
falls back to running the current code with a log entry.

The release pipeline is rewritten: the existing PyPI-publishing workflow
is replaced with `gh release create` that attaches the built wheel to a
GitHub Release. PyPI publication is out of scope for v1 and re-enabled
later if a use case emerges.

## Consequences

  - Every nexus invocation makes one GitHub API call (~200-500ms latency,
    3s timeout). User explicitly chose this over daily-cached or
    manual-only checks.
  - First non-Pierre install (via wheel) gets auto-update behavior
    immediately.
  - Pierre's dev environment (pip install -e .) is unaffected.
  - Rollback if a release is bad: NEXUS_AUTO_UPDATE=0 + manual
    `pip install nexus-sn==<good-version>`.
  - Wheel hash verification is skipped for v1 (HTTPS is sufficient
    against MITM; a compromised repo bypasses any hash check anyway).
  - Adds packaging >= 23 as an explicit runtime dep (was transitive).

Spec: docs/superpowers/specs/2026-05-08-auto-update-design.md
Plan: docs/superpowers/plans/2026-05-08-auto-update.md
