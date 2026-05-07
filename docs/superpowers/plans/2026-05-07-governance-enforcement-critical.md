# Governance Enforcement -- Critical Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the broken post-edit hook, add type-safety blocking rules, bump to Python 3.14, add pyright strict, and clean up all pre-existing violations that the new rules would block.

**Architecture:** 8 sequential tasks. Python version and pyright must be installed (Tasks 1-2) before the hook can invoke pyright (Task 4). Existing violations must be fixed (Tasks 5-6) before new blocking rules are added (Task 7) -- otherwise the hook blocks the very edits that fix the violations.

**Tech Stack:** Python 3.14, pyright, mypy strict, ruff, Poetry, pre-edit hook (pre-edit-validate.py), post-edit hook (post-edit-lint.py).

---

## File Map

```
Modify:  .claude/settings.json               -- fix shell expansion in hook commands
Modify:  pyproject.toml                      -- Python 3.14, add pyright dev dep, update mypy config
Modify:  pyrightconfig.json                  -- pythonVersion 3.12 -> 3.14
Modify:  .claude/hooks/post-edit-lint.py     -- stderr routing + add pyright
Modify:  tests/test_api_client.py            -- remove 4 type: ignore comments, use _FakeModel
Modify:  src/nexus/api/client.py             -- fix _ModelDiscoveryClient Protocol chain
Modify:  .claude/hooks/pre-edit-validate.py  -- add 4 new blocking patterns
Modify:  CLAUDE.md                           -- Python 3.14, 3-tier enforcement, new rules
```

---

## Task 1: Fix Hook Command Shell Expansion

**Files:**
- Modify: `.claude/settings.json`

The hook commands use `$(git rev-parse --show-toplevel)` which is shell substitution.
Claude Code does not expand `$()` in hook commands -- it passes the string literally
to the OS, causing the hook to silently fail with "No stderr output". Fix: use a
relative path. Claude Code runs hooks from the repo root, so `.claude/hooks/...`
resolves correctly.

- [ ] **Step 1: Read current settings.json**

```
cat .claude/settings.json
```

Verify both commands contain the broken `$(git rev-parse --show-toplevel)` pattern.

- [ ] **Step 2: Replace settings.json**

Write the file with fixed commands:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "python3 .claude/hooks/pre-edit-validate.py"
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "python3 .claude/hooks/post-edit-lint.py"
          }
        ]
      }
    ]
  }
}
```

- [ ] **Step 3: Smoke test the hook manually**

```bash
echo '{"tool_input": {"file_path": "src/nexus/api/errors.py", "content": ""}}' \
  | python3 .claude/hooks/post-edit-lint.py; echo "exit: $?"
```

Expected: `exit: 0` (empty content, no violations, hook runs without error)

- [ ] **Step 4: Commit**

```bash
git add .claude/settings.json
git commit -m "fix: use relative paths in hook commands (shell expansion was broken)"
```

---

## Task 2: Bump to Python 3.14 and Add pyright

**Files:**
- Modify: `pyproject.toml`
- Modify: `pyrightconfig.json`

- [ ] **Step 1: Update pyproject.toml**

Apply these changes to `pyproject.toml`:

**python constraint** (line ~14):
```toml
python = ">=3.14,<3.15"
```

**Add pyright to dev dependencies** (in `[tool.poetry.group.dev.dependencies]`):
```toml
pyright = ">=1.1"
```

**mypy python_version** (in `[tool.mypy]`):
```toml
python_version = "3.14"
```

Add these mypy settings (append to `[tool.mypy]` section):
```toml
warn_return_any = true
warn_unused_ignores = true
strict_equality = true
```

**pytest cov-fail-under** -- raise from 50 to 100:
```toml
    "--cov-fail-under=100",
```

- [ ] **Step 2: Update pyrightconfig.json**

Read the current file, then write:

```json
{
  "pythonVersion": "3.14",
  "pythonPlatform": "Darwin",
  "typeCheckingMode": "strict",
  "extraPaths": ["src"],
  "venvPath": ".",
  "venv": ".venv"
}
```

(Remove `"venvPath": "."` and `"venv": ".venv"` if the pyright venv detection is
via the Poetry env instead. Check: `poetry env info --path` and set accordingly.)

- [ ] **Step 3: Install pyright**

```bash
poetry install
```

Expected: pyright installed in the venv. Confirm:
```bash
poetry run pyright --version
```

Expected: prints `pyright X.Y.Z`

- [ ] **Step 4: Run pyright on the current codebase**

```bash
poetry run pyright src/nexus/
```

Note any errors -- they will be fixed in Tasks 5 and 6. Do not fix them here.

- [ ] **Step 5: Run full test suite to confirm Python 3.14 constraint works**

```bash
poetry run pytest -q
```

Expected: all tests pass. If any fail due to the Python version bump, investigate
before continuing.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml pyrightconfig.json poetry.lock
git commit -m "feat: bump to Python 3.14, add pyright strict, raise coverage gate to 100%"
```

---

## Task 3: Fix post-edit-lint.py (stderr + pyright)

**Files:**
- Modify: `.claude/hooks/post-edit-lint.py`

Two problems:
1. Output goes to `print()` (stdout) -- Claude Code shows only stderr in blocking
   messages, so hook violations are invisible.
2. pyright is not run.

- [ ] **Step 1: Read current post-edit-lint.py**

```
cat .claude/hooks/post-edit-lint.py
```

- [ ] **Step 2: Write the updated hook**

Replace the full content of `.claude/hooks/post-edit-lint.py`:

```python
#!/usr/bin/env python3
# .claude/hooks/post-edit-lint.py
# PostToolUse hook -- run ruff, mypy, and pyright after Claude edits a Python file.
# Author: Pierre Grothe
# Date: 2026-05-07
"""Run ruff, mypy, and pyright immediately after a Python file is written.

Exit codes:
  0 -- no issues (or non-Python file)
  2 -- lint/type issues found (output on stderr so Claude Code displays it)
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
NEXUS_SRC = REPO_ROOT / "src" / "nexus"
TESTS = REPO_ROOT / "tests"


def is_target(path: Path) -> bool:
    """Return True if path is a Python file under nexus/ or tests/."""
    if path.suffix != ".py":
        return False
    for root in (NEXUS_SRC, TESTS):
        try:
            path.relative_to(root)
            return True
        except ValueError:
            pass
    return False


def run(cmd: list[str]) -> tuple[int, str]:
    """Run a subprocess and return (returncode, combined output)."""
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO_ROOT)
    return result.returncode, (result.stdout + result.stderr).strip()


def main() -> int:
    """Lint and type-check the edited file.

    Returns:
        0 if clean, 2 if violations found.
    """
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        return 0

    file_path_str = (
        data.get("tool_input", {}).get("file_path")
        or data.get("tool_response", {}).get("filePath")
    )
    if not file_path_str:
        return 0

    path = Path(file_path_str)
    if not is_target(path):
        return 0

    issues: list[str] = []

    rc, out = run(["poetry", "run", "ruff", "check", str(path)])
    if rc != 0 and out:
        issues.append(f"ruff:\n{out}")

    rc, out = run(["poetry", "run", "mypy", str(path)])
    if rc != 0 and out:
        issues.append(f"mypy:\n{out}")

    rc, out = run(["poetry", "run", "pyright", str(path)])
    if rc != 0 and out:
        issues.append(f"pyright:\n{out}")

    if issues:
        # stderr so Claude Code displays violations in the blocking message
        print("\n".join(issues), file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Test the hook on a known-clean file**

```bash
echo "{\"tool_input\": {\"file_path\": \"$(pwd)/src/nexus/api/errors.py\", \"content\": \"\"}}" \
  | python3 .claude/hooks/post-edit-lint.py; echo "exit: $?"
```

Expected: `exit: 0`

- [ ] **Step 4: Commit**

```bash
git add .claude/hooks/post-edit-lint.py
git commit -m "fix: route hook violations to stderr, add pyright to post-edit checks"
```

---

## Task 4: Fix _ModelDiscoveryClient Protocol Chain

**Files:**
- Modify: `src/nexus/api/client.py`

The current `_ModelDiscoveryClient.models` returns `Any`. This violates ADR-008
(no bare `Any`) and hides the real structural mismatch with the SDK type. The fix:
add a proper `_ModelsList` Protocol whose `list()` returns `Iterable[_ModelEntry]`
(using `Iterable` not `list` because `anthropic.Anthropic.models.list()` returns
`SyncPage`, which is iterable but not `list`).

- [ ] **Step 1: Read the current Protocol section**

Read `src/nexus/api/client.py` lines 1-95 to see the current imports and Protocol definitions.

- [ ] **Step 2: Add Iterable import and rewrite Protocol chain**

Find the imports section at the top of `src/nexus/api/client.py`. The file currently
imports `from datetime import datetime` (added to support `_ModelEntry.created_at`).
Keep that import. Change the typing import line:

```python
# Change this line:
from typing import Any, Protocol
# To:
from collections.abc import Iterable
from typing import Protocol
```

`datetime` is needed for `_ModelEntry.created_at: datetime`. Do not remove it.

Then replace the existing Protocol definitions (the three classes before
`_discover_model`) with:

```python
class _ModelEntry(Protocol):
    """Minimal duck-typed interface for a single model listing entry."""

    id: str
    created_at: datetime


class _ModelsList(Protocol):
    """Minimal duck-typed interface for the models listing accessor."""

    def list(self) -> Iterable[_ModelEntry]:
        """Return available model entries."""
        ...


class _ModelDiscoveryClient(Protocol):
    """Duck-typed interface required by _discover_model."""

    @property
    def models(self) -> _ModelsList:
        """Provide models.list() access."""
        ...
```

Update `_discover_model` signature:

```python
def _discover_model(client: _ModelDiscoveryClient, tier: ModelTier) -> str:
```

- [ ] **Step 3: Run mypy and pyright**

```bash
poetry run mypy src/nexus/api/client.py
poetry run pyright src/nexus/api/client.py
```

If either reports an error about `Anthropic` not satisfying `_ModelDiscoveryClient`
because `Models.list()` returns `SyncPage` not `Iterable[_ModelEntry]`:

Check the exact SDK type for `Model.created_at` in the pyright error output. If
`created_at` is `int` (Unix timestamp) not `datetime`, change `_ModelEntry` to:

```python
class _ModelEntry(Protocol):
    id: str
    created_at: int | datetime  # SDK may use either
```

And update the sort key accordingly:
```python
key=lambda m: m.created_at,  # works for both int and datetime
```

If `SyncPage` itself doesn't satisfy `Iterable[_ModelEntry]`, add an explicit cast
inside `_discover_model` -- but do NOT add `# type: ignore`. Use `cast()`:

```python
from typing import cast

for m in cast(Iterable[_ModelEntry], client.models.list()):
```

- [ ] **Step 4: Run full tests**

```bash
poetry run pytest tests/test_api_client.py -v
```

Expected: all tests pass (the tests will fail in the next task because the fakes
use `SimpleNamespace` -- that's expected and will be fixed in Task 5).

- [ ] **Step 5: Commit**

```bash
git add src/nexus/api/client.py
git commit -m "fix: proper Protocol chain for _ModelDiscoveryClient, remove Any return type"
```

---

## Task 5: Fix type: ignore Comments and Fakes in Tests

**Files:**
- Modify: `tests/test_api_client.py`

Four `# type: ignore[type-arg]` comments on `list` return types in fake model
classes. Fix by introducing a `_FakeModel` dataclass that satisfies `_ModelEntry`,
replacing `SimpleNamespace` fakes, and removing all `type: ignore` annotations.

- [ ] **Step 1: Read the current test file**

Read `tests/test_api_client.py` from line 55 to 130 to see the four fake model
classes that use `# type: ignore[type-arg]`.

- [ ] **Step 2: Add _FakeModel dataclass before the first test that uses it**

Find the block starting at `def test_discover_model_returns_newest_by_created_at`.
Add a `_FakeModel` dataclass just above that block:

```python
@dataclass(slots=True)
class _FakeModel:
    """Minimal fake for _ModelEntry Protocol -- used in model discovery tests."""

    id: str
    created_at: datetime
```

Note: `dataclass` and `datetime` are already imported at the top of the file.

- [ ] **Step 3: Replace all SimpleNamespace model fakes with _FakeModel**

Replace every occurrence of:
```python
older = SimpleNamespace(
    id="claude-sonnet-4-5",
    created_at=datetime(2025, 9, 1, tzinfo=UTC),
)
newer = SimpleNamespace(
    id="claude-sonnet-4-6",
    created_at=datetime(2025, 12, 1, tzinfo=UTC),
)
```
with:
```python
older = _FakeModel(id="claude-sonnet-4-5", created_at=datetime(2025, 9, 1, tzinfo=UTC))
newer = _FakeModel(id="claude-sonnet-4-6", created_at=datetime(2025, 12, 1, tzinfo=UTC))
```

Apply the same replacement for `date_pinned`, `floating`, `preview`, `stable`
in the filter exclusion tests. All 4 test functions that create model fakes
(`test_discover_model_returns_newest_by_created_at`,
`test_discover_model_falls_back_when_list_raises`,
`test_discover_model_excludes_date_pinned_variants`,
`test_discover_model_excludes_preview_models`) need updating.

- [ ] **Step 4: Fix the _FakeModels list() return type in all 4 tests**

Replace all four occurrences of:
```python
class _FakeModels:
    def list(self) -> list:  # type: ignore[type-arg]
        return [...]
```
with:
```python
class _FakeModels:
    def list(self) -> list[_FakeModel]:
        """Return fake model entries."""
        return [...]
```

(No `# type: ignore` comment. `list[_FakeModel]` satisfies `Iterable[_ModelEntry]`
because `_FakeModel` structurally implements `_ModelEntry`, and `list` is iterable.)

- [ ] **Step 5: Verify no type: ignore remains**

```bash
grep -n "type: ignore" tests/test_api_client.py
```

Expected: no output.

- [ ] **Step 6: Run ruff and mypy and pyright**

```bash
poetry run ruff check tests/test_api_client.py
poetry run mypy tests/test_api_client.py
poetry run pyright tests/test_api_client.py
```

Expected: 0 violations, 0 errors.

- [ ] **Step 7: Run all tests**

```bash
poetry run pytest tests/test_api_client.py -v
```

Expected: all 13 tests pass.

- [ ] **Step 8: Commit**

```bash
git add tests/test_api_client.py
git commit -m "fix: replace SimpleNamespace fakes with _FakeModel, remove all type: ignore"
```

---

## Task 6: Fix Remaining tool_registry Any and Run Full Suite

**Files:**
- Modify: `src/nexus/api/tool_registry.py`

`as_anthropic_tools()` returns `list[dict[str, Any]]`. Per ADR-008, public
interfaces may not use `dict[str, Any]`. The correct return type is
`list[ToolParam]` from `anthropic.types`. The dict shape we build (`name`,
`description`, `input_schema`) matches the `ToolParam` TypedDict.

Note: `tool.parameters` is `dict[str, Any]` (from `Tool` in `connectors/base.py`).
`ToolParam.input_schema` expects `ToolInputSchemaParam` which is structurally
`dict[str, object]`. Use `cast()` at the boundary.

- [ ] **Step 1: Read tool_registry.py**

```
cat src/nexus/api/tool_registry.py
```

- [ ] **Step 2: Rewrite as_anthropic_tools**

Replace the `as_anthropic_tools` method:

```python
from typing import cast

from anthropic.types import ToolParam
from anthropic.types import ToolInputSchemaParam

def as_anthropic_tools(self) -> list[ToolParam]:
    """Return all connector tools in Anthropic API format.

    Returns:
        List of ToolParam dicts with name, description, and input_schema.
    """
    tools: list[ToolParam] = []
    for tool in self._connectors.all_tools():
        tools.append(
            ToolParam(
                name=tool.name,
                description=tool.description,
                input_schema=cast(ToolInputSchemaParam, tool.parameters),
            )
        )
    log.debug("tool registry: %d tools assembled", len(tools))
    return tools
```

Update the module imports -- remove `Any` from `typing` if it's no longer needed,
keep `cast`. Remove `from typing import Any` if only used here.

- [ ] **Step 3: Run ruff, mypy, pyright on the file**

```bash
poetry run ruff check src/nexus/api/tool_registry.py
poetry run mypy src/nexus/api/tool_registry.py
poetry run pyright src/nexus/api/tool_registry.py
```

Expected: 0 violations. If pyright complains about `ToolParam()` constructor
(TypedDicts can be constructed as keyword args in Python 3.11+), use the dict
literal form instead:

```python
tools.append({  # type: ToolParam
    "name": tool.name,
    "description": tool.description,
    "input_schema": cast(ToolInputSchemaParam, tool.parameters),
    "type": "custom",
})
```

Note: TypedDicts require all Required keys. Check the `ToolParam` definition:
`name` and `input_schema` are Required; `description`, `type`, `cache_control` are
optional. If `ToolParam` constructor is not callable (it's a TypedDict), build as a
dict literal typed with `ToolParam`.

- [ ] **Step 4: Run full test suite**

```bash
poetry run pytest -q
```

Expected: 53 tests pass, coverage >= 100% for implemented modules.

If coverage fails at 100%, identify which implemented module is under-covered
and add tests before proceeding.

- [ ] **Step 5: Commit**

```bash
git add src/nexus/api/tool_registry.py
git commit -m "fix: use ToolParam return type in as_anthropic_tools, remove dict[str, Any]"
```

---

## Task 7: Add New Blocking Patterns to pre-edit-validate.py

**Files:**
- Modify: `.claude/hooks/pre-edit-validate.py`

Add 4 new blocking rules (all violations have been cleaned up in Tasks 4-6 first):
1. `type-ignore-ban` -- blocks `# type: ignore` anywhere
2. `bare-any-in-sig` -- blocks `: Any` and `-> Any` in function signatures
3. `dict-any-in-sig` -- blocks `dict[str, Any]` in function signatures
4. `deferred-import-in-body` -- blocks `import` statements inside `def`/`class` bodies

- [ ] **Step 1: Read the current pre-edit-validate.py**

```
cat .claude/hooks/pre-edit-validate.py
```

- [ ] **Step 2: Add 4 new regex patterns after the existing patterns**

After `_UNITTEST_TESTCASE_RE = re.compile(...)`, add:

```python
_TYPE_IGNORE_RE = re.compile(r"#\s*type:\s*ignore")

# Matches ': Any' or '-> Any' only at function signature positions.
# Allows 'Any' in strings, comments, and Protocol stubs.
_BARE_ANY_SIG_RE = re.compile(
    r"(?:^[ \t]*def\s+\w+[^)]*:\s*Any\b"  # parameter: Any
    r"|->.*\bAny\b(?:\s*:|\s*\n))"          # -> Any (return type)
    , re.MULTILINE,
)

# Matches dict[str, Any] in function signatures only.
_DICT_ANY_SIG_RE = re.compile(
    r"^[ \t]*def\s+\w+[^)]*dict\[str,\s*Any\]",
    re.MULTILINE,
)

# Matches import statements indented inside a def or class body.
_DEFERRED_IMPORT_RE = re.compile(
    r"^[ \t]+(from\s+\S+\s+import|import\s+\S)",
    re.MULTILINE,
)
```

- [ ] **Step 3: Add 4 new check functions**

After `check_unittest_testcase`, add:

```python
def check_type_ignore(content: str, path: Path) -> str | None:
    """Block # type: ignore comments -- fix the actual type issue instead."""
    if _TYPE_IGNORE_RE.search(content):
        return (
            f"BLOCKED: '# type: ignore' in {path.name}. "
            "Fix the actual type error. For missing stubs add to src/stubs/."
        )
    return None


def check_bare_any_in_sig(content: str, path: Path) -> str | None:
    """Block bare Any in function signatures -- use a Protocol or concrete type."""
    if _BARE_ANY_SIG_RE.search(content):
        return (
            f"BLOCKED: Bare 'Any' in function signature in {path.name}. "
            "Use a Protocol, TypedDict, or concrete type instead."
        )
    return None


def check_dict_any_in_sig(content: str, path: Path) -> str | None:
    """Block dict[str, Any] in function signatures -- use TypedDict or Protocol."""
    if _DICT_ANY_SIG_RE.search(content):
        return (
            f"BLOCKED: 'dict[str, Any]' in function signature in {path.name}. "
            "Define a TypedDict or Protocol to express the structure."
        )
    return None


def check_deferred_import(content: str, path: Path) -> str | None:
    """Block import statements inside def/class bodies -- all imports at module level."""
    if _DEFERRED_IMPORT_RE.search(content):
        return (
            f"BLOCKED: Deferred import inside function or class body in {path.name}. "
            "Move all imports to module level."
        )
    return None
```

- [ ] **Step 4: Register the 4 new checks in the checks list**

Find the `checks = [...]` list and add the 4 new functions:

```python
checks = [
    check_mocks,
    check_sys_argv,
    check_relative_imports,
    check_bare_except,
    check_lru_cache,
    check_unittest_testcase,
    check_type_ignore,
    check_bare_any_in_sig,
    check_dict_any_in_sig,
    check_deferred_import,
]
```

- [ ] **Step 5: Update the module docstring to document new checks**

Update the module docstring to list all 10 checks:

```python
"""Block prohibited patterns before any Python file is written.

Checks (all blocking):
  1. Mock imports (unittest.mock, MagicMock, pytest_mock, @patch)
  2. sys.argv indexing in non-test files
  3. Relative imports -- use absolute imports only
  4. Bare except clauses -- catch specific exceptions
  5. @lru_cache(maxsize=None) -- use @cache
  6. unittest.TestCase subclasses in test files
  7. # type: ignore comments -- fix the actual type error
  8. Bare Any in function signatures -- use Protocol or concrete type
  9. dict[str, Any] in function signatures -- use TypedDict or Protocol
  10. Deferred imports inside def/class bodies -- imports at module level only

Exit codes:
  0 -- content is clean (or non-Python file)
  2 -- prohibited pattern detected
"""
```

- [ ] **Step 6: Test each new check with a minimal example**

Run these four tests to confirm each new check blocks correctly:

```bash
# Test type-ignore-ban
echo '{"tool_input": {"file_path": "'$(pwd)'/src/nexus/api/errors.py", "content": "x = 1  # type: ignore"}}' \
  | python3 .claude/hooks/pre-edit-validate.py; echo "exit: $?"
```
Expected: prints `BLOCKED: '# type: ignore'...` and `exit: 2`

```bash
# Test bare-any-in-sig
echo '{"tool_input": {"file_path": "'$(pwd)'/src/nexus/api/errors.py", "content": "def foo(x: Any) -> str: ..."}}' \
  | python3 .claude/hooks/pre-edit-validate.py; echo "exit: $?"
```
Expected: `exit: 2`

```bash
# Test dict-any-in-sig
echo '{"tool_input": {"file_path": "'$(pwd)'/src/nexus/api/errors.py", "content": "def foo(x: dict[str, Any]) -> str: ..."}}' \
  | python3 .claude/hooks/pre-edit-validate.py; echo "exit: $?"
```
Expected: `exit: 2`

```bash
# Test deferred-import
echo '{"tool_input": {"file_path": "'$(pwd)'/src/nexus/api/errors.py", "content": "def foo():\n    import os\n    return os.getcwd()"}}' \
  | python3 .claude/hooks/pre-edit-validate.py; echo "exit: $?"
```
Expected: `exit: 2`

- [ ] **Step 7: Test that legitimate code is NOT blocked**

```bash
# Protocol stub with Any (should pass -- the regex targets signatures)
echo '{"tool_input": {"file_path": "'$(pwd)'/src/nexus/api/errors.py", "content": "from typing import Any\nclass P:\n    @property\n    def x(self) -> Any:\n        ..."}}' \
  | python3 .claude/hooks/pre-edit-validate.py; echo "exit: $?"
```
Expected: `exit: 0` (Protocol stub with `...` body -- context matters)

Note: if false positives appear, tighten the regex. The `bare-any-in-sig` and
`dict-any-in-sig` patterns only match inside `def` lines, not bare assignments.

- [ ] **Step 8: Run ruff on the hook itself**

```bash
poetry run ruff check .claude/hooks/pre-edit-validate.py
```

Expected: 0 violations.

- [ ] **Step 9: Commit**

```bash
git add .claude/hooks/pre-edit-validate.py
git commit -m "feat: add type-ignore-ban, bare-any, dict-any, deferred-import blocking rules"
```

---

## Task 8: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

Update to reflect Python 3.14, 3-tier enforcement, and the 4 new blocking rules.

- [ ] **Step 1: Read current CLAUDE.md**

```
cat CLAUDE.md
```

- [ ] **Step 2: Apply these targeted changes**

**Change 1 -- Python version line:**
```
# From:
- Python 3.12+. Do NOT use Python 3.14-only syntax (PEP 758, Path.copy, etc.).
# To:
- Python 3.14+. Use all Python 3.14 syntax including PEP 758 (unparenthesized except).
```

**Change 2 -- Add 3-tier enforcement section** (after the Standards section):
```markdown
## Enforcement Model (3 tiers)

**Tier 1 -- Blocking (pre-edit hook):** Fails before any file is written. Zero tolerance.
  Rules: no-mocks, no-relative-imports, no-bare-except, no-lru-cache-none,
         no-unittest-testcase, no-sys-argv, no-type-ignore, no-bare-any-in-sig,
         no-dict-any-in-sig, no-deferred-import

**Tier 2 -- Ratchet (.ratchet.json):** Violations can only decrease, never increase.
  Rules: per-module coverage, McCabe complexity, file line count (plan 2)

**Tier 3 -- Soft (post-edit warning):** Advisory only, never blocks.
  Rules: missing test file, unclosed resource handle (plan 2)
```

**Change 3 -- Type checking line:**
```
# From:
- Type checker: mypy strict.
# To:
- Type checkers: mypy strict + pyright strict. Both must report 0 errors.
  No # type: ignore anywhere. For untyped third-party packages add stubs to src/stubs/.
```

**Change 4 -- Add Pydantic conventions:**
```markdown
## Pydantic Conventions

All Pydantic models use:
```python
model_config = ConfigDict(frozen=True, strict=True, extra="forbid")
```
Fields with constraints use `Annotated[Type, Field(...)]`.
Cross-field validators return `Self`.
No `dict[str, Any]` in public Pydantic interfaces -- define TypedDicts.
```

- [ ] **Step 3: Run ruff on CLAUDE.md** (it's not Python but verify no issues)

```bash
poetry run pytest -q
```

Expected: all tests pass, coverage >= 100%.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md for Python 3.14, 3-tier enforcement, dual type checking"
```

---

## Final Verification

- [ ] **Run the full suite one last time**

```bash
poetry run pytest -v
poetry run ruff check src/nexus/ tests/
poetry run mypy src/nexus/
poetry run pyright src/nexus/
```

Expected:
- All tests pass
- ruff: 0 violations
- mypy: 0 errors
- pyright: 0 errors
- Coverage >= 100% for implemented modules (stubs at 0% are expected)

- [ ] **Confirm hooks work**

Edit a file to trigger the post-edit hook and verify it produces useful stderr output
if there are violations. The hook should now be responsive (no more "No stderr output").

- [ ] **Push to GitHub**

```bash
git push origin main
```

Verify CI passes on the lint-only matrix.
