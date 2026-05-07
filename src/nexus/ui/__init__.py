# nexus/ui/__init__.py
# Optional NiceGUI dashboard. Raises ImportError if nicegui is not installed.
# Author: Pierre Grothe
# Date: 2026-05-07

"""NiceGUI dashboard for NEXUS (optional -- requires nexus-sn[ui])."""

try:
    import nicegui  # noqa: F401
except ImportError as exc:
    raise ImportError(
        "The NEXUS dashboard requires NiceGUI. "
        "Install it with: pip install nexus-sn[ui]"
    ) from exc

__all__: list[str] = []
