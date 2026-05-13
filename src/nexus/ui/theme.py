# src/nexus/ui/theme.py
# Rich theme used by the NEXUS CLI Console.
# Author: Pierre Grothe
# Date: 2026-05-11
"""NEXUS visual identity: brand RGB stops + named Rich styles.

This module owns the only colour constants in the project. All components
read from here. Inline markup uses semantic style names (``label``,
``value``, ``ok``, ``warn``, ``error``, ``dim``, ``border.start``,
``border.end``).
"""

from rich.theme import Theme

__all__ = [
    "NEXUS_THEME",
    "SN_BLUE",
    "SN_LIME",
]

SN_BLUE: tuple[int, int, int] = (0x00, 0x68, 0xB1)
SN_LIME: tuple[int, int, int] = (0x7C, 0xC1, 0x43)

_SN_BLUE_RGB = f"rgb({SN_BLUE[0]},{SN_BLUE[1]},{SN_BLUE[2]})"
_SN_LIME_RGB = f"rgb({SN_LIME[0]},{SN_LIME[1]},{SN_LIME[2]})"

NEXUS_THEME = Theme(
    {
        # Labels (panel titles, row labels, column headers) get the brand
        # gradient. Values (body text, cell contents, example commands)
        # render in bright white for maximum readability against any
        # terminal background. Dim is reserved for footer hints only.
        "label": f"{_SN_BLUE_RGB} bold",
        "value": "bright_white",
        "dim": "bright_black",
        "ok": f"{_SN_LIME_RGB} bold",
        "warn": "yellow bold",
        "error": "red bold",
        "border.start": _SN_BLUE_RGB,
        "border.end": _SN_LIME_RGB,
    }
)
