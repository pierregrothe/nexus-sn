# nexus/ui/__init__.py
# Optional NiceGUI dashboard package. Always importable.
# Author: Pierre Grothe
# Date: 2026-05-07

"""NiceGUI dashboard for NEXUS (optional -- requires nexus-sn[ui]).

This package is always importable. The nicegui dependency is checked at
runtime inside start_ui() rather than at module load, so importing the
package never raises ImportError on systems without nicegui installed.
"""

__all__: list[str] = []
