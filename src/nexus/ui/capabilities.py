# src/nexus/ui/capabilities.py
# Terminal capability detection and four-tier render profile selection.
# Author: Pierre Grothe
# Date: 2026-05-15

"""Detect the terminal's capabilities and pick a render profile.

NEXUS picks one of four profiles at process startup based on what the
terminal supports. Components consult the profile via ``RenderContext``
to choose layouts, colours, and pager behaviour without per-call TTY
checks.

Profiles:
    RICH:   modern TTY with truecolor + sufficient height + interactive
    BASIC:  TTY with 16+ colours but missing one of the RICH preconditions
    LEGACY: TTY that lacks ANSI escape support (pre-Win10 cmd.exe, dumb)
    PLAIN:  not a TTY, or forced via ``--plain`` / ``NEXUS_PLAIN`` / CI
"""

import os
import shutil
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator
from rich.console import Console

__all__ = [
    "CI_ENV_VARS",
    "ColorDepth",
    "RenderProfile",
    "TerminalCapabilities",
    "detect",
    "pick_profile",
]

CI_ENV_VARS: tuple[str, ...] = (
    "CI",
    "GITHUB_ACTIONS",
    "JENKINS_HOME",
    "GITLAB_CI",
    "BUILDKITE",
    "CIRCLECI",
    "TRAVIS",
    "DRONE",
    "TF_BUILD",
)


class ColorDepth(StrEnum):
    """Terminal colour capability tier.

    Ordered from least to most capable. Comparison uses the StrEnum
    value, so callers must use ``_DEPTH_ORDER`` rather than ``<``.
    """

    NONE = "none"
    ANSI16 = "ansi16"
    ANSI256 = "ansi256"
    TRUECOLOR = "truecolor"


_DEPTH_ORDER: dict[ColorDepth, int] = {
    ColorDepth.NONE: 0,
    ColorDepth.ANSI16: 1,
    ColorDepth.ANSI256: 2,
    ColorDepth.TRUECOLOR: 3,
}


class RenderProfile(StrEnum):
    """Render strategy tier picked once at process startup."""

    RICH = "rich"
    BASIC = "basic"
    LEGACY = "legacy"
    PLAIN = "plain"


class TerminalCapabilities(BaseModel):
    """Immutable snapshot of the terminal's capabilities at startup.

    Attributes:
        is_tty: stdout and stderr both report ``isatty()``.
        is_ci: One of the documented CI env vars is set.
        color_depth: Detected colour capability tier.
        cols: Terminal width in columns (fallback 80 on OSError).
        rows: Terminal height in rows (fallback 24 on OSError).
        legacy_windows: Rich's pre-Win10 cmd.exe detection, suppressed
            when Windows Terminal or iTerm session env is present.
        term_program: Value of ``$TERM_PROGRAM`` (empty string when unset).
        is_dumb_terminal: ``$TERM == "dumb"``.
        is_multiplexer: Inside tmux/screen without truecolor confirmation.
        no_color_env: ``$NO_COLOR`` is set to any value.
        forced_plain: ``--plain`` flag detected in argv or
            ``$NEXUS_PLAIN`` env var is set.
        supports_hyperlinks: At least ANSI256 and not legacy_windows.
    """

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    is_tty: bool
    is_ci: bool
    color_depth: ColorDepth
    cols: int
    rows: int
    legacy_windows: bool
    term_program: str
    is_dumb_terminal: bool
    is_multiplexer: bool
    no_color_env: bool
    forced_plain: bool
    supports_hyperlinks: bool

    @model_validator(mode="after")
    def _check_dimensions(self) -> Self:
        if self.cols < 1 or self.rows < 1:
            raise ValueError(f"cols and rows must be positive (got {self.cols}x{self.rows})")
        return self


def _detect_color_depth(console: Console) -> ColorDepth:
    """Map Rich's ``console.color_system`` to our :class:`ColorDepth` enum."""
    system = console.color_system
    match system:
        case None:
            return ColorDepth.NONE
        case "standard" | "windows":
            return ColorDepth.ANSI16
        case "256":
            return ColorDepth.ANSI256
        case "truecolor":
            return ColorDepth.TRUECOLOR
        case _:  # pragma: no cover -- Rich's color_system enum is closed.
            return ColorDepth.ANSI16


def _detect_ci(environ: dict[str, str]) -> bool:
    """Return True when any of the documented CI env vars is set."""
    return any(var in environ for var in CI_ENV_VARS)


def _detect_legacy_windows(console: Console, environ: dict[str, str]) -> bool:
    """Override Rich's legacy_windows when a modern session marker is present."""
    if "WT_SESSION" in environ or "ITERM_SESSION_ID" in environ:
        return False
    return console.legacy_windows


def _detect_multiplexer(environ: dict[str, str]) -> bool:
    """Detect tmux/screen sessions without an explicit truecolor claim."""
    term = environ.get("TERM", "")
    in_multiplexer = term.startswith("tmux") or "screen" in term
    if not in_multiplexer:
        return False
    return environ.get("COLORTERM", "") != "truecolor"


def _safe_terminal_size() -> tuple[int, int]:
    """Return (cols, rows) with a stable 80x24 fallback on OSError."""
    try:
        size = shutil.get_terminal_size(fallback=(80, 24))
    except OSError:
        return (80, 24)
    return (size.columns, size.lines)


def detect(
    console: Console, forced_plain: bool, environ: dict[str, str] | None = None
) -> TerminalCapabilities:
    """Build a :class:`TerminalCapabilities` snapshot from the live process.

    Args:
        console: A Rich Console used to read ``is_terminal``, ``color_system``,
            and ``legacy_windows``. The console is not retained.
        forced_plain: Result of the argv pre-scan and ``$NEXUS_PLAIN`` lookup
            performed by :func:`nexus.ui.console_factory.make_console`.
        environ: Optional environment mapping for testing. Defaults to
            ``os.environ``.

    Returns:
        A frozen :class:`TerminalCapabilities` instance.
    """
    env = environ if environ is not None else dict(os.environ)
    cols, rows = _safe_terminal_size()
    color_depth = _detect_color_depth(console)
    legacy = _detect_legacy_windows(console, env)
    is_tty = console.is_terminal
    return TerminalCapabilities(
        is_tty=is_tty,
        is_ci=_detect_ci(env),
        color_depth=color_depth,
        cols=cols,
        rows=rows,
        legacy_windows=legacy,
        term_program=env.get("TERM_PROGRAM", ""),
        is_dumb_terminal=env.get("TERM", "") == "dumb",
        is_multiplexer=_detect_multiplexer(env),
        no_color_env="NO_COLOR" in env,
        forced_plain=forced_plain,
        supports_hyperlinks=_DEPTH_ORDER[color_depth] >= _DEPTH_ORDER[ColorDepth.ANSI256]
        and not legacy,
    )


def pick_profile(caps: TerminalCapabilities) -> RenderProfile:
    """Choose a :class:`RenderProfile` from the snapshot. Pure function.

    Args:
        caps: A frozen terminal-capabilities snapshot.

    Returns:
        Exactly one of RICH, BASIC, LEGACY, PLAIN.
    """
    if caps.forced_plain or not caps.is_tty or caps.is_dumb_terminal or caps.is_ci:
        return RenderProfile.PLAIN
    if caps.legacy_windows or caps.color_depth is ColorDepth.NONE:
        return RenderProfile.LEGACY
    if (
        caps.color_depth is ColorDepth.TRUECOLOR
        and caps.rows >= 24
        and not caps.no_color_env
        and not caps.is_multiplexer
    ):
        return RenderProfile.RICH
    return RenderProfile.BASIC
