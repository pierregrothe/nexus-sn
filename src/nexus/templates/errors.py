# src/nexus/templates/errors.py
# Typed exceptions for the templates layer.
# Author: Pierre Grothe
# Date: 2026-05-18
"""Errors raised by the templates subpackage."""

from __future__ import annotations

from pathlib import Path

__all__ = [
    "InvalidGitHubRepoError",
    "ScopeNotFoundError",
    "TemplateLoadError",
    "TemplatesError",
]


class TemplatesError(Exception):
    """Base class for all templates-layer errors."""


class InvalidGitHubRepoError(TemplatesError):
    """Raised when ``github_repo`` is not a valid ``<owner>/<name>`` slug.

    Attributes:
        value: The rejected input string.
        reason: A short slug describing which rule was violated. One of
            "empty", "missing slash", "too many slashes",
            "empty component", "url not allowed".
    """

    def __init__(self, value: str, reason: str) -> None:
        """Initialize with the rejected value and the violated rule.

        Args:
            value: The candidate string supplied by the user.
            reason: One of the documented reason slugs.
        """
        super().__init__(f"Invalid github_repo {value!r}: {reason}")
        self.value = value
        self.reason = reason


class TemplateLoadError(TemplatesError):
    """A template YAML file failed to read, parse, or validate.

    Attributes:
        path: Filesystem path of the offending template.
        cause: Underlying OSError, yaml.YAMLError, or pydantic.ValidationError.
    """

    def __init__(self, path: Path, cause: Exception) -> None:
        """Initialize with the offending path and the wrapped exception.

        Args:
            path: Filesystem path of the failed template.
            cause: Original exception.
        """
        self.path = path
        self.cause = cause
        super().__init__(f"failed to load template at {path}: {cause}")


class ScopeNotFoundError(TemplatesError):
    """ApplyEngine failed to resolve a target_scope slug to a sys_scope sys_id.

    Attributes:
        slug: The unresolved slug ApplyEngine tried to look up.
    """

    def __init__(self, slug: str) -> None:
        """Initialize with the unresolved slug.

        Args:
            slug: The target_scope value that no sys_scope record matched.
        """
        self.slug = slug
        super().__init__(f"no sys_scope record matches target_scope slug {slug!r}")
