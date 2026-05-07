# ADR-006: Python 3.14 Minimum

**Status:** accepted
**Date:** 2026-05-07
**Enforcement:** hook (pyproject.toml constraint check)

## Context

The project was scaffolded targeting Python 3.12+ with a broad constraint. The active
dev environment runs Python 3.14.3. Sprint retrospective identified that the broad
constraint caused Poetry to resolve to Python 3.14, triggering nicegui version
conflicts and demonstrating the constraint was misleading.

## Decision

Minimum Python version is `>=3.14,<3.15` in pyproject.toml. All Python 3.14 syntax
is permitted and preferred, including PEP 758 unparenthesized multi-except, PEP 649
deferred annotation evaluation (default in 3.14, making `from __future__ import
annotations` optional), and PEP 695 type parameter syntax.

## Consequences

CLAUDE.md updated: "Python 3.14+. All 3.14 syntax permitted." The prior "Do NOT use
Python 3.14-only syntax" restriction is removed. CI matrix updated to Python 3.14
only. Black and ruff target-version updated to py314.
