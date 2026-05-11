# tests/test_plugins_diff.py
# Tests for cross-instance plugin diff and promote-plan projection.
# Author: Pierre Grothe
# Date: 2026-05-11
"""Tests for PluginDiff / PromotionPlan models and pure functions."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from nexus.plugins.diff import (
    PluginDiff,
    PluginDiffEntry,
    PromoteAction,
    PromotionPlan,
    compute_diff,
    project_to_promote_plan,
)
from nexus.plugins.models import PluginInfo, PluginInventory

__all__: list[str] = []


def _entry(**overrides: object) -> PluginDiffEntry:
    defaults: dict[str, object] = {
        "plugin_id": "com.snc.incident",
        "name": "Incident Management",
        "product_family": "ITSM",
        "status": "version_mismatch",
        "a_version": "1.2.0",
        "b_version": "1.0.0",
        "a_state": "active",
        "b_state": "active",
    }
    defaults.update(overrides)
    return PluginDiffEntry.model_validate(defaults)


def _action(**overrides: object) -> PromoteAction:
    defaults: dict[str, object] = {
        "action": "upgrade",
        "plugin_id": "com.snc.incident",
        "name": "Incident Management",
        "product_family": "ITSM",
        "target_version": "1.2.0",
        "current_version": "1.0.0",
    }
    defaults.update(overrides)
    return PromoteAction.model_validate(defaults)


def test_plugin_diff_entry_construction_with_required_fields() -> None:
    entry = _entry()
    assert entry.plugin_id == "com.snc.incident"
    assert entry.status == "version_mismatch"


def test_plugin_diff_entry_is_frozen() -> None:
    entry = _entry()
    with pytest.raises(ValidationError):
        entry.plugin_id = "renamed"


def test_plugin_diff_entry_rejects_unknown_status() -> None:
    with pytest.raises(ValidationError):
        _entry(status="weird")


def test_plugin_diff_entry_accepts_none_for_a_fields_when_only_in_b() -> None:
    entry = _entry(status="only_in_b", a_version=None, a_state=None)
    assert entry.a_version is None
    assert entry.a_state is None


def test_plugin_diff_holds_profiles_and_captured_at_pair() -> None:
    now = datetime.now(UTC)
    diff = PluginDiff(
        profile_a="prod",
        profile_b="dev",
        captured_at_a=now,
        captured_at_b=now,
        entries=(_entry(),),
    )
    assert diff.profile_a == "prod"
    assert diff.profile_b == "dev"
    assert len(diff.entries) == 1


def test_plugin_diff_round_trips_through_json() -> None:
    now = datetime.now(UTC)
    diff = PluginDiff(
        profile_a="prod",
        profile_b="dev",
        captured_at_a=now,
        captured_at_b=now,
        entries=(_entry(),),
    )
    re = PluginDiff.model_validate_json(diff.model_dump_json())
    assert re == diff


def test_promote_action_construction_with_required_fields() -> None:
    action = _action()
    assert action.action == "upgrade"
    assert action.current_version == "1.0.0"


def test_promote_action_is_frozen() -> None:
    action = _action()
    with pytest.raises(ValidationError):
        action.plugin_id = "renamed"


def test_promote_action_rejects_unknown_action() -> None:
    with pytest.raises(ValidationError):
        _action(action="delete")


def test_promote_action_install_has_no_current_version() -> None:
    install = _action(action="install", current_version=None)
    assert install.current_version is None


def test_promotion_plan_holds_profiles_and_actions() -> None:
    plan = PromotionPlan(
        source_profile="prod",
        target_profile="dev",
        actions=(_action(),),
    )
    assert plan.source_profile == "prod"
    assert plan.actions[0].action == "upgrade"


def test_promotion_plan_round_trips_through_json() -> None:
    plan = PromotionPlan(
        source_profile="prod",
        target_profile="dev",
        actions=(_action(),),
    )
    re = PromotionPlan.model_validate_json(plan.model_dump_json())
    assert re == plan


def _info(
    plugin_id: str,
    *,
    version: str = "1.0.0",
    state: str = "active",
    product_family: str = "ITSM",
    name: str = "",
) -> PluginInfo:
    return PluginInfo.model_validate(
        {
            "plugin_id": plugin_id,
            "name": name or plugin_id,
            "version": version,
            "state": state,
            "source": "servicenow",
            "product_family": product_family,
            "depends_on": (),
            "sys_id": f"sys-{plugin_id}",
            "installed_at": None,
        }
    )


def _inventory(*plugins: PluginInfo) -> PluginInventory:
    return PluginInventory(
        captured_at=datetime.now(UTC),
        sn_version="Xanadu",
        plugins=plugins,
    )


def test_compute_diff_returns_empty_entries_for_identical_inventories() -> None:
    inv = _inventory(_info("com.snc.incident"))
    diff = compute_diff(inv, inv, profile_a="prod", profile_b="dev")
    assert diff.entries == ()
    assert diff.profile_a == "prod"
    assert diff.profile_b == "dev"


def test_compute_diff_reports_only_in_a_when_a_has_extra_plugin() -> None:
    a = _inventory(_info("com.snc.incident"), _info("com.snc.problem"))
    b = _inventory(_info("com.snc.incident"))
    diff = compute_diff(a, b, profile_a="prod", profile_b="dev")
    assert len(diff.entries) == 1
    only = diff.entries[0]
    assert only.plugin_id == "com.snc.problem"
    assert only.status == "only_in_a"
    assert only.a_version == "1.0.0"
    assert only.b_version is None
    assert only.a_state == "active"
    assert only.b_state is None


def test_compute_diff_reports_only_in_b_when_b_has_extra_plugin() -> None:
    a = _inventory(_info("com.snc.incident"))
    b = _inventory(_info("com.snc.incident"), _info("com.snc.problem"))
    diff = compute_diff(a, b, profile_a="prod", profile_b="dev")
    only = next(e for e in diff.entries if e.plugin_id == "com.snc.problem")
    assert only.status == "only_in_b"
    assert only.a_version is None
    assert only.b_version == "1.0.0"


def test_compute_diff_reports_version_mismatch() -> None:
    a = _inventory(_info("com.snc.incident", version="1.2.0"))
    b = _inventory(_info("com.snc.incident", version="1.0.0"))
    diff = compute_diff(a, b, profile_a="prod", profile_b="dev")
    assert len(diff.entries) == 1
    e = diff.entries[0]
    assert e.status == "version_mismatch"
    assert e.a_version == "1.2.0"
    assert e.b_version == "1.0.0"
    assert e.a_state == "active"
    assert e.b_state == "active"


def test_compute_diff_reports_state_mismatch() -> None:
    a = _inventory(_info("com.snc.incident", state="active"))
    b = _inventory(_info("com.snc.incident", state="inactive"))
    diff = compute_diff(a, b, profile_a="prod", profile_b="dev")
    assert len(diff.entries) == 1
    e = diff.entries[0]
    assert e.status == "state_mismatch"
    assert e.a_state == "active"
    assert e.b_state == "inactive"


def test_compute_diff_sorts_entries_by_product_then_plugin_id() -> None:
    a = _inventory(
        _info("com.snc.discovery", product_family="ITOM"),
        _info("com.snc.problem", product_family="ITSM"),
        _info("com.snc.incident", product_family="ITSM"),
    )
    b = _inventory()
    diff = compute_diff(a, b, profile_a="prod", profile_b="dev")
    ids = [e.plugin_id for e in diff.entries]
    assert ids == ["com.snc.discovery", "com.snc.incident", "com.snc.problem"]


def test_project_to_promote_plan_includes_install_for_only_in_a() -> None:
    diff = compute_diff(
        _inventory(_info("com.snc.problem")),
        _inventory(),
        profile_a="prod",
        profile_b="dev",
    )
    plan = project_to_promote_plan(diff)
    assert plan.source_profile == "prod"
    assert plan.target_profile == "dev"
    assert len(plan.actions) == 1
    a = plan.actions[0]
    assert a.action == "install"
    assert a.plugin_id == "com.snc.problem"
    assert a.target_version == "1.0.0"
    assert a.current_version is None


def test_project_to_promote_plan_includes_activate_for_active_on_a_inactive_on_b() -> None:
    diff = compute_diff(
        _inventory(_info("com.snc.problem", state="active")),
        _inventory(_info("com.snc.problem", state="inactive")),
        profile_a="prod",
        profile_b="dev",
    )
    plan = project_to_promote_plan(diff)
    assert len(plan.actions) == 1
    assert plan.actions[0].action == "activate"


def test_project_to_promote_plan_skips_deactivate_direction() -> None:
    diff = compute_diff(
        _inventory(_info("com.snc.problem", state="inactive")),
        _inventory(_info("com.snc.problem", state="active")),
        profile_a="prod",
        profile_b="dev",
    )
    plan = project_to_promote_plan(diff)
    assert plan.actions == ()


def test_project_to_promote_plan_includes_upgrade_when_a_version_newer() -> None:
    diff = compute_diff(
        _inventory(_info("com.snc.incident", version="2.0.0")),
        _inventory(_info("com.snc.incident", version="1.0.0")),
        profile_a="prod",
        profile_b="dev",
    )
    plan = project_to_promote_plan(diff)
    assert len(plan.actions) == 1
    a = plan.actions[0]
    assert a.action == "upgrade"
    assert a.target_version == "2.0.0"
    assert a.current_version == "1.0.0"


def test_project_to_promote_plan_skips_downgrade_when_a_version_older() -> None:
    diff = compute_diff(
        _inventory(_info("com.snc.incident", version="1.0.0")),
        _inventory(_info("com.snc.incident", version="2.0.0")),
        profile_a="prod",
        profile_b="dev",
    )
    plan = project_to_promote_plan(diff)
    assert plan.actions == ()


def test_project_to_promote_plan_skips_only_in_b() -> None:
    diff = compute_diff(
        _inventory(),
        _inventory(_info("com.snc.problem")),
        profile_a="prod",
        profile_b="dev",
    )
    plan = project_to_promote_plan(diff)
    assert plan.actions == ()


def test_project_to_promote_plan_sorts_install_then_activate_then_upgrade() -> None:
    diff = compute_diff(
        _inventory(
            _info("com.snc.aaa"),  # only_in_a -> install
            _info("com.snc.bbb", version="2.0.0"),  # upgrade
            _info("com.snc.ccc", state="active"),  # activate
        ),
        _inventory(
            _info("com.snc.bbb", version="1.0.0"),
            _info("com.snc.ccc", state="inactive"),
        ),
        profile_a="prod",
        profile_b="dev",
    )
    plan = project_to_promote_plan(diff)
    actions = [a.action for a in plan.actions]
    assert actions == ["install", "activate", "upgrade"]


def test_project_to_promote_plan_handles_unparseable_versions_safely() -> None:
    """Unparseable versions yield a diff entry but no upgrade action."""
    diff = compute_diff(
        _inventory(_info("com.snc.incident", version="rolling-feature-x")),
        _inventory(_info("com.snc.incident", version="rolling-feature-y")),
        profile_a="prod",
        profile_b="dev",
    )
    plan = project_to_promote_plan(diff)
    assert plan.actions == ()
