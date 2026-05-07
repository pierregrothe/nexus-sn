# ADR-004: CalVer versioning (YYYY.0M.PATCH)

**Status:** accepted
**Date:** 2026-05-07
**Enforcement:** agent

## Context

NEXUS is a ServiceNow tooling project where "how current is this?" matters
more than API stability signaling. SemVer MAJOR bumps would be meaningless
without a stable external API contract -- there are no downstream library
consumers pinning to a version range.

## Decision

CalVer format YYYY.0M.PATCH (e.g., 2026.05.0). The patch component resets
to 0 each month. Breaking changes are documented in CHANGELOG.md. No
automated version bumping -- Pierre sets the version manually in
pyproject.toml before tagging a release.

## Consequences

Version number encodes freshness at a glance. CI release workflow tags from
the pyproject.toml version field. The calver agent-enforced rule tracks this
convention. Dependabot and other tools that expect SemVer may flag version
strings as unusual -- this is expected and acceptable.
