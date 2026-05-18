# Story S1-04 — Transform ABC + ApplyContext + provenance

**Step:** Step 1 — Scaffold packages, domain primitives, sum types, and structural CI fences
**Status:** Ready
**Effort:** S
**Depends on:** S1-01 (`TransformId`, `WorkflowId`, `AttemptNumber`, `SignalKind`, `PluginId`, `RecipeId` newtypes)
**ADRs honored:** ADR-0001 (Phase-5 contract surface — `Transform` ABC, `ApplyContext`, `prior_attempts: list = []` shipped Phase-3-time; contract snapshot test S6-06 freezes it), ADR-0010 (`frozen=True` + `extra="forbid"` everywhere; primitives-only `details`), ADR-0011 (`SandboxedPath` framing — `Transform.files_changed: list[SandboxedPath]` is in-jail-at-construction)

## Context

Phase 5's already-merged design names `Transform` (ABC), `ApplyContext` (with `prior_attempts`), and `AttemptSummary` by exact identifier; its `GateRunner.run(...)` and `GateContext.transform_output: Transform` consume these contracts verbatim. If Phase 3 ships only some of the fields, Phase 5 has to amend the Pydantic models (breaking the contract snapshot) before it can land. ADR-0001's Decision §C — "ship the full named surface with Phase-5-required fields already present" — forces this story to land `prior_attempts: list[AttemptSummary] = Field(default_factory=list)` *now*, even though Phase 3 itself never populates it. The Transform ABC, similarly, must be an `ABC` (not a Protocol) because Phase 5 uses `isinstance(t, Transform)` — see ADR-0001's Tradeoffs row 3 and Phase 5 ADR-0006.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design C4` — `Transform` ABC fields verbatim (`transform_id: TransformId`, `diff_bytes: bytes`, `files_changed: list[SandboxedPath]`, `provenance: TransformProvenance`). `NpmLockfileTransform(Transform)` and `DockerfileBaseImageTransform(Transform)` are the Phase-3 concrete subclasses S5-02 / S5-03 ship.
  - `../phase-arch-design.md §Component design C5` — `AttemptSummary` and `ApplyContext` field-for-field; `prior_attempts: list[AttemptSummary] = Field(default_factory=list)` with comment "dead-weight in Phase 3; Phase 5 populates."
  - `../phase-arch-design.md §Scenarios §Scenario C` — `Validated(passed=False)` is terminal in Phase 3 because `prior_attempts` stays empty; Phase 5's retry envelope reads it.
- **Phase ADRs:**
  - `../ADRs/0001-ship-phase5-contract-surface-by-name.md` — Decision §C names exactly the modules this story creates (`apply_context.py`, `transform.py`); Consequences names `TrustScorer.__init__(event_log)` (S6-02), `_validate_stage6` (S6-04). The contract snapshot test (S6-06) is the gate that blocks Phase 5 if this story drifts.
  - `../ADRs/0010-domain-modeling-discipline-scope-sum-type-and-newtypes.md` — `extra="forbid"` + `frozen=True` on every Pydantic model; `prior_failure_summary: str` truncated to 8 KB (canary-checked downstream).
  - `../ADRs/0011-honest-framing-capability-sandboxedpath-pluginslock.md` — `SandboxedPath` framing context for `Transform.files_changed`; implementer should NOT add runtime symlink-check logic here (S4-04 ships `SandboxedPath`).
- **Existing code:**
  - `src/codegenie/probes/base.py` — Phase 0 precedent for a frozen ABC + Pydantic models pattern (`Probe`, `ProbeContext`, `ProbeOutput`); same architectural shape.
  - `src/codegenie/output/sanitizer.py` — Pydantic `extra="forbid"` + `frozen=True` precedent.

## Goal

Land `src/codegenie/transforms/transform.py` (ABC + `TransformProvenance`) and `src/codegenie/transforms/apply_context.py` (`ApplyContext` + `AttemptSummary`) with the Phase-3-final shapes ADR-0001 commits to — including `prior_attempts: list[AttemptSummary] = Field(default_factory=list)` shipped already so Phase 5's amendment is a behavior-only change.

## Acceptance criteria

- [ ] `src/codegenie/transforms/transform.py` defines `class Transform(ABC)` with `transform_id: TransformId`, `diff_bytes: bytes`, `files_changed: list[SandboxedPath]`, `provenance: TransformProvenance`. ABC has no `__init__` body but each subclass-required attribute is declared via `@property @abstractmethod` or class-level annotation as appropriate (mirror `src/codegenie/probes/base.py`).
- [ ] `TransformProvenance` is a `BaseModel` (`frozen=True`, `extra="forbid"`) with `plugin_id: PluginId`, `recipe_id: RecipeId`, `transform_kind: TransformKind`, `applied_at: datetime` (UTC), `recipe_version: str`, `plugin_version: str`.
- [ ] `src/codegenie/transforms/apply_context.py` defines `AttemptSummary` (Pydantic, `frozen=True`, `extra="forbid"`): `attempt: AttemptNumber`, `failing_signals: list[SignalKind]`, `prior_failure_summary: str` (validator: `len(s) ≤ 8192`), `evidence_paths: list[SandboxedPath]`, `transform_id: TransformId | None`.
- [ ] `ApplyContext` (Pydantic, `frozen=True`, `extra="forbid"`): `workflow_id: WorkflowId`, `attempt: AttemptNumber = AttemptNumber(1)`, `prior_attempts: list[AttemptSummary] = Field(default_factory=list)`, `capabilities: CapabilityBundle` — `CapabilityBundle` lands in S4-05; for Phase-3-Step-1, define a `CapabilityBundle` forward-reference Pydantic shell with no fields plus a docstring naming S4-05 as the filler. (Pydantic v2 supports forward refs via `model_rebuild()`.)
- [ ] `SandboxedPath` is similarly forward-referenced (lands in S4-04). For Step 1, ship a `_PathPlaceholder` shim or `from __future__ import annotations` + `TYPE_CHECKING` import so the annotation parses but the runtime model accepts `pathlib.Path` until S4-04 substitutes the real class. Document the shim explicitly in code comments.
- [ ] `tests/unit/transforms/test_apply_context.py` covers: default `prior_attempts == []`; explicit-populate round-trip via `model_dump_json()` → `model_validate_json()`; `prior_failure_summary` of 8193 bytes is rejected; extra field rejected; mutation rejected.
- [ ] `tests/unit/transforms/test_transform_abc.py` covers: instantiating `Transform()` directly raises `TypeError` (ABC); a `class FakeTransform(Transform)` minimal subclass instantiates with all four fields; `isinstance(t, Transform)` is True (the Phase-5 contract).
- [ ] `mypy --strict src/codegenie/transforms/transform.py src/codegenie/transforms/apply_context.py` clean.
- [ ] `ruff check`, `ruff format --check` clean.
- [ ] TDD plan's red test exists, committed, green.

## Implementation outline

1. In `src/codegenie/transforms/transform.py`: import `ABC`, `abstractmethod`; declare `class Transform(ABC)` with the four typed class-level attributes (use `@property @abstractmethod` for `transform_id`, `diff_bytes`, `files_changed`, `provenance` so subclasses must define them — matches `src/codegenie/probes/base.py`).
2. In the same file, define `TransformProvenance` Pydantic model.
3. In `src/codegenie/transforms/apply_context.py`: define `AttemptSummary` then `ApplyContext`. Use Pydantic v2 `field_validator` for the 8 KB cap on `prior_failure_summary`.
4. For `CapabilityBundle` and `SandboxedPath` forward refs: under `if TYPE_CHECKING:` import from `codegenie.plugins.capabilities` (S4-05) and `codegenie.plugins.sandbox_path` (S4-04). At runtime, define a `class CapabilityBundle(BaseModel): model_config = ConfigDict(frozen=True, extra="forbid")` shell with `_placeholder: bool = True` field (the field disappears in S4-05's PR). Same for `SandboxedPath = Path` runtime alias. Add a load-bearing comment naming the substituting story.
5. Re-export the four new types from `src/codegenie/transforms/__init__.py` (per ADR-0001 §Consequences fence test).
6. Add `tests/unit/transforms/test_apply_context.py` + `test_transform_abc.py`.
7. Run `mypy --strict src/codegenie/transforms/` + `pytest tests/unit/transforms/ -v`.

## TDD plan — red / green / refactor

### Red — write the failing test first
Test file path: `tests/unit/transforms/test_apply_context.py`

```python
import pytest
from pydantic import ValidationError

from codegenie.transforms.apply_context import ApplyContext, AttemptSummary
from codegenie.types.identifiers import (
    WorkflowId, AttemptNumber, SignalKind, TransformId,
)


def test_apply_context_defaults_to_empty_prior_attempts():
    ctx = ApplyContext(
        workflow_id=WorkflowId("wf-1"),
        capabilities=...,  # filled by S4-05; placeholder accepted in Step 1
    )
    assert ctx.prior_attempts == []
    assert ctx.attempt == AttemptNumber(1)


def test_apply_context_round_trips_with_prior_attempts():
    a = AttemptSummary(
        attempt=AttemptNumber(1),
        failing_signals=[SignalKind("tests")],
        prior_failure_summary="x" * 100,
        evidence_paths=[],
        transform_id=TransformId("a" * 64),
    )
    ctx = ApplyContext(
        workflow_id=WorkflowId("wf-1"),
        attempt=AttemptNumber(2),
        prior_attempts=[a],
        capabilities=...,
    )
    raw = ctx.model_dump_json()
    parsed = ApplyContext.model_validate_json(raw)
    assert parsed.prior_attempts[0].prior_failure_summary == "x" * 100


def test_prior_failure_summary_truncation_cap():
    with pytest.raises(ValidationError):
        AttemptSummary(
            attempt=AttemptNumber(1),
            failing_signals=[],
            prior_failure_summary="x" * 8193,  # > 8 KiB
            evidence_paths=[],
            transform_id=None,
        )


def test_apply_context_frozen_and_extra_forbid():
    ctx = ApplyContext(workflow_id=WorkflowId("wf-1"), capabilities=...)
    with pytest.raises(ValidationError):
        ctx.workflow_id = WorkflowId("wf-2")  # frozen
    with pytest.raises(ValidationError):
        ApplyContext(workflow_id=WorkflowId("wf-1"), capabilities=..., oops="x")  # extra


# tests/unit/transforms/test_transform_abc.py:

from codegenie.transforms.transform import Transform


def test_transform_is_abstract():
    with pytest.raises(TypeError):
        Transform()  # type: ignore[abstract]
```

State why it fails: `ModuleNotFoundError: codegenie.transforms.apply_context` — the modules don't exist.

### Green — minimal pass
- Add `src/codegenie/transforms/transform.py` with `Transform(ABC)` + `TransformProvenance`.
- Add `src/codegenie/transforms/apply_context.py` with `AttemptSummary` + `ApplyContext`.
- Add the placeholder `CapabilityBundle` (S4-05 substitutes) and `SandboxedPath` alias (S4-04 substitutes) plus the load-bearing code comments.
- Update `src/codegenie/transforms/__init__.py` re-exports.

### Refactor
- Land the contract-snapshot-helper docstring on `Transform`, `ApplyContext`, `AttemptSummary` — each names ADR-0001 + the Phase 5 wrap target.
- Apply `field_validator("prior_failure_summary")` for the 8 KB cap; reject > 8192 bytes (UTF-8-encoded len, not char count — `len(s.encode("utf-8")) <= 8192`).
- Edge cases from §Edge cases that touch this code: E20 (adversarial repo content — NUL bytes / zero-width / bidi in `prior_failure_summary`). Add NFKC normalize + reject controls in the validator with a comment naming the gate. (Phase 5 will widen / relax via Pydantic versioning; for Phase 3, hard reject is the right default.)
- Confirm S5-02's `NpmLockfileTransform(Transform)` will compile against this ABC — write a one-paragraph note in `Transform`'s docstring on what subclasses must implement.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/transforms/transform.py` | NEW — `Transform` ABC + `TransformProvenance`. |
| `src/codegenie/transforms/apply_context.py` | NEW — `ApplyContext` + `AttemptSummary` with Phase-5-required `prior_attempts` already shipped. |
| `src/codegenie/transforms/__init__.py` | Extend (from S1-03) — re-export `Transform`, `TransformProvenance`, `ApplyContext`, `AttemptSummary` per ADR-0001 §Consequences. |
| `tests/unit/transforms/test_apply_context.py` | NEW — defaults + round-trip + 8 KB cap + freeze + extra-rejection. |
| `tests/unit/transforms/test_transform_abc.py` | NEW — `isinstance(t, Transform)` works; bare `Transform()` raises. |

## Out of scope

- **Concrete `NpmLockfileTransform` / `DockerfileBaseImageTransform`** — S5-02 / S5-03. This story only ships the ABC.
- **`CapabilityBundle` real fields** — S4-05 substitutes the placeholder; the import path is stable.
- **`SandboxedPath` real type** — S4-04 substitutes the placeholder; the import path is stable.
- **`RecipeEngine` Protocol** — S5-01.
- **`RemediationOrchestrator._validate_stage6` method** — S6-04. This story ships the types its signature consumes; not the method itself.
- **Contract snapshot test** (`test_phase5_contract_snapshot.py`) — S6-06.

## Notes for the implementer

- **`prior_attempts: list[AttemptSummary] = Field(default_factory=list)` is load-bearing.** ADR-0001 §Tradeoffs explicitly accepts this as Phase-3 dead weight; deleting it because "Phase 3 never uses it" breaks Phase 5's `ADR-P5-002` amendment guarantee.
- **`Transform` is an ABC, not a Protocol** — load-bearing per ADR-0001 Tradeoffs row 3 + Phase 5 ADR-0006. Don't convert to `@runtime_checkable Protocol` for "consistency with Plugin/RecipeEngine"; the asymmetry is documented.
- **Forward references via Pydantic v2** require `model_rebuild()` after the substituting module loads. For Step 1, the placeholder approach (define a minimal `CapabilityBundle` shell) avoids the `model_rebuild` dance; S4-05's PR substitutes the real class and removes the placeholder. Document this transition explicitly in code comments so the S4-05 implementer doesn't get confused.
- **`SandboxedPath` placeholder = `pathlib.Path`** is honest framing per ADR-0011: until S4-04 lands the real `SandboxedPath` (with `O_NOFOLLOW`), `files_changed: list[Path]` is what Phase 3 has. The runtime check that paths are in-jail comes from S4-04, not from `Transform`'s constructor.
- **`prior_failure_summary` 8 KB cap is bytes, not chars** — UTF-8 multi-byte chars mean `len(s) <= 8192` would let through > 8 KiB of data. Use `len(s.encode("utf-8")) <= 8192`. The canary-check downstream (Phase 5) assumes this byte cap.
- **`applied_at: datetime`** must be timezone-aware (UTC). Use `Field(default_factory=lambda: datetime.now(UTC))` and validate `tz is not None`. Naive datetimes have bitten earlier phases; the convention here is UTC-aware.
- **Don't import from `codegenie.plugins.*`** at runtime in `transforms/apply_context.py` — the `transforms/` namespace is the contract-frozen layer (ADR-0001) and importing `plugins/` would tangle the dependency direction. If you need the `CapabilityBundle` type at runtime, import it under `if TYPE_CHECKING:` and use string annotations.
