# Story S7-03 — `plugin_telemetry` projection + Phase-8 log fanout

**Step:** Step 7 — Projections (real, not stubs — ADR-0043 cleanliness)
**Status:** Ready
**Effort:** M
**Depends on:** S3-04 (`EventLog.read_workflow` + chain-verify); transitively S1-02 (`PluginResolved` / `BundleBuilt` / `RouteDecided` / `MergeOutcome` variants), S1-05 (`Projection` Protocol + `@register_projection`), S4-05 (`run_vuln_subgraph` activity — the forward-emit site)
**ADRs honored:** ADR-0002 (Phase-8 `codegenie.plugins.events` → canonical event log cutover; strangler-fig with explicit 30-day-drain termination), ADR-0043 (real fold; no stubs), production ADR-0034 (canonical event-sourced read path)

## Context

The third real Phase-9 projection. `plugin_telemetry` joins `PluginResolved` (from the Phase-8 Supervisor's resolve node) with `MergeOutcome` (from the workflow's terminal HITL signal) per workflow, producing a per-plugin `{plugin_id -> {resolved: int, merged: int, fallback: int}}` rollup. This is the projection role the Phase-8 internal log (`codegenie.plugins.events`) filled for plugin-level decisions; now it lives off the canonical log so Phase 10 can delete the Phase-8 log on its first commit ([ADR-0002](../ADRs/0002-phase-8-plugin-events-log-cutover-to-canonical-event-log.md)).

Two distinct concerns ride together in this story because they form the strangler-fig pattern:

1. **The projection itself** — a pure fold over `PluginResolved` + `MergeOutcome` events; cross-workflow scoped (no chain-verify); registered via `@register_projection(ProjectionId("plugin_telemetry"))`. Mirrors S7-01/S7-02's shape.

2. **The Phase-8 → canonical log forward-emitter** — Phase 8's `codegenie.plugins.events` log keeps running unchanged inside `run_vuln_subgraph` (ADR-0002 explicitly preserves it for the 30-day-drain window). The new contribution from this story: `run_vuln_subgraph` emits `PluginResolved` / `BundleBuilt` / `RouteDecided` events **forward** into the canonical log via the `emit_event` activity. This is the one-way emitter the architect named in [phase-arch-design Step 7 risks](../phase-arch-design.md). A byte-identity test asserts the forward-emitted canonical record matches the corresponding Phase-8 internal record so projections cannot diverge during the drain.

The structural defense against accidental coupling: **no projection module may import `codegenie.plugins.events`**. The canonical log is the only source the projections consume. A new `import-linter` contract enforces this.

## References — where to look

- **Architecture:**
  - [`../phase-arch-design.md §C10 — Projections`](../phase-arch-design.md) — "`plugin_telemetry` — `PluginResolved × MergeOutcome` join for per-plugin merge / fallback rates; replaces the projection role the Phase-8 plugin-events log filled".
  - [`../phase-arch-design.md §Risks specific to Step 7`](../phase-arch-design.md) — the architect's explicit warning: "The Phase-8 log fanout invites silent double-recording or silent miss; … Add a fence that no projection imports `codegenie.plugins.events`."
  - [`../phase-arch-design.md §Integration with Phase 10`](../phase-arch-design.md) — Phase 10's first commit deletes the Phase-8 log; 30-day drain; canary precondition.
  - [`../phase-arch-design.md §Non-goals — Parallel-running Phase-8 log indefinitely`](../phase-arch-design.md) — Phase 9 ships a one-way emitter; deletion is Phase 10.
- **Phase ADRs:**
  - [`../ADRs/0002-phase-8-plugin-events-log-cutover-to-canonical-event-log.md`](../ADRs/0002-phase-8-plugin-events-log-cutover-to-canonical-event-log.md) — strangler-fig cutover discipline; this story implements the "one-way forward emit" decision.
- **Production ADRs:**
  - [`../../../production/adrs/0034-event-sourcing-canonical-primitive.md`](../../../production/adrs/0034-event-sourcing-canonical-primitive.md).
  - [`../../../production/adrs/0043-extension-by-addition-means-no-silent-edits.md`](../../../production/adrs/0043-extension-by-addition-means-no-silent-edits.md).
- **Predecessor stories:**
  - `S1-02-event-payload-union.md` — `PluginResolved`, `BundleBuilt`, `RouteDecided`, `MergeOutcome` variants.
  - `S1-05-projection-protocol.md` — Protocol + registry.
  - `S4-05-run-vuln-subgraph-activity.md` — the fat activity that wraps the Phase-6 LangGraph; the forward-emitter lands here.
  - `S4-02-system-queue-activities.md` — `emit_event` is the activity called by the forward-emitter.
  - `S7-01-audit-trail-projection.md`, `S7-02-retry-histogram-projection.md` — module layout, golden-file convention, no-stubs fence (extended here), cursor-recovery test pattern. Mirror.
- **Existing Phase-8 code (READ BEFORE WRITING — Rule 8):**
  - `src/codegenie/plugins/events.py` (or wherever Phase 8 lands the internal log — check Phase 8 stories' GREEN status as of 2026-05). The byte-identity test must read from this log; do not modify its append path.
- **Pre-commit / lint config:**
  - `pyproject.toml § [tool.importlinter]` — contracts shape; this story adds one.

## Goal

Ship (1) a real `plugin_telemetry` projection at `src/codegenie/events/projections/plugin_telemetry.py` folding `PluginResolved × MergeOutcome` into per-plugin merge / fallback rates, (2) a one-way forward-emitter from `run_vuln_subgraph` into the canonical event log for `PluginResolved` / `BundleBuilt` / `RouteDecided`, (3) a byte-identity test against the Phase-8 internal log, and (4) the `import-linter` fence forbidding any projection from importing `codegenie.plugins.events`.

## Acceptance criteria

### Projection module shape

- [ ] AC-1 — `src/codegenie/events/projections/plugin_telemetry.py` exports exactly one class `PluginTelemetryProjection` decorated with `@register_projection(ProjectionId("plugin_telemetry"))`; module-level `__all__ = ["PluginTelemetryProjection"]`.
- [ ] AC-2 — `PluginTelemetryProjection` implements `Projection`: `name: ProjectionId`, `fold(self, events: Sequence[EventPayload]) -> PluginTelemetryState` is pure.
- [ ] AC-3 — `PluginTelemetryState` is a frozen Pydantic v2 model (`model_config = ConfigDict(frozen=True, extra="forbid")`) with fields:
  - `per_plugin: Mapping[PluginId, PluginTelemetryRow]` (or tuple-of-pairs for frozen-Mapping discipline).
  - `last_event_id: EventId | None`.
  - `events_processed: int`.
  - Where `PluginTelemetryRow` is itself a frozen model with fields `resolved: int`, `merged: int`, `fallback: int`, `failed: int`.
- [ ] AC-4 — Fold semantics:
  - `PluginResolved(plugin_id=P)` increments `per_plugin[P].resolved`.
  - `MergeOutcome(plugin_id=P, outcome="merged")` (or whatever the `MergeOutcome.outcome` discriminator literals are — read S1-02) increments `per_plugin[P].merged`.
  - `MergeOutcome(plugin_id=P, outcome="rejected" | "failed")` increments `per_plugin[P].failed`.
  - A `RouteDecided` carrying `routed_to_fallback=True` (or whichever field signals tier-descent — read S1-02) increments `per_plugin[P].fallback`. If `RouteDecided` does not carry plugin_id directly, the fold joins on `workflow_id` with the most recent `PluginResolved` for that workflow.
- [ ] AC-5 — Cross-workflow scoped; the projection does NOT chain-verify (per-workflow chain is S7-01's surface — ADR-0003).
- [ ] AC-6 — Events whose `kind` is not in `{plugin_resolved, merge_outcome, route_decided}` are ignored. Filtered-stream invariance test parametrizes interleaved unrelated events.
- [ ] AC-7 — Dedup by `event_id` (at-least-once delivery defense; mirrors S7-02 AC-13).

### Forward-emitter from `run_vuln_subgraph`

- [ ] AC-8 — `src/codegenie/durable/activities/run_vuln_subgraph.py` (S4-05's module) is extended with a thin forward-emitter call: every time the inner Phase-8 Supervisor logs `PluginResolved` / `BundleBuilt` / `RouteDecided` to `codegenie.plugins.events`, the activity also invokes `execute_activity("emit_event", canonical_payload)` (or the in-process `EventLog.append` helper if the architectural seam allows — read S4-05). The forward-emit is **one-way**: the canonical log never writes back into `codegenie.plugins.events`.
- [ ] AC-9 — `tests/integration/test_phase08_log_fanout.py` runs a real `run_vuln_subgraph` through one workflow case (cassette LLM, fake Redis, testcontainers PG) and asserts: for each Phase-8 internal log record of kind `PluginResolved` / `BundleBuilt` / `RouteDecided`, there exists a byte-identical record in `events.events` (canonical log) — same `plugin_id`, same digests, same timestamp (within Temporal's clock resolution), same `correlation_id`. Byte-identity is verified via canonical-payload JSON serialization on both sides.
- [ ] AC-10 — Negative coverage: a deliberately-broken forward-emitter (mocked to skip emission of `BundleBuilt`) fails the byte-identity test loudly with a structured error naming the missing kind. This is the regression catch — engineers cannot silently add new Phase-8-only events without the fanout.

### Structural fence — no projection imports `codegenie.plugins.events`

- [ ] AC-11 — `pyproject.toml § [tool.importlinter]` gets a new contract `codegenie.events.projections-must-not-import-phase8-log`: forbids any module under `codegenie.events.projections.*` from importing `codegenie.plugins.events` (or any submodule thereof).
- [ ] AC-12 — A deliberate-violation xfail fixture `tests/fence/fixtures/projection_imports_phase8_log/__init__.py` contains a module that imports `codegenie.plugins.events`; `tests/fence/test_projection_no_phase8_import.py` runs `import-linter` and asserts the fixture fails, proving the contract bites.
- [ ] AC-13 — The `plugin_telemetry` module's actual `import` set (AST-walked) is exactly `{__future__, collections, collections.abc, typing, pydantic, codegenie.events.payloads, codegenie.types.identifiers, codegenie.events.projections}` — no `codegenie.plugins.events`, no `psycopg`.

### No-stubs discipline (ADR-0043)

- [ ] AC-14 — `tests/fence/test_no_projection_notimplementederror.py` parametrization is extended to include `plugin_telemetry.py`; zero `Raise(NotImplementedError(...))` nodes.

### Verification

- [ ] AC-15 — Golden event-stream fixture lands at `tests/golden/events/plugin_telemetry_stream.json` — ~40 events across 3 workflows × 3 plugins covering happy path, fallback descent, and rejection. Folding produces a byte-stable `PluginTelemetryState` at `tests/golden/events/plugin_telemetry_stream.expected.json`.
- [ ] AC-16 — Skip-ahead cursor-recovery: `tests/unit/events/projections/test_plugin_telemetry_cursor_recovery.py` — split golden stream at the midpoint; resume from midpoint; assert resumed state equals one-shot fold. Boundary-event re-fold is a no-op (dedup by `event_id`).
- [ ] AC-17 — Idempotence property: `tests/property/test_plugin_telemetry_idempotence.py` Hypothesis-generates streams; `fold(events) == fold(events)`; `resume_from(fold(events), events) == fold(events)`.
- [ ] AC-18 — Replay-N-times convergence: folding the same stream N times via repeated `resume_from` converges to the same state as one-shot `fold`. Mirrors S7-02 AC-14.
- [ ] AC-19 — Registry membership: `ProjectionId("plugin_telemetry") in codegenie.events.projections._PROJECTIONS`; duplicate `@register_projection` raises `TypeError` at import.
- [ ] AC-20 — `mypy --strict src/codegenie/events/projections/` clean; `ruff check`, `ruff format --check` clean; `make lint-imports` green (new contract + the existing `codegenie.durable.workflows-must-be-pure`).

## Implementation outline

1. Add `src/codegenie/events/projections/plugin_telemetry.py` with `PluginTelemetryState`, `PluginTelemetryRow`, `PluginTelemetryProjection`. Mirror S7-01/S7-02 layout.
2. Update `src/codegenie/events/projections/__init__.py` — explicit `from .plugin_telemetry import PluginTelemetryProjection`.
3. Extend `src/codegenie/durable/activities/run_vuln_subgraph.py` with the forward-emitter:
   - Wrap (don't modify) the existing Phase-8 internal log call.
   - Translate the Phase-8 log record into the canonical `EventPayload` variant.
   - Call `execute_activity("emit_event", canonical_payload, ...)` (or use the EventLog injection point S4-05 established).
4. Add `pyproject.toml § [tool.importlinter]` contract.
5. Add fences: `tests/fence/test_projection_no_phase8_import.py` + the xfail fixture.
6. Add golden fixtures (input + expected).
7. Add unit / property / integration tests under `tests/unit/events/projections/`, `tests/property/`, `tests/integration/`.
8. Extend `tests/fence/test_no_projection_notimplementederror.py` parametrization.
9. Run `mypy --strict`, `make lint-imports`, `make check`.

## TDD plan — red / green / refactor

### Red — write the failing test first

Three red tests; all fail with `ImportError` initially.

Test 1 — golden fold (mirror S7-01/S7-02):

```python
from pathlib import Path
from codegenie.events.payloads import EventPayloadAdapter
from codegenie.events.projections.plugin_telemetry import PluginTelemetryProjection

FIXTURE = Path(__file__).parents[3] / "golden/events/plugin_telemetry_stream.json"
EXPECTED = Path(__file__).parents[3] / "golden/events/plugin_telemetry_stream.expected.json"

def test_plugin_telemetry_golden_fold():
    events = EventPayloadAdapter.validate_json(FIXTURE.read_bytes())
    state = PluginTelemetryProjection().fold(events)
    assert state.model_dump_json(indent=2, sort_keys=True) == EXPECTED.read_text()
```

Test 2 — byte-identity fanout:

```python
def test_phase8_log_fanout_byte_identical(temporal_dev_server, real_postgres, cassette_llm):
    # Run one workflow case end-to-end via TemporalVulnRemediationSut.
    result = run_one_canonical_case(case="lodash-cve-2019-10744")
    phase8_records = read_phase8_log(workflow_id=result.workflow_id)
    canonical_records = read_canonical_log(
        workflow_id=result.workflow_id,
        kinds=["plugin_resolved", "bundle_built", "route_decided"],
    )
    assert len(phase8_records) == len(canonical_records)
    for p8, can in zip(phase8_records, canonical_records, strict=True):
        assert canonicalize(p8) == canonicalize(can), \
            f"Phase-8 record {p8.kind} differs from canonical: {diff(p8, can)}"
```

Test 3 — import-linter fence:

```python
import subprocess
def test_projection_cannot_import_phase8_log():
    result = subprocess.run(
        ["lint-imports", "--config", "pyproject.toml"],
        capture_output=True, text=True, cwd=PROJECT_ROOT,
    )
    assert "codegenie.events.projections-must-not-import-phase8-log" in result.stdout
    assert result.returncode == 0  # baseline passes; fixture-violation runs separately
```

Plus the cursor-recovery and idempotence-property tests mirroring S7-02 ACs 12–14.

### Green — minimal pass

- Implement `PluginTelemetryRow` (frozen Pydantic, four int fields).
- Implement `PluginTelemetryState` (frozen Pydantic, `per_plugin` as tuple-of-pairs, `last_event_id`, `events_processed`).
- Implement `PluginTelemetryProjection`:
  - Filter to relevant kinds.
  - Sort by `(timestamp, wf_seq, event_id)`.
  - Dedup by `event_id` (carry `seen_event_ids` in state OR re-dedupe on every fold from a tuple field; choose the frozen-friendly representation).
  - Build a per-workflow scratch map `{workflow_id -> last_plugin_resolved.plugin_id}` to handle `RouteDecided.routed_to_fallback` cases where the event doesn't carry `plugin_id` directly.
  - Accumulate counters; produce frozen state.
- Extend `run_vuln_subgraph` with the forward-emit. Locate the Phase-8 internal log call sites; add a sibling `execute_activity("emit_event", ...)` immediately after each one.
- Add the `[tool.importlinter]` contract:
  ```toml
  [[tool.importlinter.contracts]]
  name = "codegenie.events.projections-must-not-import-phase8-log"
  type = "forbidden"
  source_modules = ["codegenie.events.projections"]
  forbidden_modules = ["codegenie.plugins.events"]
  ```
- Add the xfail fixture + the fence test.
- Register the projection via `@register_projection`; explicit import in `__init__.py`.

### Refactor

- If `PluginTelemetryRow.fallback` rule turns out to need cross-event joins (e.g., `RouteDecided` doesn't carry `plugin_id`), extract a `_PerWorkflowState` scratch dataclass with a clear docstring. Do NOT introduce a `JoinEngine` abstraction — kernel-tier, closed-set.
- Confirm zero `NotImplementedError`.
- Confirm `import codegenie.plugins.events` is NOT in `plugin_telemetry.py`'s AST.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/events/projections/plugin_telemetry.py` | NEW — projection class + state model + row model. |
| `src/codegenie/events/projections/__init__.py` | Explicit-import to populate registry. |
| `src/codegenie/durable/activities/run_vuln_subgraph.py` | EXTEND — add forward-emitter after each Phase-8 internal log call. |
| `pyproject.toml` | NEW import-linter contract. |
| `tests/golden/events/plugin_telemetry_stream.json` | NEW — 40-event input fixture. |
| `tests/golden/events/plugin_telemetry_stream.expected.json` | NEW — golden output. |
| `tests/unit/events/projections/test_plugin_telemetry_golden.py` | NEW — golden fold. |
| `tests/unit/events/projections/test_plugin_telemetry_cursor_recovery.py` | NEW — skip-ahead resume. |
| `tests/property/test_plugin_telemetry_idempotence.py` | NEW — Hypothesis idempotence + dedup. |
| `tests/property/test_plugin_telemetry_replay_convergent.py` | NEW — N-replay convergence. |
| `tests/integration/test_phase08_log_fanout.py` | NEW — byte-identity test. |
| `tests/fence/test_projection_no_phase8_import.py` | NEW — import-linter contract exercise. |
| `tests/fence/fixtures/projection_imports_phase8_log/__init__.py` | NEW — deliberate-violation xfail fixture. |
| `tests/fence/test_no_projection_notimplementederror.py` | EXTEND parametrization to include `plugin_telemetry.py`. |

## Out of scope

- **Deletion of `codegenie.plugins.events`** — Phase 10's first commit ([ADR-0002](../ADRs/0002-phase-8-plugin-events-log-cutover-to-canonical-event-log.md)). This story preserves the Phase-8 log unchanged inside `run_vuln_subgraph`.
- **Phase 10 cutover canary** — "no in-flight workflow on Phase-8-log-only path" — ADR-0002 names it as a Phase-10 precondition. Not this story.
- **`RouteDecision.freshness_window` semantics** — handled by S5-03 (`RouteStalenessDescent` workflow body emission) and S1-02 (variant landed in union). The `plugin_telemetry` projection counts the *outcome*, not the staleness recovery path.
- **`MultiPluginParentWorkflow` aggregate telemetry** — `MultiPluginParentWorkflow` (S5-04) emits its own `ParentResult` outcome events; aggregating those into `plugin_telemetry` lands additively in Phase 10 (when `coordination_policy="all_or_nothing"` / `"best_effort"` ship). Phase 9 ships only the leaf workflow telemetry.
- **Cost / token telemetry** — Phase 13's cost-ledger projection consumes `LlmInvoked.cost_usd` + `LlmInvoked.tokens`. ADR-0043 forbids a stub here.
- **Grafana / Phase-13.5 portal** — consumers, not producers; this story ships the fold only.
- **Cross-projection property tests** — S7-04 owns the matrixed property tests across all three projections.

## Notes for the implementer

- **The architect specifically called out this story's failure mode** ([phase-arch-design §Step 7 Risks](../phase-arch-design.md)): "engineers may forget [the canonical log is the only source] and accidentally read Phase-8 records into a new projection. Add a fence that no projection imports `codegenie.plugins.events`." AC-11 / AC-12 / AC-13 are that fence in three layers (import-linter contract, xfail fixture proving the contract bites, AST verification of the actual module). All three are load-bearing.
- **Byte-identity is the cutover guarantee.** ADR-0002's strangler-fig works because the canonical log can be trusted to contain everything the Phase-8 log contained. AC-9's byte-identity test is the structural defense. If timestamps drift between the two emit sites (Phase-8 internal log uses `datetime.now()`; canonical log uses Temporal's clock), the implementer must align them — likely by passing the Phase-8 record's timestamp through to the canonical emit.
- **One-way emit, not bidirectional.** Do not, under any circumstance, add a reverse path (canonical → Phase 8). ADR-0002's reversibility is "low" after Phase-10 deletion; a reverse path would invent dependencies that block Phase 10's first commit.
- **Read S4-05 first.** That story establishes the `run_vuln_subgraph` activity skeleton. The forward-emitter is a minimal addition — likely a `_forward_emit(phase8_record: PhaseEightLogRecord) -> None` helper that translates and calls `emit_event`. Do not refactor `run_vuln_subgraph`'s existing event emission; only add the fanout.
- **The `PluginTelemetryRow.fallback` counter requires a per-workflow join.** `RouteDecided.routed_to_fallback=True` does not necessarily carry `plugin_id` (read S1-02's variant definition). The projection joins on `workflow_id` with the most recent `PluginResolved` from the same workflow. Implementation: maintain a `{workflow_id -> last_plugin_id}` scratch map during the fold. The frozen state model does NOT carry this scratch — it's reconstructed on every fold from the input. (Skip-ahead `resume_from` MUST also carry forward the last-plugin-per-workflow map; otherwise resume produces wrong fallback counts. This is the load-bearing wrinkle that distinguishes `plugin_telemetry` from `retry_histogram`.) Concretely: extend `PluginTelemetryState` with a private `_last_plugin_by_workflow: tuple[tuple[WorkflowId, PluginId], ...]` field for cursor recovery; AC-16 must specifically test resume across a workflow boundary where the resume slice starts with `RouteDecided` and the prior slice ended with `PluginResolved`.
- **`MergeOutcome.outcome` discriminator literals.** Read S1-02. Likely `Literal["merged", "rejected", "human_terminated"]` or similar; map each to a counter in `PluginTelemetryRow`. Don't invent outcome names.
- **Mirror S7-01 and S7-02's module purity and frozen-state discipline.** If those stories diverged from this template (e.g., chose `frozendict` over tuple-of-pairs), ALIGN to them — Rule 11.
- **Performance envelope.** Phase-arch-design does not name a specific SLO for `plugin_telemetry`; mirror S7-02's `retry_histogram` budget ("fold over 10k events in <50 ms"). Add a perf smoke test at 1k events <50 ms; S8-04 owns the canonical bench.
- **Rule 12 (Fail loud) on fanout.** If the forward-emit fails (e.g., `emit_event` activity raises), the workflow MUST surface the error rather than silently dropping the canonical log entry. Temporal's retry policy on `emit_event` (S4-01) covers transient failures; permanent failures bubble up. Do not catch-and-log.
