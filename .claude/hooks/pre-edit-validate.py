#!/usr/bin/env python3
# .claude/hooks/pre-edit-validate.py
# PreToolUse hook -- block known anti-patterns before Claude writes them to disk.
# Author: Pierre Grothe
# Date: 2026-05-07
"""Block prohibited patterns before any Python file is written.

Checks (all blocking):
  1. Mock imports (unittest.mock, MagicMock, pytest_mock imports, @patch)
     NOTE: pytest's monkeypatch fixture *parameter* is allowed. Only import-based
     mock libraries are blocked.
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

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
NEXUS_SRC = REPO_ROOT / "src" / "nexus"
TESTS = REPO_ROOT / "tests"

_MOCK_RE = re.compile(
    r"unittest\.mock|from\s+mock\s+import|import\s+mock\b"
    r"|import\s+pytest_mock|from\s+pytest_mock"
    r"|\bMagicMock\b|\bAsyncMock\b|@patch\b"
    # Note: pytest's monkeypatch fixture parameter is allowed -- only import-based
    # mock usage is blocked. The old \bmonkeypatch\b pattern was too broad.
)
_SYS_ARGV_RE = re.compile(r"sys\.argv\[")
_RELATIVE_IMPORT_RE = re.compile(r"^from\s+\.\.?\w", re.MULTILINE)
_BARE_EXCEPT_RE = re.compile(r"^\s*except\s*:", re.MULTILINE)
_LRU_CACHE_RE = re.compile(r"@lru_cache\s*\(\s*(?:maxsize\s*=\s*)?None\s*\)")
_UNITTEST_TESTCASE_RE = re.compile(r"class\s+\w+\s*\(.*TestCase.*\)")

_TYPE_IGNORE_RE = re.compile(r"#\s*type:\s*ignore")

# Matches function signatures containing ': Any' as a parameter type or '-> Any' as return.
# Uses a two-part alternation:
#   Part 1: parameter annotation -- ': Any' (word boundary, excludes AnyStr etc.)
#   Part 2: return annotation -- '-> Any' at end of def line (before ':' or newline)
# Both alternatives use \([^)]*\) to cross typed parameters that contain ':'.
_BARE_ANY_SIG_RE = re.compile(
    r"def\s+\w+\s*\([^)]*:\s*Any\b"  # parameter: Any
    r"|def\s+\w+\s*\([^)]*\)\s*->\s*Any\s*[:\n]",  # -> Any (return type)
    re.MULTILINE,
)

# Matches dict[str, Any] inside a function signature (param list or return type).
# Uses \([^)]*\) to correctly traverse typed param lists containing ':'.
_DICT_ANY_SIG_RE = re.compile(
    r"def\s+\w+\s*\([^)]*dict\[str,\s*Any\]"  # dict[str, Any] in params
    r"|def\s+\w+\s*\([^)]*\)\s*->\s*dict\[str,\s*Any\]",  # -> dict[str, Any] return
    re.MULTILINE,
)

# Matches import statements indented at least 4 spaces (inside def/class body).
# Lines under 'if TYPE_CHECKING:' are exempted by check_deferred_import().
_DEFERRED_IMPORT_RE = re.compile(
    r"^[ \t]{4,}(from\s+\S+\s+import\b|import\s+\S)",
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


def check_mocks(content: str, path: Path) -> str | None:
    """Block mock imports in any Python file."""
    if _MOCK_RE.search(content):
        return (
            f"BLOCKED: Mock usage in {path.name}. "
            "Use fakes in tests/fakes/ instead."
        )
    return None


def check_sys_argv(content: str, path: Path) -> str | None:
    """Block sys.argv indexing outside test files."""
    if is_test_file(path):
        return None
    if _SYS_ARGV_RE.search(content):
        return (
            f"BLOCKED: sys.argv indexing in {path.name}. "
            "Use Typer parameters instead."
        )
    return None


def check_relative_imports(content: str, path: Path) -> str | None:
    """Block relative imports -- absolute imports only."""
    if _RELATIVE_IMPORT_RE.search(content):
        return (
            f"BLOCKED: Relative import in {path.name}. "
            "Use absolute imports: 'from nexus.config.settings import NexusConfig'."
        )
    return None


def check_bare_except(content: str, path: Path) -> str | None:
    """Block bare except clauses."""
    if _BARE_EXCEPT_RE.search(content):
        return (
            f"BLOCKED: Bare 'except:' in {path.name}. "
            "Catch specific exceptions: 'except (ValueError, OSError):'."
        )
    return None


def check_lru_cache(content: str, path: Path) -> str | None:
    """Block @lru_cache(maxsize=None) -- use @cache."""
    if _LRU_CACHE_RE.search(content):
        return (
            f"BLOCKED: @lru_cache(maxsize=None) in {path.name}. "
            "Use @cache from functools instead."
        )
    return None


def check_unittest_testcase(content: str, path: Path) -> str | None:
    """Block unittest.TestCase in test files -- use plain pytest functions."""
    if not is_test_file(path):
        return None
    if _UNITTEST_TESTCASE_RE.search(content):
        return (
            f"BLOCKED: unittest.TestCase in {path.name}. "
            "Use plain pytest functions: def test_<function>_<scenario>()."
        )
    return None


def check_type_ignore(content: str, path: Path) -> str | None:
    """Block # type: ignore comments -- fix the actual type issue instead."""
    if _TYPE_IGNORE_RE.search(content):
        return (
            f"BLOCKED: '# type: ignore' in {path.name}. "
            "Fix the actual type error. For untyped third-party packages, "
            "add a stub file to src/stubs/."
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
            "Define a TypedDict or Protocol to express the dict structure."
        )
    return None


def _strip_type_checking_imports(content: str) -> str:
    """Remove lines that are imports nested under 'if TYPE_CHECKING:' blocks.

    These are required by the TYPE_CHECKING imports rule and must not be
    flagged as deferred imports.

    Args:
        content: Full file content.

    Returns:
        Content with TYPE_CHECKING-guarded import lines replaced by blank lines
        so line numbers are preserved and subsequent regex positions are stable.
    """
    lines = content.splitlines(keepends=True)
    result: list[str] = []
    in_type_checking = False
    for line in lines:
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        if re.match(r"if\s+TYPE_CHECKING\s*:", stripped):
            in_type_checking = True
            result.append(line)
            continue
        if in_type_checking:
            # Still inside the block if the line is blank or more indented than 0
            if stripped == "" or indent > 0:
                result.append("\n")  # blank out so _DEFERRED_IMPORT_RE skips it
                continue
            else:
                in_type_checking = False
        result.append(line)
    return "".join(result)


def check_deferred_import(content: str, path: Path) -> str | None:
    """Block import statements inside function or class bodies."""
    scrubbed = _strip_type_checking_imports(content)
    if _DEFERRED_IMPORT_RE.search(scrubbed):
        return (
            f"BLOCKED: Deferred import inside function or class body in {path.name}. "
            "Move all imports to module level."
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

    content = data.get("tool_input", {}).get("new_string") or data.get("tool_input", {}).get(
        "content"
    ) or ""
    if not content:
        return 0

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

    for check in checks:
        if violation := check(content, path):
            print(violation, file=sys.stderr)
            return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
