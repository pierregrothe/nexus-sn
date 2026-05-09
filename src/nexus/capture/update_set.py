# src/nexus/capture/update_set.py
# Injects captured configs into a ServiceNow update set via the Table API.
# Author: Pierre Grothe
# Date: 2026-05-09

"""UpdateSetWriter: creates or reuses a sys_update_set and injects records."""

import logging

from nexus.capture.errors import UpdateSetError
from nexus.capture.models import CaptureResult, UpdateSetRef
from nexus.capture.xml_builder import UpdateSetXmlBuilder
from nexus.connectors.servicenow.client import ServiceNowClient
from nexus.connectors.servicenow.errors import SNClientError

log = logging.getLogger(__name__)

__all__ = ["UpdateSetWriter"]


class UpdateSetWriter:
    """Pushes a CaptureResult into a ServiceNow update set.

    Args:
        client: Open ServiceNowClient for the target instance.
        builder: XML builder for generating update set payloads.
    """

    def __init__(
        self,
        client: ServiceNowClient,
        builder: UpdateSetXmlBuilder,
    ) -> None:
        """Initialize with an open client and XML builder."""
        self._client = client
        self._builder = builder

    async def push(
        self,
        result: CaptureResult,
        instance_id: str,
        update_set_name: str,
    ) -> UpdateSetRef:
        """Inject all records into a new or existing in-progress update set.

        Args:
            result: CaptureResult to deploy.
            instance_id: Target instance profile name.
            update_set_name: Name for the update set.

        Returns:
            UpdateSetRef for the created or reused update set.

        Raises:
            UpdateSetError: If any record injection fails.
        """
        update_set_sys_id = await self._get_or_create_update_set(update_set_name)
        count = 0
        for record in result.records:
            payload = self._builder.build(record)
            try:
                await self._client.create_record(
                    "sys_update_xml",
                    data={
                        "update_set": update_set_sys_id,
                        "name": f"{record.table}_{record.sys_id}",
                        "type": record.table,
                        "payload": payload,
                        "action": "INSERT_OR_UPDATE",
                    },
                )
                count += 1
            except SNClientError as exc:
                raise UpdateSetError(
                    update_set_name=update_set_name,
                    instance_id=instance_id,
                    failed_record_sys_id=record.sys_id,
                    failed_table=record.table,
                ) from exc

        log.info(
            "injected %d records into update set %r on %s",
            count,
            update_set_name,
            instance_id,
        )
        return UpdateSetRef(
            sys_id=update_set_sys_id,
            name=update_set_name,
            state="in progress",
            record_count=count,
            instance_id=instance_id,
        )

    async def _get_or_create_update_set(self, name: str) -> str:
        """Find an existing in-progress update set or create a new one.

        Args:
            name: Update set name to look up or create.

        Returns:
            sys_id of the located or newly created update set.
        """
        existing = await self._client.query_table(
            "sys_update_set",
            query=f"name={name}^state=in progress",
            limit=1,
        )
        if existing:
            sys_id = str(existing[0].get("sys_id", ""))
            log.info("reusing existing update set %r (%s)", name, sys_id)
            return sys_id

        created = await self._client.create_record(
            "sys_update_set",
            data={"name": name, "state": "in progress"},
        )
        sys_id = str(created.get("sys_id", ""))
        log.info("created update set %r (%s)", name, sys_id)
        return sys_id
