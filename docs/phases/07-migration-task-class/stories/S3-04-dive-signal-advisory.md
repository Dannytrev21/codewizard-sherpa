# Story S3-04 — `DiveSignal` advisory-only collector

**Step:** Step 3 — Land `BaseImageProbe`, `ShellInvocationTraceProbe`, and the four signal collectors
**Status:** Ready
**Effort:** S
**Depends on:** S3-01
**ADRs honored:** ADR-P7-007 (`dive_efficiency` advisory-only), ADR-P7-002 (`ObjectiveSignals` widening + allowlists), ADR-0008 (facts, not judgments)

## Context

This is the first of four `@register_signal_kind` collectors that light up the optional fields S1-02 added to `ObjectiveSignals`. `dive` is the deliberately *advisory-only* one — `passed=True` always, even when `size_ratio_post_pre > 1.0`. The ADR-P7-007 / critic sec.3 lesson is that strict-AND on size ratio would auto-fail legitimate Alpine→glibc migrations and cascade into LLM-fallback spend on non-bugs. This story is the test that proves that fix landed (`tests/unit/sandbox/signals/test_dive_signal.py` asserts `passed=True` under image growth) — closing critic sec.3 mechanically.

It is also one of the four collectors S3-06's widening-compat test sweeps; the populated-vs-`None` permutations exercised there pivot on whether this collector ran for a given workflow. Keep the shape tight: one Pydantic model (`DiveSignal`), one collector function, one registration call.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design ›8. Signal collectors` — `dive` is **ADVISORY only**; `passed=True` always; `details` carries `final_size_bytes`, `efficiency_pct`, `wasted_bytes`, `size_ratio_post_pre`.
  - `../phase-arch-design.md §Data model ›Contracts` — `DiveSignal(passed: bool, details: dict[str, int | float | str])` with `extra="forbid"`, `frozen=True`.
  - `../phase-arch-design.md §Edge cases` — row 6 (Alpine→glibc legitimate growth; `size_ratio_post_pre > 1.0`; `passed=True`).
  - `../phase-arch-design.md §Testing strategy ›Unit tests` — `test_dive_signal.py`: fixture `dive --json`; assert advisory `passed=True` even when `size_ratio_post_pre > 1.0`.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0008-dive-efficiency-advisory-only.md` — ADR-P7-007 — `passed=True` always; rationale; Phase 13 calibration retains the right to harden later.
  - `../ADRs/0003-objective-signals-widening-and-allowlists.md` — ADR-P7-002 — collector populates the `ObjectiveSignals.dive` slot.
- **Production ADRs:**
  - `../../../production/adrs/0008-objective-signal-trust-score.md` — objective signals only; no LLM self-confidence.
  - `../../../production/adrs/0015-trust-score-threshold-calibration.md` — Phase 13 owns the eventual tightening.
- **Existing code:**
  - `src/codegenie/sandbox/signals/models.py` — `ObjectiveSignals.dive: DiveSignal | None = None` (S1-02); `DiveSignal` model lives or is imported here.
  - `src/codegenie/sandbox/signals/__init__.py` — `@register_signal_kind` decorator (Phase 5; pre-existing).
  - `src/codegenie/tools/dive.py` — Pydantic wrapper around `dive --json` (S2-03); returns `DiveResult`.

## Goal

`@register_signal_kind("dive") def collect_dive(image_digest: str, ctx: GateContext) -> DiveSignal` lives at `src/codegenie/sandbox/signals/dive.py`, registers at import time, populates `details` with the four metrics, and returns `passed=True` **always** — including the fixture case where `size_ratio_post_pre > 1.0`.

## Acceptance criteria

- [ ] `src/codegenie/sandbox/signals/dive.py` exists with `@register_signal_kind("dive")` decorator on the `collect_dive` function.
- [ ] `DiveSignal` Pydantic model (in `signals/models.py` or imported there from this module) has `extra="forbid"`, `frozen=True`, `passed: bool`, `details: dict[str, int | float | str]`.
- [ ] **Intent test** `test_dive_signal_emits_facts_not_judgments` asserts no field name on `DiveSignal` matches `^(is_|safe_|recommended_).*` and that the only verdict-shaped field (`passed`) is hardcoded `True` in the collector's source.
- [ ] **Advisory-only test** `test_dive_passed_true_when_image_grows`: arrange a `DiveResult` fixture with `size_ratio_post_pre = 1.4` (Alpine→glibc growth case); act → `collect_dive`; assert `result.passed is True`. This is the load-bearing assertion that closes critic sec.3.
- [ ] **Details-population test**: assert all four detail keys (`final_size_bytes`, `efficiency_pct`, `wasted_bytes`, `size_ratio_post_pre`) are present with the values from the `DiveResult` fixture.
- [ ] **Registry test**: `@register_signal_kind` produces a lookup such that `signal_kinds()["dive"]` returns this function (use Phase 5's existing registry accessor).
- [ ] **None-friendly downstream test**: a `DiveResult` with `size_ratio_post_pre=None` (pre-image size unknown) still returns `DiveSignal(passed=True, details={..., "size_ratio_post_pre": <serialized None or omitted>})`.
- [ ] `mypy --strict src/codegenie/sandbox/signals/dive.py` + `ruff check` clean.
- [ ] Fence-CI denies LLM-SDK imports under `sandbox/signals/` (S1-08 / S7-06) — this file imports only `pydantic`, `codegenie.sandbox.*`, `codegenie.tools.dive`.
- [ ] ADR-0008 traceability: the docstring on `collect_dive` cites `ADR-P7-007` and the rationale "facts, not judgments".

## Implementation outline

1. Scaffold `src/codegenie/sandbox/signals/dive.py` with `from codegenie.sandbox.signals import register_signal_kind` and `from codegenie.tools.dive import run as dive_run, DiveResult`.
2. Define (or re-export) `DiveSignal` Pydantic model with the contract shape.
3. Implement:
   ```python
   @register_signal_kind("dive")
   def collect_dive(image_digest: str, ctx: GateContext) -> DiveSignal:
       result = dive_run(image_digest, ctx)
       return DiveSignal(
           passed=True,  # always; ADR-P7-007
           details={
               "final_size_bytes": result.final_size_bytes,
               "efficiency_pct": result.efficiency_pct,
               "wasted_bytes": result.wasted_bytes,
               "size_ratio_post_pre": result.size_ratio_post_pre,  # may be None
           },
       )
   ```
4. Handle `size_ratio_post_pre is None`: serialize as the string `"unknown"` *or* omit the key — pick one and document the choice in the docstring + an explicit test (the contract-surface snapshot will capture whichever choice is made).
5. Ensure no `random` / `time` import; deterministic.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/sandbox/signals/test_dive_signal.py`

```python
# tests/unit/sandbox/signals/test_dive_signal.py
import re
from unittest.mock import patch

from codegenie.sandbox.signals.dive import collect_dive, DiveSignal
from codegenie.tools.dive import DiveResult

JUDGMENT_RE = re.compile(r"^(is_|safe_|recommended_).*")

def test_dive_signal_emits_facts_not_judgments():
    # arrange + act
    field_names = list(DiveSignal.model_fields.keys())
    # assert: no judgment-shaped field names
    offenders = [f for f in field_names if JUDGMENT_RE.match(f)]
    assert offenders == [], f"DiveSignal must be facts-only: {offenders}"

def test_dive_passed_true_when_image_grows():
    # arrange: Alpine→glibc fixture — image grew 40%
    fixture = DiveResult(
        image_digest="sha256:" + "a" * 64,
        final_size_bytes=140_000_000,
        efficiency_pct=92.5,
        wasted_bytes=11_200_000,
        layer_count=4,
        final_layer_files=[],
        size_ratio_post_pre=1.4,
    )
    with patch("codegenie.sandbox.signals.dive.dive_run", return_value=fixture):
        # act
        sig = collect_dive(image_digest=fixture.image_digest, ctx=_fake_ctx())
    # assert: passed is True even when image grew (ADR-P7-007, closes critic sec.3)
    assert sig.passed is True
    assert sig.details["size_ratio_post_pre"] == 1.4

def test_dive_details_carry_all_four_metrics(): ...
def test_dive_registered_on_signal_kind_registry(): ...
def test_dive_size_ratio_none_is_handled_explicitly(): ...
```

Fails immediately on `ImportError` (`collect_dive`, `DiveSignal` not yet defined). Commit red.

### Green — make it pass

Implement the 10-line collector body. The signal model fields must match the contract exactly (`passed: bool`, `details: dict[str, int | float | str]`). Use `unittest.mock.patch` on the `dive_run` symbol imported into the dive signal module (not the original `tools.dive.run`) so mocking is unambiguous.

### Refactor — clean up

- Docstring on `collect_dive` citing ADR-P7-007 and the closure of critic sec.3.
- Type hints fully nailed (`Mapping[str, int | float | str]` would be tighter but `dict` matches the contract; stick with `dict` for symmetry with other `*Signal` types).
- If `size_ratio_post_pre is None`, document the chosen behavior (omit vs `"unknown"`) and ensure one test exercises it explicitly. The contract-surface snapshot captures the chosen behavior.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/sandbox/signals/dive.py` | New — collector + `@register_signal_kind("dive")` per Component 8 + ADR-P7-007. |
| `tests/unit/sandbox/signals/test_dive_signal.py` | New — advisory + intent + registry + details + None tests. |
| `src/codegenie/sandbox/signals/__init__.py` | Additive import line so registration fires at package import time (no removal/reorder of existing imports). |
| `src/codegenie/sandbox/signals/models.py` | If `DiveSignal` is not yet exported here, add additive re-export; do **not** change S1-02's widening additions. |

## Out of scope

- **`tools/dive.py`** — S2-03; this story consumes the wrapper.
- **Strict-AND collectors** — S3-05 (`ShellPresenceSignal`, `ShellInvocationTraceSignal`).
- **`BaseImageSignal` collector + widening-compat test** — S3-06.
- **Phase 13 calibration** — production ADR-0015 owns the eventual decision to harden any advisory signal.
- **The legitimate-growth fixture repo (`alpine-to-glibc-distroless`)** — S6-05; this story uses a constructed `DiveResult` value, not a real `dive` invocation.
- **`migration-report.yaml` surfacing of `dive_summary`** — S5-03/S5-04 (`emit_artifact` node).

## Notes for the implementer

- `passed=True` is hardcoded. Do not parameterize it, do not feature-flag it, do not put a `# TODO: harden later` comment with a threshold. ADR-P7-007 is the documented decision; Phase 13 owns any future change. If you find yourself writing `if size_ratio_post_pre > THRESHOLD:`, stop and re-read ADR-P7-007.
- The collector is *deterministic*. No `random`, no `time`. Output depends only on `DiveResult` input.
- `size_ratio_post_pre: float | None` — `tools.dive.DiveResult` allows `None` (pre-image size unknown). Decide once whether the signal omits the detail key or serializes a sentinel string; document the choice; cover it with a test. The contract-surface snapshot (`tests/integration/test_contract_surface_snapshot.py`) freezes whichever you pick.
- The intent test asserting `is_*|safe_*|recommended_*` is *cross-cutting* across all four Step 3 signal stories. The pattern repeats: `test_<signal>_emits_facts_not_judgments`. Keep the regex identical across stories for grep-ability.
- Don't pre-emptively add ELF-symbol scanning, layer-by-layer growth attribution, or any other "richer evidence" — non-goal #14 (`phase-arch-design.md §Non-goals`) defers ELF scanning to Phase 12+; this story stays small.
- Fence-CI denies `anthropic|chromadb|sentence-transformers` under `sandbox/signals/` — only `pydantic`, `codegenie.sandbox.*`, `codegenie.tools.*` allowed.
