# Tier Detection Design Spec

Date: 2026-05-08
Status: approved (brainstorming complete)
Author: Pierre Grothe

## Goal

NEXUS runs on any Claude account. When the user has a ServiceNow Enterprise
account with org-pushed MCP servers, NEXUS auto-detects this and unlocks
features that depend on those servers. The user sees a clear tier banner
plus the list of available SN MCP servers.

## Why

The existing `src/nexus/capabilities/` layer was scaffolded with
`FeatureFlag`, `MCPServer`, `FEATURE_MAP`, `CapabilitySet`, and a
stub `MCPProbe._check_server` that returns False. This means every
feature is currently disabled regardless of what the user actually has
access to. Real detection is needed for the existing scaffold to pay off.

The user also asked for a solution to a recurring annoyance: SN-managed
MCP servers periodically need re-authentication, which the user has to
re-do manually in Claude Code. Investigation found the mechanism --
`~/.claude/mcp-needs-auth-cache.json` lists per-server expiry state.
NEXUS surfaces this and provides a one-shot re-auth command.

## Architecture

### Module layout (extends existing `src/nexus/capabilities/`)

```
src/nexus/capabilities/
  __init__.py              -- public exports
  feature_flags.py         -- EXISTING: FeatureFlag, MCPServer, FEATURE_MAP, ServerSpec
                              + NEW: _CLAUDE_AI_NAME_TO_SERVER mapping
                              + NEW: MCPServer.MARKETING entry
  registry.py              -- EXISTING CapabilitySet, extended with tier + needs_reauth
  probe.py                 -- EXISTING (stub stays) for future live-probe path
  tier.py                  -- NEW: Tier enum, TierDetector, TierDetection
  claude_config.py         -- NEW: ClaudeCodeConfig + ClaudeCodeConfigReader
  status_reporter.py       -- NEW: Rich-based status panel rendering

src/nexus/cli.py           -- MODIFIED: implement `nexus status`, add `nexus reauth`

tests/
  test_capabilities_tier.py
  test_capabilities_claude_config.py
  test_capabilities_status.py
  test_capabilities.py     -- EXTENDED: from_detection tests
  test_cli_status.py       -- NEW: CLI command tests via Typer CliRunner
  fakes/fake_claude_config.py
```

### Detection flow (cheap to expensive)

1. **Subscription claim** -- read OAuth payload from macOS Keychain via
   `keyring.get_password("Claude Code-credentials", username)` or fall
   back to `~/.claude/.credentials.json` (Linux/Windows). The payload's
   `subscriptionType` field is the authoritative tier signal.
2. **Org MCP list** -- read `~/.claude.json` `claudeAiMcpEverConnected`
   entry. Confirms which org-managed MCP servers exist.
3. **Re-auth state** -- read `~/.claude/mcp-needs-auth-cache.json`. Each
   key in the dict names a server that needs user re-authentication.

No live probing in this PR. The OAuth claim plus config inspection is
sufficient for tier and feature accuracy. `MCPProbe._check_server` stays
a stub; live probing is a follow-up PR when the Agent SDK exposes a
clean tool-list query.

### Caching

`TierDetector.detect()` is decorated `@cached(ttl=86400, persist=True,
namespace="capabilities")`. Result lives 24h on disk under
`~/.nexus/cache/capabilities/`. `nexus status --refresh` calls
`clear_cache(TierDetector.detect)` before re-running.

### Layer placement

`capabilities/` stays at its existing layer (above auth/config). It
imports `cache` (Layer 0). No new runtime dependencies; the existing
`keyring` dep handles macOS Keychain access.

## Components and types

### `Tier` enum (`src/nexus/capabilities/tier.py`)

```python
class Tier(StrEnum):
    """User capability tier derived from authentication and org MCP access."""
    ANONYMOUS = "anonymous"   # No Claude OAuth; API-key-only or unauthenticated
    PRO = "pro"               # Authenticated Claude account, no Enterprise MCP
    ENTERPRISE = "enterprise" # Claude Enterprise + ServiceNow MCP servers provisioned
```

### `ClaudeCodeConfig` (`src/nexus/capabilities/claude_config.py`)

```python
@dataclass(slots=True, frozen=True)
class ClaudeCodeConfig:
    subscription_type: str | None
    org_mcp_servers: tuple[str, ...]
    needs_reauth: tuple[str, ...]


class ClaudeCodeConfigReader(Protocol):
    def read(self) -> ClaudeCodeConfig: ...


class FilesystemClaudeCodeConfigReader:
    """Production reader: macOS Keychain + ~/.claude.json + needs-auth-cache.

    The keychain entry for the Claude Code OAuth payload is stored under
    service="Claude Code-credentials", username=<OS user>. The OS user
    defaults to getpass.getuser() but can be overridden for tests.
    """
    def __init__(
        self,
        *,
        keychain: KeychainClient,
        home: Path | None = None,
        os_user: str | None = None,  # default: getpass.getuser()
    ) -> None: ...
    def read(self) -> ClaudeCodeConfig: ...
```

`read()` is sync, never raises. Missing or malformed files become empty
fields with a WARNING log.

### `TierDetector` and `TierDetection` (`src/nexus/capabilities/tier.py`)

```python
@dataclass(slots=True, frozen=True)
class TierDetection:
    tier: Tier
    config: ClaudeCodeConfig
    detected_servers: frozenset[MCPServer]
    needs_reauth_servers: frozenset[MCPServer]


class TierDetector:
    def __init__(self, reader: ClaudeCodeConfigReader) -> None: ...

    @cached(ttl=86400, persist=True, namespace="capabilities")
    def detect(self) -> TierDetection: ...
```

### `CapabilitySet` extension (`src/nexus/capabilities/registry.py`)

```python
@dataclass(slots=True, frozen=True)
class CapabilitySet:
    available_servers: frozenset[MCPServer]
    unavailable_servers: frozenset[MCPServer]
    enabled_features: frozenset[FeatureFlag]
    tier: Tier                         # NEW
    needs_reauth: frozenset[MCPServer] # NEW

    @classmethod
    def from_detection(cls, detection: TierDetection) -> CapabilitySet:
        """Build from TierDetection (no live probe). Available = detected_servers."""

    @classmethod
    def from_probe_results(cls, results: list[ProbeResult]) -> CapabilitySet:
        """EXISTING method. Used by future live-probe flow."""
```

### Static name mapping (`feature_flags.py`)

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

    Raises:
        KeyError: If the server has no mapping (would only happen if a new
            MCPServer enum value is added without updating the table).
    """
    return _SERVER_TO_CLAUDE_AI_NAME[server]
```

`MCPServer.MARKETING` is added to the existing enum. Unrecognized
`claudeAiMcpEverConnected` entries are dropped with a DEBUG log.

## Data flow

### `TierDetector.detect()`

```
detect()
   - reader.read() -> ClaudeCodeConfig
   - subscription_type -> Tier (initial):
        "enterprise" -> ENTERPRISE
        None and org_mcp_servers empty -> ANONYMOUS
        else (any other value, including None with non-empty org) -> PRO
     Override: if org_mcp_servers non-empty AND tier != ENTERPRISE -> ENTERPRISE
              (org MCP presence is the strongest signal: if claude.ai has
              actually pushed SN MCP config to this user, they are by
              definition an Enterprise user, regardless of the OAuth claim)
   - org_mcp_servers -> frozenset[MCPServer] via _CLAUDE_AI_NAME_TO_SERVER
   - needs_reauth -> frozenset[MCPServer] via same table
   - return TierDetection(tier, config, detected_servers, needs_reauth_servers)
```

### `nexus status [--refresh]`

```
status(refresh: bool):
   if refresh: clear_cache(TierDetector.detect)
   detection = TierDetector(reader).detect()
   capability_set = CapabilitySet.from_detection(detection)
   StatusReporter().print(detection, capability_set)
```

`StatusReporter` output (Rich panel):

```
+-- NEXUS Status -------------------------------------+
| Tier: Enterprise                                    |
| 5/6 SN MCP servers ready                            |
+-----------------------------------------------------+

+-- MCP Servers --------------------------------------+
| Server               Status         Features        |
+-----------------------------------------------------+
| Value Melody         ready          ROI_ANALYSIS,   |
|                                     VE_PIPELINE     |
| BT1                  ready          WORK_ITEM_LOOKUP|
| Data Analytics       ready          ACCOUNT_INSIGHTS|
| GTM                  ready          DEAL_REGISTRATION
| Microsoft 365        ready          EMAIL_CALENDAR  |
| Marketing MCP        needs re-auth  -               |
+-----------------------------------------------------+

Run `nexus reauth --server "Marketing MCP"` to fix.
```

### `nexus reauth [--server NAME] [--execute]`

```
reauth(server: str | None, execute: bool):
   detection = TierDetector(reader).detect()
   if detection.needs_reauth_servers is empty:
       print("All MCP servers authenticated. Nothing to do.")
       return 0
   if server is None and len(needs_reauth) > 1:
       print list of needs_reauth + example commands; return 0
   target = resolve(server, needs_reauth)
   if target not in needs_reauth:
       print warning; return 1
   command = ["claude", "/mcp", claude_ai_name_for(target)]
   print command
   if execute: subprocess.run(command, check=False)
   return 0
```

`--execute` is opt-in. Default is print-only.

## Error handling

All failures map to graceful states; no exceptions raised to the user.

### Cross-platform credential lookup

| Platform | Source |
|---|---|
| macOS | `keyring.get_password("Claude Code-credentials", user)` |
| Linux/Windows | `~/.claude/.credentials.json` |
| Headless / API-key-only | Neither -> subscription_type is None |

### Failure matrix

| Condition | Behavior |
|---|---|
| Keychain has entry but JSON is malformed | log WARNING, treat as None |
| `~/.claude.json` missing or no `claudeAiMcpEverConnected` key | empty list |
| `mcp-needs-auth-cache.json` malformed | WARNING log, empty needs_reauth |
| Unknown subscription_type value | map to PRO + DEBUG log |
| Unknown MCP name in `claudeAiMcpEverConnected` | drop + DEBUG log |
| `subscription_type="enterprise"` but no `claudeAiMcpEverConnected` | Tier.ENTERPRISE, zero detected servers; banner clarifies |
| `subscription_type=None` but `claudeAiMcpEverConnected` non-empty | Tier.ENTERPRISE (org wins) |

### Re-auth edges

| Condition | Behavior |
|---|---|
| `needs_reauth` cache entry NEXUS doesn't recognize | shown raw in status; `nexus reauth` declines automation |
| `nexus reauth` with empty `needs_reauth` | "All MCP servers authenticated." Exit 0. |
| `--server NAME` not flagged | "Server NAME is not currently flagged for re-auth." Exit 1. |
| Multiple needed, no `--server` | List + example per server. Exit 0. No interactive prompt. |

### Logging

- DEBUG: every detection step, drops, fallbacks
- INFO: when detection runs (cache miss): "tier=enterprise; 5 SN MCP servers"
- WARNING: malformed config files
- No errors raised to the user. Detection failure -> Tier.ANONYMOUS with INFO log.

## Testing

### Test files

```
tests/test_capabilities_tier.py        -- TierDetector + name mapping (~12 tests)
tests/test_capabilities_claude_config.py -- file-system reader (~8 tests)
tests/test_capabilities_status.py      -- StatusReporter rendering (~5 tests)
tests/test_capabilities.py             -- EXTENDED: from_detection (~3 new tests)
tests/test_cli_status.py               -- CLI commands via Typer CliRunner (~6 tests)
tests/fakes/fake_claude_config.py      -- @dataclass(slots=True) test double
```

### Detection coverage matrix

| Scenario | Inputs | Expected |
|---|---|---|
| API-key-only | subscription=None, org=[] | Tier.ANONYMOUS, 0 servers |
| Pro no SN | subscription="pro", org=[] | Tier.PRO, 0 servers |
| Enterprise claim, no MCP yet | "enterprise", [] | Tier.ENTERPRISE, 0 servers |
| Pro claim with org MCP (override) | "pro", ["claude.ai BT1_MCP"] | Tier.ENTERPRISE, BT1 |
| Enterprise full | "enterprise", full SN list | ENTERPRISE, 6 servers |
| Unknown subscription | "team" | Tier.PRO + DEBUG |
| Unknown MCP name | ["claude.ai NewThing"] | dropped + DEBUG |
| Re-auth needed | needs=["claude.ai Marketing MCP"] | needs_reauth_servers={MARKETING} |

### CLI test coverage

```
test_nexus_status_anonymous_user_prints_anonymous_panel
test_nexus_status_enterprise_with_full_servers_prints_panel
test_nexus_status_refresh_clears_cache
test_nexus_reauth_with_no_flagged_returns_zero_and_prints_ok
test_nexus_reauth_with_one_flagged_prints_command_no_execute
test_nexus_reauth_with_unknown_server_returns_one
```

### Coverage target

100% on new modules per existing project gate. ~30 new tests total.

## Migration plan

### Initial PR (this spec)

- New: `tier.py`, `claude_config.py`, `status_reporter.py`, `MCPServer.MARKETING`
- Modified: `feature_flags.py` (mapping + new enum entry), `registry.py` (`from_detection`),
  `cli.py` (`status`, `reauth`)
- Test files: 5 new + 1 extended
- Docs: ADR-018, governance.md catalog row, decisions.md entry, ratchet entries

### Behavior changes user-visible

- `nexus status` works end-to-end (was `NotImplementedError` stub)
- `nexus reauth` is a new command
- Other commands unchanged (no auto-banner)

### Deferred to follow-ups

| Item | Reason |
|---|---|
| Live MCP probe via Agent SDK | SDK doesn't expose tool-list query yet |
| `--execute` flag actually invoking `claude` CLI | Print-only is the default; subprocess wiring deferred |
| Background watcher for needs-auth-cache | Heavy persistent process; `--refresh` is enough for v1 |
| Per-feature flag overrides in `~/.nexus/config.yaml` | Out of scope for THIS PR |

### Out of scope (entire feature)

- Auto-fix MCP server enable/disable -- the disable mechanism is OAuth
  re-auth, which inherently requires user interaction (browser).
- Detecting non-SN org MCP servers -- the static name table is SN-specific.

### Rollback

Misreporting -> `nexus status --refresh` -> if still wrong, delete
`~/.nexus/cache/capabilities/`. Detection is read-only; no risk to
Claude Code state.

### Coverage ratchet

`.ratchet.json` gains entries for `nexus.capabilities.tier`,
`nexus.capabilities.claude_config`, `nexus.capabilities.status_reporter`,
and updated baseline for `nexus.capabilities.registry`,
`nexus.capabilities.feature_flags`, and `nexus.cli` (when status/reauth
are implemented).
