# src/nexus/templates/document.py
# TemplateDocument discriminated union + YAML loader.
# Author: Pierre Grothe
# Date: 2026-05-19

"""TemplateDocument is the schema entry point for all v1 templates.

A YAML file is parsed via `load_template_document(path)` which uses
Pydantic's discriminated-union machinery to dispatch on the document's
`kind` field. The result is one of the variant Pydantic models declared
under `nexus.templates.schemas`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import yaml
from pydantic import Field, TypeAdapter, ValidationError

from nexus.templates.errors import TemplateLoadError
from nexus.templates.schemas.now_assist_skill import NowAssistSkill
from nexus.templates.schemas.workflow import Workflow

__all__ = ["TemplateDocument", "load_template_document"]


type TemplateDocument = Annotated[NowAssistSkill | Workflow, Field(discriminator="kind")]


_ADAPTER: TypeAdapter[TemplateDocument] = TypeAdapter(TemplateDocument)


def load_template_document(path: Path) -> TemplateDocument:
    """Read a YAML template file and validate it against TemplateDocument.

    Args:
        path: Filesystem path to the YAML template.

    Returns:
        Parsed `NowAssistSkill` or `Workflow` instance (whichever the
        document's `kind` field selects).

    Raises:
        TemplateLoadError: If the file cannot be read, the YAML is
            malformed, or the parsed structure does not validate
            against TemplateDocument. The original exception is
            preserved as the `cause`.
    """
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise TemplateLoadError(path, exc) from exc

    try:
        raw_data = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        raise TemplateLoadError(path, exc) from exc

    try:
        return _ADAPTER.validate_python(raw_data, strict=False)
    except ValidationError as exc:
        raise TemplateLoadError(path, exc) from exc
