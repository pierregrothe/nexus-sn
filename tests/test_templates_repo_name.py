# tests/test_templates_repo_name.py
# Tests for validate_github_repo (story 02 of the sync epic).
# Author: Pierre Grothe
# Date: 2026-05-18
"""Tests for nexus.templates.repo_name.validate_github_repo."""

from __future__ import annotations

import pytest

from nexus.templates.errors import InvalidGitHubRepoError
from nexus.templates.repo_name import validate_github_repo


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("owner/name", "owner/name"),
        ("Owner-A/repo_b.git", "Owner-A/repo_b.git"),
        ("owner/name/", "owner/name"),
        ("owner/name.git/", "owner/name.git"),
        (" owner/name ", "owner/name"),
    ],
)
def test_validate_github_repo_accepts_canonical_inputs(value: str, expected: str) -> None:
    assert validate_github_repo(value) == expected


@pytest.mark.parametrize(
    ("value", "reason"),
    [
        ("", "empty"),
        ("   ", "empty"),
        ("singleword", "missing slash"),
        ("a/b/c", "too many slashes"),
        ("/name", "empty component"),
        ("owner/", "empty component"),
        ("https://github.com/owner/name", "url not allowed"),
        ("http://github.com/owner/name", "url not allowed"),
        ("git@github.com:owner/name", "url not allowed"),
    ],
)
def test_validate_github_repo_rejects_invalid_inputs(value: str, reason: str) -> None:
    with pytest.raises(InvalidGitHubRepoError) as excinfo:
        validate_github_repo(value)
    assert excinfo.value.reason == reason
    assert excinfo.value.value == value


def test_validate_github_repo_error_message_includes_value_and_reason() -> None:
    with pytest.raises(InvalidGitHubRepoError) as excinfo:
        validate_github_repo("https://github.com/x/y")
    msg = str(excinfo.value)
    assert "https://github.com/x/y" in msg
    assert "url not allowed" in msg
