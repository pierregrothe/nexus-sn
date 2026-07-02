# NEXUS -- Replatform Checklist (assess inventory / assess migration)

## What it answers

"Compare an existing ServiceNow deployment against a new clean instance and
produce a checklist of the use cases and workflows that still need to be built
on the new one."

Two commands:

| Command | What it does |
|---|---|
| `nexus assess inventory <instance>` | Classifies one instance's custom config into a use-case inventory (grouped by product domain). |
| `nexus assess migration --from <old> --to <new>` | Bi-directional diff of two instances into a per-use-case + per-workflow checklist for the new instance. |

Optional flags on `migration`: `--scope-alias OLD=NEW` (handles an app whose
scope was renamed on the new instance, repeatable) and `--out <file>` (writes
the checklist as markdown). Both commands also accept `--group <key>`
(restrict to a table group, repeatable; default all) and
`--domain-map <file>` (YAML `scope: Domain` overlay for business-domain
grouping).

## The checklist

GitHub-flavored markdown with task-list checkboxes that tick themselves as work
lands on the new instance -- re-run any time to refresh. Every row is statused:

- `DONE`    -- exists on both; already built on the new instance (`- [x]`)
- `TODO`    -- on the old instance, not yet on the new one; this is the build list (`- [ ]`)
- `PARTIAL` -- a use case partly migrated, shown with a built/total fraction (e.g. 553/558)
- `EXTRA`   -- on the new instance but not the old; flags scope creep / things to confirm

Matching is on a normalized name key (`scope | type | name`), never on internal
sys_ids, so a rebuilt artifact still matches its original. The layer is strictly
read-only and advisory -- it never modifies either instance.

## What it covers today (be precise with the prospect)

The inventory covers customer-developed artifacts in two table groups, for
custom-scoped (x_/u_) applications AND customer-created/modified artifacts in
the global scope (`sys_customer_update=true`):

**AI & Automation** (`--group ai_automation`):

- Flows & subflows (`sys_hub_flow`)
- IntegrationHub actions (`sys_hub_action_type_definition`)
- Virtual Agent topics (`virtual_agent_conversation_topic`)
- NowAssist skills (`ai_skill`)
- AI Agents (`sys_ai_agent`)

**Developer Platform** (`--group developer_platform`):

- Business rules (`sys_script`)
- Script includes (`sys_script_include`)
- Client scripts (`sys_script_client`)
- UI policies (`sys_ui_policy`)
- UI actions (`sys_ui_action`)
- Access controls (`sys_security_acl`)
- Scheduled script jobs (`sysauto_script`)
- Classic workflows (`wf_workflow`)

Not yet covered: catalog items, notifications, CMDB data, transform maps, and
data records generally. A table absent on an instance (plugin not installed,
API-blocked) is excluded AND warned per side -- never silently skipped.

## Domain grouping

Use cases are named after the owning application: catalog-known scopes get the
product name (e.g. Hardware Asset Management), every other application --
custom or global-scope -- gets its own display name (e.g. "Property
Management: 91 workflows"). "Uncategorized" appears only for genuinely
unresolvable scopes. For business-domain rollups ("HR", "Lending Ops"), supply
`--domain-map map.yaml` with `scope_key: Domain` lines -- no code or catalog
change needed. The workflow-level DONE/TODO/EXTRA comparison never depends on
grouping.

## How it maps to the request

| Their ask | What the tool does today | Gap |
|---|---|---|
| Compare existing vs new instance | `assess migration --from --to`, bi-directional diff on normalized keys | none |
| Checklist of use cases and workflows | per-use-case markdown checklist, DONE/TODO/PARTIAL/EXTRA, auto-ticking boxes | "workflows" = the AI/Automation artifact set, not yet every config type |
| For the new clean instance | the TODO list is exactly the old-only items the clean instance still needs | none |
