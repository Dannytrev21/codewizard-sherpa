# Story S7-01 — `audit_trail` projection + chain-verify on fold

**Step:** Step 7 — Projections (real, not stubs — ADR-0043 cleanliness)
**Status:** Ready
**Effort:** M
**Depends on:** S1-02 (21-variant `EventPayload` union), S3-04 (`EventLog.read_workflow` + chain-verify)
**ADRs honored:** ADR-0003 (per-workflow BLAKE3 prev-hash chain), ADR-0006 (`@critical_event` synchronous-flush vocabulary — `ChainTamperDetected` is one of the five), ADR-0043 (extension by addition — no `NotImplementedError` stubs), production ADR-0034 (event-sourcing canonical primitive)

## Context

Phase 9 ships three real projections (zero stubs) off the canonical event log. `audit_trail` is the first and the load-bearing one: it is the projection the architect named as the chain-verify enforcement point — projections halt loudly on tamper rather than reading suspect rows ([phase-arch-design §C10](../phase-arch-design.md), [Edge case 8](../phase-arch-design.md)). It also pays the [ADR-0043](../../../production/adrs/0043-extension-by-addition-means-no-silent-edits.md) rent that earned Phase 9 the right to delete the Phase-13 `cost_ledger_v1` stub: every Phase-9 projection is a real fold that produces a real value with a real test, not a `raise NotImplementedError("Phase 13")`.

The fold is pure: `audit_trail(workflow_id)` reads `events.events` rows for that workflow via `EventLog.read_workflow` and returns a chronologically-ordered list of typed `EventPayload`s. The verification work happens *at fold time*: as each row streams in, the projection re-computes `BLAKE3(prev_row_hash || canonical_payload)` and asserts equality with the stored `row_hash`; a mismatch or gap emits `ChainTamperDetected` (a `@critical_event`, sync-flushed) and halts further folding for that workflow. Per-workflow chain scoping (ADR-0003) means tamper blast radius is exactly one workflow's projection — other workflows' `audit_trail` calls remain valid.

## References — where to look

- **Architecture:**
  - [`../phase-arch-design.md §C10 — Projections`](../phase-arch-design.md) — Protocol shape, the three projections, perf envelope (`audit_trail(workflow_id)` reads ~12 events in <5 ms), chain-verify failure mode.
  - [`../phase-arch-design.md §C9 — EventLog`](../phase-arch-design.md) — `read_workflow(workflow_id) -> AsyncIterator[EventPayload]` shape, BLAKE3 chain semantics.
  - [`../phase-arch-design.md §Logical view`](../phase-arch-design.md) — the `Projection` class block (line 185).
  - [`../phase-arch-design.md §Edge case 8`](../phase-arch-design.md) — "per-workflow chain break: prev_hash mismatch on next read; `audit_trail` projection's chain-verify on each row; `ChainTamperDetected` (`@critical_event`) emitted; projections halt for the affected workflow".
- **Phase ADRs:**
  - [`../ADRs/0003-per-workflow-blake3-prev-hash-chain.md`](../ADRs/0003-per-workflow-blake3-prev-hash-chain.md) — per-workflow scoping, why chain-verify happens at read time.
  - [`../ADRs/0006-critical-event-synchronous-flush-vocabulary.md`](../ADRs/0006-critical-event-synchronous-flush-vocabulary.md) — `ChainTamperDetected` is one of the five sync-flush variants.
- **Production ADRs:**
  - [`../../../production/adrs/0034-event-sourcing-canonical-primitive.md`](../../../production/adrs/0034-event-sourcing-canonical-primitive.md) — projections as the read path.
  - [`../../../production/adrs/0043-extension-by-addition-means-no-silent-edits.md`](../../../production/adrs/0043-extension-by-addition-means-no-silent-edits.md) — zero stubs, every projection is real.
- **Predecessor stories (READ BEFORE WRITING — Rule 8):**
  - `S1-02-event-payload-union.md` — the 21-variant `EventPayload` and `EventPayloadAdapter`; the projection consumes these typed instances.
  - `S1-05-projection-protocol.md` — the `Projection` Protocol + `@register_projection` registry kernel this story instantiates.
  - `S3-01-event-log-append-chain.md` — how `row_hash = BLAKE3(prev_row_hash || canonical_payload)` is computed at append time.
  - `S3-04-event-log-read-chain-verify.md` — the `read_workflow` iterator + the `ChainTamperDetected` emission point this story consumes.
- **Existing repo patterns to mirror:**
  - `src/codegenie/types/identifiers.py` — `ProjectionId = NewType("ProjectionId", str)` shape (added in S1-01).
  - `src/codegenie/probes/__init__.py` — `@register_probe` explicit-import collection precedent; `@register_projection` follows the same shape.

## Goal

Ship a real `audit_trail` projection at `src/codegenie/events/projections/audit_trail.py` that folds `EventLog.read_workflow(workflow_id)` into a chronologically-ordered typed event list, chain-verifies each row against the stored BLAKE3 prev-hash, emits `ChainTamperDetected` on mismatch, and halts folding for that workflow without ever raising `NotImplementedError`.

## Acceptance criteria

### Module shape

- [ ] AC-1 — `src/codegenie/events/projections/audit_trail.py` exports exactly one class `AuditTrailProjection` decorated with `@register_projection(ProjectionId("audit_trail"))`; module-level `__all__ = ["AuditTrailProjection"]`.
- [ ] AC-2 — `AuditTrailProjection` implements the `Projection` Protocol from `codegenie.events.projections`: class attribute `name: ProjectionId = ProjectionId("audit_trail")`; method `fold(self, events: Sequence[EventPayload]) -> AuditTrailState` is pure (no Postgres, no async IO inside `fold`).
- [ ] AC-3 — `AuditTrailState` is a frozen Pydantic v2 model (`model_config = ConfigDict(frozen=True, extra="forbid")`) with fields `workflow_id: WorkflowId | None`, `events: tuple[EventPayload, ...]` (tuple, not list — frozenness), `halted: bool`, `halt_reason: ChainTamperDetected | None`. No other fields.
- [ ] AC-4 — `AuditTrailProjection.fold` returns the events in monotonically-non-decreasing `(timestamp, wf_seq)` order; the test parametrizes a stream with reversed timestamps and asserts the projection re-orders them deterministically.

### Chain verification

- [ ] AC-5 — `fold` re-computes `row_hash = BLAKE3(prev_row_hash || canonical_payload(event))` for every event using the same canonicalization (`EventPayloadAdapter.dump_json(..., by_alias=True, exclude_none=False)`) as `EventLog.append`; mismatch → `halted=True`, `halt_reason = ChainTamperDetected(...)`, and **no further events are included in the returned state**.
- [ ] AC-6 — A chain gap (`wf_seq` jumps from N to N+2 with no row at N+1) is detected and emits `ChainTamperDetected` with `gap_at_wf_seq=N+1`; the test asserts gap detection independently of hash-mismatch detection.
- [ ] AC-7 — `ChainTamperDetected` is emitted via the threaded `EventLogWriteCapability` passed to `__init__`; the projection itself does not import `codegenie.events.log` (the capability is the one-arg seam — same shape as Phase-3 `ApplyContext`). Test asserts the capability was invoked exactly once with the tamper event.
- [ ] AC-8 — Cross-workflow scoping: if the input event stream interleaves rows from `workflow_id=A` and `workflow_id=B`, `fold` raises `ValueError("audit_trail folds a single workflow at a time")` — the projection refuses ambiguous input rather than silently slicing.

### No-stubs discipline (ADR-0043)

- [ ] AC-9 — `tests/fence/test_no_projection_notimplementederror.py` AST-walks `src/codegenie/events/projections/audit_trail.py` and asserts zero `Raise(NotImplementedError(...))` nodes anywhere in the module. (The fence file is created by this story; later projection stories extend its parametrization.)
- [ ] AC-10 — The module's `import` set is exactly `{__future__, collections.abc, typing, pydantic, blake3, codegenie.events.payloads, codegenie.types.identifiers, codegenie.durable.capabilities, codegenie.events.projections}` (no logger, no `psycopg`, no `asyncio`). Mirrors the S1-01 module-purity discipline.

### Verification

- [ ] AC-11 — Golden event-stream fixture lands at `tests/golden/events/audit_trail_happy_workflow.json` — a ~12-event stream covering `WorkflowStarted → PluginResolved → BundleBuilt → RouteDecided → RecipeApplied → PatchApplied → TrustGatePassed → PrOpened → HumanReviewRequested → HumanReviewDecision → MergeOutcome → WorkflowCompleted`. Folding it produces a byte-stable `AuditTrailState` JSON (test compares `AuditTrailState.model_dump_json()` against a checked-in golden output `tests/golden/events/audit_trail_happy_workflow.expected.json`).
- [ ] AC-12 — Integration test `tests/integration/test_audit_trail_chain_verify.py` writes 12 events for a workflow via the real `EventLog`, then via `migrations_role` forges a poisoned row (mutates one row's `payload`), then folds `audit_trail(workflow_id)` and asserts (a) `halted=True`, (b) `halt_reason.kind == "chain_tamper_detected"`, (c) the capability emitted exactly one `ChainTamperDetected` to the event log.
- [ ] AC-13 — Skip-ahead cursor-recovery: `tests/unit/events/projections/test_audit_trail_cursor_recovery.py` folds the first 6 events of the golden stream, records the projection state, then folds the remaining 6 events starting from that state via a `AuditTrailProjection.resume_from(state, events) -> AuditTrailState` method; asserts the resumed final state equals `AuditTrailProjection.fold(all_12_events)`. Validates idempotent-consumer scaffolding (cursor + checkpoint, at-least-once delivery — re-folding the boundary event N+1 is a no-op).
- [ ] AC-14 — Idempotence property: `tests/property/test_audit_trail_idempotence.py` Hypothesis-generates EventPayload streams; asserts `AuditTrailProjection().fold(events) == AuditTrailProjection().fold(events)` for any valid stream (replay N times → convergent state).
- [ ] AC-15 — Registry membership: `ProjectionId("audit_trail") in codegenie.events.projections._PROJECTIONS` (parametrized fixture); duplicate `@register_projection(ProjectionId("audit_trail"))` raises `TypeError` at import.
- [ ] AC-16 — Performance smoke: `tests/unit/events/projections/test_audit_trail_perf_smoke.py` (no `-m bench`) folds a 100-event stream in <50 ms wall-clock on the contributor laptop; this is a smoke gate, not the canonical bench (S8-04 owns ratchet baselines).
- [ ] AC-17 — `mypy --strict src/codegenie/events/projections/` clean; `ruff check`, `ruff format --check` clean on touched files.
- [ ] AC-18 — `make lint-imports` green; the projection module does not import `codegenie.plugins.events` (the S7-03 fence catches this, but this story must not violate it).

## Implementation outline

1. Add `src/codegenie/events/projections/audit_trail.py`:
   - `AuditTrailState` frozen Pydantic model.
   - `AuditTrailProjection` class with `name: ProjectionId` + `fold` + `resume_from`.
   - Private `_verify_row(prev_hash, event)` helper returning `(new_hash, ok)`.
   - Threaded `event_log_write: EventLogWriteCapability` constructor argument.
   - `@register_projection(ProjectionId("audit_trail"))` decoration.
2. Update `src/codegenie/events/projections/__init__.py` — explicit `from .audit_trail import AuditTrailProjection` import to populate the registry.
3. Add `tests/golden/events/audit_trail_happy_workflow.json` (input) + `audit_trail_happy_workflow.expected.json` (output) — both checked in.
4. Add `tests/integration/test_audit_trail_chain_verify.py` (testcontainers PG; mirrors S3-04 test layout).
5. Add `tests/unit/events/projections/test_audit_trail_*.py` (golden, cursor recovery, property, perf smoke).
6. Add `tests/fence/test_no_projection_notimplementederror.py` (AST walker; one parametrized file for S7-01, S7-02, S7-03 extend it).
7. Run `mypy --strict`, `make lint-imports`, `make check` locally.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file: `tests/unit/events/projections/test_audit_trail_golden.py`

```python
from __future__ import annotations
from pathlib import Path
from codegenie.events.payloads import EventPayloadAdapter
from codegenie.events.projections.audit_trail import AuditTrailProjection
from codegenie.durable.capabilities import EventLogWriteCapability

FIXTURE = Path(__file__).parent.parent.parent.parent / "golden/events/audit_trail_happy_workflow.json"
EXPECTED = Path(__file__).parent.parent.parent.parent / "golden/events/audit_trail_happy_workflow.expected.json"

def test_audit_trail_golden_fold(noop_event_log_write: EventLogWriteCapability) -> None:
    events = EventPayloadAdapter.validate_json(FIXTURE.read_bytes())  # list[EventPayload]
    state = AuditTrailProjection(event_log_write=noop_event_log_write).fold(events)
    assert state.model_dump_json(indent=2) == EXPECTED.read_text()
```

State why it fails: `ImportError` — `codegenie.events.projections.audit_trail` and `AuditTrailProjection` don't exist yet. Plus the golden expected file is missing.

Add the chain-tamper test:

```python
def test_audit_trail_halts_on_chain_mismatch(forged_event_stream, recording_capability):
    state = AuditTrailProjection(event_log_write=recording_capability).fold(forged_event_stream)
    assert state.halted is True
    assert state.halt_reason is not None
    assert state.halt_reason.kind == "chain_tamper_detected"
    assert len(recording_capability.emitted) == 1
    assert recording_capability.emitted[0].kind == "chain_tamper_detected"
```

Add the cursor-recovery test:

```python
def test_audit_trail_resume_equals_full_fold(golden_events, noop_event_log_write):
    proj = AuditTrailProjection(event_log_write=noop_event_log_write)
    first_half = proj.fold(golden_events[:6])
    full_via_resume = proj.resume_from(first_half, golden_events[6:])
    full_via_one_shot = proj.fold(golden_events)
    assert full_via_resume == full_via_one_shot
```

### Green — minimal pass

- Implement `AuditTrailState` (frozen Pydantic).
- Implement `AuditTrailProjection.fold`: iterate `events`, sort by `(timestamp, wf_seq)`, recompute prev-hash chain (use `blake3` directly — the same library `EventLog.append` uses), build the `events` tuple, return `AuditTrailState(workflow_id=..., events=tuple(verified), halted=False, halt_reason=None)`.
- On mismatch/gap: stop iteration, populate `halt_reason`, set `halted=True`, invoke `event_log_write(ChainTamperDetected(...))`, return the partial state.
- Implement `resume_from(state, more_events)`: chain from `state.events[-1]`'s row_hash; otherwise mechanically identical to `fold`.
- Register via `@register_projection`.

### Refactor

- Extract `_canonical_payload_bytes(event)` shared helper if the test file diverges from `EventLog.append`'s canonicalization — but prefer importing the existing helper from `codegenie.events.log` (read-only; this avoids the projection re-implementing canonicalization, which would be a Rule-7 fork). If `codegenie.events.log` doesn't yet expose it as a public symbol, this story adds the export.
- Lift the sort key `(timestamp, wf_seq)` into a module-level `_SORT_KEY` `Final` constant with a docstring naming ADR-0003.
- Confirm zero `NotImplementedError` literal in the AST (the fence test enforces this).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/events/projections/audit_trail.py` | NEW — projection class + state model. |
| `src/codegenie/events/projections/__init__.py` | Explicit-import the new module; registry collects on import. |
| `tests/golden/events/audit_trail_happy_workflow.json` | NEW — 12-event input fixture. |
| `tests/golden/events/audit_trail_happy_workflow.expected.json` | NEW — golden output. |
| `tests/unit/events/projections/test_audit_trail_golden.py` | NEW — golden-file fold test. |
| `tests/unit/events/projections/test_audit_trail_cursor_recovery.py` | NEW — skip-ahead/resume test. |
| `tests/property/test_audit_trail_idempotence.py` | NEW — Hypothesis idempotence. |
| `tests/integration/test_audit_trail_chain_verify.py` | NEW — testcontainers PG; forged row → halt + ChainTamperDetected. |
| `tests/fence/test_no_projection_notimplementederror.py` | NEW — AST fence; ADR-0043 cleanliness. |
| `tests/unit/events/projections/test_audit_trail_perf_smoke.py` | NEW — sub-50 ms smoke gate. |
| `src/codegenie/events/log.py` | Possibly export `_canonical_payload_bytes` (read-only) if needed to share canonicalization with the projection. |

## Out of scope

- **`retry_histogram` projection** — handled by S7-02.
- **`plugin_telemetry` projection + Phase-8 log fanout** — handled by S7-03.
- **Cross-projection property tests** (idempotence + timestamp-tied invariance over all three) — handled by S7-04. This story ships an idempotence test only for `audit_trail`; S7-04 generalizes.
- **`EventLog.read_kind` API** — open question #7 (architect); not required here. `audit_trail` consumes per-workflow streams via the existing `read_workflow`.
- **Continue-as-new / projection-lag alarms** — not Phase 9. The architect notes projection-lag UI lands in Phase 13.5 ([phase-arch-design.md Edge case 12](../phase-arch-design.md)).
- **Phase 10 `vuln.provenance` projection** — additive new file; ADR-0034.
- **Phase 11/13 projections** — additive in later phases; this story commits to *not* shipping `cost_ledger_v1` or `kg_writeback` stubs.

## Notes for the implementer

- **ADR-0043 cleanliness is the load-bearing AC.** The critic specifically destroyed the "ship a `cost_ledger_v1` projection that raises `NotImplementedError`" alternative on Critic-5 ([phase-arch-design Non-goals](../phase-arch-design.md)). The AST fence test (AC-9) is the structural defense; do not be tempted to add `raise NotImplementedError("see Phase 13")` anywhere in the projection module just to satisfy a not-yet-implemented branch — refactor the branch out.
- **`fold` is pure; the capability is the impure seam.** The mistake to avoid: invoking `event_log_write` from inside `fold`'s body in a way that makes the function untestable without a real EventLog. Pattern: pass a recording test double that captures calls; assert against the captured list. Same shape as Phase-3 `ApplyContext.event_log_emit`.
- **Per-workflow scoping is load-bearing.** The chain is per-workflow (ADR-0003) — folding a stream that mixes workflows would compute a meaningless chain. AC-8 makes the cross-workflow input case an explicit `ValueError`, not silent slicing. Phase 10's `vuln.provenance` projection will be cross-workflow; that's a *different* projection with a *different* chain discipline.
- **Canonicalization must match `EventLog.append`.** If the projection re-implements `EventPayloadAdapter.dump_json(...)` with different `by_alias`/`exclude_none` flags than the append path, every hash mismatch is a false positive. Read `src/codegenie/events/log.py` first (S3-01 ships it) and share the helper. If S3-01 made the helper private, this story may surface a public re-export — that's a Rule-7-sized refactor, not a fork.
- **`ChainTamperDetected` is a `@critical_event` (sync flush).** The projection's invocation of `event_log_write(ChainTamperDetected(...))` MUST go through the synchronous path; the projection itself does not own that decision — the `EventLog` does. The projection just hands the event over.
- **`resume_from` is the cursor-recovery seam.** At-least-once delivery means the boundary event may be re-folded; the test (AC-13) asserts that re-folding is a no-op when the resume state already includes that event. Implementation: dedupe by `event_id` at the resume boundary.
- **Golden file canonicalization.** Use `model_dump_json(indent=2)` with sorted keys so the golden file is diff-stable across Python minor versions. Commit a `.gitattributes` `eol=lf` entry on the golden files if not already present (likely yes — Phase 0).
- **Property-test budget.** Hypothesis can synthesize EventPayload instances (S1-02 ships the Hypothesis strategies). Use `max_examples=100` for the idempotence test; this story's perf smoke (AC-16) is separate from S8-04's ratchet bench.
- **Performance envelope context.** Phase-arch-design names "~12 events in <5 ms" for `audit_trail(workflow_id)` — that's the production SLO. AC-16's <50 ms is a smoke gate against catastrophic regressions; S8-04 will ratchet the real budget.
- **Rule 8 — `EventLog.read_workflow` already chain-verifies on read** (S3-04). Why also re-verify here? Defense in depth — projections may be folded over event streams sourced from anywhere (golden fixtures, snapshots, replicated read-stores in future phases). The projection cannot assume the source already verified. The S3-04 verification is the per-row hot path; this story's verification is the projection's own correctness contract.
