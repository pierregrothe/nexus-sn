# tests/test_instances_registry.py
# Tests for InstanceRegistry disk operations.
# Author: Pierre Grothe
# Date: 2026-05-08
"""Tests for nexus.instances.registry."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from nexus.instances.errors import InstanceNotFoundError
from nexus.instances.models import ArtifactRecord, InstanceMeta, InstanceSnapshot
from nexus.instances.registry import InstanceRegistry


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
