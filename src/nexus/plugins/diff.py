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

from packaging.version import InvalidVersion
from packaging.version import parse as parse_version
from pydantic import BaseModel, ConfigDict

from nexus.config.types import UtcDatetime
from nexus.plugins.models import PluginInfo, PluginInventory

__all__ = [
    "PluginDiff",
    "PluginDiffEntry",
    "PromoteAction",
    "PromotionPlan",
    "compute_diff",
    "project_to_promote_plan",
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


def compute_diff(
    a: PluginInventory,
    b: PluginInventory,
    profile_a: str,
    profile_b: str,
) -> PluginDiff:
    """Set-diff two plugin inventories.

    Identical plugins (same ``plugin_id``, ``version``, and ``state``)
    are excluded from the result. Entries are returned in stable
    ``(product_family, plugin_id)`` order.

    Args:
        a: Inventory captured from the first instance.
        b: Inventory captured from the second instance.
        profile_a: Profile name of instance A (recorded on the diff).
        profile_b: Profile name of instance B (recorded on the diff).

    Returns:
        A frozen ``PluginDiff`` describing every non-identical plugin.
    """
    by_id_a: dict[str, PluginInfo] = {p.plugin_id: p for p in a.plugins}
    by_id_b: dict[str, PluginInfo] = {p.plugin_id: p for p in b.plugins}
    all_ids = sorted(set(by_id_a) | set(by_id_b))
    entries: list[PluginDiffEntry] = []
    for plugin_id in all_ids:
        a_info = by_id_a.get(plugin_id)
        b_info = by_id_b.get(plugin_id)
        entry = _diff_entry(plugin_id, a_info, b_info)
        if entry is not None:
            entries.append(entry)
    entries.sort(key=lambda e: (e.product_family, e.plugin_id))
    return PluginDiff(
        profile_a=profile_a,
        profile_b=profile_b,
        captured_at_a=a.captured_at,
        captured_at_b=b.captured_at,
        entries=tuple(entries),
    )


def _diff_entry(
    plugin_id: str, a: PluginInfo | None, b: PluginInfo | None
) -> PluginDiffEntry | None:
    """Build one diff entry, or return ``None`` when a and b are identical."""
    if a is None and b is not None:
        return PluginDiffEntry(
            plugin_id=plugin_id,
            name=b.name,
            product_family=b.product_family,
            status="only_in_b",
            a_version=None,
            b_version=b.version,
            a_state=None,
            b_state=b.state,
        )
    if b is None and a is not None:
        return PluginDiffEntry(
            plugin_id=plugin_id,
            name=a.name,
            product_family=a.product_family,
            status="only_in_a",
            a_version=a.version,
            b_version=None,
            a_state=a.state,
            b_state=None,
        )
    if a is None or b is None:
        return None  # both None is impossible by construction
    if a.version != b.version:
        status: Literal[
            "only_in_a", "only_in_b", "version_mismatch", "state_mismatch"
        ] = "version_mismatch"
    elif a.state != b.state:
        status = "state_mismatch"
    else:
        return None
    return PluginDiffEntry(
        plugin_id=plugin_id,
        name=a.name,
        product_family=a.product_family,
        status=status,
        a_version=a.version,
        b_version=b.version,
        a_state=a.state,
        b_state=b.state,
    )


_ACTION_ORDER: dict[str, int] = {"install": 0, "activate": 1, "upgrade": 2}


def project_to_promote_plan(diff: PluginDiff) -> PromotionPlan:
    """Project a diff into an additive set of install/activate/upgrade actions.

    Rules:
        - ``only_in_a`` -> ``install``.
        - ``state_mismatch`` where ``a_state == "active"`` and
          ``b_state == "inactive"`` -> ``activate``.
        - ``version_mismatch`` where ``a_version`` is strictly newer than
          ``b_version`` per ``packaging.version.parse`` -> ``upgrade``.
        - All other entries (deactivations, downgrades, ``only_in_b``,
          and entries with unparseable versions on either side) are
          skipped.

    Args:
        diff: The diff produced by ``compute_diff``.

    Returns:
        A frozen ``PromotionPlan`` whose actions are sorted by
        ``(install < activate < upgrade, product_family, plugin_id)``.
    """
    actions: list[PromoteAction] = []
    for entry in diff.entries:
        action = _project_entry(entry)
        if action is not None:
            actions.append(action)
    actions.sort(
        key=lambda a: (_ACTION_ORDER[a.action], a.product_family, a.plugin_id)
    )
    return PromotionPlan(
        source_profile=diff.profile_a,
        target_profile=diff.profile_b,
        actions=tuple(actions),
    )


def _project_entry(entry: PluginDiffEntry) -> PromoteAction | None:
    """Return the matching PromoteAction for a diff entry, or None to skip."""
    if entry.status == "only_in_a" and entry.a_version is not None:
        return PromoteAction(
            action="install",
            plugin_id=entry.plugin_id,
            name=entry.name,
            product_family=entry.product_family,
            target_version=entry.a_version,
            current_version=None,
        )
    if (
        entry.status == "state_mismatch"
        and entry.a_state == "active"
        and entry.b_state == "inactive"
        and entry.a_version is not None
    ):
        return PromoteAction(
            action="activate",
            plugin_id=entry.plugin_id,
            name=entry.name,
            product_family=entry.product_family,
            target_version=entry.a_version,
            current_version=entry.b_version,
        )
    if (
        entry.status == "version_mismatch"
        and entry.a_version is not None
        and entry.b_version is not None
        and _is_newer(entry.a_version, entry.b_version)
    ):
        return PromoteAction(
            action="upgrade",
            plugin_id=entry.plugin_id,
            name=entry.name,
            product_family=entry.product_family,
            target_version=entry.a_version,
            current_version=entry.b_version,
        )
    return None


def _is_newer(candidate: str, baseline: str) -> bool:
    """True when ``candidate`` is strictly newer than ``baseline``.

    Returns ``False`` when either string fails to parse as a version --
    skipping unparseable strings is safer than guessing.
    """
    try:
        return parse_version(candidate) > parse_version(baseline)
    except InvalidVersion:
        return False
