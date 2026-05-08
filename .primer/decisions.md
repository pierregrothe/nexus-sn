# Decision Log

Append-only record of architectural and design decisions.

## Template

```
### YYYY-MM-DD -- [Title]

**Status:** proposed | accepted | superseded by [link]

**Context:** Why this decision was needed.

**Decision:** What was decided.

**Consequences:** What follows from this decision.
```

### 2026-05-07 -- API-direct architecture (no Claude Code dependency)

**Status:** accepted

**Context:** JARVIS required Claude Code + MCP protocol + Node.js, limiting deployment
to developers who had Claude Desktop or Claude Code installed.

**Decision:** NEXUS calls the Anthropic API directly using the Python SDK.
No Claude Code, no MCP protocol, no Node.js. Ships as a pip package that
runs on Windows, macOS, and Linux identically.

**Consequences:** NEXUS can be installed anywhere Python runs. Enterprise MCP servers
(Value Melody, SSC, BT1, etc.) are accessed via the Claude Enterprise API key's
server-sent events channel, not via a local MCP host process. The capability probing
layer must handle absent enterprise MCP gracefully.

---

### 2026-05-07 -- Template distribution via GitHub sync

**Status:** accepted

**Context:** Four distribution models were evaluated: (A) bundled at install, (B)
versioned PyPI data package, (C) separate templates-only repo, (D) same repo + sync
command. JARVIS used bundled knowledge that went stale between installs.

**Decision:** Option D -- templates live in the same GitHub repo under templates/.
The `nexus sync` command fetches the manifest and downloads changed files to
~/.nexus/templates/. No version pinning required; latest is always authoritative.

**Consequences:** nexus sync is a required first step after install. Offline use
requires a prior sync. The GitHubSync layer must handle rate limiting and partial
downloads gracefully.

---

### 2026-05-07 -- Assessment 3-gate model

**Status:** accepted

**Context:** JARVIS had no validation step -- it applied templates and hoped for
the best. Failed deployments left instances in an unknown state.

**Decision:** Assessment runs in three phases: Gate 1 (readiness check before deploy),
Gate 2 (validation check after deploy), and standalone `nexus assess` (health scan
at any time). Each gate is a separate RuleEngine evaluation pass.

**Consequences:** Every template deployment requires two assessment passes. The
RuleEngine must be stateless and re-runnable. Rollback logic is scoped to the
execution layer, not the assessment layer.

---

### 2026-05-07 -- CalVer versioning (YYYY.0M.PATCH)

**Status:** accepted

**Context:** NEXUS is a ServiceNow tooling project where "how current is this?"
matters more than API stability signaling. SemVer MAJOR bumps would be meaningless
without a stable external API contract.

**Decision:** CalVer format YYYY.0M.PATCH (e.g., 2026.05.0). Patch resets to 0
each month. Breaking changes are documented in CHANGELOG.md.

**Consequences:** Version number encodes freshness. CI release workflow tags from
pyproject.toml version field. No automated version bumping -- Pierre sets the
version manually before tagging.

---

### 2026-05-07 -- Connector plugin system

**Status:** accepted

**Context:** ServiceNow is the first and primary connector, but future connectors
(JIRA, GitHub, Confluence) were anticipated in the JARVIS analysis.

**Decision:** Connectors are registered via ConnectorProtocol. ConnectorRegistry
discovers them by class name. ServiceNow REST is built-in; enterprise MCP is
optional. Plugins can be added without modifying core code.

**Consequences:** ServiceNowClient is not imported directly outside the connectors
layer. All tool calls go through ConnectorRegistry.get(). Future connectors inherit
ConnectorProtocol and register themselves.

---

### 2026-05-07 -- Sprint retrospective governance upgrade

**Status:** accepted

**Context:** MVP Step 1 sprint revealed 23 issues across 6 categories. Most were
type safety failures, test quality gaps, and broken hook infrastructure. Cataloged
in docs/superpowers/specs/2026-05-07-governance-enforcement-design.md.

**Decision:** 8 new ADRs (006-013) document the governance improvements. Plan 1
fixed the critical issues (broken hooks, Python 3.14, type enforcement). Plan 2
adds the ratchet baseline, lean CI, pre-commit hook, and formal ADR documents.

**Consequences:** The codebase now has 10 blocking pre-edit rules, a coverage ratchet
in .ratchet.json, pyright strict alongside mypy, and lean CI (<30s feedback).
Pre-commit hook enforces full test suite locally before every commit. CI cross-platform
testing only runs on release tags.

---

### 2026-05-07 -- Pluggable AuthProvider with OAuth-first chain

**Status:** superseded by ADR-015 (2026-05-08)

**Context:** Original design (ADR-001) assumed users would have Anthropic API keys.
Smoke-test reality check exposed the gap: getting a key from ServiceNow's enterprise
Claude account is a lengthy process; personal keys violate company AI usage guidelines
and lack access to org MCP servers. Anthropic forbids third parties from offering
claude.ai login flows -- but the Claude Agent SDK reads OAuth tokens from Claude Code's
stored credentials, and the standard Anthropic SDK accepts those tokens via auth_token=.

**Decision:** AnthropicClient takes a Sequence[AuthProvider] instead of api_key:str.
The default chain (get_default_providers()) is [ClaudeCodeOAuthProvider, AnthropicAPIKeyProvider].
OAuth provider reads token from CLAUDE_CODE_OAUTH_TOKEN env, then ~/.claude/.credentials.json,
then macOS Keychain ("Claude Code-credentials" via keyring lib). API key provider is
the fallback for users without Claude Code. The architecture supports future Bedrock,
Vertex, and Foundry providers without further interface changes.

**Consequences:** Users authenticated to Claude Code (the typical case for ServiceNow
employees) get API access for free, including their org's MCP servers. ADR-001 (API-direct)
remains valid -- still calling Anthropic directly via the standard SDK; OAuth uses the
Bearer auth header (auth_token=) instead of X-Api-Key. Spec at
docs/superpowers/specs/2026-05-07-pluggable-auth-design.md (PR #1).

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
~150 lines added). ADR-001 partially superseded; the 2026-05-07
AuthProvider entry is superseded by ADR-015.
Spec at docs/superpowers/specs/2026-05-08-agent-sdk-migration-design.md.


---

### 2026-05-08 -- Single canonical caching decorator (@cached)

**Status:** accepted (ADR-017)

**Context:** Four families of operations in NEXUS benefit from caching
(Agent SDK calls, ServiceNow API responses, capability probes, config
lookups). Without a canonical decorator, each would invent its own layer
with different semantics.

**Decision:** Layer-0 utility `src/nexus/cache/` exports `@cached(ttl,
persist, namespace, key_fn)` and `clear_cache(target)`. Three Semgrep rules
plus runtime TypeError/ValueError enforce the contract.

**Consequences:** Adds diskcache as a runtime dep. Instances must be
hashable (slots+frozen dataclasses use an id-keyed strong-dict fallback;
documented in ADR-017). Function exceptions never cached. Initial adoption:
ConfigManager.load and NexusPaths.from_env. Spec at
docs/superpowers/specs/2026-05-08-cached-decorator-design.md; plan at
docs/superpowers/plans/2026-05-08-cached-decorator.md.


---

### 2026-05-08 -- Tier detection from Claude Code OAuth + org MCP config

**Status:** accepted (ADR-018)

**Context:** Capabilities layer was scaffolded but `_check_server` was a
stub. Real detection needed. Investigation found three usable signals:
OAuth subscription claim, claudeAiMcpEverConnected list, and the
mcp-needs-auth-cache file. No email heuristic needed.

**Decision:** Add Tier enum + TierDetector to capabilities. `nexus status`
renders a Rich panel; `nexus reauth` prints the one-shot command. Detection
caches per-instance in-memory (cross-invocation disk caching deferred --
the @cached(persist=True) path captures the disk backend at decoration
time, preventing test isolation). No live MCP probing in this PR;
deferred until the Agent SDK exposes a clean tool-list query.

**Consequences:** Cross-platform via keyring (macOS Keychain / Linux/Windows
file fallback). Static SN MCP name table; new servers without table updates
appear unrecognized but don't break anything. Re-auth is print-only (no
subprocess invocation). `_CLAUDE_AI_NAME_TO_SERVER` renamed to public
`CLAUDE_AI_NAME_TO_SERVER` so tier.py can import it without violating
pyright strict's reportPrivateUsage. Spec at
docs/superpowers/specs/2026-05-08-tier-detection-design.md.


---

### 2026-05-08 -- Lessons from /simplify reviews (ADR-019)

**Status:** accepted

**Context:** Three /simplify sessions (PRs #2, #5, #6) caught real issues
every time, including a CRITICAL keychain-prefix bug in PR #6 that pre-
commit and tests missed. Recurring style smells (enum-shadowing dict,
stub "See" docstrings, hot-path attribute access) appeared across PRs.
The @cached(persist=True) decoration-time backend capture broke test
isolation in PR #6, forcing a fallback to ttl=None.

**Decision:** Bundled PR codifies four threads: ExternalKeychainClient
wrapper for cross-app keychain reads, @cached(persist=True) lazy-resolve
fix, three new Semgrep rules, and a PR template gating /simplify
execution.

**Consequences:** The keychain pattern bug class is closed. @cached
persist mode is test-friendly (AgentClient adoption unblocked). Three
new lint rules trace to ADR-019. PR template is a soft gate; the
unchecked /simplify checkbox is review-visible. Spec at
docs/superpowers/specs/2026-05-08-simplify-lessons-design.md.
