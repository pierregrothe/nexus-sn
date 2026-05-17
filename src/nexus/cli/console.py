# src/nexus/cli/console.py
# Shared module-level consoles for cli.py and its extracted helper modules.
# Author: Pierre Grothe
# Date: 2026-05-16
"""Shared Rich consoles for the CLI surface.

Lives in its own module so the helper packages broken out of ``cli.py``
(cli_oauth, cli_help_text, etc.) can import the same console instance
the entry point uses, without creating a circular import.

Side effects on import:
    * Reconfigures ``sys.stdout`` / ``sys.stderr`` to UTF-8 so Rich's box
      characters render correctly on Windows code pages.
    * Builds a single :class:`RenderContext` via :func:`make_console`.

Both ``console`` and ``err_console`` are module-level singletons. Tests
may swap them via ``monkeypatch.setattr`` when they need to capture output.
"""

from __future__ import annotations

import sys

from rich.console import Console

from nexus.ui.console_factory import make_console
from nexus.ui.render_context import RenderContext
from nexus.ui.theme import NEXUS_THEME

__all__ = ["console", "err_console", "render_context"]


def _force_utf8_streams() -> None:
    """Reconfigure stdout/stderr to UTF-8 so Rich's box and ellipsis chars render.

    Windows defaults stdout to the system code page (cp1252 on en-US).
    Rich's Panel/Table borders and ellipsis truncation use characters
    outside cp1252 and crash with UnicodeEncodeError on legacy_windows
    code paths. Forcing UTF-8 with ``errors='replace'`` keeps NEXUS
    usable on default Git Bash / cmd.exe while honoring the project's
    ASCII-only output rule (no glyphs are introduced by NEXUS itself).
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


_force_utf8_streams()
render_context: RenderContext = make_console()
console: Console = render_context.console
err_console: Console = Console(stderr=True, theme=NEXUS_THEME, safe_box=True)
