# NEXUS -- Product Vision

## User persona

Primary: ServiceNow Solution Consultants and Architects at ServiceNow.
Secondary: Technical customers who want to automate SN configurations.
"Lambda users" (non-technical): can use the tool via `nexus apply <template>` or
the NiceGUI dashboard without touching a terminal.

## CLI surface

Shipped:
nexus setup                        -- first-run wizard (credentials, config, sync)
nexus status                       -- instance connection + capability summary
nexus reauth [--server <name>]     -- print re-auth command(s) for MCP servers
nexus update [--check-only]        -- check for / install a NEXUS update
nexus sync                         -- pull latest templates + product catalog from GitHub
nexus templates                    -- show the cached template catalog (flat; no subcommands)
nexus apply <template>             -- deploy a template (deterministic render + push)
nexus instance <list|status|register|use|connect|refresh|delete|diagnose-roles>
nexus capture <discover|pull|list|push>   -- scope config -> update-set archive -> push
nexus schema <products|erd>        -- reverse-engineer SN tables into ERDs
nexus plugins <list|info|diff|advisories|impact|orphans|drift|outdated|export|
               install|activate|upgrade|apply|deactivate|uninstall|recommend|baselines>
nexus assess                       -- standalone instance health scan
nexus assess --for <template>      -- readiness check only (no deploy)
nexus assess --job <id>            -- validate a past deployment
nexus assess inventory <profile>   -- replatform use-case inventory
nexus assess migration --from <old> --to <new>   -- cross-instance migration checklist
nexus migrate <select|plan|preflight>            -- selective-migration planner

Planned / stubbed:
nexus run "<request>"              -- free-form AI orchestration (stub)
nexus rollback <job-id>            -- undo a previous deployment (stub)
nexus ui                           -- NiceGUI dashboard (nexus-sn[ui], not built)

## Install profiles

pip install nexus-sn              -- CLI (all shipped features)
pip install nexus-sn[ui]          -- + NiceGUI dashboard extra (dashboard itself planned)

(Only the `ui` extra is defined in pyproject.toml.)

## Template types (GitHub repo root: templates/)

Live (Pydantic schema + loadable):
now-assist-skill    -- Now Assist skill definitions
workflow            -- Flow Designer flows and subflows

Planned (schema stubs, not yet loadable):
ai-agent            -- SN AI Agent Studio agent definitions
catalog-item        -- Service catalog items
business-rule       -- Business rules
recipe              -- Any table, any record (lowest-level config unit)
project             -- High-level blueprint: references multiple templates

assessments/health       -- Health scan rulesets (run by nexus assess)
assessments/readiness    -- Pre-deploy readiness checks (gate 1)
assessments/validation   -- Post-deploy validation checks (gate 2)

## Shipped capabilities (beyond template apply)

NEXUS shipped a set of deterministic ServiceNow analysis/migration tools, each
wired into the CLI:

- Schema cartographer (nexus schema) -- reverse-engineers SN table schemas into
  Mermaid/image ERDs per product; GitHub-synced product catalog.
- Plugin management (nexus plugins) -- inventory, advisories, impact, orphan and
  drift analysis, baselines, and install/activate/upgrade/deactivate/uninstall
  lifecycle over REST.
- Capture (nexus capture) -- discover/pull scope config into update-set archives
  and push them to a target instance.
- Replatform analysis (nexus assess inventory/migration) -- bi-directional
  use-case + workflow checklist across two instances (deterministic, natural-key
  matching, advisory only).
- Migration planner (nexus migrate) -- dependency-closure + waved,
  approval-gated, hand-executable migration runbooks with drift re-check and a
  preflight probe. Advisory only.

## Assessment gates

Gate 1 (readiness) and Gate 2 (validation) back the assess flows today via
`nexus assess` (--for = gate 1, --job = gate 2). Auto-running them inside
`nexus apply` is planned -- apply is currently a single-phase deterministic
render + push.

Gate 1 -- Readiness (before deploy):
  - Plugins installed?
  - License tier matches template requirements?
  - Existing data conflicts?
  - SN version >= template.sn_version?
  FAIL = stop and report. PASS = proceed to planning.

Gate 2 -- Validation (after deploy):
  - All expected records created?
  - Required fields populated?
  - CSDM relationships valid?
  FAIL = offer rollback. PASS = generate final report.

Standalone: nexus assess runs health rulesets from templates/assessments/health/
and produces a scored HTML report.

## Two-phase execution (planned -- not yet built)

The eventual apply model. Today `nexus apply` is a single-phase deterministic
path (load -> render records -> create one update set -> push); the planner /
dispatcher / reporter (src/nexus/execution/) and specialist agents are stubs.

Phase 1 -- Planning (with human approval checkpoint):
  Instance scan -> knowledge lookup -> solution design
  Rollback plan generation -> HTML executive briefing -> USER APPROVAL

Phase 2 -- Parallel dispatch (autonomous after approval):
  Task graph with dependency resolution
  Agents activate in parallel when their dependencies resolve
  Execution context registry passes sys_ids between tasks
  Post-deploy validation (gate 2)

## Enterprise MCP integration

ServiceNow has configured MCP servers inside the Claude Enterprise account. These are
not services NEXUS calls directly -- they are injected into the Anthropic API session
by the enterprise account configuration. When NEXUS makes an Anthropic API call using
the enterprise API key, those MCP tools become available to Claude as additional tools.

At startup NEXUS detects which servers are available by reading Claude Code's local
state -- its config (~/.claude.json), the OS-keychain credentials entry, and its MCP
re-auth cache -- via a TierDetector. Results build a CapabilitySet; features tied to
unavailable servers are hidden from CLI help and skipped (graceful degradation, no
errors). (A direct Anthropic-API probe path, MCPProbe, is scaffolded but stubbed
until the enterprise MCP server endpoints are known.)

Known servers:
  value_melody   -- ROI, VE pipeline, value calculations
  ssc            -- Sales Success Center: content, competitive intel, battle cards
  bt1            -- Internal SN work item tracking and project data
  data_analytics -- Snowflake-based customer analytics and account insights
  gtm            -- Deal registration, partner data
  m365           -- Email, calendar, SharePoint content
  marketing      -- Marketing operations (campaign analytics)

## Web UI (Phase 2 -- not MVP)

NiceGUI (pip install nexus-sn[ui]). Pure Python. No Node.js ever.
Runs at localhost:7000. Launched via `nexus ui`.
Control plane: real authority to pause, inspect, redirect agent execution.
