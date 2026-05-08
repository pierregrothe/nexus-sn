# tests/test_config.py
# Tests for config layer: NexusPaths, NexusConfig, ConfigManager.
# Author: Pierre Grothe
# Date: 2026-05-07

"""Tests for nexus.config."""

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from nexus.cache import clear_cache
from nexus.config.manager import ConfigManager
from nexus.config.paths import NexusPaths
from nexus.config.settings import AuthConfig, InstanceProfile, NexusConfig


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
    with pytest.raises(ValidationError):
        setattr(config, "auto_probe", False)


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


def test_config_manager_load_caches_after_first_call(nexus_paths: NexusPaths) -> None:
    """load() should serve the cached NexusConfig on subsequent calls."""
    manager = ConfigManager(nexus_paths)
    initial = NexusConfig.default().model_copy(update={"auth": AuthConfig(claude_org="initial")})
    manager.save(initial)

    first = manager.load()
    assert first.auth.claude_org == "initial"

    # Mutate the file directly. A non-cached load would see "changed";
    # the cached load returns the originally-loaded value.
    nexus_paths.config_file.write_text(
        "version: '1.0'\nauth:\n  claude_org: changed\n", encoding="utf-8"
    )
    second = manager.load()
    assert second.auth.claude_org == "initial"
    assert first == second

    clear_cache(manager)
    third = manager.load()
    assert third.auth.claude_org == "changed"
