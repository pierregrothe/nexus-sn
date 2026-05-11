# src/nexus/plugins/diff.py
# Cross-instance plugin diff + promote-plan logic.
# Author: Pierre Grothe
# Date: 2026-05-11
"""PluginDiff and PromotionPlan models plus pure-function builders.

Consumes ``PluginInventory`` produced by sub-project A. No I/O; the CLI
layer is responsible for reading inventories from disk and writing the
YAML output. ``compute_diff`` and ``project_to_promote_plan`` are pure
functions that operate on already-loaded inventories.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict

from nexus.config.types import UtcDatetime

__all__ = [
    "PluginDiff",
    "PluginDiffEntry",
    "PromoteAction",
    "PromotionPlan",
]

_FROZEN = ConfigDict(frozen=True, strict=True, extra="forbid")


class PluginDiffEntry(BaseModel):
    """One row of a cross-instance plugin diff.

    Attributes:
        plugin_id: Canonical SN plugin identifier.
        name: Display name (from whichever inventory had the entry).
        product_family: Curated product family or ``Uncategorized``.
        status: Why this row appears in the diff.
        a_version: Version on instance A, or ``None`` when only_in_b.
        b_version: Version on instance B, or ``None`` when only_in_a.
        a_state: State on A, or ``None`` when only_in_b.
        b_state: State on B, or ``None`` when only_in_a.
    """

    model_config = _FROZEN

    plugin_id: str
    name: str
    product_family: str
    status: Literal[
        "only_in_a", "only_in_b", "version_mismatch", "state_mismatch"
    ]
    a_version: str | None
    b_version: str | None
    a_state: Literal["active", "inactive"] | None
    b_state: Literal["active", "inactive"] | None


class PluginDiff(BaseModel):
    """Full diff of two plugin inventories.

    Attributes:
        profile_a: Source instance profile name.
        profile_b: Target instance profile name.
        captured_at_a: When inventory A was captured (UTC).
        captured_at_b: When inventory B was captured (UTC).
        entries: All non-identical plugins in stable ``(product_family,
            plugin_id)`` order.
    """

    model_config = _FROZEN

    profile_a: str
    profile_b: str
    captured_at_a: UtcDatetime
    captured_at_b: UtcDatetime
    entries: tuple[PluginDiffEntry, ...]


class PromoteAction(BaseModel):
    """One step in a promotion plan.

    Attributes:
        action: ``install``, ``activate``, or ``upgrade``.
        plugin_id: Canonical SN plugin identifier.
        name: Display name from the source inventory.
        product_family: Curated product family.
        target_version: Version present on the source instance.
        current_version: Version present on the target instance, or
            ``None`` when the action is ``install``.
    """

    model_config = _FROZEN

    action: Literal["install", "activate", "upgrade"]
    plugin_id: str
    name: str
    product_family: str
    target_version: str
    current_version: str | None


class PromotionPlan(BaseModel):
    """Actions required to make ``target_profile`` match ``source_profile``.

    Attributes:
        source_profile: Profile the actions originate from.
        target_profile: Profile the actions are applied to.
        actions: All actions in stable ``(install < activate < upgrade,
            product_family, plugin_id)`` order.
    """

    model_config = _FROZEN

    source_profile: str
    target_profile: str
    actions: tuple[PromoteAction, ...]
