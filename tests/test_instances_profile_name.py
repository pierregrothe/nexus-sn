# tests/test_instances_profile_name.py
# Tests for nexus.instances.profile_name.validate_profile_name.
# Author: Pierre Grothe
# Date: 2026-05-18
"""Tests for nexus.instances.profile_name."""

from __future__ import annotations

import pytest

from nexus.instances.errors import InvalidProfileNameError
from nexus.instances.profile_name import validate_profile_name


@pytest.mark.parametrize(
    "name",
    [
        "prod",
        "prod-east-1",
        "prod_team_a",
        "Prod1",
        "a",
        "a" * 64,
    ],
)
def test_validate_profile_name_accepts_valid_names(name: str) -> None:
    assert validate_profile_name(name) == name


@pytest.mark.parametrize(
    ("name", "expected_reason"),
    [
        ("", "empty"),
        ("   ", "empty"),
        ("\t\n", "empty"),
        ("prod team", "whitespace"),
        (" prod", "whitespace"),
        ("prod ", "whitespace"),
        ("a" * 65, "too long"),
        ("../prod", "traversal"),
        ("prod/..", "traversal"),
        ("a..b", "traversal"),
        ("..", "traversal"),
        ("prod/east", "separator"),
        ("prod\\east", "separator"),
        (".hidden", "leading dot"),
        (".", "leading dot"),
        ("prod\x00null", "control"),
        ("prod\x01ctrl", "control"),
        ("prod\xe9", "non-ascii"),
        ("éprod", "non-ascii"),
        ("prod:east", "disallowed"),
        ("prod@host", "disallowed"),
        ("prod.east", "disallowed"),
    ],
)
def test_validate_profile_name_rejects_invalid_names(
    name: str, expected_reason: str
) -> None:
    with pytest.raises(InvalidProfileNameError) as excinfo:
        validate_profile_name(name)
    assert excinfo.value.reason == expected_reason
    assert excinfo.value.name == name


def test_validate_profile_name_error_message_includes_name_and_reason() -> None:
    with pytest.raises(InvalidProfileNameError) as excinfo:
        validate_profile_name("../escape")
    msg = str(excinfo.value)
    assert "../escape" in msg
    assert "traversal" in msg
