# nexus/ui/app.py
# NiceGUI application entry point (requires nexus-sn[ui] for actual UI).
# Author: Pierre Grothe
# Date: 2026-05-07

"""NiceGUI application entry point.

start_ui() raises ImportError if nicegui is not installed and
NotImplementedError until the dashboard is built (planned for 2026.07).
"""

import importlib.util

__all__ = ["start_ui"]


def start_ui() -> None:
    """Start the NiceGUI dashboard.

    Raises:
        ImportError: When nicegui is not installed (install nexus-sn[ui]).
        NotImplementedError: When nicegui is installed but the dashboard is
            not yet implemented (planned for 2026.07).
    """
    if importlib.util.find_spec("nicegui") is None:
        raise ImportError(
            "NEXUS dashboard requires NiceGUI. Install with: pip install nexus-sn[ui]"
        )
    raise NotImplementedError("NEXUS dashboard is planned for 2026.07")
