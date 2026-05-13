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

from dataclasses import dataclass
from pathlib import Path

import pytest
from sync_readme import sync_readme

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
    # Override cli.py so stubs match README (setup + sync both stubbed)
    (root / "src" / "nexus" / "cli.py").write_text(
        '@app.command()\ndef setup() -> None:\n    print("not yet implemented")\n'
        '@app.command()\ndef sync() -> None:\n    print("not yet implemented")\n',
        encoding="utf-8",
    )
    result = sync_readme(root, pytest_runner=FakePytest(824))
    assert result.changed == []
    assert result.warnings == []


def test_sync_readme_warns_on_stub_mismatch(tmp_path: Path) -> None:
    # README lists setup+sync as stubs; cli.py only has setup as stub
    root = _make_project(tmp_path)
    result = sync_readme(root, pytest_runner=FakePytest(824))
    # cli.py has "setup" as stub; README has "setup" and "sync" -- mismatch
    assert any("stub mismatch" in w for w in result.warnings)


def test_sync_readme_warns_when_pytest_output_unparseable(tmp_path: Path) -> None:
    root = _make_project(tmp_path)
    # Override cli.py so stubs match README (setup + sync both stubbed)
    (root / "src" / "nexus" / "cli.py").write_text(
        '@app.command()\ndef setup() -> None:\n    print("not yet implemented")\n'
        '@app.command()\ndef sync() -> None:\n    print("not yet implemented")\n',
        encoding="utf-8",
    )
    # FakePytest returns garbage that can't be parsed
    result = sync_readme(root, pytest_runner=lambda _: "error: no output\n")
    assert any("test count could not be determined" in w for w in result.warnings)
    content = (root / "README.md").read_text(encoding="utf-8")
    assert "<!-- tests -->" not in content


def test_sync_readme_warns_when_test_count_is_zero(tmp_path: Path) -> None:
    root = _make_project(tmp_path)
    result = sync_readme(root, pytest_runner=FakePytest(0))
    assert any("test count is 0" in w for w in result.warnings)
    content = (root / "README.md").read_text(encoding="utf-8")
    assert "<!-- tests -->" not in content


def test_sync_readme_updates_gantt_when_roadmap_changes(tmp_path: Path) -> None:
    readme = _README_BASE.replace(
        "## What is implemented\n",
        "## Roadmap\n\n<!-- gantt -->\n```mermaid\ngantt\n    old content\n```\n<!-- /gantt -->\n\n## What is implemented\n",
    )
    root = _make_project(tmp_path, readme)
    primer_dir = root / ".primer"
    primer_dir.mkdir()
    (primer_dir / "roadmap.md").write_text(
        "# Roadmap\n\n## Foundation [done]\n- [x] Config layer\n\n## 2026.05 -- Setup [active]\n- [ ] nexus setup command\n",
        encoding="utf-8",
    )
    result = sync_readme(root, pytest_runner=FakePytest(100))
    assert "gantt" in result.changed
    content = (root / "README.md").read_text(encoding="utf-8")
    assert "old content" not in content
    assert "section Foundation" in content
    assert "section Setup" in content
    assert ":done," in content
    assert ":active," in content


def test_sync_readme_gantt_no_change_when_roadmap_absent(tmp_path: Path) -> None:
    readme = _README_BASE.replace(
        "## What is implemented\n",
        "## Roadmap\n\n<!-- gantt -->\n```mermaid\ngantt\n    handcrafted\n```\n<!-- /gantt -->\n\n## What is implemented\n",
    )
    root = _make_project(tmp_path, readme)
    # No .primer/roadmap.md -- Gantt must be left unchanged
    result = sync_readme(root, pytest_runner=FakePytest(100))
    assert "gantt" not in result.changed
    content = (root / "README.md").read_text(encoding="utf-8")
    assert "handcrafted" in content


def test_sync_readme_exits_1_if_readme_missing(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(_PYPROJECT, encoding="utf-8")
    # README.md deliberately absent
    with pytest.raises(SystemExit) as exc:
        sync_readme(tmp_path, pytest_runner=FakePytest(0))
    assert exc.value.code == 1
