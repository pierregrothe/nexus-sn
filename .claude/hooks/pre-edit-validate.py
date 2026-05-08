#!/usr/bin/env python3
# .claude/hooks/pre-edit-validate.py
# PreToolUse hook -- block known anti-patterns before Claude writes them to disk.
# Author: Pierre Grothe
# Date: 2026-05-07
"""Block prohibited patterns before any Python file is written.

Rules in this hook are file-aware (sys-argv, dict-any-in-sig need test-vs-source
distinction or signature-only matching that ruff/semgrep can't express cleanly).

Other governance rules live in:
  - pyproject.toml [tool.ruff.lint]: no-mocks, no-relative-imports, no-bare-except,
    no-deferred-import (PLC0415), no-type-ignore (PGH003)
  - .semgrep/rules.yml: no-lru-cache-none, no-unittest-testcase

Checks remaining here (all blocking):
  1. sys.argv indexing in non-test files
  2. Bare Any in function signatures
  3. dict[str, Any] in function signatures

Exit codes:
  0 -- content is clean (or non-Python file)
  2 -- prohibited pattern detected
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
NEXUS_SRC = REPO_ROOT / "src" / "nexus"
TESTS = REPO_ROOT / "tests"

_SYS_ARGV_RE = re.compile(r"sys\.argv\[")

# Matches function signatures containing ': Any' as a parameter type or '-> Any' as return.
# Two-part alternation:
#   Part 1: parameter annotation -- ': Any' (word boundary, excludes AnyStr etc.)
#   Part 2: return annotation -- '-> Any' at end of def line (before ':' or newline)
# Both alternatives use \([^)]*\) to cross typed parameters that contain ':'.
_BARE_ANY_SIG_RE = re.compile(
    r"def\s+\w+\s*\([^)]*:\s*Any\b"  # parameter: Any
    r"|def\s+\w+\s*\([^)]*\)\s*->\s*Any\s*[:\n]",  # -> Any (return type)
    re.MULTILINE,
)

# Matches dict[str, Any] inside a function signature (param list or return type).
# \([^)]*\) traverses typed param lists containing ':'.
_DICT_ANY_SIG_RE = re.compile(
    r"def\s+\w+\s*\([^)]*dict\[str,\s*Any\]"  # dict[str, Any] in params
    r"|def\s+\w+\s*\([^)]*\)\s*->\s*dict\[str,\s*Any\]",  # -> dict[str, Any] return
    re.MULTILINE,
)


def is_project_python(path: Path) -> bool:
    """Return True if path is a tracked Python file under nexus/ or tests/."""
    if path.suffix != ".py":
        return False
    for root in (NEXUS_SRC, TESTS):
        try:
            path.relative_to(root)
            return True
        except ValueError:
            pass
    return False


def is_test_file(path: Path) -> bool:
    """Return True if path is under tests/."""
    try:
        path.relative_to(TESTS)
        return True
    except ValueError:
        return False


def check_sys_argv(content: str, path: Path) -> str | None:
    """Block sys.argv indexing outside test files."""
    if is_test_file(path):
        return None
    if _SYS_ARGV_RE.search(content):
        return f"BLOCKED: sys.argv indexing in {path.name}. Use Typer parameters instead."
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
            "Define a TypedDict or Protocol to express the dict structure."
        )
    return None


def main() -> int:
    """Validate content and block anti-patterns.

    Returns:
        0 if clean, 2 if a prohibited pattern is detected.
    """
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        return 0

    file_path_str = data.get("tool_input", {}).get("file_path")
    if not file_path_str:
        return 0

    path = Path(file_path_str)
    if not is_project_python(path):
        return 0

    content = (
        data.get("tool_input", {}).get("new_string")
        or data.get("tool_input", {}).get("content")
        or ""
    )
    if not content:
        return 0

    checks = [
        check_sys_argv,
        check_bare_any_in_sig,
        check_dict_any_in_sig,
    ]

    for check in checks:
        if violation := check(content, path):
            print(violation, file=sys.stderr)
            return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
