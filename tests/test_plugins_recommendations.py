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
    assert "candidates" in text.lower()


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
