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
    "severity_color",
    "truncate_middle",
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


def severity_color(score: int) -> str:
    """Map a 0..100 severity score to a Rich ``rgb(r,g,b)`` style string.

    The hue sweeps HSL green (120 deg) at score 0 to red (0 deg) at score 100
    with full saturation and 50% lightness. Out-of-range inputs are clamped.

    Args:
        score: Integer severity 0..100. Values outside the range are clamped.

    Returns:
        A Rich-compatible style string like ``"rgb(124,193,67)"``.
    """
    clamped = max(0, min(100, score))
    hue_deg = 120.0 * (1.0 - clamped / 100.0)
    h_prime = hue_deg / 60.0
    chroma = 1.0
    x = chroma * (1.0 - abs(h_prime % 2.0 - 1.0))
    if 0.0 <= h_prime < 1.0:
        r1, g1, b1 = chroma, x, 0.0
    elif 1.0 <= h_prime < 2.0:
        r1, g1, b1 = x, chroma, 0.0
    else:
        r1, g1, b1 = 0.0, chroma, x
    m = 0.5 - chroma / 2.0
    r = round((r1 + m) * 255)
    g = round((g1 + m) * 255)
    b = round((b1 + m) * 255)
    return f"rgb({r},{g},{b})"


def truncate_middle(text: str, width: int, marker: str = "...") -> str:
    """Truncate ``text`` to ``width`` columns by elision from the middle.

    Preserves a prefix and suffix so identifiers like
    ``sn_grc_advanced_dependencies_v3.2.1`` stay recognisable at both ends.

    Args:
        text: The string to fit.
        width: Maximum number of characters in the returned string.
        marker: Elision marker inserted between the prefix and suffix.

    Returns:
        ``text`` unchanged when it already fits, otherwise a shorter string
        of length ``width`` whose middle is replaced by ``marker``.

    Raises:
        ValueError: If ``width`` is non-positive or smaller than ``len(marker)``.
    """
    if width <= 0:
        raise ValueError(f"width must be positive (got {width})")
    if len(marker) >= width:
        raise ValueError(f"marker {marker!r} does not fit in width {width}")
    if len(text) <= width:
        return text
    remaining = width - len(marker)
    prefix_len = (remaining + 1) // 2
    suffix_len = remaining - prefix_len
    if suffix_len == 0:
        return text[:prefix_len] + marker
    return text[:prefix_len] + marker + text[-suffix_len:]
