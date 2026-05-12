# tests/test_plugins_baselines.py
# Tests for baseline-name validation.
# Author: Pierre Grothe
# Date: 2026-05-12
"""Tests for validate_baseline_name."""

import pytest

from nexus.plugins.baselines import DEFAULT_BASELINE_NAME, validate_baseline_name
from nexus.plugins.errors import InvalidBaselineNameError

__all__: list[str] = []


@pytest.mark.parametrize(
    "name",
    [
        "default",
        "pre-upgrade",
        "quarterly_2026q2",
        "a",
        "0",
        "abc-123_xyz",
        "a" * 63,
    ],
)
def test_validate_baseline_name_accepts_valid(name: str) -> None:
    validate_baseline_name(name)


@pytest.mark.parametrize(
    "name",
    [
        "",
        "_leading-underscore",
        "-leading-dash",
        "UPPERCASE",
        "has space",
        "has/slash",
        "has.dot",
        "a" * 64,
    ],
)
def test_validate_baseline_name_rejects_invalid(name: str) -> None:
    with pytest.raises(InvalidBaselineNameError):
        validate_baseline_name(name)


def test_default_baseline_name_constant() -> None:
    assert DEFAULT_BASELINE_NAME == "default"
    validate_baseline_name(DEFAULT_BASELINE_NAME)
