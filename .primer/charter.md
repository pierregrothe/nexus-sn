---
title: NEXUS Charter
status: accepted
date: 2026-06-29
version: CalVer (YYYY.0M.PATCH)
---

# NEXUS Charter

## 1. Vision
NEXUS is a standalone, cross-platform Python CLI that acts as a ServiceNow AI
architect -- a ServiceNow configuration package manager backed by direct
Anthropic API orchestration.

## 2. Must-Have Capabilities
- Declarative YAML templates as first-class, GitHub-versioned, Pydantic-validated
  artifacts, synced via `nexus sync`.
- Multi-instance management with OAuth auto-provisioning; per-profile credentials
  in the OS keychain.
- Bidirectional ServiceNow config transport (`nexus capture` discover/pull/push).
- Plugin / scoped-app inventory, cross-instance diff, advisories, drift, impact,
  AI recommendations.
- 3-gate assessment model (readiness, validation, standalone health) over
  declarative rulesets.
- Schema cartographer (ERD / mindmap from live instances).
- Direct Anthropic API integration; enterprise MCP servers probed and degraded
  gracefully.
- Identical behavior on Windows, macOS, Linux; ships as the pip package nexus-sn.

## 3. Hard Product Limits (NEVER)
- NEVER depends on Claude Code, Claude Desktop, or Node.js -- pure Python, direct
  Anthropic API.
- NEVER runs or hosts an MCP server; it only probes enterprise MCP servers
  injected by the Anthropic account.
- NEVER stores secrets in config files -- OS keychain only, env vars as CI override.
- NEVER applies changes to a ServiceNow instance without an explicit human approval
  checkpoint; assessment, diff, and analysis layers are advisory and NEVER mutate
  instance state.
- NEVER self-modifies its own agent/config files without a validation gate (the
  JARVIS anti-pattern NEXUS exists to fix).
- NEVER bundles static knowledge that goes stale at install time -- templates and
  catalog are refreshable via `nexus sync`.
- NEVER hardcodes product / license / scope specifics -- the catalog is
  GitHub-synced and scope-driven from the live instance.

## 4. Constraints
- Python 3.14+; Poetry with in-project venv. CalVer (YYYY.0M.PATCH).
- 100% line coverage; mypy strict + pyright strict (0 errors); ruff 0 violations;
  no `# type: ignore`; no mocks (fakes only).
- ASCII only; absolute imports; Pydantic frozen+strict+extra=forbid.
- Distribution: public GitHub repo + PyPI (nexus-sn); templates via the same repo.

## 5. Success Metrics
- A Solution Consultant goes from `pip install nexus-sn` to a gated, validated
  template deployment on any OS.
- Templates are community-contributable via PR with CI validation, no Python
  required of the author.
- The suite stays green at 100% line coverage with zero type/lint violations.

## 6. Out of Charter Scope
- ServiceNow itself / the platform runtime -- NEXUS configures SN; it is not SN.
- The Anthropic API / model hosting -- NEXUS calls it; it does not host models.
- Enterprise MCP servers (Value Melody, SSC, BT1, ...) -- owned by the ServiceNow
  Claude Enterprise account; NEXUS only probes and degrades.
- OS keychain implementation -- delegated to `keyring`.
- Long-term data warehousing / analytics history -- NEXUS is point-in-time.

## 7. Charter Amendment Process
Append the change + rationale to `.primer/decisions.md`, then edit `charter.md`
and bump the date. Hard Product Limits change only via an explicit decision entry.
