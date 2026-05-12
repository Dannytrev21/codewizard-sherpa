# Story S4-04 — Phase 3 `TrustScorer` open signal-kind registry widening

**Step:** Step 4 — Six signal collectors + StrictAndGate adapter
**Status:** Ready
**Effort:** S
**Depends on:** S1-05 (`@register_signal_kind` registry pattern is the template)
**ADRs honored:** ADR-0003, ADR-0014

## Context

Phase 3 already ships a `TrustScorer` implementing strict-AND of objective signals per production ADR-0008. Phase 5 introduces three new signal kinds (`trace`, `policy`, `cve_delta`) that Phase 3 doesn't yet know about. ADR-0003 forbids replacing Phase 3's scorer; the canonical design is to widen Phase 3's existing kind registry via `@register_trust_signal_kind`. This story confirms the registry exists in Phase 3 (architect Risk #6) and registers the three new kinds. **If Phase 3 lacks an open registry, this story expands to land one first — and surfaces an ADR-0003 amendment** before downstream work can proceed.

## References — where to look

- **Architecture:** `../phase-arch-design.md §Component design — `Gate` (ABC) + `StrictAndGate`` — "New signal kinds (`trace`, `policy`, `cve_delta`) register against Phase 3's existing kind extension point (ADR-P5-003)."
- **Architecture:** `../phase-arch-design.md §Risk register — Risk #6` — "Phase 3 `TrustScorer` signal-kind extension point doesn't actually exist or is closed. … confirm Phase 3 has an open registry (e.g., `@register_trust_signal_kind`) before Step 4 starts. If not, add it as a Step 4a (Phase 3 amendment) before Step 4 — keeps 'extension by addition' honest."
- **Phase ADRs:** `../ADRs/0003-trustscorer-extension-via-signal-kind-registry.md` — ADR-0003 — `TrustSignal.kind` widens from closed `Literal[...]` to open string keyed by registry; collision policy is `SignalKindAlreadyRegistered` at import (Open Q10).
- **Production ADRs:** `../../../production/adrs/0008-objective-signal-trust-score.md` — Phase 3 strict-AND contract this widens.
- **Existing code:** `src/codegenie/trust/` (Phase 3) — `TrustScorer`, `TrustSignal`. **Verify shape during the spike step (below).**
- **Existing code:** `src/codegenie/sandbox/signals/registry.py` (S1-05) — Phase 5's `@register_signal_kind`; this story's Phase 3 registry should mirror its shape.

## Goal

Confirm (or land) Phase 3's `@register_trust_signal_kind` open registry and register the three new kinds (`trace`, `policy`, `cve_delta`) against it so the `StrictAndGate` adapter (S4-05) can materialize them without editing Phase 3 internals.

## Acceptance criteria

- [ ] **Spike step (must run first):** Read `src/codegenie/trust/*` and capture in the story `_attempts/S4-04.md` log whether `@register_trust_signal_kind` already exists. If yes, this story is registration-only. If no, expand to land the registry in Phase 3 with a deprecation-free additive change AND open an ADR-0003 amendment note.
- [ ] `TrustSignal.kind` is an open `str` (not a closed `Literal[...]`) keyed by the `@register_trust_signal_kind` registry; Phase 3's contract-snapshot test regenerates (or this story documents the regeneration).
- [ ] `src/codegenie/sandbox/signals/trust_registration.py` registers the three new kinds: `trace`, `policy`, `cve_delta`. Each registration is one line: `register_trust_signal_kind("trace")`, etc.
- [ ] The pre-existing kinds (`build`, `install`, `tests`) remain registered (either by Phase 3 or — if newly added — by this same module's call sites). No existing kind is renamed or removed.
- [ ] Duplicate registration of the same kind raises `SignalKindAlreadyRegistered` at import time (Open Q10 — fail-loud collision policy).
- [ ] `tests/integration/test_trustscorer_widening.py` proves: (a) Phase 3's strict-AND still passes with only `build/install/tests` populated; (b) the three new kinds participate in strict-AND without changing `TrustScorer` internals; (c) a `TrustSignal` with `kind="not_registered"` raises a structured error at scoring time (or at materialization, depending on where the registry check lives — pick one and document).
- [ ] Property test: for any subset `S ⊆ {build, install, tests, trace, policy, cve_delta}`, if every signal in `S` has `passed=True`, `TrustScorer.score([...]).passed == True`; if any signal has `passed=False`, `TrustScorer.score([...]).passed == False`. (Strict-AND invariant preservation.)
- [ ] `tests/schema/test_objective_signals_static.py` still green — no banned substring entered any field reachable from `ObjectiveSignals` (defense-in-depth: this story does NOT modify `ObjectiveSignals` but its fixtures must not introduce a banned key).
- [ ] No edits to existing Phase 3 `TrustScorer.score(...)` logic. The widening is registry-only.
- [ ] TDD plan's red test exists, is committed, and is green.
- [ ] `ruff`, `mypy --strict`, `pytest` pass on touched files.

## Implementation outline

1. **Spike** (record findings in `_attempts/S4-04.md`):
   - Inspect `src/codegenie/trust/` for an existing `register_trust_signal_kind` decorator.
   - If present, capture its signature and import path. Skip to step 3.
   - If absent, write Phase 3 the registry: a module-level dict `_KINDS: dict[str, _SignalKindRec]` keyed by kind name, a `register_trust_signal_kind(kind: str)` function with collision check, and a `is_registered(kind: str) -> bool` helper. **Additive only.** Do not rename `TrustSignal.kind` if it's already `str`; if it's a closed `Literal`, widen it to `str` and regenerate the contract snapshot.
2. Create `src/codegenie/sandbox/signals/trust_registration.py`:
   ```python
   from codegenie.trust.registry import register_trust_signal_kind
   register_trust_signal_kind("trace")
   register_trust_signal_kind("policy")
   register_trust_signal_kind("cve_delta")
   ```
   Import this module from `src/codegenie/sandbox/signals/__init__.py` so the registrations fire on package import.
3. Write `tests/integration/test_trustscorer_widening.py` exercising the strict-AND invariant across the cartesian product of populated/unpopulated × passed/failed.
4. If the spike landed Phase 3 changes, add a Phase 3 contract-snapshot regen line to the PR description; flag ADR-0003 amendment requirement.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/integration/test_trustscorer_widening.py`

```python
# tests/integration/test_trustscorer_widening.py
import pytest
from hypothesis import given, strategies as st

from codegenie.trust.registry import (
    register_trust_signal_kind,
    is_registered,
    SignalKindAlreadyRegistered,
)
from codegenie.trust.scorer import TrustScorer, TrustSignal
# Importing this module is what triggers the three new registrations.
import codegenie.sandbox.signals.trust_registration  # noqa: F401


ALL_KINDS = ["build", "install", "tests", "trace", "policy", "cve_delta"]


def test_three_new_kinds_registered_after_import():
    # WHY: Phase 5's contract — trace/policy/cve_delta participate in strict-AND
    #      without editing TrustScorer internals.
    for kind in ("trace", "policy", "cve_delta"):
        assert is_registered(kind), f"{kind} not registered"


def test_pre_existing_kinds_still_registered():
    for kind in ("build", "install", "tests"):
        assert is_registered(kind)


def test_duplicate_registration_raises_signal_kind_already_registered():
    # WHY: Open Q10 — fail-loud collision policy. Silent overwrite would let
    #      Phase 7 distroless accidentally shadow a Phase 5 kind.
    with pytest.raises(SignalKindAlreadyRegistered):
        register_trust_signal_kind("trace")  # already registered above


def test_unknown_kind_in_trust_signal_rejected():
    # WHY: TrustSignal.kind is widened to open str — but the scorer must reject
    #      kinds the registry doesn't know about, to prevent silent kind typos.
    bad = TrustSignal(kind="not_registered", passed=True, details={})
    with pytest.raises(ValueError):
        TrustScorer().score([bad])


def test_strict_and_holds_with_all_six_kinds_passing():
    signals = [TrustSignal(kind=k, passed=True, details={}) for k in ALL_KINDS]
    outcome = TrustScorer().score(signals)
    assert outcome.passed is True


def test_strict_and_fails_when_any_single_kind_fails():
    # WHY: strict-AND invariant; if Phase 3 ever drifts to weighted scoring,
    #      this test screams.
    for fail_idx in range(len(ALL_KINDS)):
        signals = [
            TrustSignal(kind=k, passed=(i != fail_idx), details={})
            for i, k in enumerate(ALL_KINDS)
        ]
        assert TrustScorer().score(signals).passed is False


@given(st.lists(st.sampled_from(ALL_KINDS), min_size=1, max_size=6, unique=True),
       st.lists(st.booleans(), min_size=1, max_size=6))
def test_strict_and_property_holds_for_any_subset(kinds, passes):
    # WHY: extension-by-addition — the strict-AND invariant must hold across
    #      arbitrary subsets and arbitrary passed/failed combinations.
    n = min(len(kinds), len(passes))
    signals = [TrustSignal(kind=k, passed=p, details={}) for k, p in zip(kinds[:n], passes[:n])]
    expected = all(p for p in passes[:n])
    assert TrustScorer().score(signals).passed == expected
```

### Green — make it pass

- If spike confirmed registry exists: just add `trust_registration.py`. The tests should green immediately.
- If spike required adding the registry: implement `codegenie.trust.registry` (module-level dict, `register_trust_signal_kind`, `is_registered`, `SignalKindAlreadyRegistered` exception), wire `TrustScorer.score` to validate `signal.kind` via `is_registered`, regen contract snapshot, then add `trust_registration.py`.

### Refactor — clean up

- Keep `trust_registration.py` to three lines. If you find logic creeping in, put it in `codegenie.trust.registry` instead — Phase 5 owns *registration*, not *registry mechanics*.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/sandbox/signals/trust_registration.py` | Three-line registrations for new kinds. |
| `src/codegenie/sandbox/signals/__init__.py` | Import the registration module so it fires on package import. |
| `src/codegenie/trust/registry.py` | **Conditional** — only if spike found Phase 3 lacks an open registry. |
| `src/codegenie/trust/scorer.py` | **Conditional** — only if `TrustSignal.kind` needs widening. |
| `tests/integration/test_trustscorer_widening.py` | All seven cases. |
| `_attempts/S4-04.md` | Spike findings — registry-present or registry-added decision and evidence. |

## Out of scope

- Building the `StrictAndGate` adapter — S4-05.
- The signal collectors themselves — S4-01, S4-02, S4-03.
- Threshold calibration (production ADR-0015) — Phase 5 is strict-AND only; calibration is future-phase per ADR-0003's Consequences §5.

## Notes for the implementer

1. **Read Phase 3 before you write.** Architect Risk #6 explicitly flags this. The spike step is not optional — if the registry already exists, this story is 5 minutes plus tests.
2. Collision policy is **fail-loud** (Open Q10 default). A second `register_trust_signal_kind("trace")` must raise, not silently overwrite. Phase 7 distroless will rely on this guarantee.
3. `TrustSignal.kind: str` — open, not `Literal`. The type system no longer enumerates kinds; the registry does, at import time. This is an explicit ADR-0003 tradeoff (gain: extension by addition; cost: weaker static typing).
4. Do **not** edit `TrustScorer.score(...)` logic. The widening is registry-only. Strict-AND is preserved.
5. If you widen `TrustSignal.kind` from `Literal[...]` to `str`, Phase 3's contract-snapshot test will fail. That's expected — regen the snapshot and call it out in the PR description.
6. If Phase 3 has *no* registry mechanism at all and you must land one, this story balloons. Surface it in your spike log AND open a follow-up ADR-0003 amendment noting the Phase-3 surgery; that's load-bearing for ADR transparency.
