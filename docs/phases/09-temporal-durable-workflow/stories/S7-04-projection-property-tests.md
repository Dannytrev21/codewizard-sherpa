# Story S7-04 — Cross-projection property + golden tests

**Step:** Step 7 — Projections (real, not stubs — ADR-0043 cleanliness)
**Status:** Ready
**Effort:** S
**Depends on:** S7-01 (`audit_trail`), S7-02 (`retry_histogram`), S7-03 (`plugin_telemetry`); transitively S1-05 (`Projection` Protocol + `@register_projection`)
**ADRs honored:** ADR-0003 (per-workflow chain — projections respect scoping), ADR-0043 (no stubs across the registry), production ADR-0034 (canonical event-sourced read path)

## Context

The three Phase-9 projections (S7-01 audit_trail, S7-02 retry_histogram, S7-03 plugin_telemetry) each ship their own per-projection property tests. This closeout story lifts those into a **registry-driven cross-projection matrix**: every projection registered via `@register_projection` is automatically exercised by the canonical pair of property tests the architect named ([phase-arch-design §Property](../phase-arch-design.md)):

1. **Idempotence:** `fold(events) == fold(events)` — replay convergence.
2. **Timestamp-tied ordering invariance:** `fold(shuffle_within_equal_ts(events)) == fold(events)` — the projection is order-independent within an equal-timestamp group.

The story also lands the **registry-collision-at-import** test (one duplicate `@register_projection` raises `TypeError`) as a single canonical site rather than three per-projection copies, and the **golden event-stream fixture index** at `tests/golden/events/` so any new projection (Phase 11 KG writeback, Phase 13 cost ledger) lands its golden alongside the existing three.

The intent is the future-extensibility seam: when Phase 11 adds `kg_writeback_projection`, no edits to this file are needed — `@register_projection` collects it, and the parametrized matrix automatically exercises it. ADR-0043 cleanliness as a self-extending property battery.

## References — where to look

- **Architecture:**
  - [`../phase-arch-design.md §Testing strategy — Property`](../phase-arch-design.md) — the two named property tests this story implements as a matrix.
  - [`../phase-arch-design.md §C10 — Projections`](../phase-arch-design.md) — "Registry-collision-at-import raises `TypeError` at module import (same shape as `@register_probe`)".
  - [`../phase-arch-design.md §Goldens`](../phase-arch-design.md) — "One golden event stream per workflow type for the projection regression tests".
- **Phase ADRs:**
  - [`../ADRs/0003-per-workflow-blake3-prev-hash-chain.md`](../ADRs/0003-per-workflow-blake3-prev-hash-chain.md) — chain-verify is per-workflow; the timestamp-shuffle property MUST respect chain order for `audit_trail` (special-cased — see Notes).
- **Production ADRs:**
  - [`../../../production/adrs/0043-extension-by-addition-means-no-silent-edits.md`](../../../production/adrs/0043-extension-by-addition-means-no-silent-edits.md) — the registry-driven matrix is the structural defense against future stub-shaped additions.
- **Predecessor stories:**
  - `S7-01-audit-trail-projection.md` — established the golden fixture pattern, the no-stubs fence, the per-projection idempotence test (this story generalizes).
  - `S7-02-retry-histogram-projection.md` — established the cursor-recovery + dedup-by-event_id discipline; the timestamp-tied-ordering invariance property test (this story generalizes).
  - `S7-03-plugin-telemetry-projection.md` — established the `[tool.importlinter]` projection-no-Phase-8-import fence (this story does not modify it).
  - `S1-05-projection-protocol.md` — the `@register_projection` registry kernel + duplicate-collision-at-import behavior.
- **Existing repo patterns:**
  - `src/codegenie/probes/__init__.py` — `@register_probe` collision-at-import precedent (Phase 0); same shape for projections.
  - `tests/property/test_event_payload_hypothesis.py` (from S1-02) — Hypothesis strategy for `EventPayload`; this story consumes the same strategy.

## Goal

Ship a registry-driven cross-projection property + golden test battery at `tests/property/` and `tests/unit/events/projections/` that exercises every `@register_projection`-collected projection against (1) `fold(events) == fold(events)`, (2) `fold(shuffle_within_equal_ts(events)) == fold(events)`, plus a single canonical registry-collision-at-import test. Adding a new projection in a later phase requires zero edits to this story's files.

## Acceptance criteria

### Registry-driven matrix

- [ ] AC-1 — `tests/property/test_projection_idempotence.py` parametrizes over `codegenie.events.projections._PROJECTIONS.values()` (or whichever public introspection symbol the registry exposes — read S1-05); for every registered `Projection` class, asserts `proj.fold(events) == proj.fold(events)` for Hypothesis-drawn event streams. Drawn from the shared `EventPayload` Hypothesis strategy.
- [ ] AC-2 — `tests/property/test_projection_timestamp_invariance.py` parametrizes the same way and asserts `proj.fold(shuffle_within_equal_ts(events)) == proj.fold(events)`. The shuffle helper preserves order across distinct timestamps but randomizes within equal-timestamp groups.
- [ ] AC-3 — The matrix discovers projections via the registry, NOT a hardcoded list. Test asserts that the parametrize_ids enumeration `>= 3` (audit_trail, retry_histogram, plugin_telemetry) and that **adding a new `@register_projection` in a downstream test fixture causes parametrize_ids to grow by exactly one**. Concretely: a fixture-scope test `test_matrix_grows_with_new_projection` registers a no-op `IdentityProjection`, snapshots the parametrize cardinality before/after, asserts `+1`. (Cleanup deregisters.)

### Registry collision

- [ ] AC-4 — `tests/unit/events/projections/test_projection_registry_collision.py` — a single canonical test asserts that re-applying `@register_projection(ProjectionId("audit_trail"))` to a fresh class raises `TypeError` with a message naming the colliding `ProjectionId`. (Per-projection collision tests in S7-01/02/03 may be deleted in favor of this canonical test; if those stories landed individual collision tests, this story REMOVES them to avoid duplication — Rule 7 surface-conflicts-don't-average-them.)
- [ ] AC-5 — Collision discrimination: registering two different classes with **different** `ProjectionId`s does NOT raise. Parametrized over a fresh `ProjectionId("test_kg_writeback")` + a fresh `ProjectionId("test_cost_ledger")`.

### Golden index

- [ ] AC-6 — `tests/golden/events/README.md` (NEW) — a one-page index naming every golden event-stream fixture in the directory, the projection(s) that consume it, and the convention: "one workflow type → one golden stream". This is the seam Phase 10+ extends. Renders mkdocs-strict clean.
- [ ] AC-7 — Golden-stream linter `tests/fence/test_golden_event_streams_well_formed.py` — for every `*.json` in `tests/golden/events/` that does NOT end in `.expected.json`, asserts: (a) parses as `list[EventPayload]` via `EventPayloadAdapter.validate_json`; (b) all `workflow_id`s belong to the set named in `README.md`; (c) `(timestamp, wf_seq)` is monotonically non-decreasing within each workflow; (d) the matching `*.expected.json` exists.

### Timestamp-shuffle helper

- [ ] AC-8 — `tests/property/helpers/event_stream.py` (NEW) exports a pure helper `shuffle_within_equal_ts(events: Sequence[EventPayload], rng: random.Random) -> Sequence[EventPayload]` that groups by `timestamp` (UTC, microsecond resolution), shuffles within each group, returns a flat sequence. Type-strict; never raises. Deterministic given the rng seed.
- [ ] AC-9 — Helper unit test `tests/unit/property/test_event_stream_helper.py` — single-timestamp stream gets permuted; mixed-timestamp stream preserves cross-group order; empty stream returns empty.

### Special-case carve-out — audit_trail respects chain order

- [ ] AC-10 — `audit_trail`'s `fold` re-sorts by `(timestamp, wf_seq)` (S7-01 AC-4 ensures this), so the timestamp-shuffle property holds. The matrix property test does NOT exempt `audit_trail`; it relies on the projection's own re-sort discipline. If `audit_trail` were to special-case input order (it does not), this story would add a `_TIMESTAMP_INVARIANCE_EXEMPTIONS: frozenset[ProjectionId]` constant; today it MUST be the empty set. Test asserts `len(_TIMESTAMP_INVARIANCE_EXEMPTIONS) == 0` so a future contributor cannot quietly exempt a projection without surfacing it.

### Verification

- [ ] AC-11 — `mypy --strict tests/property/` (if the strict surface includes tests; if not, at minimum the new helper module under `tests/property/helpers/` passes). `ruff check`, `ruff format --check` clean.
- [ ] AC-12 — `make check` includes the new test files; CI catches a new-projection-without-property-test regression because the matrix is registry-driven (the test fails-loud if a registered projection's `fold` violates idempotence).
- [ ] AC-13 — Skip-ahead matrix: a third parametrized property test `tests/property/test_projection_cursor_recovery.py` asserts for every registered projection: `proj.resume_from(proj.fold(events[:k]), events[k:]) == proj.fold(events)` for Hypothesis-drawn `k` and `events`. Requires every projection to implement `resume_from` (S7-01/02/03 all do per their ACs). If a projection lacks `resume_from`, the test fails-loud with a structured message naming the missing method — the structural defense against silent skip-ahead-unsupported additions.

## Implementation outline

1. Add `tests/property/helpers/event_stream.py` — `shuffle_within_equal_ts` pure helper.
2. Add `tests/property/test_projection_idempotence.py` — registry-driven matrix.
3. Add `tests/property/test_projection_timestamp_invariance.py` — registry-driven matrix.
4. Add `tests/property/test_projection_cursor_recovery.py` — registry-driven `resume_from` matrix.
5. Add `tests/unit/events/projections/test_projection_registry_collision.py` — single canonical collision test (deleting per-projection duplicates in S7-01/02/03 if present — Rule 7).
6. Add `tests/golden/events/README.md` — golden index.
7. Add `tests/fence/test_golden_event_streams_well_formed.py` — golden linter.
8. Add `tests/unit/property/test_event_stream_helper.py` — helper unit tests.
9. Run `mypy --strict`, `make check`.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file: `tests/property/test_projection_idempotence.py`

```python
from __future__ import annotations
import pytest
from hypothesis import given
from hypothesis import strategies as st

from codegenie.events.projections import _PROJECTIONS  # registry-driven discovery
from codegenie.events.payloads import event_payload_strategy  # from S1-02

PROJECTIONS = list(_PROJECTIONS.values())

@pytest.mark.parametrize("projection_cls", PROJECTIONS, ids=lambda c: c.name)
@given(events=st.lists(event_payload_strategy(), max_size=100))
def test_projection_fold_is_idempotent(projection_cls, events):
    proj = projection_cls()  # noop-capability default for projections that accept one
    assert proj.fold(events) == proj.fold(events)
```

State why it fails: at story start, `_PROJECTIONS` may not yet expose iteration in the shape this test consumes; the test exposes the gap. If S1-05 already shipped iteration, this test fails because each projection's `__init__` signature varies (some take `event_log_write`; others don't) — the implementer must add a uniform default-constructor seam or a parametrize-conftest fixture that supplies the right capability per class.

Test file: `tests/property/test_projection_timestamp_invariance.py`

```python
@pytest.mark.parametrize("projection_cls", PROJECTIONS, ids=lambda c: c.name)
@given(events=st.lists(event_payload_strategy(), max_size=100), seed=st.integers())
def test_projection_timestamp_shuffle_invariance(projection_cls, events, seed):
    proj = projection_cls()
    rng = random.Random(seed)
    shuffled = shuffle_within_equal_ts(events, rng)
    assert proj.fold(shuffled) == proj.fold(events)
```

Test file: `tests/unit/events/projections/test_projection_registry_collision.py`

```python
def test_duplicate_register_projection_raises_typeerror():
    with pytest.raises(TypeError, match="audit_trail"):
        @register_projection(ProjectionId("audit_trail"))
        class _Conflicting:
            name = ProjectionId("audit_trail")
            def fold(self, events): return None
```

Test file: `tests/property/test_projection_cursor_recovery.py`

```python
@pytest.mark.parametrize("projection_cls", PROJECTIONS, ids=lambda c: c.name)
@given(events=st.lists(event_payload_strategy(), max_size=50), k=st.integers(min_value=0, max_value=50))
def test_projection_resume_equals_one_shot(projection_cls, events, k):
    if k > len(events): return
    proj = projection_cls()
    intermediate = proj.fold(events[:k])
    via_resume = proj.resume_from(intermediate, events[k:])
    via_one_shot = proj.fold(events)
    assert via_resume == via_one_shot
```

### Green — minimal pass

- Implement `shuffle_within_equal_ts` as a pure helper. Group by `timestamp`; for each group, `rng.shuffle(group)`; concat.
- Implement the registry-driven matrix tests. If S1-05's `_PROJECTIONS` is private (leading underscore), expose a public iteration helper (`iter_projections() -> Iterable[type[Projection]]`) and add the public symbol to `codegenie.events.projections.__all__`. Surgical addition; no signature changes.
- Add a `_project()` factory fixture in `tests/property/conftest.py` that constructs each projection with the right default arguments (no-op capability for `audit_trail`; no arguments for the cross-workflow projections). Keeps the parametrize cell uniform.
- Add the golden index + golden linter.

### Refactor

- If the `_project()` factory grows beyond three case-arms, surface it as a class-method `Projection.default_for_test()` Protocol method. Today three cases is below the rule-of-three threshold; inline conftest is the right shape.
- Lift the `event_payload_strategy` import to a single re-export under `tests/property/conftest.py` so future projections need not edit imports.
- Confirm `_TIMESTAMP_INVARIANCE_EXEMPTIONS` is empty (AC-10).

## Files to touch

| Path | Why |
|---|---|
| `tests/property/helpers/__init__.py` | NEW — package init for helpers. |
| `tests/property/helpers/event_stream.py` | NEW — `shuffle_within_equal_ts`. |
| `tests/property/test_projection_idempotence.py` | NEW — registry-driven matrix. |
| `tests/property/test_projection_timestamp_invariance.py` | NEW — registry-driven matrix. |
| `tests/property/test_projection_cursor_recovery.py` | NEW — registry-driven `resume_from` matrix. |
| `tests/property/conftest.py` | NEW — `_project()` factory + shared imports. |
| `tests/unit/events/projections/test_projection_registry_collision.py` | NEW — canonical collision test. |
| `tests/unit/property/test_event_stream_helper.py` | NEW — helper unit tests. |
| `tests/golden/events/README.md` | NEW — golden index page. |
| `tests/fence/test_golden_event_streams_well_formed.py` | NEW — golden linter. |
| `src/codegenie/events/projections/__init__.py` | Possibly expose `iter_projections()` if S1-05's registry symbol is private. |
| `tests/unit/events/projections/test_*_registry_collision.py` (if present from S7-01/02/03) | DELETE — consolidated here per Rule 7. |

## Out of scope

- **New projections beyond audit_trail / retry_histogram / plugin_telemetry** — Phase 11 (KG writeback) and Phase 13 (cost ledger) land additively. The matrix automatically picks them up.
- **`read_kind` API ergonomics** — open question #7; not Phase 9.
- **Phase-10 cutover canary** — handled by Phase 10's first commit per ADR-0002; not this story.
- **Projection-lag alarms** — Phase 13.5.
- **Mutation testing of projections** — `mutmut` integration is a follow-up; the architect did not name it as Phase-9 scope.
- **Performance benches** — S8-04 owns ratchet baselines. This story is correctness-only.
- **Property-test budgets** — set sensible `max_examples` defaults (100); if CI runtime becomes an issue, the budget is tunable in conftest.

## Notes for the implementer

- **Registry-driven discovery is the load-bearing design choice.** The matrix MUST iterate over the live registry at test collection time, not a hardcoded list. The fail-loud test (AC-3) is the structural defense: if a future contributor adds a projection without exercising the property contract, they cannot. ADR-0043 in test form.
- **The `_project()` factory is the uniform-construction seam.** Projections that take an `EventLogWriteCapability` (S7-01 `audit_trail`) need a no-op default; projections that take nothing (S7-02 / S7-03) construct trivially. If a future projection takes a richer constructor, the factory grows one arm. At three arms we promote to a Protocol method; at two we inline. Today inline conftest is right.
- **`shuffle_within_equal_ts` MUST be deterministic given seed.** The Hypothesis property test re-runs failing seeds; nondeterminism would mask bugs. Pass an `rng: random.Random` explicitly; do not call `random.shuffle` (module-level RNG).
- **`audit_trail` chain-verify and the timestamp-shuffle property compose correctly because the projection re-sorts on input.** If you suspect the property is failing because of chain-tamper detection on shuffled input — read S7-01 AC-4 again. The fold's first step is `events.sort(key=(timestamp, wf_seq))`. Shuffle-then-sort = sort. The property holds.
- **Rule 7 — consolidate the registry-collision test here.** If S7-01/02/03 individually shipped collision tests in their unit files, this story DELETES those duplicates and centralizes here. Pull request comment names the deletion. Per-projection collision testing is a Rule-7 "two patterns disagree" outcome — pick the more recent canonical site.
- **Skip-ahead requires every projection to expose `resume_from`.** S7-01 / S7-02 / S7-03 all do per their ACs. If any of them landed without `resume_from`, this story's AC-13 fails-loud and that story must amend. The fail-loud is intentional — projections that cannot resume cannot provide at-least-once consumer scaffolding, and at-least-once is the Temporal-activity delivery contract this whole step is paying rent for.
- **Golden index README purpose.** Engineers writing Phase 10/11/13 projections often copy an existing golden as a starting point. The README names which workflow type each fixture exemplifies (single-workflow happy path, fallback descent, HITL rejection, multi-plugin parent, etc.) so the copy-from-source choice is obvious.
- **Mirror predecessor module purity.** If S7-01/02/03 imposed module-level import-set constraints (they did; see each story's AC-10/13), the new helper module follows the same discipline. AST-walked tests do not yet exist for the helper; add to taste if Rule-11 churn surfaces.
- **Performance.** Each property test runs ≤100 examples × 3 projections = 300 folds per test; budget under 30 s total at `max_examples=100`. If slow, lower budget or shrink `max_size` on event-list strategy.
- **What this story does NOT do.** It does not change `audit_trail` / `retry_histogram` / `plugin_telemetry` behavior. It does not add new projections. It does not change `EventPayload`. It is correctness-of-the-fold-contract, expressed as a registry-driven matrix that any future projection auto-satisfies-or-fails-loudly.
