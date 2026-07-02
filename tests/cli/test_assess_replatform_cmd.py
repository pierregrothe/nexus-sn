# tests/cli/test_assess_replatform_cmd.py
# Tests for assess inventory/migration command logic (Story 06).
# Author: Pierre Grothe
# Date: 2026-06-29

"""run_inventory / run_migration / parse_scope_aliases via an injected builder."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path

import pytest
import typer
from rich.console import Console
from typer.testing import CliRunner

from nexus.cli import commands_assess_replatform
from nexus.cli.apps import app
from nexus.cli.commands_assess_replatform import (
    ReplatformCollaborators,
    _merge_manifests,
    _ref_value,
    parse_domain_map,
    parse_scope_aliases,
    resolve_groups,
    run_inventory,
    run_migration,
)
from nexus.replatform.models import UseCaseInventory
from nexus.ui.capabilities import ColorDepth, RenderProfile, TerminalCapabilities
from nexus.ui.render_context import RenderContext
from nexus.ui.theme import NEXUS_THEME
from tests.fakes.replatform import (
    make_scope_manifest,
    make_use_case,
    make_use_case_inventory,
    make_workflow_ref,
)


@dataclass(slots=True)
class _FixedInventory:
    by_profile: dict[str, UseCaseInventory]

    def __call__(self, profile: str) -> UseCaseInventory:
        return self.by_profile[profile]


def _plain_ctx(buf: StringIO) -> RenderContext:
    console = Console(file=buf, width=120, record=True, theme=NEXUS_THEME, force_terminal=False)
    caps = TerminalCapabilities(
        is_tty=False,
        is_ci=False,
        color_depth=ColorDepth.NONE,
        cols=120,
        rows=40,
        legacy_windows=False,
        term_program="",
        is_dumb_terminal=False,
        is_multiplexer=False,
        no_color_env=False,
        forced_plain=True,
        supports_hyperlinks=False,
    )
    return RenderContext(console=console, caps=caps, profile=RenderProfile.PLAIN)


def _itsm_inventory(profile: str, names: tuple[str, ...]) -> UseCaseInventory:
    workflows = tuple(make_workflow_ref(scope="x_app", name=n) for n in names)
    return make_use_case_inventory(
        profile=profile,
        use_cases=(make_use_case(key="x_app", domain="ITSM", workflows=workflows),),
    )


def test_run_inventory_prints_summary_and_writes_json(tmp_path: Path) -> None:
    inv = _itsm_inventory("prod", ("Alpha",))
    collaborators = ReplatformCollaborators(build_inventory=_FixedInventory({"prod": inv}))
    buf = StringIO()
    out = tmp_path / "inv.json"
    code = run_inventory(
        profile="prod", out=out, render_context=_plain_ctx(buf), collaborators=collaborators
    )
    assert code == 0
    assert "ITSM" in buf.getvalue()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["profile"] == "prod"


def test_run_inventory_without_out_writes_no_file() -> None:
    inv = _itsm_inventory("prod", ("Alpha",))
    collaborators = ReplatformCollaborators(build_inventory=_FixedInventory({"prod": inv}))
    buf = StringIO()
    code = run_inventory(
        profile="prod", out=None, render_context=_plain_ctx(buf), collaborators=collaborators
    )
    assert code == 0
    assert "prod" in buf.getvalue()


def test_run_migration_renders_checklist_and_writes_markdown(tmp_path: Path) -> None:
    source = _itsm_inventory("old", ("Alpha", "Beta"))
    target = _itsm_inventory("new", ("Alpha",))
    collaborators = ReplatformCollaborators(
        build_inventory=_FixedInventory({"old": source, "new": target})
    )
    buf = StringIO()
    out = tmp_path / "checklist.md"
    code = run_migration(
        from_profile="old",
        to_profile="new",
        aliases=(),
        out=out,
        render_context=_plain_ctx(buf),
        collaborators=collaborators,
    )
    assert code == 0
    assert "TODO" in buf.getvalue()
    content = out.read_text(encoding="utf-8")
    assert "- [x]" in content
    assert "- [ ]" in content


def test_run_migration_applies_scope_alias(tmp_path: Path) -> None:
    src_wf = make_workflow_ref(scope="x_oldcorp", name="Intake")
    tgt_wf = make_workflow_ref(scope="x_newcorp", name="Intake")
    source = make_use_case_inventory(
        profile="old", use_cases=(make_use_case(key="x_oldcorp", workflows=(src_wf,)),)
    )
    target = make_use_case_inventory(
        profile="new", use_cases=(make_use_case(key="x_newcorp", workflows=(tgt_wf,)),)
    )
    collaborators = ReplatformCollaborators(
        build_inventory=_FixedInventory({"old": source, "new": target})
    )
    buf = StringIO()
    code = run_migration(
        from_profile="old",
        to_profile="new",
        aliases=(("x_oldcorp", "x_newcorp"),),
        out=None,
        render_context=_plain_ctx(buf),
        collaborators=collaborators,
    )
    assert code == 0
    assert "DONE" in buf.getvalue()
    assert "EXTRA" not in buf.getvalue()


def test_parse_scope_aliases_parses_pairs() -> None:
    assert parse_scope_aliases(["a=b", "c=d"]) == (("a", "b"), ("c", "d"))


def test_parse_scope_aliases_rejects_missing_equals() -> None:
    with pytest.raises(typer.BadParameter):
        parse_scope_aliases(["nope"])


def test_parse_domain_map_returns_none_when_omitted() -> None:
    assert parse_domain_map("") is None


def test_parse_domain_map_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(typer.BadParameter):
        parse_domain_map(str(tmp_path / "absent.yaml"))


def test_ref_value_extracts_value_from_reference_dict() -> None:
    assert _ref_value({"value": "abc123", "link": "https://x"}) == "abc123"


def test_ref_value_passes_through_plain_string() -> None:
    assert _ref_value("plain") == "plain"


def test_ref_value_handles_none() -> None:
    assert _ref_value(None) == ""


def test_assess_inventory_command_routes_profile_and_writes_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NEXUS_AUTO_UPDATE", "0")
    seen: list[str] = []
    inv = _itsm_inventory("prod", ("Alpha",))

    def fake_factory(_paths: object, **_kwargs: object) -> ReplatformCollaborators:
        def build(profile: str) -> UseCaseInventory:
            seen.append(profile)
            return inv

        return ReplatformCollaborators(build_inventory=build)

    monkeypatch.setattr(
        commands_assess_replatform, "default_replatform_collaborators", fake_factory
    )
    out = tmp_path / "inv.json"
    result = CliRunner().invoke(app, ["assess", "inventory", "prod", "--out", str(out)])
    assert result.exit_code == 0
    # The positional `profile` argument routed through to the inventory builder.
    assert seen == ["prod"]
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["profile"] == "prod"


def test_assess_migration_command_routes_options_and_writes_markdown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NEXUS_AUTO_UPDATE", "0")
    seen: list[str] = []
    src_wf = make_workflow_ref(scope="x_oldcorp", name="Intake")
    tgt_wf = make_workflow_ref(scope="x_newcorp", name="Intake")
    source = make_use_case_inventory(
        profile="old", use_cases=(make_use_case(key="x_oldcorp", workflows=(src_wf,)),)
    )
    target = make_use_case_inventory(
        profile="new", use_cases=(make_use_case(key="x_newcorp", workflows=(tgt_wf,)),)
    )
    by_profile = {"old": source, "new": target}

    def fake_factory(_paths: object, **_kwargs: object) -> ReplatformCollaborators:
        def build(profile: str) -> UseCaseInventory:
            seen.append(profile)
            return by_profile[profile]

        return ReplatformCollaborators(build_inventory=build)

    monkeypatch.setattr(
        commands_assess_replatform, "default_replatform_collaborators", fake_factory
    )
    out = tmp_path / "checklist.md"
    result = CliRunner().invoke(
        app,
        [
            "assess",
            "migration",
            "--from",
            "old",
            "--to",
            "new",
            "--scope-alias",
            "x_oldcorp=x_newcorp",
            "--out",
            str(out),
        ],
    )
    assert result.exit_code == 0
    # `--from`/`--to` bound in order; the source is diffed against the target.
    assert seen == ["old", "new"]
    content = out.read_text(encoding="utf-8")
    # `--scope-alias` bound: the renamed target workflow matches the source, so it
    # reads DONE (checked box) with nothing left over as EXTRA.
    assert "- [x]" in content
    assert "EXTRA" not in content


def test_run_inventory_warns_on_skipped_tables() -> None:
    buf = StringIO()
    inv = make_use_case_inventory(profile="dev", skipped_tables=("ai_skill",))
    collaborators = ReplatformCollaborators(build_inventory=lambda _p: inv)
    code = run_inventory(
        profile="dev", out=None, render_context=_plain_ctx(buf), collaborators=collaborators
    )
    assert code == 0
    assert "tables absent on dev" in buf.getvalue()
    assert "ai_skill" in buf.getvalue()


def test_run_migration_warns_on_skipped_tables_per_side() -> None:
    buf = StringIO()
    by_profile = {
        "old": make_use_case_inventory(profile="old", skipped_tables=("ai_skill",)),
        "new": make_use_case_inventory(profile="new", use_cases=()),
    }
    collaborators = ReplatformCollaborators(build_inventory=lambda p: by_profile[p])
    code = run_migration(
        from_profile="old",
        to_profile="new",
        aliases=(),
        out=None,
        render_context=_plain_ctx(buf),
        collaborators=collaborators,
    )
    assert code == 0
    assert "tables absent on old" in buf.getvalue()


def test_resolve_groups_defaults_to_all_registered_groups() -> None:
    groups = resolve_groups([])
    assert tuple(g.key for g in groups) == ("ai_automation", "developer_platform")


def test_resolve_groups_rejects_unknown_key() -> None:
    with pytest.raises(typer.BadParameter, match="unknown table group"):
        resolve_groups(["nope"])


def test_resolve_groups_with_explicit_keys_returns_cli_order() -> None:
    groups = resolve_groups(["developer_platform", "ai_automation"])
    assert tuple(g.key for g in groups) == ("developer_platform", "ai_automation")


def test_merge_manifests_unions_scopes_by_sys_id() -> None:
    ts = datetime(2026, 7, 1, 12, 0, 0, tzinfo=UTC)
    a = make_scope_manifest(scopes={"s1": "x_app"}, captured_at=ts)
    b = make_scope_manifest(scopes={"s1": "x_app", "s2": "x_other"}, captured_at=ts)
    merged = _merge_manifests((a, b))
    assert tuple(e.sys_id for e in merged.scopes) == ("s1", "s2")
