# Story S2-02 — Declare the hot-view slice model and HotViewKey

**Step:** Step 2 — Declare the hot-view data model and the Supervisor/routing sum types
**Status:** Ready
**Effort:** S
**Depends on:** S1-01
**ADRs honored:** ADR-0003, ADR-0004

## Context
The four Redis hot-view slices (`available_skills`, `entrypoint`, `risk_flags`, `confidence_summary`) are the warm-path agent context the planner reads in `< 50 ms p95`. This story lands every frozen Pydantic contract behind that read — the `HotViewSliceName` `Literal`, the `HotViewKey` whose `redis_key()` is the only place a Redis key string is constructed, the `HotViewSlice` envelope stamped for content-addressed integrity, and the four per-slice payload models — *before* the store (S5-01) or renderer (S5-03) exist. It is foundational, contracts-first work: the `gather_id` + `slice_schema_version` stamping declared here is exactly what makes a tampered or stale Redis value structurally a cache miss (ADR-0003).

## References — where to look
- **Architecture:**
  - `../phase-arch-design.md §Data model` — the `[contract] hot-view slices` block: `HotViewSliceName` `Literal`, `HotViewKey`, `HotViewSlice` with `gather_id: BlobDigest` and `slice_schema_version: int`, and the per-slice payload union.
  - `../phase-arch-design.md §C4 — HotViewStore` — the `HotViewKey` / `HotViewSlice` public-interface block; `redis_key()` returns `"hotview:{repo}:{slice}:v{n}"`.
  - `../phase-arch-design.md §Logical view` — `HotViewKey` carries `repo_id`, `slice_name`, `slice_schema_version`; `HotViewSlice` is what `get_all` returns.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0003-hot-view-integrity-by-gather-id-content-addressing.md` — ADR-0003 — every slice is `gather_id`- and `slice_schema_version`-stamped; the `(repo, slice_name, gather_id, slice_schema_version)` binding is the integrity check.
  - `../ADRs/0004-per-slice-hot-view-schema-versioning.md` — ADR-0004 — each slice carries its *own* `slice_schema_version: int`; the version rides in `redis_key()`; one slice's bump must not evict the other three.
- **Production ADRs (if applicable):**
  - `../../../production/adrs/0013-pre-rendered-redis-hot-views.md` — the four-slice catalogue; "versioned, evicted on read."
- **Source design:**
  - `../final-design.md §Departures from all three inputs` — item 3: per-slice versioning (the inputs picked one global `schema_version`).
- **Existing code (if any):**
  - `src/codegenie/types/identifiers.py` — `RepoId` (added by S1-01), `BlobDigest` newtype (the `gather_id` type).
  - `src/codegenie/plugins/subgraph.py:65` — the frozen-model `ConfigDict` convention.
  - `src/codegenie/probes/layer_c/_cve_models.py` — a `Field(discriminator=...)` precedent for the per-slice payload union if discrimination is used; otherwise a plain `|` union keyed by `slice_name` is acceptable since `slice_name` already discriminates.

## Goal
Declare `HotViewSliceName`, `HotViewKey` (with a `redis_key()` returning `hotview:{repo}:{slice}:v{n}`), `HotViewSlice`, and the four per-slice payload models in `codegenie/hotviews/model.py`, so the store and renderer have a typed, integrity-stamped slice contract.

## Acceptance criteria
- [ ] `codegenie/hotviews/model.py` declares `HotViewSliceName = Literal["available_skills", "entrypoint", "risk_flags", "confidence_summary"]`.
- [ ] `HotViewKey` is a frozen model (`repo_id: RepoId`, `slice_name: HotViewSliceName`, `slice_schema_version: int`); `HotViewKey.redis_key()` returns exactly `f"hotview:{repo_id}:{slice_name}:v{slice_schema_version}"`.
- [ ] `HotViewSlice` is a frozen model carrying `slice_name`, `gather_id: BlobDigest`, `slice_schema_version: int`, and a `payload` typed as the union of the four per-slice payload models.
- [ ] The four per-slice payload models (`AvailableSkillsPayload`, `EntrypointPayload`, `RiskFlagsPayload`, `ConfidenceSummaryPayload`) are declared as frozen `extra="forbid"` models.
- [ ] `redis_key()` is unit-tested over all four `HotViewSliceName` values and confirms the `v{n}` segment reflects the per-slice version (ADR-0004).
- [ ] The new public names are listed in `codegenie/hotviews/__init__.py.__all__`; the running ≤ 24 public-surface count is noted in the attempt log.
- [ ] The TDD plan's red test exists, was committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest` all pass on the touched files.

## Implementation outline
1. Create `codegenie/hotviews/` with `__init__.py` and `model.py`.
2. Declare `HotViewSliceName` as a closed four-member `Literal`.
3. Declare the four per-slice payload models. Field shapes are derived from what the renderer aggregates (`available_skills` ← Skills index; `entrypoint` ← build/CI probes; `risk_flags` ← risk probes; `confidence_summary` ← `IndexHealthProbe` verbatim) — keep them minimal frozen models; the renderer (S5-03) populates them. Use simple typed fields; do not over-model — the renderer story owns the exact field set, this story locks the model *exists* and is frozen.
4. Declare `HotViewKey` with the three fields and a pure `redis_key()` method.
5. Declare `HotViewSlice` with `slice_name`, `gather_id`, `slice_schema_version`, and `payload: AvailableSkillsPayload | EntrypointPayload | RiskFlagsPayload | ConfidenceSummaryPayload`.
6. Export the public names via `__init__.py.__all__`.

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file path: `tests/unit/hotviews/test_hot_view_model.py`

```python
@pytest.mark.parametrize("slice_name", ["available_skills", "entrypoint", "risk_flags", "confidence_summary"])
def test_redis_key_format(slice_name: HotViewSliceName) -> None:
    # WHY: redis_key() is the SINGLE place a Redis key string is built — the
    # "hotview:{repo}:{slice}:v{n}" grammar is the content-addressed cache key
    # (ADR-0003/0004); a drift here silently splits warm/cold key spaces.
    key = HotViewKey(repo_id=RepoId("acme/api"), slice_name=slice_name, slice_schema_version=3)
    assert key.redis_key() == f"hotview:acme/api:{slice_name}:v3"

def test_redis_key_reflects_per_slice_version() -> None:
    # WHY: ADR-0004 — each slice versions independently; the version segment
    # must come from THIS slice's slice_schema_version, never a global int.
    k_v1 = HotViewKey(repo_id=RepoId("r"), slice_name="risk_flags", slice_schema_version=1)
    k_v7 = HotViewKey(repo_id=RepoId("r"), slice_name="risk_flags", slice_schema_version=7)
    assert k_v1.redis_key().endswith(":v1") and k_v7.redis_key().endswith(":v7")

def test_hot_view_slice_is_frozen_and_gather_id_stamped() -> None:
    # WHY: the gather_id stamp is the integrity binding (ADR-0003) — a slice
    # whose stamp can be mutated post-construction defeats fail-closed reads.
    s = HotViewSlice(slice_name="entrypoint", gather_id=BlobDigest("a"*64),
                     slice_schema_version=2, payload=EntrypointPayload(...))
    with pytest.raises(ValidationError):
        s.gather_id = BlobDigest("b"*64)
```

### Green — make it pass
Declare the `Literal`, `HotViewKey` with the f-string `redis_key()`, `HotViewSlice`, and the four payload models — all frozen, `extra="forbid"`. Minimal payload field sets; no rendering logic (S5-03), no Redis I/O (S5-01).

### Refactor — clean up
Docstrings naming the ADR-0003/0004 lineage and the `[contract]` status of `HotViewSlice`. Confirm `redis_key()` is pure (no I/O, no `self` mutation). Add a module comment that `slice_schema_versions` is injected, not read at import (ADR-0004 §Consequences) — the store, not this model, owns that mapping.

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/hotviews/__init__.py` | New package; `__all__` exports the public model names. |
| `src/codegenie/hotviews/model.py` | Declares `HotViewSliceName`, `HotViewKey`, `HotViewSlice`, the four payload models. |
| `tests/unit/hotviews/test_hot_view_model.py` | Red tests: `redis_key()` format, per-slice version, frozen slice. |

## Out of scope
- `RenderReport` — S2-05.
- `HotViewStore` and the `ColdStoreReader` Protocol — S3-02 / S5-01.
- `render_hot_views` and the exact payload field population — S5-03 (this story locks the payload models exist and are frozen; the renderer fills them).
- The `slice_schema_versions: Mapping[HotViewSliceName, int]` `Final` default dict — injected into `HotViewStore`, lands with S5-01.

## Notes for the implementer
- `redis_key()` is the *only* place a Redis key is constructed anywhere in the phase (ADR-0003 §Pattern fit — "`HotViewKey` is a typed key, never an f-string at a call site"). Do not let the store build keys inline.
- The version segment is per-slice (ADR-0004). A reviewer must be able to bump *one* slice's version without touching the other three — keep the version on `HotViewKey`/`HotViewSlice`, never a shared module-level scalar.
- Keep the four payload models deliberately thin. The renderer story (S5-03) owns the exact aggregation; if you over-specify fields here, S5-03 will fight the contract. Frozen + `extra="forbid"` + a couple of obvious typed fields is enough.
- `gather_id: BlobDigest` — reuse the existing `BlobDigest` newtype; do not introduce a new digest type.
- `HotViewSlice.payload` does not need a `Field(discriminator=...)` — `slice_name` already discriminates the slice; a plain `|` union is honest here. If `mypy --strict` round-tripping needs a `TypeAdapter`, key it on `slice_name`.
