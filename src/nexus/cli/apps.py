# src/nexus/cli/apps.py
# Typer application objects shared by every command module.
# Author: Pierre Grothe
# Date: 2026-05-16
"""Shared Typer ``app`` instances for the CLI.

Lives in its own module so the command sub-packages broken out of
``cli/__init__.py`` can attach ``@<sub_app>.command(...)`` decorators
without re-importing the entry point (which would create a circular
import).

Each ``app.add_typer(...)`` wiring also lives here so the parent/child
relationship is declared in one place rather than scattered across the
extracted command modules.
"""

from __future__ import annotations

import typer

__all__ = [
    "app",
    "assess_app",
    "baselines_app",
    "capture_app",
    "instance_app",
    "plugins_app",
    "recommend_app",
    "schema_app",
]

app = typer.Typer(
    name="nexus",
    help="NEXUS -- ServiceNow AI architect agent",
)

instance_app = typer.Typer(name="instance", help="Manage ServiceNow instances.")
app.add_typer(instance_app)

capture_app = typer.Typer(name="capture", help="Capture and deploy ServiceNow configurations.")
app.add_typer(capture_app)

schema_app = typer.Typer(name="schema", help="Reverse-engineer SN table schemas into ERDs.")
app.add_typer(schema_app)

assess_app = typer.Typer(name="assess", help="Assess instances and plan replatform migrations.")
app.add_typer(assess_app)

plugins_app = typer.Typer(
    name="plugins", help="Inspect the plugin inventory of registered instances."
)
app.add_typer(plugins_app)

recommend_app = typer.Typer(help="AI recommendations.")
plugins_app.add_typer(recommend_app, name="recommend")

baselines_app = typer.Typer(help="Manage plugin drift baselines.")
plugins_app.add_typer(baselines_app, name="baselines")
