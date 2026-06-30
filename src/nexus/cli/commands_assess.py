# src/nexus/cli/commands_assess.py
# Implementation of the `nexus assess` command.
# Author: Pierre Grothe
# Date: 2026-05-19

"""`nexus assess` -- Gate 1 readiness, Gate 2 validation, or standalone health scan.

The `assess_callback` group callback in this module calls `run_assess(...)` with
collaborators that production resolves to real modules (only when no subcommand
is invoked). Tests inject fakes for everything that crosses an I/O boundary
(ruleset loader, archive reader, capture runner, apply-result loader).

Verdict-to-exit-code mapping:
    PASS  -> 0
    BLOCK -> 2 (matches InteractiveRequiredError precedent)
    ERROR -> 1
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Annotated

import typer

from nexus.assessment.context import ApplyResult, GateContext
from nexus.assessment.gates import Gate1Readiness, Gate2Validation, HealthScan
from nexus.assessment.loader import load_ruleset
from nexus.assessment.report import GateReport
from nexus.assessment.reporter import render_report
from nexus.assessment.schemas.enums import Phase
from nexus.assessment.schemas.rule import AssessmentRule
from nexus.assessment.schemas.ruleset import Ruleset
from nexus.assessment.verdict import GateVerdict
from nexus.capture.archive import ArchiveReader
from nexus.capture.models import CaptureResult
from nexus.cli.apps import assess_app
from nexus.cli.console import render_context as _render_context
from nexus.config.paths import NexusPaths
from nexus.ui.components import Notice
from nexus.ui.render_context import RenderContext

__all__ = [
    "AssessCollaborators",
    "default_collaborators",
    "run_assess",
]


RulesetsLoader = Callable[[Path], tuple[Ruleset, ...]]
ArchiveLoader = Callable[[Path], CaptureResult]
CaptureRunner = Callable[[str | None], CaptureResult]
ApplyResultLoader = Callable[[str], tuple[ApplyResult, str]]


class AssessCollaborators:
    """Wire-up bundle for the assess command body.

    Production builds default values via `default_collaborators(paths)`; tests
    construct one with fakes for the injectable callables.
    """

    __slots__ = (
        "apply_result_loader",
        "archive_loader",
        "capture_runner",
        "rulesets_loader",
    )

    def __init__(
        self,
        *,
        rulesets_loader: RulesetsLoader,
        archive_loader: ArchiveLoader,
        capture_runner: CaptureRunner,
        apply_result_loader: ApplyResultLoader,
    ) -> None:
        """Bind the four injectable callables this command needs."""
        self.rulesets_loader = rulesets_loader
        self.archive_loader = archive_loader
        self.capture_runner = capture_runner
        self.apply_result_loader = apply_result_loader


def default_collaborators(paths: NexusPaths) -> AssessCollaborators:
    """Return production wire-up of the assess command collaborators."""
    return AssessCollaborators(
        rulesets_loader=_load_rulesets_from_dir,
        archive_loader=ArchiveReader().read,
        capture_runner=_capture_runner_not_implemented,
        apply_result_loader=_apply_result_loader_not_implemented,
    )


def run_assess(
    *,
    for_template: str,
    job: str,
    live: bool,
    archive_path: Path | None,
    skip_gate2: bool,
    render_context: RenderContext,
    paths: NexusPaths,
    collaborators: AssessCollaborators,
) -> int:
    """Dispatch `nexus assess` to the appropriate gate and return an exit code.

    Args:
        for_template: Template id from --for (empty string when unset).
        job: Apply-job id from --job (empty string when unset).
        live: True when --live was provided.
        archive_path: Explicit archive path from --archive, or None.
        skip_gate2: True when --skip-gate2 was provided.
        render_context: For rendering output.
        paths: NexusPaths for default archive resolution.
        collaborators: Wire-up bundle with injectable IO collaborators.

    Returns:
        Exit code: 0 (PASS), 2 (BLOCK), 1 (ERROR or setup failure).

    Raises:
        typer.BadParameter: On mutually exclusive flag combinations.
    """
    _validate_flag_mutex(for_template=for_template, job=job, live=live, archive_path=archive_path)
    if for_template:
        return _run_gate1(
            template_id=for_template,
            live=live,
            archive_path=archive_path,
            render_context=render_context,
            paths=paths,
            collaborators=collaborators,
        )
    if job:
        return _run_gate2(
            job_id=job,
            live=live,
            archive_path=archive_path,
            skip_gate2=skip_gate2,
            render_context=render_context,
            paths=paths,
            collaborators=collaborators,
        )
    return _run_health(
        live=live,
        archive_path=archive_path,
        render_context=render_context,
        paths=paths,
        collaborators=collaborators,
    )


def _validate_flag_mutex(
    *, for_template: str, job: str, live: bool, archive_path: Path | None
) -> None:
    """Reject incompatible flag combinations with typer.BadParameter."""
    if for_template and job:
        raise typer.BadParameter("--for and --job cannot be used together")
    if live and archive_path is not None:
        raise typer.BadParameter("--live and --archive cannot be used together")


def _run_gate1(
    *,
    template_id: str,
    live: bool,
    archive_path: Path | None,
    render_context: RenderContext,
    paths: NexusPaths,
    collaborators: AssessCollaborators,
) -> int:
    """`nexus assess --for <template>` -> Gate1Readiness."""
    rulesets = collaborators.rulesets_loader(paths.templates_dir / "assessments")
    matching = _rulesets_for_template(rulesets, template_id)
    if not matching:
        render_context.console.print(
            Notice.error(f"no readiness ruleset for template {template_id!r}")
        )
        return 1
    merged = _merge_rulesets(matching, target_phase=Phase.PRE_APPLY)
    capture = _resolve_capture(
        live=live,
        archive_path=archive_path,
        render_context=render_context,
        paths=paths,
        collaborators=collaborators,
    )
    if capture is None:
        return 1
    ctx = GateContext(capture=capture, apply_result=None, phase=Phase.PRE_APPLY)
    gate = Gate1Readiness(ruleset=merged, template_id=template_id)
    return _render_and_exit(gate.evaluate(ctx), render_context)


def _run_gate2(
    *,
    job_id: str,
    live: bool,
    archive_path: Path | None,
    skip_gate2: bool,
    render_context: RenderContext,
    paths: NexusPaths,
    collaborators: AssessCollaborators,
) -> int:
    """`nexus assess --job <id>` -> Gate2Validation, or skip on --skip-gate2."""
    if skip_gate2:
        render_context.console.print(Notice.warn("Gate 2 skipped by --skip-gate2"))
        return 0
    try:
        apply_result, template_id = collaborators.apply_result_loader(job_id)
    except NotImplementedError as exc:
        render_context.console.print(Notice.error(f"Gate 2 apply-result loader: {exc}"))
        return 1
    rulesets = collaborators.rulesets_loader(paths.templates_dir / "assessments")
    matching = _rulesets_for_template(rulesets, template_id)
    if not matching:
        render_context.console.print(
            Notice.error(f"no validation ruleset for template {template_id!r}")
        )
        return 1
    merged = _merge_rulesets(matching, target_phase=Phase.POST_APPLY)
    capture = _resolve_capture(
        live=live,
        archive_path=archive_path,
        render_context=render_context,
        paths=paths,
        collaborators=collaborators,
    )
    if capture is None:
        return 1
    ctx = GateContext(capture=capture, apply_result=apply_result, phase=Phase.POST_APPLY)
    gate = Gate2Validation(ruleset=merged, template_id=template_id)
    return _render_and_exit(gate.evaluate(ctx), render_context)


def _run_health(
    *,
    live: bool,
    archive_path: Path | None,
    render_context: RenderContext,
    paths: NexusPaths,
    collaborators: AssessCollaborators,
) -> int:
    """`nexus assess` (no flags) -> HealthScan over every loaded ruleset."""
    rulesets = collaborators.rulesets_loader(paths.templates_dir / "assessments")
    if not rulesets:
        render_context.console.print(Notice.warn("no rulesets in templates/assessments/"))
        return 0
    merged = _merge_rulesets(rulesets, target_phase=Phase.STANDALONE)
    capture = _resolve_capture(
        live=live,
        archive_path=archive_path,
        render_context=render_context,
        paths=paths,
        collaborators=collaborators,
    )
    if capture is None:
        return 1
    ctx = GateContext(capture=capture, apply_result=None, phase=Phase.STANDALONE)
    gate = HealthScan(ruleset=merged)
    return _render_and_exit(gate.evaluate(ctx), render_context)


def _resolve_capture(
    *,
    live: bool,
    archive_path: Path | None,
    render_context: RenderContext,
    paths: NexusPaths,
    collaborators: AssessCollaborators,
) -> CaptureResult | None:
    """Resolve a CaptureResult from --live, explicit --archive, or default archive."""
    if live:
        try:
            return collaborators.capture_runner(None)
        except NotImplementedError as exc:
            render_context.console.print(Notice.error(f"--live capture runner: {exc}"))
            return None
    target = archive_path or _default_archive_path(paths)
    if target is None:
        render_context.console.print(
            Notice.error("no archive found; run `nexus capture` first or pass --live")
        )
        return None
    return collaborators.archive_loader(target)


def _default_archive_path(paths: NexusPaths) -> Path | None:
    """Pick the newest manifest.yaml under paths.archives_dir, or None."""
    if not paths.archives_dir.is_dir():
        return None
    candidates = sorted(paths.archives_dir.rglob("manifest.yaml"), key=lambda p: p.stat().st_mtime)
    if not candidates:
        return None
    return candidates[-1]


def _rulesets_for_template(rulesets: tuple[Ruleset, ...], template_id: str) -> tuple[Ruleset, ...]:
    """Filter rulesets whose applies_to includes the template or "*"."""
    return tuple(rs for rs in rulesets if template_id in rs.applies_to or "*" in rs.applies_to)


def _merge_rulesets(rulesets: tuple[Ruleset, ...], *, target_phase: Phase) -> Ruleset:
    """Combine multiple rulesets into one synthetic Ruleset filtered to target_phase."""
    merged_rules: list[AssessmentRule] = []
    for rs in rulesets:
        merged_rules.extend(rule for rule in rs.rules if rule.phase is target_phase)
    if not merged_rules:
        merged_rules = [rule for rs in rulesets for rule in rs.rules]
    return Ruleset(
        id="__merged__",
        version="0.0.0",
        description="merged assessment ruleset",
        applies_to=("*",),
        rules=tuple(merged_rules),
    )


def _render_and_exit(report: GateReport, render_context: RenderContext) -> int:
    """Render the GateReport and return the verdict-derived exit code."""
    render_report(report, render_context)
    match report.verdict:
        case GateVerdict.PASS:
            return 0
        case GateVerdict.BLOCK:
            return 2
        case GateVerdict.ERROR:
            return 1
        case _:  # pragma: no cover -- exhaustive over GateVerdict
            raise AssertionError(f"unreachable verdict: {report.verdict!r}")


def _load_rulesets_from_dir(directory: Path) -> tuple[Ruleset, ...]:
    """Default rulesets_loader: walk `directory/*.yaml` and load each via load_ruleset."""
    if not directory.is_dir():
        return ()
    return tuple(load_ruleset(path) for path in sorted(directory.glob("*.yaml")))


def _capture_runner_not_implemented(scope_hint: str | None) -> CaptureResult:
    """Default `--live` capture-runner stub. Template Library epic populates this."""
    del scope_hint
    raise NotImplementedError(
        "live capture in `nexus assess` is not wired yet; "
        "use `nexus capture` then `nexus assess --archive <path>`"
    )


def _apply_result_loader_not_implemented(job_id: str) -> tuple[ApplyResult, str]:
    """Default --job loader stub. Template Library epic populates this."""
    del job_id
    raise NotImplementedError(
        "apply-job log reader is not wired yet; ApplyEngine ships in 2026.06-template-library"
    )


@assess_app.callback(invoke_without_command=True)
def assess_callback(
    ctx: typer.Context,
    for_template: Annotated[
        str, typer.Option("--for", help="Check readiness for a specific template")
    ] = "",
    job: Annotated[str, typer.Option("--job", help="Validate a past deployment by job ID")] = "",
    live: Annotated[
        bool, typer.Option("--live", help="Re-capture from the live instance instead of an archive")
    ] = False,
    archive: Annotated[
        str, typer.Option("--archive", help="Path to a capture-archive manifest.yaml")
    ] = "",
    skip_gate2: Annotated[
        bool,
        typer.Option("--skip-gate2", help="Acknowledge that Gate 2 verification is being skipped"),
    ] = False,
) -> None:
    """Run an instance health scan or targeted assessment.

    With no subcommand this runs the gate/health path; subcommands (inventory,
    migration) short-circuit it via the ``invoked_subcommand`` guard.
    """
    if ctx.invoked_subcommand is not None:
        return
    paths = NexusPaths.from_env()
    archive_path = Path(archive) if archive else None
    exit_code = run_assess(
        for_template=for_template,
        job=job,
        live=live,
        archive_path=archive_path,
        skip_gate2=skip_gate2,
        render_context=_render_context,
        paths=paths,
        collaborators=default_collaborators(paths),
    )
    raise typer.Exit(exit_code)
