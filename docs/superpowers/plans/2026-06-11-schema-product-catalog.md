# Schema Product Catalog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hardcoded `areas.py` registry with a community-maintained JSON product catalog bundled in the package and kept current by `nexus sync`.

**Architecture:** `SchemaProduct` / `SchemaProductCatalog` Pydantic models live in `products.py`; `SchemaArea` + `ScopeEntry` (renamed from `ScopeRef`) move to `models.py`; `ProductRegistry` handles read/write/resolve against `~/.nexus/schema/catalog.json` with a bundled fallback; `SchemaSync` mirrors the existing `GitHubSync` pattern; `nexus schema erd` accepts 1-2 product names/acronyms and builds a `SchemaArea` on the fly.

**Tech Stack:** Python 3.14, Pydantic v2, httpx, typer, importlib.resources, pytest

---

## File Map

| Action   | Path                                           | Responsibility                                        |
|----------|------------------------------------------------|-------------------------------------------------------|
| Modify   | `src/nexus/schema/models.py`                   | Add `ScopeEntry` + `SchemaArea` (moved from areas.py) |
| Create   | `src/nexus/schema/products.py`                 | `SchemaProduct`, `SchemaProductCatalog` models        |
| Create   | `src/nexus/schema/products.json`               | Bundled default catalog (4 entries)                   |
| Create   | `src/nexus/schema/product_registry.py`         | Load / save / resolve catalog                         |
| Create   | `src/nexus/schema/sync.py`                     | `GitHubProductCatalogClient` + `SchemaSync`           |
| Modify   | `src/nexus/cli/commands_sync.py`               | Call `SchemaSync` after template sync                 |
| Modify   | `src/nexus/cli/views.py`                       | Accept `areas` param in `_build_schema_cartographer`  |
| Modify   | `src/nexus/cli/commands_schema.py`             | Product resolution, 1-2 product args                  |
| Modify   | `src/nexus/cli/help_text.py`                   | `areas` -> `products`, `erd <area>` -> `erd <product>`|
| Delete   | `src/nexus/schema/areas.py`                    | Replaced by catalog + models.py                       |
| Modify   | `src/nexus/schema/__init__.py`                 | Update exports                                        |
| Modify   | `src/nexus/schema/discoverer.py`               | Import `SchemaArea` from `models` not `areas`         |
| Modify   | `src/nexus/schema/engine.py`                   | Import `SchemaArea` from `models` not `areas`         |
| Modify   | `pyproject.toml`                               | Include `products.json` as package data               |
| Rename   | `tests/schema/test_schema_areas.py`            | -> `tests/schema/test_schema_products.py`             |
| Modify   | `tests/schema/test_schema_exports.py`          | Remove `DEFAULT_AREAS` import                         |
| Modify   | `tests/cli/test_commands_schema.py`            | Update area->product arg, add new tests               |
| Create   | `tests/fakes/fake_product_registry.py`         | In-memory `ProductRegistry` for CLI tests             |
| Create   | `tests/schema/test_schema_product_registry.py` | Registry I/O tests                                    |
| Create   | `tests/schema/test_schema_sync.py`             | Sync client + orchestrator tests                      |

---

## Task 1: Move ScopeEntry + SchemaArea into models.py

**Files:**
- Modify: `src/nexus/schema/models.py`
- Modify: `src/nexus/schema/areas.py` (re-export only -- keep alive for Task 7)
- Modify: `src/nexus/schema/discoverer.py`
- Modify: `src/nexus/schema/engine.py`

- [ ] **Step 1: Add ScopeEntry and SchemaArea to models.py**

Append to `src/nexus/schema/models.py` (after existing `__all__`, before `_CONFIG`):

```python
# src/nexus/schema/models.py
# Frozen Pydantic models for the schema cartography graph.
# Author: Pierre Grothe
# Date: 2026-06-08
"""TableDef, FieldDef, edge models, SchemaGraph, ScopeEntry, SchemaArea."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from pydantic import BaseModel, ConfigDict

__all__ = [
    "FieldDef",
    "InheritanceEdge",
    "ReferenceEdge",
    "RelationshipEdge",
    "SchemaArea",
    "SchemaGraph",
    "ScopeEntry",
    "TableDef",
]

_CONFIG = ConfigDict(frozen=True, strict=True, extra="forbid")


@dataclass(slots=True, frozen=True)
class ScopeEntry:
    """One application scope included in a schema area.

    Args:
        key: The sys_scope.scope key, e.g. "sn_grc_doc_design".
        label: Human-readable product label.
    """

    key: str
    label: str


@dataclass(slots=True, frozen=True)
class SchemaArea:
    """A named group of scopes to reverse-engineer together.

    Args:
        key: Machine-readable area key used in CLI and archives.
        display: Human-readable label.
        scopes: Scopes whose tables form the area.
        bridge_targets: When set, narrow the discovered graph to the bridge
            neighborhood around these target tables (e.g. ("cmdb_ci",)).
            Empty means keep the whole area.
    """

    key: str
    display: str
    scopes: tuple[ScopeEntry, ...]
    bridge_targets: tuple[str, ...] = ()
```

Then keep the existing `FieldDef`, `TableDef`, `ReferenceEdge`, `InheritanceEdge`, `RelationshipEdge`, `SchemaGraph` classes unchanged below.

- [ ] **Step 2: Make areas.py a thin re-export shim**

Replace the `ScopeRef` and `SchemaArea` definitions in `areas.py` with imports from models, renaming `ScopeRef` as an alias. The `DEFAULT_AREAS` dict stays in `areas.py` (it is deleted in Task 7).

Change `src/nexus/schema/areas.py` so the top reads:

```python
# src/nexus/schema/areas.py
# Pluggable registry of schema areas (scope groups) to map.
# Author: Pierre Grothe
# Date: 2026-06-08
"""SchemaArea registry: which SN application scopes form each cartography area."""

from nexus.schema.models import SchemaArea, ScopeEntry

# Backward-compat alias -- removed in Task 7 when areas.py is deleted.
ScopeRef = ScopeEntry

__all__ = [
    "BCM",
    "CMDB_BCM",
    "DEFAULT_AREAS",
    "DOC_DESIGNER",
    "HAM_ITSM",
    "SchemaArea",
    "ScopeRef",
]
```

Then update the existing area constants to use `ScopeEntry` instead of the dataclass that was defined inline:

```python
DOC_DESIGNER = SchemaArea(
    key="doc-designer",
    display="Document Designer",
    scopes=(
        ScopeEntry("sn_grc_doc_design", "Document Designer with Word"),
        ScopeEntry("sn_grc_rel_config", "Data Relationships Framework"),
    ),
)

BCM = SchemaArea(
    key="bcm",
    display="Business Continuity Management",
    scopes=(
        ScopeEntry("sn_bcm", "BCM Core"),
        ScopeEntry("sn_bcm_lite", "BCM User Lite"),
        ScopeEntry("sn_bcm_map", "Crisis Map"),
        ScopeEntry("sn_bcp", "Business Continuity Planning"),
    ),
)

CMDB_BCM = SchemaArea(
    key="cmdb-bcm",
    display="CMDB <-> BCM bridge",
    scopes=(
        ScopeEntry("sn_bcm", "BCM Core"),
        ScopeEntry("sn_bcp", "Business Continuity Planning"),
    ),
    bridge_targets=("cmdb_ci",),
)

HAM_ITSM = SchemaArea(
    key="ham-itsm",
    display="Hardware Asset Management -> ITSM bridge",
    scopes=(
        ScopeEntry("sn_hamp", "Hardware Asset Management Pro"),
    ),
    bridge_targets=("cmdb_ci",),
)

DEFAULT_AREAS: dict[str, SchemaArea] = {
    a.key: a for a in (DOC_DESIGNER, BCM, CMDB_BCM, HAM_ITSM)
}
```

- [ ] **Step 3: Update discoverer.py import**

In `src/nexus/schema/discoverer.py` change:
```python
from nexus.schema.areas import DEFAULT_AREAS, SchemaArea
```
to:
```python
from nexus.schema.areas import DEFAULT_AREAS
from nexus.schema.models import SchemaArea
```

Also update the single usage of `.scope` on a `ScopeRef`/`ScopeEntry` inside the discoverer. Find `s.scope` (if any) and change to `s.key`. In `discoverer.py` line ~93:
```python
scope_keys = [s.scope for s in area.scopes]
```
becomes:
```python
scope_keys = [s.key for s in area.scopes]
```

- [ ] **Step 4: Update engine.py import**

In `src/nexus/schema/engine.py` change:
```python
from nexus.schema.areas import DEFAULT_AREAS, SchemaArea
```
to:
```python
from nexus.schema.areas import DEFAULT_AREAS
from nexus.schema.models import SchemaArea
```

- [ ] **Step 5: Run the existing schema tests**

```
pytest tests/schema/ -v --timeout=30
```

Expected: all pass. Fix any `.scope` -> `.key` attribute errors before continuing.

- [ ] **Step 6: Commit**

```
git add src/nexus/schema/models.py src/nexus/schema/areas.py \
        src/nexus/schema/discoverer.py src/nexus/schema/engine.py
git commit -m "refactor(schema): move SchemaArea+ScopeEntry into models.py; ScopeRef alias in areas.py"
```

---

## Task 2: SchemaProduct + SchemaProductCatalog models

**Files:**
- Create: `src/nexus/schema/products.py`
- Create: `tests/schema/test_schema_products.py`

- [ ] **Step 1: Write failing tests**

Create `tests/schema/test_schema_products.py`:

```python
# tests/schema/test_schema_products.py
# Tests for SchemaProduct and SchemaProductCatalog models.
# Author: Pierre Grothe
# Date: 2026-06-11
"""SchemaProduct model validation and catalog resolution."""

import pytest
from pydantic import ValidationError

from nexus.schema.models import ScopeEntry
from nexus.schema.products import SchemaProduct, SchemaProductCatalog


def _ham() -> SchemaProduct:
    return SchemaProduct(
        key="ham",
        acronym="HAM",
        name="Hardware Asset Management",
        scopes=(ScopeEntry(key="sn_hamp", label="Hardware Asset Management Pro"),),
        bridge_targets=("cmdb_ci",),
    )


def _itsm() -> SchemaProduct:
    return SchemaProduct(
        key="itsm",
        acronym="ITSM",
        name="IT Service Management",
        scopes=(),
        bridge_targets=("incident", "task", "cmdb_ci"),
    )


def _catalog() -> SchemaProductCatalog:
    return SchemaProductCatalog(version="1.0", products=(_ham(), _itsm()))


def test_schema_product_is_frozen() -> None:
    p = _ham()
    with pytest.raises(ValidationError):
        p.model_copy(update={"key": "new"})  # type: ignore[call-arg]


def test_schema_product_catalog_resolves_by_key() -> None:
    assert _catalog().resolve("ham") == _ham()


def test_schema_product_catalog_resolves_by_acronym() -> None:
    assert _catalog().resolve("HAM") == _ham()


def test_schema_product_catalog_resolves_by_name() -> None:
    assert _catalog().resolve("Hardware Asset Management") == _ham()


def test_schema_product_catalog_resolve_is_case_insensitive() -> None:
    assert _catalog().resolve("hardware asset management") == _ham()
    assert _catalog().resolve("ham") == _ham()


def test_schema_product_catalog_resolve_unknown_returns_none() -> None:
    assert _catalog().resolve("NoSuchProduct") is None


def test_schema_product_bridge_only_has_no_scopes() -> None:
    p = _itsm()
    assert not p.scopes
    assert p.bridge_targets


def test_schema_product_catalog_extra_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        SchemaProduct(
            key="x",
            acronym="X",
            name="X",
            scopes=(),
            bridge_targets=(),
            unknown_field="bad",  # type: ignore[call-arg]
        )
```

- [ ] **Step 2: Run tests to confirm they fail**

```
pytest tests/schema/test_schema_products.py -v
```

Expected: `ImportError` (module does not exist yet).

- [ ] **Step 3: Create products.py**

Create `src/nexus/schema/products.py`:

```python
# src/nexus/schema/products.py
# Pydantic models for the schema product catalog.
# Author: Pierre Grothe
# Date: 2026-06-11
"""SchemaProduct, SchemaProductCatalog: the community-maintained product catalog."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from nexus.schema.models import ScopeEntry

__all__ = [
    "SchemaProduct",
    "SchemaProductCatalog",
]

_CONFIG = ConfigDict(frozen=True, strict=True, extra="forbid")


class SchemaProduct(BaseModel):
    """One product entry in the schema catalog.

    Args:
        key: Machine slug, e.g. "ham".
        acronym: Short form, e.g. "HAM".
        name: Full product name.
        scopes: Ordered list of sys_scope keys to discover.
        bridge_targets: Tables used as bridge narrowing targets. Empty
            for unrestricted discovery. Products with empty scopes are
            bridge-only and cannot be used as the sole ERD argument.
    """

    model_config = _CONFIG

    key: str
    acronym: str
    name: str
    scopes: tuple[ScopeEntry, ...]
    bridge_targets: tuple[str, ...] = ()


class SchemaProductCatalog(BaseModel):
    """The full product catalog, either bundled or synced from GitHub.

    Args:
        version: Schema version string, e.g. "1.0".
        products: Ordered collection of products.
    """

    model_config = _CONFIG

    version: str
    products: tuple[SchemaProduct, ...]

    def resolve(self, ref: str) -> SchemaProduct | None:
        """Find a product by key, acronym, or name (case-insensitive).

        Args:
            ref: Key, acronym, or full product name.

        Returns:
            The matching SchemaProduct, or None if not found.
        """
        needle = ref.lower()
        for p in self.products:
            if needle in (p.key.lower(), p.acronym.lower(), p.name.lower()):
                return p
        return None
```

- [ ] **Step 4: Run tests to confirm they pass**

```
pytest tests/schema/test_schema_products.py -v
```

Expected: all 8 tests pass.

- [ ] **Step 5: Commit**

```
git add src/nexus/schema/products.py tests/schema/test_schema_products.py
git commit -m "feat(schema): SchemaProduct + SchemaProductCatalog models with resolve()"
```

---

## Task 3: Bundled products.json

**Files:**
- Create: `src/nexus/schema/products.json`

- [ ] **Step 1: Create the bundled catalog**

Create `src/nexus/schema/products.json`:

```json
{
  "version": "1.0",
  "products": [
    {
      "key": "ham",
      "acronym": "HAM",
      "name": "Hardware Asset Management",
      "scopes": [
        {"key": "sn_hamp", "label": "Hardware Asset Management Pro"}
      ],
      "bridge_targets": ["cmdb_ci"]
    },
    {
      "key": "itsm",
      "acronym": "ITSM",
      "name": "IT Service Management",
      "scopes": [],
      "bridge_targets": ["incident", "task", "change_request", "cmdb_ci"]
    },
    {
      "key": "doc-designer",
      "acronym": "DOC",
      "name": "Document Designer",
      "scopes": [
        {"key": "sn_grc_doc_design", "label": "Document Designer with Word"},
        {"key": "sn_grc_rel_config", "label": "Data Relationships Framework"}
      ],
      "bridge_targets": []
    },
    {
      "key": "bcm",
      "acronym": "BCM",
      "name": "Business Continuity Management",
      "scopes": [
        {"key": "sn_bcm", "label": "BCM Core"},
        {"key": "sn_bcm_lite", "label": "BCM User Lite"},
        {"key": "sn_bcm_map", "label": "Crisis Map"},
        {"key": "sn_bcp", "label": "Business Continuity Planning"}
      ],
      "bridge_targets": []
    }
  ]
}
```

- [ ] **Step 2: Add a bundled-load test to test_schema_products.py**

Append to `tests/schema/test_schema_products.py`:

```python
import importlib.resources


def test_bundled_catalog_parses_and_contains_required_products() -> None:
    data = importlib.resources.files("nexus.schema").joinpath("products.json").read_text()
    catalog = SchemaProductCatalog.model_validate_json(data)
    keys = {p.key for p in catalog.products}
    assert {"ham", "itsm", "doc-designer", "bcm"} <= keys
```

- [ ] **Step 3: Run the new test**

```
pytest tests/schema/test_schema_products.py::test_bundled_catalog_parses_and_contains_required_products -v
```

Expected: FAIL (products.json not yet on the package path -- may need pyproject.toml, but importlib.resources with src layout often resolves at dev-install time).

If FAIL due to `FileNotFoundError`, add to `pyproject.toml` under `[tool.poetry]`:
```toml
packages = [{include = "nexus", from = "src"}]
include = ["src/nexus/schema/products.json"]
```
Then re-run.

Expected: PASS.

- [ ] **Step 4: Commit**

```
git add src/nexus/schema/products.json pyproject.toml tests/schema/test_schema_products.py
git commit -m "feat(schema): bundled products.json catalog + package data include"
```

---

## Task 4: ProductRegistry

**Files:**
- Create: `src/nexus/schema/product_registry.py`
- Create: `tests/fakes/fake_product_registry.py`
- Create: `tests/schema/test_schema_product_registry.py`

- [ ] **Step 1: Write failing tests**

Create `tests/schema/test_schema_product_registry.py`:

```python
# tests/schema/test_schema_product_registry.py
# Tests for ProductRegistry I/O and bundled fallback.
# Author: Pierre Grothe
# Date: 2026-06-11
"""ProductRegistry: save/load/resolve against ~/.nexus/schema/catalog.json."""

from datetime import UTC, datetime
from pathlib import Path

from nexus.schema.models import ScopeEntry
from nexus.schema.product_registry import CachedSchemaProductCatalog, ProductRegistry
from nexus.schema.products import SchemaProduct, SchemaProductCatalog
from nexus.schema.sync import SchemaSyncSource


def _catalog() -> SchemaProductCatalog:
    return SchemaProductCatalog(
        version="1.0",
        products=(
            SchemaProduct(
                key="ham",
                acronym="HAM",
                name="Hardware Asset Management",
                scopes=(ScopeEntry(key="sn_hamp", label="HAM Pro"),),
                bridge_targets=("cmdb_ci",),
            ),
        ),
    )


def _source() -> SchemaSyncSource:
    return SchemaSyncSource(repo="owner/repo", branch="main", path="schema/products.json")


def test_product_registry_save_then_load_roundtrip(tmp_path: Path) -> None:
    registry = ProductRegistry(tmp_path)
    catalog = _catalog()
    cached = registry.save_catalog(catalog, _source())
    assert cached.catalog == catalog
    loaded = registry.load_catalog()
    assert loaded == catalog


def test_product_registry_load_falls_back_to_bundled_when_cache_absent(
    tmp_path: Path,
) -> None:
    registry = ProductRegistry(tmp_path)
    catalog = registry.load_catalog()
    # bundled catalog has the four default products
    assert catalog.resolve("ham") is not None


def test_product_registry_load_cached_returns_none_when_no_sync(tmp_path: Path) -> None:
    registry = ProductRegistry(tmp_path)
    assert registry.load_cached() is None


def test_product_registry_load_cached_returns_entry_after_save(tmp_path: Path) -> None:
    registry = ProductRegistry(tmp_path)
    registry.save_catalog(_catalog(), _source())
    cached = registry.load_cached()
    assert cached is not None
    assert cached.source == _source()


def test_product_registry_atomic_write_leaves_old_cache_on_oserror(
    tmp_path: Path, monkeypatch: import_pytest.MonkeyPatch
) -> None:
    import pytest as import_pytest
    registry = ProductRegistry(tmp_path)
    registry.save_catalog(_catalog(), _source())

    import tempfile
    original_mkstemp = tempfile.mkstemp

    def _fail(*args: object, **kwargs: object) -> object:
        raise OSError("disk full")

    monkeypatch.setattr(tempfile, "mkstemp", _fail)
    try:
        registry.save_catalog(_catalog(), _source())
    except OSError:
        pass

    # old cache still loadable
    assert registry.load_catalog() is not None


def test_product_registry_resolve_delegates_to_catalog(tmp_path: Path) -> None:
    registry = ProductRegistry(tmp_path)
    registry.save_catalog(_catalog(), _source())
    assert registry.resolve("HAM") is not None
    assert registry.resolve("nobody") is None
```

Fix the import in that test -- `import pytest as import_pytest` is awkward. Use a proper fixture:

```python
# tests/schema/test_schema_product_registry.py
# Tests for ProductRegistry I/O and bundled fallback.
# Author: Pierre Grothe
# Date: 2026-06-11
"""ProductRegistry: save/load/resolve against ~/.nexus/schema/catalog.json."""

import tempfile
from pathlib import Path

import pytest

from nexus.schema.models import ScopeEntry
from nexus.schema.product_registry import ProductRegistry
from nexus.schema.products import SchemaProduct, SchemaProductCatalog
from nexus.schema.sync import SchemaSyncSource


def _catalog() -> SchemaProductCatalog:
    return SchemaProductCatalog(
        version="1.0",
        products=(
            SchemaProduct(
                key="ham",
                acronym="HAM",
                name="Hardware Asset Management",
                scopes=(ScopeEntry(key="sn_hamp", label="HAM Pro"),),
                bridge_targets=("cmdb_ci",),
            ),
        ),
    )


def _source() -> SchemaSyncSource:
    return SchemaSyncSource(repo="owner/repo", branch="main", path="schema/products.json")


def test_product_registry_save_then_load_roundtrip(tmp_path: Path) -> None:
    registry = ProductRegistry(tmp_path)
    catalog = _catalog()
    cached = registry.save_catalog(catalog, _source())
    assert cached.catalog == catalog
    assert registry.load_catalog() == catalog


def test_product_registry_load_falls_back_to_bundled_when_cache_absent(
    tmp_path: Path,
) -> None:
    catalog = ProductRegistry(tmp_path).load_catalog()
    assert catalog.resolve("ham") is not None


def test_product_registry_load_cached_returns_none_when_no_sync(tmp_path: Path) -> None:
    assert ProductRegistry(tmp_path).load_cached() is None


def test_product_registry_load_cached_returns_entry_after_save(tmp_path: Path) -> None:
    registry = ProductRegistry(tmp_path)
    registry.save_catalog(_catalog(), _source())
    cached = registry.load_cached()
    assert cached is not None
    assert cached.source == _source()


def test_product_registry_atomic_write_leaves_old_cache_on_oserror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = ProductRegistry(tmp_path)
    registry.save_catalog(_catalog(), _source())

    def _fail(*args: object, **kwargs: object) -> object:
        raise OSError("disk full")

    monkeypatch.setattr(tempfile, "mkstemp", _fail)
    try:
        registry.save_catalog(_catalog(), _source())
    except OSError:
        pass

    assert registry.load_catalog() is not None


def test_product_registry_resolve_delegates_to_catalog(tmp_path: Path) -> None:
    registry = ProductRegistry(tmp_path)
    registry.save_catalog(_catalog(), _source())
    assert registry.resolve("HAM") is not None
    assert registry.resolve("nobody") is None
```

- [ ] **Step 2: Run tests to confirm they fail**

```
pytest tests/schema/test_schema_product_registry.py -v
```

Expected: `ImportError` on `product_registry` and `sync`.

- [ ] **Step 3: Create SchemaSyncSource (needed by test above)**

Create a stub `src/nexus/schema/sync.py` containing only `SchemaSyncSource` for now (the rest is added in Task 5):

```python
# src/nexus/schema/sync.py
# GitHub sync client and orchestrator for the schema product catalog.
# Author: Pierre Grothe
# Date: 2026-06-11
"""SchemaSyncSource, GitHubProductCatalogClient, SchemaSync."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

__all__ = [
    "SchemaSyncSource",
]

_CONFIG = ConfigDict(frozen=True, strict=True, extra="forbid")


class SchemaSyncSource(BaseModel):
    """Record of where a catalog was fetched from.

    Args:
        repo: Canonical owner/name GitHub slug.
        branch: Branch name.
        path: Path to the catalog file within the repo.
    """

    model_config = _CONFIG

    repo: str
    branch: str
    path: str
```

- [ ] **Step 4: Create product_registry.py**

Create `src/nexus/schema/product_registry.py`:

```python
# src/nexus/schema/product_registry.py
# Reads and writes the schema product catalog cache.
# Author: Pierre Grothe
# Date: 2026-06-11
"""ProductRegistry: load/save/resolve SchemaProductCatalog from disk."""

from __future__ import annotations

import importlib.resources
import json
import logging
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

from nexus.config.types import UtcDatetime
from nexus.schema.products import SchemaProduct, SchemaProductCatalog
from nexus.schema.sync import SchemaSyncSource

log = logging.getLogger(__name__)

__all__ = ["CachedSchemaProductCatalog", "ProductRegistry"]

_CONFIG = ConfigDict(frozen=True, strict=True, extra="forbid")
_CATALOG_FILE = "catalog.json"


class CachedSchemaProductCatalog(BaseModel):
    """On-disk wrapper that adds provenance and timestamp to a catalog.

    Args:
        catalog: The catalog payload.
        source: Repo / branch / path the catalog was fetched from.
        cached_at: UTC timestamp the cache was written.
    """

    model_config = _CONFIG

    catalog: SchemaProductCatalog
    source: SchemaSyncSource
    cached_at: UtcDatetime


class ProductRegistry:
    """Owns the on-disk schema product catalog cache.

    Args:
        schema_dir: Filesystem directory for the cache.
            Typically ``NexusPaths.schema_dir``.
    """

    def __init__(self, schema_dir: Path) -> None:
        """See class docstring."""
        self._dir = schema_dir

    def load_catalog(self) -> SchemaProductCatalog:
        """Return the synced catalog, or the bundled default if no sync yet.

        Returns:
            A valid SchemaProductCatalog; never raises.
        """
        cached = self.load_cached()
        if cached is not None:
            return cached.catalog
        return self._load_bundled()

    def load_cached(self) -> CachedSchemaProductCatalog | None:
        """Read the on-disk cache. Returns None when absent or unreadable.

        Returns:
            The cached entry, or None.
        """
        target = self._dir / _CATALOG_FILE
        if not target.exists():
            return None
        try:
            payload = target.read_text(encoding="utf-8")
        except OSError as exc:
            log.warning("schema catalog read failed (%s): %s", type(exc).__name__, exc)
            return None
        try:
            return CachedSchemaProductCatalog.model_validate_json(payload)
        except (json.JSONDecodeError, ValidationError) as exc:
            log.warning("schema catalog invalid (%s): %s", type(exc).__name__, exc)
            return None

    def save_catalog(
        self, catalog: SchemaProductCatalog, source: SchemaSyncSource
    ) -> CachedSchemaProductCatalog:
        """Atomically persist catalog + source to disk.

        Args:
            catalog: The catalog to persist.
            source: Provenance record.

        Returns:
            The CachedSchemaProductCatalog that was written.

        Raises:
            OSError: If the directory cannot be created or file cannot be written.
        """
        self._dir.mkdir(parents=True, exist_ok=True)
        cached = CachedSchemaProductCatalog(
            catalog=catalog,
            source=source,
            cached_at=datetime.now(UTC),
        )
        target = self._dir / _CATALOG_FILE
        fd, tmp_path = tempfile.mkstemp(dir=target.parent, suffix=".tmp")
        try:
            with open(fd, "w", encoding="utf-8") as f:
                f.write(cached.model_dump_json(indent=2))
            Path(tmp_path).replace(target)
        except OSError:
            Path(tmp_path).unlink(missing_ok=True)
            raise
        log.info(
            "schema catalog cached: source=%s/%s/%s entries=%d",
            source.repo,
            source.branch,
            source.path,
            len(catalog.products),
        )
        return cached

    def resolve(self, ref: str) -> SchemaProduct | None:
        """Resolve a product reference using the best available catalog.

        Args:
            ref: Key, acronym, or full product name.

        Returns:
            The matching SchemaProduct, or None.
        """
        return self.load_catalog().resolve(ref)

    @staticmethod
    def _load_bundled() -> SchemaProductCatalog:
        data = (
            importlib.resources.files("nexus.schema")
            .joinpath("products.json")
            .read_text(encoding="utf-8")
        )
        return SchemaProductCatalog.model_validate_json(data)
```

- [ ] **Step 5: Run tests**

```
pytest tests/schema/test_schema_product_registry.py -v
```

Expected: all 6 tests pass.

- [ ] **Step 6: Create FakeProductRegistry**

Create `tests/fakes/fake_product_registry.py`:

```python
# tests/fakes/fake_product_registry.py
# In-memory ProductRegistry for CLI tests.
# Author: Pierre Grothe
# Date: 2026-06-11
"""FakeProductRegistry: injectable stand-in backed by a fixed catalog."""

from __future__ import annotations

from nexus.schema.product_registry import CachedSchemaProductCatalog, ProductRegistry
from nexus.schema.products import SchemaProduct, SchemaProductCatalog

__all__ = ["FakeProductRegistry"]


class FakeProductRegistry(ProductRegistry):
    """ProductRegistry that reads from a fixed in-memory catalog.

    Args:
        catalog: The catalog to serve from load_catalog() and resolve().
    """

    def __init__(self, catalog: SchemaProductCatalog) -> None:
        """See class docstring."""
        from pathlib import Path

        super().__init__(Path("/fake"))
        self._catalog = catalog

    def load_catalog(self) -> SchemaProductCatalog:
        """Return the fixed catalog."""
        return self._catalog

    def load_cached(self) -> CachedSchemaProductCatalog | None:
        """Always returns None -- no on-disk state."""
        return None

    def resolve(self, ref: str) -> SchemaProduct | None:
        """Resolve against the fixed catalog."""
        return self._catalog.resolve(ref)
```

- [ ] **Step 7: Commit**

```
git add src/nexus/schema/product_registry.py src/nexus/schema/sync.py \
        tests/schema/test_schema_product_registry.py \
        tests/fakes/fake_product_registry.py
git commit -m "feat(schema): ProductRegistry with load/save/resolve and bundled fallback"
```

---

## Task 5: SchemaSync

**Files:**
- Modify: `src/nexus/schema/sync.py` (add client + orchestrator)
- Create: `tests/schema/test_schema_sync.py`

- [ ] **Step 1: Write failing tests**

Create `tests/schema/test_schema_sync.py`:

```python
# tests/schema/test_schema_sync.py
# Tests for GitHubProductCatalogClient and SchemaSync.
# Author: Pierre Grothe
# Date: 2026-06-11
"""Sync client fetches SchemaProductCatalog; SchemaSync caches it."""

import json
from pathlib import Path

import httpx
import pytest

from nexus.schema.models import ScopeEntry
from nexus.schema.product_registry import ProductRegistry
from nexus.schema.products import SchemaProduct, SchemaProductCatalog
from nexus.schema.sync import GitHubProductCatalogClient, SchemaSync, SchemaSyncSource


def _catalog_json() -> str:
    catalog = SchemaProductCatalog(
        version="1.0",
        products=(
            SchemaProduct(
                key="ham",
                acronym="HAM",
                name="Hardware Asset Management",
                scopes=(ScopeEntry(key="sn_hamp", label="HAM Pro"),),
                bridge_targets=("cmdb_ci",),
            ),
        ),
    )
    return catalog.model_dump_json()


class _OkTransport(httpx.BaseTransport):
    def __init__(self, body: str) -> None:
        self._body = body

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=self._body)


class _ErrorTransport(httpx.BaseTransport):
    def __init__(self, status: int) -> None:
        self._status = status

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        return httpx.Response(self._status)


def test_github_product_catalog_client_returns_catalog_on_200() -> None:
    client = GitHubProductCatalogClient(
        httpx_client=httpx.Client(transport=_OkTransport(_catalog_json()))
    )
    result = client.fetch_catalog("owner/repo", "main", "schema/products.json")
    assert result is not None
    assert result.resolve("ham") is not None


def test_github_product_catalog_client_returns_none_on_404() -> None:
    client = GitHubProductCatalogClient(
        httpx_client=httpx.Client(transport=_ErrorTransport(404))
    )
    assert client.fetch_catalog("owner/repo", "main", "schema/products.json") is None


def test_github_product_catalog_client_returns_none_on_invalid_json() -> None:
    client = GitHubProductCatalogClient(
        httpx_client=httpx.Client(transport=_OkTransport("not-json"))
    )
    assert client.fetch_catalog("owner/repo", "main", "schema/products.json") is None


def test_schema_sync_run_ok_caches_catalog(tmp_path: Path) -> None:
    http_client = httpx.Client(transport=_OkTransport(_catalog_json()))
    catalog_client = GitHubProductCatalogClient(httpx_client=http_client)
    registry = ProductRegistry(tmp_path)
    report = SchemaSync(client=catalog_client, registry=registry).run(
        repo="owner/repo", branch="main", path="schema/products.json"
    )
    assert report.outcome == "ok"
    assert report.cached is not None
    assert registry.resolve("ham") is not None


def test_schema_sync_run_fetch_failed_preserves_existing_cache(tmp_path: Path) -> None:
    registry = ProductRegistry(tmp_path)
    registry.save_catalog(
        SchemaProductCatalog(
            version="1.0",
            products=(
                SchemaProduct(
                    key="old",
                    acronym="OLD",
                    name="Old Product",
                    scopes=(),
                    bridge_targets=(),
                ),
            ),
        ),
        SchemaSyncSource(repo="owner/repo", branch="main", path="schema/products.json"),
    )

    http_client = httpx.Client(transport=_ErrorTransport(500))
    catalog_client = GitHubProductCatalogClient(httpx_client=http_client)
    report = SchemaSync(client=catalog_client, registry=registry).run(
        repo="owner/repo", branch="main", path="schema/products.json"
    )
    assert report.outcome == "fetch-failed"
    assert registry.resolve("old") is not None
```

- [ ] **Step 2: Run to confirm failure**

```
pytest tests/schema/test_schema_sync.py -v
```

Expected: `ImportError` on `GitHubProductCatalogClient` and `SchemaSync`.

- [ ] **Step 3: Implement sync.py (full)**

Replace the stub content of `src/nexus/schema/sync.py` with the full implementation:

```python
# src/nexus/schema/sync.py
# GitHub sync client and orchestrator for the schema product catalog.
# Author: Pierre Grothe
# Date: 2026-06-11
"""SchemaSyncSource, GitHubProductCatalogClient, SchemaSync, SchemaSyncReport."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from nexus.schema.products import SchemaProductCatalog

if TYPE_CHECKING:
    from nexus.schema.product_registry import CachedSchemaProductCatalog, ProductRegistry

log = logging.getLogger(__name__)

__all__ = [
    "GitHubProductCatalogClient",
    "SchemaSync",
    "SchemaSyncReport",
    "SchemaSyncSource",
]

_CONFIG = ConfigDict(frozen=True, strict=True, extra="forbid")
_DEFAULT_TIMEOUT = 10.0
_OutcomeT = Literal["ok", "fetch-failed"]


class SchemaSyncSource(BaseModel):
    """Record of where a catalog was fetched from.

    Args:
        repo: Canonical owner/name GitHub slug.
        branch: Branch name.
        path: Path to the catalog file within the repo.
    """

    model_config = _CONFIG

    repo: str
    branch: str
    path: str


@dataclass(frozen=True, slots=True)
class SchemaSyncReport:
    """Typed result of a SchemaSync.run() call.

    Attributes:
        outcome: "ok" or "fetch-failed".
        cached: The cached entry on success, else None.
        reason: One-line failure description when outcome != "ok".
    """

    outcome: _OutcomeT
    cached: CachedSchemaProductCatalog | None
    reason: str | None


class GitHubProductCatalogClient:
    """Anonymous fetcher for the raw GitHub schema product catalog.

    Args:
        httpx_client: Optional pre-built httpx.Client. Tests inject one
            backed by a transport stub. Production callers omit it.
        timeout_seconds: HTTP timeout when building the default client.
    """

    def __init__(
        self,
        *,
        httpx_client: httpx.Client | None = None,
        timeout_seconds: float = _DEFAULT_TIMEOUT,
    ) -> None:
        """See class docstring."""
        self._injected = httpx_client
        self._timeout = timeout_seconds

    def fetch_catalog(
        self, repo: str, branch: str, path: str
    ) -> SchemaProductCatalog | None:
        """GET the raw catalog JSON. Returns None on any failure.

        Args:
            repo: Canonical owner/name slug.
            branch: GitHub branch name.
            path: Path within the repo (e.g. "schema/products.json").

        Returns:
            Parsed SchemaProductCatalog, or None on any failure.
        """
        url = f"https://raw.githubusercontent.com/{repo}/{branch}/{path}"
        try:
            if self._injected is not None:
                response = self._injected.get(url)
            else:
                with httpx.Client(timeout=self._timeout) as client:
                    response = client.get(url)
        except httpx.HTTPError as exc:
            log.info("catalog fetch failed (%s): %s", type(exc).__name__, exc)
            return None
        if response.status_code != 200:
            log.warning("catalog fetch status=%d url=%s", response.status_code, url)
            return None
        try:
            return SchemaProductCatalog.model_validate_json(response.text)
        except (json.JSONDecodeError, ValidationError) as exc:
            log.info("catalog parse error (%s): %s", type(exc).__name__, exc)
            return None


class SchemaSync:
    """Orchestrates a single schema catalog sync run.

    Args:
        client: GitHubProductCatalogClient (or test subclass).
        registry: ProductRegistry to receive the cached catalog.
    """

    def __init__(
        self, *, client: GitHubProductCatalogClient, registry: ProductRegistry
    ) -> None:
        """See class docstring."""
        self._client = client
        self._registry = registry

    def run(self, *, repo: str, branch: str, path: str) -> SchemaSyncReport:
        """Fetch the catalog, cache it, and return a typed report.

        Args:
            repo: GitHub owner/name slug (already validated by caller).
            branch: GitHub branch name.
            path: Path to the catalog within the repo.

        Returns:
            SchemaSyncReport with outcome "ok" or "fetch-failed".
        """
        wire = self._client.fetch_catalog(repo, branch, path)
        if wire is None:
            return SchemaSyncReport(
                outcome="fetch-failed",
                cached=None,
                reason="Fetch failed (see log for details).",
            )
        source = SchemaSyncSource(repo=repo, branch=branch, path=path)
        try:
            cached = self._registry.save_catalog(wire, source)
        except OSError as exc:
            return SchemaSyncReport(
                outcome="fetch-failed",
                cached=None,
                reason=f"Cache write failed: {type(exc).__name__}",
            )
        return SchemaSyncReport(outcome="ok", cached=cached, reason=None)
```

- [ ] **Step 4: Run tests**

```
pytest tests/schema/test_schema_sync.py -v
```

Expected: all 5 tests pass.

- [ ] **Step 5: Commit**

```
git add src/nexus/schema/sync.py tests/schema/test_schema_sync.py
git commit -m "feat(schema): GitHubProductCatalogClient + SchemaSync + SchemaSyncReport"
```

---

## Task 6: Wire SchemaSync into commands_sync.py

**Files:**
- Modify: `src/nexus/cli/commands_sync.py`

- [ ] **Step 1: Update _sync_main to also run SchemaSync**

In `src/nexus/cli/commands_sync.py`, add imports after the existing ones:

```python
from nexus.config.paths import NexusPaths
from nexus.schema.product_registry import ProductRegistry
from nexus.schema.sync import GitHubProductCatalogClient, SchemaSync
```

Change `_DEFAULT_MANIFEST_PATH` and add a catalog path constant:

```python
_DEFAULT_MANIFEST_PATH = "templates/manifest.json"
_DEFAULT_CATALOG_PATH = "schema/products.json"
```

Replace `_sync_main` with:

```python
def _sync_main(
    *,
    paths: NexusPaths,
    config_manager: ConfigManager,
    client: GitHubTemplateClient,
    console_out: Console,
    console_err: Console,
    manifest_path: str = _DEFAULT_MANIFEST_PATH,
    catalog_path: str = _DEFAULT_CATALOG_PATH,
    catalog_client: GitHubProductCatalogClient | None = None,
) -> int:
    """Core sync logic; returns exit code (0 success, 1 error).

    Args:
        paths: NexusPaths rooted at the runtime .nexus/ dir.
        config_manager: ConfigManager to load github_repo / github_branch.
        client: GitHubTemplateClient for the template manifest HTTP fetch.
        console_out: Rich console for user-facing status.
        console_err: Rich console for errors.
        manifest_path: Path to the template manifest within the repo.
        catalog_path: Path to the schema product catalog within the repo.
        catalog_client: GitHubProductCatalogClient (injectable for tests).

    Returns:
        0 on success; 1 if the template sync fails (catalog failure is
        non-fatal and never causes a non-zero exit).
    """
    preferences = config_manager.load().preferences
    registry = TemplateRegistry(paths.templates_dir)
    orchestrator = GitHubSync(client=client, registry=registry)
    report = orchestrator.run(
        repo=preferences.github_repo,
        branch=preferences.github_branch,
        path=manifest_path,
    )
    exit_code = _render_sync_report(report, console_out, console_err)
    if exit_code != 0:
        return exit_code

    # Schema product catalog sync -- best-effort, never blocks template sync.
    _sync_schema_catalog(
        repo=preferences.github_repo,
        branch=preferences.github_branch,
        path=catalog_path,
        schema_dir=paths.schema_dir,
        catalog_client=catalog_client or GitHubProductCatalogClient(),
        console_out=console_out,
        console_err=console_err,
    )
    return 0


def _sync_schema_catalog(
    *,
    repo: str,
    branch: str,
    path: str,
    schema_dir: Path,
    catalog_client: GitHubProductCatalogClient,
    console_out: Console,
    console_err: Console,
) -> None:
    """Run SchemaSync and print a one-line result. Never raises.

    Args:
        repo: GitHub owner/name slug.
        branch: GitHub branch name.
        path: Path to the catalog within the repo.
        schema_dir: Local cache directory.
        catalog_client: HTTP client for the fetch.
        console_out: Rich console for success output.
        console_err: Rich console for warnings.
    """
    from nexus.schema.product_registry import ProductRegistry
    from nexus.schema.sync import SchemaSync

    schema_registry = ProductRegistry(schema_dir)
    schema_report = SchemaSync(client=catalog_client, registry=schema_registry).run(
        repo=repo, branch=branch, path=path
    )
    if schema_report.outcome == "ok" and schema_report.cached is not None:
        count = len(schema_report.cached.catalog.products)
        console_out.print(
            Notice.info(f"Synced {count} schema products from {repo}@{branch}.")
        )
    else:
        console_err.print(
            Notice.warn(
                "Schema product catalog sync failed (see log). "
                "Using cached or bundled catalog."
            )
        )
```

Also add `Path` to the imports at the top of the file:
```python
from pathlib import Path
```

- [ ] **Step 2: Run the full CLI sync tests**

```
pytest tests/ -k "sync" -v --timeout=30
```

Expected: all pass (no sync-specific tests existed before, but nothing should break).

- [ ] **Step 3: Commit**

```
git add src/nexus/cli/commands_sync.py
git commit -m "feat(cli): nexus sync also fetches schema product catalog (best-effort)"
```

---

## Task 7: Update commands_schema.py for product resolution

**Files:**
- Modify: `src/nexus/cli/commands_schema.py`
- Modify: `src/nexus/cli/views.py`
- Modify: `src/nexus/cli/help_text.py`
- Modify: `tests/cli/test_commands_schema.py`

- [ ] **Step 1: Add _build_schema_area helper to commands_schema.py and update imports**

In `src/nexus/cli/commands_schema.py`, change the imports block to:

```python
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

import typer

from nexus.api.errors import KrokiError
from nexus.api.kroki_client import DEFAULT_KROKI_TIMEOUT, DEFAULT_KROKI_URL, ImageFormat
from nexus.cli.apps import schema_app
from nexus.cli.auth import config_default as _config_default
from nexus.cli.console import console
from nexus.cli.help_text import SCHEMA_HELP, SCHEMA_PARENT, guide_items
from nexus.cli.views import _build_offline_schema_renderer, _build_schema_cartographer
from nexus.config.paths import NexusPaths
from nexus.schema.errors import SchemaError
from nexus.schema.models import SchemaArea, ScopeEntry
from nexus.schema.product_registry import ProductRegistry
from nexus.schema.products import SchemaProduct, SchemaProductCatalog
from nexus.ui import CommandGuide, CommandHelp, Hint, Notice, nexus_progress
```

- [ ] **Step 2: Add _build_schema_area helper**

Add this function before the `schema_callback`:

```python
def _build_schema_area(
    product: str,
    product2: str | None,
    catalog: SchemaProductCatalog,
) -> SchemaArea | None:
    """Resolve 1-2 product references to a SchemaArea. Prints errors and returns None on failure.

    Args:
        product: First product reference (key, acronym, or name).
        product2: Optional second product reference.
        catalog: The catalog to resolve against.

    Returns:
        A SchemaArea on success, None if any error was printed.
    """
    p1 = catalog.resolve(product)
    if p1 is None:
        valid = ", ".join(p.key for p in catalog.products)
        console.print(Notice.error(f"Unknown product {product!r}. Available: {valid}."))
        console.print(Hint(label="List products", command="nexus schema products"))
        return None

    if product2 is None:
        if not p1.scopes:
            console.print(
                Notice.error(
                    f"Product {p1.key!r} has no discoverable scopes. "
                    "Use it as the second argument to combine with a scoped product."
                )
            )
            return None
        return SchemaArea(
            key=p1.key,
            display=p1.name,
            scopes=tuple(ScopeEntry(key=s.key, label=s.label) for s in p1.scopes),
            bridge_targets=p1.bridge_targets,
        )

    p2 = catalog.resolve(product2)
    if p2 is None:
        valid = ", ".join(p.key for p in catalog.products)
        console.print(Notice.error(f"Unknown product {product2!r}. Available: {valid}."))
        console.print(Hint(label="List products", command="nexus schema products"))
        return None

    if not p1.scopes and not p2.scopes:
        console.print(
            Notice.error(
                f"Cannot combine two bridge-only products ({p1.key!r} and {p2.key!r}). "
                "At least one must have scopes."
            )
        )
        return None

    if p1.scopes and p2.scopes:
        combined_scopes = (*p1.scopes, *p2.scopes)
        combined_bridge = (*p1.bridge_targets, *p2.bridge_targets)
    elif p1.scopes:
        combined_scopes = p1.scopes
        combined_bridge = p2.bridge_targets
    else:
        combined_scopes = p2.scopes
        combined_bridge = p1.bridge_targets

    return SchemaArea(
        key=f"{p1.key}-{p2.key}",
        display=f"{p1.name} + {p2.name}",
        scopes=tuple(ScopeEntry(key=s.key, label=s.label) for s in combined_scopes),
        bridge_targets=combined_bridge,
    )
```

- [ ] **Step 3: Replace schema_areas command with schema_products**

Replace the `schema_areas` command with:

```python
@schema_app.command("products")
def schema_products() -> None:
    """List available schema products and their scopes."""
    registry = ProductRegistry(NexusPaths.from_env().schema_dir)
    catalog = registry.load_catalog()
    cached = registry.load_cached()
    for p in catalog.products:
        scope_str = ", ".join(s.key for s in p.scopes) or "(bridge-only)"
        bridge_str = f"  bridge: {', '.join(p.bridge_targets)}" if p.bridge_targets else ""
        console.print(f"{p.key}  [{p.acronym}]  {p.name}  ({scope_str}){bridge_str}")
    if cached is not None:
        from nexus.cli.utils import humanize_age
        from datetime import UTC, datetime

        age = datetime.now(UTC) - cached.cached_at
        console.print(f"(synced {humanize_age(age)} via {cached.source.repo}@{cached.source.branch})")
    else:
        console.print("(bundled)")
```

- [ ] **Step 4: Replace schema_erd command**

Replace the entire `schema_erd` function with:

```python
@schema_app.command("erd")
def schema_erd(
    product: Annotated[str, typer.Argument(help="Product name, acronym, or key")],
    product2: Annotated[
        str | None, typer.Argument(help="Second product to combine (optional, max 2)")
    ] = None,
    profile: Annotated[str, typer.Option(help="Instance profile name")] = "",
    output: Annotated[
        Path | None, typer.Option("-o", "--output", help="Output Markdown path")
    ] = None,
    image: Annotated[
        ImageFormat | None,
        typer.Option("--image", help="Also render a shareable image (svg or png) via Kroki"),
    ] = None,
    grouped: Annotated[
        bool,
        typer.Option("--grouped", help="Split the ERD into one Mermaid diagram per scope"),
    ] = False,
    save_archive: Annotated[
        bool,
        typer.Option("--save-archive", help="Also persist the discovered graph as a JSON snapshot"),
    ] = False,
    from_archive: Annotated[
        Path | None,
        typer.Option(
            "--from-archive",
            help="Re-render offline from a saved JSON snapshot (no instance access)",
        ),
    ] = None,
    kroki_url: Annotated[
        str, typer.Option("--kroki-url", envvar="NEXUS_KROKI_URL", help="Kroki render endpoint")
    ] = DEFAULT_KROKI_URL,
    kroki_timeout: Annotated[
        float, typer.Option("--kroki-timeout", help="Kroki request timeout in seconds")
    ] = DEFAULT_KROKI_TIMEOUT,
) -> None:
    """Reverse-engineer one or two products and write a Markdown ERD."""
    if save_archive and from_archive is not None:
        console.print(Notice.error("--save-archive cannot be combined with --from-archive."))
        raise typer.Exit(2)

    catalog = ProductRegistry(NexusPaths.from_env().schema_dir).load_catalog()

    if from_archive is None:
        area = _build_schema_area(product, product2, catalog)
        if area is None:
            raise typer.Exit(2)

    async def _run_live() -> None:
        assert area is not None
        cartographer, client = _build_schema_cartographer(
            profile, kroki_url, kroki_timeout, areas={area.key: area}
        )
        resolved = profile or _config_default()
        labels = {s.key: s.label for s in area.scopes}
        with nexus_progress(console) as progress:
            progress.add_task(f"Mapping {area.key} on {resolved}...", total=None)
            async with client:
                graph = await cartographer.discover(resolved, area.key)
            if not graph.tables:
                console.print(Notice.warn(f"No tables discovered for {area.key} on {resolved}."))
            if save_archive:
                snapshot = cartographer.save_archive(graph)
                console.print(f"Wrote archive to {snapshot}")
            markdown = (
                cartographer.render_erd_grouped(graph, labels)
                if grouped
                else cartographer.render_erd(graph)
            )
            dest = output or Path(f"{area.key}-{resolved}.md")
            dest.write_text(markdown, encoding="utf-8")
            console.print(f"Wrote ERD to {dest}")
            if image is not None:
                progress.add_task(f"Rendering {image} via {kroki_url}...", total=None)
                if grouped:
                    images = await cartographer.render_erd_group_images(graph, labels, fmt=image)
                    for key, data in images:
                        img_dest = dest.with_name(f"{dest.stem}-{key}.{image}")
                        img_dest.write_bytes(data)
                        console.print(f"Wrote image to {img_dest}")
                else:
                    data = await cartographer.render_erd_image(graph, fmt=image)
                    img_dest = dest.with_suffix(f".{image}")
                    img_dest.write_bytes(data)
                    console.print(f"Wrote image to {img_dest}")

    async def _run_offline(snapshot: Path) -> None:
        reader, emitter, kroki = _build_offline_schema_renderer(kroki_url, kroki_timeout)
        graph = reader.read(snapshot)
        snap_product = catalog.resolve(graph.area_key)
        labels = {s.key: s.label for s in snap_product.scopes} if snap_product else {}
        if from_archive is not None and product != graph.area_key:
            console.print(
                Notice.warn(f"archive contains area {graph.area_key}, ignoring argument {product}")
            )
        markdown = emitter.render_grouped(graph, labels) if grouped else emitter.render(graph)
        dest = output or Path(f"{graph.area_key}-{graph.instance_id}.md")
        dest.write_text(markdown, encoding="utf-8")
        console.print(f"Wrote ERD to {dest}")
        if image is not None:
            from nexus.ui import nexus_progress as _np

            with _np(console) as progress:
                progress.add_task(f"Rendering {image} via {kroki_url}...", total=None)
                if grouped:
                    for group in emitter.group_diagrams(graph, labels):
                        data = await kroki.render(group.source, fmt=image)
                        img_dest = dest.with_name(f"{dest.stem}-{group.key}.{image}")
                        img_dest.write_bytes(data)
                        console.print(f"Wrote image to {img_dest}")
                else:
                    data = await kroki.render(emitter.diagram(graph), fmt=image)
                    img_dest = dest.with_suffix(f".{image}")
                    img_dest.write_bytes(data)
                    console.print(f"Wrote image to {img_dest}")

    try:
        if from_archive is not None:
            asyncio.run(_run_offline(from_archive))
        else:
            asyncio.run(_run_live())
    except SchemaError as exc:
        console.print(Notice.error(str(exc)))
        raise typer.Exit(1) from exc
    except KrokiError as exc:
        console.print(Notice.error(str(exc)))
        console.print(
            Hint(
                label="Kroki",
                command="--kroki-url <endpoint> --kroki-timeout <seconds>",
                suffix="(self-hosting guide: docs/schema-image-export.md)",
            )
        )
        raise typer.Exit(1) from exc
```

- [ ] **Step 5: Update _build_schema_cartographer in views.py to accept areas**

In `src/nexus/cli/views.py` change the signature of `_build_schema_cartographer`:

```python
from collections.abc import Mapping

from nexus.schema.models import SchemaArea
```

Add to the existing imports block, then change the function signature:

```python
def _build_schema_cartographer(
    profile: str,
    kroki_url: str,
    kroki_timeout: float,
    areas: Mapping[str, SchemaArea] | None = None,
) -> tuple[SchemaCartographer, ServiceNowClient]:
    """Build a SchemaCartographer for the given registered instance profile.

    Args:
        profile: Instance profile name from InstanceRegistry.
        kroki_url: Kroki render endpoint for diagram image export.
        kroki_timeout: Per-request Kroki timeout in seconds.
        areas: Area registry to inject. Uses DEFAULT_AREAS when None.

    Returns:
        Tuple of (SchemaCartographer, ServiceNowClient) for the caller to use.
    """
    from nexus.schema.areas import DEFAULT_AREAS

    _, meta, token, _ = _acquire_token(profile)
    client = ServiceNowClient(instance_url=meta.url, token=token)
    cartographer = SchemaCartographer(
        client=client,
        areas=areas if areas is not None else DEFAULT_AREAS,
        archive_root=NexusPaths.from_env().schema_dir,
        kroki=KrokiClient(kroki_url, timeout=kroki_timeout),
    )
    return cartographer, client
```

- [ ] **Step 6: Update help_text.py**

In `src/nexus/cli/help_text.py`, find `SCHEMA_HELP` and update the two entries:

```python
SCHEMA_HELP: list[CommandHelpEntry] = [
    help_entry(
        "products",
        "List the available schema products and the ServiceNow scopes each "
        "covers. Product keys, acronyms, and full names are all accepted by 'erd'.",
        "nexus schema products",
    ),
    help_entry(
        "erd <product> [product2]",
        "Reverse-engineer one or two products into a Mermaid ERD. Accepts key, "
        "acronym, or full name. Pass --image svg|png to also export a diagram image.",
        "nexus schema erd HAM ITSM --image svg",
    ),
]
```

Also update `SCHEMA_PARENT` example:
```python
SCHEMA_PARENT = help_entry(
    "schema",
    "Reverse-engineer ServiceNow table schemas: list available products, then "
    "generate an ERD -- optionally as an SVG or PNG image via Kroki.",
    "nexus schema erd HAM --image svg",
)
```

- [ ] **Step 7: Update existing tests in test_commands_schema.py**

The existing tests use `"doc-designer"` as the area arg and check for `"areas"` in the commands list. Update them:

1. In `test_schema_areas_lists_registered_areas` rename to `test_schema_products_lists_products` and change:
```python
def test_schema_products_lists_products() -> None:
    result = CliRunner().invoke(app, ["schema", "products"])
    assert result.exit_code == 0
    assert "doc-designer" in result.stdout
```

2. In `test_schema_erd_writes_markdown_file` the first positional arg changes from `"doc-designer"` to `"doc-designer"` -- the key is unchanged so the call stays the same, but the `ProductRegistry` needs to be injectable. Patch it:

Add a helper at the top of the test file:

```python
from tests.fakes.fake_product_registry import FakeProductRegistry
from nexus.schema.models import ScopeEntry
from nexus.schema.products import SchemaProduct, SchemaProductCatalog
from nexus.cli import commands_schema as _cs_module

def _fake_registry() -> FakeProductRegistry:
    return FakeProductRegistry(
        SchemaProductCatalog(
            version="1.0",
            products=(
                SchemaProduct(
                    key="doc-designer",
                    acronym="DOC",
                    name="Document Designer",
                    scopes=(
                        ScopeEntry(key="sn_grc_doc_design", label="Document Designer with Word"),
                        ScopeEntry(key="sn_grc_rel_config", label="Data Relationships Framework"),
                    ),
                    bridge_targets=(),
                ),
                SchemaProduct(
                    key="bcm",
                    acronym="BCM",
                    name="Business Continuity Management",
                    scopes=(ScopeEntry(key="sn_bcm", label="BCM Core"),),
                    bridge_targets=(),
                ),
            ),
        )
    )
```

Add a `_patch_registry` helper:
```python
def _patch_registry(monkeypatch: pytest.MonkeyPatch, registry: FakeProductRegistry) -> None:
    monkeypatch.setattr(_cs_module, "ProductRegistry", lambda _path: registry)
```

Then add `_patch_registry(monkeypatch, _fake_registry())` to every test that currently invokes `schema erd` with a product key.

3. `test_schema_erd_unknown_area_exits_two_without_auth` becomes `test_schema_erd_unknown_product_exits_two_without_auth`:
```python
def test_schema_erd_unknown_product_exits_two_without_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _forbid(*_: object) -> tuple[object, object]:
        raise AssertionError("auth path must not run")

    monkeypatch.setattr(commands_schema, "_build_schema_cartographer", _forbid)
    monkeypatch.setattr(commands_schema, "ProductRegistry", lambda _path: _fake_registry())
    result = CliRunner().invoke(app, ["schema", "erd", "no-such-product"])
    assert result.exit_code == 2, result.stdout
    assert "no-such-product" in result.stdout
    assert "nexus schema products" in result.stdout
```

4. Add new tests for two-product combination and bridge-only errors:
```python
def test_schema_erd_two_products_union_scopes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nexus.schema.products import SchemaProductCatalog, SchemaProduct
    from tests.fakes.fake_product_registry import FakeProductRegistry

    catalog = SchemaProductCatalog(
        version="1.0",
        products=(
            SchemaProduct(
                key="ham",
                acronym="HAM",
                name="Hardware Asset Management",
                scopes=(ScopeEntry(key="sn_hamp", label="HAM Pro"),),
                bridge_targets=("cmdb_ci",),
            ),
            SchemaProduct(
                key="itsm",
                acronym="ITSM",
                name="IT Service Management",
                scopes=(),
                bridge_targets=("incident", "cmdb_ci"),
            ),
        ),
    )
    graph = _graph().model_copy(update={"area_key": "ham-itsm"})
    fake = FakeSchemaCartographer(graph)
    _patch_builder(monkeypatch, fake)
    monkeypatch.setattr(commands_schema, "ProductRegistry", lambda _path: FakeProductRegistry(catalog))
    out = tmp_path / "erd.md"
    result = CliRunner().invoke(
        app, ["schema", "erd", "ham", "itsm", "--profile", "alectri", "-o", str(out)]
    )
    assert result.exit_code == 0, result.stdout
    assert out.is_file()


def test_schema_erd_two_bridge_only_products_exits_two(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from nexus.schema.products import SchemaProductCatalog, SchemaProduct
    from tests.fakes.fake_product_registry import FakeProductRegistry

    catalog = SchemaProductCatalog(
        version="1.0",
        products=(
            SchemaProduct(key="a", acronym="A", name="Product A", scopes=(), bridge_targets=("t1",)),
            SchemaProduct(key="b", acronym="B", name="Product B", scopes=(), bridge_targets=("t2",)),
        ),
    )
    monkeypatch.setattr(commands_schema, "ProductRegistry", lambda _path: FakeProductRegistry(catalog))
    result = CliRunner().invoke(app, ["schema", "erd", "a", "b"])
    assert result.exit_code == 2, result.stdout
    assert "bridge-only" in result.stdout


def test_schema_products_command_shows_bundled_footer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(commands_schema, "ProductRegistry", lambda _path: _fake_registry())
    result = CliRunner().invoke(app, ["schema", "products"])
    assert result.exit_code == 0
    assert "(bundled)" in result.stdout
```

5. Update `test_help_text_registers_schema_entries`:
```python
def test_help_text_registers_schema_entries() -> None:
    assert any(entry.command == "schema" for entry in TOP_LEVEL_HELP)
    assert SCHEMA_PARENT.command == "schema"
    commands = [entry.command for entry in SCHEMA_HELP]
    assert "products" in commands
    assert "erd <product> [product2]" in commands
```

- [ ] **Step 8: Run schema CLI tests**

```
pytest tests/cli/test_commands_schema.py -v --timeout=30
```

Fix any failures before continuing. Common issues: `NexusPaths.from_env()` being called inside `ProductRegistry.__init__` -- the constructor takes a `Path`, not `NexusPaths`, so you need to monkeypatch `ProductRegistry` in the CLI, not `NexusPaths`.

- [ ] **Step 9: Commit**

```
git add src/nexus/cli/commands_schema.py src/nexus/cli/views.py \
        src/nexus/cli/help_text.py tests/cli/test_commands_schema.py \
        tests/fakes/fake_product_registry.py
git commit -m "feat(cli): nexus schema erd accepts product names/acronyms; adds schema products command"
```

---

## Task 8: Delete areas.py and final cleanup

**Files:**
- Delete: `src/nexus/schema/areas.py`
- Modify: `src/nexus/schema/__init__.py`
- Modify: `src/nexus/schema/discoverer.py`
- Modify: `src/nexus/schema/engine.py`
- Modify: `src/nexus/cli/views.py` (remove DEFAULT_AREAS fallback)
- Rename: `tests/schema/test_schema_areas.py` -> `tests/schema/test_schema_products.py` (already done)
- Modify: `tests/schema/test_schema_exports.py`

- [ ] **Step 1: Update discoverer.py -- remove DEFAULT_AREAS import**

In `src/nexus/schema/discoverer.py` change:
```python
from nexus.schema.areas import DEFAULT_AREAS
from nexus.schema.models import SchemaArea
```
to:
```python
from nexus.schema.models import SchemaArea
```

Change the default parameter `areas: Mapping[str, SchemaArea] = DEFAULT_AREAS` to require injection (no default):
```python
def __init__(
    self,
    client: ServiceNowClientProtocol,
    areas: Mapping[str, SchemaArea],
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> None:
```

- [ ] **Step 2: Update engine.py -- remove DEFAULT_AREAS import**

In `src/nexus/schema/engine.py` change:
```python
from nexus.schema.areas import DEFAULT_AREAS, SchemaArea
from nexus.schema.models import SchemaArea
```
to:
```python
from nexus.schema.models import SchemaArea
```

Change `SchemaCartographer.__init__` default to require areas (no default):
```python
def __init__(
    self,
    client: ServiceNowClientProtocol,
    areas: Mapping[str, SchemaArea],
    *,
    archive_root: Path,
    kroki: KrokiClientProtocol,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> None:
```

- [ ] **Step 3: Update views.py -- remove DEFAULT_AREAS reference**

In `src/nexus/cli/views.py` remove the `from nexus.schema.areas import DEFAULT_AREAS` local import inside `_build_schema_cartographer`, and make `areas` a required parameter:

```python
def _build_schema_cartographer(
    profile: str,
    kroki_url: str,
    kroki_timeout: float,
    areas: Mapping[str, SchemaArea],
) -> tuple[SchemaCartographer, ServiceNowClient]:
    """Build a SchemaCartographer for the given registered instance profile.

    Args:
        profile: Instance profile name from InstanceRegistry.
        kroki_url: Kroki render endpoint for diagram image export.
        kroki_timeout: Per-request Kroki timeout in seconds.
        areas: Area registry for the cartographer.

    Returns:
        Tuple of (SchemaCartographer, ServiceNowClient) for the caller to use.
    """
    _, meta, token, _ = _acquire_token(profile)
    client = ServiceNowClient(instance_url=meta.url, token=token)
    cartographer = SchemaCartographer(
        client=client,
        areas=areas,
        archive_root=NexusPaths.from_env().schema_dir,
        kroki=KrokiClient(kroki_url, timeout=kroki_timeout),
    )
    return cartographer, client
```

- [ ] **Step 4: Update schema/__init__.py**

Replace `src/nexus/schema/__init__.py` with:

```python
# src/nexus/schema/__init__.py
# Schema cartography layer: reverse-engineer a live SN data dictionary into an ERD.
# Author: Pierre Grothe
# Date: 2026-06-08
"""nexus.schema -- ServiceNow data-dictionary cartographer."""

from nexus.schema.engine import SchemaCartographer
from nexus.schema.models import SchemaArea, SchemaGraph, ScopeEntry
from nexus.schema.protocol import SchemaProtocol

__all__ = [
    "SchemaArea",
    "SchemaCartographer",
    "SchemaGraph",
    "SchemaProtocol",
    "ScopeEntry",
]
```

- [ ] **Step 5: Delete areas.py**

```
git rm src/nexus/schema/areas.py
```

- [ ] **Step 6: Delete test_schema_areas.py (already superseded)**

```
git rm tests/schema/test_schema_areas.py
```

- [ ] **Step 7: Update test_schema_exports.py**

Replace `tests/schema/test_schema_exports.py` with:

```python
# tests/schema/test_schema_exports.py
# Tests that the schema package re-exports its public API.
# Author: Pierre Grothe
# Date: 2026-06-08
"""Verify top-level imports resolve and implementations satisfy SchemaProtocol."""

from datetime import UTC, datetime
from pathlib import Path

from nexus.schema import (
    SchemaArea,
    SchemaCartographer,
    SchemaGraph,
    SchemaProtocol,
    ScopeEntry,
)
from tests.fakes.fake_kroki_client import FakeKrokiClient
from tests.fakes.fake_sn_client import FakeServiceNowClient
from tests.schema.fakes.fake_schema_cartographer import FakeSchemaCartographer


def _conforms(c: SchemaProtocol) -> None:
    del c


def _graph() -> SchemaGraph:
    return SchemaGraph(
        instance_id="alectri",
        area_key="doc-designer",
        discovered_at=datetime(2026, 6, 8, tzinfo=UTC),
        scope_keys=("sn_grc_doc_design",),
        tables=(),
        reference_edges=(),
        inheritance_edges=(),
        relationship_edges=(),
    )


def _area() -> SchemaArea:
    return SchemaArea(
        key="doc-designer",
        display="Document Designer",
        scopes=(ScopeEntry(key="sn_grc_doc_design", label="Document Designer with Word"),),
    )


def test_public_symbols_importable() -> None:
    assert SchemaArea is not None
    assert ScopeEntry is not None
    assert SchemaCartographer is not None
    assert SchemaGraph is not None
    assert SchemaProtocol is not None


def test_schema_protocol_engine_and_fake_conform(tmp_path: Path) -> None:
    _conforms(
        SchemaCartographer(
            FakeServiceNowClient(),
            areas={_area().key: _area()},
            archive_root=tmp_path,
            kroki=FakeKrokiClient(),
        )
    )
    _conforms(FakeSchemaCartographer(_graph()))
```

- [ ] **Step 8: Fix FakeSchemaCartographer if it imports from areas**

Check `tests/schema/fakes/fake_schema_cartographer.py` for any `from nexus.schema.areas import` and update to `from nexus.schema.models import SchemaArea`.

- [ ] **Step 9: Run full test suite**

```
pytest tests/ -v --timeout=60 -x
```

Fix any remaining import errors. Common locations: any test that imports `DEFAULT_AREAS` from `nexus.schema`, any test importing `ScopeRef`.

- [ ] **Step 10: Run type checkers**

```
pyright src/nexus/
mypy src/nexus/ --strict
```

Fix all errors. Common: `ScopeRef` references, missing `areas` argument to `SchemaDiscoverer` or `SchemaCartographer`.

- [ ] **Step 11: Run ruff + black**

```
ruff check src/nexus/ tests/
black src/ tests/
```

- [ ] **Step 12: Commit**

```
git add -A
git commit -m "refactor(schema): delete areas.py -- product catalog is now the single source of truth"
```

---

## Task 9: Update demo script + final validation

**Files:**
- Modify: `docs/demo/demo-script-core-sc.md`

- [ ] **Step 1: Update demo script Act 4 narration**

In `docs/demo/demo-script-core-sc.md` replace the `nexus schema areas` reference with `nexus schema products` and update the narration to match.

Find:
```
  nexus schema areas
```
Replace with:
```
  nexus schema products
```

Update the narration accordingly:
```
  [PAUSE] "I have schema snapshots pre-registered for the product areas I
  demo most often. Let me pull the HAM to ITSM bridge -- the exact tables
  and fields where Hardware Asset Management connects to the configuration
  item backbone."
```

Also update the commands list at the bottom:
```
  nexus schema products
```

- [ ] **Step 2: Run the full suite one final time**

```
pytest tests/ --timeout=60
```

Expected: all pass.

- [ ] **Step 3: Final commit**

```
git add docs/demo/demo-script-core-sc.md
git commit -m "docs(demo): update script to use nexus schema products (replaces areas)"
```

---

## Self-Review Checklist

- [x] `ScopeRef` -> `ScopeEntry` rename tracked through discoverer, engine, CLI, tests
- [x] `DEFAULT_AREAS` removal: discoverer + engine no longer have it as a default; CLI always passes explicit areas
- [x] `ScopeEntry.key` (not `.scope`) used everywhere
- [x] `_build_schema_cartographer` signature updated in both views.py and all test patches
- [x] `from_archive` offline path updated to resolve labels from catalog not DEFAULT_AREAS
- [x] `test_schema_erd_from_archive_area_mismatch_warns` still works -- it checks `"archive contains area doc-designer"` which is still printed in `_run_offline`
- [x] `test_help_text_registers_schema_entries` updated for `"products"` and `"erd <product> [product2]"`
- [x] `FakeSchemaCartographer` checked for areas import
- [x] pyproject.toml `products.json` include covered in Task 3
