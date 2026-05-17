# src/nexus/ui/console_factory.py
# Build a Rich Console + RenderContext bundle once at process startup.
# Author: Pierre Grothe
# Date: 2026-05-15

"""Construct the singleton :class:`RenderContext` for the process.

The Console must be built before Typer parses argv, so the ``--plain``
flag is detected by a pure argv pre-scan rather than waiting for Typer
to populate a flag value. Typer still validates the flag for help text;
the pre-scan is the authoritative source for the Console's behaviour.
"""

import os
import sys
from collections.abc import Sequence

from rich.console import Console

from nexus.ui.capabilities import detect, pick_profile
from nexus.ui.render_context import RenderContext
from nexus.ui.theme import NEXUS_THEME

__all__ = [
    "argv_has_plain",
    "make_console",
]


def argv_has_plain(argv: Sequence[str] | None = None) -> bool:
    """Return True if ``--plain`` appears in argv after the program name.

    The flag is detected literally, before Typer parses arguments. This
    keeps the pre-scan deterministic and lets tests pass a synthetic
    argv list without monkey-patching ``sys.argv``.

    Args:
        argv: Optional argv list. Defaults to ``sys.argv``.

    Returns:
        ``True`` when ``"--plain"`` is among ``argv[1:]``.
    """
    source = argv if argv is not None else sys.argv
    return "--plain" in source[1:]


def make_console(
    *,
    forced_plain: bool | None = None,
    environ: dict[str, str] | None = None,
    argv: Sequence[str] | None = None,
) -> RenderContext:
    """Build a Rich :class:`Console` and a frozen :class:`RenderContext`.

    Args:
        forced_plain: Override the argv + env-var pre-scan. ``None`` triggers
            the pre-scan; an explicit bool short-circuits it (tests).
        environ: Optional environment mapping; defaults to ``os.environ``.
        argv: Optional argv list; defaults to ``sys.argv``.

    Returns:
        A :class:`RenderContext` with the Console, the capability snapshot,
        and the selected render profile. Suitable for attaching to a
        Typer context's ``obj`` attribute.
    """
    env = environ if environ is not None else dict(os.environ)
    if forced_plain is None:
        forced_plain = argv_has_plain(argv) or "NEXUS_PLAIN" in env
    console = Console(theme=NEXUS_THEME, safe_box=True)
    caps = detect(console, forced_plain=forced_plain, environ=env)
    profile = pick_profile(caps)
    return RenderContext(console=console, caps=caps, profile=profile)
