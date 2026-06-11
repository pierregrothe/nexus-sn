# src/nexus/cli/commands_schema.py
# Typer command bodies for the `nexus schema` sub-app.
# Author: Pierre Grothe
# Date: 2026-06-08
"""`nexus schema` commands: products and erd."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer

from nexus.api.errors import KrokiError
from nexus.api.kroki_client import DEFAULT_KROKI_TIMEOUT, DEFAULT_KROKI_URL, ImageFormat
from nexus.cli.apps import schema_app
from nexus.cli.auth import config_default as _config_default
from nexus.cli.console import console
from nexus.cli.help_text import SCHEMA_HELP, SCHEMA_PARENT, guide_items
from nexus.cli.utils import humanize_age
from nexus.cli.views import _build_offline_schema_renderer, _build_schema_cartographer
from nexus.config.paths import NexusPaths
from nexus.schema.errors import SchemaError
from nexus.schema.models import SchemaArea, ScopeEntry
from nexus.schema.product_registry import ProductRegistry
from nexus.schema.products import SchemaProductCatalog
from nexus.ui import CommandGuide, CommandHelp, Hint, Notice, nexus_progress

__all__: list[str] = []


def _build_schema_area(
    product: str,
    product2: str | None,
    catalog: SchemaProductCatalog,
) -> SchemaArea | None:
    """Resolve 1-2 product references to a SchemaArea. Prints errors and returns None on failure.

    Args:
        product: First product reference (key, acronym, or name).
        product2: Optional second product reference.
        catalog: The catalog to resolve against.

    Returns:
        A SchemaArea on success, None if any error was printed.
    """
    p1 = catalog.resolve(product)
    if p1 is None:
        valid = ", ".join(p.key for p in catalog.products)
        console.print(Notice.error(f"Unknown product {product!r}. Available: {valid}."))
        console.print(Hint(label="List products", command="nexus schema products"))
        return None

    if product2 is None:
        if not p1.scopes:
            console.print(
                Notice.error(
                    f"Product {p1.key!r} has no discoverable scopes. "
                    "Use it as the second argument to combine with a scoped product."
                )
            )
            return None
        return SchemaArea(
            key=p1.key,
            display=p1.name,
            scopes=tuple(ScopeEntry(key=s.key, label=s.label) for s in p1.scopes),
            bridge_targets=p1.bridge_targets,
        )

    p2 = catalog.resolve(product2)
    if p2 is None:
        valid = ", ".join(p.key for p in catalog.products)
        console.print(Notice.error(f"Unknown product {product2!r}. Available: {valid}."))
        console.print(Hint(label="List products", command="nexus schema products"))
        return None

    if not p1.scopes and not p2.scopes:
        console.print(
            Notice.error(
                f"Cannot combine two bridge-only products ({p1.key!r} and {p2.key!r}). "
                "At least one must have scopes."
            )
        )
        return None

    if p1.scopes and p2.scopes:
        combined_scopes = (*p1.scopes, *p2.scopes)
        combined_bridge: tuple[str, ...] = (*p1.bridge_targets, *p2.bridge_targets)
    elif p1.scopes:
        combined_scopes = p1.scopes
        combined_bridge = p2.bridge_targets
    else:
        combined_scopes = p2.scopes
        combined_bridge = p1.bridge_targets

    return SchemaArea(
        key=f"{p1.key}-{p2.key}",
        display=f"{p1.name} + {p2.name}",
        scopes=tuple(ScopeEntry(key=s.key, label=s.label) for s in combined_scopes),
        bridge_targets=combined_bridge,
    )


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


@schema_app.command("products")
def schema_products() -> None:
    """List available schema products and their scopes."""
    registry = ProductRegistry(NexusPaths.from_env().schema_dir)
    catalog = registry.load_catalog()
    cached = registry.load_cached()
    for p in catalog.products:
        scope_str = ", ".join(s.key for s in p.scopes) or "(bridge-only)"
        bridge_str = f"  bridge: {', '.join(p.bridge_targets)}" if p.bridge_targets else ""
        console.print(f"{p.key}  [{p.acronym}]  {p.name}  ({scope_str}){bridge_str}")
    if cached is not None:
        age = datetime.now(UTC) - cached.cached_at
        console.print(
            f"(synced {humanize_age(age)} via {cached.source.repo}@{cached.source.branch})"
        )
    else:
        console.print("(bundled)")


@schema_app.command("erd")
def schema_erd(
    product: Annotated[str, typer.Argument(help="Product name, acronym, or key")],
    product2: Annotated[
        str | None, typer.Argument(help="Second product to combine (optional, max 2)")
    ] = None,
    profile: Annotated[str, typer.Option(help="Instance profile name")] = "",
    output: Annotated[
        Path | None, typer.Option("-o", "--output", help="Output Markdown path")
    ] = None,
    image: Annotated[
        ImageFormat | None,
        typer.Option("--image", help="Diagram image format via Kroki (default: svg; use --image png to change, --no-image to skip)"),
    ] = ImageFormat.svg,
    grouped: Annotated[
        bool,
        typer.Option("--grouped", help="Split the ERD into one Mermaid diagram per scope"),
    ] = False,
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
    ] = DEFAULT_KROKI_URL,
    kroki_timeout: Annotated[
        float, typer.Option("--kroki-timeout", help="Kroki request timeout in seconds")
    ] = DEFAULT_KROKI_TIMEOUT,
) -> None:
    """Reverse-engineer one or two products and write a Markdown ERD."""
    if save_archive and from_archive is not None:
        console.print(Notice.error("--save-archive cannot be combined with --from-archive."))
        raise typer.Exit(2)

    catalog = ProductRegistry(NexusPaths.from_env().schema_dir).load_catalog()
    area: SchemaArea | None = None

    if from_archive is None:
        area = _build_schema_area(product, product2, catalog)
        if area is None:
            raise typer.Exit(2)

    async def _run_live() -> None:
        assert area is not None
        cartographer, client = _build_schema_cartographer(
            profile, kroki_url, kroki_timeout, areas={area.key: area}
        )
        resolved = profile or _config_default()
        labels = {s.key: s.label for s in area.scopes}
        with nexus_progress(console) as progress:
            progress.add_task(f"Mapping {area.key} on {resolved}...", total=None)
            async with client:
                graph = await cartographer.discover(resolved, area.key)
            if not graph.tables:
                console.print(Notice.warn(f"No tables discovered for {area.key} on {resolved}."))
            if save_archive:
                snapshot = cartographer.save_archive(graph)
                console.print(f"Wrote archive to {snapshot}")
            markdown = (
                cartographer.render_erd_grouped(graph, labels)
                if grouped
                else cartographer.render_erd(graph)
            )
            dest = output or Path(f"{area.key}-{resolved}.md")
            dest.write_text(markdown, encoding="utf-8")
            console.print(f"Wrote ERD to {dest}")
            if image is not None:
                progress.add_task(f"Rendering {image} via {kroki_url}...", total=None)
                if grouped:
                    images = await cartographer.render_erd_group_images(graph, labels, fmt=image)
                    for key, data in images:
                        img_dest = dest.with_name(f"{dest.stem}-{key}.{image}")
                        img_dest.write_bytes(data)
                        console.print(f"Wrote image to {img_dest}")
                else:
                    data = await cartographer.render_erd_image(graph, fmt=image)
                    img_dest = dest.with_suffix(f".{image}")
                    img_dest.write_bytes(data)
                    console.print(f"Wrote image to {img_dest}")

    async def _run_offline(snapshot: Path) -> None:
        reader, emitter, kroki = _build_offline_schema_renderer(kroki_url, kroki_timeout)
        graph = reader.read(snapshot)
        snap_product = catalog.resolve(graph.area_key)
        labels = {s.key: s.label for s in snap_product.scopes} if snap_product else {}
        if product != graph.area_key:
            console.print(
                Notice.warn(f"archive contains area {graph.area_key}, ignoring argument {product}")
            )
        markdown = emitter.render_grouped(graph, labels) if grouped else emitter.render(graph)
        dest = output or Path(f"{graph.area_key}-{graph.instance_id}.md")
        dest.write_text(markdown, encoding="utf-8")
        console.print(f"Wrote ERD to {dest}")
        if image is not None:
            with nexus_progress(console) as progress:
                progress.add_task(f"Rendering {image} via {kroki_url}...", total=None)
                if grouped:
                    for group in emitter.group_diagrams(graph, labels):
                        data = await kroki.render(group.source, fmt=image)
                        img_dest = dest.with_name(f"{dest.stem}-{group.key}.{image}")
                        img_dest.write_bytes(data)
                        console.print(f"Wrote image to {img_dest}")
                else:
                    data = await kroki.render(emitter.diagram(graph), fmt=image)
                    img_dest = dest.with_suffix(f".{image}")
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
