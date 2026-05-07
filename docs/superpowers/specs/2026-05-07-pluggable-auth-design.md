# NEXUS Pluggable Auth Provider -- Design Spec
# Author: Pierre Grothe
# Date: 2026-05-07

## Overview

Replace the single hardcoded `api_key: str` parameter on `AnthropicClient` with
a pluggable `AuthProvider` Protocol. Initial implementations: OAuth (reads Claude
Code stored credentials) and API key (refactored from existing ClaudeAuth).
OAuth is tried first by default; API key is the fallback.

This unblocks development without requiring users to acquire individual Anthropic
API keys, lets users access their org's enterprise MCP servers transparently
(those are tied to the OAuth account), and keeps ADR-001 valid -- NEXUS still
calls the Anthropic API directly via the standard `anthropic` SDK, just with
`auth_token=` instead of `api_key=`.

## Why This Is Necessary

Sprint reality check: the maintainer (Pierre) cannot easily acquire an Anthropic
API key. ServiceNow uses an enterprise Claude account with managed access; getting
a personal API key issued by the org is a lengthy process and a personal-account
key would violate company AI usage guidelines and would not have access to the
org's enterprise MCP servers. End users (ServiceNow colleagues) face the same
friction. Without OAuth-based auth, NEXUS is impossible to validate end-to-end
during development and impossible to roll out at scale.

The Anthropic Python SDK supports OAuth tokens via the `auth_token=` parameter
(uses `Authorization: Bearer <token>` header). The Claude Agent SDK reads OAuth
tokens from a well-known location (`~/.claude/.credentials.json`, macOS Keychain
service `"Claude Code-credentials"`, or `CLAUDE_CODE_OAUTH_TOKEN` env var). Reading
a user's existing token to authenticate is supported -- the SDK does this in its
own internal session_resume.py code. The "Anthropic forbids third-party login"
rule applies to *building* a claude.ai login flow, not to using credentials a
user has already obtained via Claude Code.

## Scope

7 files (5 new, 2 modified) plus updates to existing tests. ~12 new tests.
No new dependencies (we read the credentials file directly; no need to import
`claude-agent-sdk`).

## Architecture

### AuthProvider Protocol

```python
class AuthProvider(Protocol):
    """Auth backend that produces an authenticated anthropic.Anthropic client.

    NEXUS resolves auth at AnthropicClient init by iterating a list of providers
    and picking the first one whose is_available() returns True. Order matters --
    the default chain tries OAuth before API key so Claude Code users get
    enterprise-account access without configuration.
    """

    @property
    def name(self) -> str:
        """Human-readable identifier; logged at AnthropicClient init."""

    def is_available(self) -> bool:
        """Return True if this provider's credentials are present and usable.

        MUST NOT raise. MUST NOT make network calls. SHOULD complete in <50ms.
        """

    def create_client(self, max_retries: int) -> anthropic.Anthropic:
        """Construct and return the SDK client.

        Called only when is_available() returned True. May raise AuthError if
        credentials become unavailable between is_available and create_client.
        """
```

### ClaudeCodeOAuthProvider

Reads the OAuth token from, in priority order:

  1. `CLAUDE_CODE_OAUTH_TOKEN` env var
  2. `$CLAUDE_CONFIG_DIR/.credentials.json` (or `~/.claude/.credentials.json`)
     -- parses JSON, extracts `claudeAiOauth.accessToken`
  3. macOS Keychain service `"Claude Code-credentials"` (Darwin only)
     -- via `security find-generic-password -s "Claude Code-credentials"`

Returns `anthropic.Anthropic(auth_token=token, max_retries=max_retries)`.

The token format is the access token (not the refresh token). The Anthropic API
accepts it as a Bearer token. Refresh handling is deferred to Plan 2 (Claude Code
itself refreshes the token on its own schedule; NEXUS reads the current token at
AnthropicClient init -- long-running sessions may need to re-init when tokens
expire).

`is_available()` succeeds if any of the three sources yields a non-empty string.
`create_client()` re-resolves the token at call time and constructs the SDK
client. The same priority order applies in both calls.

### AnthropicAPIKeyProvider

Refactored from the existing `ClaudeAuth` class. Reads the API key from:

  1. `ANTHROPIC_API_KEY` env var
  2. NEXUS keychain entry: service=`"nexus-claude"`, username=`"api_key"`

Returns `anthropic.Anthropic(api_key=key, max_retries=max_retries)`.

`is_available()` is the existing `ClaudeAuth.is_configured()`.
`create_client()` calls `get_api_key()` and constructs the SDK client.

The class keeps backward-compatible `is_configured()` and `get_api_key()` methods
so external callers (if any) do not break, but the canonical interface is the
Protocol methods.

### Provider chain factory

```python
def get_default_providers() -> list[AuthProvider]:
    """Return the default provider chain in priority order.

    OAuth first (preferred -- gives access to enterprise MCP servers tied to
    the user's Claude account), API key second (fallback for users without
    Claude Code installed).

    Returns:
        Two-element list: [ClaudeCodeOAuthProvider(), AnthropicAPIKeyProvider()].
    """
```

Future providers (Bedrock, Vertex, Foundry, NEXUS auth proxy) are added by
appending to this list or replacing it via config.

### AnthropicClient changes

`__init__` signature changes:

```python
# Before:
def __init__(
    self,
    api_key: str,
    capabilities: CapabilitySet,
    tier: ModelTier = ModelTier.STANDARD,
    _sdk_client: anthropic.Anthropic | None = None,
) -> None:

# After:
def __init__(
    self,
    auth_providers: Sequence[AuthProvider],
    capabilities: CapabilitySet,
    tier: ModelTier = ModelTier.STANDARD,
    _sdk_client: anthropic.Anthropic | None = None,
) -> None:
```

Resolution logic:

```python
if _sdk_client is not None:
    self._client = _sdk_client
    self._auth_provider_name = "injected"
else:
    for provider in auth_providers:
        if provider.is_available():
            self._client = provider.create_client(_MAX_RETRIES)
            self._auth_provider_name = provider.name
            break
    else:
        raise AuthError(
            "anthropic",
            "auth_providers",
            "No auth provider available. Run 'nexus setup' or "
            "ensure Claude Code is authenticated.",
        )
log.info(
    "AnthropicClient initialised: provider=%s tier=%s model=%s",
    self._auth_provider_name, tier, self._model,
)
```

The `_sdk_client` injectable is preserved for tests.

The change is breaking but has only one production caller (the smoke script);
all tests update in lockstep.

## File Layout

### New files

```
src/nexus/auth/providers.py
  -- AuthProvider Protocol
  -- get_default_providers() factory
  -- module-level constants for env var names

src/nexus/auth/oauth.py
  -- ClaudeCodeOAuthProvider class
  -- _read_credentials_file(path) helper
  -- _read_macos_keychain() helper

tests/fakes/fake_auth_provider.py
  -- FakeAuthProvider(name, is_available_value, sdk_client)
  -- For dependency injection in AnthropicClient tests

tests/test_auth_providers.py
  -- 12 tests (see Test Plan below)
```

### Modified files

```
src/nexus/auth/claude.py
  -- ClaudeAuth refactored to implement AuthProvider
  -- Renamed alias: AnthropicAPIKeyProvider = ClaudeAuth (kept for clarity)
  -- Existing methods preserved for backward compat

src/nexus/auth/__init__.py
  -- Export: AuthProvider, ClaudeCodeOAuthProvider,
              AnthropicAPIKeyProvider, get_default_providers
  -- Keep: AuthError, ClaudeAuth (as alias for AnthropicAPIKeyProvider),
            SNAuth, KeychainClient

src/nexus/api/client.py
  -- AnthropicClient.__init__ signature: api_key:str -> auth_providers:Sequence
  -- Resolution loop replaces direct anthropic.Anthropic(api_key=...) call
  -- Logs auth_provider_name

tests/test_api_client.py
  -- All tests using api_key="test-key" replaced with FakeAuthProvider injection
  -- New test: test_anthropic_client_logs_auth_provider_name

scripts/smoke_anthropic.py
  -- Uses get_default_providers() instead of ClaudeAuth.get_api_key()
  -- Removes the "no API key found" error path; AuthError is raised by client

.ratchet.json
  -- Add baseline entries for nexus.auth.providers and nexus.auth.oauth
```

## Test Plan

### tests/test_auth_providers.py (~12 tests)

**ClaudeCodeOAuthProvider (7):**

```python
def test_oauth_provider_is_available_true_with_env_var(monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "tok-xyz")
    assert ClaudeCodeOAuthProvider().is_available() is True

def test_oauth_provider_is_available_true_with_credentials_file(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    creds = {"claudeAiOauth": {"accessToken": "tok-xyz", "refreshToken": "ref-xyz"}}
    (tmp_path / ".credentials.json").write_text(json.dumps(creds))
    assert ClaudeCodeOAuthProvider().is_available() is True

def test_oauth_provider_is_available_false_when_nothing_present(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    assert ClaudeCodeOAuthProvider().is_available() is False

def test_oauth_provider_is_available_false_when_credentials_file_malformed(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    (tmp_path / ".credentials.json").write_text("not json")
    assert ClaudeCodeOAuthProvider().is_available() is False

def test_oauth_provider_create_client_uses_auth_token_from_env(monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "tok-from-env")
    client = ClaudeCodeOAuthProvider().create_client(max_retries=3)
    assert client.auth_token == "tok-from-env"
    assert client.api_key is None

def test_oauth_provider_create_client_uses_auth_token_from_file(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    creds = {"claudeAiOauth": {"accessToken": "tok-from-file"}}
    (tmp_path / ".credentials.json").write_text(json.dumps(creds))
    client = ClaudeCodeOAuthProvider().create_client(max_retries=3)
    assert client.auth_token == "tok-from-file"

def test_oauth_provider_priority_env_over_file(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "tok-from-env")
    creds = {"claudeAiOauth": {"accessToken": "tok-from-file"}}
    (tmp_path / ".credentials.json").write_text(json.dumps(creds))
    client = ClaudeCodeOAuthProvider().create_client(max_retries=3)
    assert client.auth_token == "tok-from-env"
```

Note: macOS Keychain test is not in this list because it requires Darwin and
a real Keychain entry. Manual smoke test covers it on Pierre's machine; the
existing `_read_macos_keychain()` helper is structurally tested via the
"is_available_true_with_credentials_file" path which exercises the same fallback
chain logic.

**Provider chain (3):**

```python
def test_default_providers_returns_oauth_first():
    providers = get_default_providers()
    assert len(providers) == 2
    assert providers[0].name == "claude_code_oauth"
    assert providers[1].name == "anthropic_api_key"

def test_default_providers_resolves_first_available():
    providers = [
        FakeAuthProvider(name="oauth", available=False),
        FakeAuthProvider(name="api_key", available=True),
    ]
    client = AnthropicClient(
        auth_providers=providers,
        capabilities=CapabilitySet.none(),
        _sdk_client=_FakeSdk(...),
    )
    # Provider name is logged; verify with caplog or expose getter

def test_anthropic_client_raises_when_no_provider_available():
    providers = [FakeAuthProvider(name="oauth", available=False)]
    with pytest.raises(AuthError):
        AnthropicClient(auth_providers=providers, capabilities=CapabilitySet.none())
```

**AnthropicAPIKeyProvider (refactored, existing tests updated):**

The 12 existing tests in `test_auth.py` for ClaudeAuth continue to pass after
refactor. Two new assertions added:
- `provider.name == "anthropic_api_key"`
- `provider.is_available()` matches `provider.is_configured()`

### tests/fakes/fake_auth_provider.py

```python
@dataclass(slots=True)
class FakeAuthProvider:
    """Test double for AuthProvider Protocol.

    Configurable per-test:
      name: identifier returned by the .name property
      available: value returned by is_available()
      sdk_client: Anthropic-like instance returned by create_client()
    """
    name: str = "fake"
    available: bool = True
    sdk_client: anthropic.Anthropic | None = None

    def is_available(self) -> bool:
        return self.available

    def create_client(self, max_retries: int) -> anthropic.Anthropic:
        if self.sdk_client is None:
            raise AuthError("fake", "client", "no sdk_client configured")
        return self.sdk_client
```

## Smoke Test Update

`scripts/smoke_anthropic.py` becomes:

```python
from nexus.api.client import AnthropicClient, ModelTier
from nexus.auth.providers import get_default_providers
from nexus.capabilities.registry import CapabilitySet

logging.basicConfig(level=logging.INFO, format="...")

client = AnthropicClient(
    auth_providers=get_default_providers(),
    capabilities=CapabilitySet.none(),
    tier=ModelTier.STANDARD,
)
# AnthropicClient.__init__ logs "provider=claude_code_oauth tier=STANDARD model=..."

msg = client.complete(
    messages=[{"role": "user", "content": "What is NEXUS?"}],
    system="You are a terse assistant. ...",
    max_tokens=200,
)
print(msg.content[0].text)
```

When Pierre runs this on his machine (Claude Code authenticated), the
ClaudeCodeOAuthProvider picks up his token from `~/.claude/.credentials.json`
or the Keychain, the SDK uses `auth_token=...` Bearer auth, and the API call
succeeds against his enterprise account.

## Out of Scope (deferred to follow-up)

- **OAuth token refresh.** Long-running NEXUS sessions may hit token expiry.
  Current scope: read token at init; long-running sessions re-init AnthropicClient
  if they get a 401. Refresh logic is deferred.

- **Bedrock / Vertex / Foundry providers.** Architecture supports them (just
  another AuthProvider impl returning AnthropicBedrock/etc. instances). Implement
  when an audience needs them.

- **MCPProbe implementation.** With OAuth working, MCPProbe can finally probe
  real enterprise MCP servers via lightweight Anthropic API calls. Currently
  stubbed (returns False always). Tracked separately; this spec only enables it.

- **Config-driven provider chain.** `~/.nexus/config.yaml` could specify which
  providers to use and in what order (`auth.providers: ["api_key", "oauth"]`).
  Default chain is hardcoded for now.

## Migration

Breaking change to `AnthropicClient.__init__`. Affected callers:

- `tests/test_api_client.py` -- 5 tests using `api_key="test-key"`. Updated to
  use `FakeAuthProvider` injection.
- `scripts/smoke_anthropic.py` -- uses `get_default_providers()`.

No production callers (cli.py commands are stubs that don't construct
AnthropicClient). Migration is mechanical and complete in a single PR.

## Risks

1. **Claude Code credentials file format changes.** `~/.claude/.credentials.json`
   structure (`claudeAiOauth.accessToken`) is observable from the Claude Agent SDK
   source but not officially documented as a stable third-party API. If Anthropic
   changes the format, ClaudeCodeOAuthProvider breaks. Mitigation: extensive
   logging at WARNING when the file is present but unparseable; clear fallback
   to API key path; integration test verifies on every release.

2. **Token expiry during long sessions.** OAuth access tokens typically expire in
   ~1 hour. NEXUS reads at AnthropicClient init; if the session runs longer, an
   API call eventually returns 401. Currently maps to `AnthropicError(401, ...)`.
   Workaround: caller catches and re-inits AnthropicClient (which re-reads the
   token Claude Code has refreshed in the background). Proper refresh handling
   deferred to follow-up.

3. **Token reuse policy.** Reading another tool's stored OAuth token is sensitive
   even when supported. The Claude Agent SDK reading these credentials is part of
   its sanctioned design (it's an Anthropic-published SDK). Whether a third-party
   tool reading the same files for the same purpose violates ToS is unclear.
   Mitigation: clear documentation in NEXUS that the user is opting into auth
   sharing; explicit log line at AnthropicClient init showing which provider was
   selected; if Anthropic asks us to stop, we add a config flag to disable OAuth
   provider.

## Updates to Existing Documentation

- `CLAUDE.md` Standards section: add `auth_token=` Bearer auth as an accepted path
- `.primer/governance.md` Agent-Enforced Rules: add `auth-providers` rule (use
  AuthProvider Protocol, never construct anthropic.Anthropic directly outside
  the providers module)
- ADR-014 (NEW): document the pluggable AuthProvider decision
- `.primer/decisions.md`: append entry referencing ADR-014
- `.primer/stack.md`: update auth section
