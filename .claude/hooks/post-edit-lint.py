#!/usr/bin/env python3
# .claude/hooks/post-edit-lint.py
# PostToolUse hook -- run black, ruff, mypy, pyright, and coverage ratchet after edits.
# Author: Pierre Grothe
# Date: 2026-05-07
"""Run black, ruff, mypy, pyright, and per-module coverage ratchet after a Python file is written.

Exit codes:
  0 -- no issues (or non-Python file)
  2 -- lint/format/type/coverage issues found (output on stderr so Claude Code displays it)
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
NEXUS_SRC = REPO_ROOT / "src" / "nexus"
TESTS = REPO_ROOT / "tests"
_VENV_BIN_NAME = "Scripts" if sys.platform == "win32" else "bin"
_EXE_SUFFIX = ".exe" if sys.platform == "win32" else ""
VENV_BIN = REPO_ROOT / ".venv" / _VENV_BIN_NAME


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


def run_tool(cmd: list[str]) -> tuple[int, str]:
    """Invoke a venv-installed tool by name and return (returncode, output).

    Resolves cmd[0] against .venv/<bin|Scripts>/ to bypass Poetry's per-call
    overhead. Fails loudly when the venv exists but the tool does not -- a
    silent PATH fallback would let a misconfigured environment use a system
    tool with different config or version. Falls back to PATH only when no
    venv exists at all (fresh clone before poetry install).
    """
    if VENV_BIN.is_dir():
        tool = VENV_BIN / f"{cmd[0]}{_EXE_SUFFIX}"
        if not tool.exists():
            return 2, f"venv tool '{cmd[0]}' not found at {tool} -- run 'poetry install'"
        full_cmd = [str(tool), *cmd[1:]]
    else:
        full_cmd = cmd
    result = subprocess.run(full_cmd, capture_output=True, text=True, cwd=REPO_ROOT)
    return result.returncode, (result.stdout + result.stderr).strip()


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
    return "nexus." + ".".join(parts) if parts else None


def check_coverage_ratchet(path: Path) -> str | None:
    """Run coverage and block if covered lines for the edited module decreased.

    Args:
        path: Path to the edited source file.

    Returns:
        Error string if coverage decreased, None if clean or not applicable.
    """
    module = _module_name(path)
    if module is None:
        return None

    ratchet_path = REPO_ROOT / ".ratchet.json"
    if not ratchet_path.exists():
        return None

    ratchet = json.loads(ratchet_path.read_text())
    baseline = ratchet.get("modules", {}).get(module)
    if baseline is None:
        return None

    baseline_covered = baseline["covered_lines"]

    rc, _ = run_tool(
        [
            "pytest",
            f"--cov={module}",
            "--cov-report=json",
            "--cov-fail-under=0",
            "-q",
            "--tb=no",
            "--no-header",
        ]
    )
    if rc != 0:
        return None  # tests failed; let ruff/mypy/pyright report

    cov_file = REPO_ROOT / "coverage.json"
    if not cov_file.exists():
        return None

    cov_data = json.loads(cov_file.read_text())
    module_path_fragment = module.replace(".", "/")
    for file_key, file_data in cov_data.get("files", {}).items():
        normalized = file_key.replace("\\", "/")
        if module_path_fragment in normalized and normalized.endswith(".py"):
            current = file_data["summary"]["covered_lines"]
            if current < baseline_covered:
                return (
                    f"RATCHET VIOLATION: {module} coverage decreased "
                    f"({current} < {baseline_covered} covered lines). "
                    "Add tests before reducing coverage."
                )
            break

    return None


def main() -> int:
    """Lint and type-check the edited file.

    Returns:
        0 if clean, 2 if violations found.
    """
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError, EOFError:
        return 0

    file_path_str = data.get("tool_input", {}).get("file_path") or data.get(
        "tool_response", {}
    ).get("filePath")
    if not file_path_str:
        return 0

    path = Path(file_path_str)
    if not is_target(path):
        return 0

    issues: list[str] = []

    rc, out = run_tool(["black", "--check", "--quiet", str(path)])
    if rc != 0:
        issues.append(
            f"black: {path.name} would be reformatted. "
            f"Run '.venv/Scripts/black {path}' (or '.venv/bin/black {path}') to fix."
        )

    rc, out = run_tool(["ruff", "check", str(path)])
    if rc != 0 and out:
        issues.append(f"ruff:\n{out}")

    rc, out = run_tool(["mypy", str(path)])
    if rc != 0 and out:
        issues.append(f"mypy:\n{out}")

    rc, out = run_tool(["pyright", str(path)])
    if rc != 0 and out:
        issues.append(f"pyright:\n{out}")

    ratchet_issue = check_coverage_ratchet(path)
    if ratchet_issue:
        issues.append(f"ratchet:\n{ratchet_issue}")

    if issues:
        print("\n".join(issues), file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
