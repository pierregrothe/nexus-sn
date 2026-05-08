# nexus/config/manager.py
# Reads, writes, and migrates the ~/.nexus/config.yaml file.
# Author: Pierre Grothe
# Date: 2026-05-07

"""ConfigManager: persistent configuration I/O and version migration."""

import logging
from pathlib import Path

import yaml

from nexus.cache import cached
from nexus.config.paths import NexusPaths
from nexus.config.settings import NexusConfig

log = logging.getLogger(__name__)

__all__ = ["ConfigManager"]


class ConfigManager:
    """Read, write, and migrate the NEXUS config file.

    Args:
        paths: Runtime path provider. Defaults to NexusPaths.from_env().
    """

    def __init__(self, paths: NexusPaths | None = None) -> None:
        """Initialize with optional config file path."""
        self._paths = paths or NexusPaths.from_env()

    @cached(ttl=None)
    def load(self) -> NexusConfig:
        """Load config from disk, returning defaults if the file does not exist.

        Cached per-instance for the lifetime of the process. Call
        ``nexus.cache.clear_cache(self)`` after writing config out-of-band.

        Returns:
            Validated NexusConfig instance.
        """
        config_file = self._paths.config_file
        if not config_file.exists():
            log.info("config file not found at %s -- using defaults", config_file)
            return NexusConfig.default()

        raw: dict[str, object] = yaml.safe_load(config_file.read_text(encoding="utf-8")) or {}
        config = NexusConfig.model_validate(raw)
        log.debug("loaded config version=%s from %s", config.version, config_file)
        return config

    def save(self, config: NexusConfig) -> None:
        """Write config to disk.

        Args:
            config: Configuration to persist.
        """
        self._paths.ensure_dirs()
        config_file = self._paths.config_file
        data = config.model_dump()
        config_file.write_text(yaml.dump(data, default_flow_style=False), encoding="utf-8")
        log.info("config saved to %s", config_file)

    def exists(self) -> bool:
        """Return True if a config file exists on disk.

        Returns:
            True when ~/.nexus/config.yaml (or override) is present.
        """
        return self._paths.config_file.exists()

    @staticmethod
    def config_path_from(root: Path) -> Path:
        """Return the config file path for a given root directory.

        Args:
            root: Base directory, typically ~/.nexus.

        Returns:
            Path to the config YAML file.
        """
        return root / "config.yaml"
