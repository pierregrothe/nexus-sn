# src/nexus/schema/enricher.py
# AI-enriches a SchemaGraph into a domain-grouped MindmapCatalog.
# Author: Pierre Grothe
# Date: 2026-06-08
"""TableEnricher: sys_documentation hints + one batched AgentClient call."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import cast

from nexus.api.agent_client import AgentClientProtocol
from nexus.api.errors import AnthropicError
from nexus.connectors.servicenow.protocol import ServiceNowClientProtocol
from nexus.schema.catalog import Domain, MindmapCatalog, Section, TableDescription
from nexus.schema.discoverer import cell
from nexus.schema.models import SchemaGraph, TableDef

log = logging.getLogger(__name__)

__all__ = ["TableEnricher"]

_IN_BATCH = 50
_SYSTEM = (
    "You are a ServiceNow data-model architect. Given tables with their fields, "
    "organize EVERY table into a two-level hierarchy: a few broad top-level "
    "sections (e.g. Core, Planning), each containing business domains, each "
    "containing tables. Each domain must list its tables directly in a 'tables' "
    "array; never nest domains inside domains. Write a one-line 'Stores X' "
    "description for each table, grounded ONLY in the listed columns. Never invent "
    "tables. Respond with JSON only (no prose) of the exact shape: "
    '{"sections":[{"name":"<section>","domains":[{"name":"<domain>",'
    '"tables":[{"table":"<name>","description":"<text>"}]}]}]}'
)


def _tables_from(
    raw_tables: object, label_by_name: Mapping[str, str]
) -> tuple[TableDescription, ...]:
    """Build table descriptions, skipping entries missing table or description.

    Args:
        raw_tables: The AI ``tables`` value (expected a list of dicts).
        label_by_name: table name -> discovered label.

    Returns:
        Validated table descriptions in input order.
    """
    if not isinstance(raw_tables, list):
        return ()
    out: list[TableDescription] = []
    for item in cast("list[object]", raw_tables):
        if not isinstance(item, dict):
            continue
        t = cast("dict[str, object]", item)
        if "table" in t and "description" in t:
            name = str(t["table"])
            out.append(
                TableDescription(
                    table=name,
                    label=label_by_name.get(name, name),
                    description=str(t["description"]),
                    source="ai",
                )
            )
    return tuple(out)


def _domains_from(node: object, label_by_name: Mapping[str, str]) -> list[Domain]:
    """Flatten an AI node into leaf domains.

    A node carries either ``tables`` (a leaf domain) or nested ``domains`` (the
    model occasionally adds an extra level); nesting is flattened recursively so
    the catalog stays two-level. Tables-less domains are dropped.

    Args:
        node: A domain-shaped dict from the AI response.
        label_by_name: table name -> discovered label.

    Returns:
        The flattened leaf domains.
    """
    if not isinstance(node, dict):
        return []
    n = cast("dict[str, object]", node)
    if "tables" in n:
        tables = _tables_from(n["tables"], label_by_name)
        return [Domain(name=str(n.get("name", "")), tables=tables)] if tables else []
    out: list[Domain] = []
    nested = n.get("domains", [])
    if isinstance(nested, list):
        for sub in cast("list[object]", nested):
            out.extend(_domains_from(sub, label_by_name))
    return out


def _sections_from(raw_sections: object, label_by_name: Mapping[str, str]) -> tuple[Section, ...]:
    """Build catalog sections, tolerating shape variation and extra nesting.

    Args:
        raw_sections: The AI ``sections`` value (expected a list of dicts).
        label_by_name: table name -> discovered label.

    Returns:
        Sections with at least one domain each; empty when nothing usable.
    """
    if not isinstance(raw_sections, list):
        return ()
    out: list[Section] = []
    for item in cast("list[object]", raw_sections):
        if not isinstance(item, dict):
            continue
        s = cast("dict[str, object]", item)
        domains: list[Domain] = []
        nested = s.get("domains", [])
        if isinstance(nested, list):
            for d in cast("list[object]", nested):
                domains.extend(_domains_from(d, label_by_name))
        if "tables" in s:  # a section that directly holds tables
            domains.extend(_domains_from(s, label_by_name))
        if domains:
            out.append(Section(name=str(s.get("name", "")), domains=tuple(domains)))
    return tuple(out)


class TableEnricher:
    """Builds a MindmapCatalog from a SchemaGraph using Claude.

    Args:
        client: Open ServiceNow client (read-only; used for sys_documentation).
        agent_client: LLM client for clustering + descriptions.
        clock: UTC clock (injectable for tests).
    """

    def __init__(
        self,
        client: ServiceNowClientProtocol,
        agent_client: AgentClientProtocol,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        """Initialize with a client, agent client, and clock."""
        self._client = client
        self._agent = agent_client
        self._clock = clock

    async def enrich(self, graph: SchemaGraph, *, display: str) -> MindmapCatalog:
        """Cluster the area's tables into domains with AI descriptions.

        Args:
            graph: The discovered schema graph.
            display: Area display name (the mindmap root label).

        Returns:
            A MindmapCatalog. Falls back to scope-grouping if the AI call fails.
        """
        in_scope = [t for t in graph.tables if not t.is_neighbor]
        label_by_name = {t.name: t.label for t in in_scope}
        hints = await self._fetch_hints([t.name for t in in_scope])
        prompt = self._build_prompt(in_scope, hints)
        try:
            raw = await self._agent.complete(prompt, system=_SYSTEM)
            return self._parse(raw, label_by_name, graph, display)
        except (AnthropicError, ValueError) as exc:
            log.warning("mindmap AI enrichment failed (%s); using fallback", exc)
            return self._fallback(in_scope, graph, display)

    async def _fetch_hints(self, table_names: list[str]) -> dict[tuple[str, str], str]:
        """Fetch sparse field-level hint text for grounding.

        Args:
            table_names: In-scope table names.

        Returns:
            Mapping of (table, element) to hint text.
        """
        hints: dict[tuple[str, str], str] = {}
        uniq = sorted(set(table_names))
        for i in range(0, len(uniq), _IN_BATCH):
            batch = uniq[i : i + _IN_BATCH]
            rows = await self._client.list_records(
                "sys_documentation",
                query=f"nameIN{','.join(batch)}^elementISNOTEMPTY^hintISNOTEMPTY",
                fields="name,element,hint",
                limit=5000,
            )
            for r in rows:
                hints[(cell(r, "name"), cell(r, "element"))] = cell(r, "hint")
        return hints

    def _build_prompt(self, tables: list[TableDef], hints: Mapping[tuple[str, str], str]) -> str:
        """Render a deterministic prompt describing every table and its fields.

        Args:
            tables: In-scope tables.
            hints: (table, element) -> hint text for grounding.

        Returns:
            The prompt string.
        """
        blocks: list[str] = []
        for t in sorted(tables, key=lambda x: x.name):
            field_lines: list[str] = []
            for f in t.fields:
                ref = f" -> {f.reference_target}" if f.reference_target else ""
                hint = hints.get((t.name, f.name), "")
                hint_txt = f"  ({hint})" if hint else ""
                field_lines.append(f"    - {f.name}: {f.label}{ref}{hint_txt}")
            fields = "\n".join(field_lines) or "    (no custom fields)"
            blocks.append(f"TABLE {t.name} [{t.label}] scope={t.scope}\n{fields}")
        return "Tables:\n\n" + "\n\n".join(blocks)

    def _parse(
        self,
        raw: str,
        label_by_name: Mapping[str, str],
        graph: SchemaGraph,
        display: str,
    ) -> MindmapCatalog:
        """Parse the AI JSON into a MindmapCatalog.

        Args:
            raw: The raw AI response text.
            label_by_name: table name -> discovered label.
            graph: The source graph (for instance/area identity).
            display: Area display name.

        Returns:
            The parsed MindmapCatalog.

        Raises:
            ValueError: If the response has no JSON object or a malformed shape.
        """
        start, end = raw.find("{"), raw.rfind("}")
        if start == -1 or end < start:
            raise ValueError("no JSON object in AI response")
        # json.loads raises JSONDecodeError (a ValueError), which enrich() maps to
        # the scope-grouping fallback; the tolerant helpers below never raise.
        obj = json.loads(raw[start : end + 1])
        raw_sections: object = None
        if isinstance(obj, dict):
            top = cast("dict[str, object]", obj)
            raw_sections = top.get("sections")
            if raw_sections is None and "domains" in top:
                # tolerate the older flat {"domains": [...]} shape
                raw_sections = [{"name": display, "domains": top["domains"]}]
        sections = _sections_from(raw_sections, label_by_name)
        if not sections:
            raise ValueError("AI JSON produced no usable tables")
        return MindmapCatalog(
            instance_id=graph.instance_id,
            area_key=graph.area_key,
            generated_at=self._clock(),
            display=display,
            sections=sections,
        )

    def _fallback(self, tables: list[TableDef], graph: SchemaGraph, display: str) -> MindmapCatalog:
        """Build a scope-grouped, label-described catalog when the AI is unavailable.

        Args:
            tables: In-scope tables.
            graph: The source graph (for instance/area identity).
            display: Area display name.

        Returns:
            A fallback MindmapCatalog: a single section, one domain per scope.
        """
        by_scope: dict[str, list[TableDef]] = {}
        for t in tables:
            by_scope.setdefault(t.scope, []).append(t)
        domains = tuple(
            Domain(
                name=scope,
                tables=tuple(
                    TableDescription(
                        table=t.name, label=t.label, description=t.label, source="label"
                    )
                    for t in tabs
                ),
            )
            for scope, tabs in sorted(by_scope.items())
        )
        return MindmapCatalog(
            instance_id=graph.instance_id,
            area_key=graph.area_key,
            generated_at=self._clock(),
            display=display,
            sections=(Section(name=display, domains=domains),),
        )
