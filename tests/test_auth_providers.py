# tests/test_auth_providers.py
# Tests for AuthProvider Protocol, ClaudeCodeOAuthProvider, and the default chain.
# Author: Pierre Grothe
# Date: 2026-05-07

"""Tests for nexus.auth.providers and nexus.auth.oauth."""

from tests.fakes.fake_auth_provider import FakeAuthProvider


def test_fake_auth_provider_default_is_available() -> None:
    fake = FakeAuthProvider()
    assert fake.is_available() is True
    assert fake.name == "fake"


def test_fake_auth_provider_returns_configured_unavailability() -> None:
    fake = FakeAuthProvider(available=False)
    assert fake.is_available() is False
