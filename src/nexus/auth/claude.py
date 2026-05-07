# nexus/auth/claude.py
# Claude Enterprise API key storage as an AuthProvider implementation.
# Author: Pierre Grothe
# Date: 2026-05-07

"""ClaudeAuth: AnthropicAPIKeyProvider -- API-key-based auth provider."""

import logging
import os

import anthropic

from nexus.auth.errors import AuthError
from nexus.auth.keychain import KeychainClient

log = logging.getLogger(__name__)

__all__ = ["ClaudeAuth"]

_ENV_VAR = "NEXUS_CLAUDE_API_KEY"
_KEYCHAIN_SERVICE = "claude"
_KEYCHAIN_USERNAME = "api_key"


class ClaudeAuth:
    """API-key auth provider for the Anthropic API.

    Implements the AuthProvider Protocol structurally. Resolution order:
      1. NEXUS_CLAUDE_API_KEY environment variable (CI / scripted use)
      2. OS keychain under service "nexus-claude", username "api_key"

    Args:
        keychain: KeychainClient instance. Defaults to a standard client.
        org: Org slug used as a keychain label (informational only).
    """

    def __init__(self, keychain: KeychainClient | None = None, org: str = "servicenow") -> None:
        """Initialize with optional keychain and org slug."""
        self._keychain = keychain or KeychainClient()
        self._org = org

    @property
    def name(self) -> str:
        """AuthProvider identifier."""
        return "anthropic_api_key"

    def is_available(self) -> bool:
        """Return True if an API key is reachable in env or keychain."""
        return self.is_configured()

    def create_client(self, max_retries: int) -> anthropic.Anthropic:
        """Construct an Anthropic client authenticated with the API key.

        Args:
            max_retries: Max retries to set on the SDK client.

        Returns:
            anthropic.Anthropic instance using X-Api-Key authentication.
        """
        return anthropic.Anthropic(api_key=self.get_api_key(), max_retries=max_retries)

    def get_api_key(self) -> str:
        """Return the Claude API key.

        Returns:
            The API key string.

        Raises:
            AuthError: When no key is configured in env or keychain.
        """
        env_value = os.environ.get(_ENV_VAR)
        if env_value:
            log.debug("Claude API key loaded from environment variable")
            return env_value
        return self._keychain.get(_KEYCHAIN_SERVICE, _KEYCHAIN_USERNAME)

    def store_api_key(self, api_key: str) -> None:
        """Persist the API key in the OS keychain.

        Args:
            api_key: The API key to store. Never logged.
        """
        self._keychain.set(_KEYCHAIN_SERVICE, _KEYCHAIN_USERNAME, api_key)
        log.info("Claude API key stored in keychain for org=%s", self._org)

    def is_configured(self) -> bool:
        """Return True if an API key is available (env or keychain)."""
        if os.environ.get(_ENV_VAR):
            return True
        try:
            self._keychain.get(_KEYCHAIN_SERVICE, _KEYCHAIN_USERNAME)
            return True
        except AuthError:
            return False
