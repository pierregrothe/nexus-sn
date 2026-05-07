# Pluggable AuthProvider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `AnthropicClient(api_key: str, ...)` with `AnthropicClient(auth_providers: Sequence[AuthProvider], ...)` so users authenticate via Claude Code OAuth (env, file, or macOS Keychain) when available, and fall back to API key otherwise.

**Architecture:** AuthProvider Protocol with two initial implementations -- `ClaudeCodeOAuthProvider` (OAuth) and `AnthropicAPIKeyProvider` (refactored ClaudeAuth). Default chain tries OAuth first. AnthropicClient resolves the first available provider at init and constructs the underlying anthropic SDK client via the provider's `create_client()` method.

**Tech Stack:** Python 3.14, anthropic SDK (uses `auth_token=` for OAuth Bearer auth), structural Protocol typing, no new dependencies.

---

## File Map

```
Create:  src/nexus/auth/providers.py     -- AuthProvider Protocol + factory
Create:  src/nexus/auth/oauth.py         -- ClaudeCodeOAuthProvider
Create:  tests/fakes/fake_auth_provider.py -- FakeAuthProvider test double
Create:  tests/test_auth_providers.py    -- new tests for providers + oauth
Modify:  src/nexus/auth/claude.py        -- ClaudeAuth implements AuthProvider
Modify:  src/nexus/auth/__init__.py      -- export new types
Modify:  tests/fakes/__init__.py         -- export FakeAuthProvider
Modify:  src/nexus/api/client.py         -- AnthropicClient takes auth_providers
Modify:  tests/test_api_client.py        -- tests use FakeAuthProvider injection
Modify:  scripts/smoke_anthropic.py      -- uses get_default_providers()
Modify:  .ratchet.json                   -- baseline for new modules
```

---

## Task 1: AuthProvider Protocol + FakeAuthProvider

**Files:**
- Create: `src/nexus/auth/providers.py`
- Create: `tests/fakes/fake_auth_provider.py`
- Modify: `tests/fakes/__init__.py`

This task lays the foundation: the Protocol that all providers implement and the test double that satisfies it for unit tests. No real auth logic yet.

- [ ] **Step 1: Write a failing test for FakeAuthProvider**

Create `tests/test_auth_providers.py`:

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
.venv/bin/pytest tests/test_auth_providers.py -v
```

Expected: `ModuleNotFoundError: No module named 'tests.fakes.fake_auth_provider'`

- [ ] **Step 3: Create FakeAuthProvider**

Write `tests/fakes/fake_auth_provider.py`:

```python
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
        """Return the configured SDK client or raise AuthError."""
        if self.sdk_client is None:
            raise AuthError("fake", "client", "no sdk_client configured")
        return self.sdk_client
```

- [ ] **Step 4: Add FakeAuthProvider to tests/fakes/__init__.py**

Replace the file content:

```python
# tests/fakes/__init__.py
# Fake implementations used in tests. No mocks anywhere.
# Author: Pierre Grothe
# Date: 2026-05-07
"""Fake connectors and clients for use in tests."""

from tests.fakes.fake_anthropic_client import FakeAnthropicClient
from tests.fakes.fake_auth_provider import FakeAuthProvider
from tests.fakes.fake_keychain import FakeKeychainClient
from tests.fakes.fake_sn_client import FakeServiceNowClient

__all__ = ["FakeAnthropicClient", "FakeAuthProvider", "FakeKeychainClient", "FakeServiceNowClient"]
```

- [ ] **Step 5: Create the AuthProvider Protocol**

Write `src/nexus/auth/providers.py`:

```python
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

    def is_available(self) -> bool:
        """Return True if this provider's credentials are present and usable.

        MUST NOT raise. MUST NOT make network calls. SHOULD complete in <50ms.
        """

    def create_client(self, max_retries: int) -> anthropic.Anthropic:
        """Construct the SDK client.

        Called only when is_available() returned True. May raise AuthError
        if credentials become unavailable between is_available and create_client.

        Args:
            max_retries: Max retries to set on the SDK client.

        Returns:
            An authenticated anthropic.Anthropic instance.
        """
```

Note: `get_default_providers()` is added in Task 4 once the concrete providers exist.

- [ ] **Step 6: Verify the test passes**

```bash
.venv/bin/pytest tests/test_auth_providers.py -v
```

Expected: 2 passed.

- [ ] **Step 7: Run lint + type checks**

```bash
.venv/bin/ruff check src/nexus/auth/providers.py tests/fakes/fake_auth_provider.py tests/fakes/__init__.py tests/test_auth_providers.py
.venv/bin/mypy src/nexus/auth/providers.py
.venv/bin/pyright src/nexus/auth/providers.py tests/fakes/fake_auth_provider.py
```

Expected: 0 violations, 0 errors from each.

- [ ] **Step 8: Commit**

```bash
git add src/nexus/auth/providers.py tests/fakes/fake_auth_provider.py tests/fakes/__init__.py tests/test_auth_providers.py
git commit -m "feat: add AuthProvider Protocol and FakeAuthProvider test double"
```

---

## Task 2: Refactor ClaudeAuth to implement AuthProvider

**Files:**
- Modify: `src/nexus/auth/claude.py`

ClaudeAuth becomes the concrete `AnthropicAPIKeyProvider`. Add Protocol methods (`name`, `is_available`, `create_client`) while keeping existing public methods (`get_api_key`, `store_api_key`, `is_configured`) for backward compatibility.

- [ ] **Step 1: Append a Protocol-conformance test**

Append to `tests/test_auth.py` after the last test:

```python


def test_claude_auth_implements_auth_provider_name() -> None:
    auth = ClaudeAuth(keychain=FakeKeychainClient())
    assert auth.name == "anthropic_api_key"


def test_claude_auth_is_available_matches_is_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NEXUS_CLAUDE_API_KEY", raising=False)
    keychain = FakeKeychainClient({("nexus-claude", "api_key"): "sk-test"})
    auth = ClaudeAuth(keychain=keychain)
    assert auth.is_available() is True
    assert auth.is_available() == auth.is_configured()


def test_claude_auth_create_client_returns_anthropic_with_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NEXUS_CLAUDE_API_KEY", "sk-test-create")
    auth = ClaudeAuth(keychain=FakeKeychainClient())
    client = auth.create_client(max_retries=3)
    assert client.api_key == "sk-test-create"
    assert client.auth_token is None
```

- [ ] **Step 2: Run tests to verify failure**

```bash
.venv/bin/pytest tests/test_auth.py -v -k "implements_auth_provider or is_available_matches or create_client_returns_anthropic"
```

Expected: 3 errors (ClaudeAuth has no `name`, `is_available`, or `create_client`).

- [ ] **Step 3: Update ClaudeAuth with Protocol methods**

Replace the contents of `src/nexus/auth/claude.py`:

```python
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
```

- [ ] **Step 4: Run all auth tests**

```bash
.venv/bin/pytest tests/test_auth.py -v
```

Expected: 15 passed (12 original + 3 new).

- [ ] **Step 5: Run lint + type checks**

```bash
.venv/bin/ruff check src/nexus/auth/claude.py
.venv/bin/mypy src/nexus/auth/claude.py
.venv/bin/pyright src/nexus/auth/claude.py
```

Expected: 0 violations, 0 errors.

- [ ] **Step 6: Commit**

```bash
git add src/nexus/auth/claude.py tests/test_auth.py
git commit -m "feat: ClaudeAuth implements AuthProvider Protocol (name, is_available, create_client)"
```

---

## Task 3: ClaudeCodeOAuthProvider

**Files:**
- Create: `src/nexus/auth/oauth.py`
- Modify: `tests/test_auth_providers.py` (append tests)

The big task. Reads OAuth tokens from three sources in priority order: env var, credentials file, macOS Keychain. Returns `Anthropic(auth_token=...)`.

- [ ] **Step 1: Append OAuth provider tests**

Add to `tests/test_auth_providers.py` (after existing FakeAuthProvider tests):

```python
import json
from pathlib import Path

import pytest

from nexus.auth.oauth import ClaudeCodeOAuthProvider


def _write_credentials(path: Path, access_token: str) -> None:
    """Write a credentials.json file at path with the given accessToken."""
    creds = {"claudeAiOauth": {"accessToken": access_token, "refreshToken": "ref-xyz"}}
    path.write_text(json.dumps(creds), encoding="utf-8")


def test_oauth_provider_name_is_claude_code_oauth() -> None:
    assert ClaudeCodeOAuthProvider().name == "claude_code_oauth"


def test_oauth_provider_is_available_true_with_env_var(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "tok-from-env")
    assert ClaudeCodeOAuthProvider().is_available() is True


def test_oauth_provider_is_available_true_with_credentials_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    _write_credentials(tmp_path / ".credentials.json", "tok-from-file")
    assert ClaudeCodeOAuthProvider().is_available() is True


def test_oauth_provider_is_available_false_when_nothing_present(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    assert ClaudeCodeOAuthProvider().is_available() is False


def test_oauth_provider_is_available_false_when_credentials_file_malformed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    (tmp_path / ".credentials.json").write_text("not json", encoding="utf-8")
    assert ClaudeCodeOAuthProvider().is_available() is False


def test_oauth_provider_create_client_uses_auth_token_from_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "tok-from-env")
    client = ClaudeCodeOAuthProvider().create_client(max_retries=3)
    assert client.auth_token == "tok-from-env"
    assert client.api_key is None


def test_oauth_provider_create_client_uses_auth_token_from_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    _write_credentials(tmp_path / ".credentials.json", "tok-from-file")
    client = ClaudeCodeOAuthProvider().create_client(max_retries=3)
    assert client.auth_token == "tok-from-file"


def test_oauth_provider_priority_env_over_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "tok-from-env")
    _write_credentials(tmp_path / ".credentials.json", "tok-from-file")
    client = ClaudeCodeOAuthProvider().create_client(max_retries=3)
    assert client.auth_token == "tok-from-env"


def test_oauth_provider_create_client_raises_when_no_token() -> None:
    from nexus.auth.errors import AuthError
    provider = ClaudeCodeOAuthProvider()
    # Force all sources empty: redirect config dir + clear env var
    import os
    saved_env = os.environ.pop("CLAUDE_CODE_OAUTH_TOKEN", None)
    saved_dir = os.environ.pop("CLAUDE_CONFIG_DIR", None)
    os.environ["CLAUDE_CONFIG_DIR"] = "/nonexistent-path-for-test"
    try:
        with pytest.raises(AuthError):
            provider.create_client(max_retries=3)
    finally:
        os.environ.pop("CLAUDE_CONFIG_DIR", None)
        if saved_env is not None:
            os.environ["CLAUDE_CODE_OAUTH_TOKEN"] = saved_env
        if saved_dir is not None:
            os.environ["CLAUDE_CONFIG_DIR"] = saved_dir
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/test_auth_providers.py -v -k "oauth"
```

Expected: 8 errors -- `ModuleNotFoundError: No module named 'nexus.auth.oauth'`.

- [ ] **Step 3: Create ClaudeCodeOAuthProvider**

Write `src/nexus/auth/oauth.py`:

```python
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
import subprocess
from pathlib import Path

import anthropic

from nexus.auth.errors import AuthError

log = logging.getLogger(__name__)

__all__ = ["ClaudeCodeOAuthProvider"]

_OAUTH_ENV_VAR = "CLAUDE_CODE_OAUTH_TOKEN"
_CREDENTIALS_FILENAME = ".credentials.json"
_KEYCHAIN_SERVICE = "Claude Code-credentials"
_KEYCHAIN_TIMEOUT_SECONDS = 5.0


class ClaudeCodeOAuthProvider:
    """Auth provider that reads Claude Code's stored OAuth tokens."""

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
        """Return the OAuth token, trying env -> file -> Keychain in order."""
        return (
            self._read_token_from_env()
            or self._read_token_from_file()
            or self._read_token_from_keychain()
        )

    def _read_token_from_env(self) -> str | None:
        """Return token from CLAUDE_CODE_OAUTH_TOKEN env var, if set."""
        return os.environ.get(_OAUTH_ENV_VAR) or None

    def _read_token_from_file(self) -> str | None:
        """Return access token from .credentials.json, or None if missing/malformed."""
        creds_path = self._config_dir() / _CREDENTIALS_FILENAME
        if not creds_path.exists():
            return None
        try:
            content = creds_path.read_text(encoding="utf-8")
        except OSError as exc:
            log.warning("could not read %s: %s", creds_path, exc)
            return None
        return self._parse_token_from_credentials_json(content)

    def _read_token_from_keychain(self) -> str | None:
        """Return token from macOS Keychain (Darwin only), or None."""
        if platform.system() != "Darwin":
            return None
        user = os.environ.get("USER", "")
        if not user:
            return None
        try:
            result = subprocess.run(
                [
                    "security",
                    "find-generic-password",
                    "-a", user,
                    "-w",
                    "-s", _KEYCHAIN_SERVICE,
                ],
                capture_output=True,
                text=True,
                timeout=_KEYCHAIN_TIMEOUT_SECONDS,
                check=False,
            )
        except (subprocess.SubprocessError, OSError) as exc:
            log.warning("could not read macOS Keychain: %s", exc)
            return None
        if result.returncode != 0:
            return None
        return self._parse_token_from_credentials_json(result.stdout.strip())

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
            data = json.loads(creds_json)
        except json.JSONDecodeError:
            return None
        oauth = data.get("claudeAiOauth") if isinstance(data, dict) else None
        if not isinstance(oauth, dict):
            return None
        token = oauth.get("accessToken")
        return token if isinstance(token, str) and token else None
```

- [ ] **Step 4: Run the OAuth tests**

```bash
.venv/bin/pytest tests/test_auth_providers.py -v -k "oauth"
```

Expected: 9 passed.

- [ ] **Step 5: Run lint + type checks**

```bash
.venv/bin/ruff check src/nexus/auth/oauth.py tests/test_auth_providers.py
.venv/bin/mypy src/nexus/auth/oauth.py
.venv/bin/pyright src/nexus/auth/oauth.py
```

Expected: 0 violations, 0 errors.

- [ ] **Step 6: Commit**

```bash
git add src/nexus/auth/oauth.py tests/test_auth_providers.py
git commit -m "feat: add ClaudeCodeOAuthProvider (env, file, macOS Keychain sources)"
```

---

## Task 4: get_default_providers() factory

**Files:**
- Modify: `src/nexus/auth/providers.py`
- Modify: `tests/test_auth_providers.py` (append tests)

Add the factory function and export the concrete provider names. Verifies the chain ordering and resolution behavior.

- [ ] **Step 1: Append factory tests**

Append to `tests/test_auth_providers.py`:

```python


def test_default_providers_returns_two_providers_oauth_first() -> None:
    from nexus.auth.providers import get_default_providers

    providers = get_default_providers()

    assert len(providers) == 2
    assert providers[0].name == "claude_code_oauth"
    assert providers[1].name == "anthropic_api_key"


def test_anthropic_api_key_provider_alias_is_claude_auth() -> None:
    from nexus.auth.claude import ClaudeAuth
    from nexus.auth.providers import AnthropicAPIKeyProvider

    assert AnthropicAPIKeyProvider is ClaudeAuth
```

- [ ] **Step 2: Run tests to verify failure**

```bash
.venv/bin/pytest tests/test_auth_providers.py -v -k "default_providers or anthropic_api_key_provider_alias"
```

Expected: 2 errors -- `ImportError: cannot import name 'get_default_providers'` and `'AnthropicAPIKeyProvider'`.

- [ ] **Step 3: Update providers.py**

Replace the contents of `src/nexus/auth/providers.py`:

```python
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

from nexus.auth.claude import ClaudeAuth
from nexus.auth.oauth import ClaudeCodeOAuthProvider

__all__ = [
    "AnthropicAPIKeyProvider",
    "AuthProvider",
    "ClaudeCodeOAuthProvider",
    "get_default_providers",
]

# Alias for clarity in type hints and docs. ClaudeAuth implements AuthProvider
# structurally; the alias makes its role in the provider chain explicit.
AnthropicAPIKeyProvider = ClaudeAuth


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

    def is_available(self) -> bool:
        """Return True if this provider's credentials are present and usable.

        MUST NOT raise. MUST NOT make network calls. SHOULD complete in <50ms.
        """

    def create_client(self, max_retries: int) -> anthropic.Anthropic:
        """Construct the SDK client.

        Called only when is_available() returned True. May raise AuthError
        if credentials become unavailable between is_available and create_client.

        Args:
            max_retries: Max retries to set on the SDK client.

        Returns:
            An authenticated anthropic.Anthropic instance.
        """


def get_default_providers() -> list[AuthProvider]:
    """Return the default provider chain in priority order.

    Returns:
        Two-element list: [ClaudeCodeOAuthProvider, AnthropicAPIKeyProvider].
        OAuth tried first (gives access to enterprise MCP servers tied to the
        Claude account); API key second (fallback for users without Claude Code).
    """
    return [ClaudeCodeOAuthProvider(), AnthropicAPIKeyProvider()]
```

- [ ] **Step 4: Run all auth_providers tests**

```bash
.venv/bin/pytest tests/test_auth_providers.py -v
```

Expected: 13 passed (2 from Task 1 + 9 from Task 3 + 2 new).

- [ ] **Step 5: Run lint + type checks**

```bash
.venv/bin/ruff check src/nexus/auth/providers.py
.venv/bin/mypy src/nexus/auth/providers.py
.venv/bin/pyright src/nexus/auth/providers.py
```

Expected: 0 violations, 0 errors.

- [ ] **Step 6: Commit**

```bash
git add src/nexus/auth/providers.py tests/test_auth_providers.py
git commit -m "feat: add get_default_providers() factory and AnthropicAPIKeyProvider alias"
```

---

## Task 5: Update AnthropicClient signature

**Files:**
- Modify: `src/nexus/api/client.py`
- Modify: `tests/test_api_client.py`

Replace `api_key: str` with `auth_providers: Sequence[AuthProvider]`. Resolve at init by picking the first available provider. Update all existing tests to use `FakeAuthProvider`.

- [ ] **Step 1: Update test_api_client.py imports and helpers**

Find this section in `tests/test_api_client.py`:

```python
from nexus.api.errors import AnthropicError
from nexus.api.logging_config import configure_logging
from nexus.auth.errors import AuthError
from nexus.capabilities.registry import CapabilitySet
```

Add import after the auth.errors line:

```python
from nexus.auth.errors import AuthError
from nexus.auth.providers import AuthProvider
from nexus.capabilities.registry import CapabilitySet
```

Find `_make_client` helper:

```python
def _make_client(messages_fake: _FakeSdkMessages) -> AnthropicClient:
    """Construct AnthropicClient with injected FakeSdk (empty model list -> fallback)."""
    return AnthropicClient(
        api_key="test-key",
        capabilities=CapabilitySet.none(),
        _sdk_client=_FakeSdk(messages=messages_fake),
    )
```

Replace it with:

```python
def _make_client(messages_fake: _FakeSdkMessages) -> AnthropicClient:
    """Construct AnthropicClient with injected FakeSdk (empty model list -> fallback)."""
    return AnthropicClient(
        auth_providers=[],
        capabilities=CapabilitySet.none(),
        _sdk_client=_FakeSdk(messages=messages_fake),
    )
```

(`auth_providers=[]` is fine because `_sdk_client` is injected -- the resolution loop is skipped.)

- [ ] **Step 2: Add new resolution-logic tests**

Append to `tests/test_api_client.py`:

```python


def test_anthropic_client_picks_first_available_provider(
    caplog: pytest.LogCaptureFixture,
) -> None:
    fake_messages = _FakeSdkMessages(response=_CANNED_RESPONSE)
    fake_sdk = _FakeSdk(messages=fake_messages)
    providers: list[AuthProvider] = [
        FakeAuthProvider(name="oauth", available=False),
        FakeAuthProvider(name="api_key", available=True, sdk_client=fake_sdk),
    ]
    with caplog.at_level(logging.INFO, logger="nexus.api.client"):
        AnthropicClient(
            auth_providers=providers,
            capabilities=CapabilitySet.none(),
        )
    assert "provider=api_key" in caplog.text


def test_anthropic_client_raises_auth_error_when_no_provider_available() -> None:
    providers: list[AuthProvider] = [
        FakeAuthProvider(name="oauth", available=False),
        FakeAuthProvider(name="api_key", available=False),
    ]
    with pytest.raises(AuthError):
        AnthropicClient(
            auth_providers=providers,
            capabilities=CapabilitySet.none(),
        )
```

The `FakeAuthProvider` import should already be picked up via the existing `from tests.fakes.fake_anthropic_client import ...` line; if not, add `from tests.fakes.fake_auth_provider import FakeAuthProvider`.

- [ ] **Step 3: Run tests to verify failures**

```bash
.venv/bin/pytest tests/test_api_client.py -v 2>&1 | tail -25
```

Expected: many failures because `AnthropicClient(api_key=...)` no longer accepts that kwarg, and the resolution-logic tests reference behavior not yet implemented.

- [ ] **Step 4: Update AnthropicClient.__init__**

In `src/nexus/api/client.py`:

Update the existing `from collections.abc import Iterable` line to add Sequence:

```python
# Before:
from collections.abc import Iterable
# After:
from collections.abc import Iterable, Sequence
```

Find the imports section and add (alphabetical order):

```python
from nexus.api.errors import AnthropicError
from nexus.auth.errors import AuthError
from nexus.capabilities.registry import CapabilitySet
```

becomes

```python
from nexus.api.errors import AnthropicError
from nexus.auth.errors import AuthError
from nexus.auth.providers import AuthProvider
from nexus.capabilities.registry import CapabilitySet
```

Replace the `AnthropicClient` class docstring and `__init__`:

```python
class AnthropicClient:
    """Anthropic API wrapper with prompt caching and capability-aware tools.

    Args:
        auth_providers: Ordered list of AuthProvider instances. The first one
            whose is_available() returns True is used to construct the SDK
            client. Pass get_default_providers() for the standard chain.
        capabilities: Session capability set from startup probe.
        tier: Model capability tier (default STANDARD).
        _sdk_client: Injectable anthropic.Anthropic instance (tests only).
            When provided, auth_providers is ignored.
    """

    def __init__(
        self,
        auth_providers: Sequence[AuthProvider],
        capabilities: CapabilitySet,
        tier: ModelTier = ModelTier.STANDARD,
        _sdk_client: anthropic.Anthropic | None = None,
    ) -> None:
        """Initialize with auth providers, capabilities, and model tier."""
        if _sdk_client is not None:
            self._client = _sdk_client
            provider_name = "injected"
        else:
            self._client, provider_name = self._resolve_auth(auth_providers)
        self._capabilities = capabilities
        self._model = _discover_model(self._client, tier)
        log.info(
            "AnthropicClient initialised: provider=%s tier=%s model=%s",
            provider_name, tier, self._model,
        )

    @staticmethod
    def _resolve_auth(
        auth_providers: Sequence[AuthProvider],
    ) -> tuple[anthropic.Anthropic, str]:
        """Pick the first available provider and create its SDK client.

        Args:
            auth_providers: Ordered provider chain.

        Returns:
            Tuple of (sdk_client, provider_name).

        Raises:
            AuthError: When no provider is available.
        """
        for provider in auth_providers:
            if provider.is_available():
                return provider.create_client(_MAX_RETRIES), provider.name
        raise AuthError(
            "anthropic",
            "auth_providers",
            "No auth provider available. Run 'nexus setup' or "
            "ensure Claude Code is authenticated.",
        )
```

- [ ] **Step 5: Run all api_client tests**

```bash
.venv/bin/pytest tests/test_api_client.py -v 2>&1 | tail -20
```

Expected: all tests pass (existing 14 + 2 new = 16).

- [ ] **Step 6: Run lint + type checks on changed files**

```bash
.venv/bin/ruff check src/nexus/api/client.py tests/test_api_client.py
.venv/bin/mypy src/nexus/api/client.py
.venv/bin/pyright src/nexus/api/client.py tests/test_api_client.py
```

Expected: 0 violations, 0 errors.

- [ ] **Step 7: Commit**

```bash
git add src/nexus/api/client.py tests/test_api_client.py
git commit -m "feat: AnthropicClient takes auth_providers Sequence (was api_key str)"
```

---

## Task 6: Update auth/__init__.py exports + smoke script

**Files:**
- Modify: `src/nexus/auth/__init__.py`
- Modify: `scripts/smoke_anthropic.py`

Wire the new types into the package's public API and update the smoke test to use the default provider chain.

- [ ] **Step 1: Update auth/__init__.py**

Replace the contents of `src/nexus/auth/__init__.py`:

```python
# nexus/auth/__init__.py
# Authentication layer public exports.
# Author: Pierre Grothe
# Date: 2026-05-07

"""Credential storage and retrieval for NEXUS."""

from nexus.auth.claude import ClaudeAuth
from nexus.auth.errors import AuthError
from nexus.auth.keychain import KeychainClient
from nexus.auth.oauth import ClaudeCodeOAuthProvider
from nexus.auth.providers import (
    AnthropicAPIKeyProvider,
    AuthProvider,
    get_default_providers,
)
from nexus.auth.servicenow import SNAuth

__all__ = [
    "AnthropicAPIKeyProvider",
    "AuthError",
    "AuthProvider",
    "ClaudeAuth",
    "ClaudeCodeOAuthProvider",
    "KeychainClient",
    "SNAuth",
    "get_default_providers",
]
```

- [ ] **Step 2: Update smoke_anthropic.py**

Replace the contents of `scripts/smoke_anthropic.py`:

```python
# scripts/smoke_anthropic.py
# Manual smoke test for AnthropicClient against the real Anthropic API.
# Author: Pierre Grothe
# Date: 2026-05-07

"""End-to-end smoke test for AnthropicClient with default auth providers.

Run with:
    .venv/bin/python scripts/smoke_anthropic.py

Picks up auth automatically:
  - ClaudeCodeOAuthProvider (uses ~/.claude/.credentials.json or Keychain)
  - AnthropicAPIKeyProvider (uses NEXUS_CLAUDE_API_KEY or nexus keychain)

Validates:
  1. Default provider chain resolves to an authenticated client
  2. AnthropicClient auto-discovers the newest Sonnet via models.list()
  3. complete() makes a real API call with prompt caching on system prompt
  4. Two consecutive calls with the same system prompt produce cache_read > 0
"""

import logging
import sys

from nexus.api.client import AnthropicClient, ModelTier
from nexus.auth.errors import AuthError
from nexus.auth.providers import get_default_providers
from nexus.capabilities.registry import CapabilitySet


def main() -> int:
    """Run the smoke test and return an exit code."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s -- %(message)s",
    )

    try:
        client = AnthropicClient(
            auth_providers=get_default_providers(),
            capabilities=CapabilitySet.none(),
            tier=ModelTier.STANDARD,
        )
    except AuthError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        print(
            "\nEnsure one of the following:\n"
            "  - Claude Code is authenticated ('claude login')\n"
            "  - CLAUDE_CODE_OAUTH_TOKEN env var is set\n"
            "  - NEXUS_CLAUDE_API_KEY env var is set\n"
            "  - API key is in keychain (service='nexus-claude', user='api_key')",
            file=sys.stderr,
        )
        return 1

    system_prompt = (
        "You are a terse assistant. Answer in one short sentence. "
        "If asked about NEXUS, say it is a ServiceNow AI architect tool."
    )

    msg1 = client.complete(
        messages=[{"role": "user", "content": "What is NEXUS?"}],
        system=system_prompt,
        max_tokens=200,
    )
    print("\n--- Response 1 ---")
    for block in msg1.content:
        if block.type == "text":
            print(block.text)
    print(
        f"usage: in={msg1.usage.input_tokens} out={msg1.usage.output_tokens} "
        f"cache_write={getattr(msg1.usage, 'cache_creation_input_tokens', 0)} "
        f"cache_read={getattr(msg1.usage, 'cache_read_input_tokens', 0)}"
    )

    msg2 = client.complete(
        messages=[{"role": "user", "content": "What is the capital of France?"}],
        system=system_prompt,
        max_tokens=200,
    )
    print("\n--- Response 2 ---")
    for block in msg2.content:
        if block.type == "text":
            print(block.text)
    print(
        f"usage: in={msg2.usage.input_tokens} out={msg2.usage.output_tokens} "
        f"cache_write={getattr(msg2.usage, 'cache_creation_input_tokens', 0)} "
        f"cache_read={getattr(msg2.usage, 'cache_read_input_tokens', 0)}"
    )

    cache_read_2 = getattr(msg2.usage, "cache_read_input_tokens", 0)
    if cache_read_2 > 0:
        print(f"\nSUCCESS: prompt caching working (call 2 read {cache_read_2} cached tokens).")
    else:
        print(
            "\nWARNING: cache_read_input_tokens = 0 on second call. "
            "Prompt caching may not be enabled, or system prompt is too short."
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Run all tests to confirm nothing broke**

```bash
.venv/bin/pytest -q --override-ini="addopts=" 2>&1 | tail -3
```

Expected: 70 passed (53 original + 13 from test_auth_providers + 2 new in test_api_client + 3 new in test_auth -- actual count may vary; verify all pass).

- [ ] **Step 4: Run lint + type checks on changed files**

```bash
.venv/bin/ruff check src/nexus/auth/__init__.py scripts/smoke_anthropic.py
.venv/bin/mypy src/nexus/auth/__init__.py scripts/smoke_anthropic.py
.venv/bin/pyright src/nexus/auth/__init__.py scripts/smoke_anthropic.py
```

Expected: 0 violations, 0 errors.

- [ ] **Step 5: Commit**

```bash
git add src/nexus/auth/__init__.py scripts/smoke_anthropic.py
git commit -m "feat: export AuthProvider types from auth/, smoke test uses default chain"
```

---

## Task 7: Update .ratchet.json + final verification + push

**Files:**
- Modify: `.ratchet.json`

Add coverage baselines for the new modules. Run final full suite + pre-commit. Push the branch.

- [ ] **Step 1: Get per-module coverage for new modules**

```bash
.venv/bin/pytest --cov=nexus.auth.providers --cov=nexus.auth.oauth --cov=nexus.auth.claude --cov-report=term --cov-fail-under=0 -q 2>&1 | grep -E "auth/(providers|oauth|claude)\.py"
```

Note the covered/total lines for each module.

- [ ] **Step 2: Update .ratchet.json**

Read the current `.ratchet.json`. Add three new entries to the `modules` map (or update `nexus.auth.claude` if it changed):

```json
"nexus.auth.providers": {"covered_lines": <covered>, "total_lines": <total>},
"nexus.auth.oauth": {"covered_lines": <covered>, "total_lines": <total>},
```

For `nexus.auth.claude`, update with the new totals (it grew with the AuthProvider methods).

Example (replace numbers with actuals from Step 1):

```json
"nexus.auth.claude": {"covered_lines": 35, "total_lines": 38},
"nexus.auth.oauth": {"covered_lines": 50, "total_lines": 52},
"nexus.auth.providers": {"covered_lines": 8, "total_lines": 8},
```

- [ ] **Step 3: Run pre-commit (matches CI lint stage)**

```bash
.venv/bin/pre-commit run --all-files 2>&1 | tail -10
```

Expected: black, ruff, mypy, pyright, pytest all pass.

- [ ] **Step 4: Commit ratchet update**

```bash
git add .ratchet.json
git commit -m "chore: update .ratchet.json baseline for new auth provider modules"
```

- [ ] **Step 5: Push the branch**

```bash
git push origin feat/pluggable-auth
```

- [ ] **Step 6: Open the PR**

```bash
gh pr create --title "feat: pluggable AuthProvider (OAuth + API key)" --body "$(cat <<'EOF'
## Summary

- Adds `AuthProvider` Protocol and two implementations: `ClaudeCodeOAuthProvider` (reads OAuth token from Claude Code's stored credentials) and `AnthropicAPIKeyProvider` (refactored from `ClaudeAuth`).
- `AnthropicClient.__init__` now takes `auth_providers: Sequence[AuthProvider]` instead of `api_key: str`. Default chain (`get_default_providers()`) tries OAuth first, falls back to API key.
- ADR-001 stays valid -- still calling Anthropic directly via the standard SDK; OAuth uses the SDK's `auth_token=` Bearer auth path.

## Why

Sprint reality check: getting individual Anthropic API keys for ServiceNow employees is a lengthy enterprise process and personal keys violate company AI usage guidelines. Reading the user's existing Claude Code OAuth token (which the Claude Agent SDK does internally) lets NEXUS authenticate against the user's enterprise Claude account -- including their org's MCP servers -- with zero per-user setup.

Spec: `docs/superpowers/specs/2026-05-07-pluggable-auth-design.md`

## Test plan

- [ ] All existing tests still pass (53)
- [ ] New: 9 tests for ClaudeCodeOAuthProvider
- [ ] New: 2 tests for default provider chain
- [ ] New: 2 tests for AnthropicClient resolution logic
- [ ] New: 3 tests for ClaudeAuth Protocol methods
- [ ] Pre-commit (black, ruff, mypy, pyright, pytest) green
- [ ] Smoke test: \`.venv/bin/python scripts/smoke_anthropic.py\` makes real Anthropic API calls using OAuth from Claude Code

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: PR URL is printed.

---

## Self-Review

After running the plan, verify:

1. **Spec coverage:**
   - AuthProvider Protocol -> Task 1 ✓
   - ClaudeCodeOAuthProvider with 3 sources -> Task 3 ✓
   - AnthropicAPIKeyProvider (refactored ClaudeAuth) -> Task 2 ✓
   - get_default_providers() -> Task 4 ✓
   - AnthropicClient signature change -> Task 5 ✓
   - FakeAuthProvider -> Task 1 ✓
   - Smoke test using default chain -> Task 6 ✓
   - All exports -> Task 6 ✓

2. **No type:ignore introduced** -- if any pyright/mypy error appears, fix the type, never add `# type: ignore`.

3. **Coverage maintained** -- ratchet baseline updated in Task 7. Per-module coverage gate enforces this on every edit.

4. **Tests use fakes, not mocks** -- FakeAuthProvider is a real dataclass; no `unittest.mock` anywhere.
