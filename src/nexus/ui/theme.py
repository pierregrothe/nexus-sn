# src/nexus/ui/theme.py
# Rich theme used by the NEXUS CLI Console.
# Author: Pierre Grothe
# Date: 2026-05-08
"""NEXUS visual identity: gradient stops + named rich styles.

Importing nexus.ui.theme has no nicegui dependency, so cli.py can apply the
theme on every invocation without forcing the optional [ui] extra.
"""

from rich.theme import Theme

__all__ = ["NEXUS_BLUE", "NEXUS_CYAN", "NEXUS_THEME"]

NEXUS_BLUE: tuple[int, int, int] = (0x1F, 0x6F, 0xEB)
NEXUS_CYAN: tuple[int, int, int] = (0x39, 0xD3, 0xC3)


NEXUS_THEME = Theme(
    {
        "primary": f"rgb({NEXUS_BLUE[0]},{NEXUS_BLUE[1]},{NEXUS_BLUE[2]})",
        "accent": f"rgb({NEXUS_CYAN[0]},{NEXUS_CYAN[1]},{NEXUS_CYAN[2]})",
        "info": "blue",
        "ok": "cyan",
        "warning": "yellow",
        "error": "bold red",
        "muted": "bright_black",
    }
)
