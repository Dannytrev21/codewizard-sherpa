# Story S2-05 — Declare the RenderReport model

**Step:** Step 2 — Declare the hot-view data model and the Supervisor/routing sum types
**Status:** Ready
**Effort:** S
**Depends on:** S2-02
**ADRs honored:** ADR-0003, ADR-0004

## Context
The hot-view renderer writes four slices to Redis as a detached background task. If it crashes mid-run, the result must be a *typed report* of what was written and what failed — not a silent partial state. This story lands `RenderReport`, the frozen model `write_hot_views` returns (edge case 7), so the renderer's partial-failure path is structurally honest from the start. It is foundational, contracts-first work: a no-slice or partial render must be observable, and `RenderReport` is how — a crashed render yields a `RenderReport` with non-empty `failed_slices`, and a missing slice on read triggers the cold-storage fallback (ADR-0003).

## References — where to look
- **Architecture:**
  - `../phase-arch-design.md §Data model` — the `[internal] render report` block: `RenderReport` with `rendered_slices: tuple[HotViewSliceName, ...]`, `failed_slices: tuple[HotViewSliceName, ...]`, `gather_id: BlobDigest`.
  - `../phase-arch-design.md §C5 — HotViewRenderer` — `write_hot_views(...) -> RenderReport`; "A mid-render crash yields a `RenderReport` with `failed_slices`."
  - `../phase-arch-design.md §Edge cases` — edge case 7: renderer crashes mid-run → `RenderReport.failed_slices` non-empty; the prior consistent slice or no slice stays; a torn slice is structurally impossible (one atomic write per slice).
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0003-hot-view-integrity-by-gather-id-content-addressing.md` — ADR-0003 — every rendered slice (and the report describing the render) is `gather_id`-stamped; a no-slice read falls closed to cold storage.
  - `../ADRs/0004-per-slice-hot-view-schema-versioning.md` — ADR-0004 — slices version independently; a `RenderReport` describes a single gather's render, so one `gather_id` for the whole report is correct.
- **Production ADRs (if applicable):**
  - `../../../production/adrs/0013-pre-rendered-redis-hot-views.md` — the four-slice render model.
- **Existing code (if any):**
  - `src/codegenie/hotviews/model.py` — created by S2-02; this story adds `RenderReport` to the *same* module. `HotViewSliceName` and `BlobDigest` are already in scope.
  - `src/codegenie/plugins/subgraph.py:65` — the frozen-model `ConfigDict` convention.

## Goal
Declare the frozen `RenderReport` model in `codegenie/hotviews/model.py`, so the renderer's `write_hot_views` shell has a typed partial-failure return that names exactly which slices rendered and which failed.

## Acceptance criteria
- [ ] `codegenie/hotviews/model.py` declares `RenderReport` as a frozen model (`model_config = ConfigDict(frozen=True, extra="forbid")`).
- [ ] `RenderReport` carries `rendered_slices: tuple[HotViewSliceName, ...]`, `failed_slices: tuple[HotViewSliceName, ...]`, and `gather_id: BlobDigest`.
- [ ] A `RenderReport` with all four slices in `rendered_slices` and an empty `failed_slices` round-trips through `model_validate(model_dump())`.
- [ ] A `RenderReport` constructed with a slice name outside the four-member `HotViewSliceName` `Literal` raises a `ValidationError`.
- [ ] `RenderReport` is listed in `codegenie/hotviews/__init__.py.__all__`; the running ≤ 24 public-surface count is noted in the attempt log.
- [ ] The TDD plan's red test exists, was committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest` all pass on the touched files.

## Implementation outline
1. In `codegenie/hotviews/model.py` (created by S2-02), declare `RenderReport` frozen with the three fields.
2. Type `rendered_slices` and `failed_slices` as `tuple[HotViewSliceName, ...]` so an invalid slice name fails validation.
3. Add `RenderReport` to `codegenie/hotviews/__init__.py.__all__`.

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file path: `tests/unit/hotviews/test_render_report.py`

```python
def test_render_report_records_partial_failure() -> None:
    # WHY: edge case 7 — a mid-render crash must produce a TYPED report
    # naming what failed, never a silent partial state; failed_slices is the
    # observable signal a downstream read uses to fall closed to cold storage.
    report = RenderReport(
        rendered_slices=("available_skills", "entrypoint", "confidence_summary"),
        failed_slices=("risk_flags",),
        gather_id=BlobDigest("a" * 64),
    )
    assert report.failed_slices == ("risk_flags",)

def test_render_report_round_trips() -> None:
    # WHY: a RenderReport is logged — it must survive a dump/validate cycle
    # byte-stably so the audit trail is faithful.
    full = RenderReport(rendered_slices=("available_skills", "entrypoint",
                        "risk_flags", "confidence_summary"), failed_slices=(),
                        gather_id=BlobDigest("b" * 64))
    assert RenderReport.model_validate(full.model_dump()) == full

def test_render_report_rejects_unknown_slice_name() -> None:
    # WHY: the slice set is closed (HotViewSliceName Literal) — a report
    # naming a non-existent slice is a malformed render, caught at construction.
    with pytest.raises(ValidationError):
        RenderReport(rendered_slices=("not_a_slice",), failed_slices=(),
                     gather_id=BlobDigest("c" * 64))
```

### Green — make it pass
Declare `RenderReport` frozen with the three typed fields. Smallest shape — no renderer logic (S5-03/S5-04), no Redis write (S5-04).

### Refactor — clean up
Docstring naming the `[internal]` status and edge case 7. Confirm `tuple[HotViewSliceName, ...]` rejects an unknown slice name. Add a module comment that a `RenderReport` describes one gather's render — hence one `gather_id` for the whole report, consistent with ADR-0003's per-gather content identity.

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/hotviews/model.py` | Adds the `RenderReport` model. |
| `src/codegenie/hotviews/__init__.py` | `__all__` gains `RenderReport`. |
| `tests/unit/hotviews/test_render_report.py` | Red tests: partial-failure record, round-trip, unknown-slice rejection. |

## Out of scope
- `write_hot_views` — the shell that *produces* a `RenderReport` — S5-04.
- `render_hot_views` and the `invalidates` matcher — S5-03 / S5-04.
- The atomic per-slice `HSET` writes — S5-04.
- Any logic that reads `RenderReport.failed_slices` to drive a cold-storage fallback — that lives in the store path (S5-02); this story only declares the model.

## Notes for the implementer
- `RenderReport` is `[internal]` (Phase-8-internal), not a `[contract]` — but it is still frozen and `extra="forbid"`. Being internal does not relax the model discipline.
- `rendered_slices` and `failed_slices` are tuples, not sets — order is the render order and the report is a frozen record; mirror the tuple-for-frozen-collections convention.
- A `RenderReport` where the same slice appears in *both* `rendered_slices` and `failed_slices` is logically incoherent. This story is not required to validate against it (the renderer never produces it), but note it in the attempt log — S5-04 owns the renderer logic that must never produce such a report.
- One `gather_id` per `RenderReport` is correct: a render is per-gather. Do not add a per-slice gather_id here — the per-slice `gather_id` lives on `HotViewSlice` (S2-02).
- This story depends only on S2-02 (it needs `HotViewSliceName` and shares `model.py`). It has no dependency on the Supervisor or planner packages.
