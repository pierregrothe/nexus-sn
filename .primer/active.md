# NEXUS -- Active Work

Last updated: 2026-06-29
Session: scaffolded the 2026.07 Replatform Checklist milestone -- promoted the
`nexus assess inventory` / `assess migration` feature from backlog to a full
milestone (charter.md created, ADR-025, PRD-004, epic with 6 stories) off an
adversarially-validated brainstorm. Spec + governance only; no code yet.

## Current Focus

On branch: primer/replatform-checklist-milestone
Version: 2026.06.0 (tagged for release)

Active: 2026.07 Replatform Checklist scaffolded and ready for implementation.
  Epic: epics/2026.07-nexus-replatform-checklist/ (6 stories, all backlog)
  Start: 01-replatform-models.story.md

Other roadmap candidates:
* `2026.07-agent-specialists` -- 8 domain specialists + ExecutionContext
  enrichment + Planner/Dispatcher + rollback manager. (Replatform v2 AI
  enrichment depends on this.)
* `2026.08-distribution` -- 100% line coverage push + README + PyPI publish.
* Schema fast-follows -- local graphviz renderer (preferred over Kroki/mmdc),
  record-level config-trace, nexus schema diff, more products in catalog.
* License Audit (nexus.licenses) -- role-check, user-exposure, assess
  license-exposure; product-agnostic, scope-driven from sys_scope.

## Recent Changes

- primer: scaffold 2026.07 Replatform Checklist milestone (charter, ADR-025,
  PRD-004, epic + 6 stories) -- uncommitted history captured on branch
- 2026.06.0 -- version bump + release tag
- #54 feat(schema): replace hardcoded areas.py with GitHub-synced product catalog
- docs: rename License Audit to platform-agnostic naming in roadmap
- docs(readme): update schema section, test count, roadmap Gantt

## Open Blockers

- MCPProbe._check_server() still stubbed; enterprise MCP endpoints unknown.
- knowledge/mastery/ empty (decision pending: copy from JARVIS or rebuild).
- `nexus run`, `nexus rollback` still raise NotImplementedError.
- `nexus apply --live` capture-runner and ApplyEngine factory raise
  NotImplementedError until ServiceNowClient + CaptureEngine pairing wired.
- sys_update_xml direct-REST POST blocked by SN ACL even for admin via OAuth
  Bearer (affects `nexus apply` and `nexus capture push`). See decisions.md
  2026-05-19 entry + backlog "ApplyEngine v2".
- Plugin deactivate/uninstall are SN-platform-blocked at the OAuth/REST
  boundary; surfaced as clean failures.
- Kroki public instance (kroki.io) intermittently hits disk-full errors;
  local graphviz renderer is on the roadmap as the replacement.

## Next Steps

1. Implement 2026.07 Replatform Checklist: superpowers writing-plans on
   01-replatform-models.story.md, then stories 02-06 in dependency order.
2. Tag and verify 2026.06.0 GitHub Release wheel builds correctly.
3. Pick a parallel sprint: agent-specialists (largest) or distribution (smallest).
4. Schema fast-follow: local graphviz renderer.

## Branch / remote state

On branch primer/replatform-checklist-milestone (milestone scaffolding).
main is the integration target. Latest tag: 2026.06.0
