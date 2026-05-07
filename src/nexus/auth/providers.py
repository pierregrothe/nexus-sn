# src/nexus/auth/providers.py
# AuthProvider Protocol and default provider chain factory.
# Author: Pierre Grothe
# Date: 2026-05-07

"""AuthProvider: pluggable authentication backends for the Anthropic API.

Protocol defines the contract every auth backend must satisfy. The default
chain returned by get_default_providers() tries OAuth first (Claude Code's
stored credentials) and falls back to API key (env var or NEXUS keychain).
"""

from typing import Protocol

import anthropic

__all__ = ["AuthProvider"]


class AuthProvider(Protocol):
    """Auth backend that produces an authenticated anthropic.Anthropic client.

    NEXUS resolves auth at AnthropicClient init by iterating a list of
    providers and picking the first one whose is_available() returns True.
    Order matters -- the default chain tries OAuth before API key so Claude
    Code users get enterprise-account access without configuration.
    """

    @property
    def name(self) -> str:
        """Provider identifier (logged at AnthropicClient init)."""
        ...

    def is_available(self) -> bool:
        """Return True if this provider's credentials are present and usable.

        MUST NOT raise. MUST NOT make network calls. SHOULD complete in <50ms.
        """
        ...

    def create_client(self, max_retries: int) -> anthropic.Anthropic:
        """Construct the SDK client.

        Called only when is_available() returned True. May raise AuthError
        if credentials become unavailable between is_available and create_client.

        Args:
            max_retries: Max retries to set on the SDK client.

        Returns:
            An authenticated anthropic.Anthropic instance.
        """
        ...
