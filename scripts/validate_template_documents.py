#!/usr/bin/env python
# scripts/validate_template_documents.py
# CI validator for templates/<id>/template.yaml.
# Author: Pierre Grothe
# Date: 2026-05-19

"""Validate every template document under `templates/<id>/template.yaml`.

Walks the `templates/` root, loads each `<id>/template.yaml` through
`nexus.templates.document.load_template_document`, and verifies the
Pydantic discriminated-union parses cleanly. Prints `OK` / `FAIL` lines
per template plus a final summary; exits 0 on success, 1 on any
failure.

Usage::

    python scripts/validate_template_documents.py [<templates-dir>]

When no argument is given the script uses `./templates` relative to the
current working directory.
"""

from __future__ import annotations

import sys
from pathlib import Path

from nexus.templates.document import load_template_document
from nexus.templates.errors import TemplateLoadError

__all__ = ["main", "validate_directory"]


def validate_directory(templates_dir: Path) -> tuple[int, list[str]]:
    """Validate every template.yaml under templates_dir/<id>/template.yaml.

    Args:
        templates_dir: Project `templates/` root.

    Returns:
        Tuple `(failures, messages)`.
    """
    messages: list[str] = []
    if not templates_dir.is_dir():
        messages.append(f"no templates directory at {templates_dir}")
        return 0, messages

    paths = sorted(templates_dir.glob("*/template.yaml"))
    if not paths:
        messages.append(f"no templates to validate under {templates_dir}")
        return 0, messages

    failures = 0
    for path in paths:
        try:
            doc = load_template_document(path)
        except TemplateLoadError as exc:
            failures += 1
            messages.append(f"FAIL {path}: {exc.cause}")
            continue
        messages.append(f"OK   {path.parent.name}: kind={doc.kind} id={doc.id}")

    messages.append(f"validated {len(paths)} template(s); {failures} failure(s)")
    return failures, messages


def main(argv: list[str] | None = None) -> int:
    """Entry point; argv defaults to sys.argv[1:]."""
    args = argv if argv is not None else sys.argv[1:]
    target = Path(args[0]) if args else Path.cwd() / "templates"
    failures, messages = validate_directory(target)
    for line in messages:
        print(line)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
