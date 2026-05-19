# src/nexus/assessment/loader.py
# YAML ruleset loader.
# Author: Pierre Grothe
# Date: 2026-05-19

"""Load and parse a YAML ruleset file into a Ruleset Pydantic model."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from nexus.assessment.errors import RulesetLoadError
from nexus.assessment.schemas.ruleset import Ruleset

__all__ = ["load_ruleset"]


def load_ruleset(path: Path) -> Ruleset:
    """Load a YAML ruleset file and validate it against the Ruleset schema.

    Args:
        path: Filesystem path to the YAML ruleset.

    Returns:
        Parsed and validated Ruleset.

    Raises:
        RulesetLoadError: If the file cannot be read, the YAML is malformed,
            or the parsed structure does not validate against the Ruleset
            schema. The original exception is preserved as the cause.
    """
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RulesetLoadError(path, exc) from exc

    try:
        raw_data = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        raise RulesetLoadError(path, exc) from exc

    try:
        return Ruleset.model_validate(raw_data, strict=False)
    except ValidationError as exc:
        raise RulesetLoadError(path, exc) from exc
