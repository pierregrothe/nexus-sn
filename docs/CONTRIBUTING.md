# Contributing Templates to NEXUS

## Process

1. Fork the repository.
2. Create a branch: `template/<type>/<name>`.
3. Add your YAML file to the correct `templates/<type>/` directory.
4. Add a test scenario in the `tests:` section of your template.
5. Open a PR -- CI runs `nexus.templates.validator` against your file automatically.
6. After review and merge, run `nexus sync` to pull the update locally.

## Template YAML structure

Every template must include these top-level fields:

```yaml
name: unique-template-name
version: 1.0.0
type: workflow  # one of the supported types
sn_version: ">=Xanadu"
description: "One-line description"

requires:
  - plugin: com.glide.some_plugin   # optional
  - license: itsm_pro               # optional

spec:
  # type-specific configuration

tests:
  - scenario: happy_path
    description: "What this scenario tests"
    expected:
      # what the validator checks after applying
```

## Schema reference

See `docs/TEMPLATE_SCHEMA.md` for the full schema for each template type.
