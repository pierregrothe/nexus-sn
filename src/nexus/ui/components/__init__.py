# src/nexus/ui/components/__init__.py
# Public re-exports of NEXUS CLI component primitives.
# Author: Pierre Grothe
# Date: 2026-05-11
"""NEXUS CLI component library.

Each module exposes a frozen Pydantic model with a ``__rich_console__``
method or a tiny helper function. Callers do
``console.print(StatusBadge.warn("EXPIRED"))`` or
``console.print(default_marker())``.
"""

from nexus.ui.components.badge import StatusBadge
from nexus.ui.components.guide import CommandGuide
from nexus.ui.components.hint import Hint
from nexus.ui.components.marker import default_marker
from nexus.ui.components.notice import Notice
from nexus.ui.components.panel import KeyValuePanel, KvRow, two_col
from nexus.ui.components.progress import nexus_progress
from nexus.ui.components.table import DataColumn, DataTable

__all__ = [
    "CommandGuide",
    "DataColumn",
    "DataTable",
    "Hint",
    "KeyValuePanel",
    "KvRow",
    "Notice",
    "StatusBadge",
    "default_marker",
    "nexus_progress",
    "two_col",
]
