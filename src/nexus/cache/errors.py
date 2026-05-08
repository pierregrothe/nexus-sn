# src/nexus/cache/errors.py
# Exceptions raised by the cache decorator.
# Author: Pierre Grothe
# Date: 2026-05-08
"""Cache-layer exception types."""

__all__ = ["CacheKeyError"]


class CacheKeyError(Exception):
    """Raised when a @cached method receives an arg whose type is not hashable.

    The decorator cannot generate a stable cache key for this call. Declare
    a custom ``key_fn`` on the @cached decorator to convert the arg to a
    hashable string. See ADR-017.
    """
