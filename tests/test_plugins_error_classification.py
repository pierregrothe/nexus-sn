# tests/test_plugins_error_classification.py
# Unit tests for the SN-error classifier (already-installed, offering-plugin).
# Author: Pierre Grothe
# Date: 2026-05-18
"""Tests for the pure pattern matchers in ``nexus.plugins.error_classification``."""

from __future__ import annotations

from nexus.plugins.error_classification import (
    is_already_installed_error,
    is_offering_plugin_error,
)

__all__: list[str] = []


def test_is_already_installed_error_matches_canonical_sn_message() -> None:
    exc = RuntimeError("Application version is currently installed (Http Response: 400)")
    assert is_already_installed_error(exc)


def test_is_already_installed_error_is_case_insensitive() -> None:
    """SN's wording can change capitalisation across releases."""
    exc = RuntimeError("APPLICATION VERSION IS CURRENTLY INSTALLED")
    assert is_already_installed_error(exc)


def test_is_already_installed_error_rejects_unrelated_messages() -> None:
    assert not is_already_installed_error(RuntimeError("Some other error"))


def test_is_offering_plugin_error_matches_canonical_sn_message() -> None:
    exc = RuntimeError(
        "Unexpected HTTP 500: Cannot find function hasOwnProperty in object "
        "com.glide.cicd.exception.CICDProcessException: Offering plugin id must "
        "be specified for application"
    )
    assert is_offering_plugin_error(exc)


def test_is_offering_plugin_error_rejects_other_errors() -> None:
    assert not is_offering_plugin_error(RuntimeError("Unexpected HTTP 500: oops"))
