# NEXUS -- Product Vision

## User persona

Primary: ServiceNow Solution Consultants and Architects at ServiceNow.
Secondary: Technical customers who want to automate SN configurations.
"Lambda users" (non-technical): can use the tool via `nexus apply <template>` or
the NiceGUI dashboard without touching a terminal.

## CLI surface (intended)

nexus setup                       -- first-run wizard (credentials, config, sync)
nexus sync                        -- pull latest templates from GitHub
nexus templates list              -- browse available templates
nexus templates info <name>       -- show template details and requirements
nexus apply <template>            -- deploy with readiness gate + post-deploy validation
nexus run "<request>"             -- free-form AI orchestration (no template required)
nexus assess                      -- standalone instance health scan
nexus assess --for <template>     -- readiness check only (no deploy)
nexus assess --job <id>           -- validate a past deployment
nexus rollback <job-id>           -- undo a previous deployment
nexus status                      -- instance connection + capability summary
nexus ui                          -- start NiceGUI dashboard (nexus-sn[ui])

## Install profiles

pip install nexus-sn              -- CLI only (core SN connector)
pip install nexus-sn[ui]          -- CLI + NiceGUI dashboard at localhost:7000
pip install nexus-sn[all]         -- all optional connectors + UI

## Template types (GitHub repo root: templates/)

workflow            -- Flow Designer flows and subflows
ai-agent            -- SN AI Agent Studio agent definitions
now-assist-skill    -- Now Assist skill definitions
catalog-item        -- Service catalog items
business-rule       -- Business rules
recipe              -- Any table, any record (lowest-level config unit)
project             -- High-level blueprint: references multiple templates
assessments/health       -- Health scan rulesets (run by nexus assess)
assessments/readiness    -- Pre-deploy readiness checks (gate 1)
assessments/validation   -- Post-deploy validation checks (gate 2)

## Assessment gates (run automatically with nexus apply)

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

## Two-phase execution (same concept as JARVIS, properly implemented)

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

At startup, NEXUS sends lightweight probes via the Anthropic API to check which servers
respond. Results build a CapabilitySet. Features tied to unavailable servers are hidden
from the CLI help text and silently skipped by agents (graceful degradation, no errors).

Known servers:
  value_melody   -- ROI, VE pipeline, value calculations
  ssc            -- Sales Success Center: content, competitive intel, battle cards
  bt1            -- Internal SN work item tracking and project data
  data_analytics -- Snowflake-based customer analytics and account insights
  gtm            -- Deal registration, partner data
  m365           -- Email, calendar, SharePoint content

## Web UI (Phase 2 -- not MVP)

NiceGUI (pip install nexus-sn[ui]). Pure Python. No Node.js ever.
Runs at localhost:7000. Launched via `nexus ui`.
Control plane: real authority to pause, inspect, redirect agent execution.
