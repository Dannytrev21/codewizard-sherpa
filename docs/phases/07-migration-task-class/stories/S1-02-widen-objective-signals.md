# Story S1-02 — Widen `ObjectiveSignals` with four optional `None` fields

**Step:** Step 1 — Establish the six additive seams, ADRs, and the contract-surface snapshot canary
**Status:** Ready
**Effort:** S
**Depends on:** —
**ADRs honored:** ADR-P7-002 (this phase ADR-0003), ADR-P7-007 (this phase ADR-0008), ADR-P7-008 (this phase ADR-0001), production ADR-0008

## Context

Phase 5's `ObjectiveSignals` is the cross-phase contract that `StrictAndGate.evaluate` iterates and `TrustScorer.score` reads. Phase 7 introduces four new gate-time signal kinds (`dive`, `shell_presence`, `shell_invocation_trace`, `base_image`); they must live as *optional* fields on `ObjectiveSignals` so vuln callsites are byte-identical when the new fields stay `None`. This story lands the additive Pydantic widening plus the four `*Signal` Pydantic model stubs the new fields reference — the model stubs are the smallest forward declarations Step 3's collectors can light up later.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component 13 ADR-P7-002` (lines ~847–859) — exact diff, the four `| None = None` fields, behavior-preservation rationale.
  - `../phase-arch-design.md §Component 8. Signal collectors` (lines ~712–746) — collector contracts that consume these models in Step 3.
  - `../phase-arch-design.md §Edge cases #6` — legitimate Alpine→glibc image-grows case proves `dive.passed=True` always (ADR-P7-007).
  - `../phase-arch-design.md §Gap 3` — the widening-compat test (`tests/integration/test_objective_signals_widening_compat.py`) is *out of scope here* (S3-06 owns it) but the model stubs land here so it can compile in Step 3.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0003-objective-signals-widening-and-allowlists.md` — ADR-P7-002 — only the `ObjectiveSignals` portion is in scope here; the two allowlist file edits live in S1-03.
  - `../ADRs/0008-dive-efficiency-advisory-only.md` — ADR-P7-007 — `DiveSignal` carries advisory details only; `passed=True` always is *not enforced* on the model itself (no Pydantic-level constraint), but the docstring must say so. Enforcement lives in the collector (S3-04).
  - `../ADRs/0001-six-named-additive-seams-and-adr-0028-amendment.md` — ADR-P7-008 — operational rule: default-`None` fields are behavior-preserving additive.
- **Production ADRs:**
  - `../../../production/adrs/0008-objective-signal-trust-score.md` — Trust score uses objective signals only; `extra="forbid"` discipline preserved.
- **Source design:**
  - `../final-design.md §Conflict-resolution row 5–6` (rootfs-bump rejection; this widening is the chosen alternative).
- **Existing code (read before writing):**
  - `src/codegenie/sandbox/signals/models.py` — the current `ObjectiveSignals` shape; do NOT rename fields or reorder existing ones. Add the four new fields at the *end* of the model.
  - `src/codegenie/sandbox/signals/__init__.py` — re-export the four new `*Signal` classes if Phase 5's `__init__.py` re-exports the existing signal models.

## Goal

`ObjectiveSignals` gains exactly four optional `None`-defaulting fields (`dive`, `shell_presence`, `shell_invocation_trace`, `base_image`), four new Pydantic `*Signal` model stubs are added in the same module, and existing Phase 3/4/5/6 callsites are provably byte-identical when the fields are unpopulated.

## Acceptance criteria

- [ ] `src/codegenie/sandbox/signals/models.py` defines four new Pydantic `BaseModel` classes with `model_config = ConfigDict(extra="forbid")`: `DiveSignal`, `ShellPresenceSignal`, `ShellInvocationTraceSignal`, `BaseImageSignal`. Each has a `passed: bool` field, a `details: dict[str, Any]` field, and (optionally) a `retryable: bool = False` field where the collector contract needs it (`ShellInvocationTraceSignal` per `phase-arch-design.md §Component 8`).
- [ ] `ObjectiveSignals` gains four optional fields, defaulting to `None`, in this order and *at the end of the existing field list*: `dive: DiveSignal | None = None`, `shell_presence: ShellPresenceSignal | None = None`, `shell_invocation_trace: ShellInvocationTraceSignal | None = None`, `base_image: BaseImageSignal | None = None`.
- [ ] Every existing pre-Phase-7 field on `ObjectiveSignals` is byte-stable (same name, same type, same default, same order) — verified by diffing `inspect.signature(ObjectiveSignals)` against a snapshot taken from `master`.
- [ ] `tests/unit/sandbox/signals/test_objective_signals_widening.py` is committed and green: (a) constructing `ObjectiveSignals()` with no arguments yields all four new fields as `None`; (b) `ObjectiveSignals(dive=DiveSignal(passed=True, details={}))` serializes via `model_dump_json` and round-trips through `model_validate_json` byte-identically; (c) the model rejects an unknown extra field (`ObjectiveSignals(unknown="x")` raises `ValidationError` because `extra="forbid"` is preserved).
- [ ] An existing-fixture compat test in `tests/unit/sandbox/signals/test_objective_signals_widening.py` loads a pre-Phase-7 `ObjectiveSignals` JSON fixture (one of the existing test fixtures in `tests/fixtures/objective_signals/` — or a copy preserved from `master`) and asserts deserialization succeeds with all four new fields equal to `None`.
- [ ] `ruff check`, `ruff format --check`, and `mypy --strict` pass on `src/codegenie/sandbox/signals/models.py` and the new test file.

## Implementation outline

1. Read `src/codegenie/sandbox/signals/models.py` end-to-end. Note the existing field list, the `model_config`, and whether `__init__.py` re-exports the model.
2. Snapshot the existing `ObjectiveSignals` JSON schema to `tests/fixtures/objective_signals/v0.6_baseline.json` (or reuse an existing fixture). This is the regression anchor.
3. Write the failing tests in `tests/unit/sandbox/signals/test_objective_signals_widening.py` (TDD red).
4. Add the four `*Signal` model classes to `models.py` (TDD green for the test that constructs them).
5. Append the four optional fields to `ObjectiveSignals` *at the end*; re-run the test.
6. Refactor: add module/class docstrings citing ADR-P7-002 and ADR-P7-007; ensure the `details: dict[str, Any]` typing doesn't trigger `mypy --strict` `Any`-leakage warnings.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file: `tests/unit/sandbox/signals/test_objective_signals_widening.py`

```python
# tests/unit/sandbox/signals/test_objective_signals_widening.py
import json
import pytest
from pydantic import ValidationError

from codegenie.sandbox.signals.models import (
    ObjectiveSignals,
    DiveSignal,
    ShellPresenceSignal,
    ShellInvocationTraceSignal,
    BaseImageSignal,
)


def test_objective_signals_new_fields_default_to_none():
    sig = ObjectiveSignals(<every existing required field…>)  # read models.py to fill these
    assert sig.dive is None
    assert sig.shell_presence is None
    assert sig.shell_invocation_trace is None
    assert sig.base_image is None


def test_dive_signal_round_trips_through_objective_signals():
    sig = ObjectiveSignals(
        <existing required fields…>,
        dive=DiveSignal(passed=True, details={"final_size_bytes": 12_345_678}),
    )
    payload = sig.model_dump_json()
    restored = ObjectiveSignals.model_validate_json(payload)
    assert restored == sig
    assert restored.dive is not None
    assert restored.dive.details["final_size_bytes"] == 12_345_678


def test_objective_signals_rejects_unknown_field_extra_forbid_preserved():
    with pytest.raises(ValidationError):
        ObjectiveSignals(<existing required fields…>, totally_unknown_field=1)


def test_v0_6_baseline_fixture_still_loads_with_new_fields_all_none():
    payload = (
        pathlib.Path("tests/fixtures/objective_signals/v0.6_baseline.json")
        .read_text(encoding="utf-8")
    )
    sig = ObjectiveSignals.model_validate_json(payload)
    assert sig.dive is None
    assert sig.shell_presence is None
    assert sig.shell_invocation_trace is None
    assert sig.base_image is None


def test_shell_invocation_trace_signal_carries_retryable_flag():
    s = ShellInvocationTraceSignal(passed=False, retryable=True, details={"reason": "budget_exhausted"})
    assert s.retryable is True
```

Expected red failure mode: `ImportError: cannot import name 'DiveSignal' from 'codegenie.sandbox.signals.models'` on the first test that imports any of the four new classes.

### Green — make it pass

In `src/codegenie/sandbox/signals/models.py`:

1. Add four new Pydantic models *above* `ObjectiveSignals` so the type references resolve without forward references:
   - `class DiveSignal(BaseModel)` with `model_config = ConfigDict(extra="forbid")`, `passed: bool`, `details: dict[str, Any] = Field(default_factory=dict)`.
   - `class ShellPresenceSignal(BaseModel)` — same shape.
   - `class ShellInvocationTraceSignal(BaseModel)` — same shape **plus** `retryable: bool = False` (the collector in Step 3 sets it on budget-exhaust / confidence-medium per `phase-arch-design.md §Component 8`).
   - `class BaseImageSignal(BaseModel)` — same shape (no `retryable`).
2. On `ObjectiveSignals`, append four optional fields at the end of the existing field list, each defaulting to `None`. Do not change `model_config`; do not reorder existing fields.

### Refactor — clean up

- Class docstrings naming ADR-P7-002 and (for `DiveSignal`) ADR-P7-007's "advisory only — `passed=True` always at the collector layer (not enforced here)" guidance.
- Confirm `details: dict[str, Any]` — if the codebase has a `details` typed elsewhere (e.g., `JsonValue`), match precedent rather than introducing `Any` here.
- Confirm the new fields appear after the existing ones in `model_json_schema()` output — order matters for the snapshot S1-07 will take.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/sandbox/signals/models.py` | Add four `*Signal` Pydantic classes and four optional fields to `ObjectiveSignals` (ADR-P7-002). |
| `tests/unit/sandbox/signals/test_objective_signals_widening.py` | New test — TDD red anchor; round-trip + v0.6-baseline compat. |
| `tests/fixtures/objective_signals/v0.6_baseline.json` | Regression-anchor fixture; pre-Phase-7-shape `ObjectiveSignals` JSON for the compat test. |
| `src/codegenie/sandbox/signals/__init__.py` | Only if Phase 5's `__init__.py` already re-exports `ObjectiveSignals` — match precedent and re-export the four new `*Signal` classes too. |

## Out of scope

- **`ALLOWED_BINARIES` and egress allowlist edits** — handled by S1-03 (same ADR-P7-002 bundle, separate story for diff hygiene).
- **Collector implementations (`dive.py`, `shell_presence.py`, etc.)** — handled by Step 3 (S3-04, S3-05, S3-06).
- **`tests/integration/test_objective_signals_widening_compat.py` exercising `TrustScorer.score` and `StrictAndGate.evaluate` over every populated/non-populated permutation** — handled by S3-06 (the test depends on real collectors landing, not just stubs).
- **Contract-surface snapshot regen capturing the new schema** — handled by S1-07.

## Notes for the implementer

- *Do not* enforce `passed=True` at the `DiveSignal` Pydantic layer — the advisory-only rule (ADR-P7-007) is enforced inside the *collector* in S3-04. If you add a Pydantic validator that forces `passed=True`, you collapse the model's expressiveness and break the integration test in S3-06. The docstring is the signal; the validator is wrong.
- The new optional fields must default to `None` (not `Field(default=None)`-with-a-validator-that-rewrites). Default-`None` is what makes existing `model_dump_json` payloads byte-identical when callers don't pass the fields — `pytest tests/integration/test_phase4_default_task_type_behavior_unchanged.py` (S1-04) and the v0.6 baseline fixture above are the mechanical enforcement.
- If `ObjectiveSignals` currently uses `Field(...)` annotations for documentation, mirror that style for the four new fields; do not switch annotation styles mid-file.
- `extra="forbid"` is load-bearing per production ADR-0008. The test that asserts it cannot regress (`test_objective_signals_rejects_unknown_field_extra_forbid_preserved`) is mandatory — if you remove or weaken `extra="forbid"` to accommodate the widening, the whole point of the widening is lost.
- `ShellInvocationTraceSignal.retryable: bool = False` is the field S3-05's collector sets to `True` on `confidence != "high"` and to `False` on "observed shell." Land it now so S3-05 doesn't have to come back and edit the model.
- Read `src/codegenie/sandbox/signals/models.py` end-to-end *before* writing tests. The existing required fields on `ObjectiveSignals` must appear in your test's constructor call — guessing them will leave the test red for the wrong reason.
- The v0.6-baseline JSON fixture must be the pre-Phase-7 shape (no new fields). If `tests/fixtures/objective_signals/` doesn't exist, create the directory and add a single canonical-JSON file matching the current `ObjectiveSignals` schema as-shipped on `master`. This fixture is also load-bearing for S3-06's widening-compat test.
