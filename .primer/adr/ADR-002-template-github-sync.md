# ADR-002: Template distribution via GitHub sync

**Status:** accepted
**Date:** 2026-05-07
**Enforcement:** agent

## Context

Four distribution models were evaluated:
  A. Bundled at install -- templates go stale between installs (JARVIS pattern)
  B. Versioned PyPI data package -- requires a release for every template change
  C. Separate templates-only repo -- splits the community contribution surface
  D. Same repo + sync command -- latest is always authoritative

JARVIS used option A; its bundled knowledge went stale between installs.

## Decision

Option D -- templates live in the same GitHub repo under templates/. The
`nexus sync` command fetches the manifest and downloads changed files to
~/.nexus/templates/. No version pinning required; latest is always
authoritative.

## Consequences

nexus sync is a required first step after install. Offline use requires a
prior sync. The GitHubSync layer must handle rate limiting and partial
downloads gracefully. Template contributions go through the same PR process
as code -- CI validates YAML on every PR via validate-templates.yml.
