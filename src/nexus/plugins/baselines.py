# src/nexus/plugins/baselines.py
# Baseline-name validation and default constants.
# Author: Pierre Grothe
# Date: 2026-05-12
"""Baseline naming policy for plugin drift baselines."""

import re

from nexus.plugins.errors import InvalidBaselineNameError

__all__ = ["DEFAULT_BASELINE_NAME", "validate_baseline_name"]

DEFAULT_BASELINE_NAME = "default"
_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")


def validate_baseline_name(name: str) -> None:
    """Raise InvalidBaselineNameError when ``name`` is not a safe filename.

    Rules:
        - Lowercase ASCII letters, digits, hyphens, underscores only.
        - Must start with a letter or digit.
        - Maximum 63 characters.

    Args:
        name: Candidate baseline name.

    Raises:
        InvalidBaselineNameError: If ``name`` violates any rule above.
    """
    if not _NAME_RE.match(name):
        raise InvalidBaselineNameError(name)
