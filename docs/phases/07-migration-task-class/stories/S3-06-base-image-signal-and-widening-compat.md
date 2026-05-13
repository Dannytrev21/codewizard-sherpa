# Story S3-06 — `BaseImageSignal` collector + `ObjectiveSignals` widening-compat integration test

**Step:** Step 3 — Land `BaseImageProbe`, `ShellInvocationTraceProbe`, and the four signal collectors
**Status:** Ready
**Effort:** M
**Depends on:** S1-02, S3-04, S3-05
**ADRs honored:** ADR-P7-002 (`ObjectiveSignals` widening — this is the test that proves "additive" mechanically), ADR-0008 (facts, not judgments — `BaseImageSignal.passed=True` informational, no verdict), ADR-P7-007 (advisory-only lineage)

## Context

This story closes the Step 3 surface. It does two things:

1. Adds the fourth signal collector — `BaseImageSignal`, an *informational* projection of `BaseImageProbe`'s output into the gate audit chain. `passed=True` always (like `DiveSignal`, ADR-P7-007 lineage); `details` carries the pre-image manifest digest so Phase 11 (Handoff) can read it from the audit chain later. This is the gate-time projection of S3-01's gather-time evidence; the slot it populates is `ObjectiveSignals.base_image` (widened in S1-02).
2. Lands the **widening-compat integration test** that closes Gap 3 (`phase-arch-design.md §Gap 3`). The architect's gap analysis was explicit: the ADR-P7-002 widening is "additive" only if every existing consumer (Phase 3 `TrustScorer.score`, Phase 5 `StrictAndGate.evaluate`, future Phase 13 cost ledger) handles `None` for the new fields *and* doesn't silently drop populated new fields. The contract-surface snapshot catches *schema* drift but not *consumer-behavior* drift; this test does.

Together, this is the last story that has to land before Step 4 (recipes + transform) and Step 5 (vertical slice) can compose against `ObjectiveSignals`.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design ›8. Signal collectors` — `base_image` is informational: carries the pre-image manifest digest so Phase 11 reads it from the gate audit chain.
  - `../phase-arch-design.md §Data model ›Contracts` — `BaseImageSignal(passed: bool, details: dict[str, str])` with `passed: bool # always True (informational); details carries digests`; `extra="forbid"`, `frozen=True`.
  - `../phase-arch-design.md §Gap 3` — full statement of the widening-compat hole + the proposed fix: `tests/integration/test_objective_signals_widening_compat.py` runs `TrustScorer.score` + `StrictAndGate.evaluate` over every populated / `None` permutation of the four new fields; asserts (a) no exception, (b) `TrustSignal` list length matches the count of non-`None` fields.
  - `../phase-arch-design.md §Testing strategy ›Integration tests` — `test_objective_signals_widening_compat.py` bullet.
  - `../phase-arch-design.md §Edge cases` — row 11 (Phase 0–6 source code edited outside the six named seams → snapshot canary fires); this story is one of the new-files-only consumers the canary protects.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0003-objective-signals-widening-and-allowlists.md` — ADR-P7-002 — the widening; "additive" is conditional on this test.
  - `../ADRs/0008-dive-efficiency-advisory-only.md` — ADR-P7-007 — `BaseImageSignal.passed=True` informational policy follows the same lineage.
  - `../ADRs/0009-contract-surface-snapshot-canary.md` — ADR-P7-009 — schema snapshot; this story complements with a *behavior* snapshot.
- **Production ADRs:**
  - `../../../production/adrs/0008-objective-signal-trust-score.md` — `TrustScorer.score` interface; consumed here.
- **Existing code:**
  - `src/codegenie/probes/base_image.py` — S3-01.
  - `src/codegenie/sandbox/signals/models.py` — S1-02 widens `ObjectiveSignals` with `dive`, `shell_presence`, `shell_invocation_trace`, `base_image: ... | None = None`; `BaseImageSignal` model lives here or is imported.
  - `src/codegenie/sandbox/signals/dive.py`, `shell_presence.py`, `shell_invocation_trace.py` — S3-04 / S3-05.
  - Phase 3 `TrustScorer.score(signals: ObjectiveSignals, ctx) -> TrustScore`.
  - Phase 5 `StrictAndGate.evaluate(signals: ObjectiveSignals, ctx) -> GateOutcome`.

## Goal

`@register_signal_kind("base_image") def collect_base_image(inventory: DockerfileInventory, ctx) -> BaseImageSignal` lives at `src/codegenie/sandbox/signals/base_image.py` with `passed=True` always, and `tests/integration/test_objective_signals_widening_compat.py` exercises **every** populated / non-populated permutation of the four new optional fields against both `TrustScorer.score` and `StrictAndGate.evaluate` and asserts (a) no exception, (b) `TrustSignal` count matches the count of non-`None` fields.

## Acceptance criteria

- [ ] `src/codegenie/sandbox/signals/base_image.py` exists; `@register_signal_kind("base_image")` decorates `collect_base_image`; signature `collect_base_image(inventory: DockerfileInventory, ctx: GateContext) -> BaseImageSignal`.
- [ ] `BaseImageSignal` Pydantic model with `extra="forbid"`, `frozen=True`, `passed: bool`, `details: dict[str, str]`; `passed=True` hardcoded in the collector body (informational).
- [ ] `details` carries `pre_image_digest`, `final_stage_from_ref`, `parser_skipped_lines` (stringified), and `confidence` — exactly four string-valued keys (the model's `details: dict[str, str]` constraint enforces it).
- [ ] **Intent test** `test_base_image_signal_emits_facts_not_judgments`: no `is_*|safe_*|recommended_*` field names on `BaseImageSignal`; `passed` allowlisted.
- [ ] **Widening-compat test** `tests/integration/test_objective_signals_widening_compat.py`:
  - Parametrized over all 16 (2^4) permutations of `(dive | None, shell_presence | None, shell_invocation_trace | None, base_image | None)`.
  - For each permutation, construct an `ObjectiveSignals` instance with all required existing fields populated from a stock fixture + the parameterized new fields.
  - Call `TrustScorer.score(signals, ctx)` — assert no exception.
  - Call `StrictAndGate.evaluate(signals, ctx)` — assert no exception.
  - Assert `len(score.signals) == count_of_non_none_new_fields + count_of_existing_populated_fields`; specifically, that **no populated new field is silently dropped** by either consumer.
- [ ] **v0.6 backward-compat fixture**: a separate test asserts an `ObjectiveSignals` payload with *all four new fields `None`* produces a `GateOutcome` byte-identical (`model_dump_json()` equality) to a stored v0.6-shape fixture from before the widening — proves vuln callers see no behavior change.
- [ ] `mypy --strict src/codegenie/sandbox/signals/base_image.py` + `ruff check` clean.
- [ ] Fence-CI denies LLM-SDK imports under `sandbox/signals/`.
- [ ] All four Step 3 signal collectors visible in the signal-kind registry — single assertion: `set(signal_kinds()) >= {"dive","shell_presence","shell_invocation_trace","base_image"}`.

## Implementation outline

1. Author `src/codegenie/sandbox/signals/base_image.py`:
   ```python
   @register_signal_kind("base_image")
   def collect_base_image(inventory: DockerfileInventory, ctx) -> BaseImageSignal:
       return BaseImageSignal(
           passed=True,  # informational; ADR-P7-007 lineage
           details={
               "pre_image_digest": inventory.resolved_pre_image_digest or "unresolved",
               "final_stage_from_ref": inventory.stages[inventory.final_stage_index].from_ref,
               "parser_skipped_lines": str(inventory.parser_skipped_lines),
               "confidence": inventory.confidence,
           },
       )
   ```
2. Author `tests/integration/test_objective_signals_widening_compat.py`:
   - Define a `_base_signals(**overrides)` helper that produces a stock `ObjectiveSignals` with existing required fields populated (use Phase 5 fixtures already in `tests/fixtures/objective_signals/` if present, else inline).
   - Define `_dive_fixture()`, `_shell_presence_fixture()`, `_shell_invocation_trace_fixture()`, `_base_image_fixture()` returning concrete populated `*Signal` instances.
   - Parametrize over `itertools.product([None, fixture()], repeat=4)` — 16 permutations.
   - For each: construct `ObjectiveSignals(...)`, call `TrustScorer.score`, call `StrictAndGate.evaluate`, assert (no exception, length invariant).
3. Author the v0.6 backward-compat fixture file `tests/fixtures/objective_signals/v0_6_all_none.json` checked into the repo. The compat test loads it, populates an `ObjectiveSignals`, calls `StrictAndGate.evaluate`, and asserts the result's `model_dump_json()` matches a sibling golden `v0_6_gate_outcome.golden.json`.
4. Register `base_image` collector from `signals/__init__.py` so import-time registration fires.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/integration/test_objective_signals_widening_compat.py`

```python
# tests/integration/test_objective_signals_widening_compat.py
import itertools
import pytest

from codegenie.sandbox.signals.models import (
    ObjectiveSignals, DiveSignal, ShellPresenceSignal,
    ShellInvocationTraceSignal, BaseImageSignal,
)
from codegenie.gates.trust_scorer import TrustScorer
from codegenie.gates.strict_and import StrictAndGate

def _dive(): return DiveSignal(passed=True, details={"size_ratio_post_pre": 1.0})
def _sp():   return ShellPresenceSignal(passed=True, details={"static_shell_binary_count": 0})
def _sit():  return ShellInvocationTraceSignal(passed=True, retryable=False,
                                                details={"runtime_shell_count": 0, "confidence": "high"})
def _bi():   return BaseImageSignal(passed=True, details={"pre_image_digest": "sha256:" + "a"*64,
                                                           "final_stage_from_ref": "node:20",
                                                           "parser_skipped_lines": "0",
                                                           "confidence": "high"})

def _base_objective_signals(**overrides) -> ObjectiveSignals:
    fields = dict(
        # ... existing required Phase 5 fields populated from canonical fixture
        build={"passed": True, "details": {}},  # placeholder — match your real shape
        grype={"passed": True, "details": {"cve_delta": 0}},
        dive=None, shell_presence=None, shell_invocation_trace=None, base_image=None,
    )
    fields.update(overrides)
    return ObjectiveSignals(**fields)

@pytest.mark.parametrize(
    "dive_val,sp_val,sit_val,bi_val",
    list(itertools.product([None, "fix"], repeat=4)),
)
def test_widening_compat_all_permutations(dive_val, sp_val, sit_val, bi_val):
    overrides = {
        "dive": _dive() if dive_val else None,
        "shell_presence": _sp() if sp_val else None,
        "shell_invocation_trace": _sit() if sit_val else None,
        "base_image": _bi() if bi_val else None,
    }
    signals = _base_objective_signals(**overrides)
    expected_new_populated = sum(1 for v in overrides.values() if v is not None)

    # act + assert: no exception from either consumer
    score = TrustScorer().score(signals, ctx=None)
    outcome = StrictAndGate().evaluate(signals, ctx=None)

    # invariant: no populated new field is silently dropped by TrustScorer
    new_field_names = {"dive", "shell_presence", "shell_invocation_trace", "base_image"}
    seen_new = {s.kind for s in score.signals if s.kind in new_field_names}
    expected_new = {k for k, v in overrides.items() if v is not None}
    assert seen_new == expected_new, (
        f"TrustScorer dropped populated new fields: expected {expected_new}, got {seen_new}"
    )
```

Fails on `ImportError` for `BaseImageSignal` (until widened in S1-02) or on missing collectors. Commit red.

Sibling unit test for the base-image collector:

```python
# tests/unit/sandbox/signals/test_base_image_signal.py
def test_base_image_signal_passed_true_always(): ...
def test_base_image_signal_details_keys_are_exactly_four(): ...
def test_base_image_signal_handles_unresolved_pre_image_digest(): ...
def test_base_image_signal_emits_facts_not_judgments(): ...
def test_base_image_collector_registered(): ...
```

And the v0.6 backward-compat test:

```python
def test_v0_6_all_none_payload_produces_identical_gate_outcome(tmp_path): ...
```

### Green — make it pass

Implement `collect_base_image` (~12 lines). Ensure `BaseImageSignal` is importable from `codegenie.sandbox.signals.models` (S1-02 may already place it there; if not, additive re-export). For the widening-compat test, you may need to extend the existing Phase 3 `TrustScorer.score` to surface the new fields *if* it currently switches on a closed enum — but Gap 3's whole point is that it *should* iterate populated optional fields without an enum-switch. If you find the existing consumer hard-codes the old field set, that's the silent failure mode this test exists to catch — surface it loudly (Rule 12) rather than patching it in this story; file a follow-up under the synthesizer's "additive" claim.

### Refactor — clean up

- Pull the `_dive` / `_sp` / `_sit` / `_bi` fixture builders into a `tests/fixtures/objective_signals/conftest.py` for reuse in S5-x.
- Document the parametrization (16 rows) in the test module docstring; cite ADR-P7-002 and Gap 3.
- Add a structured-log entry on signal collection per `phase-arch-design.md §Harness engineering ›Logging strategy`.
- Verify the `signal_kinds()` registry test is hermetic — module-import order isn't guaranteed; explicitly import all four signal modules in the test setup.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/sandbox/signals/base_image.py` | New — informational `BaseImageSignal` collector. |
| `tests/unit/sandbox/signals/test_base_image_signal.py` | New — unit coverage + intent test. |
| `tests/integration/test_objective_signals_widening_compat.py` | New — 16-permutation parametrized test over `TrustScorer.score` + `StrictAndGate.evaluate` (Gap 3). |
| `tests/fixtures/objective_signals/v0_6_all_none.json` | New — v0.6-shape payload (all four new fields `None`). |
| `tests/fixtures/objective_signals/v0_6_gate_outcome.golden.json` | New — golden outcome the v0.6 payload must produce. |
| `tests/fixtures/objective_signals/conftest.py` | New — `_dive` / `_sp` / `_sit` / `_bi` fixture builders. |
| `src/codegenie/sandbox/signals/__init__.py` | Additive import line. |

## Out of scope

- **`ObjectiveSignals` widening itself** — S1-02.
- **Probe / strict-AND collectors** — S3-01, S3-02, S3-04, S3-05.
- **`TrustScorer.score` or `StrictAndGate.evaluate` source edits** — those are Phase 3 / Phase 5 surfaces; only *if* the widening-compat test surfaces a real consumer bug should this story raise it as a follow-up. Surgical-changes rule: do not "improve" the consumers in this story.
- **Phase 13 calibration** — production ADR-0015; this story is informational-only.
- **`migration-report.yaml` surfacing of `base_image` evidence** — S5-04's `emit_artifact` node.
- **Snapshot canary itself** — S1-07.
- **Adversarial / typosquat tests on the base-image catalog** — S6-09.

## Notes for the implementer

- The widening-compat test is the **mechanical** proof that ADR-P7-002 is honest. The contract-surface snapshot (S1-07) tracks the Pydantic schema; this test tracks consumer behavior. Both are needed — the schema can pass while the consumer drops the new field silently. If you find a permutation where `TrustScorer` returns the same `signals` list whether `base_image` is populated or `None`, the consumer has a bug and the additive claim fails — surface loudly (Rule 12), do not silently coerce the test green.
- 16 permutations × two consumers (`TrustScorer`, `StrictAndGate`) = 32 assertions. That's the whole space. Don't reduce to "a representative subset" — the architect's gap analysis specifies "every populated/non-populated combination".
- `BaseImageSignal.passed=True` always is informational, mirroring the `DiveSignal` policy under ADR-P7-007. The signal counts toward strict-AND but never fails it. This is the *third* of the four new signals to follow that lineage (`dive` advisory-only, `base_image` informational); `shell_presence` and `shell_invocation_trace` are the two that can fail the gate.
- The v0.6 backward-compat fixture closes the half of Gap 3 the architect didn't spell out: someone could write the parametrized test but still introduce a behavior change in the `None`-defaults path. The golden-file equality test pins down that vuln callers see byte-identical outcomes.
- `details` is `dict[str, str]` for `BaseImageSignal` — stringify everything including `parser_skipped_lines`. The contract-surface snapshot is byte-exact; coercing an `int` to `str` once at collection time keeps the snapshot stable.
- Pull `_base_objective_signals` helpers into a sibling conftest now — S5-x and S6-x will reuse them.
- Don't add a fifth optional field to `ObjectiveSignals` "for symmetry" — non-goal #3 (no cosign signature) and non-goal #14 (no ELF-symbol scanning) cover the impulse to expand. Step 3 ends at four signals.
