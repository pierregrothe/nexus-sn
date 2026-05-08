# src/nexus/cache/__init__.py
# Layer-0 caching utility -- exports the @cached decorator, clear_cache, and CacheKeyError.
# Author: Pierre Grothe
# Date: 2026-05-08
"""NEXUS canonical caching decorator (ADR-017).

All caching in src/nexus/ goes through @cached. Direct use of functools.cache,
functools.lru_cache, and functools.cached_property is forbidden by Semgrep.
"""

from nexus.cache.decorator import cached, clear_cache
from nexus.cache.errors import CacheKeyError

__all__ = ["CacheKeyError", "cached", "clear_cache"]
