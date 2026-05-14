# Story S1-03 — Adapter `Protocol`s + `AdapterConfidence` discriminated union

**Step:** Step 1 — Plant new domain primitives, kernel contracts, and the nine new ADRs
**Status:** Ready
**Effort:** S
**Depends on:** S1-01
**ADRs honored:** 02-ADR-0007

## Context

Phase 3's first plugin ships **four** adapters (`DepGraphAdapter`, `ImportGraphAdapter`, `ScipAdapter`, `TestInventoryAdapter`). Phase 2 ships them as **typed surfaces only** — `@runtime_checkable Protocol` classes plus the `AdapterConfidence = Trusted | Degraded | Unavailable` discriminated union. No implementations. The purpose is documentation as code: when Phase 3's author writes `class DepGraphNpm:`, mypy and `isinstance` agree on whether the shape matches. The contract trip-wire (`tests/integration/adapters/test_phase3_handoff_smoke.py`, lands skipped in S7-04) is the structural insurance against drift; this story plants the typed surface.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #7 — Adapter Protocol definitions` — the four signatures and the rationale for `@runtime_checkable`.
  - `../phase-arch-design.md §"Data model"` — `AdapterConfidence` shape with `Trusted | Degraded(reason) | Unavailable(reason)`.
  - `../phase-arch-design.md §"Gap 1" — Adapter Protocol drift between Phase 2 and Phase 3` — why this story alone is not enough; the named structural insurance lives in S7-04 (skipped) + S8-04 (Phase 3 unskip).
  - `../phase-arch-design.md §"Design patterns applied"` row 3 — structural subtyping (PEP 544) over Abstract Factory.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0007-no-plugin-loader-in-phase-2.md` — 02-ADR-0007 — Phase 2 ships Protocols + TCCMLoader skeleton, **never** implementations.
- **Production ADRs (if applicable):**
  - `../../../production/adrs/0032-plugin-adapter-protocols.md` (production ADR-0032 — adapters at `plugins/{slug}/adapters/*.py`) — Phase 2's commitment is the typing surface; ADR-0032 places real implementations in Phase 3 plugin source trees.
- **Source design:**
  - `../final-design.md §"Synthesis ledger" — Kernel scaffolding ships, no Plugin Loader` — the explicit scope.
- **Existing code:**
  - `src/codegenie/probes/base.py` — pattern for value types over decorators-as-classes; mirror its frozen-dataclass / pydantic discipline (`AdapterConfidence` uses pydantic per `../phase-arch-design.md §"Data model"`).
- **External docs (only if directly relevant):**
  - https://peps.python.org/pep-0544/ — `Protocol` + `@runtime_checkable` reference.

## Goal

Implement `src/codegenie/adapters/{__init__.py,protocols.py,confidence.py}` — four `@runtime_checkable Protocol` classes (`DepGraphAdapter`, `ImportGraphAdapter`, `ScipAdapter`, `TestInventoryAdapter`) plus `AdapterConfidence = Trusted | Degraded | Unavailable` Pydantic discriminated union — with **zero implementations** and a per-Protocol `isinstance` structural-conformance test using minimal stubs.

## Acceptance criteria

- [ ] **AC-1.** `src/codegenie/adapters/__init__.py` exports `DepGraphAdapter`, `ImportGraphAdapter`, `ScipAdapter`, `TestInventoryAdapter`, `AdapterConfidence`, `Trusted`, `Degraded`, `Unavailable` via `__all__`.
- [ ] **AC-2.** Each of the four Protocols is decorated with `@runtime_checkable` and declares the exact signatures from `../phase-arch-design.md §"Component design" #7`:
  - `DepGraphAdapter.consumers(self, pkg: str) -> list[str]`, `producers(self, pkg: str) -> list[str]`, `confidence(self) -> AdapterConfidence`.
  - `ImportGraphAdapter.reverse_lookup(self, module: str) -> list[str]`, `confidence(self) -> AdapterConfidence`.
  - `ScipAdapter.refs(self, symbol: str) -> list[Occurrence]`, `confidence(self) -> AdapterConfidence` — `Occurrence` is a Phase-2-local typed dataclass (`Occurrence(file: str, line: int, col: int)`); the field set is fixed and frozen, not a Pydantic stand-in for the SCIP wire format.
  - `TestInventoryAdapter.tests_exercising(self, symbol: str) -> list[TestId]`, `confidence(self) -> AdapterConfidence` — `TestId = NewType("TestId", str)` (declared in this story, not in S1-05's identifiers, because it's adapter-tier and not used elsewhere in Phase 2).
- [ ] **AC-3.** `AdapterConfidence = Annotated[Union[Trusted, Degraded, Unavailable], Field(discriminator="kind")]`; each variant is Pydantic `frozen=True, extra="forbid"` with `kind: Literal["..."]` and a single `reason: str` field on `Degraded` and `Unavailable` (`Trusted` has no extra fields).
- [ ] **AC-4.** Per Protocol, a minimal stub class (no inheritance, no `Protocol` reference, just the methods) satisfies `isinstance(stub_instance, ProtocolClass)` — the `@runtime_checkable` contract is real.
- [ ] **AC-5.** A test with an *incomplete* stub (one method missing) returns `isinstance(stub, ProtocolClass) is False`, confirming `@runtime_checkable` actually checks. (Note: `@runtime_checkable` checks attribute presence only, not signatures — that limitation is documented in the test docstring.)
- [ ] **AC-6.** Zero implementations exist in `src/codegenie/`. A test asserts no module under `src/codegenie/` that is **not** `adapters/` itself imports `DepGraphAdapter` as a base class (`isinstance` check at import time across `pkgutil.walk_packages`).
- [ ] **AC-7.** `AdapterConfidence` variants round-trip via `pydantic.TypeAdapter(AdapterConfidence).dump_json` / `.validate_json` (identity).
- [ ] **AC-8.** The TDD plan's red test exists, was committed, and is green.
- [ ] **AC-9.** `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest tests/unit/adapters/` all pass on the touched files.

## Implementation outline

1. Create `src/codegenie/adapters/confidence.py` with `Trusted`, `Degraded`, `Unavailable` (Pydantic, `frozen=True, extra="forbid"`, `kind` discriminator) + the `AdapterConfidence` `Annotated[Union, Field(discriminator="kind")]` alias.
2. Create `src/codegenie/adapters/protocols.py` with the four `@runtime_checkable Protocol` classes plus `Occurrence` (frozen dataclass) and `TestId` (`NewType`).
3. Create `src/codegenie/adapters/__init__.py` re-exporting all public names.
4. Write red tests — confirm `ImportError`.
5. Implement; confirm green.
6. Refactor — add module docstrings naming the Phase-3 consumer (per Protocol), the production ADR-0032 reference, and the Phase 3 plugin path expected to implement each.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/adapters/test_protocols.py`

```python
from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from codegenie.adapters import (
    AdapterConfidence,
    Degraded,
    DepGraphAdapter,
    ImportGraphAdapter,
    ScipAdapter,
    TestInventoryAdapter,
    Trusted,
    Unavailable,
)
from codegenie.adapters.protocols import Occurrence, TestId


# -------- AdapterConfidence variants --------

def test_adapter_confidence_variants_construct_and_roundtrip() -> None:
    adapter = TypeAdapter(AdapterConfidence)
    for instance in (
        Trusted(),
        Degraded(reason="scip_unavailable"),
        Unavailable(reason="tool_missing"),
    ):
        encoded = adapter.dump_json(instance)
        decoded = adapter.validate_json(encoded)
        assert decoded == instance
        assert type(decoded) is type(instance)


def test_adapter_confidence_rejects_unknown_kind() -> None:
    adapter = TypeAdapter(AdapterConfidence)
    with pytest.raises(ValidationError):
        adapter.validate_python({"kind": "what", "reason": "x"})


def test_degraded_and_unavailable_require_reason() -> None:
    with pytest.raises(ValidationError):
        Degraded.model_validate({"kind": "degraded"})
    with pytest.raises(ValidationError):
        Unavailable.model_validate({"kind": "unavailable"})


# -------- Protocol structural conformance --------

class _DepGraphStub:
    def consumers(self, pkg: str) -> list[str]: return []
    def producers(self, pkg: str) -> list[str]: return []
    def confidence(self) -> AdapterConfidence: return Trusted()


class _ImportGraphStub:
    def reverse_lookup(self, module: str) -> list[str]: return []
    def confidence(self) -> AdapterConfidence: return Trusted()


class _ScipStub:
    def refs(self, symbol: str) -> list[Occurrence]: return []
    def confidence(self) -> AdapterConfidence: return Trusted()


class _TestInventoryStub:
    def tests_exercising(self, symbol: str) -> list[TestId]: return []
    def confidence(self) -> AdapterConfidence: return Trusted()


class _IncompleteDepGraph:
    # missing producers + confidence
    def consumers(self, pkg: str) -> list[str]: return []


@pytest.mark.parametrize("stub_cls,proto", [
    (_DepGraphStub, DepGraphAdapter),
    (_ImportGraphStub, ImportGraphAdapter),
    (_ScipStub, ScipAdapter),
    (_TestInventoryStub, TestInventoryAdapter),
])
def test_runtime_checkable_accepts_complete_stub(stub_cls: type, proto: type) -> None:
    # @runtime_checkable conformance check is structural and attribute-based.
    assert isinstance(stub_cls(), proto)


def test_runtime_checkable_rejects_incomplete_stub() -> None:
    """@runtime_checkable checks attribute *presence* (PEP 544 §runtime_checkable);
    it does NOT validate method signatures. A class missing required methods
    must return False on isinstance."""
    assert isinstance(_IncompleteDepGraph(), DepGraphAdapter) is False


# -------- Zero-implementation invariant --------

def test_no_phase2_module_implements_adapter_protocol() -> None:
    """Phase 2 ships Protocols only (02-ADR-0007); Phase 3 plugins implement.
    Walk src/codegenie/ and assert no module other than `adapters/` provides
    a class that's an isinstance of any of the four Protocols."""
    import codegenie
    import importlib
    import inspect
    import pkgutil

    forbidden_protos = (DepGraphAdapter, ImportGraphAdapter, ScipAdapter, TestInventoryAdapter)
    offenders: list[str] = []
    for mod_info in pkgutil.walk_packages(codegenie.__path__, prefix="codegenie."):
        if mod_info.name.startswith("codegenie.adapters"):
            continue
        try:
            mod = importlib.import_module(mod_info.name)
        except Exception:
            continue
        for name, cls in inspect.getmembers(mod, inspect.isclass):
            if cls.__module__ != mod_info.name:
                continue
            try:
                if any(isinstance(cls(), proto) for proto in forbidden_protos):
                    offenders.append(f"{mod_info.name}.{name}")
            except Exception:
                # Cannot instantiate without args — fine for Phase 2; the test
                # is about isinstance, not type-check; if a class can't be
                # instantiated trivially it likely isn't an adapter.
                continue
    assert offenders == [], (
        f"02-ADR-0007 prohibits adapter implementations in Phase 2; found: {offenders}"
    )
```

Run — confirm `ImportError: cannot import name 'DepGraphAdapter' from 'codegenie.adapters'`. Commit.

### Green — make it pass

```python
# src/codegenie/adapters/confidence.py
from __future__ import annotations
from typing import Annotated, Literal, Union
from pydantic import BaseModel, ConfigDict, Field

class Trusted(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["trusted"] = "trusted"

class Degraded(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["degraded"] = "degraded"
    reason: str

class Unavailable(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["unavailable"] = "unavailable"
    reason: str

AdapterConfidence = Annotated[Union[Trusted, Degraded, Unavailable], Field(discriminator="kind")]
```

```python
# src/codegenie/adapters/protocols.py
from __future__ import annotations
from dataclasses import dataclass
from typing import NewType, Protocol, runtime_checkable

from codegenie.adapters.confidence import AdapterConfidence

TestId = NewType("TestId", str)

@dataclass(frozen=True)
class Occurrence:
    file: str
    line: int
    col: int

@runtime_checkable
class DepGraphAdapter(Protocol):
    def consumers(self, pkg: str) -> list[str]: ...
    def producers(self, pkg: str) -> list[str]: ...
    def confidence(self) -> AdapterConfidence: ...

@runtime_checkable
class ImportGraphAdapter(Protocol):
    def reverse_lookup(self, module: str) -> list[str]: ...
    def confidence(self) -> AdapterConfidence: ...

@runtime_checkable
class ScipAdapter(Protocol):
    def refs(self, symbol: str) -> list[Occurrence]: ...
    def confidence(self) -> AdapterConfidence: ...

@runtime_checkable
class TestInventoryAdapter(Protocol):
    def tests_exercising(self, symbol: str) -> list[TestId]: ...
    def confidence(self) -> AdapterConfidence: ...
```

```python
# src/codegenie/adapters/__init__.py
from codegenie.adapters.confidence import (
    AdapterConfidence, Degraded, Trusted, Unavailable,
)
from codegenie.adapters.protocols import (
    DepGraphAdapter, ImportGraphAdapter, Occurrence, ScipAdapter,
    TestId, TestInventoryAdapter,
)

__all__ = [
    "AdapterConfidence", "Degraded", "DepGraphAdapter", "ImportGraphAdapter",
    "Occurrence", "ScipAdapter", "TestId", "TestInventoryAdapter",
    "Trusted", "Unavailable",
]
```

### Refactor — clean up

- Module docstring on `protocols.py`: name each Protocol's Phase-3 consumer path (e.g., `plugins/vulnerability-remediation--node--npm/adapters/dep_graph_npm.py`). Reference 02-ADR-0007 §Consequences and the integration smoke test the architect named (`tests/integration/adapters/test_phase3_handoff_smoke.py`, lands skipped in S7-04 — name it in the docstring so anyone editing this file goes there next).
- Each Protocol docstring states the one-sentence semantic intent: `DepGraphAdapter.consumers(pkg)` returns "all internal packages that depend on `pkg`"; `producers(pkg)` returns "all internal packages `pkg` depends on" (this matters when Phase 3 author distinguishes them). Match `../phase-arch-design.md §"Component design" #7` verbatim.
- `Occurrence` is a `frozen=True` dataclass, not Pydantic — its only consumer is `ScipAdapter.refs()`, and Phase 3's adapter implementation will mmap the SCIP blob; Pydantic overhead is unwarranted. Docstring: "raw SCIP-decoded position; mmap-friendly".
- Run `ruff format`, `ruff check`, `mypy --strict src/codegenie/adapters/ tests/unit/adapters/`, `pytest tests/unit/adapters/ -v`.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/adapters/__init__.py` | New package; re-export the Protocol + confidence surface. |
| `src/codegenie/adapters/confidence.py` | New module; `AdapterConfidence` discriminated union. |
| `src/codegenie/adapters/protocols.py` | New module; four Protocol classes + `Occurrence` + `TestId`. |
| `tests/unit/adapters/test_protocols.py` | Red-then-green coverage: round-trip, `isinstance` conformance + rejection, zero-implementation invariant. |

## Out of scope

- **Actual adapter implementations** — handled in Phase 3 plugin source trees (`plugins/vulnerability-remediation--node--npm/adapters/`).
- **`Occurrence` evolution to match the SCIP wire format** — out of scope here; Phase 3 may extend with `kind: Literal["definition","reference","implementation"]` if the first real adapter needs it (02-ADR-0007 §Reversibility — extend by addition).
- **`AdapterConfidence` consumed by `IndexHealthProbe`** — explicitly NOT in Phase 2 per 02-ADR-0006; `IndexFreshness` and `AdapterConfidence` are *parallel* type families with no implicit composition.
- **The `tests/integration/adapters/test_phase3_handoff_smoke.py` Phase-3 entry-gate test** — landed (skipped) in S7-04; this story names it, S7-04 ships it.
- **TCCM consumers of the Protocols** — `TCCM.derived_queries`'s five variants reference the Protocols by name in the docs, not by Python import in Phase 2; S1-04 ships the `TCCM` model, S2-03 wires a mock dispatcher.

## Notes for the implementer

- **`@runtime_checkable` is structural, not signature-checking.** PEP 544 explicitly says `isinstance` checks only that the methods *exist* — not that they match the parameter types or return types. The test `test_runtime_checkable_rejects_incomplete_stub` makes this discoverable; the docstring on the test says so. Do not invent a `runtime_signature_checkable` decorator — Phase 3's mypy-strict pass is what catches signature drift at type-check time.
- **`TestId = NewType("TestId", str)` lives in `protocols.py`, not in S1-05's identifier file.** It's adapter-tier; S1-05's identifiers are *kernel*-tier (`IndexId`, `SkillId`, `TaskClassId`, `IndexName`) and used across multiple packages. The architect's rule: a newtype belongs where its consumer family lives.
- **No `Confidence` import side-effects.** `confidence.py` is pure typing — no logger, no I/O, no third-party deps beyond pydantic. The forbidden-patterns extension in S1-11 will catch `model_construct` here if it ever appears.
- **Zero-implementation walk test.** The test instantiates each class found in the codebase to check `isinstance`. Most Phase 0/1 classes will fail to instantiate without args; that's fine — the test only flags classes that CAN be instantiated trivially AND happen to satisfy the Protocol. The structural insurance is the gap S7-04 + S8-04 close more thoroughly (the explicit handoff smoke test).
- **`Trusted` has no `reason: str`.** Resist the urge to add one for symmetry with `Degraded` / `Unavailable`. `Trusted` carries the absence of degradation; a reason field on it is pattern-soup (final-design Anti-patterns §"Pattern soup" precedent).
- **Phase 2 Protocols may evolve, but only via ADR amendment.** If Phase 3's author finds `consumers(pkg: str)` should be `consumers(pkg: PackageId, *, transitively: bool = False)`, that requires an explicit ADR amendment to 02-ADR-0006/02-ADR-0007 (see `../phase-arch-design.md §"Open questions deferred to implementation"` #1 / Implementation risk #8). The handoff smoke test in S7-04 is the structural insurance.
