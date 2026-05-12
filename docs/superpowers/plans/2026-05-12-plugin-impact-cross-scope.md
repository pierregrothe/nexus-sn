# Plugin Impact Cross-Scope FK Scan Implementation Plan

> REQUIRED SUB-SKILL: superpowers:subagent-driven-development.

**Spec:** [2026-05-12-plugin-impact-cross-scope-design.md](../specs/2026-05-12-plugin-impact-cross-scope-design.md)

---

## File Structure

| File | Responsibility | Task |
|------|----------------|------|
| `src/nexus/plugins/models.py` | Add `CrossScopeRef`; extend `PluginImpact`. | 1 |
| `src/nexus/plugins/impact.py` | Add `fetch_cross_scope_refs`; update `compute_impact`. | 2 |
| `src/nexus/cli.py` | `--no-cross-scope` flag; render third table; summary suffix. | 3 |
| `tests/test_plugins_models.py` | CrossScopeRef tests. | 1 |
| `tests/test_plugins_impact.py` | fetch_cross_scope_refs tests + compute_impact cross-scope kwarg. | 2 |
| `tests/test_cli_plugins_impact.py` | --no-cross-scope flag, output renders. | 3 |
| `.ratchet.json` | Per-module coverage bump. | 4 |

---

## Task 1: CrossScopeRef model + PluginImpact extension

**Files:** `src/nexus/plugins/models.py`, `tests/test_plugins_models.py`.

- [ ] **Step 1: Tests** -- append to `tests/test_plugins_models.py`:

```python
def test_cross_scope_ref_rejects_negative_count() -> None:
    from nexus.plugins.models import CrossScopeRef

    with pytest.raises(ValidationError):
        CrossScopeRef(
            source_scope="com.x",
            source_table="incident",
            field="cmdb_ci",
            target_table="cmdb_ci",
            record_count=-1,
        )


def test_cross_scope_ref_accepts_zero_count() -> None:
    from nexus.plugins.models import CrossScopeRef

    ref = CrossScopeRef(
        source_scope="com.x",
        source_table="incident",
        field="cmdb_ci",
        target_table="cmdb_ci",
        record_count=0,
    )
    assert ref.record_count == 0


def test_cross_scope_ref_is_frozen() -> None:
    from nexus.plugins.models import CrossScopeRef

    ref = CrossScopeRef(
        source_scope="com.x",
        source_table="incident",
        field="cmdb_ci",
        target_table="cmdb_ci",
        record_count=5,
    )
    with pytest.raises(ValidationError):
        ref.record_count = 10


def test_plugin_impact_defaults_cross_scope_refs_to_empty_tuple() -> None:
    from nexus.plugins.models import PluginImpact

    impact = PluginImpact(
        target_plugin_id="com.x",
        target_name="X",
        reverse_deps=(),
        record_counts=(),
        counts_available=True,
    )
    assert impact.cross_scope_refs == ()
    assert impact.cross_scope_available is True
```

Move the inline imports to the top-of-file import block per project convention. Add `CrossScopeRef` to that import.

- [ ] **Step 2: Run tests** -- expect failures.

- [ ] **Step 3: Add model** to `src/nexus/plugins/models.py`. Insert `CrossScopeRef` class after `ScopeRecordCount`:

```python
class CrossScopeRef(BaseModel):
    """One table-field pair from another scope that references into the target scope.

    Attributes:
        source_scope: plugin_id of the scope owning ``source_table``.
        source_table: SN table holding the reference field.
        field: Reference column name (sys_dictionary.element).
        target_table: Target table being pointed to.
        record_count: Number of records in ``source_table`` with a
            non-null value in ``field``. Always >= 0.
    """

    model_config = _FROZEN

    source_scope: str
    source_table: str
    field: str
    target_table: str
    record_count: Annotated[int, Field(ge=0)]
```

Add `"CrossScopeRef"` to `__all__`.

Extend `PluginImpact`:

```python
class PluginImpact(BaseModel):
    ...
    target_plugin_id: str
    target_name: str
    reverse_deps: tuple[ReverseDependency, ...]
    record_counts: tuple[ScopeRecordCount, ...]
    counts_available: bool
    cross_scope_refs: tuple[CrossScopeRef, ...] = ()
    cross_scope_available: bool = True
```

Update the class docstring `Attributes:` to document both new fields.

- [ ] **Step 4: Run tests + full suite. Commit.**

```bash
git commit -m "feat(plugins): add CrossScopeRef model + extend PluginImpact"
```

---

## Task 2: fetch_cross_scope_refs + compute_impact integration

**Files:** `src/nexus/plugins/impact.py`, `tests/test_plugins_impact.py`.

- [ ] **Step 1: Tests** -- add to `tests/test_plugins_impact.py`:

```python
def _sys_db_object_response(tables: list[str]) -> dict[str, object]:
    return {"result": [{"name": t} for t in tables]}


def _sys_dictionary_response(
    rows: list[tuple[str, str, str]]
) -> dict[str, object]:
    """Each row: (source_table, field, source_scope)."""
    return {
        "result": [
            {
                "name": src,
                "element": field,
                "sys_scope.scope": scope,
            }
            for src, field, scope in rows
        ]
    }


def _stats_count_response(count: int) -> dict[str, object]:
    return {"result": {"stats": {"count": str(count)}}}


def test_fetch_cross_scope_refs_returns_empty_when_no_target_tables() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        if "sys_db_object" in req.url.path:
            return httpx.Response(200, json=_sys_db_object_response([]))
        return httpx.Response(404, json={"result": []})

    transport = httpx.MockTransport(handler)
    result = asyncio.run(
        fetch_cross_scope_refs(
            "https://x.example", "t", "com.x", transport=transport
        )
    )
    assert result == ()


def test_fetch_cross_scope_refs_returns_empty_when_no_inbound_refs() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        if "sys_db_object" in req.url.path:
            return httpx.Response(200, json=_sys_db_object_response(["cmdb_ci"]))
        if "sys_dictionary" in req.url.path:
            return httpx.Response(200, json=_sys_dictionary_response([]))
        return httpx.Response(404, json={"result": []})

    transport = httpx.MockTransport(handler)
    result = asyncio.run(
        fetch_cross_scope_refs(
            "https://x.example", "t", "com.x", transport=transport
        )
    )
    assert result == ()


def test_fetch_cross_scope_refs_returns_single_match() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        if "sys_db_object" in req.url.path:
            return httpx.Response(200, json=_sys_db_object_response(["cmdb_ci"]))
        if "sys_dictionary" in req.url.path:
            return httpx.Response(
                200,
                json=_sys_dictionary_response([("incident", "cmdb_ci", "com.snc.incident")]),
            )
        if "/api/now/stats/" in req.url.path:
            return httpx.Response(200, json=_stats_count_response(42))
        return httpx.Response(404, json={"result": []})

    transport = httpx.MockTransport(handler)
    result = asyncio.run(
        fetch_cross_scope_refs(
            "https://x.example", "t", "com.x", transport=transport
        )
    )
    assert len(result) == 1
    assert result[0].source_table == "incident"
    assert result[0].field == "cmdb_ci"
    assert result[0].source_scope == "com.snc.incident"
    assert result[0].target_table == "cmdb_ci"
    assert result[0].record_count == 42


def test_fetch_cross_scope_refs_sorts_by_count_desc() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        if "sys_db_object" in req.url.path:
            return httpx.Response(200, json=_sys_db_object_response(["t1"]))
        if "sys_dictionary" in req.url.path:
            return httpx.Response(
                200,
                json=_sys_dictionary_response(
                    [
                        ("low_count_table", "f", "com.a"),
                        ("high_count_table", "f", "com.b"),
                    ]
                ),
            )
        if "low_count_table" in req.url.path:
            return httpx.Response(200, json=_stats_count_response(5))
        if "high_count_table" in req.url.path:
            return httpx.Response(200, json=_stats_count_response(500))
        return httpx.Response(404, json={"result": []})

    transport = httpx.MockTransport(handler)
    result = asyncio.run(
        fetch_cross_scope_refs(
            "https://x.example", "t", "com.x", transport=transport
        )
    )
    assert [r.record_count for r in result] == [500, 5]


def test_fetch_cross_scope_refs_raises_on_phase1_failure() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        if "sys_db_object" in req.url.path:
            return httpx.Response(500, json={})
        return httpx.Response(200, json={"result": []})

    transport = httpx.MockTransport(handler)
    with pytest.raises(ScopeRecordCountError):
        asyncio.run(
            fetch_cross_scope_refs(
                "https://x.example", "t", "com.x", transport=transport
            )
        )


def test_compute_impact_includes_cross_scope_when_enabled() -> None:
    # Build a transport that handles all impact-time SN endpoints.
    def handler(req: httpx.Request) -> httpx.Response:
        if "sys_db_object" in req.url.path:
            return httpx.Response(200, json=_sys_db_object_response(["target_table"]))
        if "sys_dictionary" in req.url.path:
            return httpx.Response(
                200,
                json=_sys_dictionary_response([("other_table", "ref", "com.other")]),
            )
        if "/api/now/stats/sys_metadata" in req.url.path:
            return httpx.Response(200, json={"result": []})  # scope record buckets
        if "/api/now/stats/other_table" in req.url.path:
            return httpx.Response(200, json=_stats_count_response(7))
        return httpx.Response(404, json={"result": []})

    transport = httpx.MockTransport(handler)
    inv = _inventory(_plugin("com.target"))
    result = asyncio.run(
        compute_impact(
            inv,
            "com.target",
            url="https://x.example",
            token="t",
            transport=transport,
        )
    )
    assert result.cross_scope_available is True
    assert len(result.cross_scope_refs) == 1
    assert result.cross_scope_refs[0].source_table == "other_table"


def test_compute_impact_skips_cross_scope_when_disabled() -> None:
    call_count = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        if "/api/now/stats/sys_metadata" in req.url.path:
            return httpx.Response(200, json={"result": []})
        return httpx.Response(200, json={"result": []})

    transport = httpx.MockTransport(handler)
    inv = _inventory(_plugin("com.target"))
    result = asyncio.run(
        compute_impact(
            inv,
            "com.target",
            url="https://x.example",
            token="t",
            transport=transport,
            cross_scope=False,
        )
    )
    assert result.cross_scope_available is False
    assert result.cross_scope_refs == ()


def test_compute_impact_marks_cross_scope_unavailable_on_failure() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        if "sys_db_object" in req.url.path:
            return httpx.Response(500, json={})
        if "/api/now/stats/sys_metadata" in req.url.path:
            return httpx.Response(200, json={"result": []})
        return httpx.Response(404, json={"result": []})

    transport = httpx.MockTransport(handler)
    target_info = _plugin("com.target").model_copy(update={"record_counts": ()})
    inv = _inventory(target_info)
    result = asyncio.run(
        compute_impact(
            inv,
            "com.target",
            url="https://x.example",
            token="t",
            transport=transport,
        )
    )
    assert result.cross_scope_available is False
    assert result.cross_scope_refs == ()
```

Add `fetch_cross_scope_refs` and `CrossScopeRef` to the test imports.

- [ ] **Step 2: Implement `fetch_cross_scope_refs`** in `src/nexus/plugins/impact.py`. Add the function below `fetch_scope_record_counts`:

```python
_CROSS_SCOPE_CONCURRENCY = 16


async def fetch_cross_scope_refs(
    url: str,
    token: str,
    plugin_id: str,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> tuple[CrossScopeRef, ...]:
    """Find tables in other scopes that reference into ``plugin_id``'s scope.

    Args:
        url: Instance base URL.
        token: OAuth bearer token.
        plugin_id: Target plugin/scope identifier.
        transport: Optional httpx transport for tests.

    Returns:
        Tuple of CrossScopeRef sorted by ``(record_count desc,
        source_scope asc, source_table asc, field asc)``.

    Raises:
        ScopeRecordCountError: When any of the three REST phases fails.
    """
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    try:
        async with httpx.AsyncClient(
            base_url=url, headers=headers, timeout=30.0, transport=transport
        ) as client:
            target_tables = await _phase1_target_tables(client, plugin_id)
            inbound = await _phase2_inbound_refs(client, target_tables)
            counts = await _phase3_count_records(client, inbound)
    except httpx.RequestError as exc:
        raise ScopeRecordCountError(f"network error: {exc}") from exc

    refs = [
        CrossScopeRef(
            source_scope=src_scope,
            source_table=src_table,
            field=field,
            target_table=target_table,
            record_count=record_count,
        )
        for (src_scope, src_table, field, target_table), record_count in counts.items()
    ]
    refs.sort(key=lambda r: (-r.record_count, r.source_scope, r.source_table, r.field))
    return tuple(refs)


async def _phase1_target_tables(client: httpx.AsyncClient, plugin_id: str) -> list[str]:
    """Phase 1: list tables in the target plugin's scope."""
    response = await client.get(
        "/api/now/table/sys_db_object",
        params={
            "sysparm_query": f"sys_scope.scope={plugin_id}",
            "sysparm_fields": "name",
            "sysparm_limit": 200,
        },
    )
    if response.status_code != 200:
        raise ScopeRecordCountError(
            f"sys_db_object query returned HTTP {response.status_code}"
        )
    try:
        rows = response.json()["result"]
    except (KeyError, ValueError) as exc:
        raise ScopeRecordCountError(f"malformed sys_db_object response: {exc}") from exc
    return [str(r["name"]) for r in rows if r.get("name")]


async def _phase2_inbound_refs(
    client: httpx.AsyncClient, target_tables: list[str]
) -> list[tuple[str, str, str, str]]:
    """Phase 2: for each target table, find sys_dictionary rows with internal_type=reference.

    Returns:
        List of (source_scope, source_table, field, target_table) tuples.
    """
    semaphore = asyncio.Semaphore(_CROSS_SCOPE_CONCURRENCY)

    async def _one(target_table: str) -> list[tuple[str, str, str, str]]:
        async with semaphore:
            response = await client.get(
                "/api/now/table/sys_dictionary",
                params={
                    "sysparm_query": f"internal_type=reference^reference={target_table}",
                    "sysparm_fields": "name,element,sys_scope.scope",
                    "sysparm_limit": 200,
                },
            )
            if response.status_code != 200:
                raise ScopeRecordCountError(
                    f"sys_dictionary query for {target_table} returned HTTP "
                    f"{response.status_code}"
                )
            try:
                rows = response.json()["result"]
            except (KeyError, ValueError) as exc:
                raise ScopeRecordCountError(
                    f"malformed sys_dictionary response: {exc}"
                ) from exc
        out: list[tuple[str, str, str, str]] = []
        for r in rows:
            scope_val = r.get("sys_scope.scope", "")
            scope = scope_val if isinstance(scope_val, str) else scope_val.get("value", "")
            out.append((str(scope), str(r["name"]), str(r["element"]), target_table))
        return out

    nested = await asyncio.gather(*(_one(t) for t in target_tables))
    return [item for sub in nested for item in sub]


async def _phase3_count_records(
    client: httpx.AsyncClient, inbound: list[tuple[str, str, str, str]]
) -> dict[tuple[str, str, str, str], int]:
    """Phase 3: for each (src_scope, src_table, field, target_table) tuple,
    count non-null records.

    Returns:
        Mapping from the tuple to record_count.
    """
    semaphore = asyncio.Semaphore(_CROSS_SCOPE_CONCURRENCY)

    async def _one(
        ref: tuple[str, str, str, str]
    ) -> tuple[tuple[str, str, str, str], int]:
        _, source_table, field, _ = ref
        async with semaphore:
            response = await client.get(
                f"/api/now/stats/{source_table}",
                params={
                    "sysparm_query": f"{field}ISNOTEMPTY",
                    "sysparm_count": "true",
                },
            )
            if response.status_code != 200:
                raise ScopeRecordCountError(
                    f"stats/{source_table} returned HTTP {response.status_code}"
                )
            try:
                count = int(response.json()["result"]["stats"]["count"])
            except (KeyError, ValueError, TypeError) as exc:
                raise ScopeRecordCountError(
                    f"malformed stats response for {source_table}: {exc}"
                ) from exc
        return ref, count

    pairs = await asyncio.gather(*(_one(r) for r in inbound))
    return dict(pairs)
```

Add `CrossScopeRef` to the model import at the top of impact.py.

- [ ] **Step 3: Update `compute_impact`** to call `fetch_cross_scope_refs` and populate the new fields. Add the `cross_scope: bool = True` kwarg. After the existing record-count branch:

```python
    cross_scope_refs: tuple[CrossScopeRef, ...] = ()
    cross_scope_available = False
    if cross_scope:
        try:
            cross_scope_refs = await fetch_cross_scope_refs(
                url, token, target, transport=transport
            )
            cross_scope_available = True
        except ScopeRecordCountError as exc:
            log.warning("impact: cross-scope refs unavailable for %s -- %s", target, exc)

    return PluginImpact(
        target_plugin_id=target,
        target_name=target_info.name,
        reverse_deps=deps,
        record_counts=counts,
        counts_available=counts_available,
        cross_scope_refs=cross_scope_refs,
        cross_scope_available=cross_scope_available,
    )
```

The cache-first path also gets the cross-scope hook. Pull the
cross-scope call out so it runs regardless of the `live` cache decision.
One clean shape: compute `cross_scope_refs` first, then build the
PluginImpact in either branch.

- [ ] **Step 4: Update `__all__`** in impact.py to add `fetch_cross_scope_refs`.

- [ ] **Step 5: Run tests + full suite. Commit.**

```bash
git commit -m "feat(plugins): fetch_cross_scope_refs + cross_scope kwarg on compute_impact"
```

---

## Task 3: CLI `--no-cross-scope` flag + third DataTable

**Files:** `src/nexus/cli.py`, `tests/test_cli_plugins_impact.py`.

- [ ] **Step 1: Tests** -- assert: default invocation shows "Cross-scope references" header in output; `--no-cross-scope` invocation omits the header; summary line includes deferred-count when applicable.

- [ ] **Step 2: Add CLI flag.** In `plugins_impact`:

```python
    no_cross_scope: Annotated[
        bool,
        typer.Option(
            "--no-cross-scope",
            help="Skip the cross-scope FK reference scan.",
        ),
    ] = False,
```

  Pass `cross_scope=not no_cross_scope` to `compute_impact`.

- [ ] **Step 3: Render the third table.** Extend `_render_impact`:

```python
    if not impact.cross_scope_available:
        if impact.cross_scope_refs == ():
            # Either opted out, or scan failed -- choose message accordingly.
            # The CLI knows which case via the flag. For simplicity, only warn
            # when the user did NOT opt out.
            pass  # handled by the caller (passes a flag through)
    elif impact.cross_scope_refs:
        ref_rows: list[list[RenderableType]] = [
            [
                r.source_scope,
                r.source_table,
                r.field,
                r.target_table,
                f"{r.record_count:,}",
            ]
            for r in impact.cross_scope_refs
        ]
        console.print(
            DataTable(
                title="Cross-scope references",
                columns=[
                    DataColumn(header="Source scope", width=24),
                    DataColumn(header="Source table", width=24),
                    DataColumn(header="Field", width=16),
                    DataColumn(header="Target table", width=20),
                    DataColumn(header="Records", width=10),
                ],
                rows=ref_rows,
            )
        )
```

Update the summary line to include `; N cross-scope refs` when
`impact.cross_scope_refs` is non-empty.

- [ ] **Step 4: Run tests + commit.**

```bash
git commit -m "feat(cli): --no-cross-scope flag + cross-scope refs table"
```

---

## Task 4: Coverage ratchet + final green run

- [ ] Run focused coverage on `nexus.plugins.models`, `nexus.plugins.impact`, `nexus.cli`.
- [ ] Update `.ratchet.json` with new covered_lines.
- [ ] `pre-commit run --all-files` clean.
- [ ] Commit.

---

## Self-Review

Spec coverage: CrossScopeRef model (T1), three-phase scan (T2), CLI flag + render (T3), ratchet (T4). Type consistency: `CrossScopeRef.record_count: int`, `fetch_cross_scope_refs -> tuple[CrossScopeRef, ...]`, `compute_impact(..., cross_scope: bool = True)`.
