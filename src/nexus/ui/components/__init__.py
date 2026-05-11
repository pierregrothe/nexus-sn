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
from nexus.ui.components.hint import Hint
from nexus.ui.components.marker import default_marker
from nexus.ui.components.notice import Notice
from nexus.ui.components.panel import KeyValuePanel, KvRow, two_col
from nexus.ui.components.table import DataColumn, DataTable

__all__ = [
    "DataColumn",
    "DataTable",
    "Hint",
    "KeyValuePanel",
    "KvRow",
    "Notice",
    "StatusBadge",
    "default_marker",
    "two_col",
]
