# tests/test_config.py
# Tests for config layer: NexusPaths, NexusConfig, ConfigManager.
# Author: Pierre Grothe
# Date: 2026-05-07

"""Tests for nexus.config."""

from pathlib import Path

import pytest
import yaml

from nexus.config.manager import ConfigManager
from nexus.config.paths import NexusPaths
from nexus.config.settings import InstanceProfile, NexusConfig


def test_nexus_paths_default_root_is_home_nexus() -> None:
    paths = NexusPaths.default()
    assert paths.root == Path.home() / ".nexus"


def test_nexus_paths_config_file_under_root(nexus_paths: NexusPaths) -> None:
    assert nexus_paths.config_file == nexus_paths.root / "config.yaml"


def test_nexus_paths_ensure_dirs_creates_all_directories(nexus_paths: NexusPaths) -> None:
    nexus_paths.ensure_dirs()
    for path in (
        nexus_paths.root,
        nexus_paths.templates_dir,
        nexus_paths.reports_dir,
        nexus_paths.jobs_dir,
        nexus_paths.logs_dir,
    ):
        assert path.is_dir()


def test_nexus_config_default_has_empty_instances() -> None:
    config = NexusConfig.default()
    assert config.instances.default == ""
    assert config.instances.profiles == {}


def test_nexus_config_default_auto_probe_enabled() -> None:
    config = NexusConfig.default()
    assert config.capabilities.auto_probe is True


def test_nexus_config_is_frozen() -> None:
    config = NexusConfig.default()
    with pytest.raises(Exception):
        config.preferences = config.preferences  # type: ignore[misc]


def test_instance_profile_stores_url_and_username() -> None:
    profile = InstanceProfile(url="dev12345.service-now.com", username="admin")
    assert profile.url == "dev12345.service-now.com"
    assert profile.username == "admin"


def test_config_manager_load_returns_defaults_when_no_file(nexus_paths: NexusPaths) -> None:
    manager = ConfigManager(nexus_paths)
    config = manager.load()
    assert isinstance(config, NexusConfig)
    assert config.version == "1.0"


def test_config_manager_exists_returns_false_when_no_file(nexus_paths: NexusPaths) -> None:
    manager = ConfigManager(nexus_paths)
    assert manager.exists() is False


def test_config_manager_save_and_load_roundtrip(nexus_paths: NexusPaths) -> None:
    manager = ConfigManager(nexus_paths)
    original = NexusConfig.default()
    manager.save(original)

    assert manager.exists()
    loaded = manager.load()
    assert loaded.version == original.version
    assert loaded.capabilities.auto_probe == original.capabilities.auto_probe


def test_config_manager_save_writes_valid_yaml(nexus_paths: NexusPaths) -> None:
    manager = ConfigManager(nexus_paths)
    manager.save(NexusConfig.default())

    raw = yaml.safe_load(nexus_paths.config_file.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    assert "version" in raw


def test_config_manager_from_env_uses_default_when_env_not_set(
    nexus_paths: NexusPaths, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Verifies that without NEXUS_CONFIG_PATH, from_env() uses home
    monkeypatch.delenv("NEXUS_CONFIG_PATH", raising=False)
    paths = NexusPaths.from_env()
    assert paths.root == Path.home() / ".nexus"
