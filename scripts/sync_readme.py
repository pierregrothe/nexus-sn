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


def _parse_test_count(output: str) -> int | None:
    """Extract the test count from pytest --collect-only -q output.

    Args:
        output: Raw stdout from pytest --collect-only.

    Returns:
        Integer test count, or None if the output cannot be parsed
        (e.g., pytest failed or produced unexpected output).
    """
    for line in reversed(output.splitlines()):
        m = re.search(r"(\d+)\s+test", line)
        if m:
            return int(m.group(1))
    return None


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
    seen_bullet = False
    for line in readme.splitlines():
        if re.search(r"following commands are stubs", line, re.IGNORECASE):
            in_stubs = True
            seen_bullet = False
        elif in_stubs:
            m = re.match(r"- `nexus ([\w-]+)`", line)
            if m:
                stubs.add(m.group(1))
                seen_bullet = True
            elif not line.strip() and seen_bullet:
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

    if test_count is None:
        result.warnings.append(
            "test count could not be determined (pytest returned 0 or failed); "
            "skipping test_count update"
        )

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
    if test_count is not None:
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

    # -- Stub-mismatch warning (always checked, even when nothing changed) --
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
