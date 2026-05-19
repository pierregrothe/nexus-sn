# src/nexus/assessment/errors.py
# Assessment-layer error hierarchy.
# Author: Pierre Grothe
# Date: 2026-05-19

"""Exception types raised by the assessment layer."""

from __future__ import annotations

from pathlib import Path

__all__ = ["AssessmentError", "RulesetLoadError"]


class AssessmentError(Exception):
    """Base exception for the assessment package."""


class RulesetLoadError(AssessmentError):
    """A YAML ruleset file failed to parse or validate.

    Attributes:
        path: Filesystem path of the offending ruleset.
        cause: Underlying YAML or Pydantic exception.
    """

    def __init__(self, path: Path, cause: Exception) -> None:
        """Initialize with the offending path and underlying cause.

        Args:
            path: Filesystem path of the failed ruleset.
            cause: Original exception (yaml.YAMLError or pydantic.ValidationError).
        """
        self.path = path
        self.cause = cause
        super().__init__(f"failed to load ruleset at {path}: {cause}")
