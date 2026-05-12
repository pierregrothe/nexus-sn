# Plugin AI Recommendations Implementation Plan

> REQUIRED SUB-SKILL: superpowers:subagent-driven-development.

**Spec:** [2026-05-12-plugin-ai-recommendations-design.md](../specs/2026-05-12-plugin-ai-recommendations-design.md)

---

## File Structure

| File | Responsibility | Task |
|------|----------------|------|
| `src/nexus/plugins/recommendations.py` (new) | Three context-builders + system prompts + model constant. | 1 |
| `src/nexus/plugins/__init__.py` | Re-export the three builders. | 1 |
| `src/nexus/cli.py` | `plugins recommend deactivate`, `plugins explain`, `plugins roadmap`. Module-level `_agent_client_factory` for test injection. | 2, 3, 4 |
| `tests/fakes/fake_agent_client.py` (new) | FakeAgentClient that records prompts and returns canned strings. | 2 |
| `tests/test_plugins_recommendations.py` (new) | Builder tests. | 1 |
| `tests/test_cli_plugins_recommend.py` (new) | CLI tests for all three subcommands. | 2-4 |
| `.ratchet.json` | Coverage bump. | 5 |

---

## Task 1: recommendations.py (builders + system prompts)

**Files:** `src/nexus/plugins/recommendations.py`, `src/nexus/plugins/__init__.py`, `tests/test_plugins_recommendations.py`.

- [ ] **Step 1: Tests.** Each builder is pure; assert the produced string contains the inputs and the required markdown structure.

```python
# tests/test_plugins_recommendations.py
# Tests for context-builder functions in recommendations.py.
# Author: Pierre Grothe
# Date: 2026-05-12
"""Tests for build_deactivation_context, build_explain_context, build_roadmap_context."""

from datetime import UTC, datetime

from nexus.plugins.models import (
    AdvisoryFinding,
    AdvisorySet,
    AdvisoryType,
    CrossScopeRef,
    PluginImpact,
    PluginInfo,
    PluginInventory,
    ScopeRecordCount,
    Severity,
)
from nexus.plugins.recommendations import (
    AI_MODEL,
    DEACTIVATE_SYSTEM_PROMPT,
    EXPLAIN_SYSTEM_PROMPT,
    ROADMAP_SYSTEM_PROMPT,
    build_deactivation_context,
    build_explain_context,
    build_roadmap_context,
)

__all__: list[str] = []


def _info(plugin_id: str = "com.x", state: str = "active") -> PluginInfo:
    return PluginInfo.model_validate(
        {
            "plugin_id": plugin_id,
            "name": plugin_id,
            "version": "1.0",
            "state": state,
            "source": "store",
            "product_family": "Uncategorized",
            "depends_on": (),
            "sys_id": f"sys-{plugin_id}",
            "installed_at": None,
            "record_counts": (),
        }
    )


def _inventory(*plugins: PluginInfo) -> PluginInventory:
    return PluginInventory(
        captured_at=datetime(2026, 5, 12, tzinfo=UTC),
        sn_version="Xanadu",
        plugins=plugins,
    )


def _finding(plugin_id: str = "com.x", severity: Severity = Severity.HIGH) -> AdvisoryFinding:
    return AdvisoryFinding(
        plugin_id=plugin_id,
        plugin_name=plugin_id,
        plugin_version="1.0",
        advisory_type=AdvisoryType.CVE,
        severity=severity,
        summary="example",
        details="CVE-2024-1",
    )


def test_ai_model_is_haiku() -> None:
    assert AI_MODEL == "claude-haiku-4-5-20251001"


def test_deactivate_context_lists_orphans() -> None:
    inv = _inventory(_info("com.lonely"), _info("com.busy"))
    advisories = AdvisorySet(findings=())
    text = build_deactivation_context(inv, advisories, orphans=(_info("com.lonely"),))
    assert "com.lonely" in text
    assert "Top candidates" in text or "candidates" in text.lower()


def test_deactivate_context_includes_advisories() -> None:
    inv = _inventory(_info("com.x"))
    advisories = AdvisorySet(findings=(_finding("com.x", Severity.CRITICAL),))
    text = build_deactivation_context(inv, advisories, orphans=())
    assert "com.x" in text
    assert "CVE-2024-1" in text


def test_explain_context_includes_plugin_and_impact() -> None:
    plugin = _info("com.target")
    impact = PluginImpact(
        target_plugin_id="com.target",
        target_name="com.target",
        reverse_deps=(),
        record_counts=(ScopeRecordCount(table="t1", count=10),),
        counts_available=True,
        cross_scope_refs=(
            CrossScopeRef(
                source_scope="com.other",
                source_table="incident",
                field="ci",
                target_table="cmdb_ci",
                record_count=42,
            ),
        ),
        cross_scope_available=True,
    )
    text = build_explain_context(plugin, impact, advisories=())
    assert "com.target" in text
    assert "t1" in text
    assert "incident" in text


def test_explain_context_includes_advisories_when_present() -> None:
    plugin = _info("com.target")
    impact = PluginImpact(
        target_plugin_id="com.target",
        target_name="com.target",
        reverse_deps=(),
        record_counts=(),
        counts_available=True,
    )
    text = build_explain_context(plugin, impact, advisories=(_finding("com.target"),))
    assert "CVE-2024-1" in text


def test_roadmap_context_orders_critical_first() -> None:
    advisories = AdvisorySet(
        findings=(
            _finding("com.high", Severity.HIGH),
            _finding("com.critical", Severity.CRITICAL),
        )
    )
    text = build_roadmap_context(
        _inventory(_info("com.high"), _info("com.critical")),
        advisories,
        orphans=(),
        deferred_count=0,
    )
    assert text.index("com.critical") < text.index("com.high")


def test_roadmap_context_includes_orphan_section_when_present() -> None:
    text = build_roadmap_context(
        _inventory(_info("com.lonely")),
        AdvisorySet(findings=()),
        orphans=(_info("com.lonely"),),
        deferred_count=0,
    )
    assert "com.lonely" in text


def test_roadmap_context_includes_deferred_count() -> None:
    text = build_roadmap_context(
        _inventory(),
        AdvisorySet(findings=()),
        orphans=(),
        deferred_count=3,
    )
    assert "3" in text
    assert "defer" in text.lower()


def test_system_prompts_are_nonempty() -> None:
    for p in (DEACTIVATE_SYSTEM_PROMPT, EXPLAIN_SYSTEM_PROMPT, ROADMAP_SYSTEM_PROMPT):
        assert isinstance(p, str)
        assert len(p) > 50
```

- [ ] **Step 2: Run tests, expect failures.**

- [ ] **Step 3: Implement `src/nexus/plugins/recommendations.py`:**

```python
# src/nexus/plugins/recommendations.py
# Context-builders and system prompts for AI plugin recommendations.
# Author: Pierre Grothe
# Date: 2026-05-12
"""Pure prompt-builders feeding AgentClient for plugins recommend/explain/roadmap."""

from nexus.plugins.models import (
    AdvisoryFinding,
    AdvisorySet,
    PluginImpact,
    PluginInfo,
    PluginInventory,
    Severity,
)

__all__ = [
    "AI_MODEL",
    "DEACTIVATE_SYSTEM_PROMPT",
    "EXPLAIN_SYSTEM_PROMPT",
    "ROADMAP_SYSTEM_PROMPT",
    "build_deactivation_context",
    "build_explain_context",
    "build_roadmap_context",
]

AI_MODEL = "claude-haiku-4-5-20251001"

DEACTIVATE_SYSTEM_PROMPT = (
    "You are a ServiceNow architect helping the user identify plugins that are "
    "safe to deactivate. Be conservative: prefer flagging plugins with zero "
    "records, no dependents, and no critical advisories. Output two markdown "
    "sections ('### Top candidates' and '### Watch out') with one-line "
    "rationales per bullet. Limit to 10 candidates total."
)

EXPLAIN_SYSTEM_PROMPT = (
    "You are a ServiceNow architect explaining one plugin to the user. "
    "Output four short markdown sections: '## What it does' (2-3 lines), "
    "'## Why you might keep it' (bulleted), '## Why you might drop it' "
    "(bulleted), and '## Verdict' (3 lines max). Ground every claim in the "
    "evidence provided -- do not invent numbers."
)

ROADMAP_SYSTEM_PROMPT = (
    "You are a ServiceNow architect drafting a remediation roadmap. Output an "
    "ordered markdown list, critical-severity items first, then high, then "
    "orphan cleanup, then a review-deferred-overrides reminder if any "
    "overrides are deferred. Each item: 'Action: <verb phrase> (rationale)'. "
    "Keep it under 15 items."
)


def _summarize_plugin(plugin: PluginInfo) -> str:
    return (
        f"- {plugin.plugin_id} (state={plugin.state}, version={plugin.version}, "
        f"family={plugin.product_family})"
    )


def _summarize_finding(finding: AdvisoryFinding) -> str:
    return (
        f"- [{finding.severity.value}] {finding.plugin_id} "
        f"({finding.advisory_type.value}): {finding.summary} ({finding.details})"
    )


def build_deactivation_context(
    inventory: PluginInventory,
    advisories: AdvisorySet,
    orphans: tuple[PluginInfo, ...],
) -> str:
    """Build the user prompt for `plugins recommend deactivate`.

    Args:
        inventory: Captured plugin inventory.
        advisories: All findings (CVE / EOL / license) for filtering critical/high.
        orphans: Output of ``orphan_candidates(inventory)``.

    Returns:
        Markdown-ish prompt string.
    """
    lines: list[str] = ["# Deactivation analysis", ""]
    lines.append(f"Total plugins: {len(inventory.plugins)}")
    active = sum(1 for p in inventory.plugins if p.state == "active")
    lines.append(f"Active: {active}; Inactive: {len(inventory.plugins) - active}")
    lines.append("")

    lines.append("## Orphan candidates (zero deps + zero records)")
    if not orphans:
        lines.append("- (none)")
    else:
        lines.extend(_summarize_plugin(p) for p in orphans)
    lines.append("")

    severe_findings = tuple(
        f for f in advisories.findings if f.severity in (Severity.CRITICAL, Severity.HIGH)
    )
    lines.append("## Critical/high advisories")
    if not severe_findings:
        lines.append("- (none)")
    else:
        lines.extend(_summarize_finding(f) for f in severe_findings)
    lines.append("")

    lines.append("## All plugins")
    lines.extend(_summarize_plugin(p) for p in inventory.plugins)

    return "\n".join(lines)


def build_explain_context(
    plugin: PluginInfo,
    impact: PluginImpact,
    advisories: tuple[AdvisoryFinding, ...],
) -> str:
    """Build the user prompt for `plugins explain <plugin_id>`.

    Args:
        plugin: PluginInfo for the target plugin.
        impact: Output of ``compute_impact``.
        advisories: All findings matching ``plugin.plugin_id``.

    Returns:
        Markdown-ish prompt string.
    """
    lines: list[str] = [
        f"# Plugin: {plugin.plugin_id}",
        "",
        f"Name: {plugin.name}",
        f"Version: {plugin.version}",
        f"State: {plugin.state}",
        f"Vendor: {plugin.vendor or '(unknown)'}",
        f"Product family: {plugin.product_family}",
        f"Source: {plugin.source}",
        "",
        "## Reverse dependencies",
    ]
    if not impact.reverse_deps:
        lines.append("- (none)")
    else:
        for dep in impact.reverse_deps:
            lines.append(f"- {dep.plugin_id} ({dep.state}, depth {dep.depth})")
    lines.append("")

    lines.append("## Records owned by this scope")
    if not impact.counts_available:
        lines.append("- (counts unavailable)")
    elif not impact.record_counts:
        lines.append("- (zero records)")
    else:
        total = sum(c.count for c in impact.record_counts)
        lines.append(f"Total: {total:,}")
        for c in impact.record_counts[:5]:
            lines.append(f"- {c.table}: {c.count:,}")
    lines.append("")

    lines.append("## Tables pointing into this scope")
    if not impact.cross_scope_available:
        lines.append("- (not scanned)")
    elif not impact.cross_scope_refs:
        lines.append("- (no inbound references)")
    else:
        for r in impact.cross_scope_refs[:5]:
            lines.append(
                f"- {r.source_table}.{r.field} (scope {r.source_scope}): "
                f"{r.record_count:,} records"
            )
    lines.append("")

    lines.append("## Advisories")
    if not advisories:
        lines.append("- (none)")
    else:
        lines.extend(_summarize_finding(f) for f in advisories)
    return "\n".join(lines)


def build_roadmap_context(
    inventory: PluginInventory,
    advisories: AdvisorySet,
    orphans: tuple[PluginInfo, ...],
    deferred_count: int,
) -> str:
    """Build the user prompt for `plugins roadmap`.

    Args:
        inventory: Captured plugin inventory.
        advisories: All findings.
        orphans: Output of ``orphan_candidates``.
        deferred_count: Number of deferred-override entries on the instance.

    Returns:
        Markdown-ish prompt string.
    """
    sev_order = {
        Severity.CRITICAL: 0,
        Severity.HIGH: 1,
        Severity.MEDIUM: 2,
        Severity.LOW: 3,
    }
    by_sev = sorted(advisories.findings, key=lambda f: (sev_order[f.severity], f.plugin_id))
    lines: list[str] = [
        "# Remediation roadmap inputs",
        "",
        f"Inventory: {len(inventory.plugins)} plugins captured.",
        f"Deferred overrides on this instance: {deferred_count}",
        "",
        "## Advisories (sorted by severity)",
    ]
    if not by_sev:
        lines.append("- (none)")
    else:
        lines.extend(_summarize_finding(f) for f in by_sev)
    lines.append("")

    lines.append("## Orphan candidates")
    if not orphans:
        lines.append("- (none)")
    else:
        lines.extend(_summarize_plugin(p) for p in orphans)
    return "\n".join(lines)
```

- [ ] **Step 4: Re-export** from `src/nexus/plugins/__init__.py`: `AI_MODEL`, `build_deactivation_context`, `build_explain_context`, `build_roadmap_context`.

- [ ] **Step 5: Run tests + suite. Commit.**

```bash
git commit -m "feat(plugins): AI context-builders for recommend/explain/roadmap"
```

---

## Task 2: FakeAgentClient + `nexus plugins recommend deactivate`

**Files:** `tests/fakes/fake_agent_client.py`, `src/nexus/cli.py`, `tests/test_cli_plugins_recommend.py`.

- [ ] **Step 1: Build `FakeAgentClient`** at `tests/fakes/fake_agent_client.py`:

```python
# tests/fakes/fake_agent_client.py
# Fake AgentClient that records prompts and returns canned responses.
# Author: Pierre Grothe
# Date: 2026-05-12
"""FakeAgentClient: protocol-compatible stand-in for AgentClient."""

from dataclasses import dataclass, field

__all__ = ["FakeAgentClient"]


@dataclass
class _RecordedCall:
    prompt: str
    system: str | None
    model: str | None
    max_turns: int


@dataclass
class FakeAgentClient:
    """In-memory AgentClient implementing AgentClientProtocol."""

    response: str = "FAKE RESPONSE"
    calls: list[_RecordedCall] = field(default_factory=list)

    async def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        model: str | None = None,
        max_turns: int = 1,
    ) -> str:
        self.calls.append(_RecordedCall(prompt, system, model, max_turns))
        return self.response
```

- [ ] **Step 2: Add factory + command** in `src/nexus/cli.py`. Near the top of the file:

```python
def _agent_client_factory() -> "AgentClientProtocol":
    """Default AgentClient factory; monkeypatched in tests."""
    from nexus.api.agent_client import AgentClient  # noqa: PLC0415  (lazy import)

    return AgentClient()
```

Add a typer sub-app:

```python
recommend_app = typer.Typer(no_args_is_help=True, help="AI recommendations.")
plugins_app.add_typer(recommend_app, name="recommend")


@recommend_app.command("deactivate")
def plugins_recommend_deactivate(
    instance: Annotated[
        str,
        typer.Option("--instance", help="Instance profile (default: configured default)"),
    ] = "",
) -> None:
    """List plugins safest to deactivate, with AI rationale."""
    from nexus.api.errors import AnthropicError  # noqa: PLC0415
    from nexus.plugins.advisories import AdvisoryDatabase, compute_advisories
    from nexus.plugins.orphans import orphan_candidates
    from nexus.plugins.recommendations import (
        AI_MODEL,
        DEACTIVATE_SYSTEM_PROMPT,
        build_deactivation_context,
    )

    _, inventory = _load_inventory_or_exit(instance)
    db = AdvisoryDatabase.load()
    advisories = compute_advisories(inventory, db, today=datetime.now(UTC).date())
    orphans = orphan_candidates(inventory)
    if not orphans and not advisories.findings:
        console.print(Notice.info("No orphans or advisories -- nothing to recommend."))
        return
    prompt = build_deactivation_context(inventory, advisories, orphans=orphans)
    client = _agent_client_factory()
    try:
        text = asyncio.run(
            client.complete(prompt, system=DEACTIVATE_SYSTEM_PROMPT, model=AI_MODEL)
        )
    except AnthropicError as exc:
        console.print(Notice.error(f"AI request failed: {exc}"))
        raise typer.Exit(1) from exc
    console.print(text)
```

- [ ] **Step 3: Tests** at `tests/test_cli_plugins_recommend.py`. Cover:
  - `nexus plugins recommend deactivate` with FakeAgentClient -- text prints, recorded prompt contains plugin IDs.
  - `--instance` flag routes through the profile.
  - Empty inputs (no orphans, no advisories) short-circuit without calling the client.
  - `AnthropicError` is caught and the command exits 1.

Each test monkeypatches `_agent_client_factory` to return a FakeAgentClient.

- [ ] **Step 4: Run tests + commit.**

```bash
git commit -m "feat(cli): plugins recommend deactivate via AgentClient"
```

---

## Task 3: `nexus plugins explain <plugin_id>`

**Files:** `src/nexus/cli.py`, `tests/test_cli_plugins_recommend.py`.

- [ ] Implement `plugins_explain`. Gathers `PluginInfo` from inventory, runs `compute_impact` (no live -- use cached `record_counts`; pass `cross_scope=False` to avoid extra REST hops in tests), filters advisories to the plugin. Pass to `build_explain_context`, then to `AgentClient.complete`.

```python
@plugins_app.command("explain")
def plugins_explain(
    plugin_id: Annotated[str, typer.Argument(help="Plugin to explain.")],
    instance: Annotated[
        str,
        typer.Option("--instance", help="Instance profile (default: configured default)"),
    ] = "",
) -> None:
    """Explain what a plugin does and whether the user likely needs it."""
    from nexus.api.errors import AnthropicError  # noqa: PLC0415
    from nexus.plugins.advisories import AdvisoryDatabase, compute_advisories
    from nexus.plugins.impact import compute_impact
    from nexus.plugins.recommendations import (
        AI_MODEL,
        EXPLAIN_SYSTEM_PROMPT,
        build_explain_context,
    )

    _, inventory = _load_inventory_or_exit(instance)
    plugin = next((p for p in inventory.plugins if p.plugin_id == plugin_id), None)
    if plugin is None:
        console.print(Notice.error(f"Plugin not found: {plugin_id}"))
        raise typer.Exit(1)
    _registry, meta, token, _expiry = _acquire_token(instance)
    transport = _impact_transport()
    impact = asyncio.run(
        compute_impact(
            inventory,
            plugin_id,
            url=meta.url,
            token=token,
            transport=transport,
            cross_scope=False,
        )
    )
    db = AdvisoryDatabase.load()
    advisories = compute_advisories(inventory, db, today=datetime.now(UTC).date())
    plugin_findings = tuple(f for f in advisories.findings if f.plugin_id == plugin_id)
    prompt = build_explain_context(plugin, impact, plugin_findings)
    client = _agent_client_factory()
    try:
        text = asyncio.run(
            client.complete(prompt, system=EXPLAIN_SYSTEM_PROMPT, model=AI_MODEL)
        )
    except AnthropicError as exc:
        console.print(Notice.error(f"AI request failed: {exc}"))
        raise typer.Exit(1) from exc
    console.print(text)
```

- [ ] **Tests**: explain command prints fake response; explain with unknown plugin_id exits 1; client called with correct system prompt.

- [ ] **Commit:**

```bash
git commit -m "feat(cli): plugins explain via AgentClient"
```

---

## Task 4: `nexus plugins roadmap`

**Files:** `src/nexus/cli.py`, `tests/test_cli_plugins_recommend.py`.

- [ ] Implement `plugins_roadmap`. Gathers inventory + advisories + orphans + deferred-overrides count. Passes to `build_roadmap_context`.

```python
@plugins_app.command("roadmap")
def plugins_roadmap(
    instance: Annotated[
        str,
        typer.Option("--instance", help="Instance profile (default: configured default)"),
    ] = "",
) -> None:
    """Draft an AI-generated remediation roadmap."""
    from nexus.api.errors import AnthropicError  # noqa: PLC0415
    from nexus.plugins.advisories import AdvisoryDatabase, compute_advisories
    from nexus.plugins.orphans import orphan_candidates
    from nexus.plugins.recommendations import (
        AI_MODEL,
        ROADMAP_SYSTEM_PROMPT,
        build_roadmap_context,
    )

    meta, inventory = _load_inventory_or_exit(instance)
    db = AdvisoryDatabase.load()
    advisories = compute_advisories(inventory, db, today=datetime.now(UTC).date())
    orphans = orphan_candidates(inventory)

    paths = NexusPaths.from_env()
    registry = InstanceRegistry(paths.instances_dir)
    overrides = registry.load_advisory_overrides(meta.profile)
    deferred = len(overrides.overrides)

    if not advisories.findings and not orphans and deferred == 0:
        console.print(Notice.info("Nothing to remediate -- no advisories, orphans, or overrides."))
        return

    prompt = build_roadmap_context(
        inventory, advisories, orphans=orphans, deferred_count=deferred
    )
    client = _agent_client_factory()
    try:
        text = asyncio.run(
            client.complete(prompt, system=ROADMAP_SYSTEM_PROMPT, model=AI_MODEL)
        )
    except AnthropicError as exc:
        console.print(Notice.error(f"AI request failed: {exc}"))
        raise typer.Exit(1) from exc
    console.print(text)
```

- [ ] **Tests**: roadmap prints fake response; empty short-circuit; deferred-count passed through.

- [ ] **Commit:**

```bash
git commit -m "feat(cli): plugins roadmap via AgentClient"
```

---

## Task 5: Coverage ratchet + final pre-commit

- [ ] Focused coverage on `nexus.plugins.recommendations`, `nexus.cli`.
- [ ] Bump `.ratchet.json`. Add new entry `nexus.plugins.recommendations`.
- [ ] `pre-commit run --all-files` clean.
- [ ] Commit:

```bash
git commit -m "chore(ratchet): bump coverage baselines after sub-project E"
```

---

## Self-Review

Spec coverage: three context-builders + system prompts (T1), `recommend deactivate` (T2), `explain` (T3), `roadmap` (T4), ratchet (T5). Type consistency: builders return `str`; CLI commands take `--instance` only.
