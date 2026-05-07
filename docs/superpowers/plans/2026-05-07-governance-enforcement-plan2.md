# Governance Enforcement -- Plan 2 (Ratchet, CI, ADRs) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 81 pre-existing ruff violations, add the coverage ratchet baseline, lean CI for solo dev, pre-commit hook, and 8 formal ADR files (ADR-006 through ADR-013).

**Architecture:** Sequential tasks -- ruff fixes first so later tasks don't trigger the new blocking rules when editing those files. Ratchet baseline uses the current coverage numbers as the floor. CI restructured to lint-only on every push.

**Tech Stack:** Python 3.14, ruff --fix, pytest-cov JSON, pre-commit, GitHub Actions.

---

## File Map

```
Modify:  many src/ stub files              -- add minimal module/package docstrings (D100/D104)
Modify:  many src/ source files            -- __init__ docstrings (D107), sort __all__ (RUF022)
Modify:  tests/test_capabilities.py        -- fix type:ignore, narrow pytest.raises
Modify:  tests/test_config.py              -- fix type:ignore, narrow pytest.raises, remove unused import
Modify:  tests/fakes/fake_sn_client.py     -- remove quoted annotation (UP037)
Create:  .ratchet.json                     -- per-module coverage baseline
Modify:  .claude/hooks/post-edit-lint.py   -- add per-module coverage ratchet check
Modify:  .github/workflows/ci.yml          -- lean CI (lint only on push, tests on tag)
Create:  .pre-commit-config.yaml           -- pre-commit hook running full test suite
Create:  .primer/adr/ADR-006 through 009   -- 4 ADR files
Create:  .primer/adr/ADR-010 through 013   -- 4 ADR files
Modify:  .primer/governance.md             -- update with 3-tier model and new ADR catalog
Modify:  .primer/decisions.md             -- append new decisions
```

---

## Task 1: Fix Auto-Fixable ruff Violations

**Files:**
- Modify: multiple files across src/ and tests/

81 ruff errors currently. 23 are auto-fixable (RUF022 __all__ sort, UP037 quoted
annotations, I001 import sort, F401 unused imports). Fix those first.

- [ ] **Step 1: Run ruff --fix on src/ and tests/**

```bash
cd /Users/pierre.grothe/Developer/nexus && poetry run ruff check --fix src/nexus/ tests/
```

This auto-fixes: `RUF022` (sort `__all__`), `UP037` (remove quoted annotations),
`I001` (sort imports), `F401` (remove unused imports).

- [ ] **Step 2: Check what remains**

```bash
poetry run ruff check src/nexus/ tests/ 2>&1 | grep "^D\|^PT" | head -20
```

Expected: D100, D104, D107, PT011 violations remain (not auto-fixable).

- [ ] **Step 3: Count D violations by type**

```bash
poetry run ruff check src/nexus/ tests/ 2>&1 | grep -c "^.*D100\|D104\|D107"
```

- [ ] **Step 4: Commit the auto-fixes**

```bash
git add -A && git commit -m "fix: auto-fix ruff violations (sort __all__, remove quoted annotations, sort imports)"
```

---

## Task 2: Fix D100/D104/D107 -- Add Missing Docstrings to Stub Modules

**Files:**
- Modify: all stub/empty modules in src/nexus/ flagged with D100/D104/D107

Stub modules (empty or near-empty files) need at least a one-line module docstring
to satisfy D100 (public module) and D104 (public package). `__init__` methods
without docstrings need D107 fixes.

- [ ] **Step 1: Get the full list of D violations**

```bash
cd /Users/pierre.grothe/Developer/nexus && poetry run ruff check src/nexus/ --select D 2>&1 | grep "D100\|D104\|D107"
```

- [ ] **Step 2: Add module docstrings to D100 stub files**

For each file flagged with D100 that is a stub (empty body or `raise NotImplementedError`),
add a one-line module docstring as the first non-comment line. Pattern:

```python
# src/nexus/agents/orchestrator.py
# MasterOrchestrator: coordinates all specialist agents.
# Author: Pierre Grothe
# Date: 2026-05-07
"""MasterOrchestrator: stub -- to be implemented in 2026.07."""
```

Files to fix (D100, stub modules):
- `src/nexus/agents/context.py` → `"""Execution context for agent runs: stub."""`
- `src/nexus/agents/orchestrator.py` → `"""MasterOrchestrator: stub."""`
- `src/nexus/agents/router.py` → `"""IntentRouter: stub."""`
- `src/nexus/agents/specialists/csm.py` → `"""CSM specialist agent: stub."""`
- `src/nexus/agents/specialists/hrsd.py` → `"""HRSD specialist agent: stub."""`
- `src/nexus/agents/specialists/irm.py` → `"""IRM specialist agent: stub."""`
- `src/nexus/agents/specialists/itom.py` → `"""ITOM specialist agent: stub."""`
- `src/nexus/agents/specialists/itsm.py` → `"""ITSM specialist agent: stub."""`
- `src/nexus/agents/specialists/platform.py` → `"""Platform specialist agent: stub."""`
- `src/nexus/agents/specialists/secops.py` → `"""SecOps specialist agent: stub."""`
- `src/nexus/agents/specialists/spm.py` → `"""SPM specialist agent: stub."""`
- `src/nexus/assessment/readiness.py` → `"""Readiness gate checker: stub."""`
- `src/nexus/assessment/reporter.py` → `"""Assessment reporter: stub."""`
- `src/nexus/assessment/rules.py` → `"""Assessment rule engine: stub."""`
- `src/nexus/assessment/scanner.py` → `"""Instance scanner: stub."""`
- `src/nexus/assessment/schemas/health.py` → `"""Health assessment schema: stub."""`
- `src/nexus/assessment/schemas/readiness.py` → `"""Readiness schema: stub."""`
- `src/nexus/assessment/schemas/validation.py` → `"""Validation schema: stub."""`
- `src/nexus/assessment/validator.py` → `"""Post-deploy validator: stub."""`
- `src/nexus/execution/dispatcher.py` → `"""Execution dispatcher: stub."""`
- `src/nexus/execution/planner.py` → `"""Execution planner: stub."""`
- `src/nexus/execution/reporter.py` → `"""Execution reporter: stub."""`
- `src/nexus/execution/rollback.py` → `"""Rollback manager: stub."""`
- `src/nexus/knowledge/index.py` → `"""Product knowledge index: stub."""`
- `src/nexus/knowledge/loader.py` → `"""Knowledge loader: stub."""`
- `src/nexus/templates/apply.py` → `"""Template apply engine: stub."""`
- `src/nexus/templates/registry.py` → `"""Template registry: stub."""`
- `src/nexus/templates/schemas/ai_agent.py` → `"""AI agent template schema: stub."""`
- `src/nexus/templates/schemas/catalog_item.py` → `"""Catalog item schema: stub."""`
- `src/nexus/templates/schemas/now_assist_skill.py` → `"""NowAssist skill schema: stub."""`
- `src/nexus/templates/schemas/project.py` → `"""Project schema: stub."""`
- `src/nexus/templates/schemas/recipe.py` → `"""Recipe schema: stub."""`
- `src/nexus/templates/schemas/workflow.py` → `"""Workflow schema: stub."""`
- `src/nexus/templates/sync.py` → `"""GitHub template sync: stub."""`
- `src/nexus/templates/validator.py` → `"""Template YAML validator: stub."""`
- `src/nexus/ui/app.py` → `"""NiceGUI application: stub (requires nexus[ui])."""`

For D104 (public package `__init__.py` missing docstring), add to each empty `__init__.py`:
- `src/nexus/agents/__init__.py` → `"""Agent package."""`
- `src/nexus/agents/specialists/__init__.py` → `"""Specialist agents package."""`
- `src/nexus/assessment/__init__.py` → `"""Assessment package."""`
- `src/nexus/assessment/schemas/__init__.py` → `"""Assessment schemas package."""`
- `src/nexus/execution/__init__.py` → `"""Execution package."""`
- `src/nexus/knowledge/__init__.py` → `"""Knowledge package."""`
- `src/nexus/templates/__init__.py` → `"""Templates package."""`
- `src/nexus/templates/schemas/__init__.py` → `"""Template schemas package."""`

- [ ] **Step 3: Fix D107 -- add __init__ docstrings**

Files with D107 (missing `__init__` docstring):
- `src/nexus/auth/claude.py` ClaudeAuth.__init__: add `"""Initialize with optional keychain and org."""`
- `src/nexus/auth/errors.py` AuthError.__init__: add `"""Initialize with service, username, and optional suggestion."""`
- `src/nexus/auth/keychain.py` KeychainClient.__init__: add `"""Initialize with optional service prefix."""`
- `src/nexus/auth/servicenow.py` SNAuth.__init__: add `"""Initialize with optional keychain client."""`
- `src/nexus/connectors/servicenow/errors.py` SNClientError.__init__: add `"""Initialize with message, optional status code and suggestion."""`
- Any other D107 files reported by ruff

- [ ] **Step 4: Run ruff to confirm D violations are resolved**

```bash
cd /Users/pierre.grothe/Developer/nexus && poetry run ruff check src/nexus/ tests/ 2>&1 | grep " D" | head -5
```

Expected: no D violations remaining. If any remain, fix them.

- [ ] **Step 5: Run full test suite**

```bash
poetry run pytest -q 2>&1 | tail -3
```

Expected: 53 passed (coverage failure expected).

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "fix: add module docstrings to all stub files, fix D107 __init__ docstrings"
```

---

## Task 3: Fix type: ignore in Test Files

**Files:**
- Modify: `tests/test_capabilities.py`
- Modify: `tests/test_config.py`
- Modify: `tests/fakes/fake_sn_client.py` (if UP037 not auto-fixed in Task 1)

These files have `# type: ignore[misc]` (our new blocking rule will prevent editing
them until fixed) and `pytest.raises(Exception)` too broad (PT011).

- [ ] **Step 1: Read the failing sections**

```bash
grep -n "type: ignore\|pytest.raises(Exception)" /Users/pierre.grothe/Developer/nexus/tests/test_capabilities.py /Users/pierre.grothe/Developer/nexus/tests/test_config.py
```

- [ ] **Step 2: Fix test_capabilities.py**

Find `test_capability_set_is_immutable` (or similar). Replace the frozen-check test:

```python
# Before (has type: ignore[misc]):
with pytest.raises(Exception):
    caps.available_servers = frozenset()  # type: ignore[misc]

# After:
from dataclasses import FrozenInstanceError

with pytest.raises(FrozenInstanceError):
    setattr(caps, "available_servers", frozenset())
```

`setattr(obj, name, value)` bypasses mypy's frozen-field type check (setattr takes
`Any` value) while still triggering the runtime `FrozenInstanceError` from the
frozen dataclass. `FrozenInstanceError` is available in Python 3.11+.

Add `from dataclasses import FrozenInstanceError` to the test file imports.

- [ ] **Step 3: Fix test_config.py**

Find the frozen config test. Replace:

```python
# Before:
with pytest.raises(Exception):
    config.preferences = config.preferences  # type: ignore[misc]

# After:
from pydantic import ValidationError

with pytest.raises(ValidationError):
    setattr(config, "auto_probe", not config.auto_probe)
```

Pydantic v2 frozen models raise `ValidationError` when mutated at runtime. `setattr`
bypasses mypy's property-readonly check. Remove the unused `import os` at line 98
(deferred import inside the test function) if Task 1's auto-fix didn't catch it.

Also check: `test_config.py` has `import os` as a deferred import inside a function
body. Remove it:
```python
# Before (inside a test function):
    import os
    monkeypatch.delenv("NEXUS_CONFIG_PATH", raising=False)

# After:
    monkeypatch.delenv("NEXUS_CONFIG_PATH", raising=False)
```

- [ ] **Step 4: Verify no type: ignore or broad pytest.raises remain**

```bash
grep -n "type: ignore\|pytest.raises(Exception)" tests/test_capabilities.py tests/test_config.py
```

Expected: no output.

- [ ] **Step 5: Run ruff and tests**

```bash
cd /Users/pierre.grothe/Developer/nexus && poetry run ruff check tests/test_capabilities.py tests/test_config.py && poetry run pytest tests/test_capabilities.py tests/test_config.py -v 2>&1 | tail -10
```

Expected: 0 violations, all tests pass.

- [ ] **Step 6: Commit**

```bash
git add tests/test_capabilities.py tests/test_config.py && git commit -m "fix: replace type:ignore with setattr, narrow pytest.raises to specific exceptions"
```

---

## Task 4: Create .ratchet.json and Per-Module Coverage Gate

**Files:**
- Create: `.ratchet.json`
- Modify: `.claude/hooks/post-edit-lint.py`

The ratchet tracks per-module covered lines. When `src/nexus/X/Y.py` is edited,
the post-edit hook runs pytest for that module and blocks if covered lines decrease
from the baseline.

- [ ] **Step 1: Write .ratchet.json with current coverage baseline**

Create `/Users/pierre.grothe/Developer/nexus/.ratchet.json`:

```json
{
  "version": "1",
  "note": "Modules at 0% excluded -- stubs awaiting implementation. Only modules with tests are tracked.",
  "modules": {
    "nexus.api.client": {"covered_lines": 60, "total_lines": 63},
    "nexus.api.errors": {"covered_lines": 6, "total_lines": 6},
    "nexus.api.logging_config": {"covered_lines": 19, "total_lines": 20},
    "nexus.api.tool_registry": {"covered_lines": 16, "total_lines": 16},
    "nexus.auth.claude": {"covered_lines": 27, "total_lines": 30},
    "nexus.auth.errors": {"covered_lines": 7, "total_lines": 7},
    "nexus.auth.keychain": {"covered_lines": 11, "total_lines": 26},
    "nexus.auth.servicenow": {"covered_lines": 19, "total_lines": 29},
    "nexus.capabilities.feature_flags": {"covered_lines": 27, "total_lines": 27},
    "nexus.capabilities.probe": {"covered_lines": 17, "total_lines": 40},
    "nexus.capabilities.registry": {"covered_lines": 29, "total_lines": 29},
    "nexus.config.manager": {"covered_lines": 29, "total_lines": 30},
    "nexus.config.paths": {"covered_lines": 36, "total_lines": 37},
    "nexus.config.settings": {"covered_lines": 35, "total_lines": 35},
    "nexus.connectors.base": {"covered_lines": 15, "total_lines": 18},
    "nexus.connectors.registry": {"covered_lines": 22, "total_lines": 28}
  }
}
```

- [ ] **Step 2: Read current post-edit-lint.py**

```bash
cat /Users/pierre.grothe/Developer/nexus/.claude/hooks/post-edit-lint.py
```

- [ ] **Step 3: Add per-module coverage check to post-edit-lint.py**

After the existing `is_target()` function, add a `_module_name()` helper and a
`check_coverage_ratchet()` function. Then call it from `main()` after the pyright
check.

Add these after the `run()` function:

```python
import json as _json


def _module_name(path: Path) -> str | None:
    """Derive nexus.X.Y module name from a src/nexus/X/Y.py path.

    Args:
        path: Absolute path to a Python file.

    Returns:
        Module name string, or None if path is not under src/nexus/.
    """
    try:
        rel = path.relative_to(NEXUS_SRC)
    except ValueError:
        return None
    parts = list(rel.parts)
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = parts[-1].removesuffix(".py")
    return "nexus." + ".".join(parts)


def check_coverage_ratchet(path: Path) -> str | None:
    """Run coverage for the edited module and block if covered lines decrease.

    Args:
        path: Path to the edited source file.

    Returns:
        Error string if coverage decreased, None if clean.
    """
    module = _module_name(path)
    if module is None:
        return None

    ratchet_path = REPO_ROOT / ".ratchet.json"
    if not ratchet_path.exists():
        return None

    ratchet = _json.loads(ratchet_path.read_text())
    baseline = ratchet.get("modules", {}).get(module)
    if baseline is None:
        return None  # module not yet in ratchet -- skip

    baseline_covered = baseline["covered_lines"]

    rc, out = run([
        "poetry", "run", "pytest",
        f"--cov=nexus",
        "--cov-report=json",
        "--cov-fail-under=0",  # don't fail on threshold here
        "-q", "--tb=no",
    ])

    cov_file = REPO_ROOT / "coverage.json"
    if not cov_file.exists():
        return None

    cov_data = _json.loads(cov_file.read_text())
    # Map module name to file path key
    for file_key, file_data in cov_data.get("files", {}).items():
        if module.replace(".", "/") in file_key.replace("\\", "/"):
            current_covered = file_data["summary"]["covered_lines"]
            if current_covered < baseline_covered:
                return (
                    f"RATCHET VIOLATION: {module} coverage decreased "
                    f"({current_covered} < {baseline_covered} covered lines). "
                    f"Add tests before reducing coverage."
                )
            break

    return None
```

Then in `main()`, add the ratchet check after the pyright block:

```python
    ratchet_issue = check_coverage_ratchet(path)
    if ratchet_issue:
        issues.append(f"ratchet:\n{ratchet_issue}")
```

- [ ] **Step 4: Run ruff on the hook**

```bash
cd /Users/pierre.grothe/Developer/nexus && poetry run ruff check .claude/hooks/post-edit-lint.py
```

Expected: 0 violations.

- [ ] **Step 5: Test that ratchet does not block on a clean file**

```bash
echo "{\"tool_input\": {\"file_path\": \"$(pwd)/src/nexus/api/errors.py\", \"content\": \"\"}}" | python3 .claude/hooks/post-edit-lint.py; echo "exit: $?"
```

Expected: `exit: 0`

- [ ] **Step 6: Commit**

```bash
git add .ratchet.json .claude/hooks/post-edit-lint.py && git commit -m "feat: add coverage ratchet baseline and per-module gate in post-edit hook"
```

---

## Task 5: Lean CI and Pre-Commit Hook

**Files:**
- Modify: `.github/workflows/ci.yml`
- Create: `.pre-commit-config.yaml`

CI restructured for solo dev: lint/type on every push (<30s), full tests on release
tags only. Pre-commit hook runs full test suite before every local commit.

- [ ] **Step 1: Replace ci.yml**

Write `/Users/pierre.grothe/Developer/nexus/.github/workflows/ci.yml`:

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  lint:
    name: Lint and type check
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python 3.14
        uses: actions/setup-python@v5
        with:
          python-version: "3.14"

      - name: Install Poetry
        uses: snok/install-poetry@v1

      - name: Install dependencies
        run: poetry install

      - name: Check formatting (black)
        run: poetry run black --check src/nexus/ tests/

      - name: Lint (ruff)
        run: poetry run ruff check src/nexus/ tests/

      - name: Type check (mypy)
        run: poetry run mypy src/nexus/

      - name: Type check (pyright)
        run: poetry run pyright src/nexus/

  test:
    name: Full test suite (release tags only)
    runs-on: ${{ matrix.os }}
    if: startsWith(github.ref, 'refs/tags/')
    strategy:
      matrix:
        os: [ubuntu-latest, macos-latest, windows-latest]
        python-version: ["3.14"]

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}

      - name: Install Poetry
        uses: snok/install-poetry@v1

      - name: Install dependencies
        run: poetry install

      - name: Run tests
        run: poetry run pytest
```

Note: the `test` job indentation must be at the top-level `jobs:` key, not nested
under `lint`. Verify the YAML is valid.

- [ ] **Step 2: Create .pre-commit-config.yaml**

Write `/Users/pierre.grothe/Developer/nexus/.pre-commit-config.yaml`:

```yaml
repos:
  - repo: local
    hooks:
      - id: pytest
        name: Run test suite
        entry: poetry run pytest -q --tb=short
        language: system
        types: [python]
        pass_filenames: false
        always_run: true
```

- [ ] **Step 3: Install pre-commit hooks**

```bash
cd /Users/pierre.grothe/Developer/nexus && poetry run pre-commit install
```

Expected: `pre-commit installed at .git/hooks/pre-commit`

- [ ] **Step 4: Test the pre-commit hook runs**

```bash
cd /Users/pierre.grothe/Developer/nexus && poetry run pre-commit run --all-files 2>&1 | tail -5
```

Expected: pytest runs and reports "53 passed" (with coverage failure -- that's OK for
pre-commit, the hook will pass as long as pytest exits 0 for the tests themselves).

Note: if coverage gate causes `pytest` to exit 1 (failure), change the pre-commit
entry to pass coverage failure gracefully:

```yaml
entry: poetry run pytest -q --tb=short -p no:cov
```

This disables the coverage plugin for pre-commit (coverage is checked by the post-edit
hook, not pre-commit).

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/ci.yml .pre-commit-config.yaml && git commit -m "feat: lean CI (lint only on push, tests on tags), add pre-commit hook"
```

---

## Task 6: Write ADR-006 through ADR-009

**Files:**
- Create: `.primer/adr/ADR-006-python-3-14-minimum.md`
- Create: `.primer/adr/ADR-007-zero-type-ignore.md`
- Create: `.primer/adr/ADR-008-type-annotation-completeness.md`
- Create: `.primer/adr/ADR-009-behavioral-test-completeness.md`

Create each file in `.primer/adr/` using this exact content:

- [ ] **Step 1: Create ADR-006**

```
/Users/pierre.grothe/Developer/nexus/.primer/adr/ADR-006-python-3-14-minimum.md
```

Content:
```markdown
# ADR-006: Python 3.14 Minimum

**Status:** accepted
**Date:** 2026-05-07
**Enforcement:** hook (pyproject.toml constraint check)

## Context

The project was scaffolded targeting Python 3.12+ with a broad constraint. The active
dev environment runs Python 3.14.3. Sprint retrospective identified that the broad
constraint caused Poetry to resolve to Python 3.14, triggering nicegui version
conflicts and demonstrating the constraint was misleading.

## Decision

Minimum Python version is `>=3.14,<3.15` in pyproject.toml. All Python 3.14 syntax
is permitted and preferred, including PEP 758 unparenthesized multi-except, PEP 649
deferred annotation evaluation (default in 3.14, making `from __future__ import
annotations` optional), and PEP 695 type parameter syntax.

## Consequences

CLAUDE.md updated: "Python 3.14+. All 3.14 syntax permitted." The prior "Do NOT use
Python 3.14-only syntax" restriction is removed. CI matrix updated to Python 3.14
only. Black and ruff target-version updated to py314.
```

- [ ] **Step 2: Create ADR-007**

```
/Users/pierre.grothe/Developer/nexus/.primer/adr/ADR-007-zero-type-ignore.md
```

Content:
```markdown
# ADR-007: Zero type: ignore Tolerance

**Status:** accepted
**Date:** 2026-05-07
**Enforcement:** blocking hook (pre-edit-validate.py)

## Context

During MVP Step 1, four `# type: ignore[type-arg]` comments appeared in test fakes
to suppress list annotation errors. These masked real type gaps: fakes used
`SimpleNamespace` instead of typed dataclasses, and list return types were
unparameterized. The market-analysis-service blocks all type: ignore with the
same rationale.

## Decision

No `# type: ignore` comment is permitted anywhere in the codebase (src/ or tests/).
The pre-edit hook pattern `#\s*type:\s*ignore` blocks any file containing it.

For untyped third-party packages: add a stub file under `src/stubs/<package>.pyi`
or add `ignore_missing_imports = true` in `[mypy.<module>]` config for that package.

## Consequences

All existing type: ignore comments were removed in Plan 1. The pre-edit hook
enforces zero-tolerance going forward. Protocol definitions used in tests must be
structurally compatible with real objects -- no escaping via type: ignore.
```

- [ ] **Step 3: Create ADR-008**

```
/Users/pierre.grothe/Developer/nexus/.primer/adr/ADR-008-type-annotation-completeness.md
```

Content:
```markdown
# ADR-008: Type Annotation Completeness

**Status:** accepted
**Date:** 2026-05-07
**Enforcement:** blocking hook (pre-edit-validate.py) + pyright strict

## Context

Sprint retrospective issues #1-5: bare Any in test parameters, dict[str, Any] in
public interfaces, object return types, and return values flowing as Any through
untyped sources. These issues caused incorrect fakes, undetected Protocol
mismatches, and mypy-silent type gaps.

## Decision

Three rules enforced by the pre-edit hook:

1. No bare Any in function signatures: blocks `: Any` and `-> Any` in def lines.
   Use `object`, a Protocol, or a TypedDict.

2. No dict[str, Any] in public interfaces: blocks `dict[str, Any]` in function
   signatures. Use TypedDict, a Protocol, or a Pydantic model.

3. No object return types in functions with a body: -> object is valid only in
   Protocol stubs (... body). Concrete functions declare the actual return type.

TYPE_CHECKING-guarded imports are exempted from the deferred-import check.

## Consequences

Fakes must use typed dataclasses that structurally satisfy their target Protocols.
The Anthropic SDK's ToolParam TypedDict is used instead of dict[str, Any] for tool
definitions. Protocol chains use Iterable[_Entry] (covariant) instead of
list[_Entry] (invariant) at SDK boundaries.
```

- [ ] **Step 4: Create ADR-009**

```
/Users/pierre.grothe/Developer/nexus/.primer/adr/ADR-009-behavioral-test-completeness.md
```

Content:
```markdown
# ADR-009: Behavioral Test Completeness

**Status:** accepted
**Date:** 2026-05-07
**Enforcement:** ratchet (.ratchet.json, post-edit hook)

## Context

Sprint issue #7: the configure_logging test only verified directory creation, not
that handlers were attached. The test passed even when the handler-attachment code
was unreachable (due to conftest.py setting up root logger at module scope). Issue
#8: filter exclusion logic in _discover_model had no tests at all.

## Decision

Three rules:

1. Every code path must be exercised. Per-module coverage is tracked in .ratchet.json.
   The post-edit hook runs pytest for the edited module and blocks if covered lines
   decrease from baseline.

2. Tests must assert on behavior. A test whose assertions could all pass even if the
   function raised NotImplementedError is a vacuous test. Tests must assert on return
   values, state changes, or side effects of the function being tested.

3. Coverage gate is 100% (pyproject.toml --cov-fail-under=100). Stub modules are
   excluded from the ratchet baseline until they have implementations.

## Consequences

Logging tests must clear root logger handlers before testing, then restore them in
a finally block with explicit handler.close() calls. Filter/exclusion logic requires
dedicated tests for each filtering rule. The ratchet baseline in .ratchet.json stores
per-module covered-lines counts.
```

- [ ] **Step 5: Commit**

```bash
git add .primer/adr/ADR-006*.md .primer/adr/ADR-007*.md .primer/adr/ADR-008*.md .primer/adr/ADR-009*.md
git commit -m "docs: add ADR-006 through ADR-009 (Python 3.14, type safety, test completeness)"
```

---

## Task 7: Write ADR-010 through ADR-013

**Files:**
- Create: `.primer/adr/ADR-010-resource-lifecycle-in-tests.md`
- Create: `.primer/adr/ADR-011-3-tier-enforcement-model.md`
- Create: `.primer/adr/ADR-012-dual-type-checking.md`
- Create: `.primer/adr/ADR-013-lean-ci-solo-dev.md`

- [ ] **Step 1: Create ADR-010**

```
/Users/pierre.grothe/Developer/nexus/.primer/adr/ADR-010-resource-lifecycle-in-tests.md
```

Content:
```markdown
# ADR-010: Resource Lifecycle in Tests

**Status:** accepted
**Date:** 2026-05-07
**Enforcement:** soft (post-edit warning)

## Context

Sprint issue #10: a TimedRotatingFileHandler opened during the configure_logging test
was not closed before the root logger handlers were cleared. This leaked file
descriptors and caused PermissionError on Windows when pytest cleaned up tmp_path.
The test passed on macOS because rmtree uses ignore_errors=True.

## Decision

Any OS resource opened during a test (file handle, logging handler, socket) must be
explicitly closed in a finally block:

```python
finally:
    for h in root.handlers:
        h.close()
    root.handlers.clear()
    root.handlers.extend(saved_handlers)
```

Context managers are preferred where supported. The post-edit hook warns (soft) when
it detects TimedRotatingFileHandler, FileHandler, or socket.socket( in a test file
without a corresponding .close() or `with` statement.

## Consequences

All test teardown logic closes resources before restoring state. The configure_logging
test correctly closes handlers in its finally block. This prevents CI failures on
Windows runners where open file handles block directory cleanup.
```

- [ ] **Step 2: Create ADR-011**

```
/Users/pierre.grothe/Developer/nexus/.primer/adr/ADR-011-3-tier-enforcement-model.md
```

Content:
```markdown
# ADR-011: 3-Tier Enforcement Model

**Status:** accepted
**Date:** 2026-05-07
**Enforcement:** governance doc + hook architecture

## Context

Sprint issues #12-13: the post-edit hook silently failed due to shell expansion.
The single-tier "block or ignore" model collapsed to "ignore" when the hook broke.
The market-analysis-service uses a 3-tier model (blocking, ratchet, soft) that
provides graduated enforcement.

## Decision

Three enforcement tiers:

Tier 1 -- Blocking (pre-edit-validate.py, PreToolUse): runs before file is written.
Failure prevents the write. Output on stderr. Zero tolerance.
Current rules (10): no-mocks, no-relative-imports, no-bare-except, no-lru-cache-none,
no-unittest-testcase, no-sys-argv, no-type-ignore, no-bare-any-in-sig,
no-dict-any-in-sig, no-deferred-import.

Tier 2 -- Ratchet (.ratchet.json, post-edit-lint.py): tracks numeric baselines.
Metrics can only improve. Currently tracks per-module covered lines.

Tier 3 -- Soft (post-edit-lint.py warning): advisory only. Currently tracks
missing-test-file and unclosed-resource-handle.

Hook reliability contract: REPO_ROOT via Path(__file__) (not shell expansion).
All blocking output on stderr. Exit codes: 0 clean, 2 blocking violation.

## Consequences

Broken hooks now produce stderr output visible in Claude Code blocking messages.
The hook command in settings.json uses relative paths (python3 .claude/hooks/...).
Pre-edit hook blocks 10 patterns at write time, not just at CI.
```

- [ ] **Step 3: Create ADR-012**

```
/Users/pierre.grothe/Developer/nexus/.primer/adr/ADR-012-dual-type-checking.md
```

Content:
```markdown
# ADR-012: Dual Type Checking (mypy + pyright strict)

**Status:** accepted
**Date:** 2026-05-07
**Enforcement:** blocking (post-edit-lint.py) + CI

## Context

Sprint issue #4: _ModelsList Protocol was structurally incompatible with the SDK's
Models type. mypy passed because Anthropic uses Any for the models attribute. pyright
in strict mode would have caught the incompatibility via structural Protocol checking.
The two checkers complement each other -- mypy excels at control flow analysis,
pyright at structural compatibility and Protocol conformance.

## Decision

Both `mypy --strict` and `pyright --strict` must pass with 0 errors on every edited
Python file. The post-edit hook runs both. CI runs both. When they disagree, the
stricter interpretation wins. Fix the code, not the config.

mypy config: strict=true, warn_return_any=true, warn_unused_ignores=true,
strict_equality=true, python_version=3.14.

pyright config: typeCheckingMode=strict, pythonVersion=3.14.

## Consequences

_ModelDiscoveryClient now has a proper _ModelsList Protocol (list() -> Iterable[_ModelEntry])
that both mypy and pyright accept. cast() is used at SDK boundaries where structural
compatibility cannot be proven statically. No type: ignore is ever used.
```

- [ ] **Step 4: Create ADR-013**

```
/Users/pierre.grothe/Developer/nexus/.primer/adr/ADR-013-lean-ci-solo-dev.md
```

Content:
```markdown
# ADR-013: Lean CI for Solo Developer

**Status:** accepted
**Date:** 2026-05-07
**Enforcement:** ci.yml

## Context

The original CI ran the full test suite on a 3-OS matrix (ubuntu/macos/windows) on
every push. For a solo developer who tests locally before every commit, this was
redundant overhead (3+ minutes) that slowed feedback without adding safety.

## Decision

CI is restructured into two stages:

Stage 1 -- Lint/type (every push, <30 seconds):
- black --check, ruff check, mypy, pyright
- Single OS (ubuntu-latest), single Python (3.14), no matrix.

Stage 2 -- Full tests (release tags only):
- pytest --cov-fail-under=100
- Cross-platform matrix: ubuntu + macos + windows

Local enforcement: pre-commit hook runs pytest before every commit.
Post-edit hook enforces per-module coverage ratchet after every file write.

## Consequences

CI feedback is fast (<30s) for every push. Test coverage is enforced locally via
post-edit hook and pre-commit hook. If a co-developer joins, Stage 2 should be
moved back to every push. The pyrightconfig.json `pythonPlatform: "Darwin"` should
be changed to null or removed for CI (Linux runner) compatibility.
```

- [ ] **Step 5: Commit**

```bash
git add .primer/adr/ADR-010*.md .primer/adr/ADR-011*.md .primer/adr/ADR-012*.md .primer/adr/ADR-013*.md
git commit -m "docs: add ADR-010 through ADR-013 (resources, enforcement, type checking, CI)"
```

---

## Task 8: Update governance.md, decisions.md, and primer sync

**Files:**
- Modify: `.primer/governance.md`
- Modify: `.primer/decisions.md`

- [ ] **Step 1: Read current governance.md**

```bash
cat /Users/pierre.grothe/Developer/nexus/.primer/governance.md
```

- [ ] **Step 2: Rewrite governance.md**

Replace the full content with the updated 3-tier model and complete ADR catalog:

```markdown
# Governance

## Enforcement Gates

### Tier 1 -- Blocking (pre-edit hook, prevents file write)

- no-mocks -- blocks unittest.mock, MagicMock, @patch, pytest_mock
- no-relative-imports -- blocks from .module style
- no-bare-except -- blocks bare except: clauses
- no-lru-cache-none -- blocks @lru_cache(maxsize=None)
- no-unittest-testcase -- blocks class Foo(TestCase) in test files
- no-sys-argv -- blocks sys.argv indexing outside test files
- no-type-ignore -- blocks # type: ignore anywhere (ADR-007)
- no-bare-any-in-sig -- blocks : Any or -> Any in function signatures (ADR-008)
- no-dict-any-in-sig -- blocks dict[str, Any] in function signatures (ADR-008)
- no-deferred-import -- blocks import inside def/class bodies

### Tier 2 -- Ratchet (post-edit hook, blocks if metrics worsen)

- coverage-ratchet -- per-module covered lines can only increase (ADR-009)
  Baseline: .ratchet.json (updated when coverage improves)

### Tier 3 -- Soft (post-edit warning, never blocks)

- missing-test-file -- warns if src/nexus/X/Y.py edited without tests/
- resource-open -- warns if file handle / logging handler opened in test without close

### CI (blocks merge to main, every push)

- black-check -- formatting (black --check src/nexus/ tests/)
- ruff-check -- lint (ruff check src/nexus/ tests/)
- mypy -- type check (mypy src/nexus/) -- ADR-012
- pyright -- type check (pyright src/nexus/) -- ADR-012

### Pre-commit (blocks local commit)

- pytest -- full test suite (poetry run pytest -q -p no:cov)

## Agent-Enforced Rules

- calver -- CalVer YYYY.0M.PATCH; version set manually in pyproject.toml
- file-headers -- new Python files: # path, # description, # Author, # Date
- docstrings -- Google-style docstrings on all public functions, classes, methods
- module-exports -- every module declares explicit __all__
- pydantic-frozen -- ConfigDict(frozen=True, strict=True, extra="forbid")
- utc-only -- datetime.now(UTC); no naive datetimes
- slots-dataclass -- @dataclass(slots=True) for structured data
- enum-dispatch -- match/case with case _: default
- no-print -- logging.getLogger(__name__) in library code
- secrets-keychain -- secrets in OS keychain only
- layer-order -- config < auth < capabilities < api/connectors < agents/... < cli
- test-naming -- test_<function>_<scenario> convention
- 100-coverage -- 100% line coverage target for implemented modules
- behavioral-tests -- tests must assert on behavior, not just side effects (ADR-009)

## ADR Catalog

| ADR | Title | Enforcement | Status |
|-----|-------|-------------|--------|
| 001 | API-direct architecture | none | accepted |
| 002 | Template distribution via GitHub sync | agent | accepted |
| 003 | Assessment 3-gate model | agent | accepted |
| 004 | CalVer versioning (YYYY.0M.PATCH) | agent | accepted |
| 005 | Connector plugin system | agent | accepted |
| 006 | Python 3.14 minimum | hook | accepted |
| 007 | Zero type: ignore tolerance | blocking hook | accepted |
| 008 | Type annotation completeness | blocking hook + pyright | accepted |
| 009 | Behavioral test completeness | ratchet | accepted |
| 010 | Resource lifecycle in tests | soft hook | accepted |
| 011 | 3-tier enforcement model | governance doc | accepted |
| 012 | Dual type checking (mypy + pyright) | blocking hook + CI | accepted |
| 013 | Lean CI for solo developer | ci.yml | accepted |

Full ADR files: .primer/adr/
```

- [ ] **Step 3: Append governance decisions to decisions.md**

Read current decisions.md, then append:

```markdown
### 2026-05-07 -- Sprint retrospective governance upgrade

**Status:** accepted

**Context:** MVP Step 1 sprint revealed 23 issues across 6 categories. Most were
type safety failures, test quality gaps, and broken hook infrastructure.

**Decision:** 8 new ADRs (006-013) document the governance improvements. Plan 1
fixed the critical issues (broken hooks, Python 3.14, type enforcement). Plan 2
adds the ratchet baseline, lean CI, pre-commit hook, and formal ADR documents.

**Consequences:** The codebase now has 10 blocking pre-edit rules, a coverage ratchet,
pyright strict alongside mypy, and lean CI (<30s feedback). Pre-commit hook enforces
full test suite locally before every commit.
```

- [ ] **Step 4: Run full test suite and final checks**

```bash
cd /Users/pierre.grothe/Developer/nexus && poetry run pytest -q 2>&1 | tail -3 && poetry run ruff check src/nexus/ tests/ 2>&1 | tail -3 && poetry run mypy src/nexus/ 2>&1 | tail -3
```

Expected: 53 passed, 0 ruff violations, 0 mypy errors.

- [ ] **Step 5: Commit and push**

```bash
git add .primer/governance.md .primer/decisions.md
git commit -m "docs: update governance.md with 3-tier model and complete ADR catalog"
git push origin main
```
