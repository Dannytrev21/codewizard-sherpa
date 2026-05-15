# Story S1-03 — Adapter `Protocol`s + `AdapterConfidence` discriminated union

**Step:** Step 1 — Plant new domain primitives, kernel contracts, and the nine new ADRs
**Status:** Ready (HARDENED 2026-05-15)
**Effort:** S
**Depends on:** S1-01
**ADRs honored:** 02-ADR-0007

## Validation notes (2026-05-15)

Hardened via `phase-story-validator` (verdict: HARDENED). Full report at [`_validation/S1-03-adapter-protocols-confidence.md`](_validation/S1-03-adapter-protocols-confidence.md). Edits applied:

1. **AC-3** explicit discriminator-string pinning ("trusted", "degraded", "unavailable") added — symmetric-swap mutation now caught (mirrors S1-01 hardening).
2. **AC-5** strengthened with explicit PEP 544 limitation note + parametrized over **all four** Protocols (was DepGraph-only).
3. **AC-6** strengthened with a static AST/inspect base-class check complementing the dynamic `pkgutil` walk — catches inheritance-style impls that fail trivial instantiation.
4. **New AC-10** — runtime immutability (`frozen=True`) verified by mutation attempt across all three `AdapterConfidence` variants.
5. **New AC-11** — `extra="forbid"` enforced on every variant; **`Trusted` explicitly rejects `reason`** (the "resist the urge to add reason for symmetry" Notes claim is now a test).
6. **New AC-12** — JSON-shape pin (`{"kind":"...", "reason":"..."}`) blocks symmetric `kind`→`tag` rename.
7. **New AC-13** — `Occurrence` frozen dataclass + exact field set `{file, line, col}` + (recommended) `slots=True`.
8. **New AC-14** — exhaustive `match` over `AdapterConfidence` with `assert_never`; mirror S1-01 AC-6a for mypy --warn-unreachable rehearsal.
9. **New AC-15** — module-purity invariant for `confidence.py` and `protocols.py` (no I/O, no logger, only `pydantic` + stdlib `typing`/`dataclasses`).
10. **New AC-16** — `model_construct` source-scan ban under `src/codegenie/adapters/**` (matches S1-01 mutation #10 and `phase-arch-design.md §"Anti-patterns avoided"`).
11. **AC-1** enumeration now includes `Occurrence` and `TestId` (Implementation outline already does).
12. **Notes for the implementer** extended with three design framings: deliberate non-extraction of a shared `HasConfidence` Protocol; `slots=True` on `Occurrence` for Phase 3 SCIP mmap-friendliness; variant-set extension is ADR-amendment-gated (mirror S1-01 discipline) — no `@register_adapter_confidence_variant` decorator.

No RESCUE-tier findings. Stage 3 research skipped (no `NEEDS RESEARCH` gaps).

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

- [ ] **AC-1.** `src/codegenie/adapters/__init__.py` exports exactly `{DepGraphAdapter, ImportGraphAdapter, ScipAdapter, TestInventoryAdapter, AdapterConfidence, Trusted, Degraded, Unavailable, Occurrence, TestId}` via `__all__`. A test asserts `set(codegenie.adapters.__all__) == {…}` (catches reorders, typos, and accidental surface widening).
- [ ] **AC-2.** Each of the four Protocols is decorated with `@runtime_checkable` and declares the exact signatures from `../phase-arch-design.md §"Component design" #7`:
  - `DepGraphAdapter.consumers(self, pkg: str) -> list[str]`, `producers(self, pkg: str) -> list[str]`, `confidence(self) -> AdapterConfidence`.
  - `ImportGraphAdapter.reverse_lookup(self, module: str) -> list[str]`, `confidence(self) -> AdapterConfidence`.
  - `ScipAdapter.refs(self, symbol: str) -> list[Occurrence]`, `confidence(self) -> AdapterConfidence` — `Occurrence` is a Phase-2-local typed dataclass (`Occurrence(file: str, line: int, col: int)`); the field set is fixed and frozen, not a Pydantic stand-in for the SCIP wire format.
  - `TestInventoryAdapter.tests_exercising(self, symbol: str) -> list[TestId]`, `confidence(self) -> AdapterConfidence` — `TestId = NewType("TestId", str)` (declared in this story, not in S1-05's identifiers, because it's adapter-tier and not used elsewhere in Phase 2).
- [ ] **AC-3.** `AdapterConfidence = Annotated[Union[Trusted, Degraded, Unavailable], Field(discriminator="kind")]`; each variant is Pydantic `frozen=True, extra="forbid"` with `kind: Literal["..."]` and a single `reason: str` field on `Degraded` and `Unavailable` (`Trusted` has no extra fields). **Discriminator string values are pinned**: `Trusted.kind == "trusted"`, `Degraded.kind == "degraded"`, `Unavailable.kind == "unavailable"`. These three strings are a cross-ADR / cross-phase contract (02-ADR-0007 §Consequences; Phase 3 plugin renderers, golden files, and downstream consumers depend on them) — a symmetric swap of two `kind` values would round-trip cleanly but break every external consumer; AC-3 forbids it.
- [ ] **AC-4.** Per Protocol, a minimal stub class (no inheritance, no `Protocol` reference, just the methods) satisfies `isinstance(stub_instance, ProtocolClass)` — the `@runtime_checkable` contract is real. **Parametrized over all four Protocols.**
- [ ] **AC-5.** For **each of the four Protocols**, a stub with exactly one declared method removed returns `isinstance(stub, ProtocolClass) is False`. The test docstring cites PEP 544 §runtime_checkable verbatim: `@runtime_checkable` checks attribute *presence*, not signatures; signature drift is a `mypy --strict` concern at type-check time, never a runtime check. AC-5 makes the limitation discoverable AND symmetric across all four contracts (was DepGraph-only).
- [ ] **AC-6.** Zero implementations exist in `src/codegenie/`. Two complementary checks fire:
  - **Dynamic.** `pkgutil.walk_packages(codegenie.__path__)` imports every non-`adapters` module; for each importable class whose `__module__` matches, the class is constructed with `()` (best-effort), and if the instance satisfies `isinstance(inst, AnyAdapterProtocol)` the test fails. (Documented limitation: classes that require constructor args are silently skipped — closed by the static check below.)
  - **Static.** For every `.py` file under `src/codegenie/` not under `src/codegenie/adapters/`, an `ast.parse` walk asserts no `ClassDef` lists any of `DepGraphAdapter | ImportGraphAdapter | ScipAdapter | TestInventoryAdapter` in its `bases`. Catches inheritance-style implementations that the dynamic walk misses.
- [ ] **AC-7.** `AdapterConfidence` variants round-trip via `pydantic.TypeAdapter(AdapterConfidence).dump_json` / `.validate_json` (identity). The test asserts BOTH `decoded == instance` AND `type(decoded) is type(instance)` for every variant (the type-preservation arm guards against a regression that drops `Field(discriminator="kind")` from the `Annotated[Union, …]` wrapper).
- [ ] **AC-8.** The TDD plan's red test exists, was committed, and is green.
- [ ] **AC-9.** `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest tests/unit/adapters/` all pass on the touched files.
- [ ] **AC-10.** **Runtime immutability is enforced.** For each variant `V ∈ {Trusted, Degraded, Unavailable}`, attempting `inst.<field> = <new value>` raises `pydantic.ValidationError`. A regression that drops `frozen=True` is caught.
- [ ] **AC-11.** **`extra="forbid"` is enforced on every variant.** Constructing `Trusted(reason="x")`, `Degraded(reason="x", extra="bad")`, and `Unavailable(reason="x", extra="bad")` each raise `pydantic.ValidationError`. **The `Trusted`-rejects-`reason` case is explicit and named**: `Trusted` carries the *absence* of degradation; a `reason` field on it is the "pattern soup" smell `phase-arch-design.md §Anti-patterns` and `final-design §Anti-patterns §"Pattern soup"` flag, and AC-11 makes the "resist the urge to add reason for symmetry" Notes claim test-enforced rather than convention-enforced.
- [ ] **AC-12.** **JSON shape is pinned.** A test asserts that `TypeAdapter(AdapterConfidence).dump_python(Degraded(reason="x"))` equals exactly `{"kind": "degraded", "reason": "x"}` (and analogous fixtures for `Trusted` / `Unavailable`). Catches a symmetric `kind` → `tag` discriminator-field rename that AC-7's Python-object round-trip would silently tolerate. (Cross-ADR contract: 02-ADR-0007 §Consequences; Phase 3 plugin TCCM renderer, golden files, and `repo-context.yaml` all read the literal key `"kind"`.)
- [ ] **AC-13.** `Occurrence` is a `dataclass(frozen=True)`. A test asserts: `dataclasses.is_dataclass(Occurrence)`; `Occurrence.__dataclass_params__.frozen is True`; `{f.name for f in dataclasses.fields(Occurrence)} == {"file", "line", "col"}`; mutating an instance raises `dataclasses.FrozenInstanceError`. (If `slots=True` is also adopted per Notes for the implementer §"`Occurrence` and `slots=True`", a fourth assertion may verify `not hasattr(inst, "__dict__")`.)
- [ ] **AC-14.** **`AdapterConfidence` is exhaustively matchable with `assert_never`.** A test executes a `match` over a parametrized fixture of every variant and uses `typing.assert_never` on the unreachable arm. Adding a fifth variant without extending the `match` is caught at `mypy --warn-unreachable` time once S1-11's per-module overrides include `codegenie.adapters.confidence`; the runtime test ensures construction reaches every arm today. (Mirror of S1-01 AC-6a discipline.)
- [ ] **AC-15.** **Module purity invariant.** A test imports `codegenie.adapters.confidence` and `codegenie.adapters.protocols` and asserts (via `inspect.getmembers(mod, inspect.ismodule)` + import-time AST scan) that neither module imports any of: `logging`, `structlog`, `os` (except `os.PathLike`-style typing imports — none expected), `subprocess`, `socket`, `httpx`, `requests`, `anthropic`, `openai`, or any module under `codegenie.parsers` / `codegenie.probes` / `codegenie.exec`. Permitted: `__future__`, `typing`, `dataclasses`, `pydantic`. Catches a future contributor accidentally smuggling I/O into the typing surface (CLAUDE.md "No LLM in gather pipeline" + arch §Component #7 "pure typing, ~80 LOC total").
- [ ] **AC-16.** **`model_construct` is forbidden under `src/codegenie/adapters/**`.** An AST-walk source-scan test (mirroring the S1-01 / S1-11 forbidden-patterns extension) asserts no `Call` node with `attr == "model_construct"` exists in `confidence.py` or `protocols.py`. Pydantic's `model_construct` bypasses validation; `phase-arch-design.md §"Anti-patterns avoided"` row 12 + final-design §Anti-patterns ban it under the typed-sum packages.

## Implementation outline

1. Create `src/codegenie/adapters/confidence.py` with `Trusted`, `Degraded`, `Unavailable` (Pydantic, `frozen=True, extra="forbid"`, `kind` discriminator with pinned strings `"trusted"`/`"degraded"`/`"unavailable"`) + the `AdapterConfidence` `Annotated[Union, Field(discriminator="kind")]` alias.
2. Create `src/codegenie/adapters/protocols.py` with the four `@runtime_checkable Protocol` classes plus `Occurrence` (frozen dataclass — `@dataclass(frozen=True, slots=True)` recommended; see Notes for the implementer §"`Occurrence` and `slots=True`") and `TestId` (`NewType`).
3. Create `src/codegenie/adapters/__init__.py` re-exporting all public names; `__all__` exactly matches `EXPECTED_PUBLIC_SURFACE` from the test (AC-1).
4. Write red tests — confirm `ImportError`. Sixteen ACs land sixteen test groups (see TDD plan); the surface test (AC-1) red-greens the `__all__` shape, and the static + dynamic AC-6 arms run from the same test file even though they reach into the wider tree.
5. Implement; confirm green. Run `pytest tests/unit/adapters/ -v` and verify every parametrize ID appears.
6. Refactor — add module docstrings naming the Phase-3 consumer (per Protocol), the production ADR-0032 reference, and the Phase 3 plugin path expected to implement each. Re-run `mypy --strict src/codegenie/adapters/ tests/unit/adapters/` to confirm no regressions.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/adapters/test_protocols.py`

```python
from __future__ import annotations

import ast
import dataclasses
import importlib
import inspect
import pkgutil
from pathlib import Path
from typing import assert_never

import pytest
from pydantic import TypeAdapter, ValidationError

import codegenie
from codegenie import adapters as adapters_pkg
from codegenie.adapters import (
    AdapterConfidence,
    Degraded,
    DepGraphAdapter,
    ImportGraphAdapter,
    Occurrence,
    ScipAdapter,
    TestId,
    TestInventoryAdapter,
    Trusted,
    Unavailable,
)
from codegenie.adapters import confidence as confidence_mod
from codegenie.adapters import protocols as protocols_mod


# -------- __all__ surface (AC-1) --------

EXPECTED_PUBLIC_SURFACE = {
    "DepGraphAdapter",
    "ImportGraphAdapter",
    "ScipAdapter",
    "TestInventoryAdapter",
    "AdapterConfidence",
    "Trusted",
    "Degraded",
    "Unavailable",
    "Occurrence",
    "TestId",
}


def test_adapters_all_is_exactly_the_public_surface() -> None:
    """AC-1: `__all__` is a frozen contract — reorders, typos, and accidental
    surface widening must be caught at unit-test time, not at Phase 3 land time."""
    assert set(adapters_pkg.__all__) == EXPECTED_PUBLIC_SURFACE


# -------- AdapterConfidence variants (AC-3, AC-7, AC-12) --------

CONFIDENCE_INSTANCES: list[AdapterConfidence] = [
    Trusted(),
    Degraded(reason="scip_unavailable"),
    Unavailable(reason="tool_missing"),
]


@pytest.mark.parametrize("instance", CONFIDENCE_INSTANCES)
def test_adapter_confidence_variants_construct_and_roundtrip(
    instance: AdapterConfidence,
) -> None:
    """AC-7: round-trip identity through the discriminated union; nested
    concrete-type preservation guards against a regression that drops
    `Field(discriminator="kind")` from the `Annotated[Union, …]` wrapper."""
    adapter = TypeAdapter(AdapterConfidence)
    encoded = adapter.dump_json(instance)
    decoded = adapter.validate_json(encoded)
    assert decoded == instance
    assert type(decoded) is type(instance)


def test_discriminator_strings_are_exactly_pinned() -> None:
    """AC-3: discriminator strings are a cross-ADR / cross-phase contract
    (02-ADR-0007 §Consequences). A symmetric swap (e.g. ``Trusted.kind = "degraded"``
    and ``Degraded.kind = "trusted"``) would pass the round-trip test but break
    every Phase 3 plugin renderer, golden file, and `repo-context.yaml` consumer."""
    assert Trusted().kind == "trusted"
    assert Degraded(reason="x").kind == "degraded"
    assert Unavailable(reason="x").kind == "unavailable"


@pytest.mark.parametrize(
    "instance,expected_json",
    [
        (Trusted(), {"kind": "trusted"}),
        (Degraded(reason="scip_unavailable"),
         {"kind": "degraded", "reason": "scip_unavailable"}),
        (Unavailable(reason="tool_missing"),
         {"kind": "unavailable", "reason": "tool_missing"}),
    ],
)
def test_json_shape_pinned(
    instance: AdapterConfidence, expected_json: dict[str, str]
) -> None:
    """AC-12: catches a symmetric `kind` → `tag` discriminator-field rename
    that the Python-object round-trip in AC-7 tolerates. The literal key
    ``"kind"`` is a cross-phase contract."""
    adapter = TypeAdapter(AdapterConfidence)
    assert adapter.dump_python(instance) == expected_json


def test_adapter_confidence_rejects_unknown_kind() -> None:
    adapter = TypeAdapter(AdapterConfidence)
    with pytest.raises(ValidationError):
        adapter.validate_python({"kind": "what", "reason": "x"})


def test_degraded_and_unavailable_require_reason() -> None:
    with pytest.raises(ValidationError):
        Degraded.model_validate({"kind": "degraded"})
    with pytest.raises(ValidationError):
        Unavailable.model_validate({"kind": "unavailable"})


# -------- extra="forbid" + frozen (AC-10, AC-11) --------

def test_trusted_rejects_reason_field() -> None:
    """AC-11: ``Trusted`` carries the *absence* of degradation. A ``reason``
    field on ``Trusted`` is the "pattern soup" smell flagged by
    `phase-arch-design.md §Anti-patterns`. The "resist the urge to add reason
    for symmetry" Notes claim is enforced here, not by convention."""
    with pytest.raises(ValidationError):
        Trusted.model_validate({"kind": "trusted", "reason": "x"})


def test_degraded_rejects_extra_field() -> None:
    with pytest.raises(ValidationError):
        Degraded.model_validate({"kind": "degraded", "reason": "x", "extra": "bad"})


def test_unavailable_rejects_extra_field() -> None:
    with pytest.raises(ValidationError):
        Unavailable.model_validate(
            {"kind": "unavailable", "reason": "x", "extra": "bad"}
        )


@pytest.mark.parametrize("instance", CONFIDENCE_INSTANCES)
def test_adapter_confidence_instances_are_immutable(
    instance: AdapterConfidence,
) -> None:
    """AC-10: ``frozen=True`` is enforced by runtime mutation attempt.
    Dropping ``frozen=True`` from ``ConfigDict`` is a silent regression
    otherwise — round-trip tests don't exercise mutation."""
    with pytest.raises(ValidationError):
        instance.kind = "what"  # type: ignore[misc]


# -------- Exhaustive match (AC-14) --------

@pytest.mark.parametrize("instance", CONFIDENCE_INSTANCES)
def test_match_is_exhaustive_over_adapter_confidence(
    instance: AdapterConfidence,
) -> None:
    """AC-14: every consumer of ``AdapterConfidence`` (today: Phase 3 plugin
    renderers; tomorrow: bundle metadata layering) MUST pattern-match every
    variant. ``mypy --warn-unreachable`` per-module (S1-11) enforces at
    type-check time; this test rehearses the runtime construction path of
    every arm. Mirror of S1-01 AC-6a."""
    match instance:
        case Trusted():
            label = "trusted"
        case Degraded(reason=r):
            label = f"degraded:{r}"
        case Unavailable(reason=r):
            label = f"unavailable:{r}"
        case _:
            assert_never(instance)
    assert label  # non-empty — every arm must yield a value


# -------- Occurrence (AC-13) --------

def test_occurrence_is_frozen_dataclass_with_exact_fields() -> None:
    """AC-13: ``Occurrence`` is the only Phase-2-local concrete value type
    in the adapter surface (everything else is a Protocol or Pydantic model).
    A frozen + field-set assertion catches drift if a contributor reaches
    for a Pydantic stand-in or extends the wire format here (out of scope —
    Phase 3 may extend with ADR, per the Out-of-scope section)."""
    assert dataclasses.is_dataclass(Occurrence)
    assert Occurrence.__dataclass_params__.frozen is True
    assert {f.name for f in dataclasses.fields(Occurrence)} == {"file", "line", "col"}
    inst = Occurrence(file="a.ts", line=1, col=2)
    with pytest.raises(dataclasses.FrozenInstanceError):
        inst.file = "b.ts"  # type: ignore[misc]


# -------- Protocol structural conformance (AC-4, AC-5) --------

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


# Incomplete stubs: each removes exactly one declared method, parametrized
# below so AC-5 fires for ALL four Protocols (was DepGraph-only).

class _IncompleteDepGraph:
    def consumers(self, pkg: str) -> list[str]: return []
    def producers(self, pkg: str) -> list[str]: return []
    # confidence() removed


class _IncompleteImportGraph:
    def reverse_lookup(self, module: str) -> list[str]: return []
    # confidence() removed


class _IncompleteScip:
    def refs(self, symbol: str) -> list[Occurrence]: return []
    # confidence() removed


class _IncompleteTestInventory:
    def tests_exercising(self, symbol: str) -> list[TestId]: return []
    # confidence() removed


@pytest.mark.parametrize("stub_cls,proto", [
    (_DepGraphStub, DepGraphAdapter),
    (_ImportGraphStub, ImportGraphAdapter),
    (_ScipStub, ScipAdapter),
    (_TestInventoryStub, TestInventoryAdapter),
])
def test_runtime_checkable_accepts_complete_stub(stub_cls: type, proto: type) -> None:
    """AC-4: @runtime_checkable conformance check is structural and
    attribute-based; a complete stub need NOT inherit from the Protocol."""
    assert isinstance(stub_cls(), proto)


@pytest.mark.parametrize("stub_cls,proto", [
    (_IncompleteDepGraph, DepGraphAdapter),
    (_IncompleteImportGraph, ImportGraphAdapter),
    (_IncompleteScip, ScipAdapter),
    (_IncompleteTestInventory, TestInventoryAdapter),
])
def test_runtime_checkable_rejects_incomplete_stub(
    stub_cls: type, proto: type
) -> None:
    """AC-5: PEP 544 §runtime_checkable — ``isinstance`` checks attribute
    *presence*, not signatures. A class missing any declared method must
    return False; a class with mistyped signatures will pass at runtime
    and only fail under ``mypy --strict``. The test is parametrized over
    all four Protocols (was DepGraph-only) so the symmetric guarantee
    holds across the adapter surface."""
    assert isinstance(stub_cls(), proto) is False


# -------- Zero-implementation invariant (AC-6) --------

ADAPTER_PROTOCOLS: tuple[type, ...] = (
    DepGraphAdapter,
    ImportGraphAdapter,
    ScipAdapter,
    TestInventoryAdapter,
)
ADAPTER_PROTOCOL_NAMES: frozenset[str] = frozenset(
    proto.__name__ for proto in ADAPTER_PROTOCOLS
)


def test_no_phase2_module_implements_adapter_protocol_dynamic() -> None:
    """AC-6 (dynamic arm). Phase 2 ships Protocols only (02-ADR-0007); Phase 3
    plugins implement. Walk every importable module under ``codegenie`` and
    check that no class trivially-constructible satisfies any Protocol."""
    offenders: list[str] = []
    for mod_info in pkgutil.walk_packages(codegenie.__path__, prefix="codegenie."):
        if mod_info.name.startswith("codegenie.adapters"):
            continue
        try:
            mod = importlib.import_module(mod_info.name)
        except Exception:
            continue
        for cls_name, cls in inspect.getmembers(mod, inspect.isclass):
            if cls.__module__ != mod_info.name:
                continue
            try:
                inst = cls()
            except Exception:
                # Documented limitation: classes that need ctor args are
                # silently skipped here — closed by the static arm below.
                continue
            if any(isinstance(inst, proto) for proto in ADAPTER_PROTOCOLS):
                offenders.append(f"{mod_info.name}.{cls_name}")
    assert offenders == [], (
        f"02-ADR-0007 prohibits adapter implementations in Phase 2; "
        f"found (dynamic): {offenders}"
    )


def test_no_phase2_module_inherits_adapter_protocol_statically() -> None:
    """AC-6 (static arm). Closes the gap the dynamic walk leaves open:
    a class that requires constructor args and inherits from an adapter
    Protocol would pass the dynamic test silently. Static AST scan asserts
    no ``ClassDef`` under ``src/codegenie/`` (except ``adapters/``) lists
    any of the four Protocols in its bases."""
    src_root = Path(codegenie.__file__).parent
    adapters_root = src_root / "adapters"
    offenders: list[str] = []
    for py in src_root.rglob("*.py"):
        if py.is_relative_to(adapters_root):
            continue
        tree = ast.parse(py.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            for base in node.bases:
                base_name: str | None = None
                if isinstance(base, ast.Name):
                    base_name = base.id
                elif isinstance(base, ast.Attribute):
                    base_name = base.attr
                if base_name in ADAPTER_PROTOCOL_NAMES:
                    offenders.append(f"{py.relative_to(src_root)}::{node.name}")
    assert offenders == [], (
        f"02-ADR-0007 prohibits adapter implementations in Phase 2; "
        f"found (static): {offenders}"
    )


# -------- Module purity + forbidden patterns (AC-15, AC-16) --------

FORBIDDEN_IMPORTS: frozenset[str] = frozenset({
    "logging", "structlog", "subprocess", "socket",
    "httpx", "requests", "anthropic", "openai", "langgraph",
})
FORBIDDEN_CODEGENIE_PREFIXES: tuple[str, ...] = (
    "codegenie.parsers",
    "codegenie.probes",
    "codegenie.exec",
    "codegenie.coordinator",
    "codegenie.output",
)


@pytest.mark.parametrize("mod_file", [
    Path(confidence_mod.__file__),
    Path(protocols_mod.__file__),
])
def test_adapter_modules_are_pure_typing(mod_file: Path) -> None:
    """AC-15: ``confidence.py`` and ``protocols.py`` are pure typing
    (arch §Component design #7: "~80 LOC total, stdlib + ``typing`` only";
    final-design §7: "pure types, stdlib + ``typing``").
    Forbidden: I/O, logging, network, sibling Phase-2 modules. Permitted:
    ``__future__``, ``typing``, ``dataclasses``, ``pydantic``."""
    tree = ast.parse(mod_file.read_text())
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    for name in imported:
        assert name not in FORBIDDEN_IMPORTS, (
            f"{mod_file.name} imports forbidden module {name!r}"
        )
        for prefix in FORBIDDEN_CODEGENIE_PREFIXES:
            assert not name.startswith(prefix), (
                f"{mod_file.name} imports forbidden {prefix}-tree module {name!r}"
            )


@pytest.mark.parametrize("mod_file", [
    Path(confidence_mod.__file__),
    Path(protocols_mod.__file__),
])
def test_adapter_modules_have_no_model_construct(mod_file: Path) -> None:
    """AC-16: ``model_construct`` bypasses Pydantic validation;
    `phase-arch-design.md §"Anti-patterns avoided"` row 12 bans it under
    the typed-sum packages. Mirrors S1-01's mutation-#10 closure."""
    tree = ast.parse(mod_file.read_text())
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and node.attr == "model_construct"
        ):
            pytest.fail(
                f"{mod_file.name}:{node.lineno}: model_construct is forbidden "
                f"under src/codegenie/adapters/** (02-arch §Anti-patterns row 12)"
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
- **No `Confidence` import side-effects.** `confidence.py` is pure typing — no logger, no I/O, no third-party deps beyond pydantic. AC-15 enforces this with an AST-import scan; do not bypass it for "convenience." If you find yourself wanting `import structlog` to emit a warning when `Degraded` is constructed, the warning belongs in the *consumer* (the Phase 3 adapter), not the type definition.
- **Zero-implementation walk test (AC-6) has two arms — keep them both.** The dynamic arm (`pkgutil.walk_packages` + trivial-instantiate) catches duck-typed implementations. The static arm (`ast.parse` + base-class scan) catches inheritance-style implementations whose constructors take args. Removing either arm reopens a known hole.
- **`Trusted` has no `reason: str` (AC-11).** Resist the urge to add one for symmetry with `Degraded` / `Unavailable`. `Trusted` carries the absence of degradation; a reason field on it is pattern-soup (final-design Anti-patterns §"Pattern soup" precedent).
- **Phase 2 Protocols may evolve, but only via ADR amendment.** If Phase 3's author finds `consumers(pkg: str)` should be `consumers(pkg: PackageId, *, transitively: bool = False)`, that requires an explicit ADR amendment to 02-ADR-0006/02-ADR-0007 (see `../phase-arch-design.md §"Open questions deferred to implementation"` #1 / Implementation risk #8). The handoff smoke test in S7-04 is the structural insurance.

### Design-pattern framings (added by phase-story-validator 2026-05-15)

- **Deliberate non-extraction of a shared `HasConfidence` Protocol.** All four Protocols declare `def confidence(self) -> AdapterConfidence: ...`. PEP 544 supports `class HasConfidence(Protocol): ...; class DepGraphAdapter(HasConfidence, Protocol): ...`. **Do NOT extract.** Three reasons:
  1. The four declarations are *identical*, not *similar* — Rule of Three rewards extraction when sibling code drifts toward duplication. Four single-line method signatures that are byte-identical isn't duplication; it's parallel statement of a contract. Mutation cost of breaking one without breaking the others is low (the test parametrizes over all four).
  2. Phase 3 may want to evolve adapter signatures independently (e.g., one adapter's `confidence()` taking a `layer: Literal["index","content"]` parameter). A shared base would either freeze that evolution or require ADR-amending the base — both more painful than four parallel declarations.
  3. `phase-arch-design.md §"Design patterns applied"` row 3 prescribes structural subtyping over Abstract Factory; final-design §7 prescribes "four `Protocol` interfaces ... ~80 LOC total, pure types". Both are explicit. A shared base smuggles in the abstract-factory shape the architect rejected.
- **`Occurrence` should use `slots=True` (recommended, not required).** Phase 3's `ScipAdapter` will construct millions of `Occurrence` instances when mmap-walking a SCIP blob. `@dataclass(frozen=True, slots=True)` cuts per-instance memory ~30% (no `__dict__`) and forbids attribute injection. Python 3.11+ supports `slots=True` directly. If you adopt it, extend AC-13 with `assert not hasattr(inst, "__dict__")`. If you defer, leave a one-line `TODO(phase-3): adopt slots=True when SCIP adapter ships` so Phase 3's adapter author finds it.
- **Variant-set extension is ADR-gated, not Open/Closed.** Mirroring S1-01's discipline for `StaleReason`: do NOT introduce a `@register_adapter_confidence_variant` decorator-registry. Adding a fifth `AdapterConfidence` variant requires an explicit ADR amendment to 02-ADR-0007 (and possibly 02-ADR-0006); `assert_never` is the runtime + type-check enforcement. The prevalence of `@register_*` decorators elsewhere in this phase (`@register_probe`, `@register_dep_graph_strategy`, `@register_index_freshness_check`) is for *probe/strategy* extension — those are Open/Closed by intent; sum-type variant sets are deliberately not.
- **`forbidden-patterns` pre-commit extension (S1-11) MUST include `src/codegenie/adapters/**` in its `model_construct` ban path-set.** AC-16 enforces it from the test side; the pre-commit hook in S1-11 enforces it at staging time. Both are required: AC-16 catches in CI, the hook catches before push.
- **The four-Protocol set itself is closed.** Adding a fifth Protocol type (e.g., `DocGraphAdapter` for a hypothetical Phase 8 documentation-graph plugin) requires an ADR amendment to 02-ADR-0007. This is by design — `final-design.md §"Components" #7` and `phase-arch-design.md §"Component design" #7` enumerate exactly four; the typed surface is the contract Phase 3 implements against.
