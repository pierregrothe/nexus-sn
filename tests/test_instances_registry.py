# tests/test_instances_registry.py
# Tests for InstanceRegistry disk operations.
# Author: Pierre Grothe
# Date: 2026-05-08
"""Tests for nexus.instances.registry."""

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from nexus.instances.errors import InstanceNotFoundError
from nexus.plugins.errors import BaselineNotFoundError
from nexus.instances.models import ArtifactRecord, InstanceMeta, InstanceSnapshot
from nexus.instances.registry import InstanceRegistry
from nexus.plugins.models import PluginInfo, PluginInventory


def _meta(profile: str = "dev12345") -> InstanceMeta:
    return InstanceMeta.create(
        profile=profile,
        url=f"https://{profile}.service-now.com",
        username="admin",
        client_id="client-123",
        sn_version="Xanadu",
        sn_build="04-01-2025",
        instance_name=profile,
        token_expires_in=1800,
    )


def _snapshot() -> InstanceSnapshot:
    record = ArtifactRecord(
        sys_id="abc",
        name="Test Skill",
        active=True,
        updated_on=datetime.now(UTC),
        is_custom=True,
    )
    return InstanceSnapshot(
        captured_at=datetime.now(UTC),
        sn_version="Xanadu",
        ai_skills=[record],
    )


def _inventory() -> PluginInventory:
    plugin = PluginInfo(
        plugin_id="com.snc.incident",
        name="Incident Management",
        version="1.0.0",
        state="active",
        source="servicenow",
        product_family="ITSM",
        depends_on=(),
        sys_id="sys-1",
        installed_at=datetime.now(UTC),
    )
    return PluginInventory(
        captured_at=datetime.now(UTC),
        sn_version="Xanadu",
        plugins=(plugin,),
    )


def test_registry_register_creates_meta_json(tmp_path: Path) -> None:
    registry = InstanceRegistry(tmp_path)
    registry.register(_meta())
    assert (tmp_path / "dev12345" / "meta.json").exists()


def test_registry_load_returns_stored_meta(tmp_path: Path) -> None:
    registry = InstanceRegistry(tmp_path)
    meta = _meta()
    registry.register(meta)
    loaded = registry.load("dev12345")
    assert loaded.profile == "dev12345"
    assert loaded.url == meta.url


def test_registry_load_raises_when_profile_not_found(tmp_path: Path) -> None:
    registry = InstanceRegistry(tmp_path)
    with pytest.raises(InstanceNotFoundError):
        registry.load("missing")


def test_registry_save_updates_meta_json(tmp_path: Path) -> None:
    registry = InstanceRegistry(tmp_path)
    meta = _meta()
    registry.register(meta)
    new_expiry = datetime.now(UTC) + timedelta(hours=2)
    updated = meta.model_copy(update={"token_expires_at": new_expiry})
    registry.save(updated)
    loaded = registry.load("dev12345")
    assert abs((loaded.token_expires_at - new_expiry).total_seconds()) < 1


def test_registry_delete_removes_directory(tmp_path: Path) -> None:
    registry = InstanceRegistry(tmp_path)
    registry.register(_meta())
    registry.delete("dev12345")
    assert not (tmp_path / "dev12345").exists()


def test_registry_delete_raises_when_not_found(tmp_path: Path) -> None:
    registry = InstanceRegistry(tmp_path)
    with pytest.raises(InstanceNotFoundError):
        registry.delete("missing")


def test_registry_list_all_returns_all_profiles(tmp_path: Path) -> None:
    registry = InstanceRegistry(tmp_path)
    registry.register(_meta("dev12345"))
    registry.register(_meta("prod99999"))
    profiles = registry.list_all()
    names = {m.profile for m in profiles}
    assert names == {"dev12345", "prod99999"}


def test_registry_list_all_returns_empty_when_no_instances_dir(tmp_path: Path) -> None:
    registry = InstanceRegistry(tmp_path / "instances")
    assert registry.list_all() == []


def test_registry_list_all_returns_profiles_sorted_by_name(tmp_path: Path) -> None:
    registry = InstanceRegistry(tmp_path)
    registry.register(_meta("zzz"))
    registry.register(_meta("aaa"))
    profiles = registry.list_all()
    assert profiles[0].profile == "aaa"
    assert profiles[1].profile == "zzz"


def test_registry_save_snapshot_writes_snapshot_json(tmp_path: Path) -> None:
    registry = InstanceRegistry(tmp_path)
    registry.register(_meta())
    registry.save_snapshot("dev12345", _snapshot())
    assert (tmp_path / "dev12345" / "snapshot.json").exists()


def test_registry_load_snapshot_returns_stored_snapshot(tmp_path: Path) -> None:
    registry = InstanceRegistry(tmp_path)
    registry.register(_meta())
    snap = _snapshot()
    registry.save_snapshot("dev12345", snap)
    loaded = registry.load_snapshot("dev12345")
    assert loaded is not None
    assert len(loaded.ai_skills) == 1
    assert loaded.ai_skills[0].name == "Test Skill"


def test_registry_load_snapshot_returns_none_when_no_snapshot(tmp_path: Path) -> None:
    registry = InstanceRegistry(tmp_path)
    registry.register(_meta())
    assert registry.load_snapshot("dev12345") is None


def test_registry_save_raises_when_not_found(tmp_path: Path) -> None:
    registry = InstanceRegistry(tmp_path)
    with pytest.raises(InstanceNotFoundError):
        registry.save(_meta())


def test_registry_save_snapshot_raises_when_not_found(tmp_path: Path) -> None:
    registry = InstanceRegistry(tmp_path)
    with pytest.raises(InstanceNotFoundError):
        registry.save_snapshot("missing", _snapshot())


def test_registry_list_all_skips_malformed_meta(tmp_path: Path) -> None:
    (tmp_path / "bad").mkdir()
    (tmp_path / "bad" / "meta.json").write_text("not json", encoding="utf-8")
    registry = InstanceRegistry(tmp_path)
    registry.register(_meta("good"))
    profiles = registry.list_all()
    assert len(profiles) == 1
    assert profiles[0].profile == "good"


def test_registry_load_snapshot_raises_when_profile_not_found(tmp_path: Path) -> None:
    registry = InstanceRegistry(tmp_path)
    with pytest.raises(InstanceNotFoundError):
        registry.load_snapshot("nonexistent")


def test_registry_save_snapshot_cleans_tmp_on_oserror(tmp_path: Path) -> None:
    registry = InstanceRegistry(tmp_path)
    registry.register(_meta())
    profile_dir = tmp_path / "dev12345"
    # Create a directory where snapshot.json would be placed so Path.replace raises OSError.
    # POSIX raises IsADirectoryError; Windows raises PermissionError -- both are OSError.
    (profile_dir / "snapshot.json").mkdir()
    with pytest.raises((IsADirectoryError, PermissionError)):
        registry.save_snapshot("dev12345", _snapshot())
    assert not any(p.suffix == ".tmp" for p in profile_dir.iterdir())


def test_load_plugin_inventory_returns_none_when_file_missing(tmp_path: Path) -> None:
    registry = InstanceRegistry(tmp_path)
    registry.register(_meta())
    assert registry.load_plugin_inventory("dev12345") is None


def test_save_and_load_plugin_inventory_round_trips(tmp_path: Path) -> None:
    registry = InstanceRegistry(tmp_path)
    registry.register(_meta())
    inventory = _inventory()
    registry.save_plugin_inventory("dev12345", inventory)
    loaded = registry.load_plugin_inventory("dev12345")
    assert loaded is not None
    assert len(loaded.plugins) == 1
    assert loaded.plugins[0].plugin_id == "com.snc.incident"
    assert loaded.sn_version == "Xanadu"


def test_load_plugin_inventory_raises_when_profile_missing(tmp_path: Path) -> None:
    registry = InstanceRegistry(tmp_path)
    with pytest.raises(InstanceNotFoundError):
        registry.load_plugin_inventory("nonexistent")


def test_load_plugin_baseline_returns_none_when_missing(tmp_path: Path) -> None:
    """A profile dir exists but no baselines/default.json -> None."""
    registry = InstanceRegistry(tmp_path)
    registry.register(_meta("dev12345"))
    assert registry.load_plugin_baseline("dev12345", "default") is None


def test_save_and_load_plugin_baseline_round_trip(tmp_path: Path) -> None:
    """save_plugin_baseline writes the inventory; load_plugin_baseline reads it back."""
    registry = InstanceRegistry(tmp_path)
    registry.register(_meta("dev12345"))
    inv = _inventory()
    registry.save_plugin_baseline("dev12345", "default", inv)
    loaded = registry.load_plugin_baseline("dev12345", "default")
    assert loaded is not None
    assert loaded.plugins[0].plugin_id == "com.snc.incident"


def test_save_creates_baselines_dir_lazily(tmp_path: Path) -> None:
    """baselines/ directory is created on first save."""
    registry = InstanceRegistry(tmp_path)
    registry.register(_meta("dev12345"))
    profile_dir = tmp_path / "dev12345"
    assert not (profile_dir / "baselines").exists()
    registry.save_plugin_baseline("dev12345", "default", _inventory())
    assert (profile_dir / "baselines" / "default.json").exists()


def test_save_plugin_baseline_overwrites_existing(tmp_path: Path) -> None:
    """A second save replaces the first baseline."""
    registry = InstanceRegistry(tmp_path)
    registry.register(_meta("prod"))
    registry.save_plugin_baseline("prod", "default", _inventory())
    second_plugin = PluginInfo(
        plugin_id="com.snc.other",
        name="Other",
        version="2.0.0",
        state="active",
        source="servicenow",
        product_family="ITSM",
        depends_on=(),
        sys_id="sys-other",
        installed_at=None,
    )
    second = PluginInventory(
        captured_at=datetime.now(UTC) + timedelta(days=1),
        sn_version="Xanadu",
        plugins=(second_plugin,),
    )
    registry.save_plugin_baseline("prod", "default", second)
    loaded = registry.load_plugin_baseline("prod", "default")
    assert loaded is not None
    assert len(loaded.plugins) == 1
    assert loaded.plugins[0].plugin_id == "com.snc.other"


def test_load_plugin_baseline_raises_when_profile_missing(tmp_path: Path) -> None:
    """Profile directory does not exist -> InstanceNotFoundError."""
    registry = InstanceRegistry(tmp_path)
    with pytest.raises(InstanceNotFoundError):
        registry.load_plugin_baseline("ghost", "default")


def test_save_plugin_baseline_raises_when_profile_missing(tmp_path: Path) -> None:
    """save with no profile dir -> InstanceNotFoundError."""
    registry = InstanceRegistry(tmp_path)
    inv = _inventory()
    with pytest.raises(InstanceNotFoundError):
        registry.save_plugin_baseline("ghost", "default", inv)


def test_list_plugin_baselines_returns_empty_tuple_when_dir_missing(tmp_path: Path) -> None:
    registry = InstanceRegistry(tmp_path)
    registry.register(_meta("dev12345"))
    assert registry.list_plugin_baselines("dev12345") == ()


def test_list_plugin_baselines_sorts_names(tmp_path: Path) -> None:
    registry = InstanceRegistry(tmp_path)
    registry.register(_meta("dev12345"))
    registry.save_plugin_baseline("dev12345", "zzz", _inventory())
    registry.save_plugin_baseline("dev12345", "aaa", _inventory())
    registry.save_plugin_baseline("dev12345", "mmm", _inventory())
    assert registry.list_plugin_baselines("dev12345") == ("aaa", "mmm", "zzz")


def test_delete_plugin_baseline_removes_file(tmp_path: Path) -> None:
    registry = InstanceRegistry(tmp_path)
    registry.register(_meta("dev12345"))
    registry.save_plugin_baseline("dev12345", "default", _inventory())
    registry.delete_plugin_baseline("dev12345", "default")
    assert registry.load_plugin_baseline("dev12345", "default") is None


def test_delete_plugin_baseline_raises_when_missing(tmp_path: Path) -> None:
    registry = InstanceRegistry(tmp_path)
    registry.register(_meta("dev12345"))
    with pytest.raises(BaselineNotFoundError):
        registry.delete_plugin_baseline("dev12345", "nope")


def test_legacy_baseline_file_logged_and_ignored(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    import logging

    registry = InstanceRegistry(tmp_path)
    registry.register(_meta("dev12345"))
    (tmp_path / "dev12345" / "plugins.baseline.json").write_text("{}", encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger="nexus.instances.registry"):
        assert registry.load_plugin_baseline("dev12345", "default") is None
    assert any("legacy" in r.message.lower() for r in caplog.records)


def test_load_plugin_inventory_with_legacy_shape_returns_none_and_warns(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A plugins.json file with the old record_count field is treated as absent."""
    registry = InstanceRegistry(tmp_path)
    registry.register(_meta("dev"))

    legacy_inventory: dict[str, object] = {
        "captured_at": "2026-05-01T12:00:00+00:00",
        "sn_version": "Xanadu",
        "plugins": [
            {
                "plugin_id": "com.snc.incident",
                "name": "Incident",
                "version": "1.0",
                "state": "active",
                "source": "servicenow",
                "product_family": "ITSM",
                "depends_on": [],
                "sys_id": "sys-1",
                "installed_at": None,
                "record_count": 42,
            }
        ],
    }
    (tmp_path / "dev" / "plugins.json").write_text(json.dumps(legacy_inventory), encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="nexus.instances.registry"):
        result = registry.load_plugin_inventory("dev")

    assert result is None
    assert any("schema outdated" in rec.message for rec in caplog.records)


def test_load_plugin_baseline_with_stale_schema_returns_none_and_warns(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A baselines/default.json file with the old record_count field is treated as absent."""
    registry = InstanceRegistry(tmp_path)
    registry.register(_meta("dev"))
    (tmp_path / "dev" / "baselines").mkdir()

    legacy_baseline: dict[str, object] = {
        "captured_at": "2026-05-01T12:00:00+00:00",
        "sn_version": "Xanadu",
        "plugins": [
            {
                "plugin_id": "com.snc.incident",
                "name": "Incident",
                "version": "1.0",
                "state": "active",
                "source": "servicenow",
                "product_family": "ITSM",
                "depends_on": [],
                "sys_id": "sys-1",
                "installed_at": None,
                "record_count": 0,
            }
        ],
    }
    (tmp_path / "dev" / "baselines" / "default.json").write_text(
        json.dumps(legacy_baseline), encoding="utf-8"
    )

    with caplog.at_level(logging.WARNING, logger="nexus.instances.registry"):
        result = registry.load_plugin_baseline("dev", "default")

    assert result is None
    assert any("schema outdated" in rec.message.lower() for rec in caplog.records)


# ---------------------------------------------------------------------------
# Advisory overrides persistence
# ---------------------------------------------------------------------------

from nexus.plugins.models import AdvisoryType  # noqa: E402
from nexus.plugins.overrides import AdvisoryOverride, AdvisoryOverrideSet  # noqa: E402


def _override_set() -> AdvisoryOverrideSet:
    return AdvisoryOverrideSet(
        overrides=(
            AdvisoryOverride(
                plugin_id="com.x",
                advisory_type=AdvisoryType.CVE,
                details="CVE-2024-1",
                reason="WAF rule in place",
                created_at=datetime(2026, 5, 12, tzinfo=UTC),
            ),
        )
    )


def test_load_advisory_overrides_returns_empty_when_file_missing(tmp_path: Path) -> None:
    registry = InstanceRegistry(tmp_path)
    registry.register(_meta())
    result = registry.load_advisory_overrides("dev12345")
    assert result.overrides == ()


def test_save_and_load_advisory_overrides_round_trips(tmp_path: Path) -> None:
    registry = InstanceRegistry(tmp_path)
    registry.register(_meta())
    expected = _override_set()
    registry.save_advisory_overrides("dev12345", expected)
    loaded = registry.load_advisory_overrides("dev12345")
    assert loaded == expected


def test_load_advisory_overrides_with_legacy_shape_returns_empty_and_warns(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    registry = InstanceRegistry(tmp_path)
    registry.register(_meta())
    bogus = "overrides:\n  - plugin_id: com.x\n    unknown_field: 1\n"
    (tmp_path / "dev12345" / "advisory-overrides.yaml").write_text(bogus, encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger="nexus.instances.registry"):
        result = registry.load_advisory_overrides("dev12345")
    assert result.overrides == ()
    assert any("overrides" in r.message.lower() for r in caplog.records)


def test_load_advisory_overrides_raises_when_profile_missing(tmp_path: Path) -> None:
    registry = InstanceRegistry(tmp_path)
    with pytest.raises(InstanceNotFoundError):
        registry.load_advisory_overrides("nonexistent")
