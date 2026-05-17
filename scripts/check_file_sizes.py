# scripts/check_file_sizes.py
# Enforce ADR-023 file-size limits with a ratchet for grandfathered files.
# Author: Pierre Grothe
# Date: 2026-05-16
"""Check that Python files stay within the size limits set by ADR-023.

Limits:
    src/nexus/ -- 800 lines
    tests/    -- 1000 lines

Files already over the limit when this script was first introduced are
listed in ``.file-size-baseline.json`` at their current size. The ratchet
allows those files to shrink (or stay equal) but never to grow.

Exit codes:
    0 -- all checks pass
    1 -- one or more violations
    2 -- baseline file is malformed
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import cast

__all__ = ["main"]

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src" / "nexus"
TESTS_ROOT = REPO_ROOT / "tests"
BASELINE_PATH = REPO_ROOT / ".file-size-baseline.json"

SRC_LIMIT = 800
TEST_LIMIT = 1000


def _load_baseline() -> dict[str, int]:
    """Read the baseline file or return empty when missing.

    Returns:
        Mapping of ``<repo-relative path>`` to the maximum permitted line
        count for that file. Files absent from the mapping fall back to
        the category default (``SRC_LIMIT`` / ``TEST_LIMIT``).

    Raises:
        ValueError: When the baseline file is present but malformed.
    """
    if not BASELINE_PATH.exists():
        return {}
    raw = cast("dict[str, object]", json.loads(BASELINE_PATH.read_text(encoding="utf-8")))
    files_obj = raw.get("files")
    if not isinstance(files_obj, dict):
        msg = f"{BASELINE_PATH} 'files' key missing or not a mapping"
        raise ValueError(msg)
    out: dict[str, int] = {}
    for key, value in cast("dict[object, object]", files_obj).items():
        if not isinstance(key, str) or not isinstance(value, int):
            msg = f"{BASELINE_PATH} entry {key!r}: expected str -> int"
            raise ValueError(msg)
        out[key] = value
    return out


def _count_lines(path: Path) -> int:
    """Return the line count of ``path``."""
    with path.open("rb") as fh:
        return sum(1 for _ in fh)


def _python_files(root: Path) -> list[Path]:
    """Yield every ``*.py`` file under ``root`` excluding caches."""
    out: list[Path] = []
    for path in root.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        out.append(path)
    return out


def _check(root: Path, limit: int, baseline: dict[str, int]) -> list[str]:
    """Return human-readable violation strings for files under ``root``."""
    violations: list[str] = []
    for path in _python_files(root):
        rel = path.relative_to(REPO_ROOT).as_posix()
        lines = _count_lines(path)
        baselined = baseline.get(rel)
        if baselined is not None:
            if lines > baselined:
                violations.append(
                    f"{rel}: {lines} lines (baseline {baselined}, must not grow -- ADR-023)"
                )
            continue
        if lines > limit:
            violations.append(
                f"{rel}: {lines} lines exceeds limit of {limit} (ADR-023). "
                f"Either split the module or add an entry to .file-size-baseline.json "
                f"with justification."
            )
    return violations


def main() -> int:
    """Entry point; prints violations and returns a process exit code."""
    try:
        baseline = _load_baseline()
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"baseline error: {exc}", file=sys.stderr)
        return 2

    violations = _check(SRC_ROOT, SRC_LIMIT, baseline) + _check(TESTS_ROOT, TEST_LIMIT, baseline)
    if not violations:
        return 0
    print("File-size violations (ADR-023):", file=sys.stderr)
    for v in violations:
        print(f"  {v}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
