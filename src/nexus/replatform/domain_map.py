# src/nexus/replatform/domain_map.py
# Load a user-supplied scope->domain mapping for the replatform classifier.
# Author: Pierre Grothe
# Date: 2026-07-02

"""YAML loader for engagement-supplied scope-to-domain overrides.

A domain map lets a consultant group custom scopes under business domains
("HR", "Lending Ops") without waiting for catalog entries or AI enrichment:

    x_acme_hr_onboard: HR
    x_acme_kyc: Lending Ops
"""

from pathlib import Path
from typing import cast

import yaml

__all__ = ["load_domain_map"]


def load_domain_map(path: Path) -> dict[str, str]:
    """Load and validate a flat ``scope_key: domain`` YAML mapping.

    Args:
        path: YAML file containing the mapping.

    Returns:
        The parsed scope-to-domain mapping.

    Raises:
        ValueError: When the document is not valid YAML, or is not a flat
            string-to-string mapping.
        OSError: When the file cannot be read.
    """
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"domain map {path} is not valid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"domain map {path} must be a mapping of scope -> domain")
    parsed = cast("dict[object, object]", raw)
    result: dict[str, str] = {}
    for key, value in parsed.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise ValueError(f"domain map {path} must map string scopes to string domains")
        result[key] = value
    return result
