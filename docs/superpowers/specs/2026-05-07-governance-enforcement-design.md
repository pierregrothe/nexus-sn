# NEXUS Governance and Enforcement -- Design Spec
# Author: Pierre Grothe
# Date: 2026-05-07

## Overview

Sprint retrospective-driven governance upgrade. 23 issues identified across 6
categories. This spec defines 8 new ADRs, updated enforcement hooks, lean CI
config, and Pydantic alignment with Python 3.14.

Derived from: analysis of MVP Step 1 sprint + patterns from market-analysis-service.

---

## Sprint Issue Catalog (23 issues)

### Type Safety (6)

1. `tmp_path: Any` in test signature -- should be `tmp_path: Path`
2. `dict[str, Any]` instead of `MessageParam`/`ToolParam` in fake signatures
3. `object` return type instead of concrete type (`httpx.Response`)
4. `_ModelsList` Protocol incompatible with real SDK (overly strict, no pyright to catch it)
5. `candidates[0].id` returning `Any` -- mypy `no-any-return` not enforced
6. `# type: ignore` comments leaked into test file

### Test Quality (5)

7. Vacuously passing test -- configure_logging test only checked dir creation, not handlers
8. Missing filter tests for _discover_model date-pinned and preview exclusion
9. Pre-staged unused imports in plan caused F401 on first commit
10. File handler not closed in test teardown -- resource leak
11. Coverage gate at 40% while CLAUDE.md requires 100% -- disconnect

### Hook Infrastructure (2)

12. Post-edit hook broken -- `$(git rev-parse --show-toplevel)` does not expand in hook env
13. Hook exits with code 2 but routes output to stdout; Claude Code only shows stderr

### Code Conventions (4)

14. `paths.root / "logs"` instead of `paths.logs_dir` -- ignoring canonical path property
15. `import httpx` inside function body -- deferred import anti-pattern
16. Reviewer told subagent to remove `__init__` docstring, violating D107 ruff rule
17. Pydantic models missing `strict=True, extra="forbid"` -- incomplete config

### Process (3)

18. Haiku model used for code-writing subagents -- wrong model tier
19. Subagent output truncated -- required manual state verification
20. Even Sonnet-level subagents required multiple fix loops due to insufficient context

### Configuration (3)

21. `>=3.12` Python constraint too broad -- Poetry resolved to 3.14 env, caused nicegui conflict
22. `poetry.lock` in `.gitignore` -- wrong for application-style project
23. `type: ignore[type-arg]` on list annotations in test fakes -- masked real type gap

---

## ADR-006: Python 3.14 Minimum

**Status:** accepted
**Enforcement:** hook (pyproject constraint check)

### Context

The project was scaffolded targeting Python 3.12+ with a broad `>=3.12` constraint.
The active dev environment runs Python 3.14.3. Targeting 3.14 minimum removes the
constraint ambiguity, enables PEP 649 (deferred annotation evaluation by default,
making `from __future__ import annotations` optional), PEP 758 (unparenthesized
multi-except), and all other 3.14 features.

### Decision

Minimum Python version is `>=3.14,<3.15` in pyproject.toml. CLAUDE.md updated to
permit and prefer all Python 3.14 syntax. The previous "Do NOT use Python 3.14-only
syntax" restriction is removed.

### Python 3.14 Patterns to Use

```python
# PEP 758: unparenthesized multi-except (3.14)
except ValueError, TypeError:
    ...

# PEP 649: deferred evaluation (3.14 default, no __future__ needed)
class Foo:
    def method(self) -> Foo: ...  # works without quotes

# PEP 695: type parameter syntax (3.12+)
type Vector[T] = list[T]
def first[T](items: list[T]) -> T: ...

# Union types (3.10+)
def parse(value: str | int | None) -> str: ...

# Built-in generics (3.9+)
items: list[str]
mapping: dict[str, int]
```

### Consequences

- nicegui must be constrained to `<4.0` explicitly (already done)
- CI matrix targets Python 3.14 only (single version, no matrix)
- pyright and mypy both configured for py314

---

## ADR-007: Zero `type: ignore` Tolerance

**Status:** accepted
**Enforcement:** blocking hook (pre-edit-validate.py)

### Context

During MVP Step 1 sprint, `# type: ignore[type-arg]` comments appeared in test
fakes to suppress list type errors. These masked real type gaps (see issues #23, #6).
The market-analysis-service blocks all `type: ignore` except `import-untyped`, and
this proved effective at forcing correct typing.

### Decision

No `# type: ignore` comment is permitted anywhere in the codebase (src/ or tests/).
The pre-edit hook blocks any line matching `#\s*type:\s*ignore`.

If a third-party library has no type stubs, the correct fix is one of:
1. Add a stub file under `src/stubs/<package>.pyi`
2. Add a `py.typed` marker stub package
3. Add `ignore_missing_imports = true` in `[mypy.<module>]` config for that specific package

### Consequences

All existing `# type: ignore` comments must be removed before this hook is wired.
Protocol definitions used in tests must be structurally compatible with real objects --
no escaping via `type: ignore`.

---

## ADR-008: Type Annotation Completeness

**Status:** accepted
**Enforcement:** blocking hook (pre-edit-validate.py) + pyright strict

### Context

Issues #1-5 all stem from insufficiently typed code: bare `Any` in test parameters,
`dict[str, Any]` in public interfaces, `object` return types, and return values
typed as `Any` flowing through from untyped sources.

### Decision

Three rules enforced by the pre-edit hook:

**Rule 1: No bare `Any` in signatures**

`Any` is permitted only in non-public Protocol method signatures where the structural
contract is genuinely open. It is never permitted in:
- Function parameter annotations
- Function return type annotations
- Class field type annotations

The hook blocks `: Any` and `-> Any` patterns in all Python files.

**Rule 2: No `dict[str, Any]` in public interfaces**

Use `TypedDict`, a `Protocol`, or a Pydantic model instead. `dict[str, Any]` is
permitted only in internal implementation bodies where processing arbitrary JSON.

The hook blocks `dict[str, Any]` in function signatures (but not in function bodies).

**Rule 3: No `object` return types in functions with a body**

`-> object` is only valid in Protocol stubs (`...` body). Functions that return
a real value must declare the actual type. The hook blocks `-> object:` followed
by a non-`...` body.

### Consequences

Fakes must implement Protocol signatures with the exact typed parameters.
Use `TYPE_CHECKING` imports for SDK types that are only needed at annotation time.
`from __future__ import annotations` (or Python 3.14 deferred evaluation) enables
forward references without circular imports.

---

## ADR-009: Behavioral Test Completeness

**Status:** accepted
**Enforcement:** ratchet (per-module coverage), soft (vacuous-test warning)

### Context

Issue #7: the configure_logging test passed even though the main behavior (handler
attachment) was never exercised. Issue #8: filter exclusion logic in _discover_model
had no tests at all. Issue #11: coverage gate at 40% while the standard requires 100%.

### Decision

**Rule 1: Per-module coverage**

When the post-edit hook edits `src/nexus/X/Y.py`, it runs:
```
pytest --cov=nexus.X.Y --cov-fail-under=100 tests/
```
If coverage for that module drops below 100%, the hook blocks the save. This
replaces the full-suite coverage gate for the development loop.

Full suite coverage gate (100%) is enforced by the pre-commit hook.

**Rule 2: Ratchet -- violations can only decrease**

`.ratchet.json` tracks the covered-lines count for each module. The post-edit hook
updates this file. A commit that reduces any module's coverage from a previously
achieved level is blocked.

**Rule 3: Behavioral coverage (soft warning)**

The post-edit hook warns (does not block) when it detects a test whose assertions
could all pass even if the function under test raised `NotImplementedError`. This is
a heuristic: if a test has no assertions involving return values or state changes,
warn the developer.

### Consequences

Tests must be written before implementation (TDD enforced by coverage gate).
Every branch, including filter logic and error paths, must be covered.
Tests must assert on actual return values, not just on side effects.

---

## ADR-010: Resource Lifecycle in Tests

**Status:** accepted
**Enforcement:** soft hook (warning, not blocking)

### Context

Issue #10: a `TimedRotatingFileHandler` opened during a test was not closed before
the root logger handlers were cleared. This leaks file descriptors, causes
`PermissionError` on Windows when pytest cleans up `tmp_path`, and can cause
data loss on buffered handlers.

### Decision

Any OS resource opened during a test must be explicitly closed:

```python
# Pattern: try/finally with explicit close
root.handlers.clear()
try:
    # ... test body ...
finally:
    for h in root.handlers:
        h.close()
    root.handlers.clear()
    root.handlers.extend(saved_handlers)
```

Context managers (`with` statements) are preferred where the resource supports it.

The post-edit hook warns (soft) when it detects `TimedRotatingFileHandler`,
`FileHandler`, `open(`, or `socket.socket(` in a test file without a corresponding
`close()` or `with` block on the same object.

### Consequences

All test teardown logic must close resources before restoring state. Logging
handler tests must save, clear, operate, close, and restore in a `try/finally`.

---

## ADR-011: 3-Tier Enforcement Model

**Status:** accepted
**Enforcement:** governance doc + hook architecture

### Context

Issue #12: post-edit hook silently failed due to shell expansion. Issue #13: hook
output went to stdout but Claude Code shows only stderr in blocking messages.
The single-tier "block or ignore" model collapsed to "ignore" when the hook broke.

### Decision

Three enforcement tiers with distinct contracts:

**Tier 1 -- Blocking (pre-edit-validate.py, PostToolUse)**

Runs before any Python file is written. Failure prevents the write. Must produce
output on stderr (not stdout) so Claude Code's blocking message shows context.
Zero tolerance: these rules are never bypassed.

Current blocking rules:
- no-mocks, no-relative-imports, no-bare-except, no-lru-cache-none
- no-unittest-testcase, no-sys-argv
- type-ignore-ban (NEW)
- bare-any-in-sig (NEW)
- dict-any-in-sig (NEW)
- deferred-import-in-body (NEW)

**Tier 2 -- Ratchet (.ratchet.json, post-edit-lint.py)**

Tracks a numeric baseline per rule. A commit that increases any metric from the
baseline is blocked. Metrics can only improve or stay the same.

Current ratchet metrics:
- per-module covered-lines (tracked in .ratchet.json)
- complexity-mccabe (max McCabe per function <= 10; tracked per file)
- file-lines-src (src files <= 300 lines; tracked per file)

**Tier 3 -- Soft (post-edit-lint.py, warning only)**

Prints warnings but never blocks. Used for rules where judgment is needed.

Current soft rules:
- missing-test-file: warns if src/nexus/X/Y.py is edited without tests/test_X_Y.py
- resource-open: warns if file handle or logging handler opened in test without close

**Hook reliability contract:**

post-edit-lint.py must:
1. Use `Path(__file__).parent.parent.parent` for REPO_ROOT (not shell substitution)
2. Route all feedback to stderr (not stdout)
3. Return exit code 0 (clean), 1 (soft warning), 2 (ratchet violation), 3 (blocking violation)

### Consequences

Blocking tier is the highest-confidence gate -- only rules with zero false positives
belong here. Ratchet tier handles progressive improvement. Soft tier handles
advisory rules that require human judgment.

---

## ADR-012: Dual Type Checking (mypy + pyright strict)

**Status:** accepted
**Enforcement:** blocking (post-edit-lint.py) + CI

### Context

Issue #4: `_ModelsList` Protocol was structurally incompatible with the real SDK's
`Models` type. mypy passed because `Anthropic` uses `Any` for `models`. pyright
in strict mode would have caught the incompatibility because it uses the SDK's actual
stubs.

### Decision

Both `mypy --strict` and `pyright --strict` must pass with 0 errors on every edited
Python file. The post-edit hook runs both after every write. CI runs both.

mypy config additions:
```toml
[tool.mypy]
strict = true
warn_return_any = true
warn_unused_ignores = true
strict_equality = true
python_version = "3.14"
```

pyright config (pyrightconfig.json):
```json
{
  "pythonVersion": "3.14",
  "typeCheckingMode": "strict",
  "reportMissingModuleSource": "none"
}
```

When mypy and pyright disagree, both must be satisfied. If a type is correct per
one checker but not the other, fix the code (not the config).

### Consequences

`_ModelDiscoveryClient.models` returning `Any` is technically accepted by mypy but
flagged by pyright strict. The correct fix is a more precise Protocol or a `cast()`
with a documented justification comment.

---

## ADR-013: Lean CI for Solo Developer

**Status:** accepted
**Enforcement:** ci.yml, pre-commit hook

### Context

The current CI runs the full test suite cross-platform (ubuntu + macos + windows,
Python 3.12). For a solo developer who runs tests locally before every commit,
this is redundant overhead that slows feedback.

### Decision

CI is restructured to two stages:

**Stage 1 -- Lint/type (every push, <30 seconds)**
- `black --check src/nexus/ tests/`
- `ruff check src/nexus/ tests/`
- `mypy src/nexus/`
- `pyright src/nexus/`

Single OS (ubuntu-latest), single Python version (3.14), no matrix.

**Stage 2 -- Tests (release tags only)**
- `pytest --cov-fail-under=100`
- Cross-platform matrix: ubuntu + macos + windows

Pre-commit hook (local, blocks commits):
- `pytest --cov-fail-under=100 -q`
- Runs only on files changed in the commit (fast mode with `--testpaths` scoped)

### Consequences

CI never gates on test coverage. Test coverage is enforced locally (post-edit per-
module + pre-commit full suite). If Pierre adds a co-developer, Stage 2 should be
moved back to every push.

---

## Enforcement Implementation Summary

### Files to create/modify

```
src/nexus/api/client.py           -- bump to 3.14 syntax, remove any type: ignore
CLAUDE.md                         -- bump Python to 3.14, document 3-tier model
pyproject.toml                    -- >=3.14,<3.15, lean CI, pyright dep
pyrightconfig.json                -- strict mode, py314
.ratchet.json                     -- baseline coverage per module (NEW)
.claude/hooks/pre-edit-validate.py -- add type-ignore-ban, bare-any, dict-any, deferred-import
.claude/hooks/post-edit-lint.py    -- fix shell expansion, add pyright, per-module cov, stderr routing
.github/workflows/ci.yml          -- remove pytest, add pyright, lean matrix
.primer/governance.md             -- update with 3-tier model + new ADRs
.primer/adr/ADR-006 through 013   -- 8 new ADR files
```

### New blocking hook patterns

```python
# type-ignore-ban
_TYPE_IGNORE_RE = re.compile(r"#\s*type:\s*ignore")

# bare-any-in-sig  (in function signature context)
_BARE_ANY_SIG_RE = re.compile(r":\s*Any\b|->.*\bAny\b")

# dict-any-in-sig (in function signature context)
_DICT_ANY_SIG_RE = re.compile(r"dict\[str,\s*Any\]")

# deferred-import-in-body
_DEFERRED_IMPORT_RE = re.compile(r"^[ \t]+(import |from .* import )", re.MULTILINE)
```

### Ratchet baseline file

```json
{
  "version": "1",
  "modules": {
    "nexus.config.settings": {"covered_lines": 35, "total_lines": 35},
    "nexus.config.paths": {"covered_lines": 36, "total_lines": 37},
    "nexus.config.manager": {"covered_lines": 29, "total_lines": 30},
    "nexus.auth.errors": {"covered_lines": 7, "total_lines": 7},
    "nexus.auth.keychain": {"covered_lines": 26, "total_lines": 26},
    "nexus.auth.claude": {"covered_lines": 27, "total_lines": 30},
    "nexus.auth.servicenow": {"covered_lines": 19, "total_lines": 29},
    "nexus.capabilities.feature_flags": {"covered_lines": 27, "total_lines": 27},
    "nexus.capabilities.registry": {"covered_lines": 29, "total_lines": 29},
    "nexus.api.errors": {"covered_lines": 7, "total_lines": 7},
    "nexus.api.logging_config": {"covered_lines": 13, "total_lines": 14},
    "nexus.api.client": {"covered_lines": 51, "total_lines": 57},
    "nexus.api.tool_registry": {"covered_lines": 14, "total_lines": 14}
  }
}
```

### Post-edit hook fix (critical)

Replace shell-expansion path:
```python
# OLD (broken):
# "python3 \"$(git rev-parse --show-toplevel)/.claude/hooks/post-edit-lint.py\""

# NEW in post-edit-lint.py:
REPO_ROOT = Path(__file__).parent.parent.parent
```

And in settings.json, replace with an absolute-path-safe command:
```json
"command": "python3 .claude/hooks/post-edit-lint.py"
```
(Claude Code runs hooks from the repo root, so a relative path works reliably.)

---

## Pydantic Standards Update

All Pydantic models must use:
```python
from pydantic import BaseModel, ConfigDict, Field
from typing import Annotated

class MyModel(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    # Use Annotated + Field for all constrained fields
    count: Annotated[int, Field(gt=0)]
    name: Annotated[str, Field(min_length=1, max_length=100)]
```

Cross-field validators return `Self`:
```python
from typing import Self

@model_validator(mode="after")
def validate_consistency(self) -> Self:
    ...
    return self
```

---

## Scope Summary

8 ADRs, 13 modified files, 0 new source features. This is a pure governance and
tooling upgrade. All changes are confined to:
- Hook scripts
- CI config
- pyproject.toml
- CLAUDE.md
- pyrightconfig.json
- .ratchet.json (new)
- .primer/adr/ (8 new ADR files)
- .primer/governance.md (updated)
