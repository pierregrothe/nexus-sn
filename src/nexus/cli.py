# nexus/cli.py
# Typer CLI entry point for NEXUS.
# Author: Pierre Grothe
# Date: 2026-05-07

"""NEXUS command-line interface.

All commands validate config and credentials at startup.
Features requiring unavailable MCP servers are hidden from help text.
"""

from __future__ import annotations

import asyncio
import csv
import logging
import re
import sys
import uuid
from collections import Counter
from collections.abc import Iterable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, cast

if TYPE_CHECKING:
    from nexus.api.agent_client import AgentClientProtocol

import httpx
import typer
import yaml as _yaml
from packaging.version import InvalidVersion, parse
from pydantic import BaseModel, ConfigDict
from rich.console import Console, RenderableType
from rich.text import Text

from nexus.api.errors import AnthropicError
from nexus.auth.external_keychain import ExternalKeychainClient
from nexus.cache import clear_cache
from nexus.capabilities.claude_config import FilesystemClaudeCodeConfigReader
from nexus.capabilities.feature_flags import claude_ai_name_for
from nexus.capabilities.registry import CapabilitySet
from nexus.capabilities.status_reporter import StatusReporter
from nexus.capabilities.tier import TierDetection, TierDetector
from nexus.capture.engine import CaptureEngine
from nexus.capture.models import ArchiveManifest, ScopeEntry
from nexus.capture.tables import AI_AUTOMATION, DEFAULT_TABLE_GROUPS
from nexus.config.manager import ConfigManager
from nexus.config.paths import NexusPaths
from nexus.config.settings import InstancesConfig
from nexus.connectors.servicenow.client import ServiceNowClient
from nexus.instances.badges import token_badge
from nexus.instances.errors import (
    InstanceNotFoundError,
    OAuthError,
    SnapshotError,
    TokenExpiredError,
)
from nexus.instances.models import InstanceMeta, InstanceSnapshot
from nexus.instances.oauth import SNOAuthClient
from nexus.instances.registry import InstanceRegistry
from nexus.instances.scanner import InstanceScanner
from nexus.plugins import PluginInventory, PluginScanError, PluginScanner
from nexus.plugins.advisories import AdvisoryDatabase, compute_advisories
from nexus.plugins.baselines import DEFAULT_BASELINE_NAME, validate_baseline_name
from nexus.plugins.dependencies import DependencyEntry
from nexus.plugins.diff import (
    PluginDiff,
    PluginDiffEntry,
    PromotionPlan,
    compute_diff,
    project_to_promote_plan,
)
from nexus.plugins.drift import (
    compute_drift,
)
from nexus.plugins.errors import (
    BaselineNotFoundError,
    InvalidBaselineNameError,
    PluginAdvisoryDataError,
    PluginImpactError,
)
from nexus.plugins.executor import OperationResult
from nexus.plugins.impact import compute_impact
from nexus.plugins.models import (
    AdvisoryFinding,
    AdvisoryType,
    PluginImpact,
    PluginInfo,
    Severity,
)
from nexus.plugins.orphans import orphan_candidates
from nexus.plugins.overrides import AdvisoryOverride, AdvisoryOverrideSet, apply_overrides
from nexus.plugins.recommendations import (
    AI_MODEL,
    DEACTIVATE_SYSTEM_PROMPT,
    EXPLAIN_SYSTEM_PROMPT,
    ROADMAP_SYSTEM_PROMPT,
    build_deactivation_context,
    build_explain_context,
    build_roadmap_context,
)
from nexus.plugins.updates import plugins_with_updates
from nexus.ui import (
    CommandGuide,
    CommandHelp,
    CommandHelpEntry,
    DataColumn,
    DataTable,
    Hint,
    KeyValuePanel,
    KvRow,
    Notice,
    StatusBadge,
    default_marker,
    nexus_progress,
)
from nexus.ui.app import start_ui
from nexus.ui.banner import print_banner
from nexus.ui.theme import NEXUS_THEME
from nexus.updater import check_and_maybe_update, current_version
from nexus.updater.client import GitHubReleasesClient

__all__: list[str] = []

log = logging.getLogger(__name__)

app = typer.Typer(
    name="nexus",
    help="NEXUS -- ServiceNow AI architect agent",
)

instance_app = typer.Typer(name="instance", help="Manage ServiceNow instances.")
app.add_typer(instance_app)

capture_app = typer.Typer(name="capture", help="Capture and deploy ServiceNow configurations.")
app.add_typer(capture_app)

plugins_app = typer.Typer(
    name="plugins", help="Inspect the plugin inventory of registered instances."
)
app.add_typer(plugins_app)


def _help_entry(command: str, purpose: str, example: str) -> CommandHelpEntry:
    """Tiny constructor wrapper; avoids restating Pydantic keywords below."""
    return CommandHelpEntry(command=command, purpose=purpose, example=example)


def _guide_items(entries: list[CommandHelpEntry]) -> list[tuple[str, str]]:
    """Project a CommandHelpEntry list into ``(command, short_description)`` pairs.

    The short description is the first sentence of ``purpose`` (split on
    ``". "``) so the Box-2 listing stays single-line per row.
    """
    out: list[tuple[str, str]] = []
    for entry in entries:
        first = entry.purpose.split(". ", 1)[0].rstrip(".")
        out.append((entry.command, first))
    return out


_PLUGINS_PARENT = _help_entry(
    "plugins",
    "Inspect the plugin inventory of registered instances -- dependencies, "
    "advisories, drift, AI recommendations, and more.",
    "nexus plugins list --product ITSM",
)

_INSTANCE_PARENT = _help_entry(
    "instance",
    "Manage registered ServiceNow instances: register, connect, refresh, list, "
    "and switch the default profile.",
    "nexus instance register prod",
)

_CAPTURE_PARENT = _help_entry(
    "capture",
    "Bidirectional ServiceNow config transport: discover custom scopes, pull "
    "them as YAML archives, push archives back as update sets.",
    "nexus capture discover --instance prod",
)

_PLUGINS_RECOMMEND_PARENT = _help_entry(
    "plugins recommend",
    "AI-backed plugin recommendations (currently: which plugins are safest to " "deactivate).",
    "nexus plugins recommend deactivate",
)

_PLUGINS_BASELINES_PARENT = _help_entry(
    "plugins baselines",
    "Manage named plugin drift baselines. Drift is computed against the named "
    "baseline; multiple baselines can coexist per instance.",
    "nexus plugins baselines list",
)

_NEXUS_PARENT = _help_entry(
    "nexus",
    "NEXUS -- ServiceNow AI architect agent. Capture, assess, and act on "
    "ServiceNow instances from the command line.",
    "nexus instance list",
)


_PLUGINS_HELP: list[CommandHelpEntry] = [
    _help_entry(
        "list",
        "List every plugin and scoped app currently installed on the default "
        "instance. Filter by product family, source (servicenow|store|custom), "
        "or activation state to narrow the view.",
        "nexus plugins list --product ITSM --state active",
    ),
    _help_entry(
        "info <plugin_id>",
        "Drill into one plugin: full version, vendor, activation state, "
        "direct dependencies, and source table (v_plugin vs sys_store_app vs "
        "App Manager).",
        "nexus plugins info com.snc.incident",
    ),
    _help_entry(
        "export",
        "Dump the captured inventory to disk as YAML (default) or CSV. "
        "Useful for sharing snapshots with auditors or feeding external tools.",
        "nexus plugins export --format csv --out plugins.csv",
    ),
    _help_entry(
        "diff <a> <b>",
        "Compare plugin inventories across two profiles. Surfaces "
        "only-in-A, only-in-B, version mismatches, and state mismatches.",
        "nexus plugins diff dev prod --status version_mismatch",
    ),
    _help_entry(
        "promote <src> --to <dst>",
        "Generate an additive YAML action plan that brings <dst> up to "
        "match <src>: installs missing apps, upgrades older versions. "
        "Read-only -- the plan is reviewed before any apply step.",
        "nexus plugins promote dev --to prod --out promote-dev-to-prod.yaml",
    ),
    _help_entry(
        "updates",
        "List every plugin / app where a newer version is available, "
        "pulled live from the SN Application Manager. Optional --queue "
        "writes a YAML batch file for later apply.",
        "nexus plugins updates --queue pending.yaml",
    ),
    _help_entry(
        "advisories",
        "Report EOL / CVE / license findings for the inventory. Filter by "
        "type or minimum severity. --strict exits 1 if any finding remains "
        "after filters (CI gating).",
        "nexus plugins advisories --severity high --strict",
    ),
    _help_entry(
        "deactivate <plugin-id>",
        "Deactivate a plugin on the resolved instance. Mandatory impact "
        "gate blocks the op when reverse-deps exist; --force bypasses with a "
        "type-the-plugin-id confirmation.",
        "nexus plugins deactivate com.acme.app",
    ),
    _help_entry(
        "defer <id> <type> <details>",
        "Mute a single EOL/CVE/license finding with a written reason. "
        "Deferred findings are hidden from 'advisories' until "
        "--include-deferred is passed. Per-instance, persisted to disk.",
        "nexus plugins defer com.acme.helper cve 'CVE-2024-1234' --reason 'patch in next sprint'",
    ),
    _help_entry(
        "undo-defer <id> <type> <details>",
        "Reverse a previous 'defer'. The finding reappears in normal "
        "'advisories' output. Match the original plugin id + type + details exactly.",
        "nexus plugins undo-defer com.acme.helper cve 'CVE-2024-1234'",
    ),
    _help_entry(
        "list-deferred",
        "Audit view: every deferred finding on an instance with its reason "
        "and the date it was deferred. Use when reviewing whether old "
        "deferrals are still justified.",
        "nexus plugins list-deferred --format json",
    ),
    _help_entry(
        "impact <plugin_id>",
        "Pre-deactivation safety check: walks reverse dependencies, counts "
        "records owned by the plugin's scope, and scans cross-scope FK "
        "references. --live forces re-query of record counts.",
        "nexus plugins impact com.snc.incident --live",
    ),
    _help_entry(
        "orphans",
        "Find plugins safe to deactivate at a glance: no dependents AND "
        "zero scope-owned records. Filter by state to narrow further.",
        "nexus plugins orphans --state inactive",
    ),
    _help_entry(
        "drift",
        "Compare the live inventory against a named baseline. Use --ack "
        "to snapshot the current state as a new baseline. Multiple baselines "
        "can coexist (e.g. preprod, prod, golden-image).",
        "nexus plugins drift --baseline preprod --strict",
    ),
    _help_entry(
        "explain <plugin_id>",
        "Ask the bundled AI to explain what a plugin does, what depends on "
        "it, and whether keeping it makes sense. Refuses 'drop' verdicts "
        "for core ITSM/platform plugins regardless of evidence.",
        "nexus plugins explain com.snc.knowledge",
    ),
    _help_entry(
        "roadmap",
        "Ask the AI to draft an ordered remediation plan from your "
        "advisories + orphans + deferred overrides. Useful as input to a "
        "quarterly plugin-hygiene review.",
        "nexus plugins roadmap",
    ),
    _help_entry(
        "recommend deactivate",
        "AI-curated short list of plugins safest to turn off, with one-line "
        "rationale per candidate. Excludes anything load-bearing.",
        "nexus plugins recommend deactivate",
    ),
    _help_entry(
        "activate <plugin-id>",
        "Activate an installed plugin on the resolved instance. Blocks until SN "
        "reports terminal status.",
        "nexus plugins activate com.snc.discovery",
    ),
    _help_entry(
        "apply <plan.yaml>",
        "Execute a PromotionPlan YAML produced by `nexus plugins promote`. Rolls "
        "back partial failures.",
        "nexus plugins apply promote-dev-to-prod.yaml",
    ),
    _help_entry(
        "install <plugin-id>",
        "Install a plugin on the resolved instance. Shows the SN dependency "
        "cascade preview and blocks until terminal status.",
        "nexus plugins install com.snc.discovery",
    ),
    _help_entry(
        "uninstall <plugin-id>",
        "Uninstall a non-base plugin on the resolved instance. Base "
        "ServiceNow plugins (source=='servicenow') are refused even with "
        "--force.",
        "nexus plugins uninstall com.acme.app",
    ),
    _help_entry(
        "upgrade <plugin-id> [--to X.Y.Z]",
        "Upgrade a plugin to the latest available version, or to a specific "
        "version with --to. Shows the dependency cascade.",
        "nexus plugins upgrade com.snc.discovery --to 21.0",
    ),
    _help_entry(
        "baselines list",
        "Show every named drift baseline saved for an instance, with "
        "captured timestamp and plugin count.",
        "nexus plugins baselines list",
    ),
    _help_entry(
        "baselines delete <name>",
        "Remove a stored baseline. Pass --yes to skip the confirmation prompt.",
        "nexus plugins baselines delete preprod --yes",
    ),
]

_CAPTURE_HELP: list[CommandHelpEntry] = [
    _help_entry(
        "discover",
        "Walk every scope on the instance and surface the ones with custom "
        "AI / automation configs (skills, flows, virtual agent topics). "
        "Use --all to include built-in scopes; default hides them.",
        "nexus capture discover",
    ),
    _help_entry(
        "pull --scope <key>",
        "Snapshot one or more scopes to a versioned YAML archive on disk. "
        "Captured artifacts include ai_skill, sys_hub_flow, virtual agent "
        "topics, and related child records.",
        "nexus capture pull --scope x_company_app --scope x_company_helper",
    ),
    _help_entry(
        "list",
        "Show every archive previously captured on this machine, with "
        "source instance, captured timestamp, and scope counts.",
        "nexus capture list",
    ),
    _help_entry(
        "push <archive>",
        "Replay a captured archive into a sys_update_set on the target "
        "instance. The set name defaults to NEXUS-capture; override with "
        "--update-set.",
        "nexus capture push archives/2026-05-12_dev/ prod",
    ),
]

_PLUGINS_RECOMMEND_HELP: list[CommandHelpEntry] = [
    _help_entry(
        "deactivate",
        "Ask the bundled AI for a short list of plugins that look safe to "
        "turn off based on zero dependencies, zero records, and absence of "
        "advisories. Always includes a 'Watch out' section.",
        "nexus plugins recommend deactivate",
    ),
]

_PLUGINS_BASELINES_HELP: list[CommandHelpEntry] = [
    _help_entry(
        "list",
        "Show every named drift baseline saved for an instance, with "
        "captured timestamp and plugin count.",
        "nexus plugins baselines list",
    ),
    _help_entry(
        "delete <name>",
        "Remove a stored baseline. Pass --yes to skip the confirmation prompt.",
        "nexus plugins baselines delete preprod --yes",
    ),
]


# Custom scope prefixes -- anything else is an OOTB ServiceNow application.
_CUSTOM_SCOPE_PREFIXES = ("x_", "u_")

_SCOPE_KEY_WIDTH = 26  # column width for scope key (the identifier users copy)
_SCOPE_NAME_WIDTH = 20  # column width for display name

# Short column header per table spec name -- wide enough to be readable, narrow to fit 80-col
_TABLE_HEADER: dict[str, str] = {
    "ai_skill": "Skl",
    "sys_hub_flow": "Flow",
    "sys_hub_action_type_definition": "Act",
    "virtual_agent_conversation_topic": "VA",
    "sys_ai_agent": "AI",
}


def _today() -> date:
    """Current UTC calendar date. Single point for monkeypatching in tests."""
    return datetime.now(UTC).date()


def _trunc(s: str, width: int) -> str:
    """Truncate ``s`` to ``width`` characters, appending an ellipsis if needed.

    Args:
        s: Source string.
        width: Maximum width including the ellipsis.

    Returns:
        ``s`` unchanged if its length fits, otherwise the first ``width - 3``
        characters followed by ``"..."``.
    """
    return s if len(s) <= width else s[: width - 3] + "..."


def _force_utf8_streams() -> None:
    """Reconfigure stdout/stderr to UTF-8 so Rich's box and ellipsis chars render.

    Windows defaults stdout to the system code page (cp1252 on en-US).
    Rich's Panel/Table borders and ellipsis truncation use characters
    outside cp1252 and crash with UnicodeEncodeError on legacy_windows
    code paths. Forcing UTF-8 with ``errors='replace'`` keeps NEXUS
    usable on default Git Bash / cmd.exe while honoring the project's
    ASCII-only output rule (no glyphs are introduced by NEXUS itself).
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


_force_utf8_streams()
console = Console(theme=NEXUS_THEME, safe_box=True)
err_console = Console(stderr=True, theme=NEXUS_THEME, safe_box=True)

_FORMATS = ("text", "json")


def _validate_format(value: str) -> None:
    """Reject unknown ``--format`` values with a clear error.

    Args:
        value: User-provided format string.

    Raises:
        typer.Exit: With code 1 on unknown values, after printing
            a Notice.error to the console.
    """
    if value not in _FORMATS:
        console.print(Notice.error(f"Unknown --format: {value}"))
        raise typer.Exit(1)


def _emit_json(model: BaseModel) -> None:
    """Print model JSON serialization to stdout, one line.

    Uses ``model.model_dump_json()`` (not Rich's print_json) so the
    output is single-line and CI-script-friendly.

    Args:
        model: Any Pydantic model to serialize.
    """
    print(model.model_dump_json())


class _OrphansReport(BaseModel):
    """Inline wrapper for JSON output of nexus plugins orphans.

    Attributes:
        candidates: Plugins identified as orphan candidates.
    """

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    candidates: tuple[PluginInfo, ...]


class _UpdatesReport(BaseModel):
    """Inline wrapper for JSON output of nexus plugins updates.

    Attributes:
        updates: Plugins with newer versions available.
    """

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    updates: tuple[PluginInfo, ...]


def _configure_logging(level: str = "WARNING") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.WARNING),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )


_TOP_LEVEL_HELP: list[CommandHelpEntry] = [
    _help_entry(
        "status",
        "One-page dashboard: NEXUS identity, detected Claude tier, MCP "
        "integration availability, auto-update status. Run this first when "
        "something feels off.",
        "nexus status",
    ),
    _help_entry(
        "instance",
        "Manage registered SN instances -- register, connect, refresh, "
        "switch the default. Most subcommands accept [profile] and fall "
        "back to the default when omitted.",
        "nexus instance list",
    ),
    _help_entry(
        "capture",
        "Bidirectional SN config transport: discover custom scopes, pull "
        "them to YAML on disk, push archived YAML back as update sets. "
        "Workhorse command for dev -> test -> prod promotion.",
        "nexus capture discover",
    ),
    _help_entry(
        "plugins",
        "Everything about the plugin inventory: list, diff, advisories, "
        "drift, impact analysis, AI recommendations. Each subcommand has "
        "its own themed help when run without arguments.",
        "nexus plugins list",
    ),
    _help_entry(
        "reauth",
        "Print the one-shot commands needed to re-authenticate any Claude "
        "MCP server flagged by the local cache. No-op when all servers are "
        "healthy.",
        "nexus reauth",
    ),
    _help_entry(
        "update",
        "Check GitHub Releases for a newer NEXUS version. By default fetches "
        "and installs the wheel via pip; --check-only just reports.",
        "nexus update --check-only",
    ),
    _help_entry(
        "setup",
        "First-run wizard: walks through credentials, registers your first "
        "instance, pulls the initial template catalog. Stub today.",
        "nexus setup",
    ),
    _help_entry(
        "sync",
        "Pull the latest templates from the GitHub registry (stub).",
        "nexus sync",
    ),
    _help_entry(
        "templates",
        "Browse and inspect available templates (stub).",
        "nexus templates",
    ),
    _help_entry(
        "assess",
        "Run an instance health scan or targeted assessment (stub).",
        "nexus assess --for-template incident-tuner",
    ),
    _help_entry(
        "apply <template>",
        "Deploy a template to the configured ServiceNow instance (stub).",
        "nexus apply incident-tuner",
    ),
    _help_entry(
        "run <request>",
        "Free-form AI orchestration request (stub).",
        "nexus run 'reduce P3 incident backlog'",
    ),
    _help_entry(
        "rollback <job_id>",
        "Undo a previous deployment by job ID (stub).",
        "nexus rollback job-1234",
    ),
    _help_entry(
        "ui",
        "Start the NiceGUI dashboard (requires pip install nexus-sn[ui]).",
        "nexus ui",
    ),
]


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    log_level: Annotated[str, typer.Option("--log-level", envvar="NEXUS_LOG_LEVEL")] = "WARNING",
) -> None:
    """NEXUS -- ServiceNow AI architect agent."""
    _configure_logging(log_level)
    check_and_maybe_update()
    if ctx.invoked_subcommand is None:
        console.print(CommandHelp(title="nexus", entry=_NEXUS_PARENT))
        console.print(CommandGuide(app_name="nexus", items=_guide_items(_TOP_LEVEL_HELP)))


@app.command()
def setup() -> None:
    """First-run wizard: configure credentials, instances, and sync templates."""
    console.print("[bold]NEXUS Setup[/bold]")
    console.print("Interactive setup wizard -- not yet implemented.")
    console.print("Configure manually by editing ~/.nexus/config.yaml")


def _detect_tier() -> TierDetection:
    """Run tier detection using a Claude-Code-aware keychain reader."""
    reader = FilesystemClaudeCodeConfigReader(keychain=ExternalKeychainClient())
    return TierDetector(reader=reader).detect()


def _instance_registry() -> InstanceRegistry:
    """Return an InstanceRegistry rooted at the current config path.

    Returns:
        InstanceRegistry for NexusPaths.from_env().instances_dir.
    """
    return InstanceRegistry(NexusPaths.from_env().instances_dir)


def _config_default() -> str:
    """Return the default instance profile from config.

    Returns:
        Profile name string, or empty string if not set.
    """
    return ConfigManager(NexusPaths.from_env()).load().instances.default


def _resolve_profile(profile: str) -> tuple[InstanceRegistry, InstanceMeta]:
    """Resolve an optional profile to a registry and loaded meta.

    Args:
        profile: Profile name, or empty string to use the config default.

    Returns:
        Tuple of (registry, meta) for the resolved profile.

    Raises:
        SystemExit: Via typer.Exit if no default is set or the profile is not found.
    """
    if not profile:
        profile = _config_default()
    if not profile:
        err_console.print("No default instance set.")
        err_console.print("  Register one : nexus instance register <profile>")
        err_console.print("  Set default  : nexus instance use <profile>")
        err_console.print("  List all     : nexus instance")
        raise typer.Exit(1)
    registry = _instance_registry()
    try:
        return registry, registry.load(profile)
    except InstanceNotFoundError as exc:
        err_console.print(str(exc))
        raise typer.Exit(1) from exc


def _oauth_for(profile: str, meta: InstanceMeta) -> SNOAuthClient:
    """Build an SNOAuthClient for a profile and its stored meta.

    Args:
        profile: Instance profile name.
        meta: InstanceMeta loaded from the registry.

    Returns:
        Configured SNOAuthClient.
    """
    return SNOAuthClient(
        profile=profile, url=meta.url, client_id=meta.client_id, username=meta.username
    )


def _set_default_profile(paths: NexusPaths, profile: str) -> None:
    """Persist profile as the default instance in config.

    Args:
        paths: NexusPaths for the current config root.
        profile: Profile name to set as default (empty string to clear).
    """
    manager = ConfigManager(paths)
    manager.save(manager.load().model_copy(update={"instances": InstancesConfig(default=profile)}))


def _parse_buildtag_version(value: str) -> str:
    """Extract the human-readable SN release name from a glide.buildtag value.

    Args:
        value: Raw property value, e.g. ``"glide-xanadu-..."`` or ``"xanadu-..."``.

    Returns:
        Capitalised release name (e.g. ``"Xanadu"``), or the first dash-separated
        token when the value does not start with ``glide-``.
    """
    parts = value.split("-")
    word = parts[1] if parts[0].lower() == "glide" and len(parts) > 1 else parts[0]
    return word.capitalize()


def _detect_sn_version(url: str, token: str, profile: str) -> tuple[str, str, str]:
    """Query sys_properties to detect the SN version, build tag, and instance name.

    Tries glide.buildtag first; falls back to a LIKE search across all
    properties whose name contains 'buildtag' in case the exact key is absent.

    Args:
        url: Full instance URL.
        token: Valid Bearer token.
        profile: Fallback value for instance_name if the property is not found.

    Returns:
        Tuple of (sn_version, sn_build, instance_name). sn_version is
        'unknown' when the buildtag property is missing or unreadable.
    """
    sn_version = "unknown"
    sn_build = ""
    instance_name = profile
    try:
        with httpx.Client(
            base_url=url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=10.0,
        ) as client:
            _BUILDTAG_PROPS = ("glide.buildtag", "glide.buildtag.last")
            for prop in (*_BUILDTAG_PROPS, "instance_name"):
                if prop in _BUILDTAG_PROPS and sn_version != "unknown":
                    continue
                r = client.get(
                    "/api/now/table/sys_properties",
                    params={
                        "sysparm_query": f"name={prop}",
                        "sysparm_fields": "value",
                        "sysparm_limit": 1,
                    },
                )
                log.debug(
                    "version probe name=%s status=%d body=%.200s",
                    prop,
                    r.status_code,
                    r.text,
                )
                if r.status_code != 200:
                    continue
                rows = r.json().get("result", [])
                if not rows:
                    continue
                val = str(rows[0].get("value", "")).strip()
                if not val:
                    continue
                if prop in _BUILDTAG_PROPS:
                    sn_build = val
                    sn_version = _parse_buildtag_version(val)
                else:
                    instance_name = val

            if sn_version == "unknown":
                r = client.get(
                    "/api/now/table/sys_properties",
                    params={
                        "sysparm_query": "nameLIKEbuildtag",
                        "sysparm_fields": "name,value",
                        "sysparm_limit": 3,
                    },
                )
                log.debug("version fallback status=%d body=%.300s", r.status_code, r.text)
                if r.status_code == 200:
                    for row in r.json().get("result", []):
                        val = str(row.get("value", "")).strip()
                        if val:
                            sn_build = val
                            sn_version = _parse_buildtag_version(val)
                            break

            # On many PDIs an ACL blocks reading `glide.buildtag*` via the
            # Table API but `/stats.do` returns the same info as plain text.
            if sn_version == "unknown":
                r = client.get("/stats.do")
                log.debug("stats.do fallback status=%d body=%.300s", r.status_code, r.text[:300])
                if r.status_code == 200 and r.text:
                    sn_build, sn_version = _parse_stats_do(r.text)

    except httpx.RequestError:
        pass
    return sn_version, sn_build, instance_name


def _parse_stats_do(text: str) -> tuple[str, str]:
    """Extract build tag + version from a /stats.do response body.

    ``/stats.do`` returns plain text or HTML with lines like::

        Build tag: glide-yokohama-09-04-2025__patch4-01-22-2026
        Build name: Yokohama

    Args:
        text: Raw response body.

    Returns:
        ``(build_tag, version)`` -- ``("", "unknown")`` when no match found.
    """
    for raw_line in text.splitlines():
        line = raw_line.strip()
        # Match "Build tag:" or "<br/>Build tag:" in HTML-formatted responses.
        if "Build tag:" not in line:
            continue
        val = line.split("Build tag:", 1)[1].strip()
        # Strip trailing HTML breaks / tags
        for sep in ("<br", "</", "&nbsp;"):
            if sep in val:
                val = val.split(sep, 1)[0].strip()
        if val:
            return val, _parse_buildtag_version(val)
    return "", "unknown"


def _print_oauth_setup(url: str, profile: str) -> None:
    """Print step-by-step manual OAuth setup instructions for ServiceNow.

    Args:
        url: Full instance URL, used to build the direct navigation link.
        profile: Profile alias, used as the suggested OAuth app name.
    """
    console.print("")
    console.print("  Manual OAuth setup (one-time, ~2 minutes):")
    console.print("")
    console.print(f"  1. Open {url} and navigate to:")
    console.print("       System OAuth > Application Registry > New")
    console.print("     Choose 'Create an OAuth API endpoint for external clients'")
    console.print("")
    console.print("  2. Fill in:")
    console.print(f"       Name          nexus-{profile}")
    console.print("       Redirect URL   https://localhost  (placeholder, not used)")
    console.print("     Click Submit.")
    console.print("")
    console.print("  3. Open the record you just created:")
    console.print("       Copy the Client ID  (UUID shown at the top of the form)")
    console.print("       Click the lock icon next to Client Secret to reveal it")
    console.print("     Paste both values below.")
    console.print("")


_CAP_PROP = "glide.oauth.access_token.expire_in.system_max_seconds"


def _warn_token_cap(sn: httpx.Client, username: str, password: str) -> None:
    """Print a warning if the SN system access token cap is below 8 hours.

    The property glide.oauth.access_token.expire_in.system_max_seconds overrides
    the token_lifetime on any OAuth application. When it is set below 28800 (8h),
    access tokens expire sooner, but NEXUS auto-refreshes using the 90-day refresh
    token so this does not interrupt the user. The warning tells an admin how to
    raise the cap if they want longer access tokens.

    Args:
        sn: Open httpx.Client bound to the instance base URL.
        username: SN login for Basic auth.
        password: SN password for Basic auth.
    """
    try:
        r = sn.get(
            "/api/now/table/sys_properties",
            params={
                "sysparm_query": f"name={_CAP_PROP}",
                "sysparm_fields": "value",
                "sysparm_limit": "1",
            },
            auth=(username, password),
        )
        if r.status_code != 200:
            return
        rows = r.json().get("result", [])
        if not rows:
            return
        cap = int(rows[0].get("value", "0"))
        if 0 < cap < 28800:
            console.print(f"  Note: SN system cap limits access tokens to {cap // 60} min.")
            console.print("  NEXUS auto-refreshes silently -- this will not interrupt your work.")
            console.print("  To set 8h tokens, an admin can run in a SN background script:")
            console.print(f"    gs.setProperty('{_CAP_PROP}', '28800');")
    except Exception:  # non-fatal -- registration already succeeded
        pass


def _fetch_existing_nexus_oauth_apps(
    url: str, username: str, password: str
) -> list[dict[str, str]]:
    """Return oauth_entity records whose name starts with ``nexus-``.

    Lists OAuth applications already provisioned on the SN instance (e.g. by
    another Nexus install registered against the same instance). Returns ``[]``
    on any failure -- the caller treats that as 'no existing apps'.

    Args:
        url: Full instance URL.
        username: SN login for Basic auth.
        password: SN password for Basic auth.

    Returns:
        Each entry has keys ``name``, ``client_id``, ``sys_id``, ``sys_created_on``.
        Entries without a ``client_id`` are dropped.
    """
    try:
        with httpx.Client(base_url=url, timeout=10.0) as sn:
            resp = sn.get(
                "/api/now/table/oauth_entity",
                params={
                    "sysparm_query": "nameSTARTSWITHnexus-",
                    "sysparm_fields": "name,client_id,sys_id,sys_created_on",
                    "sysparm_limit": "100",
                },
                auth=(username, password),
            )
        if resp.status_code != 200:
            return []
        rows = resp.json().get("result", [])
        return [
            {
                "name": str(r.get("name", "")),
                "client_id": str(r.get("client_id", "")),
                "sys_id": str(r.get("sys_id", "")),
                "sys_created_on": str(r.get("sys_created_on", "")),
            }
            for r in rows
            if r.get("client_id")
        ]
    except httpx.RequestError, ValueError:
        return []


def _print_generated_secret(secret: str) -> None:
    """Print a freshly-generated OAuth client_secret with save-it instructions.

    ServiceNow stores ``client_secret`` as a ``password2`` field, so the value
    we just POSTed is the last time it will be readable. The user must save it
    somewhere durable (password manager) before continuing; otherwise reusing
    this OAuth app from another machine requires either re-rotating the secret
    or running the background-script recovery recipe.

    Args:
        secret: The cleartext client_secret we just provisioned.
    """
    console.print("")
    console.print(Notice.warn("Save this client secret -- ServiceNow will mask it after now."))
    console.print(f"    Client secret: {secret}")
    console.print(
        "    Store it in your password manager so you can register this same "
        "OAuth app from other machines."
    )
    console.print("")


def _print_secret_recovery_steps(url: str, sys_id: str, name: str) -> None:
    """Print copy-paste instructions for retrieving an existing OAuth secret.

    ServiceNow stores ``oauth_entity.client_secret`` as a ``password2`` (encrypted)
    field and the Table API masks it on every GET, by design. The only way to
    read the cleartext is via a server-side script context that can call
    ``GlideElement.getDecryptedValue()`` -- typically a background script.

    Args:
        url: Full instance URL.
        sys_id: ``oauth_entity.sys_id`` of the picked app.
        name: OAuth app name (e.g. ``nexus-prod``), shown for visual context.
    """
    console.print("")
    console.print(
        f"  ServiceNow does not return client secrets via REST. To recover the "
        f"secret for '{name}', run this in your SN instance:"
    )
    console.print("")
    console.print(f"    1. Open  {url}/sys.scripts.do  (System Definition > Scripts - Background).")
    console.print("    2. Paste this script and click Run script:")
    console.print("")
    console.print("       var gr = new GlideRecord('oauth_entity');")
    console.print(f"       gr.get('{sys_id}');")
    console.print("       gs.print(gr.client_secret.getDecryptedValue());")
    console.print("")
    console.print("    3. Copy the line printed below '*** Script:' and paste it here.")
    console.print("")


def _pick_existing_oauth_app(
    entries: list[dict[str, str]], profile: str, url: str
) -> tuple[str, str] | None:
    """Prompt the user to reuse an existing Nexus OAuth app or create a new one.

    The client_secret is not retrievable from ServiceNow (the Table API masks
    password2 fields), so the user must either paste it from another Nexus
    install or run the background-script recipe printed below the prompt.

    Args:
        entries: Output of ``_fetch_existing_nexus_oauth_apps``. Must be non-empty.
        profile: Profile being registered -- shown in the "create new" option.
        url: Full instance URL, used to build the Scripts - Background link.

    Returns:
        ``(client_id, client_secret)`` if the user picks an existing entry and
        supplies the secret, or ``None`` if they choose to create a new app.
    """
    console.print("")
    console.print(f"  Found {len(entries)} existing Nexus OAuth app(s) on this instance:")
    for i, entry in enumerate(entries, 1):
        console.print(
            f"    {i}. {entry['name']}  "
            f"(client_id={entry['client_id']}, created {entry['sys_created_on']})"
        )
    console.print(f"    n. Create a new app named 'nexus-{profile}'")
    console.print("")
    raw: str = typer.prompt(f"  Pick one (1-{len(entries)}) or 'n' for new")
    choice = raw.strip().lower()
    if choice == "n":
        return None
    try:
        idx = int(choice)
    except ValueError:
        console.print(f"  Invalid choice {raw!r}; will create a new app.")
        return None
    if not 1 <= idx <= len(entries):
        console.print(f"  Choice {idx} out of range; will create a new app.")
        return None
    picked = entries[idx - 1]
    console.print(f"  Reusing OAuth app '{picked['name']}' (client_id={picked['client_id']}).")
    _print_secret_recovery_steps(url=url, sys_id=picked["sys_id"], name=picked["name"])
    secret: str = typer.prompt("  OAuth Client Secret", hide_input=True)
    return picked["client_id"], secret


def _provision_oauth(url: str, profile: str, username: str, password: str) -> tuple[str, str]:
    """Reuse or auto-create an OAuth app in SN; fall back to manual prompts on failure.

    First queries the instance for any existing ``nexus-*`` OAuth apps and, if
    found, offers to reuse one (prompting the user for its client_secret since
    SN won't return it). If the user declines or no entry is found, POSTs a new
    record to the oauth_entity Table API using HTTP Basic auth. On any failure
    the user is shown setup instructions and prompted to enter the credentials
    manually.

    Args:
        url: Full instance URL.
        profile: Profile alias used as the OAuth app name suffix.
        username: SN login for Basic auth.
        password: SN password for Basic auth.

    Returns:
        Tuple of (client_id, client_secret).
    """
    existing = _fetch_existing_nexus_oauth_apps(url, username, password)
    if existing:
        picked = _pick_existing_oauth_app(existing, profile, url)
        if picked is not None:
            return picked

    generated_secret = str(uuid.uuid4())
    fail_reason = ""
    try:
        with httpx.Client(base_url=url, timeout=10.0) as sn:
            resp = sn.post(
                "/api/now/table/oauth_entity",
                json={
                    "name": f"nexus-{profile}",
                    "type": "oauth2",
                    "client_secret": generated_secret,
                    "redirect_url": "https://localhost",
                    "token_lifetime": "28800",  # 8h -- may be overridden by SN system cap
                    "refresh_token_lifetime": "7776000",  # 90 days -- survives access token cap
                },
                auth=(username, password),
            )
            if resp.status_code == 201:
                result = resp.json().get("result", {})
                client_id = str(result.get("client_id", ""))
                if client_id:
                    console.print(f"  Created OAuth application 'nexus-{profile}' automatically.")
                    _print_generated_secret(generated_secret)
                    _warn_token_cap(sn, username, password)
                    return client_id, generated_secret
                fail_reason = "HTTP 201 but no client_id in response"
            else:
                fail_reason = f"HTTP {resp.status_code}"
    except httpx.RequestError as exc:
        fail_reason = str(exc)

    console.print(f"  Could not auto-create OAuth credentials ({fail_reason}).")
    _print_oauth_setup(url, profile)
    client_id = typer.prompt("  OAuth Client ID")
    client_secret: str = typer.prompt("  OAuth Client Secret", hide_input=True)
    return client_id, client_secret


def _acquire_token(
    profile: str,
) -> tuple[InstanceRegistry, InstanceMeta, str, datetime]:
    """Resolve profile, acquire bearer token, reconnecting automatically if expired.

    When both the access token and refresh token are expired, prompts the user
    for their ServiceNow password and re-authenticates transparently so the
    caller can continue without manual intervention.

    Args:
        profile: Instance profile name (empty string uses config default).

    Returns:
        (registry, meta, bearer_token, token_expiry)
    """
    registry, meta = _resolve_profile(profile)
    oauth = _oauth_for(meta.profile, meta)
    try:
        token, expiry = oauth.get_bearer_token(meta.token_expires_at)
        # Persist the refreshed expiry so nexus instance list shows the correct status.
        if expiry != meta.token_expires_at:
            registry.save(meta.model_copy(update={"token_expires_at": expiry}))
        return registry, meta, token, expiry
    except TokenExpiredError:
        console.print(f"Session expired for {meta.profile!r}. Reconnecting...")
    try:
        password: str = typer.prompt("ServiceNow password", hide_input=True)
        token, expiry = oauth.reconnect(password)
    except OAuthError as exc:
        err_console.print(f"Reconnect failed: {exc}")
        raise typer.Exit(1) from exc
    registry.save(meta.model_copy(update={"token_expires_at": expiry}))
    console.print(f"Reconnected. Token valid until {expiry.strftime('%H:%M UTC')}.")
    return registry, meta, token, expiry


def _build_capture_engine(profile: str) -> tuple[CaptureEngine, ServiceNowClient]:
    """Build a CaptureEngine for the given registered instance profile.

    Args:
        profile: Instance profile name from InstanceRegistry.

    Returns:
        Tuple of (CaptureEngine, ServiceNowClient) for the caller to use.

    Raises:
        typer.Exit: With code 1 if the profile is not registered or expired.
    """
    _, meta, token, _ = _acquire_token(profile)
    client = ServiceNowClient(instance_url=meta.url, token=token)
    engine = CaptureEngine(client=client, archive_root=NexusPaths.from_env().archives_dir)
    return engine, client


_INSTANCE_HELP: list[CommandHelpEntry] = [
    _help_entry(
        "register <profile>",
        "Add a new SN instance and store its credentials in the OS keychain. "
        "Interactive: prompts for URL, username, password. OAuth app is "
        "auto-provisioned via the SN REST API -- no manual config needed.",
        "nexus instance register prod",
    ),
    _help_entry(
        "connect [profile]",
        "Verify the OAuth access token is still valid; refresh it via the "
        "refresh-token grant if near expiry. Run before any command that "
        "talks to SN if you're unsure the token is still live.",
        "nexus instance connect prod",
    ),
    _help_entry(
        "refresh [profile]",
        "Pull a fresh artifact + plugin inventory from SN and replace the "
        "cached snapshot on disk. Required before drift, advisories, or "
        "updates commands give meaningful answers.",
        "nexus instance refresh prod",
    ),
    _help_entry(
        "status [profile]",
        "Show metadata + the latest snapshot summary for one instance: SN "
        "version, token expiry, artifact / plugin counts, last refresh time.",
        "nexus instance status prod",
    ),
    _help_entry(
        "use [profile]",
        "Set the default instance used when --instance is omitted. With no "
        "argument, opens an interactive picker (or auto-promotes when only "
        "one instance is registered).",
        "nexus instance use prod",
    ),
    _help_entry(
        "delete <profile>",
        "Permanently remove a profile and its keychain credentials. If the "
        "deleted profile was the default and exactly one other instance "
        "remains, the survivor is promoted automatically.",
        "nexus instance delete dev --force",
    ),
    _help_entry(
        "list",
        "Tabular view of every registered instance with profile name, URL, "
        "SN version, token state (valid / EXPIRED / N min left), and last "
        "successful connection time. Default instance marked with '*'.",
        "nexus instance list",
    ),
]


@instance_app.callback(invoke_without_command=True)
def instance_callback(ctx: typer.Context) -> None:
    """Show registered instances and available commands."""
    if ctx.invoked_subcommand is not None:
        return

    if not _instance_registry().list_all():
        console.print()
        console.print(
            Hint(
                label="Get started",
                command="nexus instance register dev",
                suffix="(you will be prompted for URL, username, password)",
            )
        )
        console.print()
    else:
        instance_list()

    console.print(CommandHelp(title="nexus instance", entry=_INSTANCE_PARENT))
    console.print(CommandGuide(app_name="nexus instance", items=_guide_items(_INSTANCE_HELP)))


@instance_app.command("list")
def instance_list() -> None:
    """Show all registered ServiceNow instances."""
    registry = _instance_registry()
    metas = registry.list_all()
    if not metas:
        console.print(
            Hint(
                label="No instances registered",
                command="nexus instance register <profile>",
            )
        )
        return

    default = _config_default()
    rows: list[list[RenderableType]] = []
    for meta in metas:
        profile_cell = Text()
        if meta.profile == default:
            profile_cell.append_text(default_marker())
        else:
            profile_cell.append("  ")
        profile_cell.append(meta.profile)
        rows.append(
            [
                profile_cell,
                _trunc(meta.url.replace("https://", ""), 36),
                meta.sn_version,
                token_badge(meta),
                meta.last_connected_at.strftime("%Y-%m-%d %H:%M"),
            ]
        )
    console.print(
        DataTable(
            title="Instances",
            columns=[
                DataColumn(header="Profile", width=14),
                DataColumn(header="URL", width=30),
                DataColumn(header="Version", width=9),
                DataColumn(header="Token", width=14),
                DataColumn(header="Connected", width=17),
            ],
            rows=rows,
        )
    )


@instance_app.command("status")
def instance_status(profile: str = typer.Argument("")) -> None:
    """Show metadata and snapshot summary for an instance."""
    registry, meta = _resolve_profile(profile)

    console.print()
    console.print(
        KeyValuePanel(
            title="Instance",
            rows=[
                KvRow(label="Instance", value=meta.profile),
                KvRow(label="URL", value=meta.url),
                KvRow(label="Version", value=meta.sn_version),
                KvRow(label="Token", value=token_badge(meta)),
                KvRow(
                    label="Connected",
                    value=meta.last_connected_at.strftime("%Y-%m-%d %H:%M UTC"),
                ),
            ],
        )
    )

    snapshot = registry.load_snapshot(meta.profile)
    if snapshot is None:
        console.print()
        console.print(
            Hint(label="No snapshot", command="nexus instance refresh", suffix="to capture one")
        )
        return

    c = snapshot.counts
    custom_flows = sum(1 for f in snapshot.flows if f.is_custom)
    custom_brs = sum(1 for r in snapshot.business_rules if r.is_custom)
    custom_sis = sum(1 for s in snapshot.script_includes if s.is_custom)
    console.print()
    console.print(
        KeyValuePanel(
            title="Snapshot",
            rows=[
                KvRow(
                    label="Captured",
                    value=snapshot.captured_at.strftime("%Y-%m-%d %H:%M UTC"),
                ),
                KvRow(label="AI Skills", value=str(c.ai_skills)),
                KvRow(label="Flows", value=f"{c.flows} ({custom_flows} custom)"),
                KvRow(
                    label="Business Rules",
                    value=f"{c.business_rules} ({custom_brs} custom)",
                ),
                KvRow(
                    label="Script Includes",
                    value=f"{c.script_includes} ({custom_sis} custom)",
                ),
            ],
        )
    )


@instance_app.command("delete")
def instance_delete(
    profile: Annotated[str, typer.Argument(help="Instance profile to delete")],
    force: Annotated[bool, typer.Option("--force", help="Skip confirmation")] = False,
) -> None:
    """Remove a registered instance and its keychain entries."""
    if not force:
        if not typer.confirm(f"Delete instance {profile!r} and all its data?"):
            raise typer.Abort()

    registry, meta = _resolve_profile(profile)
    _oauth_for(profile, meta).delete_tokens()
    registry.delete(meta.profile)

    paths = NexusPaths.from_env()
    manager = ConfigManager(paths)
    cfg = manager.load()
    if cfg.instances.default == profile:
        remaining = registry.list_all()
        if len(remaining) == 1:
            # Exactly one instance left -- promote it automatically so the
            # user never has to think about a default again.
            survivor = remaining[0].profile
            _set_default_profile(paths, survivor)
            console.print(Notice.info(f"Default instance promoted to {survivor!r}."))
        else:
            manager.save(cfg.model_copy(update={"instances": InstancesConfig(default="")}))
            if remaining:
                console.print(
                    Notice.warn(
                        f"Default instance cleared. {len(remaining)} instances remain -- "
                        f"pick one with 'nexus instance use <profile>'."
                    )
                )

    console.print(Notice.info(f"Deleted instance {profile!r}."))


@instance_app.command("use")
def instance_use(
    profile: Annotated[str, typer.Argument(help="Instance profile to set as default")] = "",
) -> None:
    """Set the default instance (interactive picker when invoked with no profile)."""
    if not profile:
        registered = _instance_registry().list_all()
        if not registered:
            err_console.print(Notice.error("No instances registered."))
            console.print(Hint(label="Register one", command="nexus instance register dev"))
            raise typer.Exit(1)
        if len(registered) == 1:
            profile = registered[0].profile
            console.print(
                Notice.info(f"Only one instance registered; setting {profile!r} as default.")
            )
        else:
            current_default = _config_default()
            console.print(Notice.info("Multiple instances registered. Pick a default:"))
            for i, meta in enumerate(registered, start=1):
                marker = "*" if meta.profile == current_default else " "
                console.print(f"  {marker} {i}. {meta.profile}  ({meta.url})")
            try:
                raw_choice: object = typer.prompt("Enter number", type=int)
            except typer.Abort:
                raise typer.Exit(1) from None
            choice = int(raw_choice) if isinstance(raw_choice, int | str) else 0
            if choice < 1 or choice > len(registered):
                err_console.print(Notice.error(f"Invalid choice: {choice}"))
                raise typer.Exit(1)
            profile = registered[choice - 1].profile
    _resolve_profile(profile)
    _set_default_profile(NexusPaths.from_env(), profile)
    console.print(Notice.info(f"Default instance set to {profile!r}."))


@instance_app.command("connect")
def instance_connect(profile: str = typer.Argument("")) -> None:
    """Verify connectivity and refresh token if near expiry."""
    registry, meta, token, new_expiry = _acquire_token(profile)
    profile = meta.profile

    try:
        with httpx.Client(
            base_url=meta.url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=10.0,
        ) as client:
            resp = client.get("/api/now/table/sys_properties", params={"sysparm_limit": 1})
        if resp.status_code != 200:
            err_console.print(Notice.error(f"Probe failed: HTTP {resp.status_code}"))
            raise typer.Exit(1)
    except httpx.RequestError as exc:
        err_console.print(Notice.error(f"Cannot reach {meta.url}: {exc}"))
        raise typer.Exit(1) from exc

    now = datetime.now(UTC)
    sn_version, sn_build, instance_name = _detect_sn_version(meta.url, token, meta.profile)
    update: dict[str, object] = {"last_connected_at": now, "token_expires_at": new_expiry}
    if sn_version != "unknown":
        update["sn_version"] = sn_version
        update["sn_build"] = sn_build
        update["instance_name"] = instance_name
    registry.save(meta.model_copy(update=update))
    console.print(
        Notice.info(
            f"Connected to {profile!r}. Token valid until {new_expiry.strftime('%H:%M UTC')}."
        )
    )


@instance_app.command("refresh")
def instance_refresh(
    profile: str = typer.Argument(""),
    no_counts: Annotated[
        bool,
        typer.Option(
            "--no-counts",
            help="Skip per-plugin record-count capture for a faster refresh.",
        ),
    ] = False,
) -> None:
    """Pull a fresh artifact snapshot from the instance."""
    registry, meta, token, new_expiry = _acquire_token(profile)
    profile = meta.profile

    console.print(Notice.info(f"Capturing snapshot from {profile!r}..."))

    async def _run() -> tuple[InstanceSnapshot, PluginInventory | None]:
        scanner = InstanceScanner()
        plugin_scanner = PluginScanner()
        snapshot_task = scanner.scan(meta.url, token, meta.sn_version)
        plugin_task = plugin_scanner.scan(
            meta.url, token, meta.sn_version, capture_counts=not no_counts
        )
        results = await asyncio.gather(snapshot_task, plugin_task, return_exceptions=True)
        snap_result, plugin_result = results
        if isinstance(snap_result, BaseException):
            raise snap_result
        if isinstance(plugin_result, PluginScanError):
            err_console.print(Notice.warn(f"Plugin scan failed: {plugin_result}"))
            return snap_result, None
        if isinstance(plugin_result, BaseException):
            raise plugin_result
        return snap_result, plugin_result

    try:
        snapshot, plugin_inventory = asyncio.run(_run())
    except SnapshotError as exc:
        err_console.print(Notice.error(str(exc)))
        raise typer.Exit(1) from exc

    registry.save_snapshot(profile, snapshot)
    if plugin_inventory is not None:
        registry.save_plugin_inventory(profile, plugin_inventory)
    c = snapshot.counts
    plugin_count = len(plugin_inventory.plugins) if plugin_inventory else 0
    counts = c.model_copy(update={"plugins": plugin_count})
    registry.save(
        meta.model_copy(update={"token_expires_at": new_expiry, "snapshot_counts": counts})
    )
    console.print(
        Notice.info(
            f"Snapshot captured: {c.ai_skills} AI skills, {c.flows} flows, "
            f"{c.business_rules} business rules, {c.script_includes} script includes."
        )
    )


@instance_app.command("register")
def instance_register(
    profile: Annotated[str, typer.Argument(help="Profile name to register")],
) -> None:
    """Interactive wizard to register a new ServiceNow instance via OAuth2."""
    paths = NexusPaths.from_env()
    if (paths.instances_dir / profile).exists():
        err_console.print(
            Notice.error(
                f"Profile {profile!r} already exists. "
                f"Delete it first with 'nexus instance delete {profile}'."
            )
        )
        raise typer.Exit(1)

    console.print(f"Registering instance '{profile}'")
    console.print(f"  '{profile}' is your local alias -- use it in all nexus instance commands.")
    console.print("")
    raw_url: str = typer.prompt("  Instance (subdomain, FQDN, or https:// URL -- e.g. dev12345)")
    host = raw_url.removeprefix("https://").removeprefix("http://").rstrip("/")
    if "." not in host:
        host = f"{host}.service-now.com"
    url = f"https://{host}"
    username: str = typer.prompt("  Username")
    password: str = typer.prompt("  Password", hide_input=True)

    client_id, client_secret = _provision_oauth(url, profile, username, password)

    console.print("  Exchanging credentials for OAuth token...")
    oauth = SNOAuthClient(profile=profile, url=url, client_id=client_id, username=username)
    try:
        token_response = oauth.exchange(client_secret, password)
    except OAuthError as exc:
        err_console.print(Notice.error(str(exc)))
        raise typer.Exit(1) from exc

    sn_version, sn_build, instance_name = _detect_sn_version(
        url, token_response.access_token, profile
    )
    if sn_version == "unknown":
        console.print(
            Notice.warn(
                "Version: unknown (glide.buildtag not in sys_properties -- "
                "run with --log-level DEBUG to diagnose)"
            )
        )

    registry = InstanceRegistry(paths.instances_dir)
    meta = InstanceMeta.create(
        profile=profile,
        url=url,
        username=username,
        client_id=client_id,
        sn_version=sn_version,
        sn_build=sn_build,
        instance_name=instance_name,
        token_expires_in=token_response.expires_in,
    )
    registry.register(meta)
    console.print(Notice.info(f"Registered {profile} ({sn_version})."))

    if not ConfigManager(paths).load().instances.default:
        _set_default_profile(paths, profile)
        console.print(Notice.info("Set as default instance."))


def _plugins_for(profile: str) -> tuple[InstanceMeta, PluginInventory] | None:
    """Resolve a profile and return its plugin inventory, or None when missing.

    Args:
        profile: Instance profile name, or empty string to use the config default.

    Returns:
        Tuple of (meta, inventory) when an inventory exists, or ``None`` when the
        instance has no captured ``plugins.json``.
    """
    registry, meta = _resolve_profile(profile)
    inv = registry.load_plugin_inventory(meta.profile)
    if inv is None:
        return None
    return meta, inv


def _dependencies_panel(deps: tuple[DependencyEntry, ...], plugin_id: str) -> DataTable:
    """Render an SN dependency cascade as a DataTable.

    Args:
        deps: Dependency entries from fetch_dependencies.
        plugin_id: The target plugin id (shown in title).

    Returns:
        DataTable suitable for console.print().
    """
    rows: list[list[RenderableType]] = [
        [d.id, d.status, "yes" if d.active else "no", d.min_version] for d in deps
    ]
    return DataTable(
        title=f"Dependency cascade for {plugin_id}",
        columns=[
            DataColumn(header="Plugin", width=36),
            DataColumn(header="Status", width=20),
            DataColumn(header="Active", width=8),
            DataColumn(header="Min Version", width=14),
        ],
        rows=rows,
    )


def _result_panel(result: OperationResult) -> KeyValuePanel:
    """Render an OperationResult as a KeyValuePanel.

    Args:
        result: The OperationResult returned by PluginExecutor.

    Returns:
        KeyValuePanel suitable for console.print().
    """
    status_text = "success" if result.success else "failed"
    return KeyValuePanel(
        title=f"{result.action} {result.plugin_id}",
        rows=[
            KvRow(label="Status", value=status_text),
            KvRow(label="Tracker", value=result.tracker_id or "-"),
            KvRow(label="Duration", value=f"{result.duration_s:.1f}s"),
            KvRow(label="Update set", value=result.update_set or "-"),
            KvRow(label="Rollback version", value=result.rollback_version or "-"),
            KvRow(label="Message", value=result.message or "-"),
        ],
    )


@plugins_app.callback(invoke_without_command=True)
def plugins_callback(ctx: typer.Context) -> None:
    """Show the plugin inventory and the available subcommands."""
    if ctx.invoked_subcommand is not None:
        return
    console.print(CommandHelp(title="nexus plugins", entry=_PLUGINS_PARENT))
    console.print(CommandGuide(app_name="nexus plugins", items=_guide_items(_PLUGINS_HELP)))


@plugins_app.command("list")
def plugins_list(
    instance: Annotated[
        str,
        typer.Option("--instance", help="Instance profile (default: configured default)"),
    ] = "",
    product: Annotated[
        str, typer.Option("--product", help="Filter by product family (e.g. ITSM)")
    ] = "",
    source: Annotated[
        str, typer.Option("--source", help="Filter by source (servicenow|store|custom)")
    ] = "",
    state: Annotated[str, typer.Option("--state", help="Filter by state (active|inactive)")] = "",
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: text | json (default: text)"),
    ] = "text",
) -> None:
    """Show all plugins installed on the resolved instance."""
    _validate_format(output_format)
    resolved = _plugins_for(instance)
    if resolved is None:
        console.print(Notice.warn("Plugin inventory empty."))
        console.print(Hint(label="Refresh", command="nexus instance refresh"))
        return
    _, inv = resolved
    plugins = inv.plugins
    if product:
        plugins = tuple(p for p in plugins if p.product_family == product)
    if source:
        plugins = tuple(p for p in plugins if p.source == source)
    if state:
        plugins = tuple(p for p in plugins if p.state == state)
    if output_format == "json":
        _emit_json(inv.model_copy(update={"plugins": tuple(plugins)}))
        return
    if not plugins:
        console.print(Notice.info("No plugins match the requested filters."))
        return
    rows: list[list[RenderableType]] = [
        [
            p.plugin_id,
            p.name,
            p.version,
            StatusBadge.ok(p.state) if p.state == "active" else StatusBadge.warn(p.state),
            p.source,
            p.product_family,
        ]
        for p in sorted(plugins, key=lambda x: (x.product_family, x.plugin_id))
    ]
    console.print(
        DataTable(
            title="Plugins",
            columns=[
                DataColumn(header="Plugin ID", width=32),
                DataColumn(header="Name", width=24),
                DataColumn(header="Version", width=10),
                DataColumn(header="State", width=10),
                DataColumn(header="Source", width=11),
                DataColumn(header="Product", width=14),
            ],
            rows=rows,
        )
    )


@plugins_app.command("info")
def plugins_info(
    plugin_id: Annotated[str, typer.Argument(help="SN plugin identifier (e.g. com.snc.incident)")],
    instance: Annotated[
        str, typer.Option("--instance", help="Instance profile (default: configured default)")
    ] = "",
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: text | json (default: text)"),
    ] = "text",
) -> None:
    """Show full details and direct dependencies for one plugin."""
    _validate_format(output_format)
    resolved = _plugins_for(instance)
    if resolved is None:
        console.print(Notice.warn("Plugin inventory empty."))
        console.print(Hint(label="Refresh", command="nexus instance refresh"))
        raise typer.Exit(1)
    _, inv = resolved
    plugins = inv.plugins
    plugin = next((p for p in plugins if p.plugin_id == plugin_id), None)
    if plugin is None:
        err_console.print(Notice.error(f"Plugin {plugin_id!r} not found in inventory."))
        raise typer.Exit(1)
    if output_format == "json":
        _emit_json(plugin)
        return
    console.print(
        KeyValuePanel(
            title=plugin.name,
            rows=[
                KvRow(label="Plugin ID", value=plugin.plugin_id),
                KvRow(label="Version", value=plugin.version),
                KvRow(
                    label="State",
                    value=(
                        StatusBadge.ok(plugin.state)
                        if plugin.state == "active"
                        else StatusBadge.warn(plugin.state)
                    ),
                ),
                KvRow(label="Source", value=plugin.source),
                KvRow(label="Product family", value=plugin.product_family),
                KvRow(label="sys_id", value=plugin.sys_id),
                KvRow(
                    label="Installed at",
                    value=(
                        plugin.installed_at.strftime("%Y-%m-%d %H:%M UTC")
                        if plugin.installed_at
                        else "-"
                    ),
                ),
            ],
        )
    )
    if plugin.depends_on:
        console.print(
            Hint(
                label="Depends on",
                command=", ".join(plugin.depends_on),
            )
        )


_PLUGIN_CSV_FIELDS = (
    "plugin_id",
    "name",
    "version",
    "state",
    "source",
    "product_family",
    "sys_id",
    "installed_at",
)


@plugins_app.command("export")
def plugins_export(
    instance: Annotated[
        str, typer.Option("--instance", help="Instance profile (default: configured default)")
    ] = "",
    fmt: Annotated[str, typer.Option("--format", help="Output format (yaml|csv)")] = "yaml",
    out: Annotated[
        str, typer.Option("--out", help="Output file path (default: plugins.<ext>)")
    ] = "",
) -> None:
    """Write the plugin inventory to a YAML or CSV file."""
    if fmt not in ("yaml", "csv"):
        err_console.print(Notice.error(f"Unknown format {fmt!r}; use yaml or csv."))
        raise typer.Exit(1)
    resolved = _plugins_for(instance)
    if resolved is None:
        console.print(Notice.warn("Plugin inventory empty."))
        console.print(Hint(label="Refresh", command="nexus instance refresh"))
        raise typer.Exit(1)
    _, inv = resolved
    plugins = inv.plugins
    path = Path(out) if out else Path(f"plugins.{fmt}")
    if fmt == "yaml":
        payload = {
            "plugins": [
                {
                    field: (
                        (p.installed_at.isoformat() if p.installed_at else None)
                        if field == "installed_at"
                        else getattr(p, field)
                    )
                    for field in _PLUGIN_CSV_FIELDS
                }
                for p in plugins
            ]
        }
        path.write_text(_yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    else:
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(_PLUGIN_CSV_FIELDS)
            for p in plugins:
                writer.writerow(
                    [
                        p.plugin_id,
                        p.name,
                        p.version,
                        p.state,
                        p.source,
                        p.product_family,
                        p.sys_id,
                        p.installed_at.isoformat() if p.installed_at else "",
                    ]
                )
    console.print(Notice.info(f"Wrote {len(plugins)} plugins to {path}"))


def _diff_status_badge(status: str) -> StatusBadge:
    """Return a StatusBadge for a PluginDiffEntry.status value.

    Args:
        status: One of ``only_in_a``, ``only_in_b``, ``version_mismatch``,
            or ``state_mismatch``.

    Returns:
        StatusBadge styled per the status category.
    """
    if status == "version_mismatch":
        return StatusBadge.error(status)
    if status == "state_mismatch":
        return StatusBadge.ok(status)
    return StatusBadge.warn(status)


def _drift_status_badge(status: str) -> StatusBadge:
    """Return a StatusBadge for a PluginDriftEntry.status value.

    Args:
        status: One of ``added``, ``removed``, ``version_changed``,
            or ``state_changed``.

    Returns:
        StatusBadge styled per the status category.
    """
    if status == "added":
        return StatusBadge.ok(status)
    return StatusBadge.warn(status)


def _status_breakdown(statuses: Iterable[str], label: str) -> str:
    """Format a count-by-status summary line for trailing Notice rendering.

    Args:
        statuses: Iterable of status strings (one per entry).
        label: Singular noun for the entry kind (e.g. ``"difference"``).

    Returns:
        ``"N <label>(s): k1 status1, k2 status2, ..."``, omitting zero counts.
    """
    counts: Counter[str] = Counter(statuses)
    total = sum(counts.values())
    breakdown = ", ".join(f"{n} {k}" for k, n in counts.items() if n)
    return f"{total} {label}(s): {breakdown}"


def _load_inventory_or_exit(profile: str) -> tuple[InstanceMeta, PluginInventory]:
    """Resolve a profile and load its plugin inventory, exiting with a Hint when empty.

    Args:
        profile: Profile name to resolve.

    Returns:
        Tuple of (meta, inventory) once the inventory is loaded.

    Raises:
        typer.Exit: When the profile has no captured plugin inventory.
    """
    registry, meta = _resolve_profile(profile)
    inv = registry.load_plugin_inventory(meta.profile)
    if inv is None:
        console.print(Notice.warn(f"Plugin inventory empty for {meta.profile!r}."))
        console.print(Hint(label="Refresh", command=f"nexus instance refresh {meta.profile}"))
        raise typer.Exit(1)
    return meta, inv


@plugins_app.command("diff")
def plugins_diff(
    profile_a: Annotated[str, typer.Argument(help="First profile")],
    profile_b: Annotated[str, typer.Argument(help="Second profile")],
    status: Annotated[
        str,
        typer.Option(
            "--status",
            help="Filter by status (only_in_a|only_in_b|version_mismatch|state_mismatch)",
        ),
    ] = "",
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: text | json (default: text)"),
    ] = "text",
) -> None:
    """Show cross-instance plugin differences."""
    _validate_format(output_format)
    meta_a, inv_a = _load_inventory_or_exit(profile_a)
    meta_b, inv_b = _load_inventory_or_exit(profile_b)
    diff: PluginDiff = compute_diff(inv_a, inv_b, meta_a.profile, meta_b.profile)
    entries: tuple[PluginDiffEntry, ...] = diff.entries
    if status:
        entries = tuple(e for e in entries if e.status == status)

    if output_format == "json":
        _emit_json(diff.model_copy(update={"entries": entries}))
        return

    if not entries:
        console.print(Notice.info("No differences found."))
        return
    rows: list[list[RenderableType]] = [
        [
            e.plugin_id,
            e.name,
            e.product_family,
            _diff_status_badge(e.status),
            e.a_version or "-",
            e.b_version or "-",
            e.a_state or "-",
            e.b_state or "-",
        ]
        for e in entries
    ]
    console.print(
        DataTable(
            title=f"Plugins: {meta_a.profile} vs {meta_b.profile}",
            columns=[
                DataColumn(header="Plugin ID", width=32),
                DataColumn(header="Name", width=20),
                DataColumn(header="Product", width=14),
                DataColumn(header="Status", width=18),
                DataColumn(header="A version", width=10),
                DataColumn(header="B version", width=10),
                DataColumn(header="A state", width=9),
                DataColumn(header="B state", width=9),
            ],
            rows=rows,
        )
    )
    console.print(Notice.info(_status_breakdown((e.status for e in entries), "difference")))


def _promote_payload(plan: PromotionPlan) -> dict[str, object]:
    """Serialise a PromotionPlan into the YAML payload shape."""
    bucket: dict[str, list[dict[str, object]]] = {
        "install": [],
        "activate": [],
        "upgrade": [],
    }
    for action in plan.actions:
        row: dict[str, object] = {
            "plugin_id": action.plugin_id,
            "name": action.name,
            "product_family": action.product_family,
            "target_version": action.target_version,
        }
        if action.current_version is not None:
            row["current_version"] = action.current_version
        bucket[action.action].append(row)
    return {
        "source_profile": plan.source_profile,
        "target_profile": plan.target_profile,
        "actions": bucket,
    }


@plugins_app.command("promote")
def plugins_promote(
    source: Annotated[str, typer.Argument(help="Source profile")],
    target: Annotated[
        str, typer.Option("--to", help="Target profile to bring up to match source.")
    ] = "",
    out: Annotated[
        str,
        typer.Option(
            "--out",
            help="Output YAML file (default: promote-<src>-to-<dst>.yaml)",
        ),
    ] = "",
) -> None:
    """Write an additive action plan to make <target> match <source>."""
    if source == target:
        err_console.print(
            Notice.error("Source and target are the same profile; nothing to promote.")
        )
        raise typer.Exit(1)
    meta_src, inv_src = _load_inventory_or_exit(source)
    meta_dst, inv_dst = _load_inventory_or_exit(target)
    diff = compute_diff(inv_src, inv_dst, meta_src.profile, meta_dst.profile)
    plan = project_to_promote_plan(diff)
    if not plan.actions:
        console.print(
            Notice.info(
                f"Target {meta_dst.profile!r} already matches "
                f"{meta_src.profile!r}. No actions written."
            )
        )
        return
    path = Path(out) if out else Path(f"promote-{meta_src.profile}-to-{meta_dst.profile}.yaml")
    payload = _promote_payload(plan)
    path.write_text(_yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    counts: dict[str, int] = {"install": 0, "activate": 0, "upgrade": 0}
    for action in plan.actions:
        counts[action.action] += 1
    console.print(
        KeyValuePanel(
            title="Promotion plan",
            rows=[
                KvRow(
                    label="Source",
                    value=(
                        f"{meta_src.profile} "
                        f"(captured {inv_src.captured_at.strftime('%Y-%m-%d %H:%M UTC')})"
                    ),
                ),
                KvRow(
                    label="Target",
                    value=(
                        f"{meta_dst.profile} "
                        f"(captured {inv_dst.captured_at.strftime('%Y-%m-%d %H:%M UTC')})"
                    ),
                ),
                KvRow(label="Install", value=str(counts["install"])),
                KvRow(label="Activate", value=str(counts["activate"])),
                KvRow(label="Upgrade", value=str(counts["upgrade"])),
                KvRow(label="Output", value=str(path)),
            ],
        )
    )


@plugins_app.command("install")
def plugins_install(
    plugin_id: Annotated[str, typer.Argument(help="Plugin ID to install (e.g. com.snc.discovery)")],
    instance: Annotated[
        str, typer.Option("--instance", help="Instance profile (default: configured default)")
    ] = "",
    version: Annotated[
        str | None, typer.Option("--version", help="Pin to this version (default: latest)")
    ] = None,
    yes: Annotated[bool, typer.Option("--yes", help="Skip the confirmation prompt")] = False,
) -> None:
    """Install a plugin on the resolved instance.

    Shows the SN dependency cascade pre-flight, prompts for confirmation
    (unless ``--yes``), then blocks with a progress bar until SN reports
    terminal status.
    """
    from nexus.plugins.dependencies import fetch_dependencies  # noqa: PLC0415
    from nexus.plugins.executor import PluginExecutor  # noqa: PLC0415

    resolved = _plugins_for(instance)
    if resolved is None:
        console.print(Notice.warn("Plugin inventory empty."))
        console.print(Hint(label="Refresh", command="nexus instance refresh"))
        raise typer.Exit(1)
    meta, inventory = resolved
    _, _, token, _ = _acquire_token(meta.profile)

    async def _run() -> None:
        async with ServiceNowClient(instance_url=meta.url, token=token) as client:
            deps = await fetch_dependencies(client, plugin_id, version)
            if deps:
                console.print(_dependencies_panel(deps, plugin_id))
            if not yes and not typer.confirm(f"Install {plugin_id} against {meta.profile}?"):
                raise typer.Exit(0)
            executor = PluginExecutor(client=client, inventory=inventory)
            result = await executor.install(plugin_id, version)
            console.print(_result_panel(result))
            if not result.success:
                raise typer.Exit(1)

    asyncio.run(_run())


@plugins_app.command("activate")
def plugins_activate(
    plugin_id: Annotated[str, typer.Argument(help="Plugin ID to activate")],
    instance: Annotated[
        str, typer.Option("--instance", help="Instance profile (default: configured default)")
    ] = "",
    yes: Annotated[bool, typer.Option("--yes", help="Skip the confirmation prompt")] = False,
) -> None:
    """Activate an installed plugin on the resolved instance."""
    from nexus.plugins.executor import PluginExecutor  # noqa: PLC0415

    resolved = _plugins_for(instance)
    if resolved is None:
        console.print(Notice.warn("Plugin inventory empty."))
        console.print(Hint(label="Refresh", command="nexus instance refresh"))
        raise typer.Exit(1)
    meta, inventory = resolved
    _, _, token, _ = _acquire_token(meta.profile)

    async def _run() -> None:
        async with ServiceNowClient(instance_url=meta.url, token=token) as client:
            if not yes and not typer.confirm(f"Activate {plugin_id} against {meta.profile}?"):
                raise typer.Exit(0)
            executor = PluginExecutor(client=client, inventory=inventory)
            result = await executor.activate(plugin_id)
            console.print(_result_panel(result))
            if not result.success:
                raise typer.Exit(1)

    asyncio.run(_run())


@plugins_app.command("upgrade")
def plugins_upgrade(
    plugin_id: Annotated[str, typer.Argument(help="Plugin ID to upgrade")],
    instance: Annotated[
        str, typer.Option("--instance", help="Instance profile (default: configured default)")
    ] = "",
    to: Annotated[
        str | None, typer.Option("--to", help="Target version (default: latest available)")
    ] = None,
    yes: Annotated[bool, typer.Option("--yes", help="Skip the confirmation prompt")] = False,
) -> None:
    """Upgrade an installed plugin on the resolved instance."""
    from nexus.plugins.dependencies import fetch_dependencies  # noqa: PLC0415
    from nexus.plugins.executor import PluginExecutor  # noqa: PLC0415

    resolved = _plugins_for(instance)
    if resolved is None:
        console.print(Notice.warn("Plugin inventory empty."))
        console.print(Hint(label="Refresh", command="nexus instance refresh"))
        raise typer.Exit(1)
    meta, inventory = resolved
    _, _, token, _ = _acquire_token(meta.profile)

    async def _run() -> None:
        async with ServiceNowClient(instance_url=meta.url, token=token) as client:
            deps = await fetch_dependencies(client, plugin_id, to)
            if deps:
                console.print(_dependencies_panel(deps, plugin_id))
            if not yes and not typer.confirm(f"Upgrade {plugin_id} on {meta.profile}?"):
                raise typer.Exit(0)
            executor = PluginExecutor(client=client, inventory=inventory)
            result = await executor.upgrade(plugin_id, to)
            console.print(_result_panel(result))
            if not result.success:
                raise typer.Exit(1)

    asyncio.run(_run())


@plugins_app.command("apply")
def plugins_apply(
    plan_file: Annotated[Path, typer.Argument(help="Path to PromotionPlan YAML")],
    instance: Annotated[
        str, typer.Option("--instance", help="Instance profile (default: configured default)")
    ] = "",
    yes: Annotated[bool, typer.Option("--yes", help="Skip the confirmation prompt")] = False,
) -> None:
    """Execute a PromotionPlan YAML produced by `nexus plugins promote`.

    Rolls back partial failures in reverse order (best-effort).
    """
    from nexus.plugins.executor import PluginExecutor  # noqa: PLC0415

    if not plan_file.exists():
        err_console.print(Notice.error(f"Plan file not found: {plan_file}"))
        raise typer.Exit(2)
    raw_payload = _yaml.safe_load(plan_file.read_text(encoding="utf-8"))
    # YAML loads sequences as lists; PromotionPlan.actions is tuple[...] under
    # strict mode, so coerce before validating.
    if isinstance(raw_payload, dict):
        payload = cast(dict[str, object], raw_payload)
        actions = payload.get("actions")
        if isinstance(actions, list):
            payload["actions"] = tuple(cast(list[object], actions))
        plan = PromotionPlan.model_validate(payload)
    else:
        plan = PromotionPlan.model_validate(raw_payload)

    resolved = _plugins_for(instance)
    if resolved is None:
        console.print(Notice.warn("Plugin inventory empty."))
        console.print(Hint(label="Refresh", command="nexus instance refresh"))
        raise typer.Exit(1)
    meta, inventory = resolved
    _, _, token, _ = _acquire_token(meta.profile)

    async def _run() -> None:
        async with ServiceNowClient(instance_url=meta.url, token=token) as client:
            console.print(f"Plan: {len(plan.actions)} actions against {meta.profile}")
            if not yes and not typer.confirm("Proceed?"):
                raise typer.Exit(0)
            executor = PluginExecutor(client=client, inventory=inventory)
            log = await executor.apply_plan(plan, console=console)
            console.print(f"Done: {log.success_count} ok, {log.failure_count} failed")
            if log.failure_count:
                raise typer.Exit(1)

    asyncio.run(_run())


@plugins_app.command("deactivate")
def plugins_deactivate(
    plugin_id: Annotated[str, typer.Argument(help="Plugin ID to deactivate")],
    instance: Annotated[
        str, typer.Option("--instance", help="Instance profile (default: configured default)")
    ] = "",
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            help="Bypass the impact gate (requires typing the plugin id at the second prompt)",
        ),
    ] = False,
    yes: Annotated[bool, typer.Option("--yes", help="Skip the action confirmation prompt")] = False,
) -> None:
    """Deactivate a plugin on the resolved instance.

    The impact gate blocks the operation when the plugin has reverse-deps
    or SN reports dependents. ``--force`` bypasses the gate but always
    requires typing the plugin id at a second confirmation prompt;
    ``--yes`` only skips the first prompt and never the second.
    """
    import asyncio  # noqa: PLC0415

    from nexus.plugins.executor import PluginExecutor  # noqa: PLC0415

    resolved = _plugins_for(instance)
    if resolved is None:
        console.print(Notice.warn("Plugin inventory empty."))
        console.print(Hint(label="Refresh", command="nexus instance refresh"))
        raise typer.Exit(1)
    meta, inventory = resolved
    _, _, token, _ = _acquire_token(meta.profile)

    async def _run() -> None:
        async with ServiceNowClient(instance_url=meta.url, token=token) as client:
            if not yes and not typer.confirm(f"Deactivate {plugin_id} on {meta.profile}?"):
                raise typer.Exit(0)
            if force:
                typed = typer.prompt(
                    f"--force bypasses the impact gate. Type the plugin id "
                    f"({plugin_id}) to confirm"
                )
                if typed != plugin_id:
                    err_console.print(Notice.error("Confirmation mismatch; aborting."))
                    raise typer.Exit(2)
            executor = PluginExecutor(client=client, inventory=inventory)
            result = await executor.deactivate(plugin_id, force=force)
            console.print(_result_panel(result))
            if not result.success:
                raise typer.Exit(1)

    asyncio.run(_run())


@plugins_app.command("uninstall")
def plugins_uninstall(
    plugin_id: Annotated[str, typer.Argument(help="Plugin ID to uninstall")],
    instance: Annotated[
        str, typer.Option("--instance", help="Instance profile (default: configured default)")
    ] = "",
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            help="Bypass the impact gate (requires typing the plugin id at the second prompt)",
        ),
    ] = False,
    yes: Annotated[bool, typer.Option("--yes", help="Skip the action confirmation prompt")] = False,
) -> None:
    """Uninstall a non-base plugin on the resolved instance.

    Base ServiceNow plugins (source == 'servicenow') cannot be uninstalled
    via REST and are refused unconditionally -- ``--force`` does NOT bypass
    that refusal. For non-base plugins the impact gate applies the same way
    as ``deactivate``: it blocks on non-zero reverse-deps unless ``--force``
    is given with a type-the-plugin-id confirmation.
    """
    import asyncio  # noqa: PLC0415

    from nexus.plugins.executor import PluginExecutor  # noqa: PLC0415

    resolved = _plugins_for(instance)
    if resolved is None:
        console.print(Notice.warn("Plugin inventory empty."))
        console.print(Hint(label="Refresh", command="nexus instance refresh"))
        raise typer.Exit(1)
    meta, inventory = resolved
    _, _, token, _ = _acquire_token(meta.profile)

    async def _run() -> None:
        async with ServiceNowClient(instance_url=meta.url, token=token) as client:
            if not yes and not typer.confirm(f"Uninstall {plugin_id} on {meta.profile}?"):
                raise typer.Exit(0)
            if force:
                typed = typer.prompt(
                    f"--force bypasses the impact gate. Type the plugin id "
                    f"({plugin_id}) to confirm"
                )
                if typed != plugin_id:
                    err_console.print(Notice.error("Confirmation mismatch; aborting."))
                    raise typer.Exit(2)
            executor = PluginExecutor(client=client, inventory=inventory)
            result = await executor.uninstall(plugin_id, force=force)
            console.print(_result_panel(result))
            if not result.success:
                raise typer.Exit(1)

    asyncio.run(_run())


@plugins_app.command("updates")
def plugins_updates(
    instance: Annotated[
        str,
        typer.Option(
            "--instance",
            help="Instance profile (default: configured default)",
        ),
    ] = "",
    queue: Annotated[
        str,
        typer.Option(
            "--queue",
            help="Write a YAML queue of pending updates to the given path "
            "(writes an empty updates list when up-to-date).",
        ),
    ] = "",
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: text | json (default: text)"),
    ] = "text",
) -> None:
    """Show plugins with newer versions available; optionally write a YAML queue."""
    _validate_format(output_format)
    meta, inventory = _load_inventory_or_exit(instance)
    pending = plugins_with_updates(inventory)
    if queue:
        payload: dict[str, object] = {
            "instance": meta.profile,
            "captured_at": inventory.captured_at.isoformat(),
            "updates": [
                {
                    "plugin_id": p.plugin_id,
                    "name": p.name,
                    "product_family": p.product_family,
                    "current_version": p.version,
                    "latest_version": p.latest_version,
                }
                for p in pending
            ],
        }
        Path(queue).write_text(_yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    if output_format == "json":
        _emit_json(_UpdatesReport(updates=tuple(pending)))
        return
    if not pending:
        with_lv = sum(1 for p in inventory.plugins if p.latest_version is not None)
        if with_lv == 0:
            console.print(
                Notice.warn(
                    "No latest_version data captured -- updates cannot be detected. "
                    "Likely causes: sys_store_app REST access denied (403), or "
                    "v_plugin's available_version mirrors version on this instance."
                )
            )
            console.print(
                Hint(
                    label="Grant role",
                    command="grant the OAuth user 'app_store_pa_user_role' on the SN instance",
                )
            )
        else:
            console.print(Notice.info("Up to date."))
        if queue:
            console.print(Notice.info(f"Wrote empty queue to {queue}."))
        return
    rows: list[list[RenderableType]] = [
        [
            p.plugin_id,
            p.name,
            p.product_family,
            p.version,
            p.latest_version or "-",
        ]
        for p in pending
    ]
    console.print(
        DataTable(
            title="Updates available",
            columns=[
                DataColumn(header="Plugin ID", width=32),
                DataColumn(header="Name", width=20),
                DataColumn(header="Product", width=14),
                DataColumn(header="Current", width=12),
                DataColumn(header="Latest", width=12),
            ],
            rows=rows,
        )
    )
    console.print(Notice.info(f"{len(pending)} update(s) available."))
    if queue:
        console.print(Notice.info(f"Wrote queue ({len(pending)} entries) to {queue}."))
        console.print(
            Hint(
                label="Before applying",
                command=f"nexus instance refresh {meta.profile}",
            )
        )


_SEVERITY_ORDER: tuple[Severity, ...] = (
    Severity.CRITICAL,
    Severity.HIGH,
    Severity.MEDIUM,
    Severity.LOW,
)


def _severity_at_or_above(floor: Severity) -> set[Severity]:
    """Return severities at or above ``floor`` in the canonical ordering.

    Args:
        floor: Lower bound (inclusive).

    Returns:
        Set of severities at or above ``floor`` (critical > high > medium > low).
    """
    idx = _SEVERITY_ORDER.index(floor)
    return set(_SEVERITY_ORDER[: idx + 1])


def _render_advisory_sections(findings: tuple[AdvisoryFinding, ...]) -> None:
    """Render one DataTable per non-empty advisory type.

    Args:
        findings: All findings to render, after filtering.
    """
    by_type: dict[AdvisoryType, list[AdvisoryFinding]] = {
        AdvisoryType.EOL: [],
        AdvisoryType.CVE: [],
        AdvisoryType.LICENSE: [],
    }
    for finding in findings:
        by_type[finding.advisory_type].append(finding)

    if by_type[AdvisoryType.EOL]:
        rows: list[list[RenderableType]] = [
            [f.plugin_id, f.plugin_name, f.plugin_version, f.severity.value, Text(f.details)]
            for f in by_type[AdvisoryType.EOL]
        ]
        console.print(
            DataTable(
                title="EOL plugins",
                columns=[
                    DataColumn(header="Plugin ID", width=32),
                    DataColumn(header="Name", width=20),
                    DataColumn(header="Version", width=12),
                    DataColumn(header="Severity", width=10),
                    DataColumn(header="Details", width=42),
                ],
                rows=rows,
            )
        )
    if by_type[AdvisoryType.CVE]:
        rows = [
            [
                f.plugin_id,
                f.plugin_name,
                f.plugin_version,
                f.severity.value,
                Text(f.details),
                Text(f.summary),
            ]
            for f in by_type[AdvisoryType.CVE]
        ]
        console.print(
            DataTable(
                title="CVE advisories",
                columns=[
                    DataColumn(header="Plugin ID", width=28),
                    DataColumn(header="Name", width=18),
                    DataColumn(header="Version", width=10),
                    DataColumn(header="Severity", width=10),
                    DataColumn(header="CVE / range", width=32),
                    DataColumn(header="Summary", width=28),
                ],
                rows=rows,
            )
        )
    if by_type[AdvisoryType.LICENSE]:
        rows = [
            [f.plugin_id, f.plugin_name, f.plugin_version, f.severity.value, Text(f.details)]
            for f in by_type[AdvisoryType.LICENSE]
        ]
        console.print(
            DataTable(
                title="License findings",
                columns=[
                    DataColumn(header="Plugin ID", width=32),
                    DataColumn(header="Name", width=20),
                    DataColumn(header="Version", width=12),
                    DataColumn(header="Severity", width=10),
                    DataColumn(header="Details", width=42),
                ],
                rows=rows,
            )
        )


def _render_advisory_summary(
    findings: tuple[AdvisoryFinding, ...], deferred_count: int = 0
) -> None:
    """Print the trailing per-severity count notice.

    Args:
        findings: All rendered findings (after override filtering).
        deferred_count: Number of deferred findings excluded from display.
    """
    counts = {s: 0 for s in _SEVERITY_ORDER}
    for f in findings:
        counts[f.severity] += 1
    parts = [f"{counts[s]} {s.value}" for s in _SEVERITY_ORDER]
    suffix = f"; {deferred_count} deferred" if deferred_count else ""
    console.print(Notice.info(f"{len(findings)} advisory finding(s): {', '.join(parts)}{suffix}."))


@plugins_app.command("advisories")
def plugins_advisories(
    instance: Annotated[
        str,
        typer.Option(
            "--instance",
            help="Instance profile (default: configured default)",
        ),
    ] = "",
    advisory_type: Annotated[
        str,
        typer.Option(
            "--type",
            help="Filter to one advisory type: eol, cve, or license.",
        ),
    ] = "",
    severity: Annotated[
        str,
        typer.Option(
            "--severity",
            help="Show only findings at or above this severity (critical|high|medium|low).",
        ),
    ] = "",
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: text | json (default: text)"),
    ] = "text",
    strict: Annotated[
        bool,
        typer.Option(
            "--strict",
            help="Exit with code 1 if any findings remain after filters.",
        ),
    ] = False,
    include_deferred: Annotated[
        bool,
        typer.Option(
            "--include-deferred",
            help="Include deferred findings in output (marked [deferred]).",
        ),
    ] = False,
) -> None:
    """Show EOL / CVE / license findings for plugins on an instance."""
    _validate_format(output_format)
    meta, inventory = _load_inventory_or_exit(instance)
    try:
        db = AdvisoryDatabase.load()
    except PluginAdvisoryDataError as exc:
        console.print(Notice.error(f"Advisory data corrupted: {exc}"))
        raise typer.Exit(1) from exc

    today = _today()
    result = compute_advisories(inventory, db, today=today)

    paths = NexusPaths.from_env()
    registry = InstanceRegistry(paths.instances_dir)
    overrides_set = registry.load_advisory_overrides(meta.profile)
    remaining_set, deferred = apply_overrides(result, overrides_set)
    deferred_count = len(deferred)
    findings = remaining_set.findings

    if include_deferred:
        marked_deferred = tuple(
            f.model_copy(
                update={
                    "summary": f"[deferred] {f.summary}",
                    "details": f"[deferred] {f.details}",
                }
            )
            for f in deferred
        )
        sev_index: dict[Severity, int] = {s: i for i, s in enumerate(_SEVERITY_ORDER)}
        findings = tuple(
            sorted(
                (*findings, *marked_deferred),
                key=lambda f: (sev_index[f.severity], f.plugin_id),
            )
        )

    if advisory_type:
        try:
            wanted_type = AdvisoryType(advisory_type)
        except ValueError as exc:
            console.print(Notice.error(f"Unknown --type: {advisory_type}"))
            raise typer.Exit(1) from exc
        findings = tuple(f for f in findings if f.advisory_type is wanted_type)

    if severity:
        try:
            floor = Severity(severity)
        except ValueError as exc:
            console.print(Notice.error(f"Unknown --severity: {severity}"))
            raise typer.Exit(1) from exc
        keep = _severity_at_or_above(floor)
        findings = tuple(f for f in findings if f.severity in keep)

    if output_format == "json":
        _emit_json(result.model_copy(update={"findings": findings}))
        if strict and findings:
            raise typer.Exit(1)
        return

    if not findings and not deferred_count:
        console.print(Notice.info("No advisories found."))
        return

    if findings:
        _render_advisory_sections(findings)
    _render_advisory_summary(findings, deferred_count=deferred_count)
    if strict and findings:
        raise typer.Exit(1)


@plugins_app.command("defer")
def plugins_advisories_defer(
    plugin_id: Annotated[str, typer.Argument(help="SN plugin identifier")],
    advisory_type: Annotated[str, typer.Argument(help="eol | cve | license")],
    details: Annotated[str, typer.Argument(help="Exact finding details string")],
    reason: Annotated[str, typer.Option("--reason", help="Required justification")] = "",
    instance: Annotated[
        str,
        typer.Option("--instance", help="Instance profile (default: configured default)"),
    ] = "",
) -> None:
    """Defer an EOL/CVE/license advisory finding on a plugin."""
    if not plugin_id or not advisory_type or not details or not reason:
        err_console.print(
            Notice.error("Missing required: PLUGIN_ID, ADVISORY_TYPE, DETAILS, --reason")
        )
        raise typer.Exit(2)
    try:
        wanted_type = AdvisoryType(advisory_type)
    except ValueError as exc:
        console.print(Notice.error(f"Unknown advisory type: {advisory_type}"))
        raise typer.Exit(1) from exc
    if not reason.strip():
        console.print(Notice.error("--reason must not be empty"))
        raise typer.Exit(1)

    paths = NexusPaths.from_env()
    registry = InstanceRegistry(paths.instances_dir)
    meta, inventory = _load_inventory_or_exit(instance)
    try:
        db = AdvisoryDatabase.load()
    except PluginAdvisoryDataError as exc:
        console.print(Notice.error(f"Advisory data corrupted: {exc}"))
        raise typer.Exit(1) from exc
    today = _today()
    advisories = compute_advisories(inventory, db, today=today)

    if not any(
        f.plugin_id == plugin_id and f.advisory_type is wanted_type and f.details == details
        for f in advisories.findings
    ):
        console.print(
            Notice.error(
                f"No matching finding for plugin={plugin_id} type={wanted_type.value} "
                f"details={details!r}"
            )
        )
        raise typer.Exit(1)

    existing = registry.load_advisory_overrides(meta.profile)
    if any(
        o.plugin_id == plugin_id and o.advisory_type is wanted_type and o.details == details
        for o in existing.overrides
    ):
        console.print(Notice.error("Override already exists for that finding"))
        raise typer.Exit(1)

    new_override = AdvisoryOverride(
        plugin_id=plugin_id,
        advisory_type=wanted_type,
        details=details,
        reason=reason,
        created_at=datetime.now(UTC),
    )
    combined = tuple(
        sorted(
            (*existing.overrides, new_override),
            key=lambda o: (o.plugin_id, o.advisory_type.value, o.details),
        )
    )
    registry.save_advisory_overrides(meta.profile, AdvisoryOverrideSet(overrides=combined))
    console.print(Notice.info(f"Deferred {wanted_type.value} {details} on {plugin_id}"))


@plugins_app.command("undo-defer")
def plugins_advisories_undo_defer(
    plugin_id: Annotated[str, typer.Argument(help="SN plugin identifier")],
    advisory_type: Annotated[str, typer.Argument(help="eol | cve | license")],
    details: Annotated[str, typer.Argument(help="Exact finding details string")],
    instance: Annotated[
        str,
        typer.Option("--instance", help="Instance profile (default: configured default)"),
    ] = "",
) -> None:
    """Remove a previously deferred advisory finding."""
    try:
        wanted_type = AdvisoryType(advisory_type)
    except ValueError as exc:
        console.print(Notice.error(f"Unknown advisory type: {advisory_type}"))
        raise typer.Exit(1) from exc

    paths = NexusPaths.from_env()
    registry = InstanceRegistry(paths.instances_dir)
    meta, _ = _load_inventory_or_exit(instance)
    existing = registry.load_advisory_overrides(meta.profile)
    filtered = tuple(
        o
        for o in existing.overrides
        if not (
            o.plugin_id == plugin_id and o.advisory_type is wanted_type and o.details == details
        )
    )
    if len(filtered) == len(existing.overrides):
        console.print(Notice.error("No matching override found"))
        raise typer.Exit(1)
    registry.save_advisory_overrides(meta.profile, AdvisoryOverrideSet(overrides=filtered))
    console.print(Notice.info(f"Removed override for {wanted_type.value} {details} on {plugin_id}"))


@plugins_app.command("list-deferred")
def plugins_advisories_list_deferred(
    instance: Annotated[
        str,
        typer.Option("--instance", help="Instance profile (default: configured default)"),
    ] = "",
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: text | json (default: text)"),
    ] = "text",
) -> None:
    """List all deferred advisory findings for an instance."""
    _validate_format(output_format)
    paths = NexusPaths.from_env()
    registry = InstanceRegistry(paths.instances_dir)
    meta, _ = _load_inventory_or_exit(instance)
    overrides_set = registry.load_advisory_overrides(meta.profile)

    if output_format == "json":
        _emit_json(overrides_set)
        return
    if not overrides_set.overrides:
        console.print(Notice.info("No advisory overrides."))
        return

    rows: list[list[RenderableType]] = [
        [
            o.plugin_id,
            o.advisory_type.value,
            _trunc(o.details, 30),
            _trunc(o.reason, 40),
            str(o.created_at.date()),
        ]
        for o in overrides_set.overrides
    ]
    console.print(
        DataTable(
            title="Deferred advisories",
            columns=[
                DataColumn(header="Plugin", width=28),
                DataColumn(header="Type", width=8),
                DataColumn(header="Details", width=30),
                DataColumn(header="Reason", width=40),
                DataColumn(header="Created", width=12),
            ],
            rows=rows,
        )
    )


def _impact_transport() -> httpx.AsyncBaseTransport | None:
    """Return the async transport used by the impact command.

    In production this returns ``None`` so httpx uses the real network.
    Tests monkeypatch this to inject an ``httpx.MockTransport``.
    """
    return None


def _agent_client_factory() -> AgentClientProtocol:
    """Return a real AgentClient; monkeypatched in tests.

    Returns:
        AgentClient instance for LLM calls.
    """
    from nexus.api.agent_client import AgentClient  # noqa: PLC0415

    return AgentClient()


@plugins_app.command("impact")
def plugins_impact(
    plugin_id: Annotated[
        str,
        typer.Argument(help="Plugin identifier (e.g. com.acme.helper)"),
    ] = "",
    instance: Annotated[
        str,
        typer.Option(
            "--instance",
            help="Instance profile (default: configured default)",
        ),
    ] = "",
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: text | json (default: text)"),
    ] = "text",
    live: Annotated[
        bool,
        typer.Option(
            "--live",
            help="Force a live re-query of SN record counts instead of using the cached breakdown.",
        ),
    ] = False,
    no_cross_scope: Annotated[
        bool,
        typer.Option(
            "--no-cross-scope",
            help="Skip the cross-scope FK reference scan.",
        ),
    ] = False,
) -> None:
    """Show reverse dependencies + scope-owned record counts for a plugin."""
    _validate_format(output_format)
    _, inventory = _load_inventory_or_exit(instance)
    _registry, meta, token, _expiry = _acquire_token(instance)
    transport = _impact_transport()
    try:
        impact = asyncio.run(
            compute_impact(
                inventory,
                plugin_id,
                url=meta.url,
                token=token,
                transport=transport,
                live=live,
                cross_scope=not no_cross_scope,
            )
        )
    except PluginImpactError as exc:
        console.print(Notice.error(f"Plugin not found: {plugin_id}"))
        raise typer.Exit(1) from exc

    if output_format == "json":
        _emit_json(impact)
        return
    _render_impact(impact, opted_out=no_cross_scope)


def _render_impact(impact: PluginImpact, *, opted_out: bool = False) -> None:
    """Render the impact DataTables + trailing summary Notice.

    Args:
        impact: PluginImpact from compute_impact.
        opted_out: True when the user passed --no-cross-scope; suppresses
            the unavailability warning for the cross-scope section.
    """
    if impact.reverse_deps:
        dep_rows: list[list[RenderableType]] = [
            [
                d.plugin_id,
                d.name,
                d.state,
                str(d.depth),
                _trunc("->".join(d.via), 60),
            ]
            for d in impact.reverse_deps
        ]
        console.print(
            DataTable(
                title="Reverse dependencies",
                columns=[
                    DataColumn(header="Plugin ID", width=32),
                    DataColumn(header="Name", width=20),
                    DataColumn(header="State", width=10),
                    DataColumn(header="Depth", width=7),
                    DataColumn(header="Via", width=60),
                ],
                rows=dep_rows,
            )
        )
    else:
        console.print(Notice.info(f"No plugins depend on {impact.target_plugin_id}."))

    total_records = 0
    if not impact.counts_available:
        console.print(Notice.warn("Record counts unavailable -- could not reach instance."))
    elif not impact.record_counts:
        console.print(Notice.info("No scope-owned records."))
    else:
        count_rows: list[list[RenderableType]] = [
            [c.table, f"{c.count:,}"] for c in impact.record_counts
        ]
        console.print(
            DataTable(
                title="Scope-owned records",
                columns=[
                    DataColumn(header="Table", width=32),
                    DataColumn(header="Count", width=12),
                ],
                rows=count_rows,
            )
        )
        total_records = sum(c.count for c in impact.record_counts)

    if opted_out:
        console.print(Notice.info("Cross-scope scan skipped (--no-cross-scope)."))
    elif not impact.cross_scope_available:
        console.print(
            Notice.warn(
                "Cross-scope scan unavailable -- the SN aggregate API errored "
                "(likely permissions or async-pending). See logs for detail."
            )
        )
    elif not impact.cross_scope_refs:
        console.print(Notice.info("No inbound cross-scope references."))
    if impact.cross_scope_available and impact.cross_scope_refs:
        ref_rows: list[list[RenderableType]] = [
            [
                r.source_scope,
                r.source_table,
                r.field,
                r.target_table,
                f"{r.record_count:,}",
            ]
            for r in impact.cross_scope_refs
        ]
        console.print(
            DataTable(
                title="Cross-scope references",
                columns=[
                    DataColumn(header="Source scope", width=24),
                    DataColumn(header="Source table", width=24),
                    DataColumn(header="Field", width=16),
                    DataColumn(header="Target table", width=20),
                    DataColumn(header="Records", width=10),
                ],
                rows=ref_rows,
            )
        )

    cross_scope_suffix = (
        f"; {len(impact.cross_scope_refs)} cross-scope refs" if impact.cross_scope_refs else ""
    )
    if impact.counts_available:
        console.print(
            Notice.info(
                f"{len(impact.reverse_deps)} dependent plugin(s); "
                f"{total_records:,} records in scope {impact.target_plugin_id}"
                f"{cross_scope_suffix}."
            )
        )
    else:
        console.print(
            Notice.info(f"{len(impact.reverse_deps)} dependent plugin(s){cross_scope_suffix}.")
        )


_ORPHAN_STATES = ("active", "inactive")


@plugins_app.command("orphans")
def plugins_orphans(
    instance: Annotated[
        str,
        typer.Option(
            "--instance",
            help="Instance profile (default: configured default)",
        ),
    ] = "",
    state: Annotated[
        str,
        typer.Option(
            "--state",
            help="Filter to one plugin state: active or inactive.",
        ),
    ] = "",
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: text | json (default: text)"),
    ] = "text",
) -> None:
    """Show plugins with no dependents AND no scope-owned records."""
    _validate_format(output_format)
    meta, inventory = _load_inventory_or_exit(instance)
    if all(p.record_counts is None for p in inventory.plugins):
        console.print(
            Notice.warn("Inventory has no record counts -- run nexus instance refresh to populate.")
        )
        console.print(Hint(label="Refresh", command=f"nexus instance refresh {meta.profile}"))
        raise typer.Exit(1)
    if state and state not in _ORPHAN_STATES:
        console.print(Notice.error(f"Unknown --state: {state}"))
        raise typer.Exit(1)
    candidates = orphan_candidates(inventory)
    if state:
        candidates = tuple(p for p in candidates if p.state == state)
    if output_format == "json":
        _emit_json(_OrphansReport(candidates=tuple(candidates)))
        return
    if not candidates:
        console.print(Notice.info("No orphan candidates."))
        return
    rows: list[list[RenderableType]] = [
        [
            p.plugin_id,
            p.name,
            "active" if p.state == "active" else "inactive (license slot)",
            "no records",
        ]
        for p in candidates
    ]
    console.print(
        DataTable(
            title="Orphan candidates",
            columns=[
                DataColumn(header="Plugin ID", width=32),
                DataColumn(header="Name", width=24),
                DataColumn(header="State", width=24),
                DataColumn(header="Records", width=12),
            ],
            rows=rows,
        )
    )
    console.print(Notice.info(f"{len(candidates)} orphan candidate(s)."))


@plugins_app.command("drift")
def plugins_drift(
    instance: Annotated[
        str,
        typer.Option(
            "--instance",
            help="Instance profile (default: configured default)",
        ),
    ] = "",
    ack: Annotated[
        bool,
        typer.Option(
            "--ack",
            help="Set the current snapshot as the new baseline and exit.",
        ),
    ] = False,
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: text | json (default: text)"),
    ] = "text",
    strict: Annotated[
        bool,
        typer.Option(
            "--strict",
            help="Exit with code 1 if any drift is detected.",
        ),
    ] = False,
    baseline_name: Annotated[
        str,
        typer.Option(
            "--baseline",
            help=f"Named baseline to compare against (default: {DEFAULT_BASELINE_NAME}).",
        ),
    ] = DEFAULT_BASELINE_NAME,
) -> None:
    """Show plugin drift on an instance since the last baseline."""
    _validate_format(output_format)
    try:
        validate_baseline_name(baseline_name)
    except InvalidBaselineNameError as exc:
        err_console.print(Notice.error(str(exc)))
        raise typer.Exit(1) from exc
    meta, inventory = _load_inventory_or_exit(instance)
    paths = NexusPaths.from_env()
    registry = InstanceRegistry(paths.instances_dir)

    if ack:
        registry.save_plugin_baseline(meta.profile, baseline_name, inventory)
        captured = inventory.captured_at.strftime("%Y-%m-%d")
        console.print(
            Notice.info(f"Baseline set: {len(inventory.plugins)} plugins captured {captured}.")
        )
        return

    baseline = registry.load_plugin_baseline(meta.profile, baseline_name)
    if baseline is None:
        err_console.print(Notice.error(f"No baseline set for {meta.profile!r}."))
        console.print(
            Hint(
                label="Set baseline",
                command=f"nexus plugins drift --ack --baseline {baseline_name}",
            )
        )
        raise typer.Exit(1)

    report = compute_drift(baseline, inventory, meta.profile)

    if output_format == "json":
        _emit_json(report)
        if strict and report.entries:
            raise typer.Exit(1)
        return

    if not report.entries:
        console.print(Notice.info("No drift detected."))
        return

    rows: list[list[RenderableType]] = [
        [
            e.plugin_id,
            e.name,
            e.product_family,
            _drift_status_badge(e.status),
            (e.baseline_version or "-"),
            (e.current_version or "-"),
            (e.baseline_state or "-"),
            (e.current_state or "-"),
        ]
        for e in report.entries
    ]
    console.print(
        DataTable(
            title=f"Plugin drift: {meta.profile}",
            columns=[
                DataColumn(header="Plugin ID", width=32),
                DataColumn(header="Name", width=20),
                DataColumn(header="Product", width=14),
                DataColumn(header="Status", width=16),
                DataColumn(header="Baseline ver", width=12),
                DataColumn(header="Current ver", width=12),
                DataColumn(header="Baseline state", width=14),
                DataColumn(header="Current state", width=14),
            ],
            rows=rows,
        )
    )
    console.print(Notice.info(_status_breakdown((e.status for e in report.entries), "drift")))
    if strict and report.entries:
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# nexus plugins explain / roadmap
# ---------------------------------------------------------------------------


@plugins_app.command("explain")
def plugins_explain(
    plugin_id: Annotated[str, typer.Argument(help="Plugin to explain.")],
    instance: Annotated[
        str,
        typer.Option("--instance", help="Instance profile (default: configured default)"),
    ] = "",
) -> None:
    """Explain what a plugin does and whether the user likely needs it."""
    _, inventory = _load_inventory_or_exit(instance)
    plugin = next((p for p in inventory.plugins if p.plugin_id == plugin_id), None)
    if plugin is None:
        console.print(Notice.error(f"Plugin not found: {plugin_id}"))
        raise typer.Exit(1)
    _registry, meta, token, _expiry = _acquire_token(instance)
    transport = _impact_transport()
    impact = asyncio.run(
        compute_impact(
            inventory,
            plugin_id,
            url=meta.url,
            token=token,
            transport=transport,
            cross_scope=False,
        )
    )
    db = AdvisoryDatabase.load()
    single_plugin_inventory = inventory.model_copy(update={"plugins": (plugin,)})
    plugin_findings = compute_advisories(single_plugin_inventory, db, today=_today()).findings
    prompt = build_explain_context(plugin, impact, plugin_findings)
    client = _agent_client_factory()
    try:
        text = asyncio.run(client.complete(prompt, system=EXPLAIN_SYSTEM_PROMPT, model=AI_MODEL))
    except AnthropicError as exc:
        console.print(Notice.error(f"AI request failed: {exc}"))
        raise typer.Exit(1) from exc
    console.print(text)


@plugins_app.command("roadmap")
def plugins_roadmap(
    instance: Annotated[
        str,
        typer.Option("--instance", help="Instance profile (default: configured default)"),
    ] = "",
) -> None:
    """Draft an AI-generated remediation roadmap."""
    meta, inventory = _load_inventory_or_exit(instance)
    db = AdvisoryDatabase.load()
    advisories = compute_advisories(inventory, db, today=_today())
    orphans = orphan_candidates(inventory)

    paths = NexusPaths.from_env()
    registry = InstanceRegistry(paths.instances_dir)
    overrides = registry.load_advisory_overrides(meta.profile)
    deferred = len(overrides.overrides)

    if not advisories.findings and not orphans and deferred == 0:
        console.print(Notice.info("Nothing to remediate -- no advisories, orphans, or overrides."))
        return

    prompt = build_roadmap_context(inventory, advisories, orphans=orphans, deferred_count=deferred)
    client = _agent_client_factory()
    try:
        text = asyncio.run(client.complete(prompt, system=ROADMAP_SYSTEM_PROMPT, model=AI_MODEL))
    except AnthropicError as exc:
        console.print(Notice.error(f"AI request failed: {exc}"))
        raise typer.Exit(1) from exc
    console.print(text)


# nexus plugins recommend
# ---------------------------------------------------------------------------

recommend_app = typer.Typer(help="AI recommendations.")
plugins_app.add_typer(recommend_app, name="recommend")


@recommend_app.callback(invoke_without_command=True)
def plugins_recommend_callback(ctx: typer.Context) -> None:
    """Show the available 'plugins recommend' subcommands."""
    if ctx.invoked_subcommand is not None:
        return
    console.print(CommandHelp(title="nexus plugins recommend", entry=_PLUGINS_RECOMMEND_PARENT))
    console.print(
        CommandGuide(
            app_name="nexus plugins recommend",
            items=_guide_items(_PLUGINS_RECOMMEND_HELP),
        )
    )


@recommend_app.command("deactivate")
def plugins_recommend_deactivate(
    instance: Annotated[
        str,
        typer.Option("--instance", help="Instance profile (default: configured default)"),
    ] = "",
) -> None:
    """List plugins safest to deactivate, with AI rationale."""
    _, inventory = _load_inventory_or_exit(instance)
    db = AdvisoryDatabase.load()
    advisories = compute_advisories(inventory, db, today=_today())
    orphans = orphan_candidates(inventory)
    if not orphans and not advisories.findings:
        console.print(Notice.info("No orphans or advisories -- nothing to recommend."))
        return
    prompt = build_deactivation_context(inventory, advisories, orphans=orphans)
    client = _agent_client_factory()
    try:
        text = asyncio.run(client.complete(prompt, system=DEACTIVATE_SYSTEM_PROMPT, model=AI_MODEL))
    except AnthropicError as exc:
        console.print(Notice.error(f"AI request failed: {exc}"))
        raise typer.Exit(1) from exc
    console.print(text)


# nexus plugins baselines
# ---------------------------------------------------------------------------

baselines_app = typer.Typer(help="Manage plugin drift baselines.")
plugins_app.add_typer(baselines_app, name="baselines")


@baselines_app.callback(invoke_without_command=True)
def plugins_baselines_callback(ctx: typer.Context) -> None:
    """Show the available 'plugins baselines' subcommands."""
    if ctx.invoked_subcommand is not None:
        return
    console.print(CommandHelp(title="nexus plugins baselines", entry=_PLUGINS_BASELINES_PARENT))
    console.print(
        CommandGuide(
            app_name="nexus plugins baselines",
            items=_guide_items(_PLUGINS_BASELINES_HELP),
        )
    )


@baselines_app.command("list")
def plugins_baselines_list(
    instance: Annotated[
        str,
        typer.Option("--instance", help="Instance profile (default: configured default)"),
    ] = "",
) -> None:
    """Show all named baselines for an instance."""
    paths = NexusPaths.from_env()
    registry = InstanceRegistry(paths.instances_dir)
    meta, _ = _load_inventory_or_exit(instance)
    summaries = registry.list_plugin_baseline_summaries(meta.profile)
    if not summaries:
        console.print(Notice.info(f"No baselines saved for {meta.profile}."))
        return
    rows: list[list[RenderableType]] = [
        [name, captured[:19], str(count)] for name, captured, count in summaries
    ]
    console.print(
        DataTable(
            title=f"Baselines for instance {meta.profile}",
            columns=[
                DataColumn(header="Name", width=24),
                DataColumn(header="Captured", width=20),
                DataColumn(header="Plugins", width=8),
            ],
            rows=rows,
        )
    )


@baselines_app.command("delete")
def plugins_baselines_delete(
    name: Annotated[str, typer.Argument(help="Baseline name to delete.")],
    instance: Annotated[
        str,
        typer.Option("--instance", help="Instance profile (default: configured default)"),
    ] = "",
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Skip confirmation."),
    ] = False,
) -> None:
    """Delete a named baseline."""
    try:
        validate_baseline_name(name)
    except InvalidBaselineNameError as exc:
        err_console.print(Notice.error(str(exc)))
        raise typer.Exit(1) from exc
    paths = NexusPaths.from_env()
    registry = InstanceRegistry(paths.instances_dir)
    meta, _ = _load_inventory_or_exit(instance)
    if not yes:
        confirmed = typer.confirm(f"Delete baseline {name!r} for {meta.profile}?")
        if not confirmed:
            console.print(Notice.info("Aborted."))
            return
    try:
        registry.delete_plugin_baseline(meta.profile, name)
    except BaselineNotFoundError as exc:
        err_console.print(Notice.error(str(exc)))
        raise typer.Exit(1) from exc
    console.print(Notice.info(f"Deleted baseline {name}"))


@capture_app.callback(invoke_without_command=True)
def capture_callback(ctx: typer.Context) -> None:
    """Show local archives and available commands."""
    if ctx.invoked_subcommand is not None:
        return
    console.print(CommandHelp(title="nexus capture", entry=_CAPTURE_PARENT))
    console.print(CommandGuide(app_name="nexus capture", items=_guide_items(_CAPTURE_HELP)))


@capture_app.command("discover")
def capture_discover(
    instance: Annotated[
        str, typer.Argument(help="Instance profile name (default: configured default)")
    ] = "",
    group: Annotated[str, typer.Option(help="Table group")] = AI_AUTOMATION.key,
    all_scopes: Annotated[
        bool,
        typer.Option(
            "--all",
            help="Show all scopes, not just your custom ones (x_*, u_*)",
        ),
    ] = False,
) -> None:
    """Discover which of your scopes have custom AI/automation configs."""

    async def _run() -> None:
        engine, client = _build_capture_engine(instance)
        resolved = instance or _config_default()

        with nexus_progress(console) as progress:
            task = progress.add_task(f"Connecting to {resolved}...", total=None)

            def on_progress(completed: int, total: int, message: str) -> None:
                progress.update(
                    task,
                    description=message,
                    total=total if total > 0 else None,
                    completed=completed,
                )

            async with client:
                manifest = await engine.discover_scopes(resolved, group, on_progress=on_progress)

        if not manifest.scopes:
            console.print(Notice.info(f"No scopes with custom configurations found on {resolved}."))
            return

        all_s = list(manifest.scopes)
        custom_s = [s for s in all_s if s.scope.startswith(_CUSTOM_SCOPE_PREFIXES)]

        def _total(s: ScopeEntry) -> int:
            return sum(s.table_counts.values())

        custom_s.sort(key=_total, reverse=True)
        display = all_s if all_scopes else (custom_s if custom_s else all_s)

        group_obj = DEFAULT_TABLE_GROUPS.get(group)
        columns: list[DataColumn] = [
            DataColumn(header="Scope Key", width=_SCOPE_KEY_WIDTH),
            DataColumn(header="Name", width=_SCOPE_NAME_WIDTH),
        ]
        if group_obj:
            for spec in group_obj.tables:
                hdr = _TABLE_HEADER.get(spec.name, spec.display[:4])
                columns.append(DataColumn(header=hdr, width=5, justify="right"))

        rows: list[list[RenderableType]] = []
        for scope in display:
            row: list[RenderableType] = [
                _trunc(scope.scope, _SCOPE_KEY_WIDTH),
                _trunc(scope.name, _SCOPE_NAME_WIDTH),
            ]
            if group_obj:
                for spec in group_obj.tables:
                    row.append(str(scope.table_counts.get(spec.name, 0)))
            rows.append(row)

        console.print(DataTable(title=f"Custom scopes on {resolved}", columns=columns, rows=rows))

        if all_scopes or not custom_s:
            summary = f"{len(display)} scopes with custom configs on {resolved}"
        else:
            summary = (
                f"Showing {len(custom_s)} of your custom scopes "
                f"({len(all_s)} total with configs). Use --all to show all."
            )
        console.print(Notice.info(summary))

        if display:
            example = display[0].scope
            console.print()
            console.print(Hint(label="Next", command=f"nexus capture pull --scope {example}"))
            if len(display) > 1:
                console.print(
                    Hint(
                        label="Tip",
                        command="--scope x_a --scope x_b",
                        suffix="captures multiple at once",
                    )
                )

    asyncio.run(_run())


_UUID_RE = re.compile(r"^[0-9a-f]{32}$", re.IGNORECASE)


async def _resolve_scope_ids(
    scope_args: list[str],
    client: ServiceNowClient,
) -> list[str]:
    """Resolve scope keys (x_snc_*) or sys_ids to sys_ids.

    UUID args are passed through unchanged. Scope keys are resolved with a
    single direct sys_scope lookup instead of a full grouped-count discover.

    Args:
        scope_args: List of scope keys or sys_ids from --scope options.
        client: Open ServiceNowClient to use for key lookups.

    Returns:
        List of resolved sys_ids in the same order as scope_args.
    """
    keys_to_lookup = [s for s in scope_args if not _UUID_RE.match(s.replace("-", ""))]

    if not keys_to_lookup:
        return scope_args

    in_query = f"scopeIN{','.join(keys_to_lookup)}"
    rows = await client.list_records(
        "sys_scope",
        query=in_query,
        fields="sys_id,scope",
        limit=len(keys_to_lookup) + 1,
    )
    key_map = {str(r.get("scope", "")): str(r.get("sys_id", "")) for r in rows}

    resolved: list[str] = []
    for arg in scope_args:
        if _UUID_RE.match(arg.replace("-", "")):
            resolved.append(arg)
        elif arg in key_map:
            resolved.append(key_map[arg])
            console.print(Notice.info(f"Resolved {arg} -> {key_map[arg]}"))
        else:
            err_console.print(
                Notice.error(
                    f"Scope {arg!r} not found. "
                    f"Run 'nexus capture discover' to see available scopes."
                )
            )
            raise typer.Exit(1)
    return resolved


@capture_app.command("pull")
def capture_pull(
    instance: Annotated[
        str, typer.Argument(help="Instance profile name (default: configured default)")
    ] = "",
    scope: Annotated[
        list[str],
        typer.Option(help="Scope key (e.g. x_snc_my_app) or sys_id -- repeatable, from 'discover'"),
    ] = [],
    group: Annotated[str, typer.Option(help="Table group")] = AI_AUTOMATION.key,
) -> None:
    """Capture custom configurations for one or more scopes to a local archive.

    Run 'nexus capture discover' first to see scope keys.
    """
    if not scope:
        err_console.print("At least one --scope is required.")
        err_console.print("  Run 'nexus capture discover' to see your scope keys.")
        raise typer.Exit(1)

    async def _run() -> None:
        engine, client = _build_capture_engine(instance)
        resolved_instance = instance or _config_default()

        async with client:
            scope_ids = await _resolve_scope_ids(scope, client)

            with nexus_progress(console) as progress:
                task = progress.add_task("Preparing...", total=None)

                def on_progress(completed: int, total: int, message: str) -> None:
                    progress.update(
                        task,
                        description=message,
                        total=total if total > 0 else None,
                        completed=completed,
                    )

                result = await engine.capture(
                    resolved_instance, scope_ids, group, on_progress=on_progress
                )

        manifest = engine.save_archive(result)
        console.print(
            KeyValuePanel(
                title="Capture complete",
                rows=[
                    KvRow(label="Records", value=f"{manifest.record_count:,}"),
                    KvRow(label="Archive", value=str(manifest.archive_dir)),
                    KvRow(
                        label="Next",
                        value=f"nexus capture push {manifest.archive_dir}",
                    ),
                ],
            )
        )

    asyncio.run(_run())


@capture_app.command("list")
def capture_list(
    instance: Annotated[str | None, typer.Argument(help="Filter by instance")] = None,
) -> None:
    """List local capture archives."""
    archives_root = NexusPaths.from_env().archives_dir
    if not archives_root.exists():
        console.print(
            Hint(label="No archives yet", command="nexus capture pull", suffix="to capture one")
        )
        return

    rows: list[list[RenderableType]] = []
    for manifest_path in sorted(archives_root.rglob("manifest.yaml")):
        try:
            raw = _yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
            manifest = ArchiveManifest.model_validate(raw, strict=False)
        except Exception as exc:
            err_console.print(
                Notice.warn(f"Skipping corrupt manifest {manifest_path.parent}: {exc}")
            )
            continue
        if instance and manifest.instance_id != instance:
            continue
        rows.append(
            [
                manifest.instance_id,
                str(manifest.captured_at)[:19],
                str(manifest.record_count),
                _trunc(str(manifest.archive_dir), 45),
            ]
        )
    console.print(
        DataTable(
            title="Archives",
            columns=[
                DataColumn(header="Instance", width=12),
                DataColumn(header="Captured", width=20),
                DataColumn(header="Recs", width=6, justify="right"),
                DataColumn(header="Archive"),
            ],
            rows=rows,
        )
    )


@capture_app.command("push")
def capture_push(
    archive: Annotated[str, typer.Argument(help="Path to archive directory")],
    instance: Annotated[
        str, typer.Argument(help="Target instance profile (default: configured default)")
    ] = "",
    update_set: Annotated[str, typer.Option(help="Update set name")] = "NEXUS-capture",
) -> None:
    """Push a local archive into an update set on the target instance."""

    async def _run() -> None:
        engine, client = _build_capture_engine(instance)
        manifest_path = Path(archive) / "manifest.yaml"
        result = engine.load_archive(manifest_path)
        resolved_instance = instance or _config_default()
        async with client:
            ref = await engine.push_to_update_set(result, resolved_instance, update_set)
        console.print(
            KeyValuePanel(
                title="Push complete",
                rows=[
                    KvRow(label="Records", value=str(ref.record_count)),
                    KvRow(label="Update set", value=ref.name),
                    KvRow(label="sys_id", value=ref.sys_id),
                ],
            )
        )

    asyncio.run(_run())


@app.command()
def status(
    refresh: Annotated[
        bool, typer.Option("--refresh", help="Clear cached tier detection and re-detect")
    ] = False,
) -> None:
    """Show NEXUS tier and available enterprise MCP servers."""
    if refresh:
        clear_cache(TierDetector.detect)

    print_banner(console)
    detection = _detect_tier()
    capabilities = CapabilitySet.from_detection(detection)
    StatusReporter(console=console).print(detection, capabilities)


@app.command()
def reauth(
    server: Annotated[
        str | None,
        typer.Option(
            "--server",
            help="Name of the MCP server to re-authenticate (lowercase enum value, e.g. 'marketing')",
        ),
    ] = None,
) -> None:
    """Print the command to re-authenticate one or more MCP servers."""
    detection = _detect_tier()

    if server is not None:
        target = next((srv for srv in detection.needs_reauth_servers if srv.value == server), None)
        if target is None:
            err_console.print(
                Notice.error(
                    f"Server {server!r} is not currently flagged for re-auth. "
                    f"Run `nexus status --refresh` if you think this is wrong."
                )
            )
            raise typer.Exit(code=1)
        console.print(f'claude /mcp "{claude_ai_name_for(target)}"')
        return

    if not detection.needs_reauth_servers:
        console.print(Notice.info("All MCP servers authenticated. Nothing to do."))
        return

    console.print(
        KeyValuePanel(
            title="Re-auth commands",
            rows=[
                KvRow(label=srv.value, value=f'claude /mcp "{claude_ai_name_for(srv)}"')
                for srv in sorted(detection.needs_reauth_servers, key=lambda s: s.value)
            ],
        )
    )


@app.command()
def update(
    check_only: Annotated[
        bool,
        typer.Option("--check-only", help="Only report; do not install"),
    ] = False,
) -> None:
    """Manually check for updates (and install unless --check-only).

    Plain ``nexus update`` runs the same auto-update path the CLI callback
    triggers. With ``--check-only``, fetch and report without installing.
    """
    if not check_only:
        check_and_maybe_update()
        return

    current = current_version()
    if current is None:
        console.print(Notice.info("nexus-sn is not installed as a distribution; cannot check."))
        return

    info = GitHubReleasesClient().fetch_latest()
    if info is None:
        console.print(Notice.info("Could not reach GitHub. No update info available."))
        return

    try:
        if parse(info.tag_name) <= parse(current):
            console.print(Notice.info(f"Up to date ({current})"))
            return
    except InvalidVersion:
        console.print(Notice.warn(f"Latest tag {info.tag_name!r} is not a valid version; skipping"))
        return

    console.print(Notice.info(f"Update available: {current} -> {info.tag_name}"))


@app.command()
def sync() -> None:
    """Pull the latest templates from the GitHub registry."""
    console.print(Notice.info("Syncing templates -- not yet implemented."))
    console.print(Notice.info("Configure github_repo in ~/.nexus/config.yaml first."))


@app.command("templates")
def templates_cmd() -> None:
    """Browse and inspect available templates."""
    console.print(Notice.info("Template browser -- not yet implemented. Run 'nexus sync' first."))


@app.command()
def assess(
    for_template: Annotated[
        str, typer.Option("--for", help="Check readiness for a specific template")
    ] = "",
    job: Annotated[str, typer.Option("--job", help="Validate a past deployment by job ID")] = "",
) -> None:
    """Run an instance health scan or targeted assessment."""
    if for_template:
        console.print(
            Notice.info(f"Readiness check for template: {for_template!r} -- not yet implemented.")
        )
    elif job:
        console.print(
            Notice.info(f"Post-deploy validation for job: {job!r} -- not yet implemented.")
        )
    else:
        console.print(Notice.info("Instance health scan -- not yet implemented."))


@app.command()
def apply(
    template: Annotated[str, typer.Argument(help="Template name to deploy")],
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
) -> None:
    """Deploy a template to the configured ServiceNow instance."""
    console.print(
        Notice.info(f"Applying template: {template!r} (dry_run={dry_run}) -- not yet implemented.")
    )


@app.command()
def run(
    request: Annotated[str, typer.Argument(help="Free-form orchestration request")],
) -> None:
    """Free-form AI orchestration request."""
    console.print(Notice.info(f"Running: {request!r} -- not yet implemented."))


@app.command()
def rollback(
    job_id: Annotated[str, typer.Argument(help="Job ID to roll back")],
) -> None:
    """Undo a previous deployment by job ID."""
    console.print(Notice.info(f"Rolling back job: {job_id!r} -- not yet implemented."))


@app.command()
def ui() -> None:
    """Start the NiceGUI dashboard (requires pip install nexus-sn[ui])."""
    try:
        start_ui()
    except ImportError as exc:
        err_console.print(Notice.error(str(exc)))
        raise typer.Exit(code=1) from exc


if __name__ == "__main__":
    app()
