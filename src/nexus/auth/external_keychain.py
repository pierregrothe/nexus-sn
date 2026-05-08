# src/nexus/auth/external_keychain.py
# Keychain reader for credentials NOT owned by NEXUS (e.g., Claude Code).
# Author: Pierre Grothe
# Date: 2026-05-08
"""ExternalKeychainClient: read keychain entries that other apps own.

NEXUS-owned secrets use KeychainClient with the default service_prefix="nexus"
(so our keys live under "nexus-<service>"). Reading other apps' keychain
entries -- like Claude Code's "Claude Code-credentials" -- requires
service_prefix="" so the lookup uses the literal service name. This wrapper
makes that intent explicit at every call site and pairs with the
external-keychain Semgrep rule (ADR-019).
"""

from nexus.auth.keychain import KeychainClient

__all__ = ["ExternalKeychainClient"]


class ExternalKeychainClient(KeychainClient):
    """KeychainClient configured for reading external apps' credentials.

    Calls KeychainClient.__init__ with service_prefix="" so .get(service, user)
    reads the literal service name without the "nexus-" prefix. Use this for
    credentials owned by other apps (Claude Code, Anthropic CLI, etc.). For
    NEXUS-owned secrets, use KeychainClient() with the default prefix.
    """

    def __init__(self) -> None:
        """Initialize with empty service prefix."""
        super().__init__(service_prefix="")
