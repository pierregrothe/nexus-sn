# src/nexus/instances/models.py
# Pydantic models for per-instance metadata and snapshots.
# Author: Pierre Grothe
# Date: 2026-05-08
"""InstanceMeta, InstanceSnapshot, ArtifactRecord, SnapshotCounts."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

__all__ = ["ArtifactRecord", "InstanceMeta", "InstanceSnapshot", "SnapshotCounts"]

_FROZEN = ConfigDict(frozen=True, strict=True, extra="forbid")


class SnapshotCounts(BaseModel):
    """Artifact counts stored in meta.json for quick display."""

    model_config = _FROZEN

    ai_skills: Annotated[int, Field(ge=0)] = 0
    flows: Annotated[int, Field(ge=0)] = 0
    business_rules: Annotated[int, Field(ge=0)] = 0
    script_includes: Annotated[int, Field(ge=0)] = 0


class InstanceMeta(BaseModel):
    """Static metadata and OAuth display fields for a registered SN instance."""

    model_config = _FROZEN

    profile: str
    url: str
    username: str
    client_id: str
    sn_version: str
    sn_build: str
    instance_name: str
    registered_at: datetime
    last_connected_at: datetime
    token_expires_at: datetime
    snapshot_counts: SnapshotCounts = Field(default_factory=SnapshotCounts)

    @field_validator("registered_at", "last_connected_at", "token_expires_at", mode="before")
    @classmethod
    def require_utc(cls, v: object) -> object:
        """Parse ISO strings and reject naive datetimes.

        Strict mode disables string->datetime coercion, so we handle it here.

        Args:
            v: Field value to validate.

        Returns:
            A timezone-aware datetime.

        Raises:
            ValueError: If v is a naive datetime or an unparseable string.
        """
        if isinstance(v, str):
            v = datetime.fromisoformat(v)
        if isinstance(v, datetime) and (v.tzinfo is None or v.utcoffset() != timedelta(0)):
            raise ValueError("datetime must be UTC (tzinfo required, offset must be +00:00)")
        return v

    @classmethod
    def create(
        cls,
        *,
        profile: str,
        url: str,
        username: str,
        client_id: str,
        sn_version: str,
        sn_build: str,
        instance_name: str,
        token_expires_in: int,
    ) -> InstanceMeta:
        """Create a fresh InstanceMeta at registration time.

        Args:
            profile: Profile name (e.g. 'dev12345').
            url: Full instance URL including scheme.
            username: ServiceNow login username.
            client_id: OAuth application client_id (not a secret).
            sn_version: SN version string (e.g. 'Xanadu').
            sn_build: SN build string.
            instance_name: SN instance name.
            token_expires_in: Seconds until the access token expires.

        Returns:
            InstanceMeta with registered_at and last_connected_at set to now.
        """
        now = datetime.now(UTC)
        return cls(
            profile=profile,
            url=url,
            username=username,
            client_id=client_id,
            sn_version=sn_version,
            sn_build=sn_build,
            instance_name=instance_name,
            registered_at=now,
            last_connected_at=now,
            token_expires_at=now + timedelta(seconds=token_expires_in),
        )


class ArtifactRecord(BaseModel):
    """A single artifact entry in the instance snapshot."""

    model_config = _FROZEN

    sys_id: str
    name: str
    active: bool
    updated_on: datetime
    is_custom: bool
    extra: dict[str, str | bool | int] = Field(default_factory=dict)

    @field_validator("updated_on", mode="before")
    @classmethod
    def require_utc(cls, v: object) -> object:
        """Parse ISO strings and reject naive datetimes.

        Args:
            v: Field value to validate.

        Returns:
            A timezone-aware datetime.

        Raises:
            ValueError: If v is a naive datetime or an unparseable string.
        """
        if isinstance(v, str):
            v = datetime.fromisoformat(v)
        if isinstance(v, datetime) and (v.tzinfo is None or v.utcoffset() != timedelta(0)):
            raise ValueError("datetime must be UTC (tzinfo required, offset must be +00:00)")
        return v


class InstanceSnapshot(BaseModel):
    """Full artifact inventory captured by InstanceScanner."""

    model_config = _FROZEN

    captured_at: datetime
    sn_version: str
    ai_skills: list[ArtifactRecord] = Field(default_factory=lambda: [])
    flows: list[ArtifactRecord] = Field(default_factory=lambda: [])
    business_rules: list[ArtifactRecord] = Field(default_factory=lambda: [])
    script_includes: list[ArtifactRecord] = Field(default_factory=lambda: [])

    @field_validator("captured_at", mode="before")
    @classmethod
    def require_utc(cls, v: object) -> object:
        """Parse ISO strings and reject naive datetimes.

        Args:
            v: Field value to validate.

        Returns:
            A timezone-aware datetime.

        Raises:
            ValueError: If v is a naive datetime or an unparseable string.
        """
        if isinstance(v, str):
            v = datetime.fromisoformat(v)
        if isinstance(v, datetime) and (v.tzinfo is None or v.utcoffset() != timedelta(0)):
            raise ValueError("datetime must be UTC (tzinfo required, offset must be +00:00)")
        return v

    @property
    def counts(self) -> SnapshotCounts:
        """Return artifact counts for storing in meta.json.

        Returns:
            SnapshotCounts derived from this snapshot's list lengths.
        """
        return SnapshotCounts(
            ai_skills=len(self.ai_skills),
            flows=len(self.flows),
            business_rules=len(self.business_rules),
            script_includes=len(self.script_includes),
        )
