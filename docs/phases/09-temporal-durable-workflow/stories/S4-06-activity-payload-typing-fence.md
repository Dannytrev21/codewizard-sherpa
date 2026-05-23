# Story S4-06 — Activity-payload-typing fence

**Step:** Step 4 — Activity catalog (one file per activity, typed in and out, registry-collected)
**Status:** Ready
**Effort:** S
**Depends on:** S4-02 (`emit_event`, `write_blob_ref`, `resolve_blob_ref` registered — first three activities the fence introspects)
**ADRs honored:** ADR-0008 (typed-credential blocklist at seal; layered defense — fence is the static-check layer); ADR-0010 (every Activity carries the same input/output discipline regardless of granularity); production ADR-0043 ("extension by addition means no silent edits" — adding a new Activity requires its typed input/output to pass this fence)

## Context

Phase 9's secret-redaction defense is **three layers in order**:
1. **Static** — `mypy --strict` catches an unsealed return at type-check time (the return annotation declares `RedactedActivityResult`-derived; an unsealed value mismatches).
2. **Runtime at seal** — `RedactedActivityResult.seal()` applies the typed-credential-class blocklist + value-shape regex backstop (S3-06).
3. **Structural fence** — this story. `tests/fence/test_activity_payload_typing.py` introspects every `@activity.defn`-decorated function via `inspect.get_type_hints` and asserts inputs are `BaseModel`-derived (`frozen=True, extra="forbid"`) and outputs are `RedactedActivityResult`-derived. The fence catches the case where a contributor writes a `dict[str, Any]` input or returns a naked dict and gets a `# type: ignore` past mypy.

ADR-0004's "three layers, each independently sufficient, none on a single trust path" pattern applies here. mypy can be bypassed with `# type: ignore`; the seal can be skipped by returning an `RedactedActivityResult`-DERIVED class without calling `.seal()` (constructing it directly); the fence is the third layer that catches both.

**Scope reminder.** This story ships ONLY the fence test. The activities the fence introspects already exist (S4-02 has the first three; S4-03..S4-05 add six more). The story land**s before** all activities are in place — that's intentional: the fence MUST be green for each activity story's commit. Today (when S4-02 is the only shipped story), the fence covers 3 activities; tomorrow (after S4-05), the fence covers 9. The fence's introspection is dynamic via `_ACTIVITIES`; it auto-extends.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §C2 — Activity catalog` line 482-483 — "Each activity … returns a `RedactedActivityResult`-derived type (enforced by `tests/fence/test_activity_payload_typing.py`)."
  - `../phase-arch-design.md §Typed state contracts` (line 932) — "Activity inputs/outputs are Pydantic models with `frozen=True, extra="forbid"`; events are the 21-variant discriminated union. No `dict[str, Any]` on any workflow ↔ activity boundary. `tests/fence/test_activity_payload_typing.py` introspects every `@activity.defn`-decorated function and asserts inputs and outputs are `BaseModel`-derived."
  - `../phase-arch-design.md §Sequence diagrams Scenario 4` (lines 416-431) — adversarial: secret in activity return; "`tests/fence/test_activity_payload_typing.py` also rejects (return type is not RedactedActivityResult-derived)" is the structural-layer defense.
- **Phase ADRs:**
  - `../ADRs/0008-typed-credential-blocklist-not-regex.md` §Decision row 25: "three layers in order: (a) Pydantic `extra="forbid"`; (b) typed-credential-class blocklist; (c) value-shape regex backstop." This fence is the static counterpart of layer (a) — it asserts the `extra="forbid"` shape at design time.
  - `../ADRs/0004-workflow-determinism-enforcement-three-layers.md` — the layered-defense pattern adapted from workflow-determinism to activity-payload-typing.
- **Production ADRs:**
  - `../../../production/adrs/0043-extension-by-addition-means-no-silent-edits.md` — fences are the load-bearing enforcement mechanism for "extension by addition." Adding a new Activity = the fence introspects it = the discipline applies automatically.
- **Existing precedent:**
  - `tests/fence/test_probe_context_conformance.py` (and other fence tests under `tests/fence/`) — the canonical fence-test idioms in this codebase (introspection, exact-set assertion, deliberate-violation xfail fixture).
  - `src/codegenie/probes/registry.py` — the `_PROBES` registry pattern this fence's `_ACTIVITIES` iteration mirrors.
- **Sibling stories:**
  - `S4-02-system-queue-activities.md` AC-10 — the per-activity static check; this fence is the systemic version.
  - `S4-07-no-merge-fence.md` — the second fence in Step 4; same idiom shape.
  - `S4-08-one-way-import-fence.md` — the third fence; mirrors via import-linter.

## Goal

Ship `tests/fence/test_activity_payload_typing.py` — a fence test that iterates every entry in `codegenie.durable.activities._ACTIVITIES` (the registry from S1-04), introspects each registered function via `typing.get_type_hints`, and asserts: (a) the single positional parameter is a Pydantic `BaseModel` subclass with `model_config.frozen is True` and `model_config.extra == "forbid"`; (b) the return annotation is `RedactedActivityResult`-derived (subclass check at the type level, NOT a runtime-instance check). The fence MUST run as part of `make check` (no `@pytest.mark.fence` opt-out gate); CI fails loud on violation.

## Acceptance criteria

- [ ] **AC-1 — Fence file location + import shape.** `tests/fence/test_activity_payload_typing.py` exists; imports `typing.get_type_hints`, `inspect`, `pydantic.BaseModel`, `codegenie.durable.activities._ACTIVITIES`, `codegenie.durable.sanitizer.RedactedActivityResult`. NO test-body usage of `pytest.importorskip` — the fence is unconditional.
- [ ] **AC-2 — Iteration over `_ACTIVITIES`.** The fence iterates `for name, registration in _ACTIVITIES.items():` (where `registration.func` is the decorated function). Today's iteration covers the activities S4-02..S4-05 have landed; tomorrow's auto-extends. A test-level docstring names: "this fence's coverage scales with the registry; adding a new Activity = automatic enforcement."
- [ ] **AC-3 — Input is a `BaseModel` subclass.** For each registered Activity function, assert via `get_type_hints(func)` that the single positional parameter (`input`, by convention) is annotated as a class that `issubclass(cls, BaseModel)` AND `cls.model_config.get("frozen") is True` AND `cls.model_config.get("extra") == "forbid"`. The assertion message names the offending Activity by name: `f"Activity {name!r}: input type {cls!r} is not a frozen, forbid-extra BaseModel"`.
- [ ] **AC-4 — Return annotation is `RedactedActivityResult`-derived.** For each registered Activity function, assert `get_type_hints(func)["return"]` is a class with `issubclass(cls, RedactedActivityResult)`. The assertion message: `f"Activity {name!r}: return type {cls!r} is not RedactedActivityResult-derived (ADR-0008 layer 3)"`. NOT an `isinstance` check on a runtime value — the annotation IS the check (catches the case where a contributor declares a `dict[str, Any]` return but constructs a `RedactedActivityResult` instance at runtime; the static layer is what we're enforcing).
- [ ] **AC-5 — Deliberate-violation xfail fixture.** A second test file `tests/fence/_violations/test_activity_payload_typing_violation.py` declares an `@activity.defn` function with a `dict[str, Any]` input AND a `dict[str, Any]` return; this file is excluded from the fence's introspection (the fence iterates `_ACTIVITIES`, NOT all `@activity.defn`-decorated functions — the violation isn't registered). A dedicated test imports the violation module and asserts: (a) the function exists; (b) if we manually run the fence's assertion against it, it fails. This is the "fence exercise" pattern from ADR-0004: a deliberate violation MUST trigger the assertion in isolation, proving the fence isn't passing trivially.
- [ ] **AC-6 — `@pytest.mark.fence` ergonomic + `make check` integration.** The test is marked `@pytest.mark.fence` (declarative, NOT exclusionary — fence tests run by default; the marker exists for `pytest -m fence` debugging). S8-06 wires `tests/fence/` into `make check`; this story's commit ensures the test runs under `make test` today.
- [ ] **AC-7 — Coverage assertion (today: ≥3 activities; tomorrow: ≥9).** A separate test asserts `len(_ACTIVITIES) >= 3` today (S4-02's three) and includes a comment naming the per-story target (`>=3` after S4-02, `>=6` after S4-03, `>=8` after S4-04, `>=9` after S4-05). The test fails-loud if `_ACTIVITIES` shrinks unexpectedly (a contributor accidentally deletes an import line in `__init__.py`). The bump is one line per consuming story.
- [ ] **AC-8 — `typing.get_type_hints` resolves forward references.** The fence MUST resolve string-form forward annotations (`from __future__ import annotations` is standard in this codebase). Test asserts the fence works against an Activity whose annotation is a forward-referenced `BaseModel` (e.g., `def emit_event(input: "EmitEventInput") -> "EmitEventOutput":`). The `include_extras=True` flag may be needed for `typing.Annotated` shapes — pin in the implementation.
- [ ] **AC-9 — Negative cases the fence catches.** The fence catches AT LEAST these four shapes (each one a unit test against the deliberate-violation fixture):
    - `def f(input: dict[str, Any]) -> RedactedFoo` — non-BaseModel input.
    - `def f(input: EmitEventInput) -> dict[str, Any]` — non-`RedactedActivityResult` return.
    - `def f(input: NonFrozenInput) -> RedactedFoo` where `NonFrozenInput.model_config.frozen is False` — non-frozen input.
    - `def f(input: ExtraAllowInput) -> RedactedFoo` where `ExtraAllowInput.model_config.extra == "allow"` — extra-allow input.
- [ ] **AC-10 — Lint / type clean.** `ruff check`, `ruff format --check`, `mypy --strict` clean on the fence + violation files. The violation file uses `# type: ignore` markers where deliberately wrong; the marker is named in a comment so reviewers don't strip them.

## Implementation outline

1. **Create `tests/fence/test_activity_payload_typing.py`**: per AC-1 / AC-2 / AC-3 / AC-4. The body is one main test (`test_every_activity_has_typed_pydantic_boundary`) iterating `_ACTIVITIES` + four named tests against violation fixtures (AC-9).
2. **Create `tests/fence/_violations/__init__.py`** (empty marker).
3. **Create `tests/fence/_violations/test_activity_payload_typing_violation.py`**: holds the four deliberately-wrong `@activity.defn` functions (named `_violation_non_basemodel_input`, etc.). Wrapped in a module-level constant `_VIOLATIONS: list[tuple[str, Callable]]` so the AC-9 tests can iterate. Important: these violations are NOT registered via `@register_activity`; they exist only as bare `@activity.defn` decorations the fence's main loop will not see.
4. **Coverage assertion**: a small test `test_activities_registry_has_at_least_three_entries` per AC-7.
5. **Update conftest.py** if needed to suppress `pytest`'s default collection of the violation file as if it were a real test (use `_violations` prefix; pytest's default `python_files = test_*.py` collection still picks it up, but the per-violation test files are themselves real tests asserting the violation triggers — see Notes §3).

## TDD plan — red / green / refactor

### Red — failing test first

```python
# tests/fence/test_activity_payload_typing.py
import typing
import pytest
from pydantic import BaseModel

from codegenie.durable.activities import _ACTIVITIES
from codegenie.durable.sanitizer import RedactedActivityResult


@pytest.mark.fence
def test_every_activity_has_typed_pydantic_boundary():
    """ADR-0008 layer (a) — Pydantic extra='forbid' on inputs;
    ADR-0008 layer (c) — RedactedActivityResult-derived returns.
    This fence is the STATIC counterpart to RedactedActivityResult.seal()'s
    RUNTIME check. The reason it's the red test: a single naive activity
    that returns `dict[str, Any]` with a secret-shaped field bypasses
    mypy's check (via # type: ignore) and the seal's check (because seal
    only runs on derived classes). The fence catches the gap."""
    failures = []
    for name, registration in _ACTIVITIES.items():
        func = registration.func
        hints = typing.get_type_hints(func, include_extras=True)
        # Find the single non-return param:
        param_names = [n for n in hints if n != "return"]
        assert len(param_names) == 1, (
            f"Activity {name!r}: expected exactly one input parameter, got {param_names!r}"
        )
        input_cls = hints[param_names[0]]
        if not (isinstance(input_cls, type) and issubclass(input_cls, BaseModel)):
            failures.append(f"Activity {name!r}: input type {input_cls!r} is not BaseModel")
            continue
        if input_cls.model_config.get("frozen") is not True:
            failures.append(f"Activity {name!r}: input type {input_cls!r} is not frozen")
        if input_cls.model_config.get("extra") != "forbid":
            failures.append(f"Activity {name!r}: input type {input_cls!r} does not have extra='forbid'")
        return_cls = hints.get("return")
        if not (isinstance(return_cls, type) and issubclass(return_cls, RedactedActivityResult)):
            failures.append(
                f"Activity {name!r}: return type {return_cls!r} is not RedactedActivityResult-derived"
            )
    assert not failures, "\n".join(failures)
```

Why it fails: today, `_ACTIVITIES` is empty (S1-04 ships the kernel; S4-02 adds the first three entries; this story may land BEFORE S4-02 in a CI run). When the kernel is empty, the assertion passes trivially — that's the bootstrap. Once S4-02 ships, the fence MUST stay green; the red test is the bootstrap version of "the fence catches the violation fixture."

The TRUE red test is one against the violation fixture (AC-5 / AC-9), proving the fence isn't a no-op.

### Green — minimal pass

- Ship the fence file.
- Ship the violation file with the four deliberate-violation activities.
- The fence iterates `_ACTIVITIES`; the violations are not in `_ACTIVITIES`; the fence passes against real activities; the AC-9 tests assert the fence's assertion FAILS when manually run against a violation.

### Required follow-on tests (per AC)

```python
# tests/fence/_violations/test_activity_payload_typing_violation.py
import typing
import pytest
from typing import Any
from pydantic import BaseModel, ConfigDict
from temporalio import activity

from codegenie.durable.sanitizer import RedactedActivityResult


class _NonFrozenInput(BaseModel):
    """Deliberately non-frozen — the fence MUST reject this shape."""
    x: int


class _ExtraAllowInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="allow")
    x: int


class _RedactedFoo(RedactedActivityResult):
    x: int


@activity.defn(name="_violation_dict_input")
async def _violation_dict_input(input: dict[str, Any]) -> _RedactedFoo:  # type: ignore[type-arg]
    """Fence MUST reject: input type is dict, not BaseModel."""
    return _RedactedFoo.seal(_RedactedFoo(x=1))


@activity.defn(name="_violation_dict_return")
async def _violation_dict_return(input: _NonFrozenInput) -> dict[str, Any]:  # type: ignore[type-arg]
    """Fence MUST reject: return type is dict, not RedactedActivityResult-derived."""
    return {}


# AC-9 — one named test per violation shape, each asserting the fence's
# assertion fires when manually applied to the violation function.

def _apply_fence_to(func) -> list[str]:
    """Apply the same assertion the main fence applies — but as a return-list
    instead of an assert, so we can verify it surfaces failures."""
    failures: list[str] = []
    hints = typing.get_type_hints(func, include_extras=True)
    param = [n for n in hints if n != "return"][0]
    input_cls = hints[param]
    if not (isinstance(input_cls, type) and issubclass(input_cls, BaseModel)):
        failures.append(f"input not BaseModel: {input_cls!r}")
    elif input_cls.model_config.get("frozen") is not True:
        failures.append(f"input not frozen: {input_cls!r}")
    elif input_cls.model_config.get("extra") != "forbid":
        failures.append(f"input not extra='forbid': {input_cls!r}")
    return_cls = hints.get("return")
    if not (isinstance(return_cls, type) and issubclass(return_cls, RedactedActivityResult)):
        failures.append(f"return not RedactedActivityResult: {return_cls!r}")
    return failures


def test_fence_rejects_dict_input():
    """AC-9 — fence catches dict[str, Any] input."""
    failures = _apply_fence_to(_violation_dict_input)
    assert any("not BaseModel" in f for f in failures)


def test_fence_rejects_dict_return():
    """AC-9 — fence catches dict[str, Any] return."""
    failures = _apply_fence_to(_violation_dict_return)
    assert any("not RedactedActivityResult" in f for f in failures)


def test_fence_rejects_non_frozen_input():
    """AC-9 — non-frozen input is caught even when the class IS a BaseModel.
    Without this, a contributor could ship a mutable Activity input and the
    workflow ↔ activity boundary's frozen invariant would silently break."""
    # Construct a one-off activity with this input shape:
    @activity.defn(name="_v_nonfrozen")
    async def _v_nonfrozen(input: _NonFrozenInput) -> _RedactedFoo:
        return _RedactedFoo.seal(_RedactedFoo(x=1))
    failures = _apply_fence_to(_v_nonfrozen)
    assert any("not frozen" in f for f in failures)


def test_fence_rejects_extra_allow_input():
    """AC-9 — extra='allow' input is caught. The reason: extra='allow' means
    Pydantic accepts unknown fields silently; a contributor could pass an
    activity an unintended GitHub token in an unrecognized field and Pydantic
    would happily round-trip it through the workflow history."""
    @activity.defn(name="_v_extra_allow")
    async def _v_extra_allow(input: _ExtraAllowInput) -> _RedactedFoo:
        return _RedactedFoo.seal(_RedactedFoo(x=1))
    failures = _apply_fence_to(_v_extra_allow)
    assert any("not extra='forbid'" in f for f in failures)
```

### Refactor

- Module docstring on `tests/fence/test_activity_payload_typing.py` cites ADR-0008's three-layer pattern + names this fence as the static counterpart of the runtime `seal()` and the type-time mypy check. Names ADR-0004 as the pattern source.
- The violation file's module docstring is a SHOUT: "DO NOT REGISTER THESE ACTIVITIES via `@register_activity`. They exist solely to exercise the fence assertions. Adding any of them to `_ACTIVITIES` will cause the main fence test to fail-loud, which is the correct behavior."
- The `_apply_fence_to` helper is named `__all__`-excluded so it's not consumed elsewhere; it's the per-violation-test-friendly counterpart of the main assertion.

## Files to touch

| Path | Why |
|---|---|
| `tests/fence/test_activity_payload_typing.py` | The fence test itself. |
| `tests/fence/_violations/__init__.py` | Namespace marker. |
| `tests/fence/_violations/test_activity_payload_typing_violation.py` | Deliberate-violation activities + per-violation AC-9 tests. |
| `tests/fence/conftest.py` | If needed: pytest collection exclusion for `_violations` to prevent the bare `@activity.defn` violations from being treated as accidental activities. |

## Out of scope

- The `_ACTIVITIES` registry — S1-04 ships it.
- The `RedactedActivityResult` class — S3-06 ships it.
- The activity functions themselves — S4-02..S4-05.
- `make check` integration — S8-06 wires every fence into the gate; this story ships the file.
- Cross-process secret-leakage adversarial — S4-07 + S8-03.
- The workflow-determinism fence (`tests/fence/test_workflow_determinism.py`) — S1-07.
- The no-merge fence (`tests/fence/test_no_merge_activity.py`) — S4-07.
- The one-way-import fence (import-linter `codegenie.durable.activities.* !→ codegenie.durable.workflows.*`) — S4-08.

## Notes for the implementer

### §1 — Fence is the third layer, NOT a replacement for the others

ADR-0008's three layers are intentionally redundant: `mypy --strict` catches at design time; `seal()` catches at runtime; this fence catches the structural drift. None alone is sufficient because:
- `mypy --strict` can be silenced with `# type: ignore`.
- `seal()` can be skipped by constructing a `RedactedActivityResult`-derived class via `cls(**kwargs)` instead of `cls.seal(model)`. The `_sanitized: Literal[True]` discipline (S3-06) limits this, but type-instance escape hatches exist.
- The fence is the third defense: it asserts the ANNOTATION shape, not the runtime value.

Layered defense; ADR-0004's pattern. Each layer must stay green; failures in any layer are P0.

### §2 — `get_type_hints` resolves `from __future__ import annotations`

Phase 9's modules use `from __future__ import annotations` (the project default in this codebase). All annotations are stored as strings; `typing.get_type_hints(func, include_extras=True)` resolves them against the module's namespace. `include_extras=True` is needed for `typing.Annotated` shapes — some Activity inputs may carry `Annotated[X, ...]` metadata; without `include_extras=True`, the resolved type is `X` without the metadata, which is fine for this fence's subclass check.

### §3 — Violation fixtures don't register

The four deliberate-violation `@activity.defn` functions in `tests/fence/_violations/` are NOT registered via `@register_activity`. They exist solely to validate the fence's assertion logic. If a contributor accidentally adds `@register_activity(...)` to one of them, the main fence test (AC-1) will catch it in CI — exactly the correct behavior.

A subtle gotcha: `@activity.defn` may emit warnings under `temporalio` if the function isn't registered with a worker. If the test runs cleanly without those warnings polluting CI output, no action needed; otherwise, wrap each violation in a `pytest.warns(...)` or use `temporalio.activity.defn` with `dynamic=False`.

### §4 — `_ACTIVITIES` iteration scales automatically

The fence's `for name, registration in _ACTIVITIES.items()` loop covers exactly the activities that have shipped at fence-run time. As S4-03..S4-05 land each new activity, the fence automatically introspects them. The story-by-story discipline: every executor that adds an activity MUST ensure this fence stays green for that activity's added entry. The fence is the "Pydantic discipline applies to every Activity, forever" enforcement.

### §5 — Don't try to assert at import time

A temptation: "let's add a module-level check to `codegenie.durable.activities/__init__.py` that runs the fence on every import." Don't. Two reasons:
1. Import-time assertions can't reach into `_ACTIVITIES` because the activities haven't yet registered (chicken-and-egg).
2. The fence is a TEST; it belongs under `tests/fence/`, NOT under `src/`. The architectural source set stays free of test-coupled introspection.

ADR-0043's "fences are CI assertions, not import-time guards" pins this. The reason: import-time guards run on every developer's local imports, dwarfing CI time; fences run once per CI pass, surface clearly, and don't slow down everyone's `python -c "import codegenie"`.

### §6 — When `_ACTIVITIES` is empty (bootstrap)

If this story lands BEFORE S4-02 (in a CI re-order), `_ACTIVITIES` is empty and the main loop iterates zero times → fence passes trivially. The AC-7 coverage assertion catches this: `len(_ACTIVITIES) >= 3` will fail-loud if the registry is empty when this story lands. The fix in that case: the executor for whichever S4-02..S4-05 story merges after this one bumps the threshold per their own AC. This story's commit ships `>= 0` if and only if it lands BEFORE S4-02 — but that ordering shouldn't happen per the DAG (S4-02 depends on S1-06 + S3-04 + S3-06 + S4-01; this story depends on S4-02). Keep the threshold at `>= 3` and trust the DAG.

### §7 — Fence's clear-message discipline

The assertion message names the offending Activity by name AND the offending type/setting. A contributor seeing the failure should know:
- WHICH activity is wrong.
- WHICH layer of the typing contract was violated (input not BaseModel? input not frozen? input not `extra="forbid"`? return not `RedactedActivityResult`-derived?).
- WHICH ADR to consult (ADR-0008 named in the message).

A message that says only "fence failed" is useless. A message that names the activity + the violated layer + the ADR is debugger-grade and the load-bearing improvement over a generic assert.
