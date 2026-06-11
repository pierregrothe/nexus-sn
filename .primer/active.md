# NEXUS -- Active Work

Last updated: 2026-06-11
Session: shipped Schema Product Catalog (PR #54) -- replaced hardcoded
areas.py with a community-maintained products.json bundled in the package
and updated via `nexus sync`; `nexus schema erd` now accepts product names,
acronyms, or keys (1-2 products); SVG rendered by default. Version bumped
to 2026.06.0 and tagged for release. Battle-tested live against alectri.

## Current Focus

On branch: main (all feature work merged)
Version: 2026.06.0 (tagged for release)

Roadmap candidates for next sprint:
* `2026.07-agent-specialists` -- 8 domain specialists + ExecutionContext
  enrichment + Planner/Dispatcher + rollback manager. Largest scope.
* `2026.08-distribution` -- 100% line coverage push + README + PyPI publish.
  Smallest scope; finishes the package.
* Schema fast-follows -- local graphviz renderer (preferred over Kroki/mmdc),
  record-level config-trace, nexus schema diff, more products in catalog.
* License Audit (nexus.licenses) -- role-check, user-exposure, assess
  license-exposure; product-agnostic, scope-driven from sys_scope.

## Recent Changes

- 2026.06.0 -- version bump + release tag
- #54 feat(schema): replace hardcoded areas.py with GitHub-synced product catalog
- docs: rename License Audit to platform-agnostic naming in roadmap
- docs(readme): update schema section, test count, roadmap Gantt
- primer(roadmap): add License Audit module, schema fast-follows, product catalog shipped

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

1. Tag and verify 2026.06.0 GitHub Release wheel builds correctly.
2. Pick next sprint: agent-specialists (largest) or distribution (smallest).
3. Schema fast-follow: local graphviz renderer.
4. License Audit: nexus licenses role-check <role_name>.

## Branch / remote state

All feature branches deleted. Only main remains.
Latest tag: 2026.06.0
