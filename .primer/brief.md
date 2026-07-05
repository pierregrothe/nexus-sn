# NEXUS -- Project Brief

## What it is

NEXUS is a standalone Python CLI tool that acts as a ServiceNow AI architect agent.
It is the successor to JARVIS (by Zach Zoretich), redesigned from scratch with proper
engineering standards, a real Python architecture, and a fundamentally new concept:
declarative YAML templates as first-class versioned artifacts.

## Origin

Designed by Pierre Grothe (pierre@grothe.ca) in May 2026 after a deep
analysis of JARVIS's architecture. The analysis identified six core weaknesses in JARVIS:

1. Fake parallelism (sequential execution disguised as parallel via TaskCreate)
2. Keyword-based routing (fragile, not semantic)
3. Self-improvement with no validation gate (writes to agent files without testing)
4. Static knowledge that goes stale (bundled at install time, not refreshable)
5. Cosmetic web app (no real control plane authority)
6. Zero test coverage across 457 files

NEXUS fixes all six.

## Core concept

NEXUS is a ServiceNow configuration package manager backed by AI orchestration.

Templates are declarative YAML artifacts versioned in the GitHub repo. The local tool
syncs against the registry, validates against Pydantic schemas, and applies templates
through a deterministic render-and-push engine. Three assessment gates back the
apply/scan flows:

- Gate 1 (readiness): checks prerequisites before deploying
- Gate 2 (validation): verifies everything was created correctly after deploying
- Standalone health scan: `nexus assess` against any instance at any time

The AI-assisted orchestration engine (specialist agents, planning/dispatch) is
scaffolded but not yet wired; see product.md "Planned".

## LLM access and Claude Code

NEXUS ships as a pure-Python pip package, runs identically on Windows, macOS, and
Linux, and runs no MCP server of its own and no Node.js. Since ADR-015, LLM calls
route through the claude-agent-sdk, which uses the installed Claude Code CLI and its
credentials (env token, credentials file, or OS keychain) -- so Claude Code is a
runtime dependency for AI features; the deterministic tools (schema, plugins,
capture, migrate, assess) run with no LLM call.

ServiceNow's enterprise MCP servers (Value Melody, SSC, BT1, Data Analytics, GTM,
M365, Marketing) live inside the Claude Enterprise account and are injected into the
model session rather than called by NEXUS directly. NEXUS detects which are available
at startup by reading Claude Code's local config/keychain state and builds a
CapabilitySet. Features requiring unavailable servers are disabled transparently.

## Distribution

Public GitHub repo. PyPI package (nexus-sn). Templates distributed via the same repo.
`nexus sync` pulls the latest templates. Primary audience: ServiceNow colleagues.
