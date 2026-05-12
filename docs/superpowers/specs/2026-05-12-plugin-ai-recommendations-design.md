# Plugin AI Recommendations -- Design Spec

**Sub-project:** E
**Status:** Approved for implementation
**Date:** 2026-05-12
**Branch:** `feat/plugins-ai-recommendations` (from `main` at `0f55967`)

## Goal

Add three AI-assisted plugin commands that turn the now-rich inventory
(advisories, impact, orphans, drift, cross-scope refs) into actionable
guidance:

1. **`nexus plugins recommend deactivate`** -- list plugins safest to
   deactivate, with reasoning. Inputs: orphans + low-record-count +
   no-dependents.
2. **`nexus plugins explain <plugin_id>`** -- describe what a plugin
   does and whether the user likely needs it, given its activity on
   their instance.
3. **`nexus plugins roadmap`** -- ordered remediation plan covering
   CVE/EOL advisories, orphan cleanup, deferred-override review.

## Non-Goals

- Streaming output. The agent SDK returns a single concatenated string;
  print it once.
- Multi-turn agent loops. `max_turns=1` for all three commands.
- Tool calls / agent autonomy. The LLM only summarizes the context we
  feed it.
- Persistent recommendation history. Output is rendered to stdout each run.
- AI-suggested override reasons. That belongs in `plugins defer`'s UX.

## Architecture

```
src/nexus/plugins/recommendations.py (new)
    build_deactivation_context(inv, advisories, orphans) -> str
    build_explain_context(inv, plugin_id, impact, advisories) -> str
    build_roadmap_context(inv, advisories, orphans, drift?) -> str

    DEACTIVATE_SYSTEM_PROMPT, EXPLAIN_SYSTEM_PROMPT, ROADMAP_SYSTEM_PROMPT

src/nexus/cli.py
    plugins_recommend_deactivate -- gathers data, calls AgentClient
    plugins_explain
    plugins_roadmap
```

The context-builders are pure: they consume already-computed data and
produce a string suitable as the user prompt. The CLI orchestrates the
data-gathering (calls existing `compute_advisories`, `orphan_candidates`,
optionally `compute_impact`) and the LLM call.

## Context Format

Each builder produces a structured prompt mixing markdown headers + YAML/JSON
fragments. The LLM is instructed (via system prompt) to return concise
markdown sections.

### `build_deactivation_context`

```
inputs:
  - inventory plugin count, active vs inactive
  - orphan_candidates list (zero-record, zero-dependent)
  - advisories: CVEs / EOL only (license deferred for E)
  - dependencies map collapsed to top-level (no recursion)

output: markdown:
  ### Top candidates
  - plugin_id (state): one-line reason

  ### Watch out
  - plugin_id: caveat
```

### `build_explain_context`

```
inputs:
  - plugin_id
  - PluginInfo (name, version, state, product_family, depends_on, vendor)
  - PluginImpact (reverse_deps, record_counts, cross_scope_refs)
  - relevant advisories
  - record_counts (total + top tables)

output: markdown:
  ## What it does
  ## Why you might keep it
  ## Why you might drop it
  ## Verdict (3 lines max)
```

### `build_roadmap_context`

```
inputs:
  - critical/high advisories grouped by plugin
  - orphan_candidates list
  - drift report if a baseline exists (otherwise omit)
  - deferred-override count (audit signal)

output: markdown ordered list:
  1. Action: ... (rationale)
  2. Action: ...
```

## CLI Surface

All three live under `plugins`:

```
nexus plugins recommend deactivate [--instance NAME]
nexus plugins explain <plugin_id> [--instance NAME]
nexus plugins roadmap [--instance NAME]
```

`recommend` is a sub-app (typer.Typer) so `recommend deactivate` reads
naturally. Future intents (`recommend keep`, `recommend upgrade`)
plug in here.

Each command:
1. Resolves the instance (default profile fallback).
2. Loads inventory; bails with the existing helper if missing.
3. Gathers data (advisories from `compute_advisories`, orphans from
   `orphan_candidates`, etc.).
4. Builds the prompt via the relevant context-builder.
5. Calls `AgentClient.complete(prompt, system=..., model=AI_MODEL,
   max_turns=1)`.
6. Prints the response inside a `console.print` block.

## Model Selection

```python
AI_MODEL = "claude-haiku-4-5-20251001"
```

Haiku is cheap and fast enough for context summarization. Constant lives
in `recommendations.py`; tests don't exercise it directly.

## Auth

Inherits the existing `claude-agent-sdk` auth chain (handled inside
`AgentClient`). Users authenticate once via `nexus auth` (already shipped).
The recommendation commands don't surface auth UX.

## Errors

- `compute_advisories` / `orphan_candidates` failures -- already handled
  by their callers; let exceptions propagate.
- `AgentClient.complete` raises `AnthropicError` -- catch in CLI, print
  `Notice.error("AI request failed: <reason>")`, exit 1.
- Empty inputs (no orphans for `deactivate`, no advisories for `roadmap`)
  -- print `Notice.info("Nothing to recommend.")` and exit 0 without
  calling the LLM.

## Testing

- `tests/test_plugins_recommendations.py` (new): builder functions are
  pure -- test their output strings contain the expected sections.
- `tests/test_cli_plugins_recommend.py` (new): use `FakeAgentClient`
  that returns canned strings; assert the commands print them, that
  empty-input cases short-circuit without invoking the client, and
  that `AnthropicError` is handled cleanly.

Inject the agent client via a module-level swappable factory
(`_agent_client_factory()`) so tests can override.

## Out of Scope

- Caching LLM responses across runs. Cost is bounded; users can re-run.
- Streaming UI. Single-shot print is enough.
- Function-calling / tool use. Models receive context as text only.
- Drift integration in `recommend deactivate`. Roadmap covers drift.
