# src/nexus/ui/components/marker.py
# Lime bold "* " prefix marking the active default row in a list.
# Author: Pierre Grothe
# Date: 2026-05-11

"""default_marker helper for the active default row indicator.

The lime asterisk used in `nexus instance list` to point at the configured
default profile.
"""

from rich.text import Text

__all__ = ["default_marker"]


def default_marker() -> Text:
    """Return the lime bold ``"* "`` indicator.

    Returns:
        A ``rich.text.Text`` carrying the asterisk and trailing space,
        styled with the theme's ``ok`` style.
    """
    return Text("* ", style="ok")
