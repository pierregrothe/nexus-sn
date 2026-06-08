# src/nexus/cli/commands_schema.py
# Typer command bodies for the `nexus schema` sub-app.
# Author: Pierre Grothe
# Date: 2026-06-08
"""`nexus schema` commands: areas and erd."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

import typer

from nexus.cli.apps import schema_app
from nexus.cli.auth import config_default as _config_default
from nexus.cli.console import console
from nexus.cli.views import _build_schema_cartographer
from nexus.schema.areas import DEFAULT_AREAS
from nexus.ui import nexus_progress

__all__: list[str] = []


@schema_app.command("areas")
def schema_areas() -> None:
    """List the registered schema areas and their scopes."""
    for key, area in DEFAULT_AREAS.items():
        scopes = ", ".join(s.scope for s in area.scopes)
        console.print(f"{key}  --  {area.display}  ({scopes})")


@schema_app.command("erd")
def schema_erd(
    area: Annotated[str, typer.Argument(help="Area key (see `nexus schema areas`)")],
    profile: Annotated[str, typer.Option(help="Instance profile name")] = "",
    output: Annotated[
        Path | None, typer.Option("-o", "--output", help="Output Markdown path")
    ] = None,
) -> None:
    """Reverse-engineer an area and write a Markdown ERD."""

    async def _run() -> Path:
        cartographer, client = _build_schema_cartographer(profile)
        resolved = profile or _config_default()
        with nexus_progress(console) as progress:
            progress.add_task(f"Mapping {area} on {resolved}...", total=None)
            async with client:
                graph = await cartographer.discover(resolved, area)
        markdown = cartographer.render_erd(graph)
        dest = output or Path(f"{area}-{resolved}.md")
        dest.write_text(markdown, encoding="utf-8")
        return dest

    written = asyncio.run(_run())
    console.print(f"Wrote ERD to {written}")


@schema_app.command("mindmap")
def schema_mindmap(
    area: Annotated[str, typer.Argument(help="Area key (see `nexus schema areas`)")],
    profile: Annotated[str, typer.Option(help="Instance profile name")] = "",
    output: Annotated[
        Path | None, typer.Option("-o", "--output", help="Output Markdown path")
    ] = None,
) -> None:
    """Reverse-engineer an area and write an AI-described mindmap catalog."""

    async def _run() -> Path:
        cartographer, client = _build_schema_cartographer(profile)
        resolved = profile or _config_default()
        with nexus_progress(console) as progress:
            progress.add_task(f"Describing {area} on {resolved}...", total=None)
            async with client:
                catalog = await cartographer.build_mindmap(resolved, area)
        markdown = cartographer.render_mindmap(catalog)
        dest = output or Path(f"{area}-{resolved}-mindmap.md")
        dest.write_text(markdown, encoding="utf-8")
        return dest

    written = asyncio.run(_run())
    console.print(f"Wrote mindmap to {written}")
