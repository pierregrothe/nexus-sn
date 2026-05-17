# src/nexus/ui/glyphs.py
# ASCII glyph palette paired with NEXUS theme styles.
# Author: Pierre Grothe
# Date: 2026-05-15

"""ASCII-only status glyphs with optional theme styling.

The palette is ASCII-only per the project rule. Each glyph has a
natural theme pairing (``[ok]`` -> ``ok`` style, ``[!!]`` -> ``error``,
etc.) so the colour signal is primary and the literal characters
provide a NO_COLOR / non-TTY fallback.

Usage:

    from nexus.ui.glyphs import glyph
    console.print(glyph("ok"), "scan complete")
"""

from rich.text import Text

__all__ = [
    "GLYPHS",
    "STYLES",
    "glyph",
]

GLYPHS: dict[str, str] = {
    "ok": "[ok]",
    "err": "[!!]",
    "pending": "[..]",
    "arrow": "[->]",
    "active": "[*]",
}

STYLES: dict[str, str] = {
    "ok": "ok",
    "err": "error",
    "pending": "dim",
    "arrow": "label",
    "active": "ok",
}


def glyph(name: str, style: str | None = None) -> Text:
    """Build a styled :class:`rich.text.Text` glyph by name.

    Args:
        name: One of the keys in :data:`GLYPHS`
            (``ok``, ``err``, ``pending``, ``arrow``, ``active``).
        style: Optional override style. ``None`` uses the default pairing
            from :data:`STYLES`.

    Returns:
        A :class:`Text` instance ready to print or embed in tables.

    Raises:
        KeyError: If ``name`` is not a known glyph.
    """
    literal = GLYPHS[name]
    resolved = style if style is not None else STYLES[name]
    return Text(literal, style=resolved)
