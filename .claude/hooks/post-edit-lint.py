#!/usr/bin/env python3
# .claude/hooks/post-edit-lint.py
# PostToolUse hook -- run ruff + mypy after Claude edits a Python file.
# Author: Pierre Grothe
# Date: 2026-05-07
"""Run ruff and mypy immediately after a Python file is written.

Exit codes:
  0 -- no issues (or non-Python file)
  2 -- lint/type issues found (Claude receives stdout as feedback)
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

    if issues:
        print("\n".join(issues))
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
