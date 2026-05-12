# Story S1-03 — `ObjectiveSignals` + six sub-models + `SignalProvenance`

**Step:** Step 1 — Scaffold packages, contracts, and CI fences
**Status:** Ready
**Effort:** M
**Depends on:** S1-01
**ADRs honored:** ADR-0014, ADR-0008, ADR-0015, ADR-0003

## Context

`ObjectiveSignals` is the strict-AND input — the model that every Phase 5 trust decision derives from. ADR-0014 mandates `extra="forbid", frozen=True` plus a static-introspection CI test asserting no field name reachable from `ObjectiveSignals` contains `confidence`, `llm`, `self_reported`, or `model_says`. This story ships the model family with that invariant baked in by construction; the fence test that polices it permanently lands in S1-07.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Data model — sandbox/signals/models.py` — full pseudo-code for `SignalProvenance`, `_SignalBase`, six sub-models, `ObjectiveSignals`.
  - `../phase-arch-design.md §Component design — SandboxSpec / SandboxRun / ObjectiveSignals` — `details: dict[str, str|int|bool]`; no float, no nested dict, no list as value type.
  - `../phase-arch-design.md §Agentic best practices — Confidence handling for ADR-0008` — the explicit rename `coverage_confidence` → `coverage_evidence_strength` (Open Q9).
  - `../phase-arch-design.md §Edge cases 6, 7` — `delta_test_count` semantics consumed by `TestSignal.details`.
  - `../phase-arch-design.md §CI gates` — `tests/schema/test_objective_signals_static.py` recursively walks every field reachable from `ObjectiveSignals` (this story produces the surface that walk traverses).
- **Phase ADRs (rules this story honors):**
  - `../ADRs/0014-objectivesignals-extra-forbid-static-introspection.md` — ADR-0014 — `extra="forbid", frozen=True`; no banned substrings; `details` value type strictly `str | int | bool`.
  - `../ADRs/0008-llm-judge-persona-deferral.md` — ADR-0008 — no LLM judgment fields anywhere in this graph.
  - `../ADRs/0015-test-inventory-delta-asymmetric-policy.md` — ADR-0015 — `TestSignal.details["delta_test_count"]` is an `int`, always emitted, even when zero.
  - `../ADRs/0003-trustscorer-extension-via-signal-kind-registry.md` — ADR-0003 — adding a new optional field requires an ADR amendment; the model is *additively* extensible.
- **Production ADRs:**
  - `../../../production/adrs/0008-objective-signal-trust-score.md` — strict-AND lineage; this is what ADR-0014 enforces.
- **Source design:**
  - `../final-design.md §Component-2 — ObjectiveSignals` — load-bearing commitments §2.2.

## Goal

Ship `src/codegenie/sandbox/signals/models.py` with `SignalProvenance`, an internal `_SignalBase`, six concrete frozen `extra="forbid"` sub-models (`BuildSignal`, `InstallSignal`, `TestSignal`, `TraceSignal`, `PolicySignal`, `CveDeltaSignal`), and the `ObjectiveSignals` container — with no field name (transitively) containing a forbidden substring.

## Acceptance criteria

- [ ] `from codegenie.sandbox.signals.models import ObjectiveSignals, BuildSignal, InstallSignal, TestSignal, TraceSignal, PolicySignal, CveDeltaSignal, SignalProvenance` succeeds.
- [ ] Every concrete model carries `model_config = ConfigDict(extra="forbid", frozen=True)`; constructing with an unknown field raises `ValidationError`; mutation post-construction raises `ValidationError`.
- [ ] Each sub-model has fields `passed: bool`, `details: dict[str, str | int | bool]`, `provenance: SignalProvenance`, `at: datetime` and nothing else.
- [ ] `details` value type rejects `float`, `list`, nested `dict`, `None`, and `bytes` at construction (parametrized `ValidationError` test).
- [ ] `ObjectiveSignals` has exactly six optional fields (`build`, `install`, `tests`, `trace`, `policy`, `cve_delta`); each defaults to `None`; all six can be `None`; all six can be populated.
- [ ] Recursive field-name introspection from `ObjectiveSignals.model_fields` (walking into sub-model fields, value-dict key annotations, and `SignalProvenance`) contains no substring from `{"confidence", "llm", "self_reported", "model_says"}` — TDD red test enforces this in-story (the structural fence in `tests/schema/` lands in S1-07; both must pass).
- [ ] `TestSignal` constructed with `details={"delta_test_count": 0}` succeeds; with `details={"delta_test_count": -1}` succeeds (the *gate logic* that flips `passed=False` lives in S4-02, not here).
- [ ] TDD plan's red tests exist, are committed, and are green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict src/codegenie/sandbox/signals/models.py`, `pytest tests/sandbox/test_signal_models.py tests/sandbox/test_objective_signals_introspection.py` all pass.
- [ ] Branch coverage on `signals/models.py` ≥ 95% (95/90 floor from `stories/README.md`).

## Implementation outline

1. Create `src/codegenie/sandbox/signals/__init__.py` (empty package marker).
2. Create `src/codegenie/sandbox/signals/models.py`.
3. Define `SignalProvenance` (`signal_kind: str`, `collector_module: str`, `collector_version: str`, `inputs_blake3: str`) with frozen + extra-forbid.
4. Define `_SignalBase(BaseModel)` (internal — leading underscore, NOT re-exported via `__all__`). Fields: `passed`, `details: dict[str, str | int | bool]`, `provenance`, `at`.
5. Subclass six sub-models — each is `class BuildSignal(_SignalBase): pass` plus its own `model_config` (Pydantic v2 subclasses do not auto-inherit `model_config`; verify and set explicitly).
6. Define `ObjectiveSignals` with six `<kind>: <Submodel> | None = None` fields and frozen + extra-forbid.
7. Write the two tests; verify recursive introspection catches a `confidence` field if introduced.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file paths: `tests/sandbox/test_signal_models.py`, `tests/sandbox/test_objective_signals_introspection.py`.

```python
# tests/sandbox/test_signal_models.py
from datetime import datetime, timezone
import pytest
from pydantic import ValidationError
from codegenie.sandbox.signals.models import (
    SignalProvenance, BuildSignal, InstallSignal, TestSignal,
    TraceSignal, PolicySignal, CveDeltaSignal, ObjectiveSignals,
)

def _prov(kind="build"):
    return SignalProvenance(
        signal_kind=kind, collector_module="codegenie.sandbox.signals.build",
        collector_version="0.1.0", inputs_blake3="0" * 32,
    )

def _build(**overrides):
    base = dict(passed=True, details={}, provenance=_prov(), at=datetime.now(timezone.utc))
    base.update(overrides)
    return BuildSignal(**base)

def test_signal_is_frozen():
    s = _build()
    with pytest.raises(ValidationError):
        s.passed = False

def test_signal_rejects_unknown_field():
    with pytest.raises(ValidationError):
        _build(extra_field="boom")

@pytest.mark.parametrize("bad_value", [3.14, [1, 2], {"nested": "x"}, None, b"bytes"])
def test_details_rejects_non_primitive(bad_value):
    with pytest.raises(ValidationError):
        _build(details={"k": bad_value})

def test_details_accepts_str_int_bool():
    s = _build(details={"s": "v", "i": 7, "b": True})
    assert s.details == {"s": "v", "i": 7, "b": True}

def test_test_signal_carries_delta_test_count_int():
    s = TestSignal(passed=True, details={"delta_test_count": 0},
                   provenance=_prov("tests"), at=datetime.now(timezone.utc))
    assert s.details["delta_test_count"] == 0

def test_objective_signals_all_fields_optional_default_none():
    os = ObjectiveSignals()
    assert os.build is None and os.install is None and os.tests is None
    assert os.trace is None and os.policy is None and os.cve_delta is None

def test_objective_signals_rejects_unknown_kind():
    with pytest.raises(ValidationError):
        ObjectiveSignals(baseimage=_build())  # not yet a kind; ADR-0003 widens additively
```

```python
# tests/sandbox/test_objective_signals_introspection.py
"""In-story sibling of tests/schema/test_objective_signals_static.py (S1-07).
   Asserts the ADR-0014 invariant at the place where the surface is defined."""
from codegenie.sandbox.signals.models import ObjectiveSignals

FORBIDDEN = ("confidence", "llm", "self_reported", "model_says")

def _walk_field_names(model_cls, visited=None):
    visited = visited or set()
    if model_cls in visited:
        return
    visited.add(model_cls)
    for name, field in model_cls.model_fields.items():
        yield name
        ann = field.annotation
        # Recurse into nested BaseModel types; descend into dict value annotations too.
        # Implementation belongs in green; test asserts behaviour against the public surface.
        yield from _yield_nested(ann, visited)

def _yield_nested(ann, visited):
    # Helper imported from the real walker module after green is done.
    from codegenie.sandbox.signals.models import _iter_nested_field_names
    yield from _iter_nested_field_names(ann, visited)

def test_no_field_name_contains_forbidden_substring():
    names = list(_walk_field_names(ObjectiveSignals))
    for n in names:
        for bad in FORBIDDEN:
            assert bad not in n.lower(), f"forbidden substring {bad!r} in field {n!r}"
```

Run; confirm `ImportError` on members (and on `_iter_nested_field_names`), commit, then implement.

### Green — make it pass

Implement `SignalProvenance`, `_SignalBase`, six sub-models, `ObjectiveSignals`. Also ship a small public helper `_iter_nested_field_names(annotation, visited)` in the same module — the recursive walker the introspection test reuses (and that S1-07's fence test will reuse). The walker descends into:
- Pydantic `BaseModel` subclasses (recurses into their `model_fields`).
- `Optional[X]` / `Union[X, None]` (descends into `X`).
- `dict[K, V]` (yields no extra names — but the *types* `K, V` are walked because forbidden substrings could be hidden in Literal-keyed dicts in future kinds).
- `Literal[...]` (no field names).

The walker yields **field names** (strings); the assertion is substring-based. Do not yield value strings.

### Refactor — clean up

- Each sub-model needs its own `model_config = ConfigDict(extra="forbid", frozen=True)` line; verify on Pydantic 2 that `_SignalBase`'s config does not auto-inherit reliably across all checks. Best practice: be explicit.
- Add `__all__` listing the seven public names plus `SignalProvenance`. Do not export `_SignalBase` or `_iter_nested_field_names` from the package `__init__.py`.
- Edge case (arch §Edge case 7): `delta_test_count > 0` is informational — this story does *not* enforce that; the sub-model just stores the int. The asymmetric policy lives in `collect_test_signal` (S4-02).
- Edge case: `TraceSignal.details["coverage_evidence_strength"]` is the renamed field per ADR-0014 / Open Q9 — add a docstring on `TraceSignal` noting the rename.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/sandbox/signals/__init__.py` | New file — package marker |
| `src/codegenie/sandbox/signals/models.py` | New file — `ObjectiveSignals` family with ADR-0014 enforcement by construction |
| `tests/sandbox/test_signal_models.py` | New test — extra-forbid / frozen / `details` value-type policy |
| `tests/sandbox/test_objective_signals_introspection.py` | New test — local mirror of the ADR-0014 fence; runs before S1-07 fence lands |

## Out of scope

- **The structural CI fence test under `tests/schema/`** — lands in S1-07 (`test_objective_signals_static.py`). This story ships the same logic *inside* the sandbox test tree as an in-story assertion.
- **Signal collectors (`collect_build_signal`, etc.)** — Step 4.
- **`@register_signal_kind` decorator** — S1-05.
- **`StrictAndGate.evaluate`** — S4-05.
- **Asymmetric `delta_test_count < 0` failure logic** — S4-02 + ADR-0015.

## Notes for the implementer

- Six sub-models all subclass `_SignalBase`. There is real risk that Pydantic v2 does not propagate `model_config` reliably to subclasses across all field-resolution paths — set `model_config` explicitly on each. Hypothesis-test: construct each sub-model with an extra field; all six must raise.
- `details: dict[str, str | int | bool]` — Pydantic 2 will accept this annotation. Confirm that `dict[str, str | int | bool]` actually rejects `float` values; Pydantic 2.x has accepted floats coerced to int in some versions — write the parametrized test FIRST, watch it fail or pass on `float`, then enforce explicitly via a `field_validator` if Pydantic permits.
- `_iter_nested_field_names` should be carefully written: use `typing.get_args` and `typing.get_origin`; handle `Union`, `Optional`, `Literal`, generic `dict`/`list`. The static fence test in S1-07 will reuse this helper — keep the API small and stable.
- ADR-0014 is the most-attacked invariant in the phase. If your in-story test passes but you suspect the walker is shallow, add a synthetic test: create a throwaway model with a `confidence: str` field, plug it into a temporary `Foo: confidence_signal | None = None` sibling of `ObjectiveSignals`, and confirm the walker yields `"confidence_signal"`. (Remove the synthetic before committing.)
- This is one of two modules with the 95/90 coverage floor. Cover: each sub-model frozen, each sub-model extra-forbid, each forbidden value type, the introspection walker on a populated and an empty `ObjectiveSignals`.
- Do not import anything from `sandbox/contract.py` here — `ObjectiveSignals` lives upstream of any sandbox `SandboxRun`; the dependency runs the other way (collectors consume `SandboxRun` and produce signals).
