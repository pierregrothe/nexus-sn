# Tier Detection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detect a NEXUS user's Tier (Anonymous / Pro / Enterprise) from Claude Code's OAuth subscription claim plus org-MCP config files, surface the result via `nexus status`, and provide a `nexus reauth` command for re-authenticating MCP servers that need it.

**Architecture:** Extend the existing `src/nexus/capabilities/` layer with `tier.py` (Tier enum + TierDetector), `claude_config.py` (file/keychain reader), and `status_reporter.py` (Rich panel). The detector caches with `@cached(persist=True, namespace="capabilities", ttl=86400)`. No live MCP probing -- the OAuth claim plus `claudeAiMcpEverConnected` is sufficient.

**Tech Stack:** Python 3.14, existing `keyring` dep (cross-platform credential store), existing `rich` dep (panel rendering), existing `typer` dep (CLI), `@cached` decorator from ADR-017.

---

## File Map

```
ADD:
  src/nexus/capabilities/tier.py              -- Tier enum, TierDetection, TierDetector
  src/nexus/capabilities/claude_config.py     -- ClaudeCodeConfig + reader Protocol + concrete reader
  src/nexus/capabilities/status_reporter.py   -- StatusReporter (Rich panel + table)
  tests/test_capabilities_claude_config.py
  tests/test_capabilities_tier.py
  tests/test_capabilities_status.py
  tests/test_cli_status.py
  tests/fakes/fake_claude_config.py
  .primer/adr/ADR-018-tier-detection.md

MODIFY:
  src/nexus/capabilities/feature_flags.py     -- add MCPServer.MARKETING; add _CLAUDE_AI_NAME_TO_SERVER + claude_ai_name_for()
  src/nexus/capabilities/registry.py          -- extend CapabilitySet (tier, needs_reauth) + from_detection()
  src/nexus/capabilities/__init__.py          -- export Tier, TierDetector, TierDetection, ClaudeCodeConfig, StatusReporter, claude_ai_name_for
  src/nexus/cli.py                            -- replace status() body; add reauth() command
  tests/fakes/__init__.py                     -- export FakeClaudeCodeConfig
  tests/test_capabilities.py                  -- add CapabilitySet.from_detection tests
  .ratchet.json                               -- add tier/claude_config/status_reporter; bump registry/feature_flags/cli
  .primer/governance.md                       -- add ADR-018 to catalog
  .primer/decisions.md                        -- append ADR-018 entry
```

---

## Task 1: Add MCPServer.MARKETING + name mapping table

**Files:**
- Modify: `src/nexus/capabilities/feature_flags.py`
- Modify: `tests/test_capabilities.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_capabilities.py`:

```python
from nexus.capabilities.feature_flags import (
    _CLAUDE_AI_NAME_TO_SERVER,
    MCPServer,
    claude_ai_name_for,
)


def test_claude_ai_name_table_contains_all_known_servers() -> None:
    assert "claude.ai ValueMelody" in _CLAUDE_AI_NAME_TO_SERVER
    assert _CLAUDE_AI_NAME_TO_SERVER["claude.ai ValueMelody"] is MCPServer.VALUE_MELODY


def test_claude_ai_name_table_includes_marketing_mcp() -> None:
    assert _CLAUDE_AI_NAME_TO_SERVER["claude.ai Marketing MCP"] is MCPServer.MARKETING


def test_claude_ai_name_for_returns_string_form() -> None:
    assert claude_ai_name_for(MCPServer.BT1) == "claude.ai BT1_MCP"
    assert claude_ai_name_for(MCPServer.MARKETING) == "claude.ai Marketing MCP"


def test_claude_ai_name_for_raises_for_unmapped_server() -> None:
    # MCPServer is exhaustively covered; this guards against future enum additions
    # without table updates. We can't test it without an unmapped value, so we
    # just assert every enum member is in the inverse table.
    inverse = {server for server in _CLAUDE_AI_NAME_TO_SERVER.values()}
    for server in MCPServer:
        assert server in inverse, f"missing claude.ai name mapping for {server}"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/test_capabilities.py -v --override-ini="addopts="
```

Expected: import errors for `_CLAUDE_AI_NAME_TO_SERVER`, `claude_ai_name_for`, and `MCPServer.MARKETING`.

- [ ] **Step 3: Add MCPServer.MARKETING and the mapping to feature_flags.py**

Read `src/nexus/capabilities/feature_flags.py` first. Find the `MCPServer` enum and add `MARKETING = "marketing"` to it. Then add the mapping table and helper at module level (after FEATURE_MAP).

Snippet to add to MCPServer enum body (next to existing entries):

```python
    MARKETING = "marketing"
```

Snippet to append at the bottom of the file (after FEATURE_MAP):

```python
_CLAUDE_AI_NAME_TO_SERVER: dict[str, MCPServer] = {
    "claude.ai ValueMelody": MCPServer.VALUE_MELODY,
    "claude.ai Sales Success Center Content Retriever": MCPServer.SSC,
    "claude.ai BT1_MCP": MCPServer.BT1,
    "claude.ai Data_Analytics_Connection": MCPServer.DATA_ANALYTICS,
    "claude.ai GTM MCP": MCPServer.GTM,
    "claude.ai Microsoft 365": MCPServer.M365,
    "claude.ai Marketing MCP": MCPServer.MARKETING,
}

_SERVER_TO_CLAUDE_AI_NAME: dict[MCPServer, str] = {
    server: name for name, server in _CLAUDE_AI_NAME_TO_SERVER.items()
}


def claude_ai_name_for(server: MCPServer) -> str:
    """Return the claude.ai-side string for a given MCPServer enum value.

    Used by `nexus reauth` to construct the exact `claude /mcp <NAME>` command.

    Args:
        server: The MCPServer enum member.

    Returns:
        The "claude.ai <Name>" string used by Claude Code.

    Raises:
        KeyError: If the server has no mapping (a new MCPServer was added
            without updating `_CLAUDE_AI_NAME_TO_SERVER`).
    """
    return _SERVER_TO_CLAUDE_AI_NAME[server]
```

Update `__all__` in feature_flags.py to include the new helper:

```python
__all__ = ["FEATURE_MAP", "FeatureFlag", "MCPServer", "ServerSpec", "claude_ai_name_for"]
```

(Do NOT export `_CLAUDE_AI_NAME_TO_SERVER` -- the underscore prefix marks it private; tests reach in directly which is allowed by the test files' wider access.)

- [ ] **Step 4: Update FEATURE_MAP for MCPServer.MARKETING**

Find the `FEATURE_MAP: dict[MCPServer, ServerSpec]` and add an entry for MCPServer.MARKETING. Marketing MCP doesn't gate any existing FeatureFlag (it's adjunct), so use an empty features tuple:

```python
    MCPServer.MARKETING: ServerSpec(
        name="Marketing MCP",
        description="Marketing operations (Marketo, campaign analytics).",
        features=(),
    ),
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
.venv/bin/pytest tests/test_capabilities.py -v --override-ini="addopts="
```

Expected: all tests pass (the existing tests + 4 new).

- [ ] **Step 6: Lint + types**

```bash
.venv/bin/ruff check src/nexus/capabilities/feature_flags.py tests/test_capabilities.py
.venv/bin/mypy src/nexus/capabilities/feature_flags.py
.venv/bin/pyright src/nexus/capabilities/feature_flags.py tests/test_capabilities.py
```

Expected: 0 violations, 0 errors.

- [ ] **Step 7: Commit**

```bash
git add src/nexus/capabilities/feature_flags.py tests/test_capabilities.py && git commit -m "feat(capabilities): add MCPServer.MARKETING + claude.ai name mapping"
```

---

## Task 2: ClaudeCodeConfig dataclass + Protocol

**Files:**
- Create: `src/nexus/capabilities/claude_config.py`
- Create: `tests/test_capabilities_claude_config.py`

This task introduces the **types only** (frozen dataclass + Protocol). The concrete reader lands in Task 3.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_capabilities_claude_config.py`:

```python
# tests/test_capabilities_claude_config.py
# Tests for ClaudeCodeConfig types and the filesystem reader.
# Author: Pierre Grothe
# Date: 2026-05-08
"""Tests for nexus.capabilities.claude_config."""

from nexus.capabilities.claude_config import ClaudeCodeConfig, ClaudeCodeConfigReader


def test_claude_code_config_default_construction() -> None:
    cfg = ClaudeCodeConfig(
        subscription_type=None,
        org_mcp_servers=(),
        needs_reauth=(),
    )
    assert cfg.subscription_type is None
    assert cfg.org_mcp_servers == ()
    assert cfg.needs_reauth == ()


def test_claude_code_config_is_frozen() -> None:
    cfg = ClaudeCodeConfig(subscription_type="enterprise", org_mcp_servers=(), needs_reauth=())
    import dataclasses
    with pytest.raises(dataclasses.FrozenInstanceError):
        cfg.subscription_type = "pro"  # type: ignore[misc]


def test_claude_code_config_reader_protocol_satisfied_by_simple_reader() -> None:
    """A minimal reader class structurally satisfies the Protocol."""
    class _OneShot:
        def read(self) -> ClaudeCodeConfig:
            return ClaudeCodeConfig(subscription_type=None, org_mcp_servers=(), needs_reauth=())

    reader: ClaudeCodeConfigReader = _OneShot()
    assert reader.read().subscription_type is None
```

(Note: the second test uses `# type: ignore[misc]` which is project-blocked. Use the workaround pattern from the @cached test: bind the variable through Any.)

Replace the second test with:

```python
def test_claude_code_config_is_frozen() -> None:
    import dataclasses
    cfg = ClaudeCodeConfig(subscription_type="enterprise", org_mcp_servers=(), needs_reauth=())
    cfg_any: Any = cfg
    with pytest.raises(dataclasses.FrozenInstanceError):
        cfg_any.subscription_type = "pro"
```

And add `from typing import Any` and `import pytest` to the imports.

Final imports section:

```python
import dataclasses
from typing import Any

import pytest

from nexus.capabilities.claude_config import ClaudeCodeConfig, ClaudeCodeConfigReader
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/test_capabilities_claude_config.py -v --override-ini="addopts="
```

Expected: ImportError on `nexus.capabilities.claude_config`.

- [ ] **Step 3: Create claude_config.py with types and Protocol**

Create `src/nexus/capabilities/claude_config.py`:

```python
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

from dataclasses import dataclass
from typing import Protocol

__all__ = ["ClaudeCodeConfig", "ClaudeCodeConfigReader"]


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
```

- [ ] **Step 4: Update __init__.py to export the new types**

Read `src/nexus/capabilities/__init__.py`. Add the new exports:

```python
from nexus.capabilities.claude_config import ClaudeCodeConfig, ClaudeCodeConfigReader
```

And add `"ClaudeCodeConfig"`, `"ClaudeCodeConfigReader"` to `__all__` in alphabetical order.

- [ ] **Step 5: Run tests + lint**

```bash
.venv/bin/pytest tests/test_capabilities_claude_config.py -v --override-ini="addopts="
.venv/bin/ruff check src/nexus/capabilities/claude_config.py tests/test_capabilities_claude_config.py
.venv/bin/mypy src/nexus/capabilities/claude_config.py
.venv/bin/pyright src/nexus/capabilities/claude_config.py
```

Expected: 3 tests pass; 0 violations; 0 errors.

- [ ] **Step 6: Commit**

```bash
git add src/nexus/capabilities/claude_config.py src/nexus/capabilities/__init__.py tests/test_capabilities_claude_config.py && git commit -m "feat(capabilities): add ClaudeCodeConfig dataclass and reader Protocol"
```

---

## Task 3: FilesystemClaudeCodeConfigReader

**Files:**
- Modify: `src/nexus/capabilities/claude_config.py`
- Modify: `tests/test_capabilities_claude_config.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_capabilities_claude_config.py`. After ruff's import
sort, the new imports merge with the existing imports at the top of the
file. The test functions go at the bottom.

New imports to add (ruff will reorder/merge):

```python
import json
from pathlib import Path

from nexus.capabilities.claude_config import FilesystemClaudeCodeConfigReader
from tests.fakes.fake_keychain import FakeKeychainClient


def test_filesystem_reader_reads_subscription_from_keychain(tmp_path: Path) -> None:
    keychain = FakeKeychainClient(
        {("Claude Code-credentials", "alice"): json.dumps(
            {"claudeAiOauth": {"subscriptionType": "enterprise"}}
        )},
    )
    reader = FilesystemClaudeCodeConfigReader(keychain=keychain, home=tmp_path, os_user="alice")
    cfg = reader.read()
    assert cfg.subscription_type == "enterprise"


def test_filesystem_reader_falls_back_to_credentials_file_when_keychain_missing(
    tmp_path: Path,
) -> None:
    creds_file = tmp_path / ".claude" / ".credentials.json"
    creds_file.parent.mkdir(parents=True)
    creds_file.write_text(
        json.dumps({"claudeAiOauth": {"subscriptionType": "pro"}}), encoding="utf-8"
    )
    reader = FilesystemClaudeCodeConfigReader(
        keychain=FakeKeychainClient(), home=tmp_path, os_user="alice"
    )
    cfg = reader.read()
    assert cfg.subscription_type == "pro"


def test_filesystem_reader_returns_none_subscription_when_no_sources(tmp_path: Path) -> None:
    reader = FilesystemClaudeCodeConfigReader(
        keychain=FakeKeychainClient(), home=tmp_path, os_user="alice"
    )
    cfg = reader.read()
    assert cfg.subscription_type is None


def test_filesystem_reader_handles_malformed_keychain_payload(tmp_path: Path) -> None:
    keychain = FakeKeychainClient(
        {("Claude Code-credentials", "alice"): "not json"},
    )
    reader = FilesystemClaudeCodeConfigReader(keychain=keychain, home=tmp_path, os_user="alice")
    cfg = reader.read()
    assert cfg.subscription_type is None


def test_filesystem_reader_reads_org_mcp_servers_from_claude_json(tmp_path: Path) -> None:
    claude_json = tmp_path / ".claude.json"
    claude_json.write_text(
        json.dumps(
            {"claudeAiMcpEverConnected": ["claude.ai ValueMelody", "claude.ai BT1_MCP"]}
        ),
        encoding="utf-8",
    )
    reader = FilesystemClaudeCodeConfigReader(
        keychain=FakeKeychainClient(), home=tmp_path, os_user="alice"
    )
    cfg = reader.read()
    assert cfg.org_mcp_servers == ("claude.ai ValueMelody", "claude.ai BT1_MCP")


def test_filesystem_reader_returns_empty_org_mcp_when_claude_json_missing(tmp_path: Path) -> None:
    reader = FilesystemClaudeCodeConfigReader(
        keychain=FakeKeychainClient(), home=tmp_path, os_user="alice"
    )
    cfg = reader.read()
    assert cfg.org_mcp_servers == ()


def test_filesystem_reader_handles_malformed_claude_json(tmp_path: Path) -> None:
    (tmp_path / ".claude.json").write_text("not json", encoding="utf-8")
    reader = FilesystemClaudeCodeConfigReader(
        keychain=FakeKeychainClient(), home=tmp_path, os_user="alice"
    )
    cfg = reader.read()
    assert cfg.org_mcp_servers == ()


def test_filesystem_reader_reads_needs_reauth_from_cache_file(tmp_path: Path) -> None:
    cache_file = tmp_path / ".claude" / "mcp-needs-auth-cache.json"
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(
        json.dumps(
            {
                "claude.ai Marketing MCP": {"timestamp": 1, "id": "x"},
                "claude.ai Microsoft 365": {"timestamp": 2, "id": "y"},
            }
        ),
        encoding="utf-8",
    )
    reader = FilesystemClaudeCodeConfigReader(
        keychain=FakeKeychainClient(), home=tmp_path, os_user="alice"
    )
    cfg = reader.read()
    assert set(cfg.needs_reauth) == {"claude.ai Marketing MCP", "claude.ai Microsoft 365"}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/test_capabilities_claude_config.py -v --override-ini="addopts="
```

Expected: ImportError on `FilesystemClaudeCodeConfigReader`.

- [ ] **Step 3: Implement FilesystemClaudeCodeConfigReader**

Append to `src/nexus/capabilities/claude_config.py`:

```python
import getpass
import json
import logging
from pathlib import Path

from nexus.auth.errors import AuthError
from nexus.auth.keychain import KeychainClient

log = logging.getLogger(__name__)

_KEYCHAIN_SERVICE = "Claude Code-credentials"


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
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            log.warning("malformed ~/.claude.json; ignoring")
            return ()
        servers = data.get("claudeAiMcpEverConnected", [])
        if not isinstance(servers, list):
            log.warning("claudeAiMcpEverConnected is not a list; ignoring")
            return ()
        return tuple(s for s in servers if isinstance(s, str))

    def _read_needs_reauth(self) -> tuple[str, ...]:
        """Read keys of ~/.claude/mcp-needs-auth-cache.json."""
        cache_path = self._home / ".claude" / "mcp-needs-auth-cache.json"
        try:
            raw = cache_path.read_text(encoding="utf-8")
        except OSError:
            return ()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            log.warning("malformed mcp-needs-auth-cache.json; ignoring")
            return ()
        if not isinstance(data, dict):
            log.warning("mcp-needs-auth-cache.json is not a dict; ignoring")
            return ()
        return tuple(str(key) for key in data)


def _extract_subscription_type(payload: str) -> str | None:
    """Parse the OAuth payload string and return claudeAiOauth.subscriptionType.

    Returns None if the payload is malformed JSON or missing the field.
    """
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        log.warning("malformed Claude Code OAuth payload; ignoring")
        return None
    inner = data.get("claudeAiOauth")
    if not isinstance(inner, dict):
        return None
    sub = inner.get("subscriptionType")
    return sub if isinstance(sub, str) else None
```

Update `__all__` in claude_config.py:

```python
__all__ = ["ClaudeCodeConfig", "ClaudeCodeConfigReader", "FilesystemClaudeCodeConfigReader"]
```

- [ ] **Step 4: Update tests/test_capabilities_claude_config.py imports**

The new tests import `FakeKeychainClient` from `tests.fakes.fake_keychain`. Verify the import path matches the existing fake's location.

- [ ] **Step 5: Run tests + lint**

```bash
.venv/bin/pytest tests/test_capabilities_claude_config.py -v --override-ini="addopts="
.venv/bin/ruff check src/nexus/capabilities/claude_config.py tests/test_capabilities_claude_config.py
.venv/bin/mypy src/nexus/capabilities/claude_config.py
.venv/bin/pyright src/nexus/capabilities/claude_config.py
```

Expected: 11 tests pass (3 from Task 2 + 8 new); 0 violations; 0 errors.

- [ ] **Step 6: Commit**

```bash
git add src/nexus/capabilities/claude_config.py tests/test_capabilities_claude_config.py && git commit -m "feat(capabilities): FilesystemClaudeCodeConfigReader + tests"
```

---

## Task 4: Tier enum + TierDetector + FakeClaudeCodeConfig

**Files:**
- Create: `src/nexus/capabilities/tier.py`
- Create: `tests/fakes/fake_claude_config.py`
- Modify: `tests/fakes/__init__.py`
- Create: `tests/test_capabilities_tier.py`

- [ ] **Step 1: Create FakeClaudeCodeConfig**

Write `tests/fakes/fake_claude_config.py`:

```python
# tests/fakes/fake_claude_config.py
# ClaudeCodeConfigReader test double. Returns a pre-built config.
# Author: Pierre Grothe
# Date: 2026-05-08
"""FakeClaudeCodeConfig: real fake (no mocks) for ClaudeCodeConfigReader."""

from dataclasses import dataclass

from nexus.capabilities.claude_config import ClaudeCodeConfig

__all__ = ["FakeClaudeCodeConfig"]


@dataclass(slots=True)
class FakeClaudeCodeConfig:
    """Returns a pre-built ClaudeCodeConfig from .read()."""

    config: ClaudeCodeConfig

    def read(self) -> ClaudeCodeConfig:
        """Return the stored config."""
        return self.config
```

- [ ] **Step 2: Update tests/fakes/__init__.py**

Read tests/fakes/__init__.py first. Add FakeClaudeCodeConfig to imports + __all__.

Final content:

```python
# tests/fakes/__init__.py
# Fake implementations used in tests. No mocks anywhere.
# Author: Pierre Grothe
# Date: 2026-05-07
"""Fake connectors and clients for use in tests."""

from tests.fakes.fake_agent_client import FakeAgentClient
from tests.fakes.fake_cache_backend import FakeCacheBackend
from tests.fakes.fake_claude_config import FakeClaudeCodeConfig
from tests.fakes.fake_clock import FakeClock
from tests.fakes.fake_keychain import FakeKeychainClient
from tests.fakes.fake_sn_client import FakeServiceNowClient

__all__ = [
    "FakeAgentClient",
    "FakeCacheBackend",
    "FakeClaudeCodeConfig",
    "FakeClock",
    "FakeKeychainClient",
    "FakeServiceNowClient",
]
```

- [ ] **Step 3: Write the failing tests**

Create `tests/test_capabilities_tier.py`:

```python
# tests/test_capabilities_tier.py
# Tests for nexus.capabilities.tier.
# Author: Pierre Grothe
# Date: 2026-05-08
"""Tests for the Tier enum and TierDetector."""

from nexus.cache import clear_cache
from nexus.capabilities.claude_config import ClaudeCodeConfig
from nexus.capabilities.feature_flags import MCPServer
from nexus.capabilities.tier import Tier, TierDetection, TierDetector
from tests.fakes.fake_claude_config import FakeClaudeCodeConfig


def _detect(config: ClaudeCodeConfig) -> TierDetection:
    clear_cache(TierDetector.detect)  # ensure cache miss for each test
    detector = TierDetector(reader=FakeClaudeCodeConfig(config=config))
    return detector.detect()


def test_tier_detector_returns_anonymous_when_no_credentials_and_no_org_mcp() -> None:
    detection = _detect(
        ClaudeCodeConfig(subscription_type=None, org_mcp_servers=(), needs_reauth=())
    )
    assert detection.tier is Tier.ANONYMOUS
    assert detection.detected_servers == frozenset()


def test_tier_detector_returns_pro_for_authenticated_no_org_mcp() -> None:
    detection = _detect(
        ClaudeCodeConfig(subscription_type="pro", org_mcp_servers=(), needs_reauth=())
    )
    assert detection.tier is Tier.PRO


def test_tier_detector_returns_enterprise_for_enterprise_claim() -> None:
    detection = _detect(
        ClaudeCodeConfig(subscription_type="enterprise", org_mcp_servers=(), needs_reauth=())
    )
    assert detection.tier is Tier.ENTERPRISE


def test_tier_detector_overrides_pro_to_enterprise_when_org_mcp_present() -> None:
    """Org MCP presence is the strongest signal; it wins over the OAuth claim."""
    detection = _detect(
        ClaudeCodeConfig(
            subscription_type="pro",
            org_mcp_servers=("claude.ai BT1_MCP",),
            needs_reauth=(),
        )
    )
    assert detection.tier is Tier.ENTERPRISE


def test_tier_detector_overrides_anonymous_to_enterprise_when_org_mcp_present() -> None:
    detection = _detect(
        ClaudeCodeConfig(
            subscription_type=None,
            org_mcp_servers=("claude.ai ValueMelody",),
            needs_reauth=(),
        )
    )
    assert detection.tier is Tier.ENTERPRISE


def test_tier_detector_maps_recognized_org_servers() -> None:
    detection = _detect(
        ClaudeCodeConfig(
            subscription_type="enterprise",
            org_mcp_servers=(
                "claude.ai ValueMelody",
                "claude.ai BT1_MCP",
                "claude.ai Microsoft 365",
            ),
            needs_reauth=(),
        )
    )
    assert detection.detected_servers == frozenset(
        {MCPServer.VALUE_MELODY, MCPServer.BT1, MCPServer.M365}
    )


def test_tier_detector_drops_unrecognized_org_server_names() -> None:
    detection = _detect(
        ClaudeCodeConfig(
            subscription_type="enterprise",
            org_mcp_servers=("claude.ai ValueMelody", "claude.ai SomethingNew"),
            needs_reauth=(),
        )
    )
    assert detection.detected_servers == frozenset({MCPServer.VALUE_MELODY})


def test_tier_detector_maps_needs_reauth_servers() -> None:
    detection = _detect(
        ClaudeCodeConfig(
            subscription_type="enterprise",
            org_mcp_servers=("claude.ai Marketing MCP",),
            needs_reauth=("claude.ai Marketing MCP",),
        )
    )
    assert detection.needs_reauth_servers == frozenset({MCPServer.MARKETING})


def test_tier_detector_unknown_subscription_falls_back_to_pro() -> None:
    detection = _detect(
        ClaudeCodeConfig(subscription_type="team", org_mcp_servers=(), needs_reauth=())
    )
    assert detection.tier is Tier.PRO


def test_tier_detection_carries_raw_config() -> None:
    cfg = ClaudeCodeConfig(
        subscription_type="enterprise", org_mcp_servers=("claude.ai BT1_MCP",), needs_reauth=()
    )
    detection = _detect(cfg)
    assert detection.config == cfg
```

- [ ] **Step 4: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/test_capabilities_tier.py -v --override-ini="addopts="
```

Expected: ImportError on `nexus.capabilities.tier`.

- [ ] **Step 5: Implement tier.py**

Write `src/nexus/capabilities/tier.py`:

```python
# src/nexus/capabilities/tier.py
# Tier enum + TierDetector. Detects user tier from Claude Code state.
# Author: Pierre Grothe
# Date: 2026-05-08
"""Tier detection (ADR-018).

Anonymous = no Claude OAuth (API-key-only or unauthenticated).
Pro       = authenticated Claude account, no Enterprise MCP servers.
Enterprise = Claude Enterprise + ServiceNow MCP servers provisioned.
"""

import logging
from dataclasses import dataclass
from enum import StrEnum

from nexus.cache import cached
from nexus.capabilities.claude_config import ClaudeCodeConfig, ClaudeCodeConfigReader
from nexus.capabilities.feature_flags import _CLAUDE_AI_NAME_TO_SERVER, MCPServer

log = logging.getLogger(__name__)

__all__ = ["Tier", "TierDetection", "TierDetector"]


class Tier(StrEnum):
    """User capability tier derived from authentication and org MCP access."""

    ANONYMOUS = "anonymous"
    PRO = "pro"
    ENTERPRISE = "enterprise"


@dataclass(slots=True, frozen=True)
class TierDetection:
    """Resolved tier detection snapshot.

    Attributes:
        tier: The resolved Tier.
        config: The raw ClaudeCodeConfig used to derive the tier (kept for UI).
        detected_servers: MCPServer enum values successfully mapped from
            org_mcp_servers via _CLAUDE_AI_NAME_TO_SERVER.
        needs_reauth_servers: Subset of detected_servers currently flagged
            for re-authentication in mcp-needs-auth-cache.
    """

    tier: Tier
    config: ClaudeCodeConfig
    detected_servers: frozenset[MCPServer]
    needs_reauth_servers: frozenset[MCPServer]


class TierDetector:
    """Detect a user's NEXUS Tier from Claude Code config.

    Args:
        reader: ClaudeCodeConfigReader Protocol implementation.
    """

    def __init__(self, reader: ClaudeCodeConfigReader) -> None:
        """Initialize with a config reader."""
        self._reader = reader

    @cached(ttl=86400, persist=True, namespace="capabilities")
    def detect(self) -> TierDetection:
        """Read Claude Code config and resolve to a TierDetection.

        Caches for 24 hours on disk under namespace="capabilities".
        Tests call clear_cache(TierDetector.detect) to force a re-read.

        Returns:
            TierDetection with tier, raw config, and mapped server sets.
        """
        config = self._reader.read()
        detected = _map_servers(config.org_mcp_servers)
        needs_reauth = _map_servers(config.needs_reauth)
        tier = _resolve_tier(config.subscription_type, detected)
        log.info(
            "tier=%s; %d org MCP servers detected; %d need re-auth",
            tier,
            len(detected),
            len(needs_reauth),
        )
        return TierDetection(
            tier=tier,
            config=config,
            detected_servers=detected,
            needs_reauth_servers=needs_reauth,
        )


_KNOWN_SUBSCRIPTIONS = ("enterprise", "pro", "max")


def _resolve_tier(subscription_type: str | None, detected: frozenset[MCPServer]) -> Tier:
    """Map subscription claim + org MCP presence to a Tier.

    Org MCP presence is the strongest signal. If claudeAiMcpEverConnected is
    non-empty, the user is Enterprise regardless of the OAuth claim.
    """
    if subscription_type == "enterprise":
        initial = Tier.ENTERPRISE
    elif subscription_type is None and not detected:
        initial = Tier.ANONYMOUS
    else:
        if subscription_type not in (None, *_KNOWN_SUBSCRIPTIONS):
            log.debug("unknown subscription_type=%r; treating as Pro", subscription_type)
        initial = Tier.PRO

    if detected and initial is not Tier.ENTERPRISE:
        log.debug("org MCP servers present; upgrading tier to Enterprise")
        return Tier.ENTERPRISE
    return initial


def _map_servers(claude_ai_names: tuple[str, ...]) -> frozenset[MCPServer]:
    """Map claude.ai server-name strings to MCPServer enum values.

    Unrecognized names are dropped with a DEBUG log.
    """
    mapped: set[MCPServer] = set()
    for name in claude_ai_names:
        server = _CLAUDE_AI_NAME_TO_SERVER.get(name)
        if server is None:
            log.debug("unrecognized claude.ai MCP server name: %r", name)
            continue
        mapped.add(server)
    return frozenset(mapped)
```

- [ ] **Step 6: Run tests + lint**

```bash
.venv/bin/pytest tests/test_capabilities_tier.py -v --override-ini="addopts="
.venv/bin/ruff check src/nexus/capabilities/tier.py tests/fakes/fake_claude_config.py tests/test_capabilities_tier.py
.venv/bin/mypy src/nexus/capabilities/tier.py
.venv/bin/pyright src/nexus/capabilities/tier.py tests/fakes/fake_claude_config.py
```

Expected: 10 tests pass; 0 violations; 0 errors.

- [ ] **Step 7: Commit**

```bash
git add src/nexus/capabilities/tier.py tests/fakes/fake_claude_config.py tests/fakes/__init__.py tests/test_capabilities_tier.py && git commit -m "feat(capabilities): Tier enum + TierDetector + FakeClaudeCodeConfig"
```

---

## Task 5: Extend CapabilitySet with from_detection

**Files:**
- Modify: `src/nexus/capabilities/registry.py`
- Modify: `src/nexus/capabilities/__init__.py`
- Modify: `tests/test_capabilities.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_capabilities.py`:

```python
from nexus.capabilities.claude_config import ClaudeCodeConfig
from nexus.capabilities.feature_flags import FeatureFlag, MCPServer
from nexus.capabilities.registry import CapabilitySet
from nexus.capabilities.tier import Tier, TierDetection


def _detection(
    *, tier: Tier, detected: frozenset[MCPServer], reauth: frozenset[MCPServer] = frozenset()
) -> TierDetection:
    return TierDetection(
        tier=tier,
        config=ClaudeCodeConfig(subscription_type=None, org_mcp_servers=(), needs_reauth=()),
        detected_servers=detected,
        needs_reauth_servers=reauth,
    )


def test_capability_set_from_detection_marks_detected_as_available() -> None:
    detection = _detection(tier=Tier.ENTERPRISE, detected=frozenset({MCPServer.BT1}))
    cs = CapabilitySet.from_detection(detection)
    assert cs.tier is Tier.ENTERPRISE
    assert cs.available_servers == frozenset({MCPServer.BT1})


def test_capability_set_from_detection_marks_remainder_as_unavailable() -> None:
    detection = _detection(tier=Tier.ENTERPRISE, detected=frozenset({MCPServer.BT1}))
    cs = CapabilitySet.from_detection(detection)
    expected_unavailable = frozenset(MCPServer) - frozenset({MCPServer.BT1})
    assert cs.unavailable_servers == expected_unavailable


def test_capability_set_from_detection_unions_features_for_detected_servers() -> None:
    detection = _detection(tier=Tier.ENTERPRISE, detected=frozenset({MCPServer.VALUE_MELODY}))
    cs = CapabilitySet.from_detection(detection)
    # ValueMelody enables ROI_ANALYSIS and VE_PIPELINE per FEATURE_MAP
    assert FeatureFlag.ROI_ANALYSIS in cs.enabled_features


def test_capability_set_from_detection_carries_needs_reauth() -> None:
    detection = _detection(
        tier=Tier.ENTERPRISE,
        detected=frozenset({MCPServer.MARKETING}),
        reauth=frozenset({MCPServer.MARKETING}),
    )
    cs = CapabilitySet.from_detection(detection)
    assert cs.needs_reauth == frozenset({MCPServer.MARKETING})


def test_capability_set_from_detection_anonymous_has_no_servers() -> None:
    detection = _detection(tier=Tier.ANONYMOUS, detected=frozenset())
    cs = CapabilitySet.from_detection(detection)
    assert cs.tier is Tier.ANONYMOUS
    assert cs.available_servers == frozenset()
    assert cs.enabled_features == frozenset()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/test_capabilities.py -v --override-ini="addopts="
```

Expected: AttributeError on `CapabilitySet.from_detection` and `CapabilitySet.tier`.

- [ ] **Step 3: Extend CapabilitySet**

Read `src/nexus/capabilities/registry.py` first. Add the two new fields and the new classmethod.

Replace the dataclass body to include `tier` and `needs_reauth`:

```python
@dataclass(slots=True, frozen=True)
class CapabilitySet:
    """Immutable snapshot of available MCP features for this session.

    Attributes:
        available_servers: Servers that responded to the probe (or detection).
        unavailable_servers: Servers that timed out, errored, or are not provisioned.
        enabled_features: Feature flags that are active.
        tier: User Tier resolved from authentication + org MCP presence.
        needs_reauth: Servers currently flagged for re-authentication.
    """

    available_servers: frozenset[MCPServer]
    unavailable_servers: frozenset[MCPServer]
    enabled_features: frozenset[FeatureFlag]
    tier: Tier
    needs_reauth: frozenset[MCPServer]
```

Update the existing `from_probe_results` classmethod to set defaults for the new fields:

```python
    @classmethod
    def from_probe_results(cls, results: list[ProbeResult]) -> CapabilitySet:
        """Build a CapabilitySet from a list of probe results.

        Args:
            results: Results from MCPProbe.probe_all().

        Returns:
            CapabilitySet reflecting the current session's capabilities.
            tier defaults to Tier.PRO and needs_reauth to empty -- callers
            using the live-probe path should populate these from a separate
            TierDetection if needed.
        """
        # ... (existing body) ...
        return cls(
            available_servers=frozenset(available),
            unavailable_servers=frozenset(unavailable),
            enabled_features=frozenset(features),
            tier=Tier.PRO,
            needs_reauth=frozenset(),
        )
```

Add the new classmethod:

```python
    @classmethod
    def from_detection(cls, detection: TierDetection) -> CapabilitySet:
        """Build a CapabilitySet from a TierDetection (no live probe).

        All detected servers are considered available; remaining MCPServer
        members are unavailable. Features are unioned from FEATURE_MAP for
        each available server.

        Args:
            detection: TierDetection from TierDetector.detect().

        Returns:
            CapabilitySet with tier and needs_reauth populated.
        """
        all_servers = frozenset(MCPServer)
        unavailable = all_servers - detection.detected_servers
        features: set[FeatureFlag] = set()
        for server in detection.detected_servers:
            features.update(FEATURE_MAP[server].features)
        return cls(
            available_servers=detection.detected_servers,
            unavailable_servers=unavailable,
            enabled_features=frozenset(features),
            tier=detection.tier,
            needs_reauth=detection.needs_reauth_servers,
        )
```

Add the imports at the top of registry.py:

```python
from nexus.capabilities.feature_flags import FEATURE_MAP, FeatureFlag, MCPServer
from nexus.capabilities.probe import ProbeResult
from nexus.capabilities.tier import Tier, TierDetection
```

- [ ] **Step 4: Run tests + lint**

```bash
.venv/bin/pytest tests/test_capabilities.py -v --override-ini="addopts="
.venv/bin/ruff check src/nexus/capabilities/registry.py
.venv/bin/mypy src/nexus/capabilities/registry.py
.venv/bin/pyright src/nexus/capabilities/registry.py tests/test_capabilities.py
```

Expected: all existing + 5 new tests pass; 0 violations; 0 errors.

- [ ] **Step 5: Commit**

```bash
git add src/nexus/capabilities/registry.py src/nexus/capabilities/__init__.py tests/test_capabilities.py && git commit -m "feat(capabilities): CapabilitySet.from_detection + tier/needs_reauth fields"
```

---

## Task 6: StatusReporter (Rich panel)

**Files:**
- Create: `src/nexus/capabilities/status_reporter.py`
- Create: `tests/test_capabilities_status.py`
- Modify: `src/nexus/capabilities/__init__.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_capabilities_status.py`:

```python
# tests/test_capabilities_status.py
# Tests for StatusReporter Rich panel rendering.
# Author: Pierre Grothe
# Date: 2026-05-08
"""Tests for nexus.capabilities.status_reporter."""

from rich.console import Console

from nexus.capabilities.claude_config import ClaudeCodeConfig
from nexus.capabilities.feature_flags import MCPServer
from nexus.capabilities.registry import CapabilitySet
from nexus.capabilities.status_reporter import StatusReporter
from nexus.capabilities.tier import Tier, TierDetection


def _detection(*, tier: Tier, detected: frozenset[MCPServer], reauth: frozenset[MCPServer]) -> TierDetection:
    return TierDetection(
        tier=tier,
        config=ClaudeCodeConfig(subscription_type=None, org_mcp_servers=(), needs_reauth=()),
        detected_servers=detected,
        needs_reauth_servers=reauth,
    )


def _render(detection: TierDetection) -> str:
    capabilities = CapabilitySet.from_detection(detection)
    console = Console(record=True, width=120, force_terminal=False)
    StatusReporter(console=console).print(detection, capabilities)
    return console.export_text()


def test_status_reporter_anonymous_panel_says_anonymous() -> None:
    out = _render(_detection(tier=Tier.ANONYMOUS, detected=frozenset(), reauth=frozenset()))
    assert "Anonymous" in out


def test_status_reporter_enterprise_panel_says_enterprise_and_lists_servers() -> None:
    out = _render(
        _detection(
            tier=Tier.ENTERPRISE,
            detected=frozenset({MCPServer.VALUE_MELODY, MCPServer.BT1}),
            reauth=frozenset(),
        )
    )
    assert "Enterprise" in out
    assert "Value Melody" in out
    assert "BT1" in out


def test_status_reporter_shows_needs_reauth_footer() -> None:
    out = _render(
        _detection(
            tier=Tier.ENTERPRISE,
            detected=frozenset({MCPServer.MARKETING}),
            reauth=frozenset({MCPServer.MARKETING}),
        )
    )
    assert "needs re-auth" in out.lower() or "needs reauth" in out.lower()
    assert "nexus reauth" in out


def test_status_reporter_pro_tier_does_not_mention_servers_when_none_detected() -> None:
    out = _render(_detection(tier=Tier.PRO, detected=frozenset(), reauth=frozenset()))
    assert "Pro" in out
    # No MCP server section when nothing detected
    assert "Value Melody" not in out
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/test_capabilities_status.py -v --override-ini="addopts="
```

Expected: ImportError on `nexus.capabilities.status_reporter`.

- [ ] **Step 3: Implement status_reporter.py**

Write `src/nexus/capabilities/status_reporter.py`:

```python
# src/nexus/capabilities/status_reporter.py
# Rich-based status panel for nexus status output.
# Author: Pierre Grothe
# Date: 2026-05-08
"""StatusReporter: render a NEXUS status panel + MCP server table.

Used by `nexus status` to print the user's tier, available MCP servers,
and any servers needing re-authentication.
"""

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from nexus.capabilities.feature_flags import FEATURE_MAP, MCPServer
from nexus.capabilities.registry import CapabilitySet
from nexus.capabilities.tier import Tier, TierDetection

__all__ = ["StatusReporter"]

_TIER_LABEL: dict[Tier, str] = {
    Tier.ANONYMOUS: "Anonymous",
    Tier.PRO: "Pro",
    Tier.ENTERPRISE: "Enterprise",
}


class StatusReporter:
    """Render a NEXUS status panel.

    Args:
        console: Rich Console used for output. Tests pass a recording console.
    """

    def __init__(self, console: Console) -> None:
        """See class docstring."""
        self._console = console

    def print(self, detection: TierDetection, capabilities: CapabilitySet) -> None:
        """Print the panel + optional MCP server table + re-auth footer."""
        self._console.print(self._panel(detection, capabilities))
        if detection.detected_servers or detection.needs_reauth_servers:
            self._console.print(self._server_table(detection))
        if detection.needs_reauth_servers:
            self._console.print(self._reauth_footer(detection))

    def _panel(self, detection: TierDetection, capabilities: CapabilitySet) -> Panel:
        """Build the top-level NEXUS Status panel."""
        tier_label = _TIER_LABEL[detection.tier]
        servers_total = len(MCPServer)
        servers_ready = len(capabilities.available_servers - detection.needs_reauth_servers)
        body = f"Tier: {tier_label}\n{servers_ready}/{servers_total} MCP servers ready"
        return Panel(body, title="NEXUS Status", title_align="left")

    def _server_table(self, detection: TierDetection) -> Table:
        """Build the per-server status table."""
        table = Table(title="MCP Servers", show_header=True)
        table.add_column("Server", style="bold")
        table.add_column("Status")
        table.add_column("Features")

        for server in sorted(detection.detected_servers, key=lambda s: s.value):
            spec = FEATURE_MAP[server]
            status = "needs re-auth" if server in detection.needs_reauth_servers else "ready"
            features = ", ".join(f.value for f in spec.features) or "-"
            table.add_row(spec.name, status, features)
        return table

    def _reauth_footer(self, detection: TierDetection) -> str:
        """Build the re-auth instruction line."""
        servers = sorted(s.value for s in detection.needs_reauth_servers)
        if len(servers) == 1:
            return f"Run `nexus reauth --server {servers[0]}` to fix."
        names = ", ".join(servers)
        return f"Run `nexus reauth --server <name>` for: {names}"
```

- [ ] **Step 4: Update __init__.py**

Add `from nexus.capabilities.status_reporter import StatusReporter` and `"StatusReporter"` to `__all__`.

- [ ] **Step 5: Run tests + lint**

```bash
.venv/bin/pytest tests/test_capabilities_status.py -v --override-ini="addopts="
.venv/bin/ruff check src/nexus/capabilities/status_reporter.py tests/test_capabilities_status.py
.venv/bin/mypy src/nexus/capabilities/status_reporter.py
.venv/bin/pyright src/nexus/capabilities/status_reporter.py
```

Expected: 4 tests pass; 0 violations; 0 errors.

- [ ] **Step 6: Commit**

```bash
git add src/nexus/capabilities/status_reporter.py src/nexus/capabilities/__init__.py tests/test_capabilities_status.py && git commit -m "feat(capabilities): StatusReporter Rich panel"
```

---

## Task 7: nexus status command

**Files:**
- Modify: `src/nexus/cli.py`
- Create: `tests/test_cli_status.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_cli_status.py`:

```python
# tests/test_cli_status.py
# Tests for `nexus status` and `nexus reauth` CLI commands.
# Author: Pierre Grothe
# Date: 2026-05-08
"""Tests for the status and reauth CLI commands."""

from typer.testing import CliRunner

from nexus.cache import clear_cache
from nexus.capabilities.tier import TierDetector
from nexus.cli import app

runner = CliRunner()


def test_nexus_status_command_runs_and_prints_tier(monkeypatch) -> None:
    # Ensure tests don't read this user's real ~/.claude.json
    monkeypatch.setenv("HOME", "/nonexistent-test-home")
    clear_cache(TierDetector.detect)
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    # On a non-existent home we expect Anonymous tier
    assert "Anonymous" in result.stdout or "Anonymous" in result.output
```

(Note: `monkeypatch` typing requires `pytest.MonkeyPatch` annotation.)

Final test file:

```python
# tests/test_cli_status.py
# Tests for `nexus status` and `nexus reauth` CLI commands.
# Author: Pierre Grothe
# Date: 2026-05-08
"""Tests for the status and reauth CLI commands."""

import pytest
from typer.testing import CliRunner

from nexus.cache import clear_cache
from nexus.capabilities.tier import TierDetector
from nexus.cli import app

runner = CliRunner()


def test_nexus_status_command_runs_and_prints_anonymous_for_isolated_home(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    clear_cache(TierDetector.detect)
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "Anonymous" in result.output


def test_nexus_status_refresh_clears_cache(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    clear_cache(TierDetector.detect)
    # First run populates cache
    runner.invoke(app, ["status"])
    # --refresh clears it; next run re-detects
    result = runner.invoke(app, ["status", "--refresh"])
    assert result.exit_code == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/test_cli_status.py -v --override-ini="addopts="
```

Expected: tests collect; the existing `nexus status` body returns only configured info (no tier banner).

- [ ] **Step 3: Replace the status command body**

Read `src/nexus/cli.py`. Find the `def status() -> None:` body and replace it. Add the imports at the top:

```python
from nexus.auth.keychain import KeychainClient
from nexus.cache import clear_cache
from nexus.capabilities.claude_config import FilesystemClaudeCodeConfigReader
from nexus.capabilities.registry import CapabilitySet
from nexus.capabilities.status_reporter import StatusReporter
from nexus.capabilities.tier import TierDetector
```

Replace the status command body:

```python
@app.command()
def status(
    refresh: Annotated[
        bool, typer.Option("--refresh", help="Clear the cached tier detection and re-detect")
    ] = False,
) -> None:
    """Show NEXUS tier and available enterprise MCP servers."""
    if refresh:
        clear_cache(TierDetector.detect)

    reader = FilesystemClaudeCodeConfigReader(keychain=KeychainClient())
    detection = TierDetector(reader=reader).detect()
    capabilities = CapabilitySet.from_detection(detection)
    StatusReporter(console=console).print(detection, capabilities)
```

(The existing `paths`/`manager`/`config` lookup is removed -- the new status surface is tier-focused. Config-file presence checks move to `nexus setup` when that gets implemented.)

- [ ] **Step 4: Run tests + full lint**

```bash
.venv/bin/pytest tests/test_cli_status.py -v --override-ini="addopts="
.venv/bin/ruff check src/nexus/cli.py tests/test_cli_status.py
.venv/bin/mypy src/nexus/cli.py
.venv/bin/pyright src/nexus/cli.py
```

Expected: 2 tests pass; 0 violations; 0 errors.

- [ ] **Step 5: Commit**

```bash
git add src/nexus/cli.py tests/test_cli_status.py && git commit -m "feat(cli): nexus status -- tier banner + MCP server table"
```

---

## Task 8: nexus reauth command

**Files:**
- Modify: `src/nexus/cli.py`
- Modify: `tests/test_cli_status.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cli_status.py`:

```python
def test_nexus_reauth_with_no_flagged_returns_zero(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    clear_cache(TierDetector.detect)
    result = runner.invoke(app, ["reauth"])
    assert result.exit_code == 0
    assert "All MCP servers authenticated" in result.output


def test_nexus_reauth_with_flagged_server_prints_command(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json

    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    (claude_dir / "mcp-needs-auth-cache.json").write_text(
        json.dumps({"claude.ai Marketing MCP": {"timestamp": 1, "id": "x"}}),
        encoding="utf-8",
    )
    (tmp_path / ".claude.json").write_text(
        json.dumps({"claudeAiMcpEverConnected": ["claude.ai Marketing MCP"]}),
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    clear_cache(TierDetector.detect)
    result = runner.invoke(app, ["reauth"])
    assert result.exit_code == 0
    assert "claude /mcp" in result.output
    assert "Marketing MCP" in result.output


def test_nexus_reauth_with_unknown_server_returns_one(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    clear_cache(TierDetector.detect)
    result = runner.invoke(app, ["reauth", "--server", "marketing"])
    assert result.exit_code == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/test_cli_status.py -v --override-ini="addopts="
```

Expected: command not found / 3 new tests fail.

- [ ] **Step 3: Add the reauth command**

In `src/nexus/cli.py`, add the import for the name lookup helper:

```python
from nexus.capabilities.feature_flags import MCPServer, claude_ai_name_for
```

Append the command after `status`:

```python
@app.command()
def reauth(
    server: Annotated[
        str | None,
        typer.Option(
            "--server",
            help="Name of the MCP server to re-authenticate (lowercase enum value, e.g. 'marketing')",
        ),
    ] = None,
    execute: Annotated[
        bool,
        typer.Option(
            "--execute",
            help="Run the resolved `claude /mcp ...` command via subprocess (opt-in)",
        ),
    ] = False,
) -> None:
    """Print the command to re-authenticate one or more MCP servers."""
    reader = FilesystemClaudeCodeConfigReader(keychain=KeychainClient())
    detection = TierDetector(reader=reader).detect()

    if not detection.needs_reauth_servers:
        console.print("All MCP servers authenticated. Nothing to do.")
        return

    if server is None:
        # Single flagged server: just print the command. Multiple: list each.
        sorted_servers = sorted(detection.needs_reauth_servers, key=lambda s: s.value)
        for srv in sorted_servers:
            cmd = f'claude /mcp "{claude_ai_name_for(srv)}"'
            console.print(f"  {srv.value}: {cmd}")
        return

    target = _resolve_target(server, detection.needs_reauth_servers)
    if target is None:
        err_console.print(
            f"[red]Server {server!r} is not currently flagged for re-auth.[/red] "
            f"Run `nexus status --refresh` if you think this is wrong."
        )
        raise typer.Exit(code=1)

    cmd = f'claude /mcp "{claude_ai_name_for(target)}"'
    console.print(cmd)
    if execute:
        import subprocess  # noqa: PLC0415  -- deferred to keep the dep optional

        subprocess.run(["claude", "/mcp", claude_ai_name_for(target)], check=False)


def _resolve_target(
    name: str, candidates: frozenset[MCPServer]
) -> MCPServer | None:
    """Match a user-supplied name (lowercase enum value) to a candidate server."""
    for srv in candidates:
        if srv.value == name:
            return srv
    return None
```

- [ ] **Step 4: Run tests + lint**

```bash
.venv/bin/pytest tests/test_cli_status.py -v --override-ini="addopts="
.venv/bin/ruff check src/nexus/cli.py tests/test_cli_status.py
.venv/bin/mypy src/nexus/cli.py
.venv/bin/pyright src/nexus/cli.py
```

Expected: all 5 cli tests pass; 0 violations; 0 errors.

- [ ] **Step 5: Run full pre-commit**

```bash
.venv/bin/pre-commit run --all-files
```

Expected: 6/6 hooks pass.

- [ ] **Step 6: Commit**

```bash
git add src/nexus/cli.py tests/test_cli_status.py && git commit -m "feat(cli): nexus reauth -- print one-shot re-auth command"
```

---

## Task 9: ADR-018 + governance + decisions + ratchet

**Files:**
- Create: `.primer/adr/ADR-018-tier-detection.md`
- Modify: `.primer/governance.md`
- Modify: `.primer/decisions.md`
- Modify: `.ratchet.json`

- [ ] **Step 1: Generate coverage numbers**

```bash
.venv/bin/pytest --cov=nexus --cov-report=json --cov-fail-under=0 -q --override-ini="addopts="
.venv/bin/python -c "
import json
data = json.load(open('coverage.json'))
for path, info in sorted(data['files'].items()):
    if 'capabilities' in path or '/cli.py' in path:
        s = info['summary']
        print(path, '-> covered=' + str(s['covered_lines']), 'total=' + str(s['num_statements']))
"
```

Note the numbers for: `nexus.capabilities.tier`, `nexus.capabilities.claude_config`, `nexus.capabilities.status_reporter`, plus updated baselines for `nexus.capabilities.registry`, `nexus.capabilities.feature_flags`, and `nexus.cli`.

- [ ] **Step 2: Update .ratchet.json**

Read `.ratchet.json`. Add three new entries (using the actual numbers from Step 1):

```json
    "nexus.capabilities.claude_config": {"covered_lines": <N>, "total_lines": <N>},
    "nexus.capabilities.status_reporter": {"covered_lines": <N>, "total_lines": <N>},
    "nexus.capabilities.tier": {"covered_lines": <N>, "total_lines": <N>},
```

Update existing baselines for `nexus.capabilities.feature_flags`, `nexus.capabilities.registry`, and add a new entry for `nexus.cli`.

- [ ] **Step 3: Create ADR-018**

Write `.primer/adr/ADR-018-tier-detection.md`:

```markdown
# ADR-018: Tier detection from Claude Code OAuth + org MCP config

**Status:** accepted
**Date:** 2026-05-08
**Enforcement:** none (architectural)

## Context

NEXUS already had a capabilities layer (FeatureFlag, MCPServer, FEATURE_MAP,
CapabilitySet, MCPProbe), but `_check_server` was a stub returning False, so
no features ever became available. Real detection was needed.

Three signals are available without live MCP probing:
  1. The Claude Code OAuth payload's `subscriptionType` (read from macOS
     Keychain or ~/.claude/.credentials.json).
  2. ~/.claude.json `claudeAiMcpEverConnected` -- the list of org-pushed
     MCP servers visible to this user.
  3. ~/.claude/mcp-needs-auth-cache.json -- per-server entries flagging
     re-authentication need.

Empirical investigation on 2026-05-08 (in this user's environment) confirmed
the OAuth payload directly carries `"subscriptionType": "enterprise"`. The
config and re-auth files contain the org MCP and re-auth state. No email
heuristic is needed.

## Decision

Add Tier (StrEnum: ANONYMOUS / PRO / ENTERPRISE) and TierDetector to the
existing capabilities layer. TierDetector reads the three sources via a
ClaudeCodeConfigReader Protocol and resolves a tier:

  - subscription_type == "enterprise" -> Tier.ENTERPRISE
  - subscription_type is None and no org MCP -> Tier.ANONYMOUS
  - else -> Tier.PRO
  - Override: if claudeAiMcpEverConnected is non-empty, the resolved tier
    is upgraded to Tier.ENTERPRISE regardless of the claim. Org MCP
    presence is the strongest signal.

CapabilitySet gains `tier` and `needs_reauth` fields plus a `from_detection`
factory. StatusReporter renders a Rich panel + per-server table for `nexus
status`. `nexus reauth` prints the exact `claude /mcp <name>` command for
each flagged server (opt-in `--execute` actually invokes it).

The detector is `@cached(ttl=86400, persist=True, namespace="capabilities")`.
`nexus status --refresh` clears the cache.

No live MCP probing in this PR. The OAuth claim plus claudeAiMcpEverConnected
inspection is sufficient. `MCPProbe._check_server` stays a stub for the
future live-probe path.

## Consequences

  - `nexus status` works end-to-end; `nexus reauth` is a new command.
  - Cross-platform credential lookup: keyring on macOS routes to Keychain
    Access; Linux/Windows fall back to `~/.claude/.credentials.json`.
  - The static `_CLAUDE_AI_NAME_TO_SERVER` table is SN-specific. If a new
    SN MCP server lands without updating the table, it is dropped at
    DEBUG-log level and does not appear in status output. NEXUS stays
    forward-compatible (no errors), but the new server is invisible
    until the table is updated.
  - Re-auth automation is print-only by default. Subprocess execution via
    `--execute` is opt-in to avoid surprise browser tabs.
  - Adds `MCPServer.MARKETING` to the existing enum.

Spec: docs/superpowers/specs/2026-05-08-tier-detection-design.md
Plan: docs/superpowers/plans/2026-05-08-tier-detection.md
```

- [ ] **Step 4: Update .primer/governance.md ADR catalog**

Append to the catalog table (after ADR-017):

```markdown
| 018 | Tier detection from Claude Code OAuth + org MCP config | none | accepted |
```

- [ ] **Step 5: Append to .primer/decisions.md**

```markdown


---

### 2026-05-08 -- Tier detection from Claude Code OAuth + org MCP config

**Status:** accepted (ADR-018)

**Context:** Capabilities layer was scaffolded but `_check_server` was a
stub. Real detection needed. Investigation found three usable signals:
OAuth subscription claim, claudeAiMcpEverConnected list, and the
mcp-needs-auth-cache file. No email heuristic needed.

**Decision:** Add Tier enum + TierDetector to capabilities. `nexus status`
renders a Rich panel; `nexus reauth` prints the one-shot command. Detection
caches 24h on disk. No live MCP probing in this PR; deferred until the
Agent SDK exposes a clean tool-list query.

**Consequences:** Cross-platform via keyring (macOS Keychain / Linux/Windows
file fallback). Static SN MCP name table; new servers without table updates
appear unrecognized but don't break anything. Re-auth automation is
print-only by default. Spec at
docs/superpowers/specs/2026-05-08-tier-detection-design.md.
```

- [ ] **Step 6: Run pre-commit**

```bash
.venv/bin/pre-commit run --all-files 2>&1 | tail -8
```

Expected: 6/6 hooks pass.

- [ ] **Step 7: Commit**

```bash
git add .ratchet.json .primer/ && git commit -m "docs: ADR-018 tier detection + governance + ratchet"
```

---

## Task 10: Push, open PR

- [ ] **Step 1: Push**

```bash
git push -u origin feat/tier-detection
```

- [ ] **Step 2: Open the PR**

```bash
gh pr create --title "feat: tier detection (ADR-018)" --body "$(cat <<'EOF'
## Summary

- Add `Tier` (StrEnum: Anonymous / Pro / Enterprise) + `TierDetector` to the existing capabilities layer.
- Read OAuth `subscriptionType` from macOS Keychain (with file fallback) + `claudeAiMcpEverConnected` from `~/.claude.json` + the `mcp-needs-auth-cache.json` file.
- New `MCPServer.MARKETING` + claude.ai name mapping table + `claude_ai_name_for()` helper.
- `nexus status` works end-to-end (was `NotImplementedError` stub) -- prints Rich panel + per-server table.
- New `nexus reauth [--server <name>] [--execute]` command -- prints the `claude /mcp ...` command for each flagged server.
- 24h disk cache via `@cached(persist=True, namespace="capabilities", ttl=86400)`. `nexus status --refresh` clears it.

## Why

Without real detection, every feature stayed disabled. The OAuth payload directly carries the subscription claim; no email heuristic needed. The recurring "MCP servers disabled" annoyance turned out to be per-server OAuth re-auth expiry tracked in `~/.claude/mcp-needs-auth-cache.json` -- NEXUS surfaces this clearly and provides a one-shot fix.

Spec: `docs/superpowers/specs/2026-05-08-tier-detection-design.md`
Plan: `docs/superpowers/plans/2026-05-08-tier-detection.md`
ADR-018: `.primer/adr/ADR-018-tier-detection.md`

## Test plan

- [x] ~30 new tests across 4 new test files
- [x] `nexus status` against an isolated tmp_path home reports Anonymous tier
- [x] `nexus reauth` with no flagged servers exits 0 with "All MCP servers authenticated"
- [x] `nexus reauth` with a flagged server prints `claude /mcp "..."` command
- [x] All 6 pre-commit hooks pass

## Out of scope (deferred)

- Live MCP probe via Agent SDK (when SDK exposes tool-list query).
- `--execute` actually invoking subprocess (currently opt-in flag, but the print path is the default).
- Background watcher for needs-auth-cache changes.

Generated with Claude Code
EOF
)"
```

Expected: PR URL printed.

---

## Self-Review Notes

- All 10 tasks contain explicit code or commands. No placeholders except the ratchet baseline numbers (Task 9 Step 1 produces them; the engineer fills them in).
- Type consistency:
  - `ClaudeCodeConfig(subscription_type, org_mcp_servers, needs_reauth)` is the same in Tasks 2, 3, 4, 5, 6, 7, 8.
  - `TierDetection(tier, config, detected_servers, needs_reauth_servers)` is the same in Tasks 4, 5, 6, 7.
  - `CapabilitySet.from_detection(detection)` signature is consistent across Tasks 5, 6, 7.
  - `claude_ai_name_for(MCPServer) -> str` is defined in Task 1, used in Task 8.
  - `TierDetector(reader=...).detect()` signature is consistent across Tasks 4, 7, 8.
- Spec coverage:
  - Architecture (spec) -> Tasks 2-7 build the modules
  - API (spec) -> Tasks 4 + 5 implement signatures
  - Detection sequence (spec) -> Task 3 (reader) + Task 4 (detector)
  - Cache 24h persist (spec) -> Task 4 step 5 (`@cached(ttl=86400, persist=True, namespace="capabilities")`)
  - Failure matrix (spec) -> Tasks 3 + 4 tests cover malformed, missing, unknown
  - StatusReporter Rich panel (spec) -> Task 6
  - `nexus status` + `nexus reauth` (spec) -> Tasks 7 + 8
  - ADR + governance + decisions (spec) -> Task 9
- Risk: cross-platform credential lookup (Task 3) hits actual filesystem and keyring. Tests use `tmp_path` and `FakeKeychainClient`, so no real-system pollution.
