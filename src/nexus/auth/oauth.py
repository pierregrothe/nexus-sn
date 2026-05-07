# nexus/auth/oauth.py
# Claude Code OAuth credential reader.
# Author: Pierre Grothe
# Date: 2026-05-07

"""ClaudeCodeOAuthProvider: read OAuth token from Claude Code's stored credentials.

Resolution order:
  1. CLAUDE_CODE_OAUTH_TOKEN environment variable
  2. $CLAUDE_CONFIG_DIR/.credentials.json (or ~/.claude/.credentials.json)
     -- parses JSON, extracts claudeAiOauth.accessToken
  3. macOS Keychain service "Claude Code-credentials" (Darwin only)
"""

import json
import logging
import os
import platform
from pathlib import Path
from typing import ClassVar, cast

import anthropic
import keyring
import keyring.errors

from nexus.auth.errors import AuthError

log = logging.getLogger(__name__)

__all__ = ["ClaudeCodeOAuthProvider"]

_OAUTH_ENV_VAR = "CLAUDE_CODE_OAUTH_TOKEN"
_CREDENTIALS_FILENAME = ".credentials.json"
_KEYCHAIN_SERVICE = "Claude Code-credentials"


class ClaudeCodeOAuthProvider:
    """Auth provider that reads Claude Code's stored OAuth tokens."""

    _UNSET: ClassVar[object] = object()

    def __init__(self) -> None:
        """Initialize with no cached token."""
        self._cached: object = self._UNSET

    @property
    def name(self) -> str:
        """AuthProvider identifier."""
        return "claude_code_oauth"

    def is_available(self) -> bool:
        """Return True if an OAuth token is reachable in any source."""
        return self._resolve_token() is not None

    def create_client(self, max_retries: int) -> anthropic.Anthropic:
        """Construct an Anthropic client using Bearer auth with the OAuth token.

        Args:
            max_retries: Max retries to set on the SDK client.

        Returns:
            anthropic.Anthropic instance using Authorization: Bearer auth.

        Raises:
            AuthError: When no token is found in any source.
        """
        token = self._resolve_token()
        if token is None:
            raise AuthError(
                "claude_code_oauth",
                "access_token",
                "OAuth token not found. Run 'claude login' to authenticate.",
            )
        return anthropic.Anthropic(auth_token=token, max_retries=max_retries)

    def _resolve_token(self) -> str | None:
        """Return the OAuth token, trying env -> file -> Keychain in order.

        Cached on first call so repeated is_available() / create_client() calls
        do not re-walk the source chain.
        """
        if self._cached is self._UNSET:
            self._cached = (
                self._read_token_from_env()
                or self._read_token_from_file()
                or self._read_token_from_keychain()
            )
        return cast(str | None, self._cached)

    def _read_token_from_env(self) -> str | None:
        """Return token from CLAUDE_CODE_OAUTH_TOKEN env var, if set."""
        return os.environ.get(_OAUTH_ENV_VAR) or None

    def _read_token_from_file(self) -> str | None:
        """Return access token from .credentials.json, or None if missing/malformed."""
        creds_path = self._config_dir() / _CREDENTIALS_FILENAME
        try:
            content = creds_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        except OSError as exc:
            log.warning("could not read %s: %s", creds_path, exc)
            return None
        return self._parse_token_from_credentials_json(content)

    def _read_token_from_keychain(self) -> str | None:
        """Return token from macOS Keychain (Darwin only), or None.

        Note: bypasses KeychainClient because Claude Code stores credentials
        under service "Claude Code-credentials" (not under the "nexus-" prefix
        that KeychainClient adds).
        """
        if platform.system() != "Darwin":
            return None
        user = os.environ.get("USER", "")
        if not user:
            return None
        try:
            creds_json = keyring.get_password(_KEYCHAIN_SERVICE, user)
        except keyring.errors.KeyringError as exc:
            log.warning("could not read macOS Keychain: %s", exc)
            return None
        if not creds_json:
            return None
        return self._parse_token_from_credentials_json(creds_json)

    @staticmethod
    def _config_dir() -> Path:
        """Resolve Claude Code config directory ($CLAUDE_CONFIG_DIR or ~/.claude)."""
        custom = os.environ.get("CLAUDE_CONFIG_DIR")
        return Path(custom) if custom else Path.home() / ".claude"

    @staticmethod
    def _parse_token_from_credentials_json(creds_json: str) -> str | None:
        """Extract claudeAiOauth.accessToken from a credentials JSON string."""
        if not creds_json:
            return None
        try:
            raw = json.loads(creds_json)
        except json.JSONDecodeError:
            return None
        if not isinstance(raw, dict):
            return None
        data = cast("dict[str, object]", raw)
        oauth = data.get("claudeAiOauth")
        if not isinstance(oauth, dict):
            return None
        creds = cast("dict[str, object]", oauth)
        token = creds.get("accessToken")
        return token if isinstance(token, str) and token else None
