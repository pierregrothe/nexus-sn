# ADR-010: Resource Lifecycle in Tests

**Status:** accepted
**Date:** 2026-05-07
**Enforcement:** soft (post-edit warning)

## Context

Sprint issue #10: a TimedRotatingFileHandler opened during the configure_logging test
was not closed before the root logger handlers were cleared. This leaked file
descriptors and caused PermissionError on Windows when pytest cleaned up tmp_path.
The test passed on macOS because rmtree uses ignore_errors=True.

## Decision

Any OS resource opened during a test (file handle, logging handler, socket) must be
explicitly closed in a finally block:

```python
finally:
    for h in root.handlers:
        h.close()
    root.handlers.clear()
    root.handlers.extend(saved_handlers)
```

Context managers are preferred where supported. The post-edit hook warns (soft) when
it detects TimedRotatingFileHandler, FileHandler, or socket.socket( in a test file
without a corresponding .close() or `with` statement.

## Consequences

All test teardown logic closes resources before restoring state. The configure_logging
test correctly closes handlers in its finally block. This prevents CI failures on
Windows runners where open file handles block directory cleanup.
