# src/nexus/templates/repo_name.py
# github_repo format validation for the nexus sync command.
# Author: Pierre Grothe
# Date: 2026-05-18
"""Validate the ``github_repo`` config field before any HTTP fetch.

Rejects URLs (``https://...``, ``http://...``, ``git@...``) and
malformed inputs (empty, missing slash, too many slashes, empty
component). Returns the canonical ``<owner>/<name>`` slug after
stripping surrounding whitespace and any trailing slash.
"""

from __future__ import annotations

from nexus.templates.errors import InvalidGitHubRepoError

__all__ = ["validate_github_repo"]

_URL_PREFIXES = ("https://", "http://", "git@")


def validate_github_repo(value: str) -> str:
    """Return the canonical ``owner/name`` form or raise.

    Args:
        value: Candidate ``github_repo`` value from config.

    Returns:
        The same value with surrounding whitespace and any trailing
        slash stripped.

    Raises:
        InvalidGitHubRepoError: When ``value`` violates any rule. The
            ``reason`` attribute carries one of the slugs documented
            in the exception class.
    """
    stripped = value.strip()
    if not stripped:
        raise InvalidGitHubRepoError(value, "empty")
    if any(stripped.startswith(prefix) for prefix in _URL_PREFIXES):
        raise InvalidGitHubRepoError(value, "url not allowed")
    had_trailing_slash = stripped.endswith("/")
    canonical = stripped.rstrip("/")
    if not canonical:
        raise InvalidGitHubRepoError(value, "empty")
    if "/" not in canonical:
        if had_trailing_slash:
            raise InvalidGitHubRepoError(value, "empty component")
        raise InvalidGitHubRepoError(value, "missing slash")
    parts = canonical.split("/")
    if len(parts) > 2:
        raise InvalidGitHubRepoError(value, "too many slashes")
    if not parts[0] or not parts[1]:
        raise InvalidGitHubRepoError(value, "empty component")
    return canonical
