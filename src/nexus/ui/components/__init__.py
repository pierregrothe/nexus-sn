# src/nexus/ui/components/__init__.py
# NEXUS CLI component library package.
# Author: Pierre Grothe
# Date: 2026-05-11

"""NEXUS CLI component library.

Each module exposes a frozen Pydantic model with a __rich_console__ method.
Callers do `console.print(StatusBadge.warn("EXPIRED"))`.
"""

__all__: list[str] = []
