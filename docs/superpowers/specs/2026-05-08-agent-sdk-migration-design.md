# Migrate from anthropic SDK to claude-agent-sdk -- Design Spec
# Author: Pierre Grothe
# Date: 2026-05-08

## Overview

Replace the `anthropic` SDK with `claude-agent-sdk` as the LLM access layer.
The `anthropic` SDK's `auth_token=` Bearer auth path (which we built in PR #1
for OAuth users) is policy-gated by Anthropic at `/v1/messages`. The Claude
Agent SDK -- an Anthropic-published SDK that wraps the bundled Claude Code CLI
internally -- successfully calls the same endpoint using the user's stored
Claude Code credentials (verified empirically with a 10-line smoke test).

This spec deletes the AnthropicClient + AuthProvider abstraction added in PR #1
and replaces it with a thin async wrapper around `claude_agent_sdk.query()`.

## Why

Empirical evidence from 2026-05-08:

- `anthropic.Anthropic(auth_token=oauth_token)` -> `client.models.list()` returns 200,
  `client.messages.create()` returns 429 every time (policy gate, not transient).
- `claude_agent_sdk.query(prompt="...")` succeeds against the same endpoint with
  the same OAuth credentials (no API key set), returns a real assistant message
  with prompt caching active and access to Opus 4.7 with 1M context.

The user (Pierre) cannot easily acquire an Anthropic API key from ServiceNow's
enterprise process. The audience (ServiceNow colleagues) similarly cannot.
Without Agent SDK, NEXUS is unusable for its target audience. With Agent SDK,
NEXUS works for any user who has Claude Code installed and authenticated --
which is the same audience.

## Scope

Net code reduction. PR #1's AuthProvider abstraction was built around the
constraint that `anthropic.Anthropic` takes either `api_key=` or `auth_token=`,
and we needed to choose at construction time. Agent SDK removes that constraint
by handling the resolution chain internally. The abstraction becomes redundant
and is deleted.

Architectural impact:

- **ADR-015 (NEW)**: Migrate from anthropic SDK to claude-agent-sdk.
- **ADR-014 (Pluggable AuthProvider)**: Marked SUPERSEDED by ADR-015.
- **ADR-001 (API-direct, no Claude Code dependency)**: PARTIALLY SUPERSEDED.
  NEXUS still ships as a pip package and is invoked as `nexus <command>`, but
  Agent SDK bundles Claude Code CLI as a subprocess under the hood. The
  user-facing distribution is unchanged; the implementation calls Claude Code
  internally for LLM access. Documented in ADR-015.

---

## Files Deleted

```
src/nexus/api/client.py              -- AnthropicClient + ModelTier auto-discovery + Protocols
src/nexus/api/tool_registry.py       -- ToolRegistry (LLM only sees enterprise MCP now)
src/nexus/auth/oauth.py              -- ClaudeCodeOAuthProvider
src/nexus/auth/providers.py          -- AuthProvider Protocol + factory + AnthropicAPIKeyProvider alias
tests/fakes/fake_anthropic_client.py -- replaced by FakeAgentClient
tests/fakes/fake_auth_provider.py    -- no abstraction to fake
tests/test_auth_providers.py         -- module deleted
tests/test_api_client.py             -- replaced by test_agent_client.py
scripts/smoke_anthropic.py           -- replaced by scripts/smoke_agent.py
```

## Files Created

```
src/nexus/api/agent_client.py        -- AgentClient + AgentClientProtocol
tests/fakes/fake_agent_client.py     -- FakeAgentClient
tests/test_agent_client.py           -- ~6 tests covering AgentClient
.primer/adr/ADR-015-claude-agent-sdk-migration.md
scripts/smoke_agent.py               -- end-to-end smoke test using new client
```

## Files Modified

```
pyproject.toml
  - Drop: anthropic = ">=0.50"
  + Add:  claude-agent-sdk = ">=0.1"
src/nexus/api/__init__.py            -- export AgentClient, AgentClientProtocol only
src/nexus/api/errors.py              -- keep (still useful for explicit error mapping)
src/nexus/auth/claude.py             -- revert to pre-PR-#1 shape (no Protocol methods)
src/nexus/auth/__init__.py           -- drop AuthProvider exports; keep ClaudeAuth, KeychainClient, SNAuth, AuthError
tests/test_auth.py                   -- remove 3 PR-#1-added tests (Protocol methods)
.ratchet.json                        -- remove deleted modules; add new agent_client baseline
.primer/adr/ADR-014-pluggable-auth-provider.md  -- update Status to SUPERSEDED by ADR-015
.primer/adr/ADR-001-api-direct-architecture.md  -- update with PARTIAL SUPERSEDED note
.primer/governance.md                -- update ADR Catalog (mark 014 superseded, add 015)
.primer/decisions.md                 -- append ADR-015 entry
CLAUDE.md                            -- update Anthropic SDK reference
```

---

## AgentClient Interface

```python
# src/nexus/api/agent_client.py

from typing import Protocol

__all__ = ["AgentClient", "AgentClientProtocol"]


class AgentClientProtocol(Protocol):
    """Async LLM client interface for NEXUS agents and CLI commands.

    Implementations route LLM calls through claude-agent-sdk, which handles
    authentication automatically (env var > Claude Code credentials).
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
            model: Optional model ID (e.g. "claude-sonnet-4-6"). If None,
                Agent SDK picks the default for the user's session.
            max_turns: Maximum agent turns (tool-call rounds). Default 1.

        Returns:
            Concatenated text from all AssistantMessage TextBlocks in the
            response stream.

        Raises:
            AnthropicError: When the underlying API returns an error.
        """
        ...


class AgentClient:
    """LLM client backed by claude-agent-sdk.

    Auth is handled internally by claude-agent-sdk's session_resume:
      - ANTHROPIC_API_KEY env var
      - CLAUDE_CODE_OAUTH_TOKEN env var
      - ~/.claude/.credentials.json
      - macOS Keychain "Claude Code-credentials"
    """

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

All imports (`query`, `ClaudeAgentOptions`, `AssistantMessage`, `ResultMessage`,
`TextBlock`, `AnthropicError`) live at module level -- no deferred imports
inside method bodies. The implementation plan will list them explicitly.

## FakeAgentClient

```python
# tests/fakes/fake_agent_client.py

from dataclasses import dataclass, field

__all__ = ["FakeAgentClient"]


@dataclass(slots=True)
class FakeAgentClient:
    """Test double for AgentClientProtocol.

    Records every call and returns a canned response. No subprocess, no Agent SDK.
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

## Test Plan (~6 tests)

```python
# tests/test_agent_client.py

import pytest

from nexus.api.agent_client import AgentClient, AgentClientProtocol
from nexus.api.errors import AnthropicError
from tests.fakes.fake_agent_client import FakeAgentClient


@pytest.mark.asyncio
async def test_fake_agent_client_records_calls() -> None:
    client = FakeAgentClient()
    result = await client.complete("hello", system="You are terse.")
    assert result == "ok"
    assert client.calls == [{
        "prompt": "hello", "system": "You are terse.",
        "model": None, "max_turns": 1,
    }]


@pytest.mark.asyncio
async def test_fake_agent_client_returns_canned() -> None:
    client = FakeAgentClient(canned_response="custom")
    assert await client.complete("anything") == "custom"


@pytest.mark.asyncio
async def test_fake_agent_client_raises_side_effect() -> None:
    client = FakeAgentClient(side_effect=AnthropicError(429, "rate limit"))
    with pytest.raises(AnthropicError):
        await client.complete("hello")


def test_agent_client_protocol_satisfied_by_real_client() -> None:
    """Static assertion: AgentClient structurally implements AgentClientProtocol."""
    client: AgentClientProtocol = AgentClient()
    assert hasattr(client, "complete")


def test_agent_client_protocol_satisfied_by_fake() -> None:
    """Static assertion: FakeAgentClient structurally implements AgentClientProtocol."""
    fake: AgentClientProtocol = FakeAgentClient()
    assert hasattr(fake, "complete")


@pytest.mark.skip(reason="Integration test: requires Claude Code authenticated. Run manually.")
@pytest.mark.asyncio
async def test_agent_client_real_call() -> None:
    client = AgentClient()
    result = await client.complete("Say 'integration ok' and nothing else.")
    assert "integration ok" in result.lower()
```

The `test_agent_client_real_call` test is skipped by default. Manual integration
runs invoke `pytest -m integration` (after setting an `integration` marker on the
test) or `python scripts/smoke_agent.py` directly.

## Smoke Test

```python
# scripts/smoke_agent.py

"""End-to-end smoke test for the new AgentClient against the real Agent SDK."""

import asyncio
import logging
import sys

from nexus.api.agent_client import AgentClient


async def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s -- %(message)s")
    log = logging.getLogger("smoke-agent")

    client = AgentClient()
    log.info("Sending first call (cache write expected)...")
    msg1 = await client.complete(
        "What is NEXUS?",
        system="You are a terse assistant. Answer in one short sentence. "
               "If asked about NEXUS, say it is a ServiceNow AI architect tool.",
    )
    print("Response 1:", msg1)

    log.info("Sending second call (cache read expected)...")
    msg2 = await client.complete(
        "What is the capital of France?",
        system="You are a terse assistant. Answer in one short sentence. "
               "If asked about NEXUS, say it is a ServiceNow AI architect tool.",
    )
    print("Response 2:", msg2)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
```

Manual run: `.venv/bin/python scripts/smoke_agent.py`. Expected: two successful
text responses (no errors, no rate-limit exceptions).

## Migration Mechanics

**Branch:** `feat/agent-sdk-migration` (already created from main).

**Order of operations** (safe ordering avoids momentary broken state on disk):

1. Add `claude-agent-sdk` dep to pyproject.toml; install.
2. Create new `agent_client.py`, `fake_agent_client.py`, `test_agent_client.py`.
3. Verify new tests pass.
4. Delete old files (`client.py`, `tool_registry.py`, `oauth.py`, `providers.py`,
   `fake_anthropic_client.py`, `fake_auth_provider.py`, `test_auth_providers.py`,
   `test_api_client.py`, `smoke_anthropic.py`).
5. Update `auth/__init__.py`, `auth/claude.py`, `tests/test_auth.py` to drop PR-#1 additions.
6. Update `api/__init__.py` to export new types.
7. Drop `anthropic = ">=0.50"` from pyproject.toml; reinstall.
8. Update `.ratchet.json`: remove deleted module entries; add `nexus.api.agent_client`.
9. Write `ADR-015`. Update `ADR-014` and `ADR-001` headers.
10. Update `governance.md` ADR catalog. Append `decisions.md` entry.
11. Run full pre-commit gauntlet. Fix any issues.
12. Manual smoke: run `python scripts/smoke_agent.py` and verify success.
13. Push branch, open PR.

## Out of Scope (deferred)

- **Tool use via NEXUS-defined MCP server.** Hybrid approach chosen: NEXUS REST
  is direct Python; LLM agents see only the user's enterprise MCP servers.
  When/if NEXUS needs to expose its own tools to the LLM, an in-process MCP
  server can be added.
- **Streaming UI.** AgentClient returns the final text. If a CLI command wants
  live progress (e.g., during a long agent run), it can be added by exposing a
  `stream_query()` method on AgentClient that yields messages directly. Not in
  this migration.
- **Refactor agent specialists** to use AgentClient. The specialists are still
  stubs; they will be implemented in 2026.07 directly against AgentClient.
- **CI integration tests with real Anthropic API.** Skipped because CI doesn't
  have Claude Code authenticated. Manual smoke is sufficient for now; a
  GitHub-Actions-only API key path can be added later if needed.

## Risks

1. **Agent SDK init overhead.** Each `query()` spins up the bundled Claude Code
   subprocess (~500ms-2s) plus runs SessionStart hooks (~10-30s if many primer
   files exist). For one-shot CLI commands this is acceptable; for tight loops
   it would not be. Mitigation: cache an `AgentClient` instance and reuse it
   across calls within a single CLI invocation; multi-turn requests use
   `max_turns=` to amortize the init cost.

2. **Agent SDK ergonomics differ from anthropic SDK.** Some behaviors are less
   transparent: model selection, system prompt handling, tool result parsing.
   First implementation may need tuning.

3. **Subprocess dependency on Claude Code CLI.** Agent SDK bundles a Claude Code
   binary; we don't ship our own. If Anthropic changes the bundle structure,
   we'd need to upgrade. Pin `claude-agent-sdk` version to control rollover.

4. **CI cannot run end-to-end tests.** Without Claude Code auth in CI, only
   unit tests with FakeAgentClient run. Real integration testing happens
   manually on the maintainer's machine.
