# Story S3-02 — Declare the ColdStoreReader port

**Step:** Step 3 — Declare the planner ports and extend the event union
**Status:** Ready
**Effort:** S
**Depends on:** S2-02
**ADRs honored:** ADR-0006, ADR-0003

## Context
The hot-view store (S5-01/S5-02) is untrusted on read: an integrity miss or a Redis `ConnectionError` must **fail closed** to cold storage, returning the *same* slice data the hot view would have. For that fallback to change only latency and never the answer, the cold read must reconstruct the slice from the identical `RepoContext` artifact the renderer rendered from. This story lands the `ColdStoreReader` `Protocol` — the storage seam — before the store logic that depends on it; Phase 9 later swaps in a Postgres adapter with zero planner-code change.

## References — where to look
- **Architecture:**
  - `../phase-arch-design.md §C4 — HotViewStore (codegenie.hotviews.store)` — `HotViewStore.__init__` takes a `cold_store: ColdStoreReader`; `get` never returns `None`.
  - `../phase-arch-design.md §Scenarios — Scenario 2` — the stale/tampered fail-closed-to-cold-storage sequence.
  - `../phase-arch-design.md §Development view` — `hotviews/store.py` holds `HotViewStore` *and* (interface only, this story) the `ColdStoreReader` `Protocol`.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0006-cold-storage-fallback-reads-the-rendered-repocontext.md` — ADR-0006 — `ColdStoreReader` is a Port; the Phase-8 adapter reads the on-disk `RepoContext` by `gather_id`; warm/cold equivalence is byte-for-byte.
  - `../ADRs/0003-hot-view-integrity-by-gather-id-content-addressing.md` — ADR-0003 — an integrity miss falls through to a cold read; Redis is untrusted on read.
- **Existing code (if any):**
  - `src/codegenie/plugins/events.py §EventStreamSink` — a shipped `@runtime_checkable Protocol` precedent.
  - `src/codegenie/schema/` — the `RepoContext` artifact type the cold adapter reads (the renderer's source).

## Goal
Declare the `ColdStoreReader` `Protocol` in `hotviews/store.py` so the fail-closed cold-storage seam is fixed before `HotViewStore` logic is written.

## Acceptance criteria
- [ ] `codegenie/hotviews/store.py` exists declaring `ColdStoreReader` as an `@runtime_checkable Protocol` with one method: `async def read_slice(self, repo: RepoId, slice_name: HotViewSliceName, gather_id: BlobDigest) -> HotViewSlice` — note the `gather_id` argument that pins artifact identity (ADR-0006).
- [ ] The method return type is `HotViewSlice` (never `HotViewSlice | None`) — a cold read always resolves, keeping `HotViewStore.get`'s warm path branchless.
- [ ] The `Protocol`'s docstring states it reads the *same* `RepoContext` artifact the renderer rendered from (ADR-0006 / Open Question 6), and that the Phase-8 adapter is a disk adapter while Phase 9 swaps a Postgres adapter.
- [ ] `codegenie/hotviews/__init__.py` exists; `ColdStoreReader` is exported via `__all__` only if a sibling package needs it, otherwise it stays package-internal.
- [ ] The TDD plan's red test exists, was committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest` all pass on the touched files.

## Implementation outline
1. Create `src/codegenie/hotviews/__init__.py` and `src/codegenie/hotviews/store.py` (interface only — no `HotViewStore` class yet).
2. Declare `ColdStoreReader` as an `@runtime_checkable Protocol` with the single `read_slice` async method.
3. Write the docstring pinning the artifact-identity invariant (ADR-0006) and naming Open Question 6 as the implementer-verification step S5-02/S7-03 close.
4. Set `__all__` on `store.py` and re-export through `hotviews/__init__.py` only what other packages consume.
5. Run `mypy --strict src/codegenie/hotviews/`.

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file path: `tests/unit/hotviews/test_cold_store_reader_port.py`
Assert the Port is structural and its method signature pins `gather_id`.
```python
def test_cold_store_reader_is_runtime_checkable_protocol() -> None:
    # arrange: a trivial object exposing async read_slice(repo, slice_name, gather_id) -> HotViewSlice
    # act:    isinstance(fake, ColdStoreReader)
    # assert: True — structural Protocol match

def test_cold_store_reader_read_slice_takes_gather_id() -> None:
    # arrange: inspect.signature(ColdStoreReader.read_slice)
    # act:    read the parameter names
    # assert: "gather_id" is a parameter — ADR-0006 artifact-identity pin is in the contract
```
### Green — make it pass
Create `hotviews/__init__.py` and `hotviews/store.py` with the single `@runtime_checkable Protocol`. The method body is `...`.
### Refactor — clean up
Add the module + `Protocol` docstrings (ADR-0006, Open Question 6). Confirm no I/O import in `store.py` yet (this story is interface-only). Note the public-surface running total in the attempt log.

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/hotviews/__init__.py` | New package marker + bounded `__all__`. |
| `src/codegenie/hotviews/store.py` | The `ColdStoreReader` `Protocol` (interface only). |
| `tests/unit/hotviews/test_cold_store_reader_port.py` | Red test — Protocol structural check + `gather_id`-in-signature check. |

## Out of scope
- The `HotViewStore` class and its Redis read path — S5-01.
- Integrity verification and the fail-closed fallback logic — S5-02.
- The concrete disk `ColdStoreReader` adapter — S5-02 (the adapter lands with the consumer that needs it).
- The warm/cold-equivalence property test — S7-03.
- `HotViewSlice` / `HotViewSliceName` model declarations — S2-02.

## Notes for the implementer
- This is **interface only** — declare the `Protocol`, not the `HotViewStore` class and not the disk adapter. Putting the `Protocol` in `store.py` (rather than a separate `ports.py`) matches §Development view's package layout.
- The `gather_id` argument is load-bearing: it is the artifact-identity pin that makes warm/cold equivalence (S7-03) provable. Do not drop it for a simpler signature.
- `read_slice` returns `HotViewSlice`, never `None` — ADR-0006 §Consequences makes the branchless warm path a stated invariant.
- Use `Protocol` (structural), not `ABC` — the Phase-8 disk adapter and the Phase-9 Postgres adapter satisfy it by shape.
- Open Question 6 (does the adapter read the renderer's exact artifact?) is *not* resolved here — it is flagged in the docstring and verified when S5-02 ships the disk adapter and S7-03 writes the equivalence test.
