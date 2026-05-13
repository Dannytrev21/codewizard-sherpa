# Story S1-01 — Add `gate_registry.py` module

**Step:** Step 1 — Establish the six additive seams, ADRs, and the contract-surface snapshot canary
**Status:** Ready
**Effort:** S
**Depends on:** —
**ADRs honored:** ADR-P7-001 (this phase ADR-0002), ADR-P7-005 (this phase ADR-0006), ADR-P7-013 (this phase ADR-0013), production ADR-0007

## Context

`ShellInvocationTraceProbe` is structurally a *gate-time* probe (it runs inside Phase 5's `run_in_sandbox` chokepoint), but Phase 2's `Probe` ABC is byte-frozen per production ADR-0007 and we may not add an `applies_to_lifecycle` field on it nor a coordinator branch. This story lands the smallest possible *pure-addition* seam — a brand-new module that holds a second registry — so later steps can register gate-time probes without touching Phase 2's ABC or coordinator. It is the first of the six named additive seams (ADR-0001) and the only one that is a literal new-file-only diff.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design — 3. gate_registry.py (NEW; ADR-P7-001)` (lines ~560–584) — canonical module shape, the ~30 LOC public interface, and the guarantees this seam preserves.
  - `../phase-arch-design.md §Component 2. ShellInvocationTraceProbe` — names this registry as the discovery surface used at gate time.
  - `../phase-arch-design.md §Component 13 ADR-P7-001` — recorded as *no edit*, pure file addition.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0002-register-gate-probe-new-registry.md` — ADR-P7-001 — the decision; Phase 2 coordinator must not import this module; double-registration last-wins; uniqueness enforced by a separate `name` test.
  - `../ADRs/0006-runtime-trace-probe-stub-kept-forever.md` — ADR-P7-005 — Phase 2's `RuntimeTraceProbe` stub stays as a no-op sibling in the *gather* registry; this story must not delete or modify it.
  - `../ADRs/0001-six-named-additive-seams-and-adr-0028-amendment.md` — ADR-P7-008 (in this phase: ADR-0001) — operational definition of behavior-preserving additive extension.
- **Production ADRs:**
  - `../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md` — Probe ABC contract preserved verbatim; nothing in this story may edit `src/codegenie/probes/base.py`.
- **Source design:**
  - `../final-design.md §"Departures from all three inputs" #1` — names this module as a synthesis-original.
- **Existing code (read before writing):**
  - `src/codegenie/probes/base.py` — the `Probe` ABC the new registry imports from; do not modify.
  - `src/codegenie/probes/__init__.py` and existing `@register_probe` accessor — copy the decorator/accessor style so the gate registry reads as a sibling, not a parallel design.
  - `src/codegenie/coordinator.py` (or wherever Phase 2's coordinator lives) — read once so the isolation test in this story is wired against the *actual* `all_probes()` symbol.

## Goal

`src/codegenie/probes/gate_registry.py` exists, exports `register_gate_probe` and `all_gate_probes`, and a test proves the Phase 2 gather-time coordinator's `all_probes()` never returns gate probes.

## Acceptance criteria

- [ ] `src/codegenie/probes/gate_registry.py` exists with the exact interface from `phase-arch-design.md §Component 3` (`register_gate_probe(cls) -> cls`, `all_gate_probes() -> Sequence[type[Probe]]`, module-level `_GATE_PROBES: list[type[Probe]]`).
- [ ] The module imports only from `collections.abc` and `.base` (Phase 2 `Probe` ABC); no import of `codegenie.coordinator` and no transitive import of it via `__init__.py` (verified by a static import-graph test or `importlib`-based runtime check).
- [ ] `tests/unit/probes/test_gate_registry.py` is committed and green: (a) `@register_gate_probe` returns the class unchanged; (b) the decorated class appears in `all_gate_probes()`; (c) `all_gate_probes()` returns a tuple (immutable view), not a list; (d) a uniqueness-by-`name` assertion flags two distinct classes registered under the same `name` attribute.
- [ ] `tests/unit/probes/test_gate_registry_isolation.py` is committed and green: registers a throwaway `_Sentinel(Probe)` with `@register_gate_probe` and asserts it is **not** present in the Phase 2 coordinator's `all_probes()` return value (the symbol Phase 2 uses today; resolve it by reading `coordinator.py` first).
- [ ] `src/codegenie/probes/base.py` byte-stable: `sha256` of the file is unchanged from `master` (this story does not edit it).
- [ ] `ruff check`, `ruff format --check`, and `mypy --strict` pass on `src/codegenie/probes/gate_registry.py` and both test files.

## Implementation outline

1. Read `src/codegenie/probes/base.py` and the existing gather-time registry decorator/accessor in `src/codegenie/probes/__init__.py` (or wherever it lives in Phase 2) — copy the style verbatim.
2. Write the failing tests in `tests/unit/probes/test_gate_registry.py` and `tests/unit/probes/test_gate_registry_isolation.py` (TDD red).
3. Add `src/codegenie/probes/gate_registry.py` matching the public interface above (TDD green).
4. Confirm `Probe` ABC source byte unchanged; run `mypy --strict` and ruff on the touched scope.
5. Refactor: add module + function docstrings citing ADR-P7-001 and the no-coordinator-import rule; ensure the uniqueness test gives an actionable error message.

## TDD plan — red / green / refactor

### Red — write the failing tests first

Test files:
- `tests/unit/probes/test_gate_registry.py`
- `tests/unit/probes/test_gate_registry_isolation.py`

```python
# tests/unit/probes/test_gate_registry.py
from codegenie.probes.base import Probe
from codegenie.probes.gate_registry import register_gate_probe, all_gate_probes


def test_register_gate_probe_returns_class_unchanged():
    @register_gate_probe
    class _G(Probe):
        name = "g_test_1"
        applies_to_tasks = ["distroless_migration"]
        applies_to_languages = ["*"]
        declared_inputs = ()
        def run(self, view):  # type: ignore[override]
            raise NotImplementedError

    assert _G.__name__ == "_G"
    assert _G in all_gate_probes()


def test_all_gate_probes_is_immutable_view():
    result = all_gate_probes()
    assert isinstance(result, tuple)  # not list — callers cannot mutate the registry


def test_double_registration_with_same_name_is_flagged_by_uniqueness_test():
    # Two distinct classes with the same `name` attribute must be detectable.
    # The uniqueness check itself lives in this test, not in the registry.
    @register_gate_probe
    class _A(Probe):
        name = "g_dup"
        # ... required ABC fields

    @register_gate_probe
    class _B(Probe):
        name = "g_dup"

    names = [p.name for p in all_gate_probes()]
    duplicates = {n for n in names if names.count(n) > 1}
    assert "g_dup" in duplicates  # surfaces the collision; registry itself does not raise
```

```python
# tests/unit/probes/test_gate_registry_isolation.py
from codegenie.probes.base import Probe
from codegenie.probes.gate_registry import register_gate_probe
# import the *actual* gather-time accessor Phase 2 uses; read coordinator.py first.
from codegenie.probes import all_probes  # or wherever it lives


def test_gate_probes_invisible_to_phase2_coordinator():
    @register_gate_probe
    class _GateSentinel(Probe):
        name = "gate_sentinel_isolation"
        # ... required ABC fields

    gather = {p.name for p in all_probes()}
    assert "gate_sentinel_isolation" not in gather
```

Expected red failure mode: `ImportError: cannot import name 'register_gate_probe' from 'codegenie.probes.gate_registry'` (module does not exist yet) on every test.

### Green — make it pass

Create `src/codegenie/probes/gate_registry.py` with exactly the shape in `phase-arch-design.md §Component 3`:

- Module-level `_GATE_PROBES: list[type[Probe]] = []`.
- `register_gate_probe(cls)` appends `cls` and returns it.
- `all_gate_probes()` returns `tuple(_GATE_PROBES)`.

Do not import anything from `codegenie.coordinator`. Do not re-export from `src/codegenie/probes/__init__.py` unless Phase 2's existing `__init__.py` already re-exports `register_probe` — match precedent.

### Refactor — clean up

- Module docstring naming ADR-P7-001 and the rule "the Phase 2 coordinator does not import this module."
- Function docstrings linking `phase-arch-design.md §Component 3`.
- Confirm `mypy --strict` produces no `Any` leakage in `Sequence[type[Probe]]`.
- If the existing gather registry has a similar uniqueness test, mirror its structure here so the two registries read in parallel.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/probes/gate_registry.py` | New file — implements the gate-probe registry (ADR-P7-001). |
| `tests/unit/probes/test_gate_registry.py` | New test — anchors the TDD red phase; covers register/accessor/uniqueness. |
| `tests/unit/probes/test_gate_registry_isolation.py` | New test — asserts Phase 2 `all_probes()` cannot see gate probes. |

## Out of scope

- **`ShellInvocationTraceProbe` implementation** — handled by S3-02. This story lands the registry only; no gate probes are registered by Phase 7's seam PR itself.
- **`GateRunner` integration that reads `all_gate_probes()`** — Phase 5's gate runner is unchanged in this PR; consumers are wired in Step 3 / Step 5.
- **Contract-surface snapshot regen capturing this decorator's signature** — handled by S1-07, which is what the dependency arrow `S1-01 → S1-07` represents.
- **Re-export from `src/codegenie/probes/__init__.py`** — only do it if Phase 2's `__init__.py` already re-exports the gather decorator; otherwise leave the import explicit (`from codegenie.probes.gate_registry import ...`).

## Notes for the implementer

- The registry must *not* import the Phase 2 coordinator — that would create a circular dependency and silently couple the two lifecycles. If you find yourself wanting to import it (e.g., to share a uniqueness check), stop and re-read ADR-P7-001's rationale.
- `all_gate_probes()` returns a tuple, not a list, because callers must not mutate the registry. This is checked by the test above; if you return the list directly, the test fails on `isinstance(result, tuple)`.
- Double-registration is allowed at the registry level (the architecture says "decorator never raises; double-registration is allowed (last wins)"). The *uniqueness-by-name* check lives in test code, not in the registry. Do not raise from the decorator.
- The `_Sentinel(Probe)` test class in the isolation test must satisfy whatever required `Probe` ABC fields exist today — read `src/codegenie/probes/base.py` before writing the test to confirm `name`, `applies_to_tasks`, `applies_to_languages`, `declared_inputs`, and `run` are all that's needed.
- This story is intentionally tiny. If you find yourself touching more than `gate_registry.py` plus two test files, you have drifted out of scope — see ADR-P7-001's "no edit to Phase 2 coordinator" line.
- Phase 2's `RuntimeTraceProbe` stub (ADR-P7-005) remains in the gather registry untouched. Do not delete it; a downstream test (in S3-02 or later) verifies it still resolves to `applies() == False`.
