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
