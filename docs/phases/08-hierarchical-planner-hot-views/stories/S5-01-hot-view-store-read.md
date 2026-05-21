# Story S5-01 — Implement the HotViewStore Redis read path

**Step:** Step 5 — Implement the HotViewStore, renderer, and PlannerNode routing core
**Status:** Ready
**Effort:** M
**Depends on:** S2-02, S3-02
**ADRs honored:** ADR-0003, ADR-0004, ADR-0005, ADR-0006

## Context
This is the warm-path read core for Phase 8's hot-view cache — the component exit criterion 2 (`<50 ms p95`) is measured against. `HotViewStore.get_all` issues one pipelined Redis round-trip of four `GET`s and deserializes each value to a `HotViewSlice`; `get` always returns a `HotViewSlice` (never `None`) so the planner's warm path is branchless. This story builds the happy-path read only — integrity verification and the cold-storage fail-closed fallback land in S5-02, which extends this same class.

## References — where to look
- **Architecture:**
  - `../phase-arch-design.md §C4 — HotViewStore` — the public interface, the one-pipeline-of-four-GETs internal structure, the performance envelope (`get_all` ≈ 1–2 ms warm)
  - `../phase-arch-design.md §Process view` — the hot-view read is the only Redis I/O on the warm path
  - `../phase-arch-design.md §Scenario 1` — happy path: `PIPELINE GET hotview:acme/api:{4 slices}` → 4 values
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0003-hot-view-integrity-by-gather-id-content-addressing.md` — ADR-0003 — `HotViewStore.get` always returns a valid `HotViewSlice`, never `None` (the integrity/fallback half is S5-02)
  - `../ADRs/0004-per-slice-hot-view-schema-versioning.md` — ADR-0004 — `HotViewStore` is injected with a `slice_schema_versions: Mapping[HotViewSliceName, int]`; the version rides `redis_key()`
  - `../ADRs/0005-50ms-p95-exit-criterion-scoped-to-hot-view-read.md` — ADR-0005 — the `<50 ms p95` SLO is scoped to exactly `get_all` + deserialization
  - `../ADRs/0006-cold-storage-fallback-reads-the-rendered-repocontext.md` — ADR-0006 — the `ColdStoreReader` Protocol (from S3-02) is a constructor dependency
- **Source design:**
  - `../final-design.md §Synthesis ledger row "Redis trust posture"` — content-addressed integrity over HMAC/KMS
- **Existing code (if any):**
  - `src/codegenie/hotviews/model.py` — `HotViewKey`, `HotViewSlice`, `HotViewSliceName` (shipped by S2-02) — `redis_key()` produces the key the store reads
  - `src/codegenie/hotviews/store.py` — `ColdStoreReader` Protocol (shipped by S3-02) — extend this file, do not create a new one
  - `src/codegenie/plugins/events.py` — `EventLog` — a constructor dependency, used by S5-02 for the integrity-miss signal; `HotViewStore.__init__` already accepts it
  - `src/codegenie/cache/keys.py` — the content-addressed cache-key discipline ADR-0003 mirrors

## Goal
`HotViewStore.get_all(repo)` serves the four hot-view slices in one pipelined Redis round-trip, and `HotViewStore.get(repo, slice_name)` returns a deserialized `HotViewSlice`.

## Acceptance criteria
- [ ] `HotViewStore.__init__(*, redis, cold_store, slice_schema_versions, event_log)` exists; no I/O and no index-building happens in the constructor.
- [ ] `get_all(repo)` issues exactly one Redis pipeline of four `GET`s (verified by a fake Redis recording the call shape) and returns a `Mapping[HotViewSliceName, HotViewSlice]` with all four keys.
- [ ] `get(repo, slice_name)` returns a `HotViewSlice` deserialized from the Redis value at `HotViewKey(repo, slice_name, slice_schema_versions[slice_name]).redis_key()`.
- [ ] The Redis key read for each slice uses `slice_schema_versions[slice_name]` for the version component — never a hardcoded `v1`.
- [ ] The TDD plan's red test exists, was committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest` all pass on the touched files.

## Implementation outline
1. Extend `src/codegenie/hotviews/store.py` (already holds `ColdStoreReader` from S3-02) with the `HotViewStore` class.
2. `__init__` stores the injected `redis` client, `cold_store`, `slice_schema_versions` mapping, and `event_log` — no side effects.
3. `get_all`: build the four `HotViewKey`s (one per `HotViewSliceName`, version from `slice_schema_versions`), open one `redis.pipeline()`, queue four `GET`s, `await pipeline.execute()`, deserialize each raw value via `HotViewSlice.model_validate_json`, return the keyed mapping.
4. `get`: build the one `HotViewKey`, `GET`, deserialize, return.
5. Keep the deserialization a private pure helper so S5-02 can wrap it with integrity verification without restructuring.

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file path: `tests/unit/hotviews/test_store_read.py`
One red test per behavior. The first asserts `get_all` does exactly one pipelined round-trip of four GETs:
```python
async def test_get_all_issues_one_pipeline_of_four_gets() -> None:
    # arrange: a fake redis whose pipeline() records each GET key and
    #          returns four serialized HotViewSlice JSON blobs on execute()
    # act:    store.get_all(RepoId("acme/api"))
    # assert: exactly one pipeline opened; exactly four GET keys queued;
    #         result is a Mapping over all four HotViewSliceName members
```
A second red test pins the key uses the injected version:
```python
async def test_get_reads_key_with_injected_slice_schema_version() -> None:
    # arrange: slice_schema_versions={"risk_flags": 3, ...}; fake redis
    # act:    store.get(RepoId("acme/api"), "risk_flags")
    # assert: the GET key is "hotview:acme/api:risk_flags:v3" — not v1
```
### Green — make it pass
Implement `HotViewStore` with the constructor and the two read methods. Use a thin `redis-py` async pipeline; deserialize with `HotViewSlice.model_validate_json`. The smallest version: no integrity check yet (that is S5-02) — just read, deserialize, return.
### Refactor — clean up
Type hints on every signature (`Redis`, `ColdStoreReader`, `Mapping[HotViewSliceName, int]`, `EventLog`); a docstring on `HotViewStore`, `get`, `get_all`. Keep the deserialization in a private helper named so S5-02 can extend it. Confirm `redis` and `EventLog` are constructor-injected, never module-level (§Harness engineering — no config at import).

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/hotviews/store.py` | Add the `HotViewStore` class alongside the existing `ColdStoreReader` Protocol |
| `src/codegenie/hotviews/__init__.py` | Export `HotViewStore` (counts against the ≤24 public-surface budget) |
| `tests/unit/hotviews/test_store_read.py` | The red tests for the read path |

## Out of scope
- Integrity verification of the `(repo, slice, gather_id, slice_schema_version)` binding and the cold-storage fail-closed fallback — S5-02.
- The `@pytest.mark.bench` `p95 < 50 ms` canary against a real `redis:7-alpine` — S7-01.
- Writing slices into Redis (`write_hot_views`) — S5-04.

## Notes for the implementer
- ADR-0003 §Consequences: `get` must end up always returning a `HotViewSlice` (never `None`). This story builds the happy read; S5-02 makes "always returns" true on a miss. Do not bake a `| None` return into the signature — keep it `-> HotViewSlice` from the start so S5-02 only adds the fallback body.
- One pipeline, four GETs — not four separate round-trips. The SLO headroom (~25×) assumes a single pipelined round-trip; four sequential GETs would quadruple the latency.
- The version component of every key comes from the injected `slice_schema_versions` mapping (ADR-0004) — a hardcoded `v1` silently breaks per-slice versioning the moment a slice's version bumps.
- No in-process LRU in front of the store (§Patterns rejected) — a second invalidation surface for no measured win.
- `redis-py >= 5` ships an async client; use the async API so `get_all` is awaitable and the bench can measure it without thread hops.
