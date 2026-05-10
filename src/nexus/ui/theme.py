# src/nexus/ui/theme.py
# Rich theme used by the NEXUS CLI Console.
# Author: Pierre Grothe
# Date: 2026-05-08
"""NEXUS visual identity: gradient stops + named rich styles.

Importing nexus.ui.theme has no nicegui dependency, so cli.py can apply the
theme on every invocation without forcing the optional [ui] extra.
"""

from rich.theme import Theme

__all__ = [
    "NEXUS_BLUE",
    "NEXUS_CYAN",
    "NEXUS_THEME",
    "SN_BLUE",
    "SN_LIME",
    "SN_TEXT_START",
]

NEXUS_BLUE: tuple[int, int, int] = (0x1F, 0x6F, 0xEB)
NEXUS_CYAN: tuple[int, int, int] = (0x39, 0xD3, 0xC3)

# ServiceNow brand colors -- gradient endpoints for panel borders and text.
SN_BLUE: tuple[int, int, int] = (0x00, 0x68, 0xB1)
SN_LIME: tuple[int, int, int] = (0x7C, 0xC1, 0x43)
# 40% along SN_BLUE -> SN_LIME: teal start point for value-text gradients.
SN_TEXT_START: tuple[int, int, int] = (
    int(SN_BLUE[0] + (SN_LIME[0] - SN_BLUE[0]) * 0.40),
    int(SN_BLUE[1] + (SN_LIME[1] - SN_BLUE[1]) * 0.40),
    int(SN_BLUE[2] + (SN_LIME[2] - SN_BLUE[2]) * 0.40),
)


NEXUS_THEME = Theme(
    {
        "primary": f"rgb({NEXUS_BLUE[0]},{NEXUS_BLUE[1]},{NEXUS_BLUE[2]})",
        "accent": f"rgb({NEXUS_CYAN[0]},{NEXUS_CYAN[1]},{NEXUS_CYAN[2]})",
        # ServiceNow brand colors as named Rich styles -- use as [sn.blue]...[/sn.blue]
        "sn.blue": f"rgb({SN_BLUE[0]},{SN_BLUE[1]},{SN_BLUE[2]})",
        "sn.lime": f"rgb({SN_LIME[0]},{SN_LIME[1]},{SN_LIME[2]})",
        "info": "blue",
        "ok": "cyan",
        "warning": "yellow",
        "error": "bold red",
        "muted": "bright_black",
    }
)
