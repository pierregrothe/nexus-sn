# src/nexus/templates/apply.py
# ApplyEngine -- end-to-end template apply orchestrator.
# Author: Pierre Grothe
# Date: 2026-05-19

"""ApplyEngine composes load -> resolve scope -> render -> push update set.

Public entry point is `ApplyEngine.apply(template_path)`. The engine is
purely async; the CLI orchestrator (Story 06) drives it with
`asyncio.run(...)`.

Provenance: ApplyEngine pre-creates the sys_update_set with a NEXUS
marker name and structured description metadata. UpdateSetWriter's
`_get_or_create_update_set` finds it by name and reuses it for the
actual record injections. After push, the result is appended to a local
`apply.jsonl` under `paths.jobs_dir / <update_set_sys_id>/`.

Failure model: when UpdateSetWriter raises UpdateSetError for one
record, ApplyEngine classifies that specific record as FAILED with the
error message; every other record retains REQUESTED status. WARNED tier
is deferred.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from nexus.assessment.context import ApplyResult
from nexus.capture.errors import UpdateSetError
from nexus.capture.models import CaptureResult, ConfigRecord
from nexus.capture.update_set import UpdateSetWriter
from nexus.capture.xml_builder import UpdateSetXmlBuilder
from nexus.config.paths import NexusPaths
from nexus.connectors.servicenow.protocol import ServiceNowClientProtocol
from nexus.templates.document import load_template_document
from nexus.templates.errors import ScopeNotFoundError
from nexus.templates.renderer import render_to_records
from nexus.templates.results import AppliedAction, AppliedRecord

__all__ = ["ApplyEngine", "Clock"]

log = logging.getLogger(__name__)

type Clock = Callable[[], datetime]

_GLOBAL_SCOPE_SYS_ID = "global"


@dataclass(slots=True, frozen=True)
class ApplyEngine:
    """End-to-end template apply orchestrator.

    Attributes:
        sn_client: ServiceNowClientProtocol for the target instance.
        paths: NexusPaths -- used for the local apply.jsonl write.
        clock: Callable returning a UTC datetime; injectable for tests.
        instance_id: Profile name of the target instance.
        nexus_version: NEXUS package version (carried in provenance metadata).
        git_sha: Source git sha (carried in provenance metadata; may be "unknown").
    """

    sn_client: ServiceNowClientProtocol
    paths: NexusPaths
    clock: Clock
    instance_id: str
    nexus_version: str
    git_sha: str

    async def apply(self, template_path: Path) -> ApplyResult:
        """Run the full apply lifecycle for one template.

        Args:
            template_path: Path to the template's `template.yaml`.

        Returns:
            ApplyResult describing the update set and per-record outcomes.

        Raises:
            TemplateLoadError: The template YAML could not be parsed.
            ScopeNotFoundError: The template's target_scope slug did not
                resolve to a sys_scope record.
        """
        started = self.clock()
        document = load_template_document(template_path)
        scope_sys_id = await self._resolve_scope(document.target_scope)
        records = render_to_records(document, scope_sys_id, started)

        update_set_name = self._build_update_set_name(document.id, started)
        update_set_sys_id = await self._create_update_set(
            update_set_name, document.id, document.version, started
        )

        applied = await self._push_records(records, update_set_name, update_set_sys_id)
        completed = self.clock()

        result = ApplyResult(
            update_set_sys_id=update_set_sys_id,
            update_set_name=update_set_name,
            template_id=document.id,
            template_version=document.version,
            target_scope_sys_id=scope_sys_id,
            applied_records=applied,
            instance_id=self.instance_id,
            started_at=started,
            completed_at=completed,
        )
        self._write_apply_log(result)
        return result

    async def _resolve_scope(self, slug: str) -> str:
        """Resolve a target_scope slug to a sys_scope sys_id."""
        if slug == "global":
            return _GLOBAL_SCOPE_SYS_ID
        rows = await self.sn_client.query_table("sys_scope", query=f"scope={slug}", limit=1)
        if not rows:
            raise ScopeNotFoundError(slug)
        sys_id = rows[0].get("sys_id")
        if not isinstance(sys_id, str) or not sys_id:
            raise ScopeNotFoundError(slug)
        return sys_id

    def _build_update_set_name(self, template_id: str, started: datetime) -> str:
        """Construct the NEXUS-apply-<template>-<timestamp> marker name."""
        timestamp = started.strftime("%Y%m%dT%H%M%SZ")
        return f"NEXUS-apply-{template_id}-{timestamp}"

    async def _create_update_set(
        self,
        name: str,
        template_id: str,
        template_version: str,
        started: datetime,
    ) -> str:
        """Create the sys_update_set with provenance metadata before push."""
        metadata = {
            "nexus": {
                "template_id": template_id,
                "template_version": template_version,
                "nexus_version": self.nexus_version,
                "git_sha": self.git_sha,
                "applied_at": started.isoformat(),
            }
        }
        created = await self.sn_client.create_record(
            "sys_update_set",
            data={
                "name": name,
                "description": json.dumps(metadata, sort_keys=True),
                "state": "in progress",
            },
        )
        sys_id = created.get("sys_id")
        if not isinstance(sys_id, str) or not sys_id:
            raise RuntimeError(f"sys_update_set create returned no sys_id; response={created!r}")
        log.info("created update set %r (%s)", name, sys_id)
        return sys_id

    async def _push_records(
        self,
        records: tuple[ConfigRecord, ...],
        update_set_name: str,
        update_set_sys_id: str,
    ) -> tuple[AppliedRecord, ...]:
        """Push records via UpdateSetWriter; classify per-record outcomes."""
        del update_set_sys_id  # ApplyEngine pre-created the update set by name
        writer = UpdateSetWriter(self.sn_client, UpdateSetXmlBuilder())
        wrapped = CaptureResult(
            instance_id=self.instance_id,
            captured_at=self.clock(),
            scope_ids=("template-apply",),
            table_group="template-apply",
            records=records,
        )
        try:
            await writer.push(wrapped, self.instance_id, update_set_name)
        except UpdateSetError as exc:
            return tuple(_classify_failure(record, exc) for record in records)
        return tuple(
            AppliedRecord(
                table=record.table,
                name=_record_name(record),
                requested_sys_id=record.sys_id,
                action=AppliedAction.REQUESTED,
                error_message=None,
            )
            for record in records
        )

    def _write_apply_log(self, result: ApplyResult) -> None:
        """Append the ApplyResult JSON to the local apply.jsonl."""
        job_dir = self.paths.jobs_dir / result.update_set_sys_id
        job_dir.mkdir(parents=True, exist_ok=True)
        path = job_dir / "apply.jsonl"
        line = json.dumps(result.model_dump(mode="json"), sort_keys=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")


def _classify_failure(record: ConfigRecord, exc: UpdateSetError) -> AppliedRecord:
    """Build an AppliedRecord whose action depends on whether THIS record failed."""
    if record.sys_id == exc.failed_record_sys_id:
        return AppliedRecord(
            table=record.table,
            name=_record_name(record),
            requested_sys_id=record.sys_id,
            action=AppliedAction.FAILED,
            error_message=str(exc),
        )
    return AppliedRecord(
        table=record.table,
        name=_record_name(record),
        requested_sys_id=record.sys_id,
        action=AppliedAction.REQUESTED,
        error_message=None,
    )


def _record_name(record: ConfigRecord) -> str:
    """Extract a display name for AppliedRecord.name (falls back to sys_id)."""
    raw = record.fields.get("name")
    if isinstance(raw, str) and raw:
        return raw
    return record.sys_id
