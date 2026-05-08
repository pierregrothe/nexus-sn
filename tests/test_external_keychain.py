# tests/test_external_keychain.py
# Test for ExternalKeychainClient -- the wrapper that bypasses the "nexus" prefix.
# Author: Pierre Grothe
# Date: 2026-05-08
"""Tests for nexus.auth.external_keychain."""

from nexus.auth.external_keychain import ExternalKeychainClient
from nexus.auth.keychain import KeychainClient


def test_external_keychain_client_uses_empty_prefix() -> None:
    client = ExternalKeychainClient()
    assert client._prefix == ""


def test_external_keychain_client_is_a_keychain_client() -> None:
    """Verify subclass relationship for type checks at call sites."""
    client = ExternalKeychainClient()
    assert isinstance(client, KeychainClient)
