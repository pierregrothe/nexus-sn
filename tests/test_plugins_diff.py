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
)

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
