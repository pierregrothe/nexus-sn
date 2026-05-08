# /simplify Lessons Learned Design Spec

Date: 2026-05-08
Status: approved (brainstorming complete)
Author: Pierre Grothe

## Goal

Codify the bugs and recurring smells caught by /simplify reviews across PRs
#2, #5, and #6 into a single bundled change: an architectural fix
(`@cached(persist=True)` lazy-resolve), a safer keychain wrapper for
external apps, three new Semgrep rules, and a PR template that gates
/simplify execution before merge.

## Why

Three /simplify sessions caught real issues every time:

  - PR #2 (Agent SDK migration): efficiency findings (qualname recomputed
    per call, double-scan for unhashable args), code-quality findings
    (dead `permissive_func` parameter, stub docstrings).
  - PR #5 (cached decorator): style findings (over-engineered `_Missing`
    singleton, dead-code branches).
  - PR #6 (tier detection): the CRITICAL bug
    (`KeychainClient(service_prefix="nexus")` silently mismatched the
    Claude Code keychain key) plus an architectural limitation
    (`@cached(persist=True)` decoration-time backend capture broke test
    isolation, forcing a workaround).

The keychain bug almost shipped. Pre-commit hooks didn't catch it; tests
didn't catch it; only review caught it. The other findings are smaller
but recurring. Together they justify codifying the lessons rather than
relying on memory.

## Architecture

### File map

```
ADD:
  src/nexus/auth/external_keychain.py   # ExternalKeychainClient subclass
  .github/PULL_REQUEST_TEMPLATE.md      # checkbox-driven gates
  .primer/adr/ADR-019-simplify-lessons-learned.md

MODIFY:
  src/nexus/auth/__init__.py            # export ExternalKeychainClient
  src/nexus/cli.py                      # use ExternalKeychainClient at the keychain construction site
  src/nexus/cache/decorator.py          # lazy-resolve disk backend per call
  .semgrep/rules.yml                    # 3 new rules
  tests/test_cache_decorator.py         # regression test for lazy-resolve
  tests/test_auth.py                    # new test for ExternalKeychainClient
  .ratchet.json                         # baselines for changed modules
  .primer/governance.md                 # 3 new semgrep gates + ADR-019 row
  .primer/decisions.md                  # append ADR-019 entry
```

### Layer placement

`src/nexus/auth/external_keychain.py` lives at Layer 2 alongside
`keychain.py`. No new dependencies. No new layer in the architecture.

### User-visible behavior changes

- `nexus status` and `nexus reauth` keep working identically -- the
  call site swap is a behavior-equivalent rename.
- `@cached(persist=True)` becomes test-friendly. AgentClient adoption
  (deferred in ADR-017) is now unblocked.
- New PR template adds a `/simplify run` checkbox.
- Three new Semgrep rules block patterns at lint time.

## Components

### `ExternalKeychainClient`

Five lines of real code:

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
    """KeychainClient configured for reading external apps' credentials."""

    def __init__(self) -> None:
        """Initialize with empty service prefix."""
        super().__init__(service_prefix="")
```

The whole point is to make intent grep-able and rule-enforceable. The
Semgrep rule then bans direct use of `KeychainClient(service_prefix=...)`
in `src/nexus/`, leaving exactly two valid forms: `KeychainClient()` for
NEXUS-owned secrets, `ExternalKeychainClient()` for other apps' secrets.

### `@cached(persist=True)` lazy-resolve fix

Current persist branch in `src/nexus/cache/decorator.py`:

```python
if persist:
    backend = _get_or_create_disk_backend(namespace)  # captured at decoration time

    def get_disk_backend(_first_arg: object) -> CacheBackend:
        return backend

    return _wrap_with_backend(...)
```

Becomes:

```python
if persist:
    # Lazy-resolve: the wrapper looks up the backend on every call instead
    # of capturing it at decoration time. Tests can monkeypatch
    # _disk_cache_root and clear _DISK_BACKENDS between tests; the next
    # call picks up the new path. The dict lookup adds ~50ns per call.
    def get_disk_backend(_first_arg: object) -> CacheBackend:
        return _get_or_create_disk_backend(namespace)

    return _wrap_with_backend(...)
```

One-line change. The rest of the persist machinery (`_DISK_BACKENDS`
dict, `_get_or_create_disk_backend` function) stays.

Performance: one extra dict lookup per `@cached(persist=True)` call.
Negligible compared to disk I/O. `_get_or_create_disk_backend` already
caches in `_DISK_BACKENDS` after first creation, so the work after the
first call is `_DISK_BACKENDS[namespace]` -- a single dict access.

### Call-site update in `cli.py`

```python
# Before:
def _detect_tier() -> TierDetection:
    reader = FilesystemClaudeCodeConfigReader(keychain=KeychainClient(service_prefix=""))
    return TierDetector(reader=reader).detect()

# After:
def _detect_tier() -> TierDetection:
    reader = FilesystemClaudeCodeConfigReader(keychain=ExternalKeychainClient())
    return TierDetector(reader=reader).detect()
```

Two-line change: import + the constructor swap.

## Semgrep rules

### Rule 1: `external-keychain-must-use-wrapper`

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
```

The `**/src/nexus/**` path filter exempts tests. The pattern matches the
literal `KeychainClient(...)` constructor call -- the wrapper itself uses
`super().__init__(service_prefix="")`, which does not match the pattern.
No false positive on the wrapper.

### Rule 2: `no-stub-see-docstring`

```yaml
- id: no-stub-see-docstring
  languages: [python]
  severity: ERROR
  message: |
    Stub docstrings like '\"\"\"See OtherClass.method.\"\"\"' add no value.
    Either copy the canonical docstring or write a one-line behavior
    description (ADR-019).
  paths:
    include: ["**/src/nexus/**"]
  pattern-regex: '"""See [A-Z][A-Za-z]+\.[a-z_]+\.\s*"""'
  metadata:
    adr: ADR-019
    category: governance
```

Caught the `"""See AgentClientProtocol.complete."""` pattern in PR #5.
Regex form is sufficient -- no AST context needed.

### Rule 3: `enum-shadowing-label-dict`

```yaml
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

Severity WARNING (not ERROR) because the pattern is heuristic -- a
`dict[Tier, str]` could legitimately map to non-label data. Manual review
on each fire. If false positives are common in practice, refine the
pattern or escalate to ERROR.

### Rule 4 -- DROPPED

The "single-use module-private helper" rule was considered but dropped.
Semgrep cannot reliably count cross-function usages; a working rule
would need an AST-walking Python script outside Semgrep, which is real
new tooling. Code review and /simplify catch this fine without a rule.

## PR template

`.github/PULL_REQUEST_TEMPLATE.md`:

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

The `/simplify` checkbox is the load-bearing one. The other gates surface
existing convention as explicit checklist items.

## ADR-019: lessons learned

`.primer/adr/ADR-019-simplify-lessons-learned.md` covers four threads:

1. **External-system credential reads.** Default
   `KeychainClient(service_prefix="nexus")` silently breaks reads of
   other apps' keychain entries. Fix: `ExternalKeychainClient` wrapper
   + Semgrep rule banning direct prefix override in `src/nexus/`.

2. **`@cached(persist=True)` lazy-resolve.** Decoration-time backend
   capture breaks test isolation. Fix: wrapper looks up the backend on
   every call instead of capturing it at decoration time.

3. **Recurring style smells worth Semgrep rules.** Three new rules:
   `external-keychain-must-use-wrapper`, `no-stub-see-docstring`,
   `enum-shadowing-label-dict` (last one WARNING-only as heuristic).
   The "single-use module-private helper" pattern was considered but
   dropped -- Semgrep cannot detect it reliably.

4. **/simplify before merge as a process gate.** PR template checkbox
   plus ADR-019 commitment. Solo-dev honor system, but the unchecked
   box is review-visible.

Status: accepted. Date: 2026-05-08. Enforcement: 3 new semgrep rules +
PR template + ADR commitment.

## Testing

### `ExternalKeychainClient`

One test in `tests/test_auth.py`:

```python
def test_external_keychain_client_uses_empty_prefix() -> None:
    client = ExternalKeychainClient()
    assert client._prefix == ""
```

The `_prefix` attribute access works in tests because of the
`pyrightconfig.json` execution-environment override (`tests/` has
`reportPrivateUsage` set to `none`).

### `@cached(persist=True)` lazy-resolve regression test

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

Without the fix this test fails: the wrapper holds the old `cache_a`
backend. With the fix, it picks up `cache_b`.

### Semgrep rules

For each rule, two checks:

1. Synthetic violation matching pattern -> rule fires:
   ```bash
   cat > /tmp/sg_violation.py <<'EOF'
   from nexus.auth.keychain import KeychainClient
   k = KeychainClient(service_prefix="something")
   EOF
   /Users/pierre.grothe/.local/bin/semgrep --config .semgrep/rules.yml /tmp/sg_violation.py --error
   # Expected: 1 finding for external-keychain-must-use-wrapper
   ```

2. Project scan -> 0 findings (existing code is clean post-PR-#6):
   ```bash
   /Users/pierre.grothe/.local/bin/semgrep --config .semgrep/rules.yml src/ tests/ --error
   ```

### Coverage target

100% on `nexus.auth.external_keychain` (trivial subclass) and the
modified `nexus.cache.decorator` per existing project gate.

## Migration

### Single PR, all four threads land together.

**Adoption diff:**
- `cli.py:_detect_tier()` swaps `KeychainClient(service_prefix="")` for
  `ExternalKeychainClient()`.
- `tier.py` and other consumers untouched.
- Existing `TierDetector.detect()` keeps `@cached(ttl=None)`. The
  `persist=True` machinery is unblocked but no current consumer adopts
  it (AgentClient remains deferred per ADR-017).

### Coverage ratchet

- `nexus.cli` -- small change (one substitution); covered_lines should
  stay the same.
- `nexus.cache.decorator` -- one closure change; covered_lines may
  shift +/-1.
- `nexus.auth.external_keychain` -- new entry, ~3 covered lines.

### Out of scope (deferred)

- AgentClient adopting `@cached(persist=True)` for LLM result caching --
  separate PR when there's a real cost-saving reason.
- An AST-walking helper for the dropped "single-use private helper"
  rule -- convention only.
- Migrating any existing `KeychainClient(service_prefix=...)` outside
  `cli.py` -- there are no other call sites; the new Semgrep rule is
  purely forward-looking.

### Rollback

Each thread rolls back independently (revert the Semgrep rule entries,
revert the decorator one-liner, revert the ExternalKeychainClient
class). Low risk.
