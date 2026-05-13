# Story S3-05 — `ShellPresenceSignal` + `ShellInvocationTraceSignal` strict-AND collectors

**Step:** Step 3 — Land `BaseImageProbe`, `ShellInvocationTraceProbe`, and the four signal collectors
**Status:** Ready
**Effort:** M
**Depends on:** S3-02
**ADRs honored:** ADR-P7-002 (`ObjectiveSignals` widening), ADR-0013 (gate-time strace; `confidence != "high" OR observed shell → passed=False`), ADR-0008 (facts, not judgments — the `passed` verdict is the gate's job, not the probe's; the projection rule is documented), ADR-0014 (production: three-retry default per gate — `retryable=True` on budget exhaust)

## Context

Two of the three remaining signal collectors (the third is `BaseImageSignal` in S3-06). Both are *strict-AND* — they participate in `StrictAndGate.evaluate`'s binary verdict and can fail the gate. The split is intentional: `shell_presence` is a static check that *projects* on the dive collector's `final_layer_files` (no second `dive --json` invocation — one dive run, two signals); `shell_invocation_trace` *projects* on `ShellInvocationTraceProbe`'s output (S3-02) and encodes the asymmetric retry policy in ADR-0013:

- `confidence != "high"` (budget exhaust) → `passed=False, retryable=True` (Phase 5 three-retry kicks in).
- Observed shell (`runtime_shell_count > 0`) → `passed=False, retryable=False` (no point retrying — the candidate genuinely shells out; HITL).

This is the *judgment seam* — the gate is where evidence becomes verdict (production ADR-0008). The probe still emits facts; the signal collector applies the documented policy.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design ›8. Signal collectors` — code sketch of `collect_shell_presence` (projection on `dive_result.final_layer_files`); the shell binary path list `["/bin/sh","/bin/bash","/bin/dash","/bin/busybox","/usr/bin/sh","/usr/bin/bash"]`; one dive invocation → two signals.
  - `../phase-arch-design.md §Data model ›Contracts` — `ShellPresenceSignal(passed, details)` and `ShellInvocationTraceSignal(passed, retryable, details)` Pydantic shapes (`extra="forbid"`, `frozen=True`).
  - `../phase-arch-design.md §Edge cases` — row 5 (budget exhaust → `confidence=medium` → `passed=False, retryable=True`); the observed-shell case is implicit in scenario 3 (gate fails non-retryably; HITL).
  - `../phase-arch-design.md §Testing strategy ›Unit tests` — `test_shell_presence_signal.py`: fixtures with/without `/bin/sh`; `test_shell_invocation_trace_signal.py`: three-way truth table (`high+count=0 → passed=True`; `medium → passed=False, retryable=True`; observed shell → `passed=False, retryable=False`).
  - `../phase-arch-design.md §Scenarios ›Scenario 3` — full retry path on budget exhaust.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0013-shell-trace-runs-gate-time-in-phase5-chokepoint.md` — ADR-0013 — strict-AND collector emits `retryable=True` on budget exhaust, `retryable=False` on observed shell.
  - `../ADRs/0003-objective-signals-widening-and-allowlists.md` — ADR-P7-002 — both signals populate slots on `ObjectiveSignals`.
  - `../ADRs/0008-dive-efficiency-advisory-only.md` — facts-not-judgments lineage for the intent test (the `passed` field is the *gate's* projection of probe evidence, not a judgment the probe wrote).
- **Production ADRs:**
  - `../../../production/adrs/0008-objective-signal-trust-score.md` — objective signals only.
  - `../../../production/adrs/0014-three-retry-default-per-gate.md` — three-retry cap; budget-exhaust path uses `retryable=True` to participate.
- **Existing code:**
  - `src/codegenie/sandbox/signals/__init__.py` — `@register_signal_kind` decorator.
  - `src/codegenie/probes/shell_invocation_trace.py` — `ShellInvocationTrace` Pydantic (S3-02).
  - `src/codegenie/tools/dive.py` — `DiveResult.final_layer_files` (S2-03).
  - `src/codegenie/sandbox/signals/models.py` — `ObjectiveSignals.shell_presence`, `.shell_invocation_trace` slots (S1-02).

## Goal

`@register_signal_kind("shell_presence")` and `@register_signal_kind("shell_invocation_trace")` collectors live at `src/codegenie/sandbox/signals/shell_presence.py` and `src/codegenie/sandbox/signals/shell_invocation_trace.py`, both implement the strict-AND policy specified in `phase-arch-design.md §Component 8` exactly, and pass an intent test asserting no judgment-named output fields.

## Acceptance criteria

- [ ] `src/codegenie/sandbox/signals/shell_presence.py` exists; registered as `"shell_presence"`; signature `collect_shell_presence(dive_result: DiveResult, ctx: GateContext) -> ShellPresenceSignal`.
- [ ] `src/codegenie/sandbox/signals/shell_invocation_trace.py` exists; registered as `"shell_invocation_trace"`; signature `collect_shell_invocation_trace(trace: ShellInvocationTrace, ctx: GateContext) -> ShellInvocationTraceSignal`.
- [ ] `ShellPresenceSignal(passed: bool, details: dict[str, int | str])` and `ShellInvocationTraceSignal(passed: bool, retryable: bool, details: dict[str, str | int])` Pydantic models with `extra="forbid"`, `frozen=True`.
- [ ] `shell_presence`: `passed = (static_shell_binary_count == 0)`; the static shell binary path set is exactly `{"/bin/sh", "/bin/bash", "/bin/dash", "/bin/busybox", "/usr/bin/sh", "/usr/bin/bash"}` (frozenset constant in the module).
- [ ] `shell_invocation_trace` truth table covered by tests:
  - `confidence="high"`, `runtime_shell_count=0` → `passed=True, retryable=False`.
  - `confidence="medium"`, `runtime_shell_count=None` (budget exhaust) → `passed=False, retryable=True`.
  - `confidence="low"`, `runtime_shell_count=None` → `passed=False, retryable=True`.
  - `confidence="high"`, `runtime_shell_count=3` (observed shell) → `passed=False, retryable=False`.
  - `confidence="medium"`, `runtime_shell_count=2` (defensive: observed shell wins over confidence) → `passed=False, retryable=False`.
- [ ] **Intent tests**, one per signal: `test_shell_presence_emits_facts_not_judgments`, `test_shell_invocation_trace_signal_emits_facts_not_judgments` — both assert no `is_*|safe_*|recommended_*` field names; `passed`/`retryable` are accepted as the documented projection-rule fields (the test exempts them by explicit allowlist).
- [ ] Strict-AND lineage proof: a single-call test that passes a `dive_result` with `/bin/sh` in `final_layer_files` and asserts `passed is False`; a second test with no shells asserts `passed is True`.
- [ ] One-dive-invocation proof: the `shell_presence` collector body does **not** invoke `tools.dive.run` — its only input is the `DiveResult` parameter. Asserted by inspecting `inspect.getsource(collect_shell_presence)` and checking the regex `dive_run|tools\.dive` is absent. (Belt-and-braces against silent re-invocation.)
- [ ] `mypy --strict` + `ruff check` clean on both files.
- [ ] Fence-CI denies LLM-SDK imports under `sandbox/signals/` (S7-06) — neither file imports any.

## Implementation outline

1. `shell_presence.py`:
   ```python
   from codegenie.sandbox.signals import register_signal_kind
   from codegenie.sandbox.signals.models import ShellPresenceSignal
   from codegenie.tools.dive import DiveResult

   _STATIC_SHELL_PATHS = frozenset({
       "/bin/sh", "/bin/bash", "/bin/dash", "/bin/busybox",
       "/usr/bin/sh", "/usr/bin/bash",
   })

   @register_signal_kind("shell_presence")
   def collect_shell_presence(dive_result: DiveResult, ctx) -> ShellPresenceSignal:
       count = sum(1 for f in dive_result.final_layer_files if f.path in _STATIC_SHELL_PATHS)
       return ShellPresenceSignal(
           passed=(count == 0),
           details={"static_shell_binary_count": count},
       )
   ```
2. `shell_invocation_trace.py`:
   ```python
   from codegenie.probes.shell_invocation_trace import ShellInvocationTrace

   @register_signal_kind("shell_invocation_trace")
   def collect_shell_invocation_trace(trace: ShellInvocationTrace, ctx) -> ShellInvocationTraceSignal:
       observed_shell = (trace.runtime_shell_count or 0) > 0
       confidence_low = trace.confidence != "high"
       if observed_shell:
           return ShellInvocationTraceSignal(
               passed=False, retryable=False,
               details={"reason": "observed_shell", "runtime_shell_count": trace.runtime_shell_count},
           )
       if confidence_low:
           return ShellInvocationTraceSignal(
               passed=False, retryable=True,
               details={"reason": "budget_exhausted", "confidence": trace.confidence},
           )
       return ShellInvocationTraceSignal(
           passed=True, retryable=False,
           details={"runtime_shell_count": 0, "confidence": "high"},
       )
   ```
3. Ensure both modules are imported from `signals/__init__.py` so `@register_signal_kind` fires at package import.

## TDD plan — red / green / refactor

### Red — write the failing test first

Two test files. The load-bearing pair (truth-table + intent) goes first:

```python
# tests/unit/sandbox/signals/test_shell_invocation_trace_signal.py
import re
import pytest

from codegenie.probes.shell_invocation_trace import ShellInvocationTrace
from codegenie.sandbox.signals.shell_invocation_trace import (
    collect_shell_invocation_trace,
)
from codegenie.sandbox.signals.models import ShellInvocationTraceSignal

JUDGMENT_RE = re.compile(r"^(is_|safe_|recommended_).*")
_ALLOWED = {"passed", "retryable", "details"}

def _trace(*, confidence, runtime_shell_count):
    return ShellInvocationTrace(
        schema_version="v0.7.0",
        candidate_image_digest="sha256:" + "a" * 64,
        scenarios_run=["default"],
        runtime_shell_count=runtime_shell_count,
        traced_binaries=[],
        network_endpoints_touched=[],
        wall_clock_ms=1000,
        budget_ms=30000,
        confidence=confidence,
        confidence_reasons=[],
    )

@pytest.mark.parametrize("confidence,count,exp_passed,exp_retryable,exp_reason", [
    ("high",   0,    True,  False, None),
    ("medium", None, False, True,  "budget_exhausted"),
    ("low",    None, False, True,  "budget_exhausted"),
    ("high",   3,    False, False, "observed_shell"),
    ("medium", 2,    False, False, "observed_shell"),
])
def test_shell_trace_signal_truth_table(confidence, count, exp_passed, exp_retryable, exp_reason):
    sig = collect_shell_invocation_trace(_trace(confidence=confidence, runtime_shell_count=count), ctx=None)
    assert sig.passed is exp_passed
    assert sig.retryable is exp_retryable
    if exp_reason is not None:
        assert sig.details.get("reason") == exp_reason

def test_shell_invocation_trace_signal_emits_facts_not_judgments():
    field_names = list(ShellInvocationTraceSignal.model_fields.keys())
    offenders = [f for f in field_names if JUDGMENT_RE.match(f) and f not in _ALLOWED]
    assert offenders == [], f"forbidden judgment fields: {offenders}"
```

And the shell-presence counterpart:

```python
# tests/unit/sandbox/signals/test_shell_presence_signal.py
def test_shell_presence_passes_when_no_shells(): ...
def test_shell_presence_fails_when_bin_sh_present(): ...
def test_shell_presence_fails_when_busybox_present(): ...
def test_shell_presence_details_carries_count(): ...
def test_shell_presence_does_not_invoke_dive():
    import inspect
    from codegenie.sandbox.signals import shell_presence
    src = inspect.getsource(shell_presence.collect_shell_presence)
    assert "dive_run" not in src and "tools.dive" not in src
def test_shell_presence_emits_facts_not_judgments(): ...
```

Both fail on `ImportError` initially. Commit red.

### Green — make it pass

Implement the two collectors per the outline. The shell-presence one is ~10 lines; the trace one is ~15 lines. Use frozen Pydantic models; no mutation.

### Refactor — clean up

- Docstrings on each collector citing ADR-0013 for the asymmetric retry policy.
- Module-level `_STATIC_SHELL_PATHS` constant so the shell-binary list is one source of truth (and the contract-surface snapshot captures it).
- Confirm `details` keys are stable strings (no f-string interpolation, no timestamp).
- Per `phase-arch-design.md §Harness engineering ›Logging strategy`: emit one structured-log entry per signal-collection event; no raw bytes.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/sandbox/signals/shell_presence.py` | New — static-shell-binary projection on `DiveResult.final_layer_files`. |
| `src/codegenie/sandbox/signals/shell_invocation_trace.py` | New — strict-AND projection on `ShellInvocationTrace`; asymmetric retry. |
| `tests/unit/sandbox/signals/test_shell_presence_signal.py` | New — fixtures with/without shells + dive-not-re-invoked + intent. |
| `tests/unit/sandbox/signals/test_shell_invocation_trace_signal.py` | New — five-row truth table + intent. |
| `src/codegenie/sandbox/signals/__init__.py` | Additive import lines so both collectors register at package import. |

## Out of scope

- **The probe itself** — S3-02.
- **`tools/dive.py` invocation** — S2-03; this story consumes `DiveResult` from the dive signal pathway (one-dive-invocation property; see arch §Component 8).
- **`DiveSignal`** — S3-04.
- **`BaseImageSignal` + widening-compat test** — S3-06.
- **Phase 5's `StrictAndGate.evaluate` itself** — pre-existing; this story produces inputs to it.
- **ELF-symbol scanning** for shell-binary detection — non-goal #14; heuristic path names only (Phase 12+ may revisit).
- **Sidecar PID-share / idempotence integration coverage** — S3-03.

## Notes for the implementer

- The asymmetric retry policy is the load-bearing detail: budget exhaust gets retried (the candidate might have been slow-starting; Phase 5's three-retry budget gives it more wall-clock); an *observed* shell does **not** retry (the candidate genuinely shells out; retrying won't change that). If you find yourself writing `retryable=True` for both cases, re-read ADR-0013 §Decision.
- `runtime_shell_count` can be `None` (the probe sets it `None` whenever `confidence != "high"`). Treat `(trace.runtime_shell_count or 0) > 0` for the observed-shell check; **never** dereference `None`.
- The "defensive" row (`confidence="medium"`, `count=2`) is the case where the probe was uncertain but did observe a shell. Observed-shell wins over confidence — `passed=False, retryable=False`. The test parameterizes this row explicitly so the rule is encoded by failing tests, not just docstrings (Rule 9).
- The intent test allowlists `passed`, `retryable`, `details` — those are the documented projection-rule outputs, not judgments the probe wrote. The probe (S3-02) emits `runtime_shell_count` (a fact); this signal collector projects facts into a verdict (per ADR-0008, that's the gate's job, not the probe's).
- The `shell_presence` "no dive re-invocation" test uses `inspect.getsource` — it's brittle to refactors that legitimately rename `dive_run`. If you change the import name, update the test's allowed-substring list, but the *property* (no second dive invocation) must hold. The arch design is explicit: "one dive invocation, two signals."
- Don't over-detail the `details` dict. Keys must be stable strings the contract-surface snapshot can freeze; values can be ints/floats/strings. No nested objects (the model is `dict[str, int | str]` for `ShellPresenceSignal`).
- Both collectors are deterministic. No `random`, no `time`, no environment reads. Output depends only on inputs.
