# /simplify Lessons Learned Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land ADR-019 governance reframe in one PR: introduce `ExternalKeychainClient`, fix `@cached(persist=True)` lazy-binding, add three Semgrep rules, and add a PR template that gates `/simplify` execution.

**Architecture:** Bundle four lessons-learned threads. (1) Layer-2 wrapper class for reading external apps' keychain entries with explicit `service_prefix=""`. (2) One-line decorator change to lazy-resolve the disk backend per call instead of capturing it at decoration time. (3) Three Semgrep rules to encode recurring style smells. (4) PR template + ADR-019 commitment for /simplify-before-merge.

**Tech Stack:** Python 3.14, existing `keyring` dep, existing semgrep tooling, existing @cached decorator from ADR-017.

---

## File Map

```
ADD:
  src/nexus/auth/external_keychain.py             -- ExternalKeychainClient(KeychainClient) thin subclass
  tests/test_external_keychain.py                 -- 1 test
  .github/PULL_REQUEST_TEMPLATE.md                -- 3-section template with /simplify checkbox
  .primer/adr/ADR-019-simplify-lessons-learned.md -- the ADR

MODIFY:
  src/nexus/auth/__init__.py                      -- export ExternalKeychainClient
  src/nexus/cli.py                                -- _detect_tier uses ExternalKeychainClient()
  src/nexus/cache/decorator.py                    -- lazy-resolve disk backend (one-line change)
  tests/test_cache_decorator.py                   -- regression test for lazy-resolve
  .semgrep/rules.yml                              -- 3 new rules
  .ratchet.json                                   -- new module entry + bumps for cli + decorator
  .primer/governance.md                           -- 3 new gates + ADR-019 catalog row
  .primer/decisions.md                            -- append ADR-019 entry
```

---

## Task 1: ExternalKeychainClient + test

**Files:**
- Create: `src/nexus/auth/external_keychain.py`
- Create: `tests/test_external_keychain.py`
- Modify: `src/nexus/auth/__init__.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_external_keychain.py`:

```python
# tests/test_external_keychain.py
# Test for ExternalKeychainClient -- the wrapper that bypasses the "nexus" prefix.
# Author: Pierre Grothe
# Date: 2026-05-08
"""Tests for nexus.auth.external_keychain."""

from nexus.auth.external_keychain import ExternalKeychainClient
from nexus.auth.keychain import KeychainClient


def test_external_keychain_client_uses_empty_prefix() -> None:
    client = ExternalKeychainClient()
    assert client._prefix == ""


def test_external_keychain_client_is_a_keychain_client() -> None:
    """Verify subclass relationship for type checks at call sites."""
    client = ExternalKeychainClient()
    assert isinstance(client, KeychainClient)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/test_external_keychain.py -v --override-ini="addopts="
```

Expected: ImportError on `nexus.auth.external_keychain`.

- [ ] **Step 3: Implement the wrapper**

Create `src/nexus/auth/external_keychain.py`:

```python
# src/nexus/auth/external_keychain.py
# Keychain reader for credentials NOT owned by NEXUS (e.g., Claude Code).
# Author: Pierre Grothe
# Date: 2026-05-08
"""ExternalKeychainClient: read keychain entries that other apps own.

NEXUS-owned secrets use KeychainClient with the default service_prefix="nexus"
(so our keys live under "nexus-<service>"). Reading other apps' keychain
entries -- like Claude Code's "Claude Code-credentials" -- requires
service_prefix="" so the lookup uses the literal service name. This wrapper
makes that intent explicit at every call site and pairs with the
external-keychain Semgrep rule (ADR-019).
"""

from nexus.auth.keychain import KeychainClient

__all__ = ["ExternalKeychainClient"]


class ExternalKeychainClient(KeychainClient):
    """KeychainClient configured for reading external apps' credentials.

    Calls KeychainClient.__init__ with service_prefix="" so .get(service, user)
    reads the literal service name without the "nexus-" prefix. Use this for
    credentials owned by other apps (Claude Code, Anthropic CLI, etc.). For
    NEXUS-owned secrets, use KeychainClient() with the default prefix.
    """

    def __init__(self) -> None:
        """Initialize with empty service prefix."""
        super().__init__(service_prefix="")
```

- [ ] **Step 4: Update src/nexus/auth/__init__.py**

Read the file first. Add the import + export:

```python
from nexus.auth.claude import ClaudeAuth
from nexus.auth.errors import AuthError
from nexus.auth.external_keychain import ExternalKeychainClient
from nexus.auth.keychain import KeychainClient
from nexus.auth.servicenow import SNAuth

__all__ = [
    "AuthError",
    "ClaudeAuth",
    "ExternalKeychainClient",
    "KeychainClient",
    "SNAuth",
]
```

- [ ] **Step 5: Run tests + lint**

```bash
.venv/bin/pytest tests/test_external_keychain.py -v --override-ini="addopts="
.venv/bin/ruff check src/nexus/auth/external_keychain.py tests/test_external_keychain.py
.venv/bin/mypy src/nexus/auth/external_keychain.py
.venv/bin/pyright src/nexus/auth/external_keychain.py
```

Expected: 2 tests pass; 0 violations; 0 errors.

- [ ] **Step 6: Commit**

```bash
git add src/nexus/auth/external_keychain.py src/nexus/auth/__init__.py tests/test_external_keychain.py && git commit -m "feat(auth): add ExternalKeychainClient for reading other apps' keychain entries"
```

---

## Task 2: cli.py call-site swap

**Files:**
- Modify: `src/nexus/cli.py`

- [ ] **Step 1: Update the import**

Read `src/nexus/cli.py`. Find the import block. Replace:

```python
from nexus.auth.keychain import KeychainClient
```

with:

```python
from nexus.auth.external_keychain import ExternalKeychainClient
```

(Drop the `KeychainClient` import; `_detect_tier` is the only consumer and it now uses the wrapper.)

- [ ] **Step 2: Update _detect_tier**

Find `_detect_tier()`. Replace:

```python
def _detect_tier() -> TierDetection:
    """Run tier detection using a Claude-Code-aware keychain reader."""
    reader = FilesystemClaudeCodeConfigReader(keychain=KeychainClient(service_prefix=""))
    return TierDetector(reader=reader).detect()
```

with:

```python
def _detect_tier() -> TierDetection:
    """Run tier detection using a Claude-Code-aware keychain reader."""
    reader = FilesystemClaudeCodeConfigReader(keychain=ExternalKeychainClient())
    return TierDetector(reader=reader).detect()
```

- [ ] **Step 3: Run all tests + lint**

```bash
.venv/bin/pytest tests/test_cli_status.py -v --override-ini="addopts="
.venv/bin/ruff check src/nexus/cli.py
.venv/bin/mypy src/nexus/cli.py
.venv/bin/pyright src/nexus/cli.py
```

Expected: 5 cli_status tests pass; 0 violations; 0 errors.

- [ ] **Step 4: Verify end-to-end against the real keychain**

```bash
.venv/bin/python -c "
from nexus.auth.external_keychain import ExternalKeychainClient
from nexus.capabilities.claude_config import FilesystemClaudeCodeConfigReader
from nexus.capabilities.tier import TierDetector
reader = FilesystemClaudeCodeConfigReader(keychain=ExternalKeychainClient())
det = TierDetector(reader=reader).detect()
print('tier:', det.tier)
print('servers:', sorted(s.value for s in det.detected_servers))
"
```

Expected: `tier: enterprise` with 5 SN servers (Pierre's machine; on a non-Enterprise machine it will report `tier: anonymous` which is also correct).

- [ ] **Step 5: Commit**

```bash
git add src/nexus/cli.py && git commit -m "refactor(cli): use ExternalKeychainClient at the Claude Code keychain call site"
```

---

## Task 3: @cached(persist=True) lazy-resolve fix + regression test

**Files:**
- Modify: `src/nexus/cache/decorator.py`
- Modify: `tests/test_cache_decorator.py`

- [ ] **Step 1: Write the failing regression test**

Append to `tests/test_cache_decorator.py`:

```python
def test_cached_persist_uses_redirected_disk_root_after_monkeypatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify lazy-resolve: monkeypatch + cache clear -> next call uses new path."""
    from nexus.cache import decorator as decorator_module

    cache_a = tmp_path / "a"
    monkeypatch.setattr(decorator_module, "_disk_cache_root", lambda: cache_a)
    decorator_module._DISK_BACKENDS.clear()

    calls: list[int] = []

    @cached(ttl=None, persist=True, namespace="lazy_test")
    def heavy(x: int) -> int:
        calls.append(x)
        return x * 10

    assert heavy(3) == 30
    assert calls == [3]

    cache_b = tmp_path / "b"
    monkeypatch.setattr(decorator_module, "_disk_cache_root", lambda: cache_b)
    decorator_module._DISK_BACKENDS.clear()

    assert heavy(3) == 30
    assert calls == [3, 3]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/pytest tests/test_cache_decorator.py::test_cached_persist_uses_redirected_disk_root_after_monkeypatch -v --override-ini="addopts="
```

Expected: FAIL -- `assert calls == [3, 3]` actually shows `[3]` because the wrapper still holds the old `cache_a` backend.

- [ ] **Step 3: Apply the lazy-resolve fix**

Edit `src/nexus/cache/decorator.py`. Find the persist branch around line 139:

```python
        if persist:
            disk_backend = _get_or_create_disk_backend(namespace)

            def get_disk_backend(_first_arg: object) -> CacheBackend:
                return disk_backend

            return _wrap_with_backend(
```

Replace with:

```python
        if persist:
            # Lazy-resolve: the wrapper looks up the backend on every call
            # instead of capturing it at decoration time. Tests can
            # monkeypatch _disk_cache_root and clear _DISK_BACKENDS between
            # tests; the next call picks up the new path. The dict lookup
            # adds ~50ns per call (negligible compared to disk I/O).
            def get_disk_backend(_first_arg: object) -> CacheBackend:
                return _get_or_create_disk_backend(namespace)

            return _wrap_with_backend(
```

(Delete the `disk_backend = _get_or_create_disk_backend(namespace)` line and the `return disk_backend` becomes `return _get_or_create_disk_backend(namespace)`.)

- [ ] **Step 4: Run the regression test to verify it passes**

```bash
.venv/bin/pytest tests/test_cache_decorator.py::test_cached_persist_uses_redirected_disk_root_after_monkeypatch -v --override-ini="addopts="
```

Expected: PASS.

- [ ] **Step 5: Run the full cache test suite**

```bash
.venv/bin/pytest tests/test_cache_decorator.py tests/test_cache_backends.py tests/test_cache_keys.py -v --override-ini="addopts="
```

Expected: all prior cache tests still pass + the new regression test (1 added).

- [ ] **Step 6: Lint + types**

```bash
.venv/bin/ruff check src/nexus/cache/decorator.py
.venv/bin/mypy src/nexus/cache/decorator.py
.venv/bin/pyright src/nexus/cache/decorator.py
```

Expected: 0 violations, 0 errors.

- [ ] **Step 7: Commit**

```bash
git add src/nexus/cache/decorator.py tests/test_cache_decorator.py && git commit -m "fix(cache): lazy-resolve disk backend in @cached(persist=True) per call"
```

---

## Task 4: Three Semgrep rules

**Files:**
- Modify: `.semgrep/rules.yml`

- [ ] **Step 1: Append the three new rules**

Read `.semgrep/rules.yml` first. Append these 3 rule blocks to the existing `rules:` list:

```yaml
  - id: external-keychain-must-use-wrapper
    languages: [python]
    severity: ERROR
    message: |
      Direct use of KeychainClient(service_prefix=...) is forbidden in src/nexus/.
      For NEXUS-owned secrets, use the default KeychainClient(). For reading
      other apps' keychain entries (e.g., Claude Code's), use
      ExternalKeychainClient() from nexus.auth (ADR-019).
    paths:
      include: ["**/src/nexus/**"]
    pattern-either:
      - pattern: KeychainClient(service_prefix=$X)
      - pattern: KeychainClient(service_prefix=$X, ...)
    metadata:
      adr: ADR-019
      category: governance

  - id: no-stub-see-docstring
    languages: [python]
    severity: ERROR
    message: |
      Stub docstrings like '"""See OtherClass.method."""' add no value.
      Either copy the canonical docstring or write a one-line behavior
      description (ADR-019).
    paths:
      include: ["**/src/nexus/**"]
    pattern-regex: '"""See [A-Z][A-Za-z]+\.[a-z_]+\.\s*"""'
    metadata:
      adr: ADR-019
      category: governance

  - id: enum-shadowing-label-dict
    languages: [python]
    severity: WARNING
    message: |
      A module-level dict[<EnumType>, str] mapping enum members to strings
      duplicates the enum's value field. Add a property to the enum
      (e.g., def label(self) -> str: return self.value.capitalize()) or call
      .value directly. Caught _TIER_LABEL in PR #6 (ADR-019).
    paths:
      include: ["**/src/nexus/**"]
    pattern: |
      $NAME: dict[$ENUM, str] = {
          ...
      }
    metadata:
      adr: ADR-019
      category: governance
```

- [ ] **Step 2: Validate the ruleset**

```bash
/Users/pierre.grothe/.local/bin/semgrep --config .semgrep/rules.yml --validate 2>&1 | tail -3
```

Expected: `Configuration is valid - found 0 configuration error(s), and 8 rule(s).` (was 5; +3).

- [ ] **Step 3: Verify no false positives in the project**

```bash
/Users/pierre.grothe/.local/bin/semgrep --config .semgrep/rules.yml src/ tests/ --error 2>&1 | tail -5
```

Expected: `Ran 8 rules on 8X files: 0 findings.` (existing code is clean post-PR-#6 simplify).

- [ ] **Step 4: Test rule 1 against a synthetic violation**

```bash
mkdir -p /tmp/sg_test/src/nexus
cat > /tmp/sg_test/src/nexus/violation.py <<'EOF'
from nexus.auth.keychain import KeychainClient

bad = KeychainClient(service_prefix="something")
EOF
cd /tmp/sg_test && /Users/pierre.grothe/.local/bin/semgrep --config /Users/pierre.grothe/Developer/nexus/.semgrep/rules.yml src/ --error 2>&1 | grep -E "Findings|❯❯❱" | head -3
cd /Users/pierre.grothe/Developer/nexus && rm -rf /tmp/sg_test
```

Expected: 1 finding -- `external-keychain-must-use-wrapper`.

- [ ] **Step 5: Test rule 2 against a synthetic violation**

```bash
mkdir -p /tmp/sg_test/src/nexus
cat > /tmp/sg_test/src/nexus/violation.py <<'EOF'
class Foo:
    def bar(self) -> int:
        """See FooProtocol.bar."""
        return 1
EOF
cd /tmp/sg_test && /Users/pierre.grothe/.local/bin/semgrep --config /Users/pierre.grothe/Developer/nexus/.semgrep/rules.yml src/ --error 2>&1 | grep -E "Findings|❯❯❱" | head -3
cd /Users/pierre.grothe/Developer/nexus && rm -rf /tmp/sg_test
```

Expected: 1 finding -- `no-stub-see-docstring`.

- [ ] **Step 6: Test rule 3 against a synthetic violation**

```bash
mkdir -p /tmp/sg_test/src/nexus
cat > /tmp/sg_test/src/nexus/violation.py <<'EOF'
from enum import StrEnum

class Tier(StrEnum):
    A = "a"
    B = "b"

LABELS: dict[Tier, str] = {
    Tier.A: "Alpha",
    Tier.B: "Beta",
}
EOF
cd /tmp/sg_test && /Users/pierre.grothe/.local/bin/semgrep --config /Users/pierre.grothe/Developer/nexus/.semgrep/rules.yml src/ --error 2>&1 | grep -E "Findings|❯❯❱" | head -3
cd /Users/pierre.grothe/Developer/nexus && rm -rf /tmp/sg_test
```

Expected: 1 finding -- `enum-shadowing-label-dict` (severity WARNING; will appear under WARNINGS, not blocking).

(If Rule 3 fires as expected on the synthetic but produces false positives on production code in Step 3, refine the pattern or accept the WARNING-level noise.)

- [ ] **Step 7: Run pre-commit on all files**

```bash
.venv/bin/pre-commit run --all-files 2>&1 | tail -8
```

Expected: 6/6 hooks pass.

- [ ] **Step 8: Commit**

```bash
git add .semgrep/rules.yml && git commit -m "feat(governance): 3 new semgrep rules from /simplify lessons (ADR-019)"
```

---

## Task 5: PR template

**Files:**
- Create: `.github/PULL_REQUEST_TEMPLATE.md`

- [ ] **Step 1: Create the template**

Write `.github/PULL_REQUEST_TEMPLATE.md`:

```markdown
## Summary

<!-- 1-3 bullets describing what this PR does and why -->

## Test plan

- [ ] Unit tests added/updated for new behavior
- [ ] All 6 pre-commit hooks pass (black, ruff, mypy, pyright, semgrep, pytest)

## Pre-merge gates (ADR-019)

- [ ] `/simplify` run on the branch and all findings addressed (or explicitly skipped with reason)
- [ ] If this PR adds a new ADR, governance.md catalog row added
- [ ] If this PR adds new public API, file headers + Google docstrings present

## Out of scope (deferred)

<!-- What you considered but explicitly didn't do, with reasons -->
```

- [ ] **Step 2: Verify GitHub picks it up**

The file path is `.github/PULL_REQUEST_TEMPLATE.md` (case-sensitive). GitHub auto-loads it for new PRs once committed.

- [ ] **Step 3: Commit**

```bash
git add .github/PULL_REQUEST_TEMPLATE.md && git commit -m "feat(repo): PR template with /simplify checkbox (ADR-019)"
```

---

## Task 6: ADR-019 + governance + decisions + ratchet

**Files:**
- Create: `.primer/adr/ADR-019-simplify-lessons-learned.md`
- Modify: `.primer/governance.md`
- Modify: `.primer/decisions.md`
- Modify: `.ratchet.json`

- [ ] **Step 1: Generate coverage numbers**

```bash
.venv/bin/pytest --cov=nexus --cov-report=json --cov-fail-under=0 -q --override-ini="addopts="
.venv/bin/python -c "
import json
data = json.load(open('coverage.json'))
for path, info in sorted(data['files'].items()):
    if 'auth/external_keychain' in path or 'cache/decorator' in path or '/cli.py' in path:
        s = info['summary']
        print(path, '-> covered=' + str(s['covered_lines']), 'total=' + str(s['num_statements']))
"
```

- [ ] **Step 2: Update .ratchet.json**

Read `.ratchet.json`. Add a new entry for `nexus.auth.external_keychain`. Update `nexus.cache.decorator` and `nexus.cli` to the new numbers from Step 1 (the decorator change is one line; cli is one substitution).

```json
    "nexus.auth.external_keychain": {"covered_lines": <N>, "total_lines": <N>},
```

(Where `<N>` is from Step 1 output.)

- [ ] **Step 3: Create ADR-019**

Write `.primer/adr/ADR-019-simplify-lessons-learned.md`:

```markdown
# ADR-019: Lessons from /simplify reviews

**Status:** accepted
**Date:** 2026-05-08
**Enforcement:** semgrep (3 new rules) + PR template + ADR commitment

## Context

Three /simplify sessions (PRs #2, #5, #6) caught real issues every time:

  - PR #2 (Agent SDK migration): efficiency findings (qualname recomputed
    per call, double-scan for unhashable args), code-quality findings
    (dead permissive_func parameter, stub docstrings).
  - PR #5 (cached decorator): style findings (over-engineered _Missing
    singleton, dead-code branches).
  - PR #6 (tier detection): the CRITICAL bug
    (KeychainClient(service_prefix="nexus") silently mismatched the
    Claude Code keychain key) plus an architectural limitation
    (@cached(persist=True) decoration-time backend capture broke test
    isolation, forcing a workaround).

The keychain bug almost shipped. Pre-commit hooks didn't catch it; tests
didn't catch it; only review caught it. The other findings are smaller
but recurring. Together they justify codifying the lessons.

## Decision

Bundle four threads into one PR:

1. **External-system credential reads** -- introduce
   ExternalKeychainClient(KeychainClient) thin subclass that calls
   super().__init__(service_prefix=""). Add Semgrep rule
   external-keychain-must-use-wrapper banning direct
   KeychainClient(service_prefix=...) usage in src/nexus/. Forces every
   call site to declare intent: KeychainClient() for NEXUS-owned secrets,
   ExternalKeychainClient() for other apps' secrets.

2. **@cached(persist=True) lazy-resolve.** Move
   _get_or_create_disk_backend(namespace) from decoration time into the
   wrapper. Tests can monkeypatch _disk_cache_root and clear
   _DISK_BACKENDS between tests; the next call picks up the new path.
   AgentClient adoption (deferred per ADR-017) is now unblocked.

3. **Three new Semgrep rules** for recurring style smells:
   external-keychain-must-use-wrapper, no-stub-see-docstring,
   enum-shadowing-label-dict (last one WARNING-only as heuristic). The
   "single-use module-private helper" pattern was considered but
   skipped -- Semgrep cannot detect it reliably.

4. **/simplify before merge as a process gate** via PR template
   checkbox. Solo-dev honor system, but the unchecked box is
   review-visible.

## Consequences

  - The keychain pattern bug class is closed. Adding a new external-app
    keychain reader requires using ExternalKeychainClient or fighting
    the Semgrep rule.
  - @cached(persist=True) is test-friendly. AgentClient.complete can
    adopt persist caching in a future PR without the disk-backend
    capture issue.
  - Three new lint rules. The enum-shadowing rule is heuristic
    (WARNING) and may produce false positives; refine on first hit.
  - PR template is a soft gate; it does not block merge. The value is
    in the conscious /simplify-or-skip choice it forces.
  - Adds nexus.auth.external_keychain module (~7 lines of code).

Spec: docs/superpowers/specs/2026-05-08-simplify-lessons-design.md
Plan: docs/superpowers/plans/2026-05-08-simplify-lessons.md
```

- [ ] **Step 4: Update .primer/governance.md**

Add three new lines under "Tier 1 -- Blocking (semgrep, semantic governance, ADR-016 + ADR-017)":

```markdown
- external-keychain-must-use-wrapper -- KeychainClient(service_prefix=...) forbidden in src/nexus/; use ExternalKeychainClient (ADR-019)
- no-stub-see-docstring -- '"""See OtherClass.method."""' stub docstrings forbidden (ADR-019)
- enum-shadowing-label-dict -- WARNING: dict[<EnumType>, str] duplicates the enum's value field (ADR-019)
```

(Update the section header to read `ADR-016 + ADR-017 + ADR-019`.)

Append to the ADR catalog:

```markdown
| 019 | Lessons from /simplify reviews | semgrep + PR template + ADR | accepted |
```

- [ ] **Step 5: Append to .primer/decisions.md**

```markdown


---

### 2026-05-08 -- Lessons from /simplify reviews (ADR-019)

**Status:** accepted

**Context:** Three /simplify sessions (PRs #2, #5, #6) caught real issues
every time, including a CRITICAL keychain-prefix bug in PR #6 that pre-
commit and tests missed. Recurring style smells (enum-shadowing dict,
stub "See" docstrings, hot-path attribute access) appeared across PRs.
The @cached(persist=True) decoration-time backend capture broke test
isolation in PR #6, forcing a fallback to ttl=None.

**Decision:** Bundled PR codifies four threads: ExternalKeychainClient
wrapper for cross-app keychain reads, @cached(persist=True) lazy-resolve
fix, three new Semgrep rules, and a PR template gating /simplify
execution.

**Consequences:** The keychain pattern bug class is closed. @cached
persist mode is test-friendly (AgentClient adoption unblocked). Three
new lint rules trace to ADR-019. PR template is a soft gate; the
unchecked /simplify checkbox is review-visible. Spec at
docs/superpowers/specs/2026-05-08-simplify-lessons-design.md.
```

- [ ] **Step 6: Run pre-commit**

```bash
.venv/bin/pre-commit run --all-files 2>&1 | tail -8
```

Expected: 6/6 hooks pass.

- [ ] **Step 7: Commit**

```bash
git add .primer/ .ratchet.json && git commit -m "docs: ADR-019 simplify lessons learned + governance + ratchet"
```

---

## Task 7: Push + open PR

- [ ] **Step 1: Push**

```bash
git push -u origin chore/simplify-lessons-adr-019
```

- [ ] **Step 2: Open the PR**

The repo now has the PR template from Task 5. Opening via `gh pr create` without `--body` will pre-populate the template; pass `--body` to override:

```bash
gh pr create --title "chore: /simplify lessons learned (ADR-019)" --body "$(cat <<'EOF'
## Summary

- Add `ExternalKeychainClient` wrapper for reading other apps' keychain entries (ADR-019).
- Fix `@cached(persist=True)` lazy-binding so tests can isolate the disk cache.
- Three new Semgrep rules: external-keychain-must-use-wrapper, no-stub-see-docstring, enum-shadowing-label-dict.
- New `.github/PULL_REQUEST_TEMPLATE.md` with /simplify checkbox.

## Test plan

- [x] Unit tests added/updated (`tests/test_external_keychain.py`, regression test in `tests/test_cache_decorator.py`)
- [x] All 6 pre-commit hooks pass (black, ruff, mypy, pyright, semgrep, pytest)

## Pre-merge gates (ADR-019)

- [x] `/simplify` -- this IS the simplify-driven PR; the lessons are the content. No additional /simplify pass required.
- [x] ADR-019 added to governance.md catalog
- [x] New public API (`ExternalKeychainClient`) has file header + Google docstrings

## Why

The CRITICAL bug in PR #6 (KeychainClient default prefix mismatch) was caught only by /simplify review, not by hooks or tests. The other findings are smaller but recurring. ADR-019 codifies the lessons.

Spec: `docs/superpowers/specs/2026-05-08-simplify-lessons-design.md`
Plan: `docs/superpowers/plans/2026-05-08-simplify-lessons.md`
ADR-019: `.primer/adr/ADR-019-simplify-lessons-learned.md`

## Out of scope (deferred)

- AgentClient adopting `@cached(persist=True)` for LLM result caching (separate PR when there's a real cost-saving reason).
- An AST-walking helper for the dropped "single-use private helper" rule (convention only).

Generated with Claude Code
EOF
)"
```

Expected: PR URL printed.

---

## Self-Review Notes

- All 7 tasks have explicit code and exact commands. The only `<N>` placeholder is in Task 6 Step 2 (ratchet baseline numbers); Step 1 of the same task generates them.
- Type consistency:
  - `ExternalKeychainClient()` no-arg constructor used in Tasks 1, 2.
  - `_get_or_create_disk_backend(namespace)` signature unchanged across Tasks 3.
  - All Semgrep rule IDs (`external-keychain-must-use-wrapper`, `no-stub-see-docstring`, `enum-shadowing-label-dict`) match across Tasks 4, 6 (ADR/governance/decisions).
- Spec coverage:
  - Architecture file map (spec) -> Tasks 1-6 cover every entry.
  - Components: ExternalKeychainClient -> Task 1; @cached lazy-resolve -> Task 3; cli call site -> Task 2.
  - Semgrep rules (spec) -> Task 4.
  - PR template (spec) -> Task 5.
  - ADR-019 (spec) -> Task 6.
  - Testing strategy (spec) -> covered in Tasks 1, 3, 4 (synthetic + project scans).
  - Migration plan (spec) -> Task 6 ratchet update + Task 7 PR.
- Risk: Rule 3 (enum-shadowing-label-dict) is heuristic. Step 6 of Task 4 includes a synthetic violation test; if it doesn't fire on the obvious case, the pattern needs refinement (semgrep's `dict[$ENUM, str] = {...}` matcher is finicky around StrEnum vs Enum and around line-anchoring). Worst case: drop Rule 3 in this PR and revisit.
