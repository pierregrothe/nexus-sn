#!/usr/bin/env python
# scripts/validate_assessment_rulesets.py
# CI validator for templates/assessments/*.yaml.
# Author: Pierre Grothe
# Date: 2026-05-19

"""Validate every YAML ruleset under `templates/assessments/`.

Walks the directory, loads each `*.yaml` through `nexus.assessment.loader.
load_ruleset`, and verifies that every `applies_to` entry either resolves
to an existing `templates/<id>/manifest.yaml` or is the literal "*".

Exit codes:
    0 -- all rulesets validated cleanly (or no rulesets present)
    1 -- one or more rulesets failed to load OR an `applies_to` entry is
         orphaned.

Usage::

    python scripts/validate_assessment_rulesets.py [<templates-dir>]

When no argument is given the script uses `./templates` relative to the
current working directory.
"""

from __future__ import annotations

import sys
from pathlib import Path

from nexus.assessment.errors import RulesetLoadError
from nexus.assessment.loader import load_ruleset
from nexus.assessment.schemas.ruleset import Ruleset

__all__ = ["main", "validate_directory"]


def validate_directory(templates_dir: Path) -> tuple[int, list[str]]:
    """Validate every assessment ruleset under templates_dir/assessments.

    Args:
        templates_dir: Project `templates/` root.

    Returns:
        Tuple `(failures, messages)` where `failures` is the count of
        rulesets that failed validation and `messages` is the
        human-readable summary including per-ruleset detail.
    """
    assessments_dir = templates_dir / "assessments"
    messages: list[str] = []
    if not assessments_dir.is_dir():
        messages.append(f"no assessments directory at {assessments_dir}")
        return 0, messages

    paths = sorted(assessments_dir.glob("*.yaml"))
    if not paths:
        messages.append(f"no rulesets to validate under {assessments_dir}")
        return 0, messages

    valid_template_ids = _collect_template_ids(templates_dir)
    failures = 0
    rules_total = 0
    for path in paths:
        try:
            ruleset = load_ruleset(path)
        except RulesetLoadError as exc:
            failures += 1
            messages.append(f"FAIL {path}: {exc.cause}")
            continue
        rules_total += len(ruleset.rules)
        orphans = _orphaned_applies_to(ruleset, valid_template_ids)
        if orphans:
            failures += 1
            messages.append(
                f"FAIL {path}: applies_to entries do not resolve: "
                f"{', '.join(repr(o) for o in orphans)}"
            )
            continue
        messages.append(f"OK   {path.name}: {len(ruleset.rules)} rule(s)")

    messages.append(
        f"validated {len(paths)} ruleset(s); {rules_total} rule(s) total; {failures} failure(s)"
    )
    return failures, messages


def _collect_template_ids(templates_dir: Path) -> frozenset[str]:
    """Return the set of valid template ids (subdirectories with manifest.yaml)."""
    if not templates_dir.is_dir():
        return frozenset()
    ids: set[str] = set()
    for path in templates_dir.iterdir():
        if path.is_dir() and (path / "manifest.yaml").exists():
            ids.add(path.name)
    return frozenset(ids)


def _orphaned_applies_to(ruleset: Ruleset, valid_template_ids: frozenset[str]) -> tuple[str, ...]:
    """Return applies_to entries that do not resolve to a known template id."""
    orphaned: list[str] = []
    for entry in ruleset.applies_to:
        if entry == "*":
            continue
        if entry not in valid_template_ids:
            orphaned.append(entry)
    return tuple(orphaned)


def main(argv: list[str] | None = None) -> int:
    """Entry point. argv defaults to sys.argv[1:].

    Returns:
        Process exit code (0 on success, 1 on any failure).
    """
    args = argv if argv is not None else sys.argv[1:]
    target = Path(args[0]) if args else Path.cwd() / "templates"
    failures, messages = validate_directory(target)
    for line in messages:
        print(line)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
