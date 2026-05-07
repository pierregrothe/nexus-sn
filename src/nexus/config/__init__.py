# nexus/config/__init__.py
# Configuration layer public exports.
# Author: Pierre Grothe
# Date: 2026-05-07

"""Configuration management for NEXUS."""

from nexus.config.manager import ConfigManager
from nexus.config.paths import NexusPaths
from nexus.config.settings import InstanceProfile, NexusConfig

__all__ = [
    "ConfigManager",
    "NexusPaths",
    "InstanceProfile",
    "NexusConfig",
]
