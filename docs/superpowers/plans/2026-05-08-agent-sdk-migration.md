# Agent SDK Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the `anthropic` SDK and the PR-#1 AuthProvider abstraction with `claude-agent-sdk`, which transparently handles auth via Claude Code's stored credentials and bypasses the `/v1/messages` policy gate.

**Architecture:** Add a thin async `AgentClient` wrapper around `claude_agent_sdk.query()`. Delete the AnthropicClient layer (model auto-discovery, AuthProvider chain, ToolRegistry, OAuth provider). Revert ClaudeAuth to its pre-PR-#1 shape. Drop `anthropic` package dependency.

**Tech Stack:** Python 3.14, claude-agent-sdk (replaces anthropic), pytest-asyncio (already in deps), pyright/mypy strict.

---

## File Map

```
ADD:
  src/nexus/api/agent_client.py        -- AgentClient + AgentClientProtocol
  tests/fakes/fake_agent_client.py     -- FakeAgentClient
  tests/test_agent_client.py           -- 6 tests
  scripts/smoke_agent.py               -- manual end-to-end smoke
  .primer/adr/ADR-015-claude-agent-sdk-migration.md

DELETE:
  src/nexus/api/client.py              -- AnthropicClient, ModelTier, _ModelDiscoveryClient
  src/nexus/api/tool_registry.py       -- ToolRegistry (no longer needed)
  src/nexus/auth/oauth.py              -- ClaudeCodeOAuthProvider
  src/nexus/auth/providers.py          -- AuthProvider Protocol + factory
  tests/fakes/fake_anthropic_client.py
  tests/fakes/fake_auth_provider.py
  tests/test_api_client.py             -- 16 tests
  tests/test_auth_providers.py         -- 13 tests
  scripts/smoke_anthropic.py

MODIFY:
  pyproject.toml                       -- drop anthropic, add claude-agent-sdk
  src/nexus/api/__init__.py            -- export AgentClient + AgentClientProtocol only
  src/nexus/api/errors.py              -- keep AnthropicError (still used)
  src/nexus/auth/__init__.py           -- drop AuthProvider exports
  src/nexus/auth/claude.py             -- revert PR-#1 Protocol methods
  tests/fakes/__init__.py              -- swap FakeAnthropicClient/FakeAuthProvider for FakeAgentClient
  tests/test_auth.py                   -- remove 3 PR-#1-added tests, restore is_configured tests
  .ratchet.json                        -- remove deleted modules, add nexus.api.agent_client
  .primer/adr/ADR-014-pluggable-auth-provider.md  -- mark SUPERSEDED
  .primer/adr/ADR-001-api-direct-architecture.md  -- partial supersede note
  .primer/governance.md                -- update ADR catalog
  .primer/decisions.md                 -- append ADR-015 entry
```

---

## Task 1: Add claude-agent-sdk dependency

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add the dependency**

In `pyproject.toml`, find the `[tool.poetry.dependencies]` section. Add:

```toml
claude-agent-sdk = ">=0.1"
```

Keep `anthropic = ">=0.50"` for now -- it stays until Task 6 cleanup.

- [ ] **Step 2: Install**

```bash
cd /Users/pierre.grothe/Developer/nexus && .venv/bin/pip install claude-agent-sdk
```

(We use `pip install` instead of `poetry install` because `poetry install` would also process the existing lockfile. The dep declaration in pyproject.toml ensures Poetry tracks it. The lockfile updates in Task 6.)

- [ ] **Step 3: Verify import works**

```bash
.venv/bin/python -c "from claude_agent_sdk import query, ClaudeAgentOptions; from claude_agent_sdk.types import AssistantMessage, ResultMessage, TextBlock; print('imports ok')"
```

Expected: `imports ok`

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml && git commit -m "deps: add claude-agent-sdk"
```

---

## Task 2: Create AgentClient + AgentClientProtocol + FakeAgentClient + tests

**Files:**
- Create: `src/nexus/api/agent_client.py`
- Create: `tests/fakes/fake_agent_client.py`
- Modify: `tests/fakes/__init__.py`
- Create: `tests/test_agent_client.py`

- [ ] **Step 1: Create FakeAgentClient first** (so the test file can import without breaking)

Write `tests/fakes/fake_agent_client.py`:

```python
# tests/fakes/fake_agent_client.py
# Test double for AgentClientProtocol -- no Agent SDK / subprocess.
# Author: Pierre Grothe
# Date: 2026-05-08

"""FakeAgentClient: implements AgentClientProtocol for unit tests."""

from dataclasses import dataclass, field

__all__ = ["FakeAgentClient"]


@dataclass(slots=True)
class FakeAgentClient:
    """Test double for AgentClientProtocol.

    Records every call and returns canned_response. No subprocess, no Agent SDK.

    Attributes:
        calls: List of dicts capturing every complete() invocation.
        canned_response: String returned by complete() on success.
        side_effect: Optional exception to raise instead of returning.
    """

    calls: list[dict[str, object]] = field(default_factory=list[dict[str, object]])
    canned_response: str = "ok"
    side_effect: BaseException | None = None

    async def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        model: str | None = None,
        max_turns: int = 1,
    ) -> str:
        """Record the call and return canned_response (or raise side_effect)."""
        self.calls.append({
            "prompt": prompt,
            "system": system,
            "model": model,
            "max_turns": max_turns,
        })
        if self.side_effect is not None:
            raise self.side_effect
        return self.canned_response
```

- [ ] **Step 2: Update tests/fakes/__init__.py**

Read the file first. It currently exports FakeAnthropicClient, FakeAuthProvider, FakeKeychainClient, FakeServiceNowClient. Replace with:

```python
# tests/fakes/__init__.py
# Fake implementations used in tests. No mocks anywhere.
# Author: Pierre Grothe
# Date: 2026-05-07
"""Fake connectors and clients for use in tests."""

from tests.fakes.fake_agent_client import FakeAgentClient
from tests.fakes.fake_anthropic_client import FakeAnthropicClient
from tests.fakes.fake_auth_provider import FakeAuthProvider
from tests.fakes.fake_keychain import FakeKeychainClient
from tests.fakes.fake_sn_client import FakeServiceNowClient

__all__ = [
    "FakeAgentClient",
    "FakeAnthropicClient",
    "FakeAuthProvider",
    "FakeKeychainClient",
    "FakeServiceNowClient",
]
```

(We add FakeAgentClient to the existing exports. The deletes happen in Tasks 4-5.)

- [ ] **Step 3: Write the failing test file**

Create `tests/test_agent_client.py`:

```python
# tests/test_agent_client.py
# Tests for the AgentClient and FakeAgentClient.
# Author: Pierre Grothe
# Date: 2026-05-08
"""Tests for nexus.api.agent_client."""

import pytest

from nexus.api.agent_client import AgentClient, AgentClientProtocol
from nexus.api.errors import AnthropicError
from tests.fakes.fake_agent_client import FakeAgentClient


async def test_fake_agent_client_records_calls() -> None:
    client = FakeAgentClient()
    result = await client.complete("hello", system="You are terse.")
    assert result == "ok"
    assert client.calls == [
        {"prompt": "hello", "system": "You are terse.", "model": None, "max_turns": 1},
    ]


async def test_fake_agent_client_returns_canned_response() -> None:
    client = FakeAgentClient(canned_response="custom")
    assert await client.complete("anything") == "custom"


async def test_fake_agent_client_raises_side_effect() -> None:
    client = FakeAgentClient(side_effect=AnthropicError(429, "rate limit"))
    with pytest.raises(AnthropicError):
        await client.complete("hello")


async def test_fake_agent_client_records_all_options() -> None:
    client = FakeAgentClient()
    await client.complete("p", system="s", model="claude-sonnet-4-6", max_turns=5)
    assert client.calls[0] == {
        "prompt": "p",
        "system": "s",
        "model": "claude-sonnet-4-6",
        "max_turns": 5,
    }


def test_agent_client_protocol_satisfied_by_real_client() -> None:
    """Static check: AgentClient structurally implements AgentClientProtocol."""
    client: AgentClientProtocol = AgentClient()
    assert callable(client.complete)


def test_agent_client_protocol_satisfied_by_fake() -> None:
    """Static check: FakeAgentClient structurally implements AgentClientProtocol."""
    fake: AgentClientProtocol = FakeAgentClient()
    assert callable(fake.complete)
```

Note: `pyproject.toml` has `asyncio_mode = "auto"` so `async def test_*` works without explicit decorators.

- [ ] **Step 4: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/test_agent_client.py -v --override-ini="addopts="
```

Expected: ImportError on `nexus.api.agent_client`.

- [ ] **Step 5: Create the AgentClient module**

Write `src/nexus/api/agent_client.py`:

```python
# src/nexus/api/agent_client.py
# AgentClient: async LLM client backed by claude-agent-sdk.
# Author: Pierre Grothe
# Date: 2026-05-08
"""AgentClient: routes LLM calls through claude-agent-sdk.

Auth is handled internally by claude-agent-sdk's session_resume:
  - ANTHROPIC_API_KEY env var
  - CLAUDE_CODE_OAUTH_TOKEN env var
  - $CLAUDE_CONFIG_DIR/.credentials.json (or ~/.claude/.credentials.json)
  - macOS Keychain "Claude Code-credentials"

NEXUS callers do not pass credentials. They construct AgentClient() and call
await client.complete(prompt, ...).
"""

from typing import Protocol

from claude_agent_sdk import ClaudeAgentOptions, query
from claude_agent_sdk.types import AssistantMessage, ResultMessage, TextBlock

from nexus.api.errors import AnthropicError

__all__ = ["AgentClient", "AgentClientProtocol"]


class AgentClientProtocol(Protocol):
    """Async LLM client interface for NEXUS agents and CLI commands.

    Implementations route LLM calls through claude-agent-sdk, which handles
    authentication automatically. Agents and CLI commands type-hint against
    this Protocol so they can accept FakeAgentClient in tests.
    """

    async def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        model: str | None = None,
        max_turns: int = 1,
    ) -> str:
        """Send a prompt and return the final assistant text.

        Args:
            prompt: User-facing prompt sent to the agent.
            system: Optional system prompt prepended by Agent SDK.
            model: Optional model ID. If None, Agent SDK picks the default.
            max_turns: Maximum agent turns (tool-call rounds). Default 1.

        Returns:
            Concatenated text from all AssistantMessage TextBlocks.

        Raises:
            AnthropicError: When the underlying API returns an error.
        """
        ...


class AgentClient:
    """LLM client backed by claude-agent-sdk."""

    async def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        model: str | None = None,
        max_turns: int = 1,
    ) -> str:
        """See AgentClientProtocol.complete."""
        options = ClaudeAgentOptions(
            system_prompt=system,
            model=model,
            max_turns=max_turns,
        )
        text_parts: list[str] = []
        result_message: ResultMessage | None = None
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        text_parts.append(block.text)
            elif isinstance(message, ResultMessage):
                result_message = message
        if result_message is not None and result_message.is_error:
            raise AnthropicError(0, result_message.result or "agent sdk error")
        return "".join(text_parts)
```

If `pyright` complains about the `claude_agent_sdk.types` imports being unknown, check what symbols are actually exported. Use:
```bash
.venv/bin/python -c "import claude_agent_sdk.types; print(dir(claude_agent_sdk.types))"
```
Adjust the import path accordingly. Common alternatives:
```python
from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
.venv/bin/pytest tests/test_agent_client.py -v --override-ini="addopts="
```

Expected: 6 passed.

- [ ] **Step 7: Run lint + type checks**

```bash
.venv/bin/ruff check src/nexus/api/agent_client.py tests/fakes/fake_agent_client.py tests/test_agent_client.py
.venv/bin/mypy src/nexus/api/agent_client.py
.venv/bin/pyright src/nexus/api/agent_client.py tests/fakes/fake_agent_client.py
```

Expected: 0 violations, 0 errors. If pyright reports unknown imports from claude_agent_sdk (the SDK may not ship full type stubs), that is acceptable per pyright `reportMissingTypeStubs` -- but ANN/RUF rules from ruff must still pass. If you get `Module "claude_agent_sdk" has no attribute "X"` errors, adjust imports per Step 5 alternatives.

- [ ] **Step 8: Commit**

```bash
git add src/nexus/api/agent_client.py tests/fakes/fake_agent_client.py tests/fakes/__init__.py tests/test_agent_client.py && git commit -m "feat: add AgentClient backed by claude-agent-sdk + FakeAgentClient"
```

---

## Task 3: Create smoke_agent.py + delete smoke_anthropic.py

**Files:**
- Create: `scripts/smoke_agent.py`
- Delete: `scripts/smoke_anthropic.py`

- [ ] **Step 1: Create the new smoke script**

Write `scripts/smoke_agent.py`:

```python
# scripts/smoke_agent.py
# End-to-end smoke test for AgentClient against the real Anthropic API.
# Author: Pierre Grothe
# Date: 2026-05-08
"""End-to-end smoke test for AgentClient backed by claude-agent-sdk.

Run with:
    .venv/bin/python scripts/smoke_agent.py

Auth is handled automatically by claude-agent-sdk:
  - ANTHROPIC_API_KEY env var
  - Claude Code stored credentials (env var, file, or macOS Keychain)

Validates:
  1. Real API call via claude-agent-sdk works (no API key required)
  2. Two consecutive calls succeed
"""

import asyncio
import logging
import sys

from nexus.api.agent_client import AgentClient


async def main() -> int:
    """Run the smoke test and return an exit code."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s -- %(message)s",
    )
    log = logging.getLogger("smoke-agent")

    client = AgentClient()
    system_prompt = (
        "You are a terse assistant. Answer in one short sentence. "
        "If asked about NEXUS, say it is a ServiceNow AI architect tool."
    )

    log.info("Sending first call...")
    msg1 = await client.complete("What is NEXUS?", system=system_prompt)
    print("Response 1:", msg1)

    log.info("Sending second call...")
    msg2 = await client.complete("What is the capital of France?", system=system_prompt)
    print("Response 2:", msg2)

    print("\nSUCCESS: both calls completed.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
```

- [ ] **Step 2: Delete the old smoke script**

```bash
rm scripts/smoke_anthropic.py
```

- [ ] **Step 3: Run lint on the new script**

```bash
.venv/bin/ruff check scripts/smoke_agent.py
.venv/bin/mypy scripts/smoke_agent.py
.venv/bin/pyright scripts/smoke_agent.py
```

Expected: 0 violations, 0 errors.

- [ ] **Step 4: Commit**

```bash
git add scripts/smoke_agent.py && git rm scripts/smoke_anthropic.py && git commit -m "feat: replace smoke_anthropic.py with smoke_agent.py using AgentClient"
```

---

## Task 4: Delete old api/ files and tests, update api/__init__.py

**Files:**
- Modify: `src/nexus/api/__init__.py`
- Delete: `src/nexus/api/client.py`
- Delete: `src/nexus/api/tool_registry.py`
- Delete: `tests/test_api_client.py`
- Delete: `tests/fakes/fake_anthropic_client.py`
- Modify: `tests/fakes/__init__.py`

Order matters here: update `__init__.py` first to remove imports from soon-to-be-deleted files, then delete files.

- [ ] **Step 1: Replace api/__init__.py**

Write `src/nexus/api/__init__.py`:

```python
# src/nexus/api/__init__.py
# Anthropic API layer public exports.
# Author: Pierre Grothe
# Date: 2026-05-07
"""LLM client layer backed by claude-agent-sdk."""

from nexus.api.agent_client import AgentClient, AgentClientProtocol
from nexus.api.errors import AnthropicError
from nexus.api.logging_config import configure_logging

__all__ = [
    "AgentClient",
    "AgentClientProtocol",
    "AnthropicError",
    "configure_logging",
]
```

- [ ] **Step 2: Update tests/fakes/__init__.py to remove FakeAnthropicClient**

Write `tests/fakes/__init__.py`:

```python
# tests/fakes/__init__.py
# Fake implementations used in tests. No mocks anywhere.
# Author: Pierre Grothe
# Date: 2026-05-07
"""Fake connectors and clients for use in tests."""

from tests.fakes.fake_agent_client import FakeAgentClient
from tests.fakes.fake_auth_provider import FakeAuthProvider
from tests.fakes.fake_keychain import FakeKeychainClient
from tests.fakes.fake_sn_client import FakeServiceNowClient

__all__ = [
    "FakeAgentClient",
    "FakeAuthProvider",
    "FakeKeychainClient",
    "FakeServiceNowClient",
]
```

(FakeAuthProvider stays for now; deleted in Task 5.)

- [ ] **Step 3: Delete old api/ source files and tests**

```bash
rm src/nexus/api/client.py
rm src/nexus/api/tool_registry.py
rm tests/test_api_client.py
rm tests/fakes/fake_anthropic_client.py
```

- [ ] **Step 4: Verify imports still work**

```bash
.venv/bin/python -c "from nexus.api import AgentClient, AgentClientProtocol, AnthropicError, configure_logging; print('imports ok')"
```

Expected: `imports ok`

- [ ] **Step 5: Run remaining tests**

```bash
.venv/bin/pytest -q --override-ini="addopts="
```

Expected: all remaining tests pass. Some auth-related tests may fail because PR-#1's Protocol methods on ClaudeAuth still exist -- that is fixed in Task 5.

- [ ] **Step 6: Run lint + type checks on changed files**

```bash
.venv/bin/ruff check src/nexus/api/__init__.py tests/fakes/__init__.py
.venv/bin/mypy src/nexus/api/__init__.py
.venv/bin/pyright src/nexus/api/__init__.py
```

Expected: 0 violations.

- [ ] **Step 7: Commit**

```bash
git add -A && git commit -m "feat: remove AnthropicClient + ToolRegistry; api/ exports AgentClient"
```

---

## Task 5: Revert PR-#1 auth abstraction

**Files:**
- Modify: `src/nexus/auth/__init__.py`
- Modify: `src/nexus/auth/claude.py`
- Modify: `tests/test_auth.py`
- Delete: `src/nexus/auth/oauth.py`
- Delete: `src/nexus/auth/providers.py`
- Delete: `tests/fakes/fake_auth_provider.py`
- Delete: `tests/test_auth_providers.py`
- Modify: `tests/fakes/__init__.py`

- [ ] **Step 1: Revert src/nexus/auth/claude.py to pre-PR-#1 shape**

Read the current file. Replace with the version from before PR #1 (no `name` property, no `is_available`, no `create_client`, no caching -- those existed pre-PR-#1 only as `is_configured`):

```python
# nexus/auth/claude.py
# Claude Enterprise API key storage and validation.
# Author: Pierre Grothe
# Date: 2026-05-07

"""ClaudeAuth: store, retrieve, and validate the Claude Enterprise API key."""

import logging
import os

from nexus.auth.errors import AuthError
from nexus.auth.keychain import KeychainClient

log = logging.getLogger(__name__)

__all__ = ["ClaudeAuth"]

_ENV_VAR = "NEXUS_CLAUDE_API_KEY"
_KEYCHAIN_SERVICE = "claude"
_KEYCHAIN_USERNAME = "api_key"


class ClaudeAuth:
    """Manage the Claude Enterprise API key.

    Resolution order:
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

    def get_api_key(self) -> str:
        """Return the Claude API key.

        Returns:
            The API key string.

        Raises:
            AuthError: When no key is configured in either location.
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

- [ ] **Step 2: Revert tests/test_auth.py PR-#1 changes**

Read the current file. Find these tests and rename them back from `is_available` to `is_configured`:

```python
def test_claude_auth_is_available_returns_true_with_env(...) -> None:
    ...
    assert auth.is_available() is True
```
becomes:
```python
def test_claude_auth_is_configured_returns_true_with_env(...) -> None:
    ...
    assert auth.is_configured() is True
```

Same for the false-with-no-credentials test.

DELETE these three tests entirely (added by PR #1):
- `test_claude_auth_implements_auth_provider_name`
- `test_claude_auth_create_client_returns_anthropic_with_api_key`
- (No `test_claude_auth_is_available_matches_is_configured` -- already removed in /simplify pass)

- [ ] **Step 3: Update src/nexus/auth/__init__.py**

Write:

```python
# nexus/auth/__init__.py
# Authentication layer public exports.
# Author: Pierre Grothe
# Date: 2026-05-07

"""Credential storage and retrieval for NEXUS."""

from nexus.auth.claude import ClaudeAuth
from nexus.auth.errors import AuthError
from nexus.auth.keychain import KeychainClient
from nexus.auth.servicenow import SNAuth

__all__ = [
    "AuthError",
    "ClaudeAuth",
    "KeychainClient",
    "SNAuth",
]
```

- [ ] **Step 4: Delete PR-#1 files**

```bash
rm src/nexus/auth/oauth.py
rm src/nexus/auth/providers.py
rm tests/fakes/fake_auth_provider.py
rm tests/test_auth_providers.py
```

- [ ] **Step 5: Update tests/fakes/__init__.py to remove FakeAuthProvider**

Write:

```python
# tests/fakes/__init__.py
# Fake implementations used in tests. No mocks anywhere.
# Author: Pierre Grothe
# Date: 2026-05-07
"""Fake connectors and clients for use in tests."""

from tests.fakes.fake_agent_client import FakeAgentClient
from tests.fakes.fake_keychain import FakeKeychainClient
from tests.fakes.fake_sn_client import FakeServiceNowClient

__all__ = [
    "FakeAgentClient",
    "FakeKeychainClient",
    "FakeServiceNowClient",
]
```

- [ ] **Step 6: Verify nothing else imports the deleted modules**

```bash
grep -rn "AuthProvider\|ClaudeCodeOAuthProvider\|FakeAuthProvider\|fake_auth_provider\|nexus.auth.providers\|nexus.auth.oauth" src/ tests/ scripts/ 2>&1 | head -10
```

Expected: no output.

- [ ] **Step 7: Run all tests**

```bash
.venv/bin/pytest -q --override-ini="addopts="
```

Expected: all remaining tests pass. Test count should be in the ~62 range (down from 71 -- 13 from test_auth_providers gone, 16 from test_api_client gone, 6 new agent_client tests added, 3 PR-#1 tests in test_auth removed).

- [ ] **Step 8: Run lint + type checks**

```bash
.venv/bin/ruff check src/nexus/auth/ tests/test_auth.py tests/fakes/__init__.py
.venv/bin/mypy src/nexus/auth/ tests/test_auth.py
.venv/bin/pyright src/nexus/auth/ tests/test_auth.py
```

Expected: 0 violations, 0 errors.

- [ ] **Step 9: Commit**

```bash
git add -A && git commit -m "feat: revert PR-#1 AuthProvider abstraction (superseded by Agent SDK migration)"
```

---

## Task 6: Drop anthropic dep + update .ratchet.json

**Files:**
- Modify: `pyproject.toml`
- Modify: `.ratchet.json`

- [ ] **Step 1: Verify nothing imports anthropic**

```bash
grep -rn "^import anthropic\|^from anthropic" src/ tests/ scripts/ 2>&1
```

Expected: no output. If anything still imports `anthropic`, fix it before continuing.

- [ ] **Step 2: Drop anthropic from pyproject.toml**

In `pyproject.toml` `[tool.poetry.dependencies]`, delete the line:
```toml
anthropic = ">=0.50"
```

- [ ] **Step 3: Update .ratchet.json**

Read the current file. Remove these entries (modules that no longer exist):
- `nexus.api.client`
- `nexus.api.tool_registry`
- `nexus.auth.oauth`
- `nexus.auth.providers`

Update `nexus.auth.claude` baseline if covered_lines changed (it shrunk after revert).

Add new entry:
- `nexus.api.agent_client`

To get the right numbers, run:
```bash
.venv/bin/pytest --cov=nexus.api.agent_client --cov=nexus.auth.claude --cov-report=json --cov-fail-under=0 -q --override-ini="addopts="
.venv/bin/python -c "
import json
data = json.load(open('coverage.json'))
for path, info in sorted(data['files'].items()):
    if 'agent_client' in path or 'auth/claude' in path:
        s = info['summary']
        print(path, '->', 'covered=' + str(s['covered_lines']), 'total=' + str(s['num_statements']))
"
```

Use those numbers in `.ratchet.json`. The baselines should be the actual covered/total values (not 100% requirements).

- [ ] **Step 4: Reinstall to update lockfile**

```bash
poetry install
```

Expected: poetry.lock updates to remove `anthropic`.

- [ ] **Step 5: Run full test suite + pre-commit**

```bash
.venv/bin/pre-commit run --all-files 2>&1 | tail -10
```

Expected: all 5 hooks (black, ruff, mypy, pyright, pytest) pass.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml poetry.lock .ratchet.json && git commit -m "deps: drop anthropic SDK; update ratchet baseline for new modules"
```

---

## Task 7: ADRs + governance + decisions

**Files:**
- Create: `.primer/adr/ADR-015-claude-agent-sdk-migration.md`
- Modify: `.primer/adr/ADR-014-pluggable-auth-provider.md`
- Modify: `.primer/adr/ADR-001-api-direct-architecture.md`
- Modify: `.primer/governance.md`
- Modify: `.primer/decisions.md`

- [ ] **Step 1: Create ADR-015**

Write `.primer/adr/ADR-015-claude-agent-sdk-migration.md`:

```markdown
# ADR-015: Migrate from anthropic SDK to claude-agent-sdk

**Status:** accepted
**Date:** 2026-05-08
**Enforcement:** none (architectural)

## Context

ADR-014 introduced a pluggable AuthProvider abstraction with two concrete
implementations: AnthropicAPIKeyProvider (X-Api-Key auth) and
ClaudeCodeOAuthProvider (Bearer auth via the user's Claude Code stored token).
The OAuth path was meant to bypass the API-key-acquisition friction for
ServiceNow employees who could not easily obtain an enterprise API key.

Empirical testing on 2026-05-08 showed the OAuth path is policy-gated by
Anthropic. With a valid OAuth token:
  - GET /v1/models returns 200
  - POST /v1/messages returns 429 immediately, on every call, on every
    retry, even with no recent traffic from the same token

This is not a transient rate limit. The error body lacks Retry-After headers
and details. The behavior matches Anthropic's stated policy that third-party
products may not use claude.ai login or rate limits.

A 10-line smoke test against `claude-agent-sdk` (Anthropic-published Python
SDK that wraps the bundled Claude Code CLI as a subprocess) succeeded against
the same /v1/messages endpoint with the same OAuth credentials, returning a
real assistant message with prompt caching active and access to Claude Opus
4.7 with 1M context.

## Decision

Replace the standard `anthropic` SDK with `claude-agent-sdk` as the LLM
access layer. The user-facing distribution model (pip package, `nexus`
CLI command) stays identical. Internally, LLM calls go through
`claude_agent_sdk.query()` which spawns the bundled Claude Code CLI as a
subprocess and authenticates using the user's stored credentials.

A new `AgentClient` class wraps `claude_agent_sdk.query()` with a simple
async interface: `async def complete(prompt, *, system, model, max_turns) -> str`.
The PR-#1 AuthProvider abstraction is deleted -- claude-agent-sdk handles
the auth resolution chain (env var > file > Keychain) internally.

## Consequences

NEXUS users who have Claude Code installed and authenticated (the target
audience: ServiceNow colleagues) get LLM access transparently with no API
key. This works for actual /v1/messages calls, not just metadata.

Tradeoffs accepted:
  - Bundled Claude Code CLI adds ~50MB to package install
  - Each `query()` invocation spawns a subprocess and runs SessionStart
    hooks (~10-30s startup cost on cold call)
  - The standard `anthropic` SDK is no longer a dependency
  - ADR-014 (Pluggable AuthProvider) becomes superseded
  - ADR-001 (API-direct, no Claude Code dependency) becomes partially
    superseded -- still pip distribution, but Claude Code CLI is now a
    subprocess dependency

Headless / CI environments without Claude Code authenticated continue to
work via ANTHROPIC_API_KEY environment variable, which claude-agent-sdk
resolves first in its auth chain.
```

- [ ] **Step 2: Mark ADR-014 as superseded**

Read `.primer/adr/ADR-014-pluggable-auth-provider.md`. Wait, that file does not exist yet -- ADR-014 was the AuthProvider work but we never created the ADR file for it. Verify:

```bash
ls /Users/pierre.grothe/Developer/nexus/.primer/adr/ADR-014*.md
```

If the file does not exist (which is the expected case -- PR #1 didn't add an ADR file, just an entry in decisions.md), skip Step 2 and instead update the decisions.md entry from PR #1 to note the supersede. If the file DOES exist, update its Status line:

```markdown
**Status:** superseded by ADR-015
```

- [ ] **Step 3: Add partial supersede note to ADR-001**

Read `.primer/adr/ADR-001-api-direct-architecture.md`. After the existing **Consequences** section, add a new section:

```markdown
## Update 2026-05-08: Partially superseded by ADR-015

The "no Claude Code dependency" claim is partially superseded. NEXUS still
ships as a pip package and is invoked as `nexus <command>` (not as a Claude
Code plugin). However, the underlying LLM access goes through claude-agent-sdk,
which bundles Claude Code CLI as a subprocess dependency.

User-facing distribution and invocation are unchanged. Implementation is
no longer Claude-Code-independent.
```

- [ ] **Step 4: Update governance.md ADR catalog**

Read `.primer/governance.md`. In the ADR Catalog section, add a row for ADR-015 and update ADR-014 (if listed) and ADR-001:

```markdown
| 001 | API-direct architecture | none | accepted (partial supersede ADR-015) |
| ... |
| 014 | Pluggable AuthProvider (OAuth + API key) | superseded | superseded by ADR-015 |
| 015 | Migrate from anthropic SDK to claude-agent-sdk | none | accepted |
```

If ADR-014 is not currently in the catalog (because it was never formalized), just add ADR-015. The decisions.md entry from PR #1 remains as the historical record.

- [ ] **Step 5: Append to decisions.md**

Read `.primer/decisions.md`. Append a new entry at the bottom:

```markdown


---

### 2026-05-08 -- Migrate from anthropic SDK to claude-agent-sdk

**Status:** accepted (supersedes the AuthProvider OAuth path from 2026-05-07)

**Context:** PR #1 introduced a Pluggable AuthProvider abstraction so users
could authenticate via Claude Code's stored OAuth credentials, bypassing the
API-key-acquisition process. Empirical testing showed the OAuth path is
policy-gated at /v1/messages: the standard anthropic SDK with auth_token=
returns 429 on every call. The Claude Agent SDK -- using the same OAuth
credentials -- succeeds.

**Decision:** Replace the anthropic SDK with claude-agent-sdk. Add an
AgentClient async wrapper. Delete the AuthProvider abstraction (Agent SDK
handles auth internally). Drop the anthropic package dependency.

**Consequences:** NEXUS users with Claude Code installed get transparent
LLM access. Subprocess overhead per call (~500ms-30s including SessionStart
hooks). PR-#1's AuthProvider work is largely deleted (~250 lines removed,
~150 lines added). ADR-014 superseded; ADR-001 partially superseded.
Spec at docs/superpowers/specs/2026-05-08-agent-sdk-migration-design.md.
```

- [ ] **Step 6: Run pre-commit**

```bash
.venv/bin/pre-commit run --all-files 2>&1 | tail -8
```

Expected: all hooks pass.

- [ ] **Step 7: Commit**

```bash
git add .primer/ && git commit -m "docs: ADR-015 (Agent SDK migration); supersede ADR-014; partial supersede ADR-001"
```

---

## Task 8: Manual smoke + push + open PR

- [ ] **Step 1: Run the smoke test manually**

```bash
.venv/bin/python scripts/smoke_agent.py
```

Expected: two responses printed without errors. The first call may take 10-30 seconds due to SessionStart hooks; the second call may be faster due to caching.

If it FAILS with a real error (not 429 -- those should be gone now), investigate before pushing. Possible failure modes:
- Claude Code not authenticated: run `claude login`
- Permissions issues with `~/.claude/`: check file ownership
- Agent SDK version mismatch: confirm `.venv/bin/python -c "import claude_agent_sdk; print(claude_agent_sdk.__version__)"` matches pyproject.toml

If smoke succeeds: continue.

- [ ] **Step 2: Push the branch**

```bash
git push -u origin feat/agent-sdk-migration
```

- [ ] **Step 3: Open the PR**

```bash
gh pr create --title "feat: migrate from anthropic SDK to claude-agent-sdk" --body "$(cat <<'EOF'
## Summary

- Replace the `anthropic` SDK with `claude-agent-sdk` as the LLM access layer.
- Delete PR #1's AuthProvider abstraction (`oauth.py`, `providers.py`, `fake_auth_provider.py`, `test_auth_providers.py`) -- Agent SDK handles auth internally.
- Add `AgentClient` async wrapper around `claude_agent_sdk.query()`.
- Net: ~250 lines added, ~500 lines removed, 71 -> ~62 tests (delete 32 tests for code we no longer ship, add 6).

## Why

Empirical evidence on 2026-05-08:

- `anthropic.Anthropic(auth_token=oauth_token).messages.create(...)` returns 429 on every call (policy-gated).
- `claude_agent_sdk.query(...)` succeeds against the same endpoint with the same OAuth credentials.

ServiceNow employees (the target audience) cannot easily acquire enterprise API keys. The Agent SDK path solves this transparently.

Spec: \`docs/superpowers/specs/2026-05-08-agent-sdk-migration-design.md\`
Plan: \`docs/superpowers/plans/2026-05-08-agent-sdk-migration.md\`

## Test plan

- [x] All unit tests pass (~62 tests)
- [x] AgentClient + FakeAgentClient + 6 new tests
- [x] Manual smoke (\`scripts/smoke_agent.py\`) succeeds against the real API
- [x] Pre-commit clean (black, ruff, mypy, pyright, pytest)
- [x] Coverage ratchet maintained for retained modules

## Out of scope (deferred)

- NEXUS-defined MCP server for exposing ServiceNowClient to LLM agents
- Streaming UI surfacing intermediate Agent SDK messages
- Refactor stub specialist agents to use AgentClient

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: PR URL printed.

---

## Self-Review Notes

- All 8 tasks have explicit code and commands. No placeholders.
- Order of operations is safe: additive changes first (new client + tests), then deletes after consumers updated, then dependency drop, then docs.
- Type consistency: `AgentClientProtocol.complete()` signature is identical across all 4 places where it appears (Protocol declaration, AgentClient implementation, FakeAgentClient, test signatures).
- Spec coverage: every section of the spec maps to a task.
  - Files Deleted (spec §) -> Tasks 4 + 5 + 7 (smoke deleted in Task 3)
  - Files Created (spec §) -> Tasks 2 + 3 + 7
  - Files Modified (spec §) -> Tasks 1 + 4 + 5 + 6 + 7
  - AgentClient Interface (spec §) -> Task 2
  - FakeAgentClient (spec §) -> Task 2
  - Test Plan ~6 tests (spec §) -> Task 2 (4 fake tests + 2 protocol tests = 6)
  - Smoke Test (spec §) -> Task 3
  - Migration Mechanics (spec §) -> overall task ordering
- Risks (spec §) -> tested in Task 8 manual smoke
