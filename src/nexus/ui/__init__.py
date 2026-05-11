# src/nexus/ui/__init__.py
# Public re-exports of the NEXUS CLI visual library.
# Author: Pierre Grothe
# Date: 2026-05-11
"""NEXUS CLI visual library.

Public API:

- ``components.*``      -- frozen Pydantic models with ``__rich_console__``
- ``banner.*``          -- ASCII banner (existing primitive)
- ``gradient_panel.*``  -- panel with gradient borders (existing primitive)
- ``theme.*``           -- colour constants and Rich Theme
"""

from nexus.ui.banner import banner_text, gradient, print_banner
from nexus.ui.components import (
    CommandGuide,
    DataColumn,
    DataTable,
    Hint,
    KeyValuePanel,
    KvRow,
    Notice,
    StatusBadge,
    default_marker,
    nexus_progress,
    two_col,
)
from nexus.ui.gradient_panel import GradientPanel, gradient_text
from nexus.ui.theme import NEXUS_THEME, SN_BLUE, SN_LIME

__all__ = [
    "NEXUS_THEME",
    "SN_BLUE",
    "SN_LIME",
    "CommandGuide",
    "DataColumn",
    "DataTable",
    "GradientPanel",
    "Hint",
    "KeyValuePanel",
    "KvRow",
    "Notice",
    "StatusBadge",
    "banner_text",
    "default_marker",
    "gradient",
    "gradient_text",
    "nexus_progress",
    "print_banner",
    "two_col",
]
