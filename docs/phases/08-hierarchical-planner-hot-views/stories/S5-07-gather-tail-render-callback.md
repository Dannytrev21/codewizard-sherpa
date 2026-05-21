# Story S5-07 — Wire the gather-tail hot-view render callback

**Step:** Step 5 — Implement the HotViewStore, renderer, and PlannerNode routing core
**Status:** Ready
**Effort:** S
**Depends on:** S5-05
**ADRs honored:** ADR-0003, ADR-0006

## Context
The hot-view cache is populated by the gather pipeline's tail: after a gather completes, a thin detached-task callback fires `render_hot_views` + `write_hot_views` so Redis carries fresh slices for the planner to read. The wiring must be a *thin callback* — the gather pipeline must reference the renderer through a detached-task hook, never an `import codegenie.hotviews` in its runtime closure, so the renderer package stays outside the gather-runtime fence (`test_pyproject_fence.py`, edge case 16). This is the last story of Step 5.

## References — where to look
- **Architecture:**
  - `../phase-arch-design.md §C5 — HotViewRenderer` — "The gather pipeline references the renderer **only through a thin detached-task callback** so the renderer's package stays *outside* the gather-runtime closure"
  - `../phase-arch-design.md §Architectural context` — "The gather pipeline's tail fires a detached `HotViewRenderer` task"
  - `../phase-arch-design.md §Edge cases` — row 16 (a new package accidentally lands inside the gather-runtime closure → CI fails)
  - `../phase-arch-design.md §Implementation-level risks` — risk 6: the gather pipeline must reference the renderer only through a thin detached-task callback
  - `../phase-arch-design.md §Harness engineering` — the `HSET` writes are background and never block a gather or an in-flight workflow
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0003-hot-view-integrity-by-gather-id-content-addressing.md` — ADR-0003 — the rendered slices are `gather_id`-stamped from the gather that just completed
  - `../ADRs/0006-cold-storage-fallback-reads-the-rendered-repocontext.md` — ADR-0006 — the callback renders from the exact `RepoContext` artifact the gather produced, so the cold path reads the same artifact
- **Existing code (if any):**
  - `src/codegenie/hotviews/renderer.py` — `render_hot_views` + `write_hot_views` (S5-03, S5-04) — what the callback fires
  - `src/codegenie/coordinator/coordinator.py` — the gather coordinator; find the tail (post-write) hook point — the callback attaches here as a detached task
  - `src/codegenie/output/` — the writer that produces `.codegenie/context/repo-context.yaml` + `raw/*.json` — the gather tail
  - `tests/fence/` — the Phase-8 fence allowlist (S1-04) — re-run after this wiring to confirm the renderer stays outside the gather closure
  - `tests/unit/test_pyproject_fence.py` — the gather-runtime closure fence

## Goal
A thin detached-task callback at the gather pipeline's tail fires `render_hot_views` + `write_hot_views`, keeping `codegenie.hotviews` outside the gather-runtime closure.

## Acceptance criteria
- [ ] After a gather completes, a callback fires that calls `render_hot_views` then `write_hot_views`, writing the four slices to Redis.
- [ ] The callback is detached (`asyncio.create_task`-style) — it does not block the gather pipeline's completion or an in-flight workflow.
- [ ] The gather-runtime closure does **not** statically import `codegenie.hotviews` — the renderer is reached only through a callback indirection (a `Callable` injected or registered, not a top-level `import`).
- [ ] `make fence` is green — the Phase-8 fence test (S1-04) confirms `codegenie.hotviews` is still outside the gather-runtime closure after this wiring.
- [ ] The slices written carry the `gather_id` of the gather that just completed.
- [ ] The TDD plan's red test exists, was committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest` all pass on the touched files.

## Implementation outline
1. Identify the gather pipeline's tail hook point (after the writer produces `repo-context.yaml` + `raw/*.json`).
2. Add a thin callback seam: the gather tail accepts an optional render callback (a `Callable` injected at wiring time) — it does not `import codegenie.hotviews` directly.
3. Implement the callback in a module *outside* the gather closure: it renders via `render_hot_views`, writes via `write_hot_views`, and is scheduled as a detached task so it never blocks the gather.
4. Wire the callback at the CLI / composition root (where `codegenie.hotviews` is allowed to be imported).
5. Re-run `make fence` to confirm the renderer package stayed outside the gather closure.

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file path: `tests/unit/hotviews/test_gather_tail_callback.py`
First red test — the callback renders and writes after a gather:
```python
async def test_gather_tail_callback_renders_and_writes_slices() -> None:
    # arrange: a completed gather producing a RepoContext + gather_id;
    #          a fake HotViewStore recording writes
    # act:    await the gather-tail render callback
    # assert: write_hot_views was called with four gather_id-stamped slices
```
A second red test — the callback is detached, not blocking:
```python
async def test_gather_tail_callback_does_not_block_gather_completion() -> None:
    # arrange: a render callback that awaits a slow operation
    # act:    run the gather tail
    # assert: the gather tail returns before the callback completes
    #         (the callback is a detached task)
```
A fence test — the renderer stays outside the gather closure:
```python
def test_hotviews_not_in_gather_runtime_closure() -> None:
    # assert: codegenie.hotviews is NOT in the import closure
    #         test_pyproject_fence.py locks for the gather pipeline
    # (extend or assert against the S1-04 Phase-8 fence allowlist)
```
### Green — make it pass
Add the callback seam to the gather tail (a `Callable` hook, no direct `hotviews` import) and the callback implementation in an out-of-closure module. The smallest version schedules the callback as a detached task.
### Refactor — clean up
Type hints on the callback `Callable` signature and the hook; a docstring on the callback stating it is detached and fire-and-forget; `structlog` logging on callback failure (Rule 12 — a render failure must be visible, not silent); confirm the gather closure has no `codegenie.hotviews` import edge.

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/coordinator/coordinator.py` (or the gather tail module) | Add the thin callback hook at the gather tail — a `Callable`, no `hotviews` import |
| `src/codegenie/hotviews/renderer.py` or a new wiring module | The detached-task callback that fires `render_hot_views` + `write_hot_views` |
| `src/codegenie/cli.py` | Wire the callback at the composition root (where importing `hotviews` is allowed) |
| `tests/unit/hotviews/test_gather_tail_callback.py` | The red tests for render-and-write + detached-not-blocking |
| `tests/fence/` | Confirm / extend the Phase-8 fence — `codegenie.hotviews` stays outside the gather closure |

## Out of scope
- The per-`RepoId` debounce under push churn (Open Question 5) — a tuning parameter validated against real push-frequency data, not a Phase-8 blocker; note in the attempt log if churn is observed.
- The `phase08_e2e` latency test that runs after a real render — S7-02.
- The `invalidates`-driven incremental render (re-render only changed slices) — `invalidates` ships in S5-04; wiring it into the callback for incremental gathers is a refinement, deferred unless the executor finds full re-render too costly.

## Notes for the implementer
- Edge case 16 is the load-bearing constraint: the gather pipeline must reference the renderer *only* through a thin detached-task callback. A top-level `import codegenie.hotviews` anywhere in the gather closure pulls `redis` into the gather-runtime closure and breaks `test_pyproject_fence.py`. Use a `Callable` hook injected at the composition root.
- Detached, not blocking: the `HSET` writes are background — a gather (or an in-flight workflow) must never wait on the hot-view render. Schedule with `asyncio.create_task` (or the codebase's equivalent detached-task idiom).
- Fail loud but isolated (Rule 12): a render failure logs via `structlog` — it must be visible — but it must not crash the gather. A stale hot view is acceptable (S5-02's integrity check + cold fallback covers it); a crashed gather is not.
- The callback renders from the exact `RepoContext` the gather just produced (ADR-0006) — this is what makes warm/cold equivalence (S7-03) hold byte-for-byte. Do not re-load or re-gather inside the callback.
- Run `make fence` as the final check — the S1-04 Phase-8 fence allowlist and the gather-closure fence are both load-bearing CI gates this story can break.
