# Story S5-03 — Implement the pure render_hot_views function

**Step:** Step 5 — Implement the HotViewStore, renderer, and PlannerNode routing core
**Status:** Ready
**Effort:** M
**Depends on:** S2-02
**ADRs honored:** ADR-0003, ADR-0004, ADR-0006

## Context
`render_hot_views` is the pure functional core of the hot-view cache: it derives the four slices (`available_skills`, `entrypoint`, `risk_flags`, `confidence_summary`) from a `RepoContext` artifact plus the union of `must_read` queries across the active TCCMs. Because it is pure, the warm renderer and the cold-storage fallback compute a slice the *same* way (ADR-0006) — warm/cold equivalence becomes structural, not a matched pair of implementations. The shell that writes slices to Redis is S5-04; this story is the derivation only.

## References — where to look
- **Architecture:**
  - `../phase-arch-design.md §C5 — HotViewRenderer` — the public interface for `render_hot_views` (pure, returns `tuple[HotViewSlice, ...]`), the "derive slices from `RepoContext` + the `must_read` union across `active_tccms`" internal structure
  - `../phase-arch-design.md §Data model` — `HotViewSlice`, the four per-slice payload models, `HotViewSliceName`
  - `../phase-arch-design.md §Harness engineering` — `render_hot_views` is idempotent: re-rendering the same `RepoContext` produces byte-identical slices (golden-tested)
  - `../phase-arch-design.md §Testing strategy` — golden files under `tests/golden/hotviews/{repo}/`; the functional-core purity AST test
  - `../phase-arch-design.md §Design patterns applied` — "which slices to render" is derived from TCCM aggregation, not a hand-curated list (production ADR-0029)
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0003-hot-view-integrity-by-gather-id-content-addressing.md` — ADR-0003 — every rendered slice is stamped with the source `gather_id`
  - `../ADRs/0004-per-slice-hot-view-schema-versioning.md` — ADR-0004 — every rendered slice carries its own `slice_schema_version`
  - `../ADRs/0006-cold-storage-fallback-reads-the-rendered-repocontext.md` — ADR-0006 — the cold reader re-runs *this same* pure function; keep it single-sourced
- **Production ADRs (if applicable):**
  - `../../../production/adrs/0029-task-class-context-manifests.md` — `must_read` / `should_read` / `may_read` bands on a TCCM
- **Existing code (if any):**
  - `src/codegenie/hotviews/model.py` — `HotViewSlice` and the four payload models (S2-02) — what `render_hot_views` constructs
  - `src/codegenie/plugins/tccm.py` — `TCCM` with `must_read: list[ContextQuery]`, `ContextQuery` — the active-TCCM input
  - `src/codegenie/schema/` — the `RepoContext` artifact shape `render_hot_views` reads from

## Goal
A pure `render_hot_views(repo, repo_context, active_tccms, gather_id) -> tuple[HotViewSlice, ...]` derives the four `gather_id`- and `slice_schema_version`-stamped hot-view slices.

## Acceptance criteria
- [ ] `render_hot_views` is a module-level pure function: it imports no I/O module (no `redis`, no filesystem, no network) — proven by a functional-core purity AST test.
- [ ] It returns exactly four `HotViewSlice` objects, one per `HotViewSliceName`, each stamped with the passed `gather_id`.
- [ ] Each returned slice's `slice_schema_version` matches the module-level `Final` per-slice version dict.
- [ ] Calling `render_hot_views` twice on the same inputs returns byte-identical slices (idempotent / deterministic — golden-tested).
- [ ] A golden fixture under `tests/golden/hotviews/{repo}/` pins a gathered `RepoContext` + the expected four rendered slices; a golden diff catches accidental shape change.
- [ ] The TDD plan's red test exists, was committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest` all pass on the touched files.

## Implementation outline
1. Create `src/codegenie/hotviews/renderer.py`.
2. Implement `render_hot_views` as a pure function: derive each of the four slice payloads from `RepoContext` plus the union of `must_read` `ContextQuery`s across `active_tccms` (deduplicate the union deterministically — sort by a stable key).
3. Construct a `HotViewSlice` per slice name, stamping `gather_id` and the `slice_schema_version` from the module-level `Final` dict.
4. Return the four slices as a fixed-order `tuple`.
5. Build one golden fixture: a small gathered `RepoContext` and the four expected slices serialized to disk.

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file path: `tests/unit/hotviews/test_renderer.py`
First red test — the four-slice contract:
```python
def test_render_hot_views_derives_four_stamped_slices() -> None:
    # arrange: a fixture RepoContext, two active TCCMs with overlapping must_read,
    #          a gather_id="abc123"
    # act:    slices = render_hot_views(repo, repo_context, active_tccms, gather_id)
    # assert: len(slices)==4; {s.slice_name for s in slices} == all HotViewSliceName;
    #         every slice.gather_id == "abc123"
```
A second red test pins determinism (the load-bearing property for ADR-0006):
```python
def test_render_hot_views_is_byte_identical_on_re_render() -> None:
    # act:    a = render_hot_views(...); b = render_hot_views(...)  # same inputs
    # assert: [s.model_dump_json() for s in a] == [s.model_dump_json() for s in b]
```
A golden test asserts the rendered slices match the committed fixture:
```python
def test_render_hot_views_matches_golden() -> None:
    # arrange: load tests/golden/hotviews/{repo}/repo-context.json + expected slices
    # act/assert: render_hot_views(...) == the committed expected slices
```
### Green — make it pass
Implement the derivation. The smallest version maps each slice name to a derivation over `RepoContext` + the `must_read` union; the `must_read` union must be deterministically ordered before it influences any payload.
### Refactor — clean up
Type hints (`RepoContext`, `Sequence[TCCM]`, `BlobDigest`, `tuple[HotViewSlice, ...]`); docstring on `render_hot_views` stating purity and determinism; a module-level `Final` per-slice version dict that S5-01/S5-02's `slice_schema_versions` mirrors. Confirm the function does not branch on a hand-curated slice list — the four slices are derived (ADR-0029).

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/hotviews/renderer.py` | New module — the pure `render_hot_views` |
| `src/codegenie/hotviews/__init__.py` | Export `render_hot_views` (counts against the ≤24 surface budget) |
| `tests/unit/hotviews/test_renderer.py` | The red + golden tests |
| `tests/golden/hotviews/{repo}/` | The golden `RepoContext` + expected four slices fixture |
| `tests/unit/hotviews/test_renderer_purity.py` | The functional-core purity AST test (mirrors `tests/unit/plugins/test_resolver_purity.py`) |

## Out of scope
- The `invalidates` matcher and the `write_hot_views` shell — S5-04 (same `renderer.py` module).
- The gather-tail callback that fires `render_hot_views` — S5-07.
- The warm/cold-equivalence Hypothesis property test — S7-03 (depends on this function being single-sourced).

## Notes for the implementer
- Purity is load-bearing: ADR-0006 makes warm/cold equivalence *structural* by re-using this exact function in the cold path. Any I/O import here forks the renderer into two implementations that can silently diverge. The purity AST test is the guard.
- Determinism: the `must_read` union across TCCMs must be deterministically ordered (sort by a stable key) before it feeds any payload — a set's iteration order is not stable across runs and would break the byte-identical golden.
- Stamp `gather_id` and `slice_schema_version` on *every* slice — the value self-describes its binding so the store (S5-02) can cross-check both (ADR-0004 §Consequences).
- The four slices are *derived* from TCCM aggregation (ADR-0029) — do not hardcode "render these four" as a branch; iterate `HotViewSliceName`'s members.
- Keep the per-slice version dict module-level `Final` — it is the single source the store's injected `slice_schema_versions` mirrors. A reviewer bumps only the slice whose shape changed (ADR-0004 reviewer discipline).
