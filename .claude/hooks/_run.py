#!/usr/bin/env python3
# .claude/hooks/_run.py
# Cross-platform launcher: find the project venv Python and run a hook.
# Author: Pierre Grothe
# Date: 2026-05-12
"""Launcher for Claude Code hooks.

Bootstrap Python (from settings.json) re-execs into the project venv Python
when one exists, so hook scripts always see the same interpreter and tooling
that the project uses for pytest/ruff/mypy/pyright. If no venv exists yet
(fresh clone before ``poetry install``), falls back to ``sys.executable``.

Usage from ``.claude/settings.json`` -- a chained ``||`` command keeps the
hook working across the three OSes without any per-machine override:

    python .claude/hooks/_run.py <hook-name>
        || python3 .claude/hooks/_run.py <hook-name>
        || py -3 .claude/hooks/_run.py <hook-name>

The fallback covers:
    - Windows: ``python.exe`` (PATH installer) and ``py.exe`` (always-present
      Python launcher)
    - macOS: ``python3`` (universal via Xcode CLT / Homebrew / python.org)
      and ``python`` (Homebrew + python.org create the symlink)
    - Linux: ``python3`` (universal) and ``python`` (Arch/Fedora default,
      or Ubuntu with ``python-is-python3`` installed)

The ``||`` operator works in bash, zsh, cmd.exe, and PowerShell 7+. After
bootstrap, the launcher locates ``.claude/hooks/<hook-name>.py``, picks the
project venv Python, and forwards stdin / stdout / stderr / exit code
unchanged.

Exit codes:
    0 -- success or hook silently skipped (missing hook script / missing argv)
    Whatever the target hook returns (typically 0 or 2)
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent


def _venv_python() -> Path:
    """Return the project venv Python path for the current OS.

    Returns:
        ``REPO_ROOT/.venv/Scripts/python.exe`` on Windows,
        ``REPO_ROOT/.venv/bin/python`` on macOS / Linux.
        Path may not exist yet on a fresh clone.
    """
    if sys.platform == "win32":
        return REPO_ROOT / ".venv" / "Scripts" / "python.exe"
    return REPO_ROOT / ".venv" / "bin" / "python"


def main() -> int:
    """Resolve the target hook and re-exec it under the venv Python.

    Returns:
        The hook's exit code, or 0 when no hook name was provided / the
        named hook does not exist (silent skip to keep Claude Code unblocked).
    """
    if len(sys.argv) < 2:
        return 0

    hook_name = sys.argv[1]
    hook_path = REPO_ROOT / ".claude" / "hooks" / f"{hook_name}.py"
    if not hook_path.exists():
        return 0

    venv = _venv_python()
    python_exe = str(venv) if venv.exists() else sys.executable

    result = subprocess.run([python_exe, str(hook_path)], stdin=sys.stdin)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
