# src/nexus/ui/components/__init__.py
# Public re-exports of NEXUS CLI component primitives.
# Author: Pierre Grothe
# Date: 2026-05-11
"""NEXUS CLI component library.

Exports are either frozen Pydantic models with a ``__rich_console__`` method or
plain factory functions returning a ``rich.text.Text``. Callers do
``console.print(StatusBadge.warn("EXPIRED"))`` or
``console.print(default_marker())``.
"""

from nexus.ui.components.badge import StatusBadge
from nexus.ui.components.marker import default_marker

__all__ = ["StatusBadge", "default_marker"]
