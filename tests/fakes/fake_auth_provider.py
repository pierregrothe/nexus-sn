# tests/fakes/fake_auth_provider.py
# Test double for the AuthProvider Protocol.
# Author: Pierre Grothe
# Date: 2026-05-07

"""FakeAuthProvider: implements AuthProvider for unit tests."""

from dataclasses import dataclass

import anthropic

from nexus.auth.errors import AuthError

__all__ = ["FakeAuthProvider"]


@dataclass(slots=True)
class FakeAuthProvider:
    """Test double for AuthProvider Protocol.

    Configurable per-test:
      name: identifier returned as .name (default "fake")
      available: value returned by is_available() (default True)
      sdk_client: anthropic.Anthropic returned by create_client() (default None)
    """

    name: str = "fake"
    available: bool = True
    sdk_client: anthropic.Anthropic | None = None

    def is_available(self) -> bool:
        """Return the configured availability."""
        return self.available

    def create_client(self, max_retries: int) -> anthropic.Anthropic:
        """Return the configured SDK client or raise AuthError.

        Args:
            max_retries: Max retries to set on the SDK client.

        Returns:
            The configured anthropic.Anthropic instance.

        Raises:
            AuthError: If no sdk_client was configured.
        """
        if self.sdk_client is None:
            raise AuthError("fake", "client", "no sdk_client configured")
        return self.sdk_client
