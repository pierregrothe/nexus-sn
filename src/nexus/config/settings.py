# nexus/config/settings.py
# Pydantic models for ~/.nexus/config.yaml. No secrets stored here.
# Author: Pierre Grothe
# Date: 2026-05-07

"""Typed configuration models for NEXUS.

All secrets are stored in the OS keychain. This file contains only
non-sensitive configuration: URLs, usernames, preferences, and flags.
"""

import logging
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

log = logging.getLogger(__name__)

__all__ = [
    "InstanceProfile",
    "InstancesConfig",
    "CapabilitiesConfig",
    "PreferencesConfig",
    "AuthConfig",
    "NexusConfig",
]

_CONFIG_VERSION = "1.0"


class InstanceProfile(BaseModel):
    """A single ServiceNow instance connection profile.

    Attributes:
        url: Full instance URL, e.g. dev12345.service-now.com.
        username: Login username. Password is stored in the OS keychain.
    """

    model_config = ConfigDict(frozen=True)

    url: str
    username: str


class InstancesConfig(BaseModel):
    """ServiceNow instance registry.

    Attributes:
        default: Name of the default profile.
        profiles: Map of profile name to connection details.
    """

    model_config = ConfigDict(frozen=True)

    default: str = ""
    profiles: dict[str, InstanceProfile] = Field(default_factory=dict)


class CapabilitiesConfig(BaseModel):
    """MCP capability probe settings.

    Attributes:
        auto_probe: Probe MCP servers at startup if True.
        probe_timeout_seconds: Seconds before marking a server unavailable.
        disabled_servers: Server names to skip regardless of availability.
    """

    model_config = ConfigDict(frozen=True)

    auto_probe: bool = True
    probe_timeout_seconds: Annotated[int, Field(ge=1, le=30)] = 5
    disabled_servers: list[str] = Field(default_factory=list)


class PreferencesConfig(BaseModel):
    """User preferences.

    Attributes:
        output_format: CLI output style.
        github_repo: Template registry repository slug.
        github_branch: Branch to sync templates from.
    """

    model_config = ConfigDict(frozen=True)

    output_format: str = "rich"
    github_repo: str = ""
    github_branch: str = "main"


class AuthConfig(BaseModel):
    """Authentication references (no secrets).

    Attributes:
        claude_org: Org slug used as the keychain service name for the API key.
    """

    model_config = ConfigDict(frozen=True)

    claude_org: str = "servicenow"


class NexusConfig(BaseModel):
    """Root configuration model for ~/.nexus/config.yaml.

    Attributes:
        version: Config format version for future migrations.
        auth: Claude authentication references.
        instances: ServiceNow instance profiles.
        capabilities: MCP probe settings.
        preferences: User preferences.
    """

    model_config = ConfigDict(frozen=True)

    version: str = _CONFIG_VERSION
    auth: AuthConfig = Field(default_factory=AuthConfig)
    instances: InstancesConfig = Field(default_factory=InstancesConfig)
    capabilities: CapabilitiesConfig = Field(default_factory=CapabilitiesConfig)
    preferences: PreferencesConfig = Field(default_factory=PreferencesConfig)

    @classmethod
    def default(cls) -> "NexusConfig":
        """Create a default configuration.

        Returns:
            NexusConfig with all fields at their default values.
        """
        return cls()
