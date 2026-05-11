# src/nexus/ui/theme.py
# Rich theme used by the NEXUS CLI Console.
# Author: Pierre Grothe
# Date: 2026-05-08

"""NEXUS visual identity: brand RGB stops + named Rich styles.

Importing nexus.ui.theme has no nicegui dependency, so cli.py can apply the
theme on every invocation without forcing the optional [ui] extra.

This module owns the only colour constants in the project. All components
read from here. Inline markup uses semantic style names (`label`, `value`,
`ok`, `warn`, `error`, `dim`, `border.start`, `border.end`); the legacy
brand-named styles (`sn.blue`, `sn.lime`, `info`, `accent`, `primary`)
remain registered for backwards source-compat during the migration PR and
are removed in the cleanup commit once all callers are converted.
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

SN_BLUE: tuple[int, int, int] = (0x00, 0x68, 0xB1)
SN_LIME: tuple[int, int, int] = (0x7C, 0xC1, 0x43)
SN_TEXT_START: tuple[int, int, int] = (
    int(SN_BLUE[0] + (SN_LIME[0] - SN_BLUE[0]) * 0.40),
    int(SN_BLUE[1] + (SN_LIME[1] - SN_BLUE[1]) * 0.40),
    int(SN_BLUE[2] + (SN_LIME[2] - SN_BLUE[2]) * 0.40),
)

_SN_BLUE_RGB = f"rgb({SN_BLUE[0]},{SN_BLUE[1]},{SN_BLUE[2]})"
_SN_LIME_RGB = f"rgb({SN_LIME[0]},{SN_LIME[1]},{SN_LIME[2]})"

NEXUS_THEME = Theme(
    {
        # New semantic names -- preferred going forward.
        "label": f"{_SN_BLUE_RGB} bold",
        "value": "default",
        "dim": "bright_black",
        "ok": f"{_SN_LIME_RGB} bold",
        "warn": "yellow bold",
        "error": "red bold",
        "border.start": _SN_BLUE_RGB,
        "border.end": _SN_LIME_RGB,
        # Legacy brand-named styles -- removed in cleanup commit.
        "primary": f"rgb({NEXUS_BLUE[0]},{NEXUS_BLUE[1]},{NEXUS_BLUE[2]})",
        "accent": f"rgb({NEXUS_CYAN[0]},{NEXUS_CYAN[1]},{NEXUS_CYAN[2]})",
        "sn.blue": _SN_BLUE_RGB,
        "sn.lime": _SN_LIME_RGB,
        "info": "blue",
        "muted": "bright_black",
    }
)
