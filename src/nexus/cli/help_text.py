# src/nexus/cli/help_text.py
# Command help text + entry helpers extracted from cli.py for ADR-023 sizing.
# Author: Pierre Grothe
# Date: 2026-05-16
"""Static help-text catalog rendered by the CLI two-box discovery view.

Extracted from ``cli.py`` to keep that module marching toward the
800-line cap defined by ADR-023. Everything here is pure data plus
two trivial constructor / projection helpers (`help_entry`,
`guide_items`). No side effects, no Typer imports, no console
references -- safe to import from anywhere.
"""

from __future__ import annotations

from nexus.ui import CommandHelpEntry

__all__ = [
    "CAPTURE_HELP",
    "CAPTURE_PARENT",
    "INSTANCE_HELP",
    "INSTANCE_PARENT",
    "NEXUS_PARENT",
    "PLUGINS_BASELINES_HELP",
    "PLUGINS_BASELINES_PARENT",
    "PLUGINS_HELP",
    "PLUGINS_PARENT",
    "PLUGINS_RECOMMEND_HELP",
    "PLUGINS_RECOMMEND_PARENT",
    "SCHEMA_HELP",
    "SCHEMA_PARENT",
    "TOP_LEVEL_HELP",
    "guide_items",
    "help_entry",
]


def help_entry(command: str, purpose: str, example: str) -> CommandHelpEntry:
    """Build a CommandHelpEntry without restating Pydantic keywords below.

    Args:
        command: Command name as typed by the user (e.g. ``"plugins scan"``).
        purpose: One-or-two-sentence description shown in the discovery view.
        example: A runnable example invocation.

    Returns:
        The populated CommandHelpEntry.
    """
    return CommandHelpEntry(command=command, purpose=purpose, example=example)


def guide_items(entries: list[CommandHelpEntry]) -> list[tuple[str, str]]:
    """Project a CommandHelpEntry list into ``(command, short_description)`` pairs.

    The short description is the first sentence of ``purpose`` (split on
    ``". "``) so the Box-2 listing stays single-line per row.

    Args:
        entries: Help entries to project.

    Returns:
        One ``(command, first_sentence_of_purpose)`` pair per entry, in order.
    """
    out: list[tuple[str, str]] = []
    for entry in entries:
        first = entry.purpose.split(". ", 1)[0].rstrip(".")
        out.append((entry.command, first))
    return out


PLUGINS_PARENT = help_entry(
    "plugins",
    "Inspect the plugin inventory of registered instances -- dependencies, "
    "advisories, drift, AI recommendations, and more.",
    "nexus plugins list --product ITSM",
)

INSTANCE_PARENT = help_entry(
    "instance",
    "Manage registered ServiceNow instances: register, connect, refresh, list, "
    "and switch the default profile.",
    "nexus instance register prod",
)

CAPTURE_PARENT = help_entry(
    "capture",
    "Bidirectional ServiceNow config transport: discover custom scopes, pull "
    "them as YAML archives, push archives back as update sets.",
    "nexus capture discover --instance prod",
)

SCHEMA_PARENT = help_entry(
    "schema",
    "Reverse-engineer ServiceNow table schemas: list available products, then "
    "generate an ERD -- optionally as an SVG or PNG image via Kroki.",
    "nexus schema erd HAM --image svg",
)

PLUGINS_RECOMMEND_PARENT = help_entry(
    "plugins recommend",
    "AI-backed plugin recommendations (currently: which plugins are safest to deactivate).",
    "nexus plugins recommend deactivate",
)

PLUGINS_BASELINES_PARENT = help_entry(
    "plugins baselines",
    "Manage named plugin drift baselines. Drift is computed against the named "
    "baseline; multiple baselines can coexist per instance.",
    "nexus plugins baselines list",
)

NEXUS_PARENT = help_entry(
    "nexus",
    "NEXUS -- ServiceNow AI architect agent. Capture, assess, and act on "
    "ServiceNow instances from the command line.",
    "nexus instance list",
)


PLUGINS_HELP: list[CommandHelpEntry] = [
    help_entry(
        "list",
        "List every plugin and scoped app currently installed on the default "
        "instance. Filter by product family, source (servicenow|store|custom), "
        "or activation state to narrow the view.",
        "nexus plugins list --product ITSM --state active",
    ),
    help_entry(
        "info <plugin_id>",
        "Drill into one plugin: full version, vendor, activation state, "
        "direct dependencies, and source table (v_plugin vs sys_store_app vs "
        "App Manager).",
        "nexus plugins info com.snc.incident",
    ),
    help_entry(
        "export",
        "Dump the captured inventory to disk as YAML (default) or CSV. "
        "Useful for sharing snapshots with auditors or feeding external tools.",
        "nexus plugins export --format csv --out plugins.csv",
    ),
    help_entry(
        "diff <a> <b>",
        "Compare plugin inventories across two profiles. Surfaces "
        "only-in-A, only-in-B, version mismatches, and state mismatches.",
        "nexus plugins diff dev prod --status version_mismatch",
    ),
    help_entry(
        "promote <src> --to <dst>",
        "Generate an additive YAML action plan that brings <dst> up to "
        "match <src>: installs missing apps, upgrades older versions. "
        "Read-only -- the plan is reviewed before any apply step.",
        "nexus plugins promote dev --to prod --out promote-dev-to-prod.yaml",
    ),
    help_entry(
        "outdated",
        "List every plugin / app where a newer version is available "
        "(brew/apt-style read-only). Optional --family filter and --queue "
        "YAML export. Use 'nexus plugins upgrade [--family X]' to apply.",
        "nexus plugins outdated --queue pending.yaml",
    ),
    help_entry(
        "advisories",
        "Report EOL / CVE / license findings for the inventory. Filter by "
        "type or minimum severity. --strict exits 1 if any finding remains "
        "after filters (CI gating).",
        "nexus plugins advisories --severity high --strict",
    ),
    help_entry(
        "deactivate <plugin-id>",
        "Deactivate a plugin on the resolved instance. Mandatory impact "
        "gate blocks the op when reverse-deps exist; --force bypasses with a "
        "type-the-plugin-id confirmation.",
        "nexus plugins deactivate com.acme.app",
    ),
    help_entry(
        "defer <id> <type> <details>",
        "Mute a single EOL/CVE/license finding with a written reason. "
        "Deferred findings are hidden from 'advisories' until "
        "--include-deferred is passed. Per-instance, persisted to disk.",
        "nexus plugins defer com.acme.helper cve 'CVE-2024-1234' --reason 'patch in next sprint'",
    ),
    help_entry(
        "undo-defer <id> <type> <details>",
        "Reverse a previous 'defer'. The finding reappears in normal "
        "'advisories' output. Match the original plugin id + type + details exactly.",
        "nexus plugins undo-defer com.acme.helper cve 'CVE-2024-1234'",
    ),
    help_entry(
        "list-deferred",
        "Audit view: every deferred finding on an instance with its reason "
        "and the date it was deferred. Use when reviewing whether old "
        "deferrals are still justified.",
        "nexus plugins list-deferred --format json",
    ),
    help_entry(
        "impact <plugin_id>",
        "Pre-deactivation safety check: walks reverse dependencies, counts "
        "records owned by the plugin's scope, and scans cross-scope FK "
        "references. --live forces re-query of record counts.",
        "nexus plugins impact com.snc.incident --live",
    ),
    help_entry(
        "orphans",
        "Find plugins safe to deactivate at a glance: no dependents AND "
        "zero scope-owned records. Filter by state to narrow further.",
        "nexus plugins orphans --state inactive",
    ),
    help_entry(
        "drift",
        "Compare the live inventory against a named baseline. Use --ack "
        "to snapshot the current state as a new baseline. Multiple baselines "
        "can coexist (e.g. preprod, prod, golden-image).",
        "nexus plugins drift --baseline preprod --strict",
    ),
    help_entry(
        "explain <plugin_id>",
        "Ask the bundled AI to explain what a plugin does, what depends on "
        "it, and whether keeping it makes sense. Refuses 'drop' verdicts "
        "for core ITSM/platform plugins regardless of evidence.",
        "nexus plugins explain com.snc.knowledge",
    ),
    help_entry(
        "roadmap",
        "Ask the AI to draft an ordered remediation plan from your "
        "advisories + orphans + deferred overrides. Useful as input to a "
        "quarterly plugin-hygiene review.",
        "nexus plugins roadmap",
    ),
    help_entry(
        "recommend deactivate",
        "AI-curated short list of plugins safest to turn off, with one-line "
        "rationale per candidate. Excludes anything load-bearing.",
        "nexus plugins recommend deactivate",
    ),
    help_entry(
        "activate <plugin-id>",
        "Activate an installed plugin on the resolved instance. Blocks until SN "
        "reports terminal status.",
        "nexus plugins activate com.snc.discovery",
    ),
    help_entry(
        "apply <plan.yaml>",
        "Execute a PromotionPlan YAML produced by `nexus plugins promote`. Rolls "
        "back partial failures.",
        "nexus plugins apply promote-dev-to-prod.yaml",
    ),
    help_entry(
        "install <plugin-id>",
        "Install a plugin on the resolved instance. Shows the SN dependency "
        "cascade preview and blocks until terminal status.",
        "nexus plugins install com.snc.discovery",
    ),
    help_entry(
        "uninstall <plugin-id>",
        "Uninstall a non-base plugin on the resolved instance. Base "
        "ServiceNow plugins (source=='servicenow') are refused even with "
        "--force.",
        "nexus plugins uninstall com.acme.app",
    ),
    help_entry(
        "upgrade [<plugin-id>|--family X|--all] [--to V]",
        "Upgrade plugins on the resolved instance. Bare = every pending "
        "(brew/apt-style). --family filters. --all upgrades everything pending. "
        "Offering plugins (sn_hs_*, sn_fs_*) install via the SN UI only.",
        "nexus plugins upgrade --family irm --yes",
    ),
    help_entry(
        "baselines list",
        "Show every named drift baseline saved for an instance, with "
        "captured timestamp and plugin count.",
        "nexus plugins baselines list",
    ),
    help_entry(
        "baselines delete <name>",
        "Remove a stored baseline. Pass --yes to skip the confirmation prompt.",
        "nexus plugins baselines delete preprod --yes",
    ),
]

CAPTURE_HELP: list[CommandHelpEntry] = [
    help_entry(
        "discover",
        "Walk every scope on the instance and surface the ones with custom "
        "AI / automation configs (skills, flows, virtual agent topics). "
        "Use --all to include built-in scopes; default hides them.",
        "nexus capture discover",
    ),
    help_entry(
        "pull --scope <key>",
        "Snapshot one or more scopes to a versioned YAML archive on disk. "
        "Captured artifacts include ai_skill, sys_hub_flow, virtual agent "
        "topics, and related child records.",
        "nexus capture pull --scope x_company_app --scope x_company_helper",
    ),
    help_entry(
        "list",
        "Show every archive previously captured on this machine, with "
        "source instance, captured timestamp, and scope counts.",
        "nexus capture list",
    ),
    help_entry(
        "push <archive>",
        "Replay a captured archive into a sys_update_set on the target "
        "instance. The set name defaults to NEXUS-capture; override with "
        "--update-set.",
        "nexus capture push archives/2026-05-12_dev/ prod",
    ),
]

SCHEMA_HELP: list[CommandHelpEntry] = [
    help_entry(
        "products",
        "List the available schema products and the ServiceNow scopes each "
        "covers. Product keys, acronyms, and full names are all accepted by 'erd'.",
        "nexus schema products",
    ),
    help_entry(
        "erd <product> [product2]",
        "Reverse-engineer one or two products into a Mermaid ERD. Accepts key, "
        "acronym, or full name. Pass --image svg|png to also export a diagram image.",
        "nexus schema erd HAM ITSM --image svg",
    ),
]

PLUGINS_RECOMMEND_HELP: list[CommandHelpEntry] = [
    help_entry(
        "deactivate",
        "Ask the bundled AI for a short list of plugins that look safe to "
        "turn off based on zero dependencies, zero records, and absence of "
        "advisories. Always includes a 'Watch out' section.",
        "nexus plugins recommend deactivate",
    ),
]

PLUGINS_BASELINES_HELP: list[CommandHelpEntry] = [
    help_entry(
        "list",
        "Show every named drift baseline saved for an instance, with "
        "captured timestamp and plugin count.",
        "nexus plugins baselines list",
    ),
    help_entry(
        "delete <name>",
        "Remove a stored baseline. Pass --yes to skip the confirmation prompt.",
        "nexus plugins baselines delete preprod --yes",
    ),
]

INSTANCE_HELP: list[CommandHelpEntry] = [
    help_entry(
        "register <profile>",
        "Add a new SN instance and store its credentials in the OS keychain. "
        "Interactive: prompts for URL, username, password. OAuth app is "
        "auto-provisioned via the SN REST API -- no manual config needed.",
        "nexus instance register prod",
    ),
    help_entry(
        "connect [profile]",
        "Verify the OAuth access token is still valid; refresh it via the "
        "refresh-token grant if near expiry. Run before any command that "
        "talks to SN if you're unsure the token is still live.",
        "nexus instance connect prod",
    ),
    help_entry(
        "refresh [profile]",
        "Pull a fresh artifact + plugin inventory from SN and replace the "
        "cached snapshot on disk. Required before drift, advisories, or "
        "updates commands give meaningful answers.",
        "nexus instance refresh prod",
    ),
    help_entry(
        "status [profile]",
        "Show metadata + the latest snapshot summary for one instance: SN "
        "version, token expiry, artifact / plugin counts, last refresh time.",
        "nexus instance status prod",
    ),
    help_entry(
        "use [profile]",
        "Set the default instance used when --instance is omitted. With no "
        "argument, opens an interactive picker (or auto-promotes when only "
        "one instance is registered).",
        "nexus instance use prod",
    ),
    help_entry(
        "delete <profile>",
        "Permanently remove a profile and its keychain credentials. If the "
        "deleted profile was the default and exactly one other instance "
        "remains, the survivor is promoted automatically.",
        "nexus instance delete dev --force",
    ),
    help_entry(
        "list",
        "Tabular view of every registered instance with profile name, URL, "
        "SN version, token state (valid / EXPIRED / N min left), and last "
        "successful connection time. Default instance marked with '*'.",
        "nexus instance list",
    ),
    help_entry(
        "diagnose-roles [profile]",
        "Probe the SN Table API endpoints NEXUS reads (sys_user, v_plugin, "
        "sys_store_app, ...) and report HTTP status + SN-side error detail "
        "per table. Use this when plugin scans warn about 403s -- the "
        "detail column names the exact role/scope SN expects.",
        "nexus instance diagnose-roles prod",
    ),
]

TOP_LEVEL_HELP: list[CommandHelpEntry] = [
    help_entry(
        "status",
        "One-page dashboard: NEXUS identity, detected Claude tier, MCP "
        "integration availability, auto-update status. Run this first when "
        "something feels off.",
        "nexus status",
    ),
    help_entry(
        "instance",
        "Manage registered SN instances -- register, connect, refresh, "
        "switch the default. Most subcommands accept [profile] and fall "
        "back to the default when omitted.",
        "nexus instance list",
    ),
    help_entry(
        "capture",
        "Bidirectional SN config transport: discover custom scopes, pull "
        "them to YAML on disk, push archived YAML back as update sets. "
        "Workhorse command for dev -> test -> prod promotion.",
        "nexus capture discover",
    ),
    help_entry(
        "schema",
        "Reverse-engineer ServiceNow table schemas into Mermaid ERDs",
        "nexus schema erd doc-designer --image svg",
    ),
    help_entry(
        "plugins",
        "Everything about the plugin inventory: list, diff, advisories, "
        "drift, impact analysis, AI recommendations. Each subcommand has "
        "its own themed help when run without arguments.",
        "nexus plugins list",
    ),
    help_entry(
        "reauth",
        "Print the one-shot commands needed to re-authenticate any Claude "
        "MCP server flagged by the local cache. No-op when all servers are "
        "healthy.",
        "nexus reauth",
    ),
    help_entry(
        "update",
        "Check GitHub Releases for a newer NEXUS version. By default fetches "
        "and installs the wheel via pip; --check-only just reports.",
        "nexus update --check-only",
    ),
    help_entry(
        "setup",
        "First-run wizard: probes the OS keychain, then either registers your "
        "first instance or shows a summary of what is already configured. "
        "Idempotent -- safe to re-run; surfaces corrupted profiles and runs "
        "inline re-auth when a profile is missing its tokens.",
        "nexus setup",
    ),
    help_entry(
        "sync",
        "Pull the template catalog from the configured GitHub registry "
        "(reads preferences.github_repo / github_branch from "
        "~/.nexus/config.yaml). Fail-fast on missing or malformed config.",
        "nexus sync",
    ),
    help_entry(
        "templates",
        "Show the cached template catalog as a table (read-only). Run "
        "'nexus sync' first to populate the cache.",
        "nexus templates",
    ),
    help_entry(
        "assess",
        "Assess instances and plan replatform migrations. Bare 'assess' runs "
        "a Gate 1/Gate 2 health scan against a captured archive; 'inventory' "
        "classifies one instance's custom config into use cases; 'migration' "
        "diffs two instances into a DONE/TODO replatform checklist.",
        "nexus assess migration --from old-prod --to new-prod --out checklist.md",
    ),
    help_entry(
        "migrate",
        "Curate a selective migration. 'select' seeds a git-reviewed "
        "Selection YAML from a replatform checklist, one undecided row per "
        "checklist item, ready for a consultant to curate include/exclude "
        "dispositions.",
        "nexus migrate select --from-checklist checklist.json --out selection.yaml",
    ),
    help_entry(
        "apply <template>",
        "Deploy a template to the configured ServiceNow instance (stub).",
        "nexus apply incident-tuner",
    ),
    help_entry(
        "run <request>",
        "Free-form AI orchestration request (stub).",
        "nexus run 'reduce P3 incident backlog'",
    ),
    help_entry(
        "rollback <job_id>",
        "Undo a previous deployment by job ID (stub).",
        "nexus rollback job-1234",
    ),
    help_entry(
        "ui",
        "Start the NiceGUI dashboard (requires pip install nexus-sn[ui]).",
        "nexus ui",
    ),
]
