# Story S7-02 — `retry_histogram` projection

**Step:** Step 7 — Projections (real, not stubs — ADR-0043 cleanliness)
**Status:** Ready
**Effort:** S
**Depends on:** S3-04 (`EventLog.read_workflow` + chain-verify); transitively S1-02 (`TrustGatePassed`/`TrustGateFailed` variants), S1-05 (`Projection` Protocol + `@register_projection`)
**ADRs honored:** ADR-0043 (real fold, not a stub), production ADR-0034 (canonical event-sourced read path)

## Context

The second of the three real Phase-9 projections. `retry_histogram` answers a single observability question: *which gate fails, and for which signal causes, and how often?* It folds the cross-workflow stream of `TrustGatePassed` + `TrustGateFailed` events into a `{(gate_id, failing_signal_kind) -> count}` histogram, plus a `{gate_id -> pass_count}` companion. The architect names this as the Phase-9 observability surface for "how often is each gate biting and why" — Phase 13's Grafana dashboard becomes a consumer ([phase-arch-design §C10](../phase-arch-design.md)).

This is a *cross-workflow* projection — unlike `audit_trail` which is per-workflow scoped, `retry_histogram` folds events from every workflow into one rollup. Per phase-arch-design open question #7, the current implementation reads via `SELECT * FROM events.events WHERE kind IN ('trust_gate_passed', 'trust_gate_failed')` rather than calling per-workflow iterators; a typed `EventLog.read_kind(...)` API may land later as ergonomics. The chain-verification *contract* is per-workflow (ADR-0003) — `retry_histogram` does NOT chain-verify; it trusts that `audit_trail` (S7-01) is the chain-verification surface and that a workflow whose chain is tampered will have its `retry_histogram` contribution be no worse than slightly stale (the architect's accepted blast-radius).

Every `TrustGate*` event carries the full signal set (`signals: dict[SignalKind, SignalValue]`) per phase-arch-design §Confidence handling. The projection folds those signals into per-gate cause histograms.

## References — where to look

- **Architecture:**
  - [`../phase-arch-design.md §C10 — Projections`](../phase-arch-design.md) — Protocol shape; "retry_histogram — GateOutcome × failing_signals rollup; folds over TrustGatePassed + TrustGateFailed"; perf envelope "fold over 10k events in <50 ms".
  - [`../phase-arch-design.md §Confidence handling`](../phase-arch-design.md) — `TrustGate*` carries `signals: dict[SignalKind, SignalValue]`; `retry_histogram` is named as the consumer.
  - [`../phase-arch-design.md §Open question 7`](../phase-arch-design.md) — `read_kind` API may land later; current implementation is `SELECT ... WHERE kind IN (...)`.
- **Phase ADRs:**
  - [`../ADRs/0003-per-workflow-blake3-prev-hash-chain.md`](../ADRs/0003-per-workflow-blake3-prev-hash-chain.md) — chain-verify is per-workflow only; cross-workflow projections do NOT chain-verify.
- **Production ADRs:**
  - [`../../../production/adrs/0034-event-sourcing-canonical-primitive.md`](../../../production/adrs/0034-event-sourcing-canonical-primitive.md).
  - [`../../../production/adrs/0043-extension-by-addition-means-no-silent-edits.md`](../../../production/adrs/0043-extension-by-addition-means-no-silent-edits.md).
- **Predecessor stories:**
  - `S1-02-event-payload-union.md` — `TrustGatePassed` / `TrustGateFailed` variants and their `signals: dict[SignalKind, SignalValue]` field shape.
  - `S1-05-projection-protocol.md` — `Projection` Protocol + `@register_projection` registry kernel.
  - `S7-01-audit-trail-projection.md` — established module layout, no-stubs fence, golden-file convention. Mirror.
- **Existing repo patterns:**
  - `src/codegenie/types/identifiers.py` — `SignalKind = NewType("SignalKind", str)` (Phase-3 S1-01).
  - `src/codegenie/probes/__init__.py` — `@register_probe` explicit-import collection precedent.

## Goal

Ship a real `retry_histogram` projection at `src/codegenie/events/projections/retry_histogram.py` that folds a cross-workflow `TrustGate*` event stream into a deterministic `{(gate_id, failing_signal_kind): count}` histogram plus a `{gate_id: pass_count}` companion, with golden-file + idempotence + skip-ahead tests proving the fold is pure, deterministic, and resumable.

## Acceptance criteria

### Module shape

- [ ] AC-1 — `src/codegenie/events/projections/retry_histogram.py` exports exactly one class `RetryHistogramProjection` decorated with `@register_projection(ProjectionId("retry_histogram"))`; module-level `__all__ = ["RetryHistogramProjection"]`.
- [ ] AC-2 — `RetryHistogramProjection` implements the `Projection` Protocol: class attribute `name: ProjectionId = ProjectionId("retry_histogram")`; method `fold(self, events: Sequence[EventPayload]) -> RetryHistogramState` is pure (no Postgres, no async IO, no logger calls inside `fold`).
- [ ] AC-3 — `RetryHistogramState` is a frozen Pydantic v2 model (`model_config = ConfigDict(frozen=True, extra="forbid")`) with fields:
  - `fail_counts: Mapping[tuple[GateId, SignalKind], int]` — keyed by `(gate_id, failing_signal)`. Use a `frozendict` (or convert to a `tuple[tuple[..., int], ...]` if no frozendict available — the model must be hashable).
  - `pass_counts: Mapping[GateId, int]` — keyed by gate.
  - `last_event_id: EventId | None` — cursor for skip-ahead.
  - `events_processed: int` — total events folded.
  - No other fields.
- [ ] AC-4 — `RetryHistogramProjection.fold` ignores events whose `kind` is not `"trust_gate_passed"` or `"trust_gate_failed"`. Test parametrizes a stream with `WorkflowStarted`, `PluginResolved`, `MergeOutcome` interleaved; the projection's counts are unchanged from a filtered stream.

### Fold semantics

- [ ] AC-5 — `TrustGatePassed(gate_id=G)` increments `pass_counts[G]` by 1 and does not touch `fail_counts`.
- [ ] AC-6 — `TrustGateFailed(gate_id=G, signals={k1: ..., k2: ...})` increments `fail_counts[(G, k)]` by 1 for **every signal key `k` whose value is `"failed"`** (or whatever the `SignalValue` "fail" discriminator is — implementer reads `SignalValue` definition; this is the architect's "full signal set → per-gate cause histograms" rendering). A single `TrustGateFailed` may increment multiple `(gate_id, signal)` cells.
- [ ] AC-7 — Ordering invariance: re-ordering events within an equal-timestamp group does NOT change the resulting state (counts are commutative). Test parametrizes a stream where two `TrustGateFailed` events share a timestamp; both orderings produce equal `RetryHistogramState`.
- [ ] AC-8 — `last_event_id` is set to the `event_id` of the **last** event in the input sequence (after sorting by `(timestamp, wf_seq)`), enabling skip-ahead resume.

### No-stubs discipline (ADR-0043)

- [ ] AC-9 — `tests/fence/test_no_projection_notimplementederror.py` (created by S7-01) is parametrized to also AST-walk `retry_histogram.py`; zero `Raise(NotImplementedError(...))` nodes.
- [ ] AC-10 — The module's `import` set is exactly `{__future__, collections, collections.abc, typing, pydantic, codegenie.events.payloads, codegenie.types.identifiers, codegenie.events.projections}` (no logger, no `psycopg`, no `asyncio`, no `blake3` — this projection does NOT chain-verify).

### Verification

- [ ] AC-11 — Golden event-stream fixture lands at `tests/golden/events/retry_histogram_stream.json` — a ~30-event stream covering: 5 `TrustGatePassed` for `recipe_correctness`, 3 `TrustGateFailed` for `recipe_correctness` (with `signals={"unit_test": "failed", "lint": "failed"}` etc.), 2 `TrustGatePassed` for `sandbox_safety`, 1 `TrustGateFailed` for `sandbox_safety` (with `signals={"sandbox_exit": "failed"}`), plus 10 unrelated events (`WorkflowStarted`, `PluginResolved`, etc.). Folding produces a byte-stable `RetryHistogramState`; golden output at `tests/golden/events/retry_histogram_stream.expected.json`.
- [ ] AC-12 — Skip-ahead cursor-recovery: `tests/unit/events/projections/test_retry_histogram_cursor_recovery.py` folds the first 15 events, records state, then folds the remaining 15 via `RetryHistogramProjection.resume_from(state, more_events)`; asserts the resumed final state equals `fold(all_30_events)`. At-least-once redelivery of the boundary event is a no-op (test re-includes event #15 in the resume slice and asserts the count is unchanged).
- [ ] AC-13 — Idempotence property: `tests/property/test_retry_histogram_idempotence.py` Hypothesis-generates `TrustGate*` streams; asserts `fold(events) == fold(events)` and `fold(events + events) == fold(events) * 2` is NOT true (re-folding the same instances should be idempotent on identity, not double-count — the projection dedupes by `event_id`). State why: at-least-once delivery means the same `event_id` may arrive twice; counts must not double-count.
- [ ] AC-14 — Replay-N-times convergence: `tests/property/test_retry_histogram_replay_convergent.py` folds the same event stream N times (N drawn from `st.integers(min_value=1, max_value=20)`); the final state is independent of N. Concretely: `fold(events) == reduce(lambda s, _: proj.resume_from(s, events), range(N), proj.fold([]))` after dedupe.
- [ ] AC-15 — Timestamp-tied ordering invariance: `tests/property/test_retry_histogram_ts_invariance.py` Hypothesis-generates a stream, shuffles within equal-timestamp groups, asserts `fold(stream) == fold(shuffle_within_equal_ts(stream))`. S7-04 generalizes this across all projections; this story ships the per-projection version.
- [ ] AC-16 — Registry membership: `ProjectionId("retry_histogram") in codegenie.events.projections._PROJECTIONS`; duplicate `@register_projection(ProjectionId("retry_histogram"))` raises `TypeError` at import.
- [ ] AC-17 — Performance smoke: `tests/unit/events/projections/test_retry_histogram_perf_smoke.py` folds a 1k-event stream in <50 ms wall-clock (loose smoke gate; S8-04 owns the 10k-event <50 ms canonical bench per phase-arch-design C10).
- [ ] AC-18 — `mypy --strict src/codegenie/events/projections/` clean; `ruff check`, `ruff format --check` clean.

## Implementation outline

1. Add `src/codegenie/events/projections/retry_histogram.py`:
   - `RetryHistogramState` frozen Pydantic model.
   - `RetryHistogramProjection` class with `name`, `fold`, `resume_from`.
   - Private `_dedupe_seen_event_ids(state, events)` helper for idempotent re-fold.
   - `@register_projection(ProjectionId("retry_histogram"))` decoration.
2. Update `src/codegenie/events/projections/__init__.py` — explicit `from .retry_histogram import RetryHistogramProjection`.
3. Add golden fixtures (`retry_histogram_stream.json`, `retry_histogram_stream.expected.json`).
4. Add unit / property / perf tests under `tests/unit/events/projections/` and `tests/property/`.
5. Extend the `tests/fence/test_no_projection_notimplementederror.py` fence's parametrization to include the new module.
6. Run `mypy --strict`, `make lint-imports`, `make check`.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file: `tests/unit/events/projections/test_retry_histogram_golden.py`

```python
from __future__ import annotations
from pathlib import Path
from codegenie.events.payloads import EventPayloadAdapter
from codegenie.events.projections.retry_histogram import RetryHistogramProjection

FIXTURE = Path(__file__).parent.parent.parent.parent / "golden/events/retry_histogram_stream.json"
EXPECTED = Path(__file__).parent.parent.parent.parent / "golden/events/retry_histogram_stream.expected.json"

def test_retry_histogram_golden_fold() -> None:
    events = EventPayloadAdapter.validate_json(FIXTURE.read_bytes())
    state = RetryHistogramProjection().fold(events)
    assert state.model_dump_json(indent=2, sort_keys=True) == EXPECTED.read_text()
```

State why it fails: `ImportError` — module doesn't exist.

Idempotence property:

```python
from hypothesis import given, strategies as st
from codegenie.events.projections.retry_histogram import RetryHistogramProjection

@given(events=trust_gate_event_streams())  # Hypothesis strategy from S1-02
def test_retry_histogram_fold_is_idempotent(events):
    proj = RetryHistogramProjection()
    assert proj.fold(events) == proj.fold(events)

@given(events=trust_gate_event_streams())
def test_retry_histogram_dedup_on_event_id(events):
    proj = RetryHistogramProjection()
    once = proj.fold(events)
    twice = proj.resume_from(once, events)  # same events again — at-least-once delivery
    assert twice == once  # dedup by event_id; counts unchanged
```

Skip-ahead cursor recovery:

```python
def test_retry_histogram_resume_equals_full_fold(golden_events):
    proj = RetryHistogramProjection()
    midpoint = len(golden_events) // 2
    first = proj.fold(golden_events[:midpoint])
    resumed = proj.resume_from(first, golden_events[midpoint:])
    full = proj.fold(golden_events)
    assert resumed == full
```

### Green — minimal pass

- Implement `RetryHistogramState` (frozen Pydantic; use `tuple[tuple[tuple[GateId, SignalKind], int], ...]` for `fail_counts` if `frozendict` unavailable — preserves frozenness).
- Implement `fold`:
  1. Filter events to `TrustGatePassed | TrustGateFailed`.
  2. Sort by `(timestamp, wf_seq, event_id)` for determinism.
  3. Dedup by `event_id` (set-based skip).
  4. Iterate and accumulate `fail_counts` / `pass_counts`.
  5. Record `last_event_id` as the final `event_id`.
- Implement `resume_from(state, more_events)`: union `state.events_seen` (a private auxiliary if exposed; otherwise re-fold by accumulating from `state` directly).
- Register via decorator; explicit import in `__init__.py`.

### Refactor

- Lift the failure-signal predicate (`SignalValue == "failed"` test) into a module-level `_is_failing_signal(v: SignalValue) -> bool` helper with a docstring naming the `SignalValue` definition.
- If `frozendict` is in `pyproject.toml`, prefer it for `Mapping` fields; otherwise the tuple-of-tuples representation is the pragmatic choice. Document the choice in a module docstring.
- Confirm zero `NotImplementedError` literal in the AST.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/events/projections/retry_histogram.py` | NEW — projection class + state model. |
| `src/codegenie/events/projections/__init__.py` | Explicit-import to populate registry. |
| `tests/golden/events/retry_histogram_stream.json` | NEW — 30-event input fixture. |
| `tests/golden/events/retry_histogram_stream.expected.json` | NEW — golden output. |
| `tests/unit/events/projections/test_retry_histogram_golden.py` | NEW — golden-file fold test. |
| `tests/unit/events/projections/test_retry_histogram_cursor_recovery.py` | NEW — skip-ahead resume test. |
| `tests/property/test_retry_histogram_idempotence.py` | NEW — replay-N-times convergence + dedup. |
| `tests/property/test_retry_histogram_ts_invariance.py` | NEW — timestamp-tied ordering invariance. |
| `tests/property/test_retry_histogram_replay_convergent.py` | NEW — fold(events) == resume(resume(... events)). |
| `tests/unit/events/projections/test_retry_histogram_perf_smoke.py` | NEW — 1k events <50 ms smoke. |
| `tests/fence/test_no_projection_notimplementederror.py` | Extend parametrization to include `retry_histogram.py`. |

## Out of scope

- **Chain-verification.** `retry_histogram` is cross-workflow and does NOT chain-verify (ADR-0003 scopes chains per-workflow). S7-01 owns chain-verify; S7-04 may add a property test that the projection is robust to a single workflow's tamper.
- **Stuck-gate alarms / SLO thresholds.** Phase 13's Grafana dashboards consume `retry_histogram` and own threshold-based alerting. This story ships only the fold.
- **`SignalKind` taxonomy expansion.** New gate signal kinds land additively via the open `SignalKind` registry (Phase-3 S1-01); this story does not enumerate them.
- **`EventLog.read_kind` API** — open question #7; current implementation uses the existing `read_workflow` iterator chained over all workflows OR direct `SELECT ... WHERE kind IN (...)`. The projection is agnostic to the source iterator shape.
- **Cross-projection property tests** — S7-04 owns the matrixed `fold(events) == fold(events)` and `fold(shuffled_within_ts) == fold(events)` tests over all three projections.

## Notes for the implementer

- **Read S7-01 first.** That story established the module layout, the no-stubs fence, the golden-file convention, the `resume_from` shape, and the `EventLogWriteCapability` threading pattern. `retry_histogram` mirrors all of those except it does NOT take an `EventLogWriteCapability` (no chain-verify → no `ChainTamperDetected` emission point).
- **Cross-workflow scope is the key shape difference vs S7-01.** `audit_trail` takes a single `workflow_id`; `retry_histogram` aggregates across workflows. This means: (a) no `workflow_id` field on the state; (b) the input stream interleaves workflow IDs freely; (c) the projection does NOT chain-verify; (d) it MUST sort deterministically because input order from `SELECT ... WHERE kind IN (...)` is server-dependent.
- **Dedup by `event_id` is the at-least-once defense.** Temporal activities are at-least-once; a single `TrustGateFailed` may emit twice if `emit_event` retries after a partial Postgres commit. The projection cannot double-count. Implementation: maintain a set of seen `event_id`s on the state (a tuple of seen-IDs is a Pydantic-frozen-friendly representation; counts are recomputed from the deduped set, NOT incremented on the fly, to preserve `fold == fold ∘ resume` equality).
- **Frozen state model is load-bearing.** AC-13 / AC-14 / AC-15 all assert `state1 == state2`. Pydantic frozen models with `Mapping` fields require canonical ordering for `__eq__` to be reliable; this story prefers tuple-of-sorted-(key, value)-pairs over `dict` to avoid hash-ordering footguns.
- **`signals: dict[SignalKind, SignalValue]` — what counts as "failing"?** Read the `SignalValue` definition (S1-02). Treat `"failed"` (the architect's example) as the failure value, but if `SignalValue` is a sum type (`Passed | Failed | Skipped`), match on the `Failed` variant. The implementer should NOT redefine "failing" — defer to the canonical type. AC-6's "every signal key whose value is failing" is the rule; document in a module docstring.
- **Performance envelope.** Phase-arch-design names "fold over 10k events in <50 ms" as the canonical SLO. AC-17's smoke is 1k events <50 ms (10× margin). S8-04's bench will exercise 10k.
- **Mirror S7-01's `last_event_id` cursor.** This is the resume seam. If the implementation chooses a different cursor key (e.g., `(timestamp, wf_seq)` tuple), document the rationale in the module docstring — the property test (AC-12) is the contract.
- **No `EventLogWriteCapability` argument.** This projection emits nothing back to the log. If a future variant grows that capability (e.g., a `RetryHistogramRolloverEmitted` event at hour boundaries), it lands additively per ADR-0043 — not by editing this module's `fold` signature.
- **Rule 11 — match S7-01's module-level conventions** (private helpers, `_PROJECTION_NAME: Final = ProjectionId("retry_histogram")` mirror, `__all__` exact set). If S7-01 diverged from this template, ALIGN to S7-01, not to this story.
