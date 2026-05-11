# src/nexus/ui/components/__init__.py
"""NEXUS CLI component library.

Each module exposes a frozen Pydantic model with a __rich_console__ method.
Callers do `console.print(StatusBadge.warn("EXPIRED"))`.
"""

from nexus.ui.components.badge import StatusBadge

__all__ = ["StatusBadge"]
