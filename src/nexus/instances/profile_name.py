# src/nexus/instances/profile_name.py
# Profile-name validation for the nexus setup / register wizard.
# Author: Pierre Grothe
# Date: 2026-05-18
"""Validate user-supplied profile names before they touch the filesystem.

The wizard writes a `meta.json` under `~/.nexus/instances/<profile>/`,
so the profile name becomes a directory name. This module rejects
inputs that could escape the parent (`..`), use path separators, hide
the directory (leading `.`), exceed 64 characters, or contain
non-ASCII / control characters.
"""

from __future__ import annotations

from nexus.instances.errors import InvalidProfileNameError

__all__ = ["validate_profile_name"]

_MAX_LENGTH = 64
_ALLOWED_PUNCT = frozenset({"-", "_"})


def validate_profile_name(name: str) -> str:
    r"""Return ``name`` unchanged when it satisfies every rule.

    Rules, applied in order (the first violation wins):

    1. After ``str.strip``, the value must be non-empty (else ``empty``).
    2. The value must contain no whitespace characters (else
       ``whitespace``).
    3. Length must be at most 64 characters (else ``too long``).
    4. The substring ``..`` is forbidden anywhere (else ``traversal``).
    5. ``/`` and ``\`` are forbidden (else ``separator``).
    6. The first character cannot be ``.`` (else ``leading dot``).
    7. Every character must be ASCII (codepoint <= 127) and not a
       control character (codepoint < 32) and either alphanumeric or
       one of ``-``, ``_`` (else ``non-ascii``, ``control``, or
       ``disallowed``).

    Args:
        name: Candidate profile name from a user prompt.

    Returns:
        The same string when it satisfies every rule.

    Raises:
        InvalidProfileNameError: When ``name`` violates any rule above.
            The ``reason`` attribute carries one of the slugs above so
            callers can render a specific hint.
    """
    if not name.strip():
        raise InvalidProfileNameError(name, "empty")
    if any(ch.isspace() for ch in name):
        raise InvalidProfileNameError(name, "whitespace")
    if len(name) > _MAX_LENGTH:
        raise InvalidProfileNameError(name, "too long")
    if ".." in name:
        raise InvalidProfileNameError(name, "traversal")
    if "/" in name or "\\" in name:
        raise InvalidProfileNameError(name, "separator")
    if name.startswith("."):
        raise InvalidProfileNameError(name, "leading dot")
    for ch in name:
        codepoint = ord(ch)
        if codepoint < 32:
            raise InvalidProfileNameError(name, "control")
        if codepoint > 127:
            raise InvalidProfileNameError(name, "non-ascii")
        if not ch.isalnum() and ch not in _ALLOWED_PUNCT:
            raise InvalidProfileNameError(name, "disallowed")
    return name
