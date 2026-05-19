# src/nexus/cli/commands_apply.py
# Implementation of the `nexus apply <template>` command.
# Author: Pierre Grothe
# Date: 2026-05-19

"""`nexus apply` orchestrator: Gate 1 -> ApplyEngine -> Gate 2.

The Typer command body in `commands_top.py` calls `run_apply(...)` with
collaborators that production resolves to real modules. Tests inject
fakes for every I/O boundary.

Verdict-to-exit code mapping (matches Assessment Story 06):
    PASS  -> 0
    BLOCK -> 2
    ERROR -> 1
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path

from nexus.assessment.context import ApplyResult, GateContext
from nexus.assessment.gates import Gate1Readiness, Gate2Validation
from nexus.assessment.loader import load_ruleset
from nexus.assessment.report import GateReport
from nexus.assessment.reporter import render_report
from nexus.assessment.schemas.enums import Phase
from nexus.assessment.schemas.rule import AssessmentRule
from nexus.assessment.schemas.ruleset import Ruleset
from nexus.assessment.verdict import GateVerdict
from nexus.capture.models import CaptureResult
from nexus.config.paths import NexusPaths
from nexus.templates.apply import ApplyEngine
from nexus.templates.errors import ScopeNotFoundError, TemplateLoadError
from nexus.ui.components import Notice
from nexus.ui.render_context import RenderContext

__all__ = [
    "ApplyCollaborators",
    "default_apply_collaborators",
    "run_apply",
]


RulesetsLoader = Callable[[Path], tuple[Ruleset, ...]]
CaptureRunner = Callable[[str | None], CaptureResult]
ApplyEngineFactory = Callable[[], ApplyEngine]


class ApplyCollaborators:
    """Wire-up bundle for the apply CLI command."""

    __slots__ = (
        "apply_engine_factory",
        "capture_runner",
        "rulesets_loader",
    )

    def __init__(
        self,
        *,
        rulesets_loader: RulesetsLoader,
        capture_runner: CaptureRunner,
        apply_engine_factory: ApplyEngineFactory,
    ) -> None:
        """Bind the three injectable callables this command needs."""
        self.rulesets_loader = rulesets_loader
        self.capture_runner = capture_runner
        self.apply_engine_factory = apply_engine_factory


def default_apply_collaborators(paths: NexusPaths) -> ApplyCollaborators:
    """Return production wire-up of the apply collaborators."""
    del paths
    return ApplyCollaborators(
        rulesets_loader=_load_rulesets_from_dir,
        capture_runner=_capture_runner_not_implemented,
        apply_engine_factory=_apply_engine_factory_not_implemented,
    )


def _load_rulesets_from_dir(directory: Path) -> tuple[Ruleset, ...]:
    """Default rulesets_loader: walk `directory/*.yaml` and load each."""
    if not directory.is_dir():
        return ()
    return tuple(load_ruleset(path) for path in sorted(directory.glob("*.yaml")))


def run_apply(
    *,
    template_id: str,
    scope_override: str,
    force: bool,
    skip_gate2: bool,
    render_context: RenderContext,
    paths: NexusPaths,
    collaborators: ApplyCollaborators,
) -> int:
    """Dispatch `nexus apply <template_id>` end-to-end.

    Args:
        template_id: Template directory name under `paths.templates_dir`.
        scope_override: When non-empty, overrides the template's
            declared `target_scope` (passed to the live capture step
            and to ApplyEngine via env or future kwarg).
        force: When True, skip Gate 1 BLOCK verdict. ERROR still aborts.
        skip_gate2: When True, do not recapture or run Gate 2 after apply.
        render_context: For rendering output.
        paths: NexusPaths for template directory resolution.
        collaborators: Wire-up bundle.

    Returns:
        Exit code: 0 (PASS), 2 (BLOCK), 1 (ERROR or setup failure).
    """
    template_path = _resolve_template_path(template_id, paths)
    if template_path is None:
        render_context.console.print(
            Notice.error(f"template id {template_id!r} not found in templates_dir")
        )
        return 1

    target_scope = scope_override or _detect_target_scope(template_path)
    rulesets = collaborators.rulesets_loader(paths.templates_dir / "assessments")
    matching = _rulesets_for_template(rulesets, template_id)

    pre_capture = _safe_capture(collaborators.capture_runner, target_scope, render_context)
    if pre_capture is None:
        return 1

    gate1_report = _run_gate1(matching, template_id, pre_capture)
    render_report(gate1_report, render_context)
    if gate1_report.verdict is GateVerdict.ERROR:
        return 1
    if gate1_report.verdict is GateVerdict.BLOCK and not force:
        return 2
    if gate1_report.verdict is GateVerdict.BLOCK:
        render_context.console.print(Notice.warn("Gate 1 BLOCK bypassed by --force"))

    apply_result = _run_apply(template_path, collaborators, render_context)
    if apply_result is None:
        return 1

    if skip_gate2:
        render_context.console.print(Notice.warn("Gate 2 skipped by --skip-gate2"))
        return 0

    post_capture = _safe_capture(collaborators.capture_runner, target_scope, render_context)
    if post_capture is None:
        return 1

    gate2_report = _run_gate2(matching, template_id, post_capture, apply_result)
    render_report(gate2_report, render_context)
    match gate2_report.verdict:
        case GateVerdict.PASS:
            return 0
        case GateVerdict.BLOCK:
            return 2
        case GateVerdict.ERROR:
            return 1
        case _:  # pragma: no cover -- exhaustive over GateVerdict
            raise AssertionError(f"unreachable verdict: {gate2_report.verdict!r}")


def _resolve_template_path(template_id: str, paths: NexusPaths) -> Path | None:
    """Return the canonical template.yaml path, or None when missing."""
    candidate = paths.templates_dir / template_id / "template.yaml"
    if candidate.is_file():
        return candidate
    return None


def _detect_target_scope(template_path: Path) -> str:
    """Quick-read `target_scope` from YAML so capture runs on the right scope.

    The full TemplateDocument validation happens later inside ApplyEngine.
    This early peek is best-effort -- it falls back to "global" if the
    file is unreadable so the capture step can still proceed (and Gate 1
    will flag any deeper issues).
    """
    from typing import cast  # noqa: PLC0415

    import yaml  # noqa: PLC0415 -- defer import to keep CLI cold-start fast

    try:
        raw_text = template_path.read_text(encoding="utf-8")
        raw = yaml.safe_load(raw_text)
    except OSError, yaml.YAMLError:
        return "global"
    if not isinstance(raw, dict):
        return "global"
    parsed = cast("dict[object, object]", raw)
    scope = parsed.get("target_scope")
    if isinstance(scope, str) and scope:
        return scope
    return "global"


def _rulesets_for_template(rulesets: tuple[Ruleset, ...], template_id: str) -> tuple[Ruleset, ...]:
    """Filter rulesets whose applies_to includes the template or '*'."""
    return tuple(rs for rs in rulesets if template_id in rs.applies_to or "*" in rs.applies_to)


def _merged_ruleset(
    rulesets: tuple[Ruleset, ...], *, target_phase: Phase, fallback_id: str
) -> Ruleset:
    """Combine matching rulesets into one synthetic ruleset filtered to phase."""
    merged_rules: list[AssessmentRule] = []
    for rs in rulesets:
        merged_rules.extend(rule for rule in rs.rules if rule.phase is target_phase)
    if not merged_rules:
        merged_rules = [_placeholder_rule(target_phase)]
    return Ruleset(
        id=fallback_id,
        version="0.0.0",
        description="merged ruleset for nexus apply",
        applies_to=("*",),
        rules=tuple(merged_rules),
    )


def _placeholder_rule(phase: Phase) -> AssessmentRule:
    """Build a no-op rule so an empty ruleset still evaluates to PASS."""
    from nexus.assessment.schemas.constraints import CountGteConstraint  # noqa: PLC0415
    from nexus.assessment.schemas.enums import Logic, Severity  # noqa: PLC0415
    from nexus.assessment.schemas.scope import TableScope  # noqa: PLC0415

    return AssessmentRule(
        id="_apply_placeholder",
        description="no rules defined for this template; auto-passing",
        severity=Severity.INFO,
        phase=phase,
        scope=TableScope(table="sys_scope"),
        required_tables=("sys_scope",),
        logic=Logic.AND_ALL,
        constraints=(CountGteConstraint(table="sys_scope", threshold=0),),
    )


def _safe_capture(
    capture_runner: CaptureRunner, scope: str | None, render_context: RenderContext
) -> CaptureResult | None:
    """Invoke the capture runner; surface NotImplementedError as exit-1."""
    try:
        return capture_runner(scope)
    except NotImplementedError as exc:
        render_context.console.print(Notice.error(f"live capture: {exc}"))
        return None


def _run_gate1(
    rulesets: tuple[Ruleset, ...], template_id: str, capture: CaptureResult
) -> GateReport:
    """Run Gate1Readiness against the pre-capture."""
    merged = _merged_ruleset(rulesets, target_phase=Phase.PRE_APPLY, fallback_id="apply-gate1")
    ctx = GateContext(capture=capture, apply_result=None, phase=Phase.PRE_APPLY)
    return Gate1Readiness(ruleset=merged, template_id=template_id).evaluate(ctx)


def _run_gate2(
    rulesets: tuple[Ruleset, ...],
    template_id: str,
    capture: CaptureResult,
    apply_result: ApplyResult,
) -> GateReport:
    """Run Gate2Validation against the post-capture + apply_result."""
    merged = _merged_ruleset(rulesets, target_phase=Phase.POST_APPLY, fallback_id="apply-gate2")
    ctx = GateContext(capture=capture, apply_result=apply_result, phase=Phase.POST_APPLY)
    return Gate2Validation(ruleset=merged, template_id=template_id).evaluate(ctx)


def _run_apply(
    template_path: Path,
    collaborators: ApplyCollaborators,
    render_context: RenderContext,
) -> ApplyResult | None:
    """Drive the async ApplyEngine.apply via asyncio.run; surface errors."""
    try:
        engine = collaborators.apply_engine_factory()
    except NotImplementedError as exc:
        render_context.console.print(Notice.error(f"ApplyEngine: {exc}"))
        return None
    try:
        return asyncio.run(engine.apply(template_path))
    except TemplateLoadError as exc:
        render_context.console.print(Notice.error(f"template load failed: {exc}"))
        return None
    except ScopeNotFoundError as exc:
        render_context.console.print(Notice.error(f"scope not found: {exc}"))
        return None


def _capture_runner_not_implemented(scope: str | None) -> CaptureResult:
    """Default capture_runner stub; production wires CaptureEngine."""
    del scope
    raise NotImplementedError(
        "live capture for `nexus apply` is not wired yet; "
        "production deployments require a configured ServiceNow client and capture engine"
    )


def _apply_engine_factory_not_implemented() -> ApplyEngine:
    """Default ApplyEngine factory stub; production wires a real engine."""
    raise NotImplementedError(
        "ApplyEngine factory is not wired in default_apply_collaborators; "
        "construct an ApplyEngine and inject via ApplyCollaborators for now"
    )
