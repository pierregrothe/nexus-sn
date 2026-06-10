# src/nexus/cli/commands_schema.py
# Typer command bodies for the `nexus schema` sub-app.
# Author: Pierre Grothe
# Date: 2026-06-08
"""`nexus schema` commands: areas and erd."""

from __future__ import annotations

import asyncio
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer

from nexus.api.errors import KrokiError
from nexus.cli.apps import schema_app
from nexus.cli.auth import config_default as _config_default
from nexus.cli.console import console
from nexus.cli.help_text import SCHEMA_HELP, SCHEMA_PARENT, guide_items
from nexus.cli.views import _build_offline_schema_renderer, _build_schema_cartographer
from nexus.schema.areas import DEFAULT_AREAS
from nexus.schema.errors import SchemaError
from nexus.ui import CommandGuide, CommandHelp, Hint, Notice, nexus_progress

__all__: list[str] = []


class ImageFormat(StrEnum):
    """Supported diagram image formats for Kroki rendering."""

    svg = "svg"
    png = "png"


_KROKI_DEFAULT = "https://kroki.io"
_KROKI_TIMEOUT_DEFAULT = 60.0


@schema_app.callback(invoke_without_command=True)
def schema_callback(ctx: typer.Context) -> None:
    """Show schema help and available commands."""
    if ctx.invoked_subcommand is not None:
        return
    console.print(CommandHelp(title="nexus schema", entry=SCHEMA_PARENT))
    console.print(
        CommandGuide(
            app_name="nexus schema",
            items=guide_items(SCHEMA_HELP),
            title="available commands",
        )
    )


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
    image: Annotated[
        ImageFormat | None,
        typer.Option("--image", help="Also render a shareable image (svg or png) via Kroki"),
    ] = None,
    save_archive: Annotated[
        bool,
        typer.Option("--save-archive", help="Also persist the discovered graph as a JSON snapshot"),
    ] = False,
    from_archive: Annotated[
        Path | None,
        typer.Option(
            "--from-archive",
            help="Re-render offline from a saved JSON snapshot (no instance access)",
        ),
    ] = None,
    kroki_url: Annotated[
        str, typer.Option("--kroki-url", envvar="NEXUS_KROKI_URL", help="Kroki render endpoint")
    ] = _KROKI_DEFAULT,
    kroki_timeout: Annotated[
        float, typer.Option("--kroki-timeout", help="Kroki request timeout in seconds")
    ] = _KROKI_TIMEOUT_DEFAULT,
) -> None:
    """Reverse-engineer an area and write a Markdown ERD."""
    if save_archive and from_archive is not None:
        console.print(Notice.error("--save-archive cannot be combined with --from-archive."))
        raise typer.Exit(2)
    if from_archive is None and area not in DEFAULT_AREAS:
        valid = ", ".join(DEFAULT_AREAS)
        console.print(Notice.error(f"Unknown schema area {area!r}. Valid areas: {valid}."))
        console.print(Hint(label="List areas", command="nexus schema areas"))
        raise typer.Exit(2)

    async def _run_live() -> None:
        cartographer, client = _build_schema_cartographer(profile, kroki_url, kroki_timeout)
        resolved = profile or _config_default()
        with nexus_progress(console) as progress:
            progress.add_task(f"Mapping {area} on {resolved}...", total=None)
            async with client:
                graph = await cartographer.discover(resolved, area)
            if not graph.tables:
                console.print(Notice.warn(f"No tables discovered for {area} on {resolved}."))
            if save_archive:
                snapshot = cartographer.save_archive(graph)
                console.print(f"Wrote archive to {snapshot}")
            markdown = cartographer.render_erd(graph)
            dest = output or Path(f"{area}-{resolved}.md")
            dest.write_text(markdown, encoding="utf-8")
            console.print(f"Wrote ERD to {dest}")
            if image is not None:
                progress.add_task(f"Rendering {image.value} via {kroki_url}...", total=None)
                data = await cartographer.render_erd_image(graph, fmt=image.value)
                img_dest = dest.with_suffix(f".{image.value}")
                img_dest.write_bytes(data)
                console.print(f"Wrote image to {img_dest}")

    async def _run_offline(snapshot: Path) -> None:
        reader, emitter, kroki = _build_offline_schema_renderer(kroki_url, kroki_timeout)
        graph = reader.read(snapshot)
        if area != graph.area_key:
            console.print(
                Notice.warn(f"archive contains area {graph.area_key}, ignoring argument {area}")
            )
        markdown = emitter.render(graph)
        dest = output or Path(f"{graph.area_key}-{graph.instance_id}.md")
        dest.write_text(markdown, encoding="utf-8")
        console.print(f"Wrote ERD to {dest}")
        if image is not None:
            with nexus_progress(console) as progress:
                progress.add_task(f"Rendering {image.value} via {kroki_url}...", total=None)
                data = await kroki.render(emitter.diagram(graph), fmt=image.value)
            img_dest = dest.with_suffix(f".{image.value}")
            img_dest.write_bytes(data)
            console.print(f"Wrote image to {img_dest}")

    try:
        if from_archive is not None:
            asyncio.run(_run_offline(from_archive))
        else:
            asyncio.run(_run_live())
    except SchemaError as exc:
        console.print(Notice.error(str(exc)))
        raise typer.Exit(1) from exc
    except KrokiError as exc:
        console.print(Notice.error(str(exc)))
        console.print(
            Hint(
                label="Kroki",
                command="--kroki-url <endpoint> --kroki-timeout <seconds>",
                suffix="(self-hosting guide: docs/schema-image-export.md)",
            )
        )
        raise typer.Exit(1) from exc
