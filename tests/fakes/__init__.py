# tests/fakes/__init__.py
# Fake implementations used in tests. No mocks anywhere.
# Author: Pierre Grothe
# Date: 2026-05-07

"""Fake connectors and clients for use in tests."""

from tests.fakes.fake_sn_client import FakeServiceNowClient
from tests.fakes.fake_keychain import FakeKeychainClient

__all__ = ["FakeServiceNowClient", "FakeKeychainClient"]
