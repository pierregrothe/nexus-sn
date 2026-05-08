# src/nexus/ui/banner.py
# Gradient ASCII banner shown by user-facing CLI commands.
# Author: Pierre Grothe
# Date: 2026-05-08
"""Print the NEXUS banner with a left-to-right blue-to-cyan gradient.

Unicode block characters carve out from the project ASCII-only rule for
this single visual surface only; source-level identifiers and comments
elsewhere remain ASCII.
"""

from rich.console import Console
from rich.text import Text

from nexus.ui.theme import NEXUS_BLUE, NEXUS_CYAN

__all__ = ["banner_text", "gradient", "print_banner"]

_BANNER_LINES: tuple[str, ...] = (
    "███╗   ██╗███████╗██╗  ██╗██╗   ██╗███████╗",
    "████╗  ██║██╔════╝╚██╗██╔╝██║   ██║██╔════╝",
    "██╔██╗ ██║█████╗   ╚███╔╝ ██║   ██║███████╗",
    "██║╚██╗██║██╔══╝   ██╔██╗ ██║   ██║╚════██║",
    "██║ ╚████║███████╗██╔╝ ██╗╚██████╔╝███████║",
    "╚═╝  ╚═══╝╚══════╝╚═╝  ╚═╝ ╚═════╝ ╚══════╝",
)
_TAGLINE = "ServiceNow AI architect agent"


def gradient(
    text: str,
    *,
    start: tuple[int, int, int],
    end: tuple[int, int, int],
) -> Text:
    """Render ``text`` with a left-to-right per-character RGB gradient.

    Args:
        text: The string to colour. Empty input yields an empty Text.
        start: ``(R, G, B)`` colour applied to the first character.
        end: ``(R, G, B)`` colour applied to the last character.

    Returns:
        A rich.Text whose segments interpolate linearly between start and end.
    """
    if not text:
        return Text()
    if len(text) == 1:
        return Text(text, style=_rgb_style(*start))
    out = Text()
    span = len(text) - 1
    sr, sg, sb = start
    er, eg, eb = end
    for i, ch in enumerate(text):
        ratio = i / span
        r = int(sr + (er - sr) * ratio)
        g = int(sg + (eg - sg) * ratio)
        b = int(sb + (eb - sb) * ratio)
        out.append(ch, style=_rgb_style(r, g, b))
    return out


def banner_text() -> Text:
    """Build the gradient banner without printing it.

    Returns:
        A rich.Text with the multi-line NEXUS art plus tagline, each line
        coloured along the blue-to-cyan gradient.
    """
    width = max(len(line) for line in _BANNER_LINES)
    out = Text()
    for line in _BANNER_LINES:
        out.append_text(gradient(line.ljust(width), start=NEXUS_BLUE, end=NEXUS_CYAN))
        out.append("\n")
    out.append(_TAGLINE.center(width), style="muted")
    out.append("\n")
    return out


def print_banner(console: Console) -> None:
    """Print the gradient banner if the console is a terminal.

    Args:
        console: Destination Console. Skipped silently when not a TTY so
            piped/scripted output stays clean.
    """
    if not console.is_terminal:
        return
    console.print(banner_text())


def _rgb_style(r: int, g: int, b: int) -> str:
    return f"rgb({r},{g},{b})"
