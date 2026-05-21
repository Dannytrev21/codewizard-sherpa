# Story S5-04 — Implement the invalidates matcher and write_hot_views shell

**Step:** Step 5 — Implement the HotViewStore, renderer, and PlannerNode routing core
**Status:** Ready
**Effort:** M
**Depends on:** S5-03, S5-02
**ADRs honored:** ADR-0003, ADR-0004

## Context
Two halves of the renderer's write side: `invalidates` is a pure matcher mapping changed probe outputs to the hot-view slices they feed (so an incremental gather re-renders only the affected slices); `write_hot_views` is the imperative shell that does one atomic Redis write per slice and returns a `RenderReport` (edge case 7 — a mid-render crash yields `failed_slices`, never a torn slice). Together they complete the renderer started in S5-03.

## References — where to look
- **Architecture:**
  - `../phase-arch-design.md §C5 — HotViewRenderer` — `invalidates` (pure matcher, 100% branch coverage), `write_hot_views` (shell, one atomic `HSET` per slice → `RenderReport`)
  - `../phase-arch-design.md §Edge cases` — row 7 (renderer crashes mid-run → `RenderReport.failed_slices` non-empty; a torn slice is structurally impossible — one atomic write per slice)
  - `../phase-arch-design.md §Testing strategy` — property test: `invalidates` is monotone (adding a probe never removes a slice); 100% branch coverage on `invalidates`
  - `../phase-arch-design.md §Harness engineering` — `write_hot_views` failures log explicitly
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0003-hot-view-integrity-by-gather-id-content-addressing.md` — ADR-0003 — each written slice carries the `gather_id`; one atomic write per slice makes a torn slice impossible
  - `../ADRs/0004-per-slice-hot-view-schema-versioning.md` — ADR-0004 — the write key carries `slice_schema_version`; a version bump touches only that slice
- **Source design:**
  - `../final-design.md §Synthesis ledger` — gather-driven invalidation, no TTL
- **Existing code (if any):**
  - `src/codegenie/hotviews/renderer.py` — `render_hot_views` (S5-03) — `invalidates` and `write_hot_views` are added to this same module
  - `src/codegenie/hotviews/model.py` — `RenderReport` (S2-05), `HotViewSlice`, `HotViewKey` (S2-02)
  - `src/codegenie/hotviews/store.py` — `HotViewStore` (S5-01/S5-02) — `write_hot_views` writes through it
  - `src/codegenie/probes/base.py` — `ProbeOutput` — the input `invalidates` matches on

## Goal
A pure `invalidates(probe_outputs) -> set[HotViewSliceName]` maps changed probes to the slices they feed, and a shell `write_hot_views(slices, store) -> RenderReport` writes each slice with one atomic Redis operation.

## Acceptance criteria
- [ ] `invalidates(probe_outputs)` returns the set of `HotViewSliceName`s the given probe outputs feed; it imports no I/O module (functional-core purity AST test).
- [ ] `invalidates` has 100% branch coverage (it is part of an exit-criteria-bearing surface — ADR-0004).
- [ ] A Hypothesis property test confirms `invalidates` is monotone: adding a probe to `probe_outputs` never removes a slice from the returned set.
- [ ] `write_hot_views(slices, store)` does exactly one atomic Redis write per slice (verified by a fake store recording the call shape) and returns a `RenderReport` with the written slices in `rendered_slices`.
- [ ] A `write_hot_views` run where one slice write fails returns a `RenderReport` with that slice in `failed_slices` and the others in `rendered_slices`; the failure is logged.
- [ ] The TDD plan's red test exists, was committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest` all pass on the touched files.

## Implementation outline
1. Add `invalidates` to `renderer.py`: a pure matcher iterating a module-level `Final` mapping of probe-name → `frozenset[HotViewSliceName]`; union the slices for every changed probe.
2. Add `write_hot_views` (async shell): for each `HotViewSlice`, build its `HotViewKey`, do one atomic Redis write through `store`; catch a per-slice write error and record it in `failed_slices`.
3. Return a `RenderReport(rendered_slices=..., failed_slices=..., gather_id=...)`.
4. The probe-name → slice mapping is a `Final` dict iterated, never an `if-elif` chain (the codebase's data-driven-catalog convention).

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file path: `tests/unit/hotviews/test_invalidates_and_write.py`
First red test — `invalidates` maps probes to slices:
```python
def test_invalidates_maps_changed_probes_to_their_slices() -> None:
    # arrange: probe outputs for a probe known to feed risk_flags
    # act:    result = invalidates(probe_outputs)
    # assert: "risk_flags" in result; an unrelated slice is not in result
```
The monotone property test (Hypothesis):
```python
@given(probes=lists(probe_output_strategy()), extra=probe_output_strategy())
def test_invalidates_is_monotone(probes, extra) -> None:
    # assert: invalidates(probes) <= invalidates(probes + [extra])
    #         (adding a probe never removes a slice)
```
A red test for `write_hot_views` atomicity:
```python
async def test_write_hot_views_one_atomic_write_per_slice() -> None:
    # arrange: four rendered slices; a fake store recording each write
    # act:    report = write_hot_views(slices, store)
    # assert: exactly four atomic writes; report.rendered_slices has all four;
    #         report.failed_slices is empty
```
A red test for the partial-failure path:
```python
async def test_write_hot_views_records_failed_slice() -> None:
    # arrange: a fake store that raises on the risk_flags write only
    # act/assert: report.failed_slices == ("risk_flags",); the other three rendered;
    #             one structlog warning emitted
```
### Green — make it pass
Implement `invalidates` over the `Final` probe→slice mapping and `write_hot_views` as the per-slice atomic-write shell. The smallest version catches each slice's write error independently and accumulates the `RenderReport`.
### Refactor — clean up
Type hints (`Sequence[ProbeOutput]`, `set[HotViewSliceName]`, `Sequence[HotViewSlice]`, `HotViewStore`, `RenderReport`); docstrings stating `invalidates` purity and `write_hot_views`'s torn-slice-impossible guarantee; `structlog` warning IDs registered in `_WARNING_IDS`; confirm `invalidates` is in the purity AST scan.

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/hotviews/renderer.py` | Add `invalidates` and `write_hot_views` alongside `render_hot_views` |
| `src/codegenie/hotviews/__init__.py` | Export `invalidates`, `write_hot_views` if part of the public surface; register warning IDs |
| `tests/unit/hotviews/test_invalidates_and_write.py` | The red + property tests |
| `tests/property/hotviews/test_invalidates_monotone.py` | The Hypothesis monotone property test (if property tests live under `tests/property/`) |

## Out of scope
- The gather-tail callback that calls `invalidates` + `render_hot_views` + `write_hot_views` — S5-07.
- The hot-view debounce under churn (per-`RepoId` debounce) — Open Question 5; a Phase-8 tuning parameter, not this story.
- The warm/cold-equivalence property test — S7-03.

## Notes for the implementer
- `invalidates` monotonicity is a real invariant, not decoration: an incremental gather that adds a probe must not *un*-invalidate a slice — that would leave a stale slice in Redis. The Hypothesis property test is the guard.
- One atomic Redis write per slice (ADR-0003) — a torn slice (half-written value) must be structurally impossible. Do not write a slice in two operations.
- A mid-render crash is acceptable: the prior consistent slice or no slice stays in Redis (edge case 7); a no-slice read triggers S5-02's cold-storage fallback. Stale-but-consistent is fine; torn is not.
- The probe→slice mapping is a `Final` dict iterated — mirror `_GENERATOR_HEADER_MARKERS` / `_LOCKFILE_PRECEDENCE` style, not an `if-elif` chain (CLAUDE.md §Open/Closed seams).
- 100% branch coverage on `invalidates` is an ADR-0004 requirement — cover the empty-input, single-probe, and multi-probe-overlapping-slices branches.
- Fail loud (Rule 12): a failed slice write is logged and surfaced in `RenderReport.failed_slices` — never swallowed.
