# scripts/__init__.py
# Marker so tests can import scripts.* as a regular package.
# Author: Pierre Grothe
# Date: 2026-05-16
"""Repo-level utility scripts (governance, smoke tests, etc.).

Each module is also runnable as ``python scripts/<name>.py`` for use
inside hooks and pre-commit gates.
"""

__all__: list[str] = []
