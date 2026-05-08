# nexus/auth/__init__.py
# Authentication layer public exports.
# Author: Pierre Grothe
# Date: 2026-05-07

"""Credential storage and retrieval for NEXUS."""

from nexus.auth.claude import ClaudeAuth
from nexus.auth.errors import AuthError
from nexus.auth.external_keychain import ExternalKeychainClient
from nexus.auth.keychain import KeychainClient
from nexus.auth.servicenow import SNAuth

__all__ = [
    "AuthError",
    "ClaudeAuth",
    "ExternalKeychainClient",
    "KeychainClient",
    "SNAuth",
]
