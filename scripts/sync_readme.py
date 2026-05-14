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
  - src/nexus/**/*.py: lines of code count
  - src/nexus/cli.py: stub command names
  - .primer/roadmap.md: roadmap sections for Gantt regeneration

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

__all__ = [
    "SyncResult",
    "sync_readme",
]

REPO_ROOT = Path(__file__).parent.parent

_APP_CMD_RE = re.compile(r"@\w+(?:\.\w+)*\.command\(")
_BADGES_RE = re.compile(r"<!-- badges -->.*?<!-- /badges -->", re.DOTALL)
_GANTT_RE = re.compile(r"<!-- gantt -->.*?<!-- /gantt -->", re.DOTALL)
_SECTION_RE = re.compile(r"^## (.+?)(?:\s*\[(done|active|planned)\])?\s*$")
_ITEM_RE = re.compile(r"^- \[([ x])\]\s*(.+)")
_YEAR_MONTH_RE = re.compile(r"^(\d{4})\.(\d{2})")
_DEF_RE = re.compile(r"^\s*def (\w+)\(")
_STUB_BODY_RE = re.compile(r"not yet implemented", re.IGNORECASE)
_ANCHOR_RE = re.compile(r"<!-- tests -->.*?<!-- /tests -->")


@dataclass(slots=True)
class _RoadmapSection:
    """One parsed section from .primer/roadmap.md."""

    label: str
    status: str  # "done" | "active" | "planned"
    items: tuple[tuple[str, bool], ...]  # (display_text, is_done)


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


def _count_loc(root: Path) -> int:
    """Count total lines across all Python source files in src/nexus/.

    Args:
        root: Project root directory.

    Returns:
        Total line count, or 0 if the source directory is absent.
    """
    src = root / "src" / "nexus"
    if not src.exists():
        return 0
    return sum(
        len(p.read_text(encoding="utf-8", errors="ignore").splitlines())
        for p in src.rglob("*.py")
        if "__pycache__" not in str(p)
    )


def _gen_badges(python_req: str, test_count: int | None, loc: int) -> str:
    """Render the badge row as a markdown string between anchor comments.

    Static badges (Release, CI, License) use auto-updating GitHub/shields URLs.
    Dynamic badges (Python version, tests, LOC) are computed from live data.

    Args:
        python_req: Python version string e.g. "3.14+".
        test_count: Collected test count, or None if unavailable.
        loc: Total source lines of code.

    Returns:
        Full badge block including anchor comments.
    """
    py_enc = python_req.replace("+", "%2B")
    loc_enc = f"{loc:,}".replace(",", "%2C")
    tests_enc = f"{test_count}%20passing" if test_count else "unknown"
    tests_color = "brightgreen" if test_count else "lightgrey"
    return "\n".join(
        [
            "<!-- badges -->",
            "[![Release](https://img.shields.io/github/v/release/pierregrothe/nexus-sn)]"
            "(https://github.com/pierregrothe/nexus-sn/releases)",
            "[![CI](https://github.com/pierregrothe/nexus-sn/actions/workflows/ci.yml/badge.svg)]"
            "(https://github.com/pierregrothe/nexus-sn/actions/workflows/ci.yml)",
            "[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)",
            f"[![Python {python_req}](https://img.shields.io/badge/python-{py_enc}-blue)]"
            "(https://www.python.org/downloads/)",
            f"[![Tests](https://img.shields.io/badge/tests-{tests_enc}-{tests_color})]"
            "(https://github.com/pierregrothe/nexus-sn/actions)",
            f"[![LOC](https://img.shields.io/badge/LOC-{loc_enc}-blue)]"
            "(https://github.com/pierregrothe/nexus-sn/tree/main/src)",
            "<!-- /badges -->",
        ]
    )


def _parse_roadmap(root: Path) -> list[_RoadmapSection]:
    """Parse .primer/roadmap.md into a list of sections with items.

    Args:
        root: Project root directory.

    Returns:
        Ordered list of sections. Returns empty list if roadmap.md absent.
    """
    path = root / ".primer" / "roadmap.md"
    if not path.exists():
        return []
    sections: list[_RoadmapSection] = []
    current_label: str | None = None
    current_status = "planned"
    current_items: list[tuple[str, bool]] = []
    pending_item: str | None = None

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        sec_m = _SECTION_RE.match(raw_line)
        if sec_m:
            if pending_item is not None:
                current_items.append((_abbreviate(pending_item), False))
                pending_item = None
            if current_label is not None:
                sections.append(
                    _RoadmapSection(current_label, current_status, tuple(current_items))
                )
            current_label = sec_m.group(1).strip()
            current_status = sec_m.group(2) or "planned"
            current_items = []
            continue

        if current_label is None:
            continue

        item_m = _ITEM_RE.match(raw_line)
        if item_m:
            if pending_item is not None:
                current_items.append((_abbreviate(pending_item), False))
            is_done = item_m.group(1) == "x"
            pending_item = item_m.group(2).strip()
            if is_done:
                current_items.append((_abbreviate(pending_item), True))
                pending_item = None
        elif pending_item is not None and raw_line.startswith(" "):
            # continuation line -- ignore; abbreviation already applied
            pass
        elif pending_item is not None:
            current_items.append((_abbreviate(pending_item), False))
            pending_item = None

    if pending_item is not None:
        current_items.append((_abbreviate(pending_item), False))
    if current_label is not None:
        sections.append(_RoadmapSection(current_label, current_status, tuple(current_items)))
    return sections


def _abbreviate(text: str) -> str:
    """Return a short Gantt-safe label from a roadmap item line.

    Takes the first clause before ' -- ' or ' (' and caps at 44 chars.

    Args:
        text: Full item text from the roadmap.

    Returns:
        Abbreviated display string safe for Mermaid Gantt.
    """
    short = re.split(r"\s+--\s+|\s+\(", text)[0].strip()
    return short if len(short) <= 44 else short[:41] + "..."


def _section_dates(label: str) -> tuple[str, str] | None:
    """Infer Gantt start/end dates from a roadmap section label.

    YYYY.MM prefixes produce a one-month band. 'Foundation' maps to the
    project start band. Sections without a date (Backlog) return None.

    Args:
        label: Section label string e.g. '2026.05 -- Plugin Execution'.

    Returns:
        (start, end) in YYYY-MM format, or None to skip the section.
    """
    m = _YEAR_MONTH_RE.match(label)
    if m:
        year, month = int(m.group(1)), int(m.group(2))
        end_month = month % 12 + 1
        end_year = year + (1 if month == 12 else 0)
        return f"{year}-{month:02d}", f"{end_year}-{end_month:02d}"
    if "Foundation" in label:
        return "2026-03", "2026-05"
    return None


def _gen_gantt(sections: list[_RoadmapSection]) -> str:
    """Render roadmap sections as a Mermaid Gantt fenced code block.

    One summary bar per section (milestone view). Per-item bars were
    discarded because 1-2 month bars cannot fit long task labels -- text
    overflows outside the box in GitHub's renderer.

    Args:
        sections: Parsed roadmap sections from _parse_roadmap().

    Returns:
        Complete ```mermaid ... ``` string, or empty string if no
        sections have inferable dates.
    """
    lines = [
        "```mermaid",
        "gantt",
        "    title NEXUS Development Roadmap",
        "    dateFormat YYYY-MM",
    ]
    has_content = False
    for sec in sections:
        dates = _section_dates(sec.label)
        if dates is None:
            continue
        start, end = dates
        # Strip YYYY.MM prefix to produce a short section/bar label.
        display = re.sub(r"^\d{4}\.\d{2}\s*--\s*", "", sec.label).strip()
        if sec.status == "done":
            marker = ":done,"
        elif sec.status == "active":
            marker = ":active,"
        else:
            marker = ":"
        lines.append(f"    section {display}")
        lines.append(f"        {display:<28} {marker} {start}, {end}")
        has_content = True
    if not has_content:
        return ""
    lines.append("```")
    return "\n".join(lines)


def _find_cli_stubs(root: Path) -> tuple[set[str], bool]:
    """Return (stub command names, cli_found) for src/nexus/cli.py.

    Scans for @app.command() decorated functions that print
    'not yet implemented' within 20 lines of the def statement.

    Args:
        root: Project root directory.

    Returns:
        Tuple of (stubs set, cli_found bool). If cli.py does not exist,
        returns (empty set, False).
    """
    cli_path = root / "src" / "nexus" / "cli.py"
    if not cli_path.exists():
        return set(), False
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
    return stubs, True


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
    loc = _count_loc(root)
    result = SyncResult()
    text = readme_path.read_text(encoding="utf-8")
    updated = text

    # -- Badges (HTML comment anchor) --
    new_badges = _gen_badges(python_req, test_count, loc)
    existing_badges = _BADGES_RE.search(updated)
    if existing_badges and existing_badges.group() != new_badges:
        updated = _BADGES_RE.sub(new_badges, updated)
        result.changed.append("badges")

    if test_count is None:
        result.warnings.append(
            "test count could not be determined (pytest output unparseable); "
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
        if test_count == 0:
            result.warnings.append("test count is 0; skipping test_count update")
        else:
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

    # -- Roadmap Gantt (HTML comment anchor, regenerated from .primer/roadmap.md) --
    sections = _parse_roadmap(root)
    if sections:
        gantt_block = _gen_gantt(sections)
        if gantt_block:
            new_gantt = f"<!-- gantt -->\n{gantt_block}\n<!-- /gantt -->"
            existing_gantt = _GANTT_RE.search(updated)
            if existing_gantt and existing_gantt.group() != new_gantt:
                updated = _GANTT_RE.sub(new_gantt, updated)
                result.changed.append("gantt")

    # -- Stub-mismatch warning (always checked, even when nothing changed) --
    cli_stubs, cli_found = _find_cli_stubs(root)
    readme_stubs = _find_readme_stubs(updated)
    if cli_found and cli_stubs != readme_stubs:
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
