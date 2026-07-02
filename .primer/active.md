# NEXUS -- Active Work

Last updated: 2026-07-02
Session: implemented and live-proved the Replatform Checklist coverage
extension (plan docs/superpowers/plans/2026-07-01-replatform-gap-closure.md)
via subagent-driven development: 7 TDD tasks + final whole-branch review, all
approved. Branch feat/2026.07-replatform-coverage ready for PR.

## Current Focus

On branch: feat/2026.07-replatform-coverage
Version: 2026.06.0 (tagged); replatform coverage extension pending PR to main

Active: Replatform Checklist v1 shipped (PRs #55/#56) and coverage extension
complete on this branch: DEVELOPER_PLATFORM table group (8 tables), global
scope customer-updated artifacts, per-app use-case naming (0 Uncategorized on
live data), --group / --domain-map flags, multiset natural-key matching,
absent-table + unnamed-artifact warnings. Live-proven vs alectri/retail
2026-07-02: 30,463 artifacts / 95 named use cases; raw-REST spot-checks incl.
a real duplicate-name multiset case. Proof pack:
artifacts/replatform-proof/verification-summary.md (v2 section).

Context: financial-services customer replatform conversation (old -> new
instance). Meeting-prep assessment 2026-07-01 identified the coverage gaps
this branch closes.

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

- fde7c92 docs(replatform): gitignore raw v2 inventories; date-fence pre-v2 reply
- 4a61baf fix(replatform): translate YAML parse errors, dedupe --group, wiring guards
- b20b401 docs(replatform): v2 proof pack + coverage docs (30,463 artifacts live-proven)
- 00d4daa..fd80033 feat(replatform): coverage extension (7 tasks -- multiset diff,
  warnings, per-app domains, --domain-map, developer_platform group, global scope)
- 094bd09 docs: sync README + CLI discovery text with shipped assess feature (on main)

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
- sys_security_acl listing returns 400/404 on the demo pair (surfaced by the
  new absent-table warning, excluded from counts); root cause on a customer
  instance TBD -- likely ACL-table REST restrictions.

## Next Steps

1. Push feat/2026.07-replatform-coverage and open the PR (final review: Ready
   to merge Yes).
2. Follow-ups deliberately deferred (see plan Out-of-scope): offline
   --from-archive mode, ApplyEngine v2 / capture-push completion (needs ADR),
   catalog items / notifications coverage, nexus --version + lazy-import
   startup fix.
3. Replatform v2 AI enrichment awaits the agent-specialists epic.
4. Pick next sprint: agent-specialists (largest) or distribution (smallest).

## Branch / remote state

On branch feat/2026.07-replatform-coverage (11 commits ahead of main's
094bd09; main itself is 1 commit ahead of origin -- README/help-text doc fix
not yet pushed). main is the integration target. Latest tag: 2026.06.0
