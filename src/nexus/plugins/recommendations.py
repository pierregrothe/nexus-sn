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
    """Format a single plugin as a brief markdown bullet.

    Args:
        plugin: PluginInfo to summarize.

    Returns:
        Markdown bullet line for the plugin.
    """
    return (
        f"- {plugin.plugin_id} (state={plugin.state}, version={plugin.version}, "
        f"family={plugin.product_family})"
    )


def _summarize_finding(finding: AdvisoryFinding) -> str:
    """Format a single advisory finding as a brief markdown bullet.

    Args:
        finding: AdvisoryFinding to summarize.

    Returns:
        Markdown bullet line for the finding.
    """
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
