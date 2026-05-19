# src/nexus/cli/errors.py
# CLI-layer exception types with conventional exit codes.
# Author: Pierre Grothe
# Date: 2026-05-18

"""Exception classes raised by CLI commands and converted to exit codes.

:class:`InteractiveRequiredError` signals that a destructive operation
under a non-interactive profile (``PLAIN``) cannot proceed because the
operator did not pass ``--yes``. Exit code 2 matches the typer
convention for usage errors (typer reserves 1 for general
exceptions); the CLI maps the exception to ``typer.Exit(2)``.
"""

__all__ = ["InteractiveRequiredError"]


class InteractiveRequiredError(RuntimeError):
    """Raised when a confirmation prompt would block in a PLAIN profile.

    Attributes:
        exit_code: Conventional ``typer.Exit`` code (2 for usage error).
    """

    exit_code: int = 2
