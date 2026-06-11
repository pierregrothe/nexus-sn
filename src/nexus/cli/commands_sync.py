# src/nexus/cli/commands_sync.py
# `nexus sync` + `nexus templates` -- catalog index commands.
# Author: Pierre Grothe
# Date: 2026-05-18
"""nexus sync and nexus templates -- v1 catalog-index commands.

* ``nexus sync`` pulls a manifest from the configured GitHub repo
  and writes it to ``~/.nexus/templates/manifest.json``. Fail-fast
  on missing/invalid config; logs every HTTP / parse failure.
* ``nexus templates`` reads the local cache and renders a DataTable
  or, when no prior sync has run, prints a Hint pointing at sync.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import typer
from rich.console import RenderableType
from rich.text import Text

from nexus.cli.apps import app
from nexus.cli.console import console, err_console
from nexus.cli.utils import humanize_age
from nexus.config.manager import ConfigManager
from nexus.config.paths import NexusPaths
from nexus.schema.sync import GitHubProductCatalogClient
from nexus.templates.registry import TemplateRegistry
from nexus.templates.sync import GitHubSync, GitHubTemplateClient, SyncReport
from nexus.ui import DataColumn, DataTable, Hint, Notice

if TYPE_CHECKING:
    from rich.console import Console

__all__: list[str] = []

_DEFAULT_MANIFEST_PATH = "templates/manifest.json"
_DEFAULT_CATALOG_PATH = "schema/products.json"


@app.command()
def sync() -> None:
    """Pull the template catalog from the configured GitHub registry.

    Reads ``github_repo`` and ``github_branch`` from ``~/.nexus/config.yaml``,
    fetches the manifest, and writes it to the local cache. Idempotent;
    safe to re-run.
    """
    exit_code = _sync_main(
        paths=NexusPaths.from_env(),
        config_manager=ConfigManager(),
        client=GitHubTemplateClient(),
        console_out=console,
        console_err=err_console,
    )
    if exit_code != 0:
        raise typer.Exit(exit_code)


@app.command("templates")
def templates_cmd() -> None:
    """Show the cached template catalog (run ``nexus sync`` first).

    Reads the local manifest cache and renders a DataTable of available
    templates. If no prior sync has run, prints a Hint pointing at
    ``nexus sync``.
    """
    _templates_main(
        paths=NexusPaths.from_env(),
        console_out=console,
    )


def _sync_main(
    *,
    paths: NexusPaths,
    config_manager: ConfigManager,
    client: GitHubTemplateClient,
    console_out: Console,
    console_err: Console,
    manifest_path: str = _DEFAULT_MANIFEST_PATH,
    catalog_path: str = _DEFAULT_CATALOG_PATH,
    catalog_client: GitHubProductCatalogClient | None = None,
) -> int:
    """Core sync logic; returns exit code (0 success, 1 error).

    Args:
        paths: NexusPaths rooted at the runtime .nexus/ dir.
        config_manager: ConfigManager to load github_repo / github_branch.
        client: GitHubTemplateClient for the template manifest HTTP fetch.
        console_out: Rich console for user-facing status.
        console_err: Rich console for errors.
        manifest_path: Path to the template manifest within the repo.
        catalog_path: Path to the schema product catalog within the repo.
        catalog_client: GitHubProductCatalogClient (injectable for tests).

    Returns:
        0 on success; 1 if the template sync fails (catalog failure is
        non-fatal and never causes a non-zero exit).
    """
    preferences = config_manager.load().preferences
    registry = TemplateRegistry(paths.templates_dir)
    orchestrator = GitHubSync(client=client, registry=registry)
    report = orchestrator.run(
        repo=preferences.github_repo,
        branch=preferences.github_branch,
        path=manifest_path,
    )
    exit_code = _render_sync_report(report, console_out, console_err)
    if exit_code != 0:
        return exit_code

    # Schema product catalog sync -- best-effort, never blocks template sync.
    _sync_schema_catalog(
        repo=preferences.github_repo,
        branch=preferences.github_branch,
        path=catalog_path,
        schema_dir=paths.schema_dir,
        catalog_client=catalog_client or GitHubProductCatalogClient(),
        console_out=console_out,
        console_err=console_err,
    )
    return 0


def _sync_schema_catalog(
    *,
    repo: str,
    branch: str,
    path: str,
    schema_dir: Path,
    catalog_client: GitHubProductCatalogClient,
    console_out: Console,
    console_err: Console,
) -> None:
    """Run SchemaSync and print a one-line result. Never raises.

    Args:
        repo: GitHub owner/name slug.
        branch: GitHub branch name.
        path: Path to the catalog within the repo.
        schema_dir: Local cache directory.
        catalog_client: HTTP client for the fetch.
        console_out: Rich console for success output.
        console_err: Rich console for warnings.
    """
    from nexus.schema.product_registry import ProductRegistry  # noqa: PLC0415
    from nexus.schema.sync import SchemaSync  # noqa: PLC0415

    schema_registry = ProductRegistry(schema_dir)
    schema_report = SchemaSync(client=catalog_client, registry=schema_registry).run(
        repo=repo, branch=branch, path=path
    )
    if schema_report.outcome == "ok" and schema_report.cached is not None:
        count = len(schema_report.cached.catalog.products)
        console_out.print(Notice.info(f"Synced {count} schema products from {repo}@{branch}."))
    else:
        console_err.print(
            Notice.warn(
                "Schema product catalog sync failed (see log). " "Using cached or bundled catalog."
            )
        )


def _render_sync_report(report: SyncReport, console_out: Console, console_err: Console) -> int:
    """Map a ``SyncReport`` to console output + exit code.

    Args:
        report: Result from ``GitHubSync.run``.
        console_out: Rich console for success output.
        console_err: Rich console for failure output.

    Returns:
        0 when ``report.outcome == "ok"``, else 1.
    """
    match report.outcome:
        case "no-config":
            console_err.print(Notice.error("Template registry not configured."))
            console_err.print(
                Hint(
                    label="Resolve",
                    command="edit ~/.nexus/config.yaml",
                    suffix="and set preferences.github_repo to <owner>/<name>",
                )
            )
            return 1
        case "invalid-repo":
            console_err.print(Notice.error(report.reason or "Invalid github_repo."))
            return 1
        case "fetch-failed":
            console_err.print(Notice.error(report.reason or "Sync failed."))
            return 1
        case "ok":
            if report.manifest is None:  # pragma: no cover -- guard for typing
                console_err.print(Notice.error("Sync reported ok but no manifest."))
                return 1
            count = len(report.manifest.wire.templates)
            source = report.manifest.source
            console_out.print(
                Notice.info(f"Synced {count} templates from {source.repo}@{source.branch}.")
            )
            return 0


def _templates_main(*, paths: NexusPaths, console_out: Console) -> int:
    """Render the cached manifest as a DataTable, or print a Hint when absent.

    Args:
        paths: ``NexusPaths`` whose ``templates_dir`` holds the cache.
        console_out: Rich console for output.

    Returns:
        Always 0 -- ``nexus templates`` is read-only and never fails
        in a user-facing way.
    """
    registry = TemplateRegistry(paths.templates_dir)
    cached = registry.load_manifest()
    if cached is None:
        console_out.print(
            Hint(
                label="No catalog cached",
                command="nexus sync",
                suffix="to pull the template catalog",
            )
        )
        return 0
    source = cached.source
    age = datetime.now(UTC) - cached.cached_at
    footer = f"synced {humanize_age(age)} via {source.repo}@{source.branch}"
    if not cached.wire.templates:
        console_out.print(Notice.info("Catalog is empty."))
        console_out.print(footer)
        return 0
    rows: list[list[RenderableType]] = []
    for entry in sorted(cached.wire.templates, key=lambda e: e.name):
        rows.append(
            [
                Text(entry.name),
                Text(entry.template_type),
                Text(entry.version),
                Text(entry.path),
            ]
        )
    console_out.print(
        DataTable(
            title="Templates",
            columns=[
                DataColumn(header="Name", width=24),
                DataColumn(header="Type", width=14),
                DataColumn(header="Version", width=10),
                DataColumn(header="Path", width=40),
            ],
            rows=rows,
        )
    )
    console_out.print(footer)
    return 0
