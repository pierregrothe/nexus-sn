# src/nexus/templates/schemas/_env.py
# Shared {{ env.X }} substitution helper for template schemas.
# Author: Pierre Grothe
# Date: 2026-05-19

"""Resolve `{{ env.X }}` references in template string fields.

Used by NowAssistSkill and Workflow field validators. The substitution
runs at parse time so downstream renderers see resolved values only.

Failure mode: unset env vars raise ValueError with the literal variable
name. Pydantic wraps the ValueError in a ValidationError; the cause
string carries the exact missing variable name so users get a clear
diagnostic.
"""

from __future__ import annotations

import os
import re

__all__ = ["resolve_env_in_string", "resolve_env_in_value"]


_ENV_PATTERN = re.compile(r"\{\{\s*env\.([A-Z_][A-Z0-9_]*)\s*\}\}")


def resolve_env_in_string(value: str) -> str:
    """Resolve every `{{ env.X }}` in `value` against os.environ.

    Args:
        value: Input string possibly containing one or more env references.

    Returns:
        The input string with each `{{ env.NAME }}` replaced by
        `os.environ["NAME"]`.

    Raises:
        ValueError: If any referenced variable is not set. The message
            contains the literal variable name.
    """

    def _substitute(match: re.Match[str]) -> str:
        name = match.group(1)
        env_value = os.environ.get(name)
        if env_value is None:
            raise ValueError(f"env var {name!r} is not set")
        return env_value

    return _ENV_PATTERN.sub(_substitute, value)


def resolve_env_in_value(value: object) -> object:
    """Resolve env references inside a parsed YAML value.

    Strings get substitution; non-strings pass through unchanged. The
    helper is safe to use as a `@field_validator(mode="before")`
    callable.

    Args:
        value: A value from parsed YAML (str / int / bool / dict / list).

    Returns:
        The value with embedded env refs resolved (strings only).

    Raises:
        ValueError: If any embedded env var is not set.
    """
    if isinstance(value, str):
        return resolve_env_in_string(value)
    return value
