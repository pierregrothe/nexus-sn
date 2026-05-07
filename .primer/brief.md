# NEXUS -- Project Brief

## What it is

NEXUS is a standalone Python CLI tool that acts as a ServiceNow AI architect agent.
It is the successor to JARVIS (by Zach Zoretich), redesigned from scratch with proper
engineering standards, a real Python architecture, and a fundamentally new concept:
declarative YAML templates as first-class versioned artifacts.

## Origin

Designed by Pierre Grothe (pierre.grothe@servicenow.com) in May 2026 after a deep
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
through an AI-assisted execution engine with three assessment gates:

- Gate 1 (readiness): checks prerequisites before deploying
- Gate 2 (validation): verifies everything was created correctly after deploying
- Standalone health scan: `nexus assess` against any instance at any time

## Why independent of Claude Code

NEXUS calls the Anthropic API directly. No Claude Code, no Claude Desktop, no Node.js.
Ships as a pip package. Runs on Windows, macOS, Linux identically.

NEXUS does NOT run an MCP server. ServiceNow has configured enterprise MCP servers
(Value Melody, SSC, BT1, Data Analytics, GTM, M365) inside the Claude Enterprise
account. These are not separate services NEXUS calls directly -- they are injected
into the Anthropic API session by the enterprise account configuration. NEXUS probes
their availability at startup via lightweight Anthropic API calls and builds a
CapabilitySet. Features requiring unavailable servers are disabled transparently.

## Distribution

Public GitHub repo. PyPI package (nexus-sn). Templates distributed via the same repo.
`nexus sync` pulls the latest templates. Primary audience: ServiceNow colleagues.
