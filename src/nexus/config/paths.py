# nexus/config/paths.py
# Authoritative path constants for all NEXUS runtime directories and files.
# Author: Pierre Grothe
# Date: 2026-05-07

"""Centralised path definitions for the ~/.nexus/ directory tree.

All NEXUS code that needs a runtime path imports it from here.
No other module hardcodes a path under ~/.nexus/.
"""

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from nexus.cache import cached

log = logging.getLogger(__name__)

__all__ = ["NexusPaths"]

_DEFAULT_ROOT = Path.home() / ".nexus"


@dataclass(slots=True, frozen=True)
class NexusPaths:
    """All runtime paths NEXUS reads from or writes to.

    Args:
        root: Base directory. Defaults to ~/.nexus/.
    """

    root: Path

    @classmethod
    def default(cls) -> NexusPaths:
        """Create paths rooted at ~/.nexus/.

        Returns:
            NexusPaths with root set to the default location.
        """
        return cls(root=_DEFAULT_ROOT)

    @classmethod
    @cached(ttl=None)
    def from_env(cls) -> NexusPaths:
        """Create paths, honouring NEXUS_CONFIG_PATH env var if set.

        Cached for the lifetime of the process. Tests that monkeypatch
        NEXUS_CONFIG_PATH should call ``nexus.cache.clear_cache(NexusPaths.from_env)``.

        Returns:
            NexusPaths with root derived from environment or default.
        """
        env_path = os.environ.get("NEXUS_CONFIG_PATH")
        if env_path:
            return cls(root=Path(env_path).parent)
        return cls.default()

    @property
    def config_file(self) -> Path:
        """Path to the main config YAML."""
        return self.root / "config.yaml"

    @property
    def templates_dir(self) -> Path:
        """Local template cache populated by nexus sync."""
        return self.root / "templates"

    @property
    def reports_dir(self) -> Path:
        """Generated HTML and JSON reports."""
        return self.root / "reports"

    @property
    def jobs_dir(self) -> Path:
        """Job history: scan results, manifests, rollback scripts."""
        return self.root / "jobs"

    @property
    def logs_dir(self) -> Path:
        """Structured session logs."""
        return self.root / "logs"

    @property
    def cache_dir(self) -> Path:
        """Auto-update lockfile, last-check timestamp, persistent caches."""
        return self.root / "cache"

    @property
    def instances_dir(self) -> Path:
        """Per-instance metadata and snapshot directories.

        Returns:
            Path to the instances root directory under ~/.nexus/.
        """
        return self.root / "instances"

    def instance_dir(self, profile: str) -> Path:
        """Directory for a specific instance profile.

        Args:
            profile: Instance profile name.

        Returns:
            Path to the per-instance directory under instances_dir.
        """
        return self.instances_dir / profile

    def ensure_dirs(self) -> None:
        """Create all runtime directories if they do not exist."""
        for path in (
            self.root,
            self.templates_dir,
            self.reports_dir,
            self.jobs_dir,
            self.logs_dir,
            self.cache_dir,
            self.instances_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)
        log.debug("runtime directories ensured under %s", self.root)
