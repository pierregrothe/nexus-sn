# tests/test_plugins_dependencies.py
# Tests for fetch_dependencies pure helper.
# Author: Pierre Grothe
# Date: 2026-05-14

"""Tests for the dependency cascade pre-flight helper."""

import pytest

from nexus.plugins.dependencies import DependencyEntry, fetch_dependencies
from tests.fakes.fake_sn_client import FakeServiceNowClient

__all__: list[str] = []


@pytest.mark.asyncio
async def test_fetch_dependencies_returns_typed_entries() -> None:
    client = FakeServiceNowClient()
    client.set_dependencies(
        "sn_si",
        [
            {
                "Id": "Common A",
                "orig_string": "sn_a:1.0",
                "type": "Application",
                "minVersion": "1.0",
                "source_app_id": "id1",
                "installed": True,
                "hide_on_ui": False,
                "status": "Will be Updated",
                "status_value": "will_be_updated",
                "active": True,
                "order": 1,
                "link": "",
                "has_license": False,
                "is_allowed_install": True,
            },
        ],
    )
    deps = await fetch_dependencies(client, "sn_si", "13.9.23")
    assert len(deps) == 1
    assert isinstance(deps[0], DependencyEntry)
    assert deps[0].id == "Common A"
    assert deps[0].status_value == "will_be_updated"


@pytest.mark.asyncio
async def test_fetch_dependencies_empty_when_no_canned() -> None:
    client = FakeServiceNowClient()
    deps = await fetch_dependencies(client, "com.notseed", None)
    assert deps == ()


def test_dependencyentry_from_sn_null_id_does_not_render_as_string_none() -> None:
    """Regression: SN returning ``"Id": null`` must not surface as ``"None"``.

    The cascade panel was rendering ``Plugin: None`` when SN replied with a
    null Id; safe-string coercion now maps null to ``""`` so the panel can
    filter the row out instead of displaying a literal.
    """
    entry = DependencyEntry.from_sn(
        {
            "Id": None,
            "orig_string": None,
            "type": "Plugin",
            "minVersion": None,
            "source_app_id": None,
            "installed": True,
            "active": True,
            "hide_on_ui": False,
            "status": None,
            "status_value": None,
            "order": 0,
            "link": None,
            "has_license": False,
            "is_allowed_install": True,
        }
    )
    assert entry.id == ""
    assert entry.orig_string == ""
    assert entry.min_version == ""
    assert entry.status == ""
    assert entry.status_value == ""
    assert entry.link == ""
    assert entry.source_app_id == ""


def test_dependencyentry_from_sn_preserves_real_strings() -> None:
    """Real (non-null) string fields survive the safe-string coercion."""
    entry = DependencyEntry.from_sn(
        {
            "Id": "Performance Analytics",
            "orig_string": "com.snc.pa:8.0.0",
            "type": "Application",
            "minVersion": "8.0.0",
            "source_app_id": "abc123",
            "installed": True,
            "active": True,
            "hide_on_ui": False,
            "status": "Will be Updated",
            "status_value": "will_be_updated",
            "order": 3,
            "link": "/nav/foo",
            "has_license": True,
            "is_allowed_install": True,
        }
    )
    assert entry.id == "Performance Analytics"
    assert entry.min_version == "8.0.0"
    assert entry.status == "Will be Updated"
    assert entry.link == "/nav/foo"
