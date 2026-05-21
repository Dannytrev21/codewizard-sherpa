# Story S5-02 — Add hot-view integrity verification and cold-storage fail-closed

**Step:** Step 5 — Implement the HotViewStore, renderer, and PlannerNode routing core
**Status:** Ready
**Effort:** M
**Depends on:** S5-01
**ADRs honored:** ADR-0003, ADR-0004, ADR-0006

## Context
This story makes Redis untrusted-on-read: every value `HotViewStore` reads is verified against the `(repo, slice, gather_id, slice_schema_version)` binding, and any mismatch — stale, tampered, or version-drift — discards the Redis value and falls closed to the `ColdStoreReader`. It closes the security half of the hot-view cache (ADR-0003): a writable-Redis compromise becomes a latency cost, never a context-poisoning cost. It extends the `HotViewStore` shipped in S5-01.

## References — where to look
- **Architecture:**
  - `../phase-arch-design.md §C4 — HotViewStore` — the integrity-verification internal structure; `get` always returns a `HotViewSlice` (never `None`); failure behavior (`ConnectionError` → cold read, integrity miss → cold read, both logged)
  - `../phase-arch-design.md §Scenario 2` — failure path: hot view stale/tampered, fail-closed to cold storage; planner context byte-identical to the no-tamper run
  - `../phase-arch-design.md §Edge cases` — rows 4 (Redis unreachable), 5 (tampered/stale value), 6 (one slice's schema shape changes)
  - `../phase-arch-design.md §Harness engineering` — integrity misses and Redis-unreachable fallbacks log explicitly via `structlog`, never silent
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0003-hot-view-integrity-by-gather-id-content-addressing.md` — ADR-0003 — verify the `(repo, slice_name, gather_id, slice_schema_version)` binding on read; any mismatch → cold read; the miss is logged as a security/ops signal with a `_WARNING_IDS`-registered ID
  - `../ADRs/0004-per-slice-hot-view-schema-versioning.md` — ADR-0004 — version-drift on one slice is a clean per-slice miss; 100% branch coverage required on the integrity/version-compare path
  - `../ADRs/0006-cold-storage-fallback-reads-the-rendered-repocontext.md` — ADR-0006 — the cold read goes through the `ColdStoreReader` Port, reading the same `RepoContext` artifact the renderer rendered from
- **Source design:**
  - `../final-design.md §Synthesis ledger row "Redis trust posture"` — fail-closed property via a substrate-honest mechanism (no KMS/HMAC)
- **Existing code (if any):**
  - `src/codegenie/hotviews/store.py` — `HotViewStore` (S5-01) and `ColdStoreReader` (S3-02) — extend in place
  - `src/codegenie/hotviews/model.py` — `HotViewSlice` carries `gather_id` and `slice_schema_version` so the value self-describes its binding
  - `src/codegenie/plugins/events.py` — `EventLog.emit_internal` — the injected log for the integrity-miss signal

## Goal
`HotViewStore.get` / `get_all` verify the `(repo, slice, gather_id, slice_schema_version)` binding on every read and fall closed to the `ColdStoreReader` — logging the miss — whenever it fails or Redis raises `ConnectionError`.

## Acceptance criteria
- [ ] A read whose deserialized `HotViewSlice` carries a `gather_id` not matching the gather identity the caller passed is discarded; the `ColdStoreReader` value is returned instead.
- [ ] A read whose `slice_schema_version` does not match `slice_schema_versions[slice_name]` is discarded → cold read (version-drift, edge case 6).
- [ ] A Redis `ConnectionError` (or a missing key) is caught and resolves to a cold read; `get` still returns a valid `HotViewSlice`, never `None` or an exception.
- [ ] Every fallback (stale / tampered / version-drift / `ConnectionError`) emits a `structlog` warning with an ID from the package `_WARNING_IDS` matching `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`.
- [ ] The integrity/version-compare path has 100% branch coverage (it is part of an exit-criteria-bearing function).
- [ ] The TDD plan's red test exists, was committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest` all pass on the touched files.

## Implementation outline
1. `get` / `get_all` must accept (or already hold) the gather identity (`gather_id`) the caller is working against — confirm the signature carries it; if S5-01 omitted it, add it as a keyword argument.
2. After deserialization, run a pure `_verify_binding(slice, repo, slice_name, expected_gather_id, expected_version) -> bool` helper.
3. On a `False` verdict, on a missing key, or on a caught `ConnectionError`: emit the integrity/fallback `structlog` warning, call `cold_store.read(repo, slice_name, gather_id)`, return that.
4. Keep `_verify_binding` pure — it imports no I/O module — so the branch-coverage test runs with zero mocks.
5. Register the new warning IDs in the package `_WARNING_IDS` (declared by S3-05).

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file path: `tests/unit/hotviews/test_store_integrity.py`
One red test per failure mode. Stale `gather_id`:
```python
async def test_stale_gather_id_falls_closed_to_cold_store() -> None:
    # arrange: fake redis returns a HotViewSlice JSON with gather_id="OLD";
    #          caller works against gather_id="NEW"; a recording ColdStoreReader
    # act:    store.get(RepoId("acme/api"), "risk_flags", gather_id="NEW")
    # assert: the returned slice is the ColdStoreReader's value, NOT the Redis one;
    #         exactly one structlog warning with a _WARNING_IDS-registered id
```
A second red test for version-drift:
```python
async def test_slice_schema_version_drift_falls_closed() -> None:
    # arrange: redis value has slice_schema_version=1; injected map says risk_flags->2
    # act/assert: cold read returned; warning emitted
```
A third for Redis unreachable:
```python
async def test_connection_error_falls_closed_and_get_never_raises() -> None:
    # arrange: fake redis whose execute() raises redis ConnectionError
    # act:    store.get_all(...)
    # assert: returns a full Mapping of cold-read slices; no exception escapes
```
### Green — make it pass
Add the `_verify_binding` pure helper and the fallback branch to `get` / `get_all`. Wrap the pipeline `execute()` in a `try/except ConnectionError`. The smallest version routes every non-verified or errored read through `cold_store`.
### Refactor — clean up
Docstrings on the verification helper stating the four miss modes; `structlog` IDs registered in `_WARNING_IDS`; confirm `_verify_binding` imports no I/O module (it will be picked up by the S5-03/S5-04 purity AST scan if co-located, or add it to the scan). Ensure the warm path stays branchless for the planner — `get` returns a `HotViewSlice` on every path.

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/hotviews/store.py` | Add `_verify_binding`, the cold-fallback branch, and the `ConnectionError` guard to `HotViewStore` |
| `src/codegenie/hotviews/__init__.py` | Register the new warning IDs in `_WARNING_IDS` if not already present |
| `tests/unit/hotviews/test_store_integrity.py` | The red tests for stale / version-drift / `ConnectionError` |

## Out of scope
- The adversarial Redis-tamper tests (attacker-controlled `risk_flags` bytes, byte-identical-to-no-tamper assertion) — S7-04.
- The warm/cold-equivalence Hypothesis property test — S7-03.
- The concrete disk `ColdStoreReader` adapter implementation — S3-02 declared the Protocol; the disk adapter is wired where the renderer is read from (S5-03/S5-07 path). If no concrete adapter exists yet, the integrity tests use a fake `ColdStoreReader`; flag the gap in the attempt log.

## Notes for the implementer
- ADR-0003: a stale value and a tampered value are *the same code path* — both fail the `(repo, slice, gather_id, slice_schema_version)` binding and both resolve as a cache miss. Do not special-case "tamper" — the design's whole point is that integrity is structural, not a bolted-on security check.
- Fail-closed, not fail-hard: a `ConnectionError` must never escape `get`/`get_all`. The planner's warm path is branchless precisely because `get` always returns a `HotViewSlice`.
- 100% branch coverage on the verify path is an ADR-0004 requirement — it is part of an exit-criteria-bearing function. Cover matching, stale `gather_id`, version-drift, and missing-key as four distinct branches.
- Log every fallback (Rule 12 — fail loud). A sustained tamper attack flips every read to cold; the integrity-miss signal is what makes that visible — silence here is the worst failure mode.
- The cold read must use the *same* `gather_id` the caller passed (ADR-0006) — otherwise warm/cold equivalence (tested in S7-03) breaks.
