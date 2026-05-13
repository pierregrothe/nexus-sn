# README Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `scripts/sync_readme.py` so that `/primer sync` auto-updates version, Python requirement, and test count in README.md, and warns when the stub-commands list diverges from cli.py.

**Architecture:** A standalone Python script with injectable dependencies reads pyproject.toml (tomllib), collects test count via a runner callable, and rewrites README in-place using line-match and HTML-comment anchors. The primer skill SKILL.md gets one new step that runs the script if present. All logic is unit-tested against tmp_path fixtures with a fake pytest runner.

**Tech Stack:** Python 3.14, stdlib only (tomllib, re, subprocess, dataclasses, pathlib). pytest + tmp_path for tests. No src/nexus imports.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `scripts/sync_readme.py` | Create | All sync logic: read sources, update README, warn on stub drift |
| `tests/test_sync_readme.py` | Create | 7 test functions covering all branches |
| `pyproject.toml` | Modify | Add `"scripts"` to `pythonpath` so tests can import the module |
| `README.md` | Modify | Fix `CalVer: YYYY.0M.PATCH` to actual version `2026.05.1` |
| `~/.claude/skills/primer/SKILL.md` | Modify | Append Step 8 to Sync section |

---

## Task 1: Fix README version placeholder and add scripts to pythonpath

**Files:**
- Modify: `README.md` (line 141-143)
- Modify: `pyproject.toml` (pythonpath line)

- [ ] **Step 1: Update README version line**

Open `README.md`. Find:
```
CalVer: YYYY.0M.PATCH
```
Replace with:
```
CalVer: 2026.05.1
```

- [ ] **Step 2: Add scripts/ to pytest pythonpath**

Open `pyproject.toml`. Find:
```toml
pythonpath = ["src"]
```
Replace with:
```toml
pythonpath = ["src", "scripts"]
```

- [ ] **Step 3: Verify pytest still collects**

```bash
pytest --collect-only -q 2>&1 | tail -3
```
Expected: same test count as before (824 tests collected).

- [ ] **Step 4: Commit**

```bash
git add README.md pyproject.toml
git commit -m "chore: fix README version placeholder + add scripts/ to pythonpath"
```

---

## Task 2: Write the test file (TDD -- tests first)

**Files:**
- Create: `tests/test_sync_readme.py`

The script does not exist yet; tests will fail with ImportError until Task 3.

- [ ] **Step 1: Create the test file**

Create `tests/test_sync_readme.py` with this full content:

```python
# tests/test_sync_readme.py
# Tests for scripts/sync_readme.py -- README field sync.
# Author: Pierre Grothe
# Date: 2026-05-13
"""Tests for the README sync script.

All tests use tmp_path fixtures with minimal README templates.
FakePytest is a @dataclass(slots=True) injectable runner that returns
canned stdout without spawning a real subprocess.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

import pytest

from sync_readme import SyncResult, sync_readme

__all__: list[str] = []

# ---------------------------------------------------------------------------
# Fake runner
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class FakePytest:
    """Injectable pytest runner returning canned collect output."""

    count: int

    def __call__(self, root: Path) -> str:
        """Return stdout mimicking pytest --collect-only -q output."""
        return f"{self.count} tests collected in 1.00s\n"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PYPROJECT = """\
[tool.poetry]
version = "2026.05.1"

[tool.poetry.dependencies]
python = ">=3.14,<3.15"
"""

_README_BASE = """\
# NEXUS

Some intro text.

## What is implemented

- `nexus status` -- works

The following commands are stubs (not yet implemented):

- `nexus setup` -- credential wizard
- `nexus sync` -- pull templates

## Requirements

- Python 3.14+
- ServiceNow instance

## Version

CalVer: 2026.05.1
"""


def _make_project(tmp_path: Path, readme: str = _README_BASE) -> Path:
    """Write pyproject.toml and README.md into tmp_path and return root."""
    (tmp_path / "pyproject.toml").write_text(_PYPROJECT, encoding="utf-8")
    (tmp_path / "README.md").write_text(readme, encoding="utf-8")
    cli_dir = tmp_path / "src" / "nexus"
    cli_dir.mkdir(parents=True)
    (cli_dir / "cli.py").write_text(
        '@app.command()\ndef setup() -> None:\n    print("not yet implemented")\n',
        encoding="utf-8",
    )
    return tmp_path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_sync_readme_updates_version(tmp_path: Path) -> None:
    readme = _README_BASE.replace("CalVer: 2026.05.1", "CalVer: 2026.04.0")
    root = _make_project(tmp_path, readme)
    result = sync_readme(root, pytest_runner=FakePytest(100))
    assert "version" in result.changed
    content = (root / "README.md").read_text(encoding="utf-8")
    assert "CalVer: 2026.05.1" in content
    assert "CalVer: 2026.04.0" not in content


def test_sync_readme_updates_python_req(tmp_path: Path) -> None:
    readme = _README_BASE.replace("Python 3.14+", "Python 3.12+")
    root = _make_project(tmp_path, readme)
    result = sync_readme(root, pytest_runner=FakePytest(100))
    assert "python_req" in result.changed
    content = (root / "README.md").read_text(encoding="utf-8")
    assert "- Python 3.14+" in content
    assert "- Python 3.12+" not in content


def test_sync_readme_inserts_test_count_first_run(tmp_path: Path) -> None:
    root = _make_project(tmp_path)
    result = sync_readme(root, pytest_runner=FakePytest(824))
    assert "test_count" in result.changed
    content = (root / "README.md").read_text(encoding="utf-8")
    assert "<!-- tests -->824 tests passing" in content
    assert "<!-- /tests -->" in content


def test_sync_readme_updates_test_count_subsequent_run(tmp_path: Path) -> None:
    readme = _README_BASE.replace(
        "## What is implemented\n",
        "## What is implemented\n\n<!-- tests -->500 tests passing, all real fakes, no mocks.<!-- /tests -->\n",
    )
    root = _make_project(tmp_path, readme)
    result = sync_readme(root, pytest_runner=FakePytest(824))
    assert "test_count" in result.changed
    content = (root / "README.md").read_text(encoding="utf-8")
    assert "<!-- tests -->824 tests passing" in content
    assert "500 tests" not in content


def test_sync_readme_no_change_when_already_current(tmp_path: Path) -> None:
    readme = _README_BASE.replace(
        "## What is implemented\n",
        "## What is implemented\n\n<!-- tests -->824 tests passing, all real fakes, no mocks.<!-- /tests -->\n",
    )
    root = _make_project(tmp_path, readme)
    result = sync_readme(root, pytest_runner=FakePytest(824))
    assert result.changed == []
    assert result.warnings == []


def test_sync_readme_warns_on_stub_mismatch(tmp_path: Path) -> None:
    # README lists setup+sync as stubs; cli.py only has setup as stub
    root = _make_project(tmp_path)
    result = sync_readme(root, pytest_runner=FakePytest(824))
    # cli.py has "setup" as stub; README has "setup" and "sync" -- mismatch
    assert any("stub mismatch" in w for w in result.warnings)


def test_sync_readme_exits_1_if_readme_missing(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(_PYPROJECT, encoding="utf-8")
    # README.md deliberately absent
    with pytest.raises(SystemExit) as exc:
        sync_readme(tmp_path, pytest_runner=FakePytest(0))
    assert exc.value.code == 1
```

- [ ] **Step 2: Run tests to confirm ImportError (expected failure)**

```bash
pytest tests/test_sync_readme.py -v 2>&1 | head -20
```
Expected: `ModuleNotFoundError: No module named 'sync_readme'`

---

## Task 3: Write scripts/sync_readme.py

**Files:**
- Create: `scripts/sync_readme.py`

- [ ] **Step 1: Create the scripts directory and the script**

```bash
mkdir -p scripts
```

Create `scripts/sync_readme.py` with this full content:

```python
# scripts/sync_readme.py
# Sync version, Python requirement, and test count into README.md.
# Author: Pierre Grothe
# Date: 2026-05-13
"""Sync live project data into README.md fields.

Run directly: python scripts/sync_readme.py
Called by /primer sync as Step 8.

Reads:
  - pyproject.toml: version, python requirement
  - pytest --collect-only -q: test count
  - src/nexus/cli.py: stub command names

Writes README.md in-place. Prints a summary of changed fields.

Exit codes:
  0 -- success (including stub-mismatch warnings)
  1 -- README.md or pyproject.toml not found
"""

from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

__all__: list[str] = []

REPO_ROOT = Path(__file__).parent.parent

_APP_CMD_RE = re.compile(r"@\w+(?:\.\w+)*\.command\(")
_DEF_RE = re.compile(r"^\s*def (\w+)\(")
_STUB_BODY_RE = re.compile(r"not yet implemented", re.IGNORECASE)
_ANCHOR_RE = re.compile(r"<!-- tests -->.*?<!-- /tests -->")


@dataclass(slots=True)
class SyncResult:
    """Result of a README sync run.

    Attributes:
        changed: Names of fields that were updated in README.
        warnings: Human-readable warning messages (non-fatal).
    """

    changed: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _read_project_data(root: Path) -> tuple[str, str]:
    """Read version and Python requirement from pyproject.toml.

    Args:
        root: Project root directory.

    Returns:
        Tuple of (version, python_req) e.g. ("2026.05.1", "3.14+").

    Raises:
        SystemExit: If pyproject.toml is not found.
    """
    toml_path = root / "pyproject.toml"
    if not toml_path.exists():
        print(f"ERROR: {toml_path} not found", file=sys.stderr)
        sys.exit(1)
    with toml_path.open("rb") as fh:
        data = tomllib.load(fh)
    version: str = data["tool"]["poetry"]["version"]
    raw: str = data["tool"]["poetry"]["dependencies"]["python"]
    # ">=3.14,<3.15" -> first constraint -> strip non-digits -> "3.14+"
    first = raw.split(",")[0]
    python_req = re.sub(r"^[^0-9]*", "", first) + "+"
    return version, python_req


def _subprocess_runner(root: Path) -> str:
    """Run pytest --collect-only -q and return stdout.

    Args:
        root: Project root (cwd for subprocess).

    Returns:
        Raw stdout from pytest.
    """
    result = subprocess.run(
        ["pytest", "--collect-only", "-q"],
        capture_output=True,
        text=True,
        cwd=root,
    )
    return result.stdout


def _parse_test_count(output: str) -> int:
    """Extract the test count from pytest --collect-only -q output.

    Args:
        output: Raw stdout from pytest --collect-only.

    Returns:
        Integer test count, or 0 if the line cannot be parsed.
    """
    for line in reversed(output.splitlines()):
        m = re.search(r"(\d+)\s+test", line)
        if m:
            return int(m.group(1))
    return 0


def _find_cli_stubs(root: Path) -> set[str]:
    """Return command names whose bodies contain 'not yet implemented'.

    Scans src/nexus/cli.py for @app.command() decorated functions
    that print a 'not yet implemented' message within 20 lines of
    the def statement.

    Args:
        root: Project root directory.

    Returns:
        Set of function-name strings matching stub commands.
    """
    cli_path = root / "src" / "nexus" / "cli.py"
    if not cli_path.exists():
        return set()
    lines = cli_path.read_text(encoding="utf-8").splitlines()
    stubs: set[str] = set()
    pending_name: str | None = None
    decorator_line: int = -1
    for i, line in enumerate(lines):
        if _APP_CMD_RE.search(line):
            pending_name = None
            decorator_line = i
        elif decorator_line >= 0 and pending_name is None:
            m = _DEF_RE.match(line)
            if m:
                pending_name = m.group(1)
        elif pending_name and (i - decorator_line) <= 20:
            if _STUB_BODY_RE.search(line):
                stubs.add(pending_name)
                pending_name = None
                decorator_line = -1
        elif decorator_line >= 0 and (i - decorator_line) > 20:
            pending_name = None
            decorator_line = -1
    return stubs


def _find_readme_stubs(readme: str) -> set[str]:
    """Return command names from the stubs bullet list in README.

    Looks for a paragraph starting with 'The following commands are stubs'
    and collects `nexus <name>` entries until a blank line.

    Args:
        readme: Full README.md text.

    Returns:
        Set of command name strings.
    """
    stubs: set[str] = set()
    in_stubs = False
    for line in readme.splitlines():
        if re.search(r"following commands are stubs", line, re.IGNORECASE):
            in_stubs = True
        elif in_stubs:
            m = re.match(r"- `nexus ([\w-]+)`", line)
            if m:
                stubs.add(m.group(1))
            elif not line.strip():
                in_stubs = False
    return stubs


def sync_readme(
    root: Path,
    *,
    pytest_runner: Callable[[Path], str] | None = None,
) -> SyncResult:
    """Sync live project data into README.md.

    Updates three fields in-place:
      - CalVer version line (line-match anchor)
      - Python requirement line (line-match anchor)
      - Test count (HTML comment anchor, inserted on first run)

    Warns if stub commands in cli.py diverge from the README stubs list.

    Args:
        root: Project root directory containing README.md and pyproject.toml.
        pytest_runner: Callable(root) -> stdout string. Defaults to running
            pytest --collect-only -q as a subprocess.

    Returns:
        SyncResult listing changed fields and any warnings.

    Raises:
        SystemExit: If README.md or pyproject.toml is not found.
    """
    runner = pytest_runner if pytest_runner is not None else _subprocess_runner
    readme_path = root / "README.md"
    if not readme_path.exists():
        print(f"ERROR: {readme_path} not found", file=sys.stderr)
        sys.exit(1)

    version, python_req = _read_project_data(root)
    test_count = _parse_test_count(runner(root))
    result = SyncResult()
    text = readme_path.read_text(encoding="utf-8")
    updated = text

    # -- Version (line-match anchor) --
    version_line = f"CalVer: {version}"
    m = re.search(r"^CalVer:.*$", updated, re.MULTILINE)
    if m and m.group() != version_line:
        updated = updated[: m.start()] + version_line + updated[m.end() :]
        result.changed.append("version")

    # -- Python requirement (line-match anchor) --
    python_line = f"- Python {python_req}"
    m = re.search(r"^- Python .*$", updated, re.MULTILINE)
    if m and m.group() != python_line:
        updated = updated[: m.start()] + python_line + updated[m.end() :]
        result.changed.append("python_req")

    # -- Test count (HTML comment anchor) --
    tests_text = (
        f"<!-- tests -->{test_count} tests passing, "
        f"all real fakes, no mocks.<!-- /tests -->"
    )
    existing = _ANCHOR_RE.search(updated)
    if existing:
        if existing.group() != tests_text:
            updated = _ANCHOR_RE.sub(tests_text, updated)
            result.changed.append("test_count")
    else:
        heading = "## What is implemented"
        if heading in updated:
            updated = updated.replace(heading, f"{heading}\n\n{tests_text}", 1)
            result.changed.append("test_count")

    # -- Stub-mismatch warning --
    cli_stubs = _find_cli_stubs(root)
    readme_stubs = _find_readme_stubs(updated)
    if cli_stubs and cli_stubs != readme_stubs:
        cli_names = ", ".join(sorted(cli_stubs))
        readme_names = ", ".join(sorted(readme_stubs))
        result.warnings.append(
            f"stub mismatch -- cli.py: {cli_names} | README: {readme_names}\n"
            "      Update the 'stubs' bullet list in README manually."
        )

    if result.changed:
        readme_path.write_text(updated, encoding="utf-8")

    return result


def main() -> int:
    """Entry point for direct script invocation.

    Returns:
        0 on success (including warnings), 1 on fatal error.
    """
    result = sync_readme(REPO_ROOT)
    if result.changed:
        print(f"README updated: {', '.join(result.changed)}")
    else:
        print("README already up to date.")
    for warning in result.warnings:
        print(f"WARN: {warning}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run the targeted tests**

```bash
pytest tests/test_sync_readme.py -v 2>&1 | tail -20
```
Expected: 7 passed.

- [ ] **Step 3: Run the script directly against the real repo to verify**

```bash
python scripts/sync_readme.py
```
Expected output (something like):
```
README already up to date.
WARN: stub mismatch -- cli.py: setup | README: setup, sync
      Update the 'stubs' bullet list in README manually.
```

---

## Task 4: Run the full test suite and fix the coverage ratchet

**Files:**
- Modify: `.ratchet.json` (if needed by post-edit hook after test run)

- [ ] **Step 1: Run the full suite**

```bash
pytest -q 2>&1 | tail -5
```
Expected: all tests pass. If coverage ratchet fails, the post-edit hook will report which modules regressed. Fix any regressions before proceeding.

- [ ] **Step 2: Commit script + tests**

```bash
git add scripts/sync_readme.py tests/test_sync_readme.py pyproject.toml
git commit -m "feat(scripts): sync_readme.py -- auto-update README on /primer sync"
```

---

## Task 5: Update the primer skill SKILL.md

**Files:**
- Modify: `~/.claude/skills/primer/SKILL.md`

- [ ] **Step 1: Open the file and locate the Sync section**

Read `~/.claude/skills/primer/SKILL.md`. Find the line:

```
### Finish

Show a brief diff summary of what changed.
```

This is the last item in the `## Sync` section.

- [ ] **Step 2: Insert Step 8 before the Finish subsection**

Replace:
```markdown
### Finish

Show a brief diff summary of what changed.
```

With:
```markdown
### Step 8: Project README sync (if applicable)

If `scripts/sync_readme.py` exists at the project root, run it:

```bash
python scripts/sync_readme.py
```

Report what fields changed, or "README already up to date." if nothing changed.
This step is a no-op on projects that do not have the script.

### Finish

Show a brief diff summary of what changed.
```

- [ ] **Step 3: Commit the primer skill change (dotfiles repo)**

```bash
cd ~/.claude/skills/primer  # or the dotfiles path if symlinked
git add SKILL.md
git commit -m "feat(primer): add Step 8 -- project README sync on /primer sync"
git push
```

The dotfiles repo is at `/Users/pierre.grothe/Developer/claude-dotfiles`.
Adjust the path accordingly:

```bash
cd /Users/pierre.grothe/Developer/claude-dotfiles
git add .claude/skills/primer/SKILL.md
git commit -m "feat(primer): add Step 8 -- project README sync on /primer sync"
git push
```

---

## Task 6: Smoke-test /primer sync end-to-end and push

**Files:**
- No new files.

- [ ] **Step 1: Verify the script is idempotent**

```bash
python scripts/sync_readme.py && python scripts/sync_readme.py
```
Expected: second run prints "README already up to date." with no changes.

- [ ] **Step 2: Push the NEXUS branch and open a PR**

```bash
git push
gh pr create \
  --title "feat(scripts): sync_readme.py -- auto-update README on /primer sync" \
  --body "Adds scripts/sync_readme.py. Run python scripts/sync_readme.py (or /primer sync) to keep version, Python req, and test count in README current. 7 tests, 0 new dependencies."
```
