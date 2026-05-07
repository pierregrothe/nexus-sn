# NEXUS Template Library

This directory is the community template registry. Templates are versioned
YAML files that NEXUS can apply to a ServiceNow instance.

## Template types

| Directory | Type | Description |
|---|---|---|
| `workflows/` | workflow | Flow Designer flows and subflows |
| `ai-agents/` | ai-agent | SN AI Agent Studio agents |
| `now-assist-skills/` | now-assist-skill | Now Assist skill definitions |
| `catalog-items/` | catalog-item | Service catalog items |
| `business-rules/` | business-rule | Business rules |
| `projects/` | project | High-level blueprints referencing other templates |
| `recipes/` | recipe | Low-level SN configuration (any table, any record) |
| `assessments/health/` | assessment/health | Health scan rulesets |
| `assessments/readiness/` | assessment/readiness | Pre-deploy readiness checks |
| `assessments/validation/` | assessment/validation | Post-deploy validation |

## Contributing

See `docs/CONTRIBUTING.md` for the contribution process and YAML schema reference.

All templates are validated against their Pydantic schema via CI before merge.
