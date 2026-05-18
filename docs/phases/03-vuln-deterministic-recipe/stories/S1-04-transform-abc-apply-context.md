# Story S1-04 — Transform ABC + ApplyContext + provenance

**Step:** Step 1 — Scaffold packages, domain primitives, sum types, and structural CI fences
**Status:** HARDENED
**Effort:** S
**Depends on:** S1-01 (`TransformId`, `WorkflowId`, `AttemptNumber`, `SignalKind`, `PluginId`, `RecipeId`, `TransformKind`, `EventId` newtypes)
**ADRs honored:** ADR-0001 (Phase-5 contract surface — `Transform` ABC, `ApplyContext`, `prior_attempts: list = []` shipped Phase-3-time; contract snapshot test S6-06 freezes it), ADR-0010 (`frozen=True` + `extra="forbid"` everywhere; primitives-only `details`; "make illegal states unrepresentable"), ADR-0011 (`SandboxedPath` framing — `Transform.files_changed: list[SandboxedPath]` is in-jail-at-construction; `Capability` audit-trail anchored via `TransformProvenance.capability_use_id`)

## Validation notes (2026-05-18, phase-story-validator → HARDENED)

This story was hardened by [`_validation/S1-04-transform-abc-apply-context.md`](_validation/S1-04-transform-abc-apply-context.md). Key changes vs the original draft:

- **Block-tier consistency fix.** `TransformProvenance` was missing `capability_use_id: EventId` (arch §Data model L800-806 ships it; ADR-0011 names it as the Capability audit anchor). Added as a required field; without it the Phase-5 contract-snapshot test would refuse the surface and ADR-0011's "audit + lint" framing has no per-Transform anchor in the event log.
- **Block-tier test-quality fix.** The 8 KB cap test must cover the UTF-8 multi-byte edge case (e.g., 4-byte emoji) — the original `"x" * 8193` test only covers ASCII and would not catch a `len(s)` regression substituted for `len(s.encode("utf-8"))`. Promoted to a parametrized AC.
- **Block-tier test-quality fix.** The original TDD red-test used `capabilities=...` (ellipsis = `Ellipsis`), which fails Pydantic validation and is not a valid red→green starting point. Rewritten with concrete fixture constructors; mirrors S1-03 T-F8 closure.
- **Design-patterns: cleaner placeholder strategy.** Original prescribed `CapabilityBundle` with a `_placeholder: bool = True` field that S4-05 must *remove*. Replaced with an empty Pydantic shell (`pass` body + `extra="forbid"`) — S4-05 *adds* fields, no removal, no `model_rebuild` churn. Phase-boundary stable contract / extension-by-addition.
- **Design-patterns: list immutability.** `prior_attempts: list[AttemptSummary] = Field(default_factory=list)` does NOT block `ctx.prior_attempts.append(...)` even with `frozen=True` (Pydantic v2 freezes attribute reassignment, not container mutation). Switched to `tuple[AttemptSummary, ...] = ()` for true immutability. Same for `failing_signals: tuple[SignalKind, ...]` and `evidence_paths: tuple[SandboxedPath, ...]`. Phase 5 ADR-P5-002 updates `prior_attempts` via `model_copy(update={"prior_attempts": old + (new,)})` — immutable-update idiom.
- **Design-patterns: precedent-mirror for the ABC pattern.** Original AC-1 wavered between `@property @abstractmethod` and class-level annotations. Pinned to the `src/codegenie/probes/base.py` precedent: class-level type annotations on the ABC + each subclass declares the attributes (validated via a fixture subclass test). Mirrors the load-bearing repo convention.
- **Harden-tier closures.** Added ACs for: `applied_at` naive-datetime rejection; NUL/control/bidi rejection in `prior_failure_summary` (E20); `plugin_version`/`recipe_version` regex validator (compensates for missing `SemverVersion` newtype — arch references it, S1-01 doesn't ship it); `transform_kind: TransformKind` newtype usage; module-purity import fence; `model_construct` absence; `__all__` exact-set pinning; round-trip preserves concrete type; JSON-shape pinning; full-coverage parametrized `frozen=True` + `extra="forbid"` over every field of every model.

Stage 3 research **skipped** — every closure is answerable from arch + ADR-0010 + ADR-0011 + ADR-0001 + S1-03 validation precedent + `src/codegenie/probes/base.py` ABC precedent + Pydantic v2 docs.

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

### Transform ABC + TransformProvenance

- [ ] **AC-1 — `Transform` ABC shape and pattern**. `src/codegenie/transforms/transform.py` defines `class Transform(ABC)` with **class-level type annotations** (NOT `@property @abstractmethod`) for `transform_id: TransformId`, `diff_bytes: bytes`, `files_changed: tuple[SandboxedPath, ...]`, `provenance: TransformProvenance`. **Pattern precedent:** `src/codegenie/probes/base.py` defines `Probe(ABC)` with class-level annotations + abstract `run`; mirror that. Pick *one* pattern (annotations) and stay with it — do NOT mix `@property @abstractmethod` with class annotations. (Story V-D-F4 closure.)
- [ ] **AC-1a — Subclass-required attributes are enforced at instantiation**. `class FakeTransform(Transform): pass` with no attributes set must either raise `TypeError` or fail attribute access at construction. A `class FakeTransform(Transform): transform_id = ...; diff_bytes = ...; files_changed = ...; provenance = ...` minimal subclass must instantiate. Test both shapes.
- [ ] **AC-2 — `TransformProvenance` Pydantic model**. `BaseModel` with `model_config = ConfigDict(frozen=True, extra="forbid")` and **all seven fields** mandated by arch §Data model L800-806:
  - `plugin_id: PluginId`
  - `plugin_version: str` (regex-validated `^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][\w.-]+)?$` via `field_validator`; arch references `SemverVersion` but S1-01 does not ship that newtype — the regex is the boundary defence; document the arch-drift in Notes)
  - `recipe_id: RecipeId`
  - `recipe_version: str` (same regex validator as above)
  - `transform_kind: TransformKind` (the S1-01 `NewType`)
  - `applied_at: datetime` (timezone-aware UTC — see AC-2a)
  - `capability_use_id: EventId` (**load-bearing — ADR-0011 audit anchor**; arch L806; missing from the original story draft)
- [ ] **AC-2a — `applied_at` is timezone-aware UTC**. A `field_validator("applied_at")` raises `ValidationError` on naive `datetime` (`tz is None`). Default factory: `datetime.now(UTC)`. Test the naive-datetime rejection path explicitly.

### AttemptSummary + ApplyContext

- [ ] **AC-3 — `AttemptSummary` Pydantic model**. `BaseModel` with `model_config = ConfigDict(frozen=True, extra="forbid")`:
  - `attempt: AttemptNumber`
  - `failing_signals: tuple[SignalKind, ...]` (**tuple, not list** — `frozen=True` does not block `list.append()`; tuples are truly immutable. Validator coerces `list` input to `tuple` for YAML/JSON ingest)
  - `prior_failure_summary: str` (validator: `len(s.encode("utf-8")) ≤ 8192` — **bytes, not chars**; rejects NUL bytes `\x00`–`\x08`/`\x0b`/`\x0c`/`\x0e`–`\x1f` and bidi controls `‪`–`‮`/`⁦`–`⁩` per E20 adversarial repo content; `\t\n\r` admitted)
  - `evidence_paths: tuple[SandboxedPath, ...]`
  - `transform_id: TransformId | None` (None when failure precedes Transform)
- [ ] **AC-4 — `ApplyContext` Pydantic model**. `BaseModel` with `model_config = ConfigDict(frozen=True, extra="forbid")`:
  - `workflow_id: WorkflowId`
  - `attempt: AttemptNumber = AttemptNumber(1)`
  - `prior_attempts: tuple[AttemptSummary, ...] = ()` (**tuple, not list** — Phase 5 ADR-P5-002 updates via `ctx.model_copy(update={"prior_attempts": old + (new,)})`; pin this idiom in Notes for the implementer)
  - `capabilities: CapabilityBundle` (forward reference — see AC-5)

### Forward references (S4-04 / S4-05 substitutes)

- [ ] **AC-5 — `CapabilityBundle` is an empty Pydantic shell, NOT a placeholder with `_placeholder` field**. `class CapabilityBundle(BaseModel): model_config = ConfigDict(frozen=True, extra="forbid")` — body is `pass`. **No `_placeholder: bool = True` field.** S4-05 *adds* fields without removing anything; the shell stays empty in Phase 3 Step 1. (Story V-D-F1 closure.) Define this minimal shell in `src/codegenie/transforms/_forward.py` (a tiny shim module) and `from codegenie.transforms._forward import CapabilityBundle` in `apply_context.py` so the import direction `transforms → transforms._forward` stays one-way and never reaches into `plugins/`. S4-05 will move the symbol to `plugins/capabilities.py` and re-export it from `_forward.py` to keep the import path stable.
- [ ] **AC-5a — `SandboxedPath` shim**. In `src/codegenie/transforms/_forward.py`, also define `SandboxedPath: TypeAlias = pathlib.Path` (runtime alias) with a load-bearing comment: "Until S4-04 lands `codegenie.plugins.sandbox_path.SandboxedPath`, this alias makes `transforms/` type-clean. S4-04 replaces the alias with a re-export — every consumer's import path stays stable." (Adapter / facade pattern for forward compatibility.)
- [ ] **AC-5b — Forward-reference module purity**. `_forward.py` imports nothing from `codegenie.plugins.*` at Phase-3-Step-1 time (S4-05 amends additively). Fence test: AST-walk `_forward.py` and assert imports ∈ `{__future__, pathlib, typing, pydantic}`. (Cycle-avoidance per ADR-0001.)

### Module-level conventions

- [ ] **AC-6 — `transforms/__init__.py` re-exports** with an exact-set `__all__`. The Phase-3-Step-1 set is `{"Transform", "TransformProvenance", "ApplyContext", "AttemptSummary", "CapabilityBundle", "SandboxedPath"}`. ADR-0001 §Consequences names the re-export list; the contract-snapshot test (S6-06) byte-pins it. Test: `set(codegenie.transforms.__all__) == EXPECTED_SET`.
- [ ] **AC-6a — Module-purity fence on `transform.py` and `apply_context.py`**. AST source-scan: imports limited to `{__future__, abc, datetime, typing, pathlib, pydantic, codegenie.types.identifiers, codegenie.types.errors, codegenie.transforms._forward}`. Mirrors S1-01 / S1-03 closures. Test file: `tests/fence/test_transforms_module_purity.py` (or extend the existing fence).
- [ ] **AC-6b — `model_construct` absent from contract-surface modules**. Source-scan `transform.py`, `apply_context.py`, `_forward.py` for `.model_construct(` — must not appear. (Bypass-validation hole; ADR-0010 §Decision-§4 smart-constructor discipline.)

### Test plan

- [ ] **AC-7 — `tests/unit/transforms/test_apply_context.py`** parametrized over all relevant models:
  - **AC-7a** — `ApplyContext` defaults: `prior_attempts == ()`; `attempt == AttemptNumber(1)`.
  - **AC-7b** — Round-trip identity preserved over every variant: `parsed = M.model_validate_json(m.model_dump_json()); assert type(parsed) is type(m); assert parsed == m`. Parametrized over `AttemptSummary`, `ApplyContext`, `TransformProvenance` fixtures.
  - **AC-7c** — UTF-8-bytes cap on `prior_failure_summary`: parametrized over `[("x" * 8192, "accept"), ("x" * 8193, "reject"), ("💀" * 2048, "accept"  # 8192 bytes), ("💀" * 2049, "reject"  # 8196 bytes)]`. (Story V-T-F2 closure.)
  - **AC-7d** — NUL/control/bidi rejection: parametrized over `["x\x00y", "x\x1fy", "x‮y", "x⁦y"]` → `ValidationError`; admitted: `"x\ty"`, `"x\ny"`, `"x\ry"`.
  - **AC-7e** — `extra="forbid"` rejection: parametrized over every model `(AttemptSummary, ApplyContext, TransformProvenance, CapabilityBundle)` × one extra field.
  - **AC-7f** — `frozen=True` rejects attribute reassignment: parametrized over every field of every model.
  - **AC-7g** — Tuple immutability (no `.append`): `ctx.prior_attempts.append(x)` raises `AttributeError` (tuple has no `append`); also asserted for `failing_signals` and `evidence_paths`.
  - **AC-7h** — `applied_at` naive-datetime rejection: `TransformProvenance(..., applied_at=datetime(2026, 5, 18))` (no tz) raises `ValidationError`.
  - **AC-7i** — `plugin_version` / `recipe_version` regex rejection: parametrized over `["not-a-semver", "1", "1.2", "1.2.3.4.5", ""]` → `ValidationError`; admitted: `["1.2.3", "1.2.3-alpha.1", "1.2.3+build.42"]`.
  - **AC-7j** — JSON-shape pinning on `TransformProvenance`: `dumped = TransformProvenance(...).model_dump(mode="json"); assert set(dumped.keys()) == {"plugin_id","plugin_version","recipe_id","recipe_version","transform_kind","applied_at","capability_use_id"}`. (Catches symmetric `key`→`renamed_key` regressions.)

- [ ] **AC-8 — `tests/unit/transforms/test_transform_abc.py`**:
  - **AC-8a** — `Transform()` raises `TypeError` (ABC instantiation).
  - **AC-8b** — `FakeTransform(Transform)` minimal subclass that defines all four attributes (transform_id, diff_bytes, files_changed, provenance) instantiates and `isinstance(t, Transform)` is `True`.
  - **AC-8c** — `FakeTransform(Transform)` that omits one of the four attributes either fails type-check (mypy) or fails attribute access at runtime — pin the precedent (whichever `Probe(ABC)` uses). Fixture lives in test file.
  - **AC-8d** — `isinstance(t, Transform)` is `True` (the Phase-5 contract via ADR-0001 / ADR-0006 of Phase 5).

### Gates

- [ ] **AC-9** — `mypy --strict src/codegenie/transforms/` clean.
- [ ] **AC-10** — `ruff check src/codegenie/transforms/ tests/unit/transforms/` and `ruff format --check` clean.
- [ ] **AC-11** — TDD plan's red test exists in commit history, then green; concrete fixture constructors (NOT `...` ellipsis placeholders) in the red-test code.

## Implementation outline

1. **`src/codegenie/transforms/_forward.py` (NEW — Phase-3-Step-1 shim)**. Define the empty `class CapabilityBundle(BaseModel): model_config = ConfigDict(frozen=True, extra="forbid")` (body: `pass`; NO `_placeholder` field) and `SandboxedPath: TypeAlias = pathlib.Path`. Both substituted by S4-04 / S4-05 via *additive* edits (S4-05 adds CapabilityBundle fields here OR moves the class to `plugins/capabilities.py` and re-exports from `_forward.py`; S4-04 re-exports `SandboxedPath` from `plugins/sandbox_path.py`). Module imports limited to `{__future__, pathlib, typing, pydantic}`.
2. **`src/codegenie/transforms/transform.py` (NEW)**. Import `ABC` from `abc`; `BaseModel`, `ConfigDict`, `Field`, `field_validator` from `pydantic`. Declare `class Transform(ABC)` with **class-level type annotations** for the four attributes (mirror `src/codegenie/probes/base.py`'s `Probe(ABC)`; do NOT use `@property @abstractmethod`). Define `TransformProvenance(BaseModel)` with the seven fields from arch §Data model L800-806 including `capability_use_id: EventId`. Apply `field_validator` for the semver regex on `plugin_version` / `recipe_version` and the UTC-tz requirement on `applied_at`.
3. **`src/codegenie/transforms/apply_context.py` (NEW)**. Define `AttemptSummary` then `ApplyContext`. Use `tuple[...]` (not `list[...]`) for `failing_signals`, `evidence_paths`, `prior_attempts`. Coerce `list` → `tuple` via `field_validator(mode="before")` so YAML/JSON arrays parse. Apply `field_validator` on `prior_failure_summary` for the 8 KB UTF-8-bytes cap + NUL/control/bidi rejection.
4. **`src/codegenie/transforms/__init__.py`**. Re-export with explicit `__all__`: `Transform`, `TransformProvenance`, `ApplyContext`, `AttemptSummary`, `CapabilityBundle`, `SandboxedPath`.
5. **Tests**. `tests/unit/transforms/test_apply_context.py` (parametrized AC-7 suite) + `tests/unit/transforms/test_transform_abc.py` (AC-8 suite) + `tests/fence/test_transforms_module_purity.py` (AST-walks; mirrors S1-01 / S1-03 fence pattern).
6. Run `mypy --strict src/codegenie/transforms/` + `pytest tests/unit/transforms/ tests/fence/test_transforms_module_purity.py -v`.

## TDD plan — red / green / refactor

### Red — write the failing test first
Test file path: `tests/unit/transforms/test_apply_context.py`

```python
from datetime import UTC, datetime
import pytest
from pydantic import ValidationError

from codegenie.transforms import (
    ApplyContext, AttemptSummary, CapabilityBundle, TransformProvenance,
)
from codegenie.types.identifiers import (
    AttemptNumber, EventId, PluginId, RecipeId, SignalKind,
    TransformId, TransformKind, WorkflowId,
)


def _empty_caps() -> CapabilityBundle:
    """S4-05 will widen this; Phase-3-Step-1 ships an empty Pydantic shell."""
    return CapabilityBundle()


def _provenance() -> TransformProvenance:
    return TransformProvenance(
        plugin_id=PluginId("vulnerability-remediation--node--npm"),
        plugin_version="1.0.0",
        recipe_id=RecipeId("npm-lockfile-pin"),
        recipe_version="1.0.0",
        transform_kind=TransformKind("lockfile_pin"),
        applied_at=datetime.now(UTC),
        capability_use_id=EventId("01HXX00000000000000000000Z"),
    )


def test_apply_context_defaults_to_empty_prior_attempts() -> None:
    ctx = ApplyContext(workflow_id=WorkflowId("01HXX00000000000000000000Z"), capabilities=_empty_caps())
    assert ctx.prior_attempts == ()
    assert ctx.attempt == AttemptNumber(1)


def test_apply_context_round_trips_with_prior_attempts() -> None:
    a = AttemptSummary(
        attempt=AttemptNumber(1),
        failing_signals=(SignalKind("tests"),),
        prior_failure_summary="x" * 100,
        evidence_paths=(),
        transform_id=TransformId("a" * 64),
    )
    ctx = ApplyContext(
        workflow_id=WorkflowId("01HXX00000000000000000000Z"),
        attempt=AttemptNumber(2),
        prior_attempts=(a,),
        capabilities=_empty_caps(),
    )
    parsed = ApplyContext.model_validate_json(ctx.model_dump_json())
    assert type(parsed) is ApplyContext
    assert parsed == ctx


@pytest.mark.parametrize(
    "raw,verdict",
    [
        ("x" * 8192, "accept"),
        ("x" * 8193, "reject"),
        ("💀" * 2048, "accept"),   # 8192 bytes (4-byte UTF-8 × 2048)
        ("💀" * 2049, "reject"),   # 8196 bytes
    ],
)
def test_prior_failure_summary_utf8_bytes_cap(raw: str, verdict: str) -> None:
    kwargs = dict(
        attempt=AttemptNumber(1),
        failing_signals=(),
        prior_failure_summary=raw,
        evidence_paths=(),
        transform_id=None,
    )
    if verdict == "accept":
        AttemptSummary(**kwargs)
    else:
        with pytest.raises(ValidationError):
            AttemptSummary(**kwargs)


@pytest.mark.parametrize("bad", ["x\x00y", "x\x1fy", "x‮y", "x⁦y"])
def test_prior_failure_summary_rejects_nul_control_bidi(bad: str) -> None:
    with pytest.raises(ValidationError):
        AttemptSummary(
            attempt=AttemptNumber(1),
            failing_signals=(),
            prior_failure_summary=bad,
            evidence_paths=(),
            transform_id=None,
        )


def test_apply_context_frozen_rejects_attribute_reassignment() -> None:
    ctx = ApplyContext(workflow_id=WorkflowId("01HXX00000000000000000000Z"), capabilities=_empty_caps())
    with pytest.raises(ValidationError):
        ctx.workflow_id = WorkflowId("01HYY00000000000000000000Z")  # type: ignore[misc]


def test_apply_context_extra_forbid() -> None:
    with pytest.raises(ValidationError):
        ApplyContext(  # type: ignore[call-arg]
            workflow_id=WorkflowId("01HXX00000000000000000000Z"),
            capabilities=_empty_caps(),
            oops="x",
        )


def test_prior_attempts_is_tuple_not_list() -> None:
    ctx = ApplyContext(workflow_id=WorkflowId("01HXX00000000000000000000Z"), capabilities=_empty_caps())
    assert isinstance(ctx.prior_attempts, tuple)
    with pytest.raises(AttributeError):
        ctx.prior_attempts.append(...)  # type: ignore[attr-defined]


def test_transform_provenance_naive_datetime_rejected() -> None:
    with pytest.raises(ValidationError):
        TransformProvenance(
            plugin_id=PluginId("vulnerability-remediation--node--npm"),
            plugin_version="1.0.0",
            recipe_id=RecipeId("npm-lockfile-pin"),
            recipe_version="1.0.0",
            transform_kind=TransformKind("lockfile_pin"),
            applied_at=datetime(2026, 5, 18),   # naive — no tz
            capability_use_id=EventId("01HXX00000000000000000000Z"),
        )


@pytest.mark.parametrize("bad_version", ["not-a-semver", "1", "1.2", "1.2.3.4.5", ""])
def test_transform_provenance_rejects_non_semver(bad_version: str) -> None:
    with pytest.raises(ValidationError):
        TransformProvenance(
            plugin_id=PluginId("p"),
            plugin_version=bad_version,
            recipe_id=RecipeId("r"),
            recipe_version="1.0.0",
            transform_kind=TransformKind("lockfile_pin"),
            applied_at=datetime.now(UTC),
            capability_use_id=EventId("01HXX00000000000000000000Z"),
        )


def test_transform_provenance_json_shape_pinned() -> None:
    dumped = _provenance().model_dump(mode="json")
    assert set(dumped.keys()) == {
        "plugin_id", "plugin_version", "recipe_id", "recipe_version",
        "transform_kind", "applied_at", "capability_use_id",
    }


# tests/unit/transforms/test_transform_abc.py:

from codegenie.transforms import SandboxedPath, Transform, TransformProvenance


def test_transform_bare_instantiation_raises() -> None:
    with pytest.raises(TypeError):
        Transform()  # type: ignore[abstract]


def test_transform_subclass_with_all_attributes_works() -> None:
    class FakeTransform(Transform):
        transform_id = TransformId("a" * 64)
        diff_bytes = b""
        files_changed: tuple[SandboxedPath, ...] = ()
        provenance = _provenance()

    t = FakeTransform()
    assert isinstance(t, Transform)
```

State why it fails: `ModuleNotFoundError: codegenie.transforms` — the package and modules don't exist yet.

### Green — minimal pass
- Add `src/codegenie/transforms/_forward.py` with the empty `CapabilityBundle` Pydantic shell + `SandboxedPath: TypeAlias = Path` alias.
- Add `src/codegenie/transforms/transform.py` with `Transform(ABC)` (class-level annotations) + `TransformProvenance` (seven fields including `capability_use_id: EventId`).
- Add `src/codegenie/transforms/apply_context.py` with `AttemptSummary` + `ApplyContext` (tuple containers, not list).
- Update `src/codegenie/transforms/__init__.py` re-exports with exact `__all__`.

### Refactor
- Apply `field_validator("prior_failure_summary")` for the 8 KB UTF-8-bytes cap + NUL/control/bidi rejection (E20 closure). Allowed control chars: `\t` (`\x09`), `\n` (`\x0a`), `\r` (`\x0d`). Rejected: `\x00`–`\x08`, `\x0b`–`\x0c`, `\x0e`–`\x1f`, `‪`–`‮`, `⁦`–`⁩`.
- Apply `field_validator(mode="before")` to coerce `list` → `tuple` on `failing_signals`, `evidence_paths`, `prior_attempts` for YAML/JSON ingest compatibility.
- Apply `field_validator("applied_at")` to reject naive datetimes and require `tz is timezone.utc` (or coerce via `astimezone(UTC)`).
- Apply `field_validator("plugin_version", "recipe_version")` with regex `^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][\w.-]+)?$`.
- Land a contract-snapshot-helper docstring on `Transform`, `ApplyContext`, `AttemptSummary`, `TransformProvenance` — each names ADR-0001 + the Phase-5 wrap target (which subclass / method consumes this).
- Confirm S5-02's `NpmLockfileTransform(Transform)` will compile against this ABC by writing the four required attributes as class variables. Document the pattern in `Transform`'s docstring with a minimal-subclass example.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/transforms/_forward.py` | NEW — empty `CapabilityBundle(BaseModel)` shell (S4-05 substitutes additively) + `SandboxedPath: TypeAlias = Path` (S4-04 re-exports). One-way import direction; never reaches into `plugins/`. |
| `src/codegenie/transforms/transform.py` | NEW — `Transform(ABC)` with class-level annotations + `TransformProvenance(BaseModel)` (7 fields including `capability_use_id: EventId` per arch §Data model L800-806). |
| `src/codegenie/transforms/apply_context.py` | NEW — `ApplyContext` + `AttemptSummary` with Phase-5-required `prior_attempts` already shipped as `tuple[AttemptSummary, ...] = ()`. |
| `src/codegenie/transforms/__init__.py` | Extend (from S1-03) — re-export `Transform`, `TransformProvenance`, `ApplyContext`, `AttemptSummary`, `CapabilityBundle`, `SandboxedPath` with exact `__all__`. |
| `tests/unit/transforms/test_apply_context.py` | NEW — AC-7 suite: defaults, round-trip, UTF-8 bytes cap (parametrized including emoji), NUL/control/bidi rejection, frozen, extra-forbid, tuple-not-list, naive-datetime rejection, semver-regex, JSON-shape pinning. |
| `tests/unit/transforms/test_transform_abc.py` | NEW — AC-8 suite: bare `Transform()` raises `TypeError`; `FakeTransform(Transform)` minimal subclass instantiates; `isinstance(t, Transform)` is `True`. |
| `tests/fence/test_transforms_module_purity.py` | NEW — AST source-scan: `transform.py`, `apply_context.py`, `_forward.py` import sets restricted; `model_construct` absent; `__all__` set pinned. Mirrors S1-01 / S1-03 fence pattern. |

## Out of scope

- **Concrete `NpmLockfileTransform` / `DockerfileBaseImageTransform`** — S5-02 / S5-03. This story only ships the ABC.
- **`CapabilityBundle` real fields** — S4-05 substitutes the placeholder; the import path is stable.
- **`SandboxedPath` real type** — S4-04 substitutes the placeholder; the import path is stable.
- **`RecipeEngine` Protocol** — S5-01.
- **`RemediationOrchestrator._validate_stage6` method** — S6-04. This story ships the types its signature consumes; not the method itself.
- **Contract snapshot test** (`test_phase5_contract_snapshot.py`) — S6-06.

## Notes for the implementer

- **`prior_attempts` is `tuple[AttemptSummary, ...] = ()` — not `list[AttemptSummary] = Field(default_factory=list)`.** Pydantic v2 `frozen=True` freezes attribute reassignment, NOT in-place mutation of mutable containers — `ctx.prior_attempts.append(x)` on a list silently succeeds. Tuples are truly immutable. Phase 5's ADR-P5-002 retry envelope updates `prior_attempts` via `ctx.model_copy(update={"prior_attempts": ctx.prior_attempts + (new_summary,)})` (immutable-update idiom). Validators coerce `list` → `tuple` for YAML/JSON ingest. Same convention for `failing_signals` and `evidence_paths`.
- **`prior_attempts` shipped at all is load-bearing.** ADR-0001 §Tradeoffs accepts the field as dead weight in Phase 3; deleting it because "Phase 3 never uses it" breaks Phase 5's `ADR-P5-002` amendment guarantee. Phase 5 amends behavior, not shape.
- **`Transform` is an ABC, not a Protocol** — load-bearing per ADR-0001 §Tradeoffs row 3 + Phase 5 ADR-0006. Don't convert to `@runtime_checkable Protocol` for "consistency with `Plugin` / `RecipeEngine`"; the asymmetry is documented.
- **Pattern precedent for the ABC**: `src/codegenie/probes/base.py`'s `Probe(ABC)` uses **class-level type annotations** (not `@property @abstractmethod`) for the contract attributes and `@abstractmethod` only for the `run` method. Mirror that exactly. Subclasses define the attributes as class variables (see `FakeTransform` in the TDD plan). Do NOT mix patterns — pick annotations and stay.
- **`TransformProvenance.capability_use_id: EventId` is load-bearing.** Arch §Data model L800-806 ships it. ADR-0011 frames `Capability` tokens as audit-tier (NOT runtime-unforgeable); `capability_use_id` is the **audit anchor** that ties a Transform to its `CapabilityUsed` event in the two-stream event log (S6-01 / Phase 5 §Capability budgets). Omitting it weakens ADR-0011's "audit + lint" framing and breaks the Phase-9 replay-consistency property.
- **`plugin_version` / `recipe_version` are `str` with regex validator, not `SemverVersion`.** Arch §Data model L803-804 references `SemverVersion`, but S1-01's newtype catalog (14 names) does not include it. Defending the boundary with a `field_validator` regex is the pragmatic resolution; if a `SemverVersion` newtype lands later (extension), it adopts this regex as its smart constructor. Document the arch-drift in code comments; do NOT introduce a new newtype in this story (scope creep — belongs to S1-01 amendment).
- **`CapabilityBundle` is an empty Pydantic shell, NOT a placeholder with `_placeholder: bool = True`.** S4-05 *adds* fields by extension; no removal, no `model_rebuild()` dance at substitution time. `class CapabilityBundle(BaseModel): model_config = ConfigDict(frozen=True, extra="forbid")` body is `pass`. Pydantic happily validates `CapabilityBundle()` with no fields.
- **`SandboxedPath: TypeAlias = pathlib.Path`** is honest framing per ADR-0011: until S4-04 lands the real `SandboxedPath` (with `O_NOFOLLOW`), `files_changed: tuple[Path, ...]` is what Phase 3 has. S4-04 substitutes by re-exporting `SandboxedPath` from `plugins/sandbox_path.py` through `_forward.py`; every import site stays stable. The runtime in-jail check comes from S4-04, not from `Transform`'s constructor.
- **`prior_failure_summary` 8 KB cap is UTF-8 bytes, not chars** — `len(s) <= 8192` lets through up to 4× too much data with 4-byte chars (emoji, CJK). Use `len(s.encode("utf-8")) <= 8192`. The canary-check downstream (Phase 5) assumes this byte cap.
- **NUL / control / bidi rejection in `prior_failure_summary`** is the E20 edge-case closure (adversarial repo content). Reject `\x00`–`\x08`, `\x0b`–`\x0c`, `\x0e`–`\x1f`, and bidi controls (`U+202A`–`U+202E`, `U+2066`–`U+2069`). Admit `\t\n\r` (legitimate whitespace in error messages). Phase 5 may widen via Pydantic versioning; for Phase 3, hard reject is the right default.
- **`applied_at: datetime`** must be timezone-aware UTC. Use `Field(default_factory=lambda: datetime.now(UTC))` and a `field_validator` that asserts `value.tzinfo is not None` (raise on naive). Naive datetimes have bitten earlier phases; the convention here is UTC-aware.
- **Don't import from `codegenie.plugins.*`** at runtime in `transforms/`. The `transforms/` namespace is the contract-frozen layer (ADR-0001); importing `plugins/` would tangle the dependency direction. The `_forward.py` shim is the only Phase-3-Step-1 substitute; S4-04 / S4-05 amend it additively (re-exports, never removals).
- **Extension by addition**: subclassing `Transform` is the open-for-extension path (Phase 4's `LLMProducedTransform(Transform)`; Phase 7's `DistrolessImageTransform(Transform)`). The ABC itself is closed for modification — any new attribute on `Transform` is a Phase-3 ADR amendment. Document this in `Transform`'s docstring.
- **Contract-snapshot test (S6-06) is the gate.** Once this story lands, any drift on `Transform` / `TransformProvenance` / `ApplyContext` / `AttemptSummary` shapes is caught by `tests/integration/test_phase5_contract_snapshot.py` byte-snapshotting the surface. Renames or field additions/removals are a deliberate ADR-amend-and-regenerate-the-snapshot ceremony, not a silent edit.
