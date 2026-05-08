# src/nexus/capabilities/claude_config.py
# Reads Claude Code's local config to detect org-pushed MCP servers + tier.
# Author: Pierre Grothe
# Date: 2026-05-08
"""ClaudeCodeConfig: snapshot of Claude Code state relevant to NEXUS tier detection.

Reads three sources:
  1. OAuth payload (macOS Keychain -> ~/.claude/.credentials.json fallback)
     for the subscription_type claim.
  2. ~/.claude.json claudeAiMcpEverConnected list for org-pushed MCP servers.
  3. ~/.claude/mcp-needs-auth-cache.json for servers requiring re-authentication.
"""

import getpass
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

from nexus.auth.errors import AuthError
from nexus.auth.keychain import KeychainClient

log = logging.getLogger(__name__)

__all__ = ["ClaudeCodeConfig", "ClaudeCodeConfigReader", "FilesystemClaudeCodeConfigReader"]

_KEYCHAIN_SERVICE = "Claude Code-credentials"


@dataclass(slots=True, frozen=True)
class ClaudeCodeConfig:
    """Snapshot of Claude Code's local config relevant to capability detection.

    Attributes:
        subscription_type: The OAuth payload's subscriptionType field
            ("enterprise", "pro", "max", etc.). None when no Claude Code
            credentials are present.
        org_mcp_servers: Strings from claudeAiMcpEverConnected in ~/.claude.json,
            e.g. "claude.ai ValueMelody". Empty tuple when not authenticated.
        needs_reauth: Server-name strings from ~/.claude/mcp-needs-auth-cache.json
            that currently need user re-authentication.
    """

    subscription_type: str | None
    org_mcp_servers: tuple[str, ...]
    needs_reauth: tuple[str, ...]


class ClaudeCodeConfigReader(Protocol):
    """Reader interface for ClaudeCodeConfig."""

    def read(self) -> ClaudeCodeConfig:
        """Return the current Claude Code config snapshot.

        Implementations must never raise; missing or malformed sources
        should yield empty/None fields.
        """
        ...


class FilesystemClaudeCodeConfigReader:
    """Production reader: macOS Keychain + ~/.claude.json + needs-auth-cache.

    Cross-platform credential lookup:
      - macOS: keyring routes to Keychain Access
      - Linux/Windows: ~/.claude/.credentials.json file fallback

    Args:
        keychain: KeychainClient used to read the OAuth payload.
        home: Override the user's home directory. Defaults to Path.home().
            Tests pass tmp_path here.
        os_user: Override the OS username for keychain lookup. Defaults to
            getpass.getuser().
    """

    def __init__(
        self,
        *,
        keychain: KeychainClient,
        home: Path | None = None,
        os_user: str | None = None,
    ) -> None:
        """See class docstring."""
        self._keychain = keychain
        self._home = home if home is not None else Path.home()
        self._os_user = os_user if os_user is not None else getpass.getuser()

    def read(self) -> ClaudeCodeConfig:
        """Build a ClaudeCodeConfig from on-disk and keychain state."""
        return ClaudeCodeConfig(
            subscription_type=self._read_subscription_type(),
            org_mcp_servers=self._read_org_mcp_servers(),
            needs_reauth=self._read_needs_reauth(),
        )

    def _read_subscription_type(self) -> str | None:
        """Try keychain first, fall back to credentials file."""
        payload = self._read_keychain_payload() or self._read_credentials_file()
        if not payload:
            return None
        return _extract_subscription_type(payload)

    def _read_keychain_payload(self) -> str | None:
        """Read the raw OAuth payload string from the OS keychain.

        Returns None if no entry exists or if the lookup raises AuthError.
        """
        try:
            return self._keychain.get(_KEYCHAIN_SERVICE, self._os_user)
        except AuthError:
            return None

    def _read_credentials_file(self) -> str | None:
        """Read the raw OAuth payload from ~/.claude/.credentials.json.

        Returns None if the file does not exist or cannot be read.
        """
        creds_path = self._home / ".claude" / ".credentials.json"
        try:
            return creds_path.read_text(encoding="utf-8")
        except OSError:
            return None

    def _read_org_mcp_servers(self) -> tuple[str, ...]:
        """Read claudeAiMcpEverConnected from ~/.claude.json."""
        claude_json = self._home / ".claude.json"
        try:
            raw = claude_json.read_text(encoding="utf-8")
        except OSError:
            return ()
        data = _parse_json_object(raw, source="~/.claude.json")
        if data is None:
            return ()
        servers = data.get("claudeAiMcpEverConnected", [])
        if not isinstance(servers, list):
            log.warning("claudeAiMcpEverConnected is not a list; ignoring")
            return ()
        servers_list = cast("list[object]", servers)
        return tuple(s for s in servers_list if isinstance(s, str))

    def _read_needs_reauth(self) -> tuple[str, ...]:
        """Read keys of ~/.claude/mcp-needs-auth-cache.json."""
        cache_path = self._home / ".claude" / "mcp-needs-auth-cache.json"
        try:
            raw = cache_path.read_text(encoding="utf-8")
        except OSError:
            return ()
        data = _parse_json_object(raw, source="mcp-needs-auth-cache.json")
        if data is None:
            return ()
        return tuple(str(key) for key in data)


def _parse_json_object(raw: str, *, source: str) -> dict[str, object] | None:
    """Parse a JSON string and return it as a dict, or None on failure.

    Args:
        raw: JSON-encoded string.
        source: Human-readable source name used in WARNING logs.

    Returns:
        The parsed dict (with string keys, object values) or None when the
        payload is not valid JSON or is not a JSON object.
    """
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        log.warning("malformed %s; ignoring", source)
        return None
    if not isinstance(parsed, dict):
        log.warning("%s is not a JSON object; ignoring", source)
        return None
    return cast("dict[str, object]", parsed)


def _extract_subscription_type(payload: str) -> str | None:
    """Parse the OAuth payload string and return claudeAiOauth.subscriptionType.

    Returns None if the payload is malformed JSON or missing the field.
    """
    data = _parse_json_object(payload, source="Claude Code OAuth payload")
    if data is None:
        return None
    inner = data.get("claudeAiOauth")
    if not isinstance(inner, dict):
        return None
    inner_dict = cast("dict[str, object]", inner)
    sub = inner_dict.get("subscriptionType")
    return sub if isinstance(sub, str) else None
