# Schema Image Export (Kroki) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let `nexus schema erd|mindmap` emit a real, shareable SVG/PNG image (via a Kroki render service) alongside the Markdown, so discovered diagrams paste straight into Teams/email/Confluence.

**Architecture:** `discoverer -> SchemaGraph -> emitter.diagram() (raw Mermaid source) -> KrokiClient.render() (HTTP POST) -> image bytes -> file`. A new `KrokiClient` (api layer, mirrors `agent_client.py`) POSTs the Mermaid source to `{base}/mermaid/{fmt}` and returns bytes. The emitters gain a `diagram()` method returning only the Mermaid source (the part between the ``` fences); `render()` reuses it. `SchemaCartographer` gains an injected `KrokiClientProtocol` and two async `render_*_image` methods. The CLI adds opt-in `--image {svg,png}` and `--kroki-url` (default env `NEXUS_KROKI_URL` or `https://kroki.io`).

**Tech Stack:** Python 3.14, httpx (async), Typer, Kroki (external render service). Tests use httpx `MockTransport` (house pattern, no mocks) + a `FakeKrokiClient`.

**Conventions (enforced by hooks):** ASCII-only; 4-line file headers; Google docstrings; `__all__`; absolute imports; `from __future__ import annotations`; frozen Pydantic where applicable; no `# type: ignore`; no bare except; no mocks; test names `test_<func>_<scenario>`; 100% line coverage; mypy+pyright strict 0 errors.

---

## Task 1: KrokiClient + KrokiError (api layer)

**Files:**
- Modify: `src/nexus/api/errors.py`
- Create: `src/nexus/api/kroki_client.py`
- Test: `tests/api/test_kroki_client.py`

- [ ] **Step 1: Add KrokiError to api/errors.py**

Append to `src/nexus/api/errors.py` and update `__all__`:

```python
__all__ = ["AnthropicError", "KrokiError"]
```

```python
class KrokiError(Exception):
    """Raised when the Kroki render service returns a non-2xx status.

    Args:
        status_code: HTTP status code from the Kroki response.
        message: Error message from the Kroki response body (truncated).
    """

    def __init__(self, status_code: int, message: str) -> None:
        """Initialize with HTTP status code and error message."""
        self.status_code = status_code
        self.message = message
        super().__init__(f"Kroki render error {status_code}: {message}")
```

- [ ] **Step 2: Write the failing tests**

Create `tests/api/test_kroki_client.py`:

```python
# tests/api/test_kroki_client.py
# Tests for KrokiClient against an httpx MockTransport.
# Author: Pierre Grothe
# Date: 2026-06-08
"""KrokiClient POSTs Mermaid source and returns image bytes."""

import httpx
import pytest

from nexus.api.errors import KrokiError
from nexus.api.kroki_client import KrokiClient

_SVG = b"<svg xmlns='http://www.w3.org/2000/svg'></svg>"


@pytest.mark.asyncio
async def test_render_returns_image_bytes() -> None:
    transport = httpx.MockTransport(lambda req: httpx.Response(200, content=_SVG))
    client = KrokiClient("https://kroki.io", transport=transport)
    assert await client.render("mindmap\n  root((X))", fmt="svg") == _SVG


@pytest.mark.asyncio
async def test_render_posts_source_to_typed_endpoint() -> None:
    seen: dict[str, object] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["url"] = str(req.url)
        seen["method"] = req.method
        seen["body"] = req.content
        return httpx.Response(200, content=_SVG)

    client = KrokiClient("https://kroki.io/", transport=httpx.MockTransport(handler))
    await client.render("erDiagram", fmt="png")
    assert seen["url"] == "https://kroki.io/mermaid/png"
    assert seen["method"] == "POST"
    assert seen["body"] == b"erDiagram"


@pytest.mark.asyncio
async def test_render_non_2xx_raises_kroki_error() -> None:
    transport = httpx.MockTransport(lambda req: httpx.Response(400, text="bad diagram"))
    client = KrokiClient("https://kroki.io", transport=transport)
    with pytest.raises(KrokiError) as exc:
        await client.render("not a diagram", fmt="svg")
    assert exc.value.status_code == 400
    assert "bad diagram" in exc.value.message
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/api/test_kroki_client.py -q`
Expected: FAIL (no module `nexus.api.kroki_client`).

- [ ] **Step 4: Implement KrokiClient**

Create `src/nexus/api/kroki_client.py`:

```python
# src/nexus/api/kroki_client.py
# KrokiClient: async HTTP client that renders diagram source to image bytes.
# Author: Pierre Grothe
# Date: 2026-06-08
"""KrokiClient: POST Mermaid source to a Kroki service, return image bytes."""

from __future__ import annotations

import logging
from typing import Protocol

import httpx

from nexus.api.errors import KrokiError

log = logging.getLogger(__name__)

__all__ = ["KrokiClient", "KrokiClientProtocol"]

_TIMEOUT_SECONDS = 30.0
_ERR_BODY_CHARS = 500


class KrokiClientProtocol(Protocol):
    """Renders diagram source text to image bytes via a Kroki service."""

    async def render(self, source: str, *, fmt: str, diagram_type: str = "mermaid") -> bytes:
        """Render diagram source to image bytes.

        Args:
            source: Diagram source text (e.g. a Mermaid block body).
            fmt: Output format, e.g. "svg" or "png".
            diagram_type: Kroki diagram type. Defaults to "mermaid".

        Returns:
            The rendered image bytes.

        Raises:
            KrokiError: When the service returns a non-2xx status.
        """
        ...


class KrokiClient:
    """Async Kroki client. Opens a short-lived httpx client per render call.

    Args:
        base_url: Kroki endpoint root, e.g. "https://kroki.io".
        transport: Optional httpx transport (test seam; house pattern).
    """

    def __init__(
        self, base_url: str = "https://kroki.io", *, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        """Initialize with a base URL and an optional transport."""
        self._base_url = base_url.rstrip("/")
        self._transport = transport

    async def render(self, source: str, *, fmt: str, diagram_type: str = "mermaid") -> bytes:
        """Render diagram source to image bytes via POST.

        Args:
            source: Diagram source text.
            fmt: Output format ("svg" or "png").
            diagram_type: Kroki diagram type. Defaults to "mermaid".

        Returns:
            The rendered image bytes.

        Raises:
            KrokiError: When the service returns a non-2xx status.
        """
        url = f"{self._base_url}/{diagram_type}/{fmt}"
        log.debug("Kroki render %s (%d chars)", url, len(source))
        async with httpx.AsyncClient(
            timeout=_TIMEOUT_SECONDS, transport=self._transport
        ) as client:
            response = await client.post(
                url, content=source.encode("utf-8"), headers={"Content-Type": "text/plain"}
            )
        if response.status_code != 200:
            raise KrokiError(response.status_code, response.text[:_ERR_BODY_CHARS])
        return response.content
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/api/test_kroki_client.py -q`
Expected: PASS (3 passed).

- [ ] **Step 6: Commit**

```bash
git add src/nexus/api/errors.py src/nexus/api/kroki_client.py tests/api/test_kroki_client.py
git commit -m "feat(schema): add KrokiClient for diagram image rendering"
```

---

## Task 2: FakeKrokiClient

**Files:**
- Create: `tests/fakes/fake_kroki_client.py`
- Test: covered indirectly by Task 4/5; add a direct smoke test in `tests/fakes/test_fake_kroki_client.py`

- [ ] **Step 1: Write the failing test**

Create `tests/fakes/test_fake_kroki_client.py`:

```python
# tests/fakes/test_fake_kroki_client.py
# Smoke test for FakeKrokiClient.
# Author: Pierre Grothe
# Date: 2026-06-08
"""FakeKrokiClient records calls and returns canned bytes."""

import pytest

from tests.fakes.fake_kroki_client import FakeKrokiClient


@pytest.mark.asyncio
async def test_render_records_call_and_returns_canned_bytes() -> None:
    fake = FakeKrokiClient(canned=b"<svg/>")
    out = await fake.render("erDiagram", fmt="svg")
    assert out == b"<svg/>"
    assert fake.calls == [{"source": "erDiagram", "fmt": "svg", "diagram_type": "mermaid"}]


@pytest.mark.asyncio
async def test_render_raises_side_effect() -> None:
    fake = FakeKrokiClient(side_effect=RuntimeError("boom"))
    with pytest.raises(RuntimeError):
        await fake.render("x", fmt="png")
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/fakes/test_fake_kroki_client.py -q`
Expected: FAIL (no module).

- [ ] **Step 3: Implement FakeKrokiClient**

Create `tests/fakes/fake_kroki_client.py`:

```python
# tests/fakes/fake_kroki_client.py
# Test double for KrokiClientProtocol -- no HTTP.
# Author: Pierre Grothe
# Date: 2026-06-08
"""FakeKrokiClient: implements KrokiClientProtocol for unit tests."""

from dataclasses import dataclass, field


def _make_calls() -> list[dict[str, object]]:
    return []


__all__ = ["FakeKrokiClient"]


@dataclass(slots=True)
class FakeKrokiClient:
    """Test double for KrokiClientProtocol.

    Records every call and returns canned bytes. No HTTP.

    Attributes:
        calls: List of dicts capturing every render() invocation.
        canned: Bytes returned by render() on success.
        side_effect: Optional exception to raise instead of returning.
    """

    calls: list[dict[str, object]] = field(default_factory=_make_calls)
    canned: bytes = b"<svg/>"
    side_effect: BaseException | None = None

    async def render(self, source: str, *, fmt: str, diagram_type: str = "mermaid") -> bytes:
        """Record the call and return canned bytes (or raise side_effect).

        Args:
            source: Diagram source text.
            fmt: Output format.
            diagram_type: Kroki diagram type.

        Returns:
            The canned bytes.

        Raises:
            BaseException: If side_effect is set.
        """
        self.calls.append({"source": source, "fmt": fmt, "diagram_type": diagram_type})
        if self.side_effect is not None:
            raise self.side_effect
        return self.canned
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/fakes/test_fake_kroki_client.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add tests/fakes/fake_kroki_client.py tests/fakes/test_fake_kroki_client.py
git commit -m "test(schema): add FakeKrokiClient test double"
```

---

## Task 3: Emitter `diagram()` extraction

**Files:**
- Modify: `src/nexus/schema/erd.py`
- Modify: `src/nexus/schema/mindmap_emitter.py`
- Test: `tests/schema/test_schema_erd.py` (add), `tests/schema/test_mindmap_emitter.py` (add)

- [ ] **Step 1: Write failing tests**

Add to `tests/schema/test_schema_erd.py` (reuse that file's existing `_graph()` helper; if it builds a graph with at least one reference edge, assert on it -- otherwise construct one inline):

```python
def test_diagram_returns_bare_mermaid_source() -> None:
    emitter = MermaidErdEmitter()
    graph = SchemaGraph(
        instance_id="i",
        area_key="a",
        discovered_at=datetime(2026, 6, 8, tzinfo=UTC),
        scope_keys=("s",),
        tables=(TableDef(name="t", label="T", scope="s"),),
        reference_edges=(
            ReferenceEdge(from_table="a", field="f", to_table="b", cross_scope=False),
        ),
        inheritance_edges=(),
        relationship_edges=(),
    )
    diagram = emitter.diagram(graph)
    assert diagram.startswith("erDiagram")
    assert 'a }o--|| b : "f"' in diagram
    assert "```" not in diagram
    assert "# Schema ERD" not in diagram
```

Add the matching imports (`ReferenceEdge`, `datetime`, `UTC`, `TableDef`, `SchemaGraph`) if not already present in that test file.

Add to `tests/schema/test_mindmap_emitter.py` (create if absent, header included):

```python
def test_diagram_returns_bare_mindmap_source() -> None:
    catalog = MindmapCatalog(
        instance_id="i",
        area_key="a",
        generated_at=datetime(2026, 6, 8, tzinfo=UTC),
        display="Doc",
        domains=(
            Domain(name="Core", tables=(
                TableDescription(table="t", label="T", description="d", source="ai"),
            )),
        ),
    )
    diagram = MindmapEmitter().diagram(catalog)
    assert diagram.startswith("mindmap")
    assert "root((Doc))" in diagram
    assert "      T -- t" in diagram
    assert "```" not in diagram
```

- [ ] **Step 2: Run to verify they fail**

Run: `pytest tests/schema/test_schema_erd.py tests/schema/test_mindmap_emitter.py -q`
Expected: FAIL (no `diagram` attribute).

- [ ] **Step 3: Extract `diagram()` in erd.py**

In `src/nexus/schema/erd.py`, add a `diagram()` method and have `render()` reuse it. Replace the `render()` body's Mermaid-block construction:

```python
    def diagram(self, graph: SchemaGraph) -> str:
        """Render only the Mermaid ``erDiagram`` source (no Markdown wrapper).

        Args:
            graph: The graph to render.

        Returns:
            The Mermaid diagram source, suitable for a render service.
        """
        lines: list[str] = ["erDiagram"]
        for edge in graph.reference_edges:
            lines.append(f'    {edge.from_table} }}o--|| {edge.to_table} : "{edge.field}"')
        for inh in graph.inheritance_edges:
            lines.append(f'    {inh.extends} ||--|| {inh.table} : "extends"')
        return "\n".join(lines)
```

Then in `render()`, replace the lines that build `"```mermaid"`, `"erDiagram"`, the edge loops, and the closing fence with:

```python
        lines: list[str] = [
            f"# Schema ERD: {graph.area_key}",
            "",
            f"Instance: `{graph.instance_id}`  |  scopes: {', '.join(graph.scope_keys)}",
            f"Discovered: {graph.discovered_at.isoformat()}",
            "",
            "```mermaid",
            self.diagram(graph),
            "```",
            "",
        ]
```

Leave the "## Cross-scope bridges" and "## Fields" sections unchanged. The rendered output is byte-identical.

- [ ] **Step 4: Extract `diagram()` in mindmap_emitter.py**

In `src/nexus/schema/mindmap_emitter.py`, add:

```python
    def diagram(self, catalog: MindmapCatalog) -> str:
        """Render only the Mermaid ``mindmap`` source (no Markdown wrapper).

        Args:
            catalog: The catalog to render.

        Returns:
            The Mermaid mindmap source, suitable for a render service.
        """
        lines: list[str] = ["mindmap", f"  root(({catalog.display}))"]
        for domain in catalog.domains:
            lines.append(f"    {domain.name}")
            for table in domain.tables:
                lines.append(f"      {table.label} -- {table.table}")
        return "\n".join(lines)
```

Then in `render()`, replace the lines building `"```mermaid"`, `"mindmap"`, `root((...))`, and the domain loop + closing fence with:

```python
        lines: list[str] = [
            f"# Schema mindmap: {catalog.area_key}",
            "",
            f"Instance: `{catalog.instance_id}`  |  generated: {catalog.generated_at.isoformat()}",
            "",
            "```mermaid",
            self.diagram(catalog),
            "```",
            "",
        ]
```

Leave the per-domain catalog list (the `## {domain.name}` sections) unchanged.

- [ ] **Step 5: Run all schema emitter tests**

Run: `pytest tests/schema/test_schema_erd.py tests/schema/test_mindmap_emitter.py -q`
Expected: PASS (existing render() tests still pass; new diagram() tests pass).

- [ ] **Step 6: Commit**

```bash
git add src/nexus/schema/erd.py src/nexus/schema/mindmap_emitter.py tests/schema/test_schema_erd.py tests/schema/test_mindmap_emitter.py
git commit -m "refactor(schema): expose bare Mermaid source via emitter.diagram()"
```

---

## Task 4: Cartographer image methods

**Files:**
- Modify: `src/nexus/schema/engine.py`
- Test: `tests/schema/test_schema_engine.py` (add; create if absent)

- [ ] **Step 1: Write failing tests**

Add to `tests/schema/test_schema_engine.py`. Build a `SchemaCartographer` with fakes (`FakeServiceNowClient`, `FakeAgentClient`, `FakeKrokiClient`):

```python
@pytest.mark.asyncio
async def test_render_erd_image_calls_kroki_with_diagram_source(tmp_path: Path) -> None:
    kroki = FakeKrokiClient(canned=b"<svg/>")
    carto = SchemaCartographer(
        client=FakeServiceNowClient(),
        archive_root=tmp_path,
        agent_client=FakeAgentClient(),
        kroki=kroki,
    )
    graph = _graph()  # a SchemaGraph with at least one reference edge
    out = await carto.render_erd_image(graph, fmt="svg")
    assert out == b"<svg/>"
    assert kroki.calls[0]["fmt"] == "svg"
    assert str(kroki.calls[0]["source"]).startswith("erDiagram")


@pytest.mark.asyncio
async def test_render_mindmap_image_calls_kroki_with_diagram_source(tmp_path: Path) -> None:
    kroki = FakeKrokiClient(canned=b"PNGDATA")
    carto = SchemaCartographer(
        client=FakeServiceNowClient(),
        archive_root=tmp_path,
        agent_client=FakeAgentClient(),
        kroki=kroki,
    )
    out = await carto.render_mindmap_image(_catalog(), fmt="png")
    assert out == b"PNGDATA"
    assert kroki.calls[0]["fmt"] == "png"
    assert str(kroki.calls[0]["source"]).startswith("mindmap")
```

Provide `_graph()` and `_catalog()` helpers in the test module (copy the shapes from `tests/cli/test_commands_schema.py`).

- [ ] **Step 2: Run to verify they fail**

Run: `pytest tests/schema/test_schema_engine.py -q`
Expected: FAIL (`SchemaCartographer.__init__` has no `kroki`; no `render_erd_image`).

- [ ] **Step 3: Implement**

In `src/nexus/schema/engine.py`:
- Add import: `from nexus.api.kroki_client import KrokiClientProtocol`
- Add a required keyword param `kroki: KrokiClientProtocol` to `__init__` and store `self._kroki = kroki`.
- Add two methods:

```python
    async def render_erd_image(self, graph: SchemaGraph, *, fmt: str) -> bytes:
        """Render a graph's ERD to image bytes via the Kroki service.

        Args:
            graph: The graph to render.
            fmt: Output format ("svg" or "png").

        Returns:
            The rendered image bytes.
        """
        return await self._kroki.render(self._emitter.diagram(graph), fmt=fmt)

    async def render_mindmap_image(self, catalog: MindmapCatalog, *, fmt: str) -> bytes:
        """Render a catalog's mindmap to image bytes via the Kroki service.

        Args:
            catalog: The catalog to render.
            fmt: Output format ("svg" or "png").

        Returns:
            The rendered image bytes.
        """
        return await self._kroki.render(self._mindmap_emitter.diagram(catalog), fmt=fmt)
```

Update the class docstring Args to document `kroki`.

- [ ] **Step 4: Run to verify they pass**

Run: `pytest tests/schema/test_schema_engine.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/nexus/schema/engine.py tests/schema/test_schema_engine.py
git commit -m "feat(schema): add cartographer render_erd_image / render_mindmap_image"
```

---

## Task 5: CLI `--image` / `--kroki-url` + wiring

**Files:**
- Modify: `src/nexus/cli/commands_schema.py`
- Modify: `src/nexus/cli/views.py`
- Modify: `tests/schema/fakes/fake_schema_cartographer.py`
- Test: `tests/cli/test_commands_schema.py` (add)

- [ ] **Step 1: Add image methods to FakeSchemaCartographer**

In `tests/schema/fakes/fake_schema_cartographer.py`, add (and update the constructor to accept canned image bytes, default `b"<svg/>"`):

```python
    async def render_erd_image(self, graph: SchemaGraph, *, fmt: str) -> bytes:
        """Return canned image bytes (ignores inputs).

        Args:
            graph: Ignored.
            fmt: Ignored.

        Returns:
            The canned image bytes.
        """
        del graph, fmt
        return self._image

    async def render_mindmap_image(self, catalog: MindmapCatalog, *, fmt: str) -> bytes:
        """Return canned image bytes (ignores inputs).

        Args:
            catalog: Ignored.
            fmt: Ignored.

        Returns:
            The canned image bytes.
        """
        del catalog, fmt
        return self._image
```

Add `image: bytes = b"<svg/>"` to `__init__` and store `self._image = image`.

- [ ] **Step 2: Write failing CLI tests**

Add to `tests/cli/test_commands_schema.py`:

```python
def test_schema_erd_writes_image_when_requested(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeSchemaCartographer(_graph(), image=b"<svg/>")
    monkeypatch.setattr(
        commands_schema, "_build_schema_cartographer", lambda _profile, _url: (fake, fake)
    )
    out = tmp_path / "erd.md"
    result = CliRunner().invoke(
        app,
        ["schema", "erd", "doc-designer", "--profile", "alectri", "-o", str(out), "--image", "svg"],
    )
    assert result.exit_code == 0, result.stdout
    assert (tmp_path / "erd.svg").read_bytes() == b"<svg/>"


def test_schema_mindmap_writes_image_when_requested(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    catalog = _catalog()  # the catalog shape already in this file
    fake = FakeSchemaCartographer(_graph(), catalog=catalog, image=b"PNG")
    monkeypatch.setattr(
        commands_schema, "_build_schema_cartographer", lambda _profile, _url: (fake, fake)
    )
    out = tmp_path / "mm.md"
    result = CliRunner().invoke(
        app,
        ["schema", "mindmap", "doc-designer", "--profile", "alectri", "-o", str(out), "--image", "png"],
    )
    assert result.exit_code == 0, result.stdout
    assert (tmp_path / "mm.png").read_bytes() == b"PNG"
```

NOTE: the existing two tests monkeypatch `_build_schema_cartographer` with `lambda _profile: ...`. Since Step 4 changes its signature to `(profile, kroki_url)`, update those two existing lambdas to `lambda _profile, _url: (fake, fake)`.

- [ ] **Step 3: Run to verify new tests fail**

Run: `pytest tests/cli/test_commands_schema.py -q`
Expected: FAIL (no `--image`; signature mismatch).

- [ ] **Step 4: Implement CLI + wiring**

In `src/nexus/cli/views.py`, update `_build_schema_cartographer`:
- Add import: `from nexus.api.kroki_client import KrokiClient`
- Signature: `def _build_schema_cartographer(profile: str, kroki_url: str = "https://kroki.io") -> tuple[SchemaCartographer, ServiceNowClient]:`
- Pass `kroki=KrokiClient(kroki_url)` into `SchemaCartographer(...)`.

In `src/nexus/cli/commands_schema.py`:
- Add an `ImageFormat` enum and imports:

```python
from enum import Enum


class ImageFormat(str, Enum):
    """Supported diagram image formats."""

    svg = "svg"
    png = "png"
```

- Add two options to BOTH `schema_erd` and `schema_mindmap`:

```python
    image: Annotated[
        ImageFormat | None,
        typer.Option("--image", help="Also render a shareable image (svg or png) via Kroki"),
    ] = None,
    kroki_url: Annotated[
        str, typer.Option("--kroki-url", envvar="NEXUS_KROKI_URL", help="Kroki render endpoint")
    ] = "https://kroki.io",
```

- In `schema_erd._run`, pass `kroki_url` to the builder and, after writing the markdown, write the image when requested:

```python
        cartographer, client = _build_schema_cartographer(profile, kroki_url)
        ...
        dest.write_text(markdown, encoding="utf-8")
        if image is not None:
            data = await cartographer.render_erd_image(graph, fmt=image.value)
            dest.with_suffix(f".{image.value}").write_bytes(data)
        return dest
```

- In `schema_mindmap._run`, mirror it with `render_mindmap_image(catalog, fmt=image.value)` and `dest.with_suffix(...)`. (The mindmap default `dest` is `f"{area}-{resolved}-mindmap.md"`; `with_suffix` yields `...-mindmap.svg`, which is correct.)
- After writing, when an image was written, print a second line: `console.print(f"Wrote image to {dest.with_suffix(f'.{image.value}')}")`.

- [ ] **Step 5: Run to verify all CLI tests pass**

Run: `pytest tests/cli/test_commands_schema.py -q`
Expected: PASS (4 passed).

- [ ] **Step 6: Commit**

```bash
git add src/nexus/cli/commands_schema.py src/nexus/cli/views.py tests/schema/fakes/fake_schema_cartographer.py tests/cli/test_commands_schema.py
git commit -m "feat(schema): nexus schema erd|mindmap --image svg|png via Kroki"
```

---

## Final verification (after all tasks)

- [ ] Run the full suite: `pytest -n auto -q` -> all pass.
- [ ] `ruff check src tests` and `black --check src tests` -> clean.
- [ ] `mypy src/nexus/` and `pyright src/nexus/` -> 0 errors.
- [ ] Live smoke (manual, network): `nexus schema erd doc-designer --profile alectri --image svg` against a registered instance -> writes `doc-designer-alectri.md` + `doc-designer-alectri.svg`; open the SVG in a browser to confirm it renders.
