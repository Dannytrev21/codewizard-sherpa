# Story S1-04 — `VulnProvenanceAdapter` Protocol + `ProvenanceError` hierarchy

**Step:** Step 1 — Scaffold `vuln.provenance` primitive — newtypes, Provenance union, Protocol, errors, SyftSbom reader, fences
**Status:** HARDENED
**Effort:** S
**Depends on:** S1-01 (newtype identifiers); S1-02 + S1-03 (`AdapterConfidence`, `Provenance`)
**ADRs honored:** ADR-0004 (the Protocol + errors live under `src/codegenie/primitives/vuln_provenance/`), ADR-0007 (registry stores classes — the Protocol is a structural duck-typed contract, no ABC inheritance), production ADR-0032 (Adapter Protocol pattern; this story instantiates it for vuln provenance), production ADR-0038 (the Protocol shape is part of the contract)

## Validation notes (`phase-story-validator`, 2026-05-19) — HARDENED

Validator pass against four critics (Coverage / Test-Quality / Consistency / Design-Patterns). Cross-checked against the existing (uncommitted) red tests at `tests/unit/primitives/vuln_provenance/test_adapter_protocol_shape.py` + `test_protocols_module_purity.py`. Edits applied:

- **AC-1** — added explicit sub-clause: every Protocol method parameter (and the return) carries a real type annotation (not just present-by-name); ties the AST scan to type-completeness (T2).
- **AC-3** — added symmetric `_BadAdapterMissingAttribute` stub (mirroring the missing-`confidence` stub) so the `@runtime_checkable` rejection is pinned in both directions (T3).
- **AC-4** — pinned mutual-exclusivity: `AdapterError` is NOT a subclass of `RegistryError` and vice versa (the existing test file enforces this; the AC didn't pin it before) — the typed-error sum-type contract is "two siblings under one base", not a chain (C3, DP4).
- **AC-5** — clarified rewrite of the bare-`Exception` negative test to assert via `excinfo.value` not catch-then-re-raise (T1 — the original test was Rule 9 thin; the existing implementation already uses the clearer form).
- **AC-6** — split into two sub-clauses naming the mypy-strict resolution path explicitly. The story now mandates a `TYPE_CHECKING`-guarded placeholder so `mypy --strict src/codegenie/primitives/vuln_provenance/protocols.py` passes **today** AND the `# TODO(S1-05)` marker tightens when the real `SyftSbom` model lands (C7, CO2).
- **AC-7** — pinned the **ASCII-sorted `__all__`** invariant from the existing `__init__.py` docstring (carried forward from S1-03 validation) — additive growth must preserve sort (C6, CO5).
- **AC-8** — extended module-purity fence to `errors.py` (allowlist: `__future__`, `codegenie.errors`) — symmetric with `protocols.py`. The new error module must not pull in I/O / logging / fs (C4).
- **AC-9** — widened gate from "Phase 3 + Phase 0/1/2 regression suite" to project-wide **`make check` end-to-end** (CO1 — parallel to S1-03 CO1 / S1-02 CO4).
- **AC-10 NEW** — Protocol is structurally a `typing.Protocol`, NOT an `abc.ABC` (ADR-0007). Pinned via `typing.Protocol in VulnProvenanceAdapter.__mro__` AND `abc.ABC not in VulnProvenanceAdapter.__mro__` (CO3, DP2).
- **AC-11 NEW** — `errors.py` follows the **markers-only convention** from `codegenie.errors`: no `__init__`, no `__str__`, no class attributes. AST-walk asserts each of `ProvenanceError`, `RegistryError`, `AdapterError` has only a docstring body (DP5 — mirrors the precedent in `src/codegenie/errors.py:20-27` "Subclasses carry no `__init__`, no `__str__`, no class attributes — they are markers only").
- **Implementer notes** — added: (1) **Hexagonal Port** pattern lineage (DP1, ADR-0032); (2) explicit ABC-inheritance prohibition with rationale (DP2, ADR-0007); (3) the SyftSbom forward-ref + mypy-strict resolution recipe (DP3 — `TYPE_CHECKING` guard or placeholder; the existing test uses `inspect.get_annotations(..., eval_str=False)` to avoid runtime resolution); (4) markers-only-errors convention with file:line pointer to `codegenie.errors` (DP5); (5) `__all__` ASCII-sort invariant from S1-03 (CO5); (6) `RegistryError` structured-message-prefix convention mirroring `DepGraphRegistryError`'s `no_strategy_for_ecosystem: <repr>` precedent for when S2-01 raises it (DP6, CO4); (7) Phase 0–6.5 regression suite via `make check` (CO4 — parallel S1-03 CO3); (8) closed-boundary statement — adding a third sibling error subclass (e.g., a `FactoryError`) is an ADR-0007 amendment, not a free edit (DP2).

Verdict: **HARDENED**. The story's goal is sound and traces to ADR-0007 + production ADR-0032/0038. Pre-edit ACs covered the load-bearing invariants but undershot in three places: the mypy-strict-today claim was unworkable without explicit guidance (AC-6); the Protocol-not-ABC structural constraint was implicit (now AC-10); the errors-as-markers convention was unpinned (now AC-11). No goal rewrite. No scope creep. Every new AC enforces an invariant the existing goal already implied.

## Context

The `@register_provenance_adapter` decorator (S2-01) stores classes typed as `type[VulnProvenanceAdapter]`; `assemble_provenance` (S2-04) calls `adapter.attribute(...)` on instances; every concrete adapter (npm in S3-02, alpine in S4-02, distroless in S4-03) must satisfy the same structural contract. The Protocol is the **port** in Hexagonal Port + Adapter; without it landing in Step 1, every Step 2+ story would either fork a definition or hard-import an ABC. The critic surfaced two non-obvious failures that this story pins:
- **Perf-5: do NOT extend the Protocol with `cost_band` or `applies_when` fields.** Performance-first proposed them; the arch + ADR-0007 explicitly reject them as kernel-contract drift.
- **BP-3: the registry must store classes, not instances** — so the Protocol intentionally does not enumerate `__init__` kwargs (DI happens at dispatch time via the `AdapterFactory` in S2-02).

Errors are a typed hierarchy: `ProvenanceError(CodegenieError)` → `RegistryError`, `AdapterError`. Phase 7 stories raise concrete subtypes; `assemble_provenance` catches `ProvenanceError` (the base) and converts to `Unknown(reason="adapter_error")` — any other exception propagates per Rule 12.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design §3` — verbatim `@runtime_checkable VulnProvenanceAdapter(Protocol)` with `attribute(...) -> Provenance` + `confidence() -> AdapterConfidence`; **"No `cost_band`, no `applies_when`"** is the explicit prohibition.
  - `../phase-arch-design.md §Design patterns applied` row 2 — Hexagonal Port + Adapter (ADR-0032).
  - `../phase-arch-design.md §Anti-patterns avoided` — "Side effects in constructors" (this story's Protocol intentionally does not enumerate `__init__` kwargs).
  - `../phase-arch-design.md §Harness engineering §Error escalation` — the `ProvenanceError`-caught path that becomes `Unknown(reason="adapter_error")`.
- **Phase ADRs:**
  - `../ADRs/0004-vuln-provenance-primitive-home.md` — Consequences clause: `protocols.py` and `errors.py` are module names.
  - `../ADRs/0007-provenance-adapter-registry-stores-classes.md` — names the kernel-contract-drift rejection (no `cost_band` / `applies_when`); names the DI vocabulary closed set (`sbom_reader`, `logger`, `image_manifest_cache`) handled by S2-02's `AdapterFactory`, NOT by this story's Protocol.
- **Production ADRs:**
  - `../../../production/adrs/0032-dep-graph-adapter-protocol.md` — the precedent Adapter-Protocol shape; this story mirrors it for vuln provenance.
  - `../../../production/adrs/0038-vulnerability-provenance-attribution.md` — the contract that names this Protocol.
- **Existing code:**
  - `src/codegenie/errors.py` (or equivalent — read first) — the root `CodegenieError` this story's hierarchy extends.
  - `src/codegenie/probes/dep_graph_strategies/` — Phase 2 / Phase 3 precedent for `@runtime_checkable Protocol` + `@register_dep_graph_strategy` pattern. Mirror the style.
  - `src/codegenie/primitives/vuln_provenance/types.py` (from S1-02 + S1-03) — `Provenance`, `AdapterConfidence` are the Protocol's return types.
  - `src/codegenie/types/identifiers.py` (from S1-01) — `CveId`, `PackageId`, `ImageRef`.
- **External docs:**
  - PEP 544 `typing.Protocol` + `@runtime_checkable` — the Protocol shape this story uses.

## Goal

Define the `VulnProvenanceAdapter` Protocol verbatim from the arch under `src/codegenie/primitives/vuln_provenance/protocols.py` and the typed error hierarchy under `src/codegenie/primitives/vuln_provenance/errors.py` — so every Phase 7 adapter story has a stable contract to satisfy and `assemble_provenance` (S2-04) has a base exception type to catch.

## Acceptance criteria

- [ ] **AC-1 — Protocol shape verbatim, fully annotated.** `src/codegenie/primitives/vuln_provenance/protocols.py` carries:
  ```python
  from typing import Protocol, runtime_checkable

  @runtime_checkable
  class VulnProvenanceAdapter(Protocol):
      def attribute(
          self,
          cve_id: CveId,
          package_id: PackageId,
          image_ref: ImageRef | None,
          sbom: "SyftSbom",
      ) -> Provenance: ...

      def confidence(self) -> AdapterConfidence: ...
  ```
  Note `sbom: "SyftSbom"` is a string forward-reference so S1-05 lands the real model; today the Protocol does not need a concrete import.

  **Sub-clause (annotation completeness).** Every parameter of both methods (`self` excepted) AND the return type carries a non-empty annotation — a stripped-annotation implementation (`def attribute(self, cve_id, package_id, image_ref, sbom):`) would pass `inspect.signature` param-name checks but defeat the Protocol's purpose. AST-walk test (or `inspect.get_annotations`) asserts the annotation set for `attribute` is exactly `{"cve_id", "package_id", "image_ref", "sbom", "return"}` and for `confidence` is exactly `{"return"}`.
- [ ] **AC-2 — NO `cost_band`, NO `applies_when`.** Parametrized AST-walk test: `tests/unit/primitives/vuln_provenance/test_adapter_protocol_shape.py` parses `protocols.py` via `ast`, walks `VulnProvenanceAdapter`'s body, and asserts the set of method names is exactly `{"attribute", "confidence"}` (no fourth method, no extra attribute). Adding either field is a hard CI failure — pins critic Perf-5.
- [ ] **AC-3 — `@runtime_checkable` decorator present, rejection is symmetric.** Test asserts `isinstance(some_obj, VulnProvenanceAdapter)` works at runtime (Protocol must be `@runtime_checkable` to admit duck-type checks in tests). A stub class with both methods passes `isinstance`; a stub **missing `confidence()`** fails; a stub **missing `attribute()`** also fails. The two negative cases together pin the bidirectional structural contract — a method-renamer mutation that drops `attribute` but keeps `confidence` is caught.
- [ ] **AC-4 — Error hierarchy.** `src/codegenie/primitives/vuln_provenance/errors.py` carries:
  ```python
  from codegenie.errors import CodegenieError

  class ProvenanceError(CodegenieError):
      """Base for vulnerability-provenance errors. Caught by assemble_provenance."""

  class RegistryError(ProvenanceError):
      """Adapter registration failed (e.g., duplicate (Layer, Ecosystem) key)."""

  class AdapterError(ProvenanceError):
      """Adapter raised during `attribute()` — caught and converted to Unknown(reason='adapter_error')."""
  ```
  All three are subclasses; `issubclass(RegistryError, ProvenanceError)` and `issubclass(AdapterError, ProvenanceError)` both `True`; both also `issubclass(_, CodegenieError)`.

  **Sub-clause (mutual exclusivity — sum-type-of-errors contract).** `AdapterError` and `RegistryError` are **siblings** under `ProvenanceError`, not in a parent-child relationship: `issubclass(AdapterError, RegistryError)` is `False` AND `issubclass(RegistryError, AdapterError)` is `False`. Pins the typed-error sum-type shape — an executor who refactored one into a subclass of the other would silently change the catch-arm semantics in S2-04.
- [ ] **AC-5 — Errors are catch-shaped.** Test pins the catch idiom S2-04 will use:
  ```python
  with pytest.raises(ProvenanceError):
      raise RegistryError("dup")
  with pytest.raises(ProvenanceError):
      raise AdapterError("kaboom")
  with pytest.raises(AdapterError):
      raise AdapterError("kaboom")
  ```
  A bare `Exception` does NOT pass `pytest.raises(ProvenanceError)` (negative test — confirms `ProvenanceError` is not just `Exception`). The negative test asserts via `excinfo.value` identity rather than catch-then-re-raise (the catch-then-re-raise idiom passes vacuously when both arms behave the same — Rule 9):

  ```python
  with pytest.raises(Exception) as excinfo:
      raise Exception("plain")
  assert not isinstance(excinfo.value, ProvenanceError)
  ```
- [ ] **AC-6 — Protocol forward-reference for `SyftSbom`, mypy-strict-clean today.** Two sub-clauses:

  **(a) Runtime behavior.** The `attribute` signature uses `"SyftSbom"` as a string annotation (S1-05 lands the real model). Today the test pins the **raw string** via `inspect.get_annotations(VulnProvenanceAdapter.attribute, eval_str=False)["sbom"] == "SyftSbom"` — this does NOT attempt resolution. A `# TODO(S1-05)` marker in the test guards the tightening: once S1-05 ships, flip the assertion to `get_type_hints(...)["sbom"] is SyftSbom`.

  **(b) Static-type cleanliness today.** `mypy --strict src/codegenie/primitives/vuln_provenance/protocols.py` must pass **today** with `SyftSbom` undefined at runtime. Resolve via one of two routes (implementer chooses; both ADR-conformant):
  - **Preferred — `TYPE_CHECKING`-guarded placeholder declaration** under `from __future__ import annotations`:
    ```python
    if TYPE_CHECKING:
        class SyftSbom: ...  # placeholder; S1-05 replaces with `from .models import SyftSbom`
    ```
    The placeholder is a *class declaration*, not `Any` (the no-`Any` fence at S1-06 will reject `Any` imports).
  - **Alternative — narrowly-scoped `# type: ignore[name-defined]`** on the `sbom` parameter line only. Adds a lint marker the executor must remove in S1-05.

  Either route MUST pass `make check` today. The story rejects `SyftSbom = Any` (anti-pattern; future fence violation).
- [ ] **AC-7 — `__init__.py` re-exports, ASCII-sorted `__all__`.** `from codegenie.primitives.vuln_provenance import VulnProvenanceAdapter, ProvenanceError, RegistryError, AdapterError` succeeds. The four new names land in `__all__` in **ASCII-sorted order** (invariant from `__init__.py` docstring established by S1-02 / S1-03: "`__all__` is sorted and exact … future stories grow it additively in ASCII order"). The existing S1-03 test `test_types_dunder_all.py` (or its equivalent) is extended — or a sibling test added — to lock the post-S1-04 surface: `AdapterConfidence, AdapterError, AppDirect, AppKind, AppTransitive, AppVendored, BaseImage, BaseKind, Both, DistroPackage, Provenance, ProvenanceError, RegistryError, RuntimeBundled, Unknown, UnknownReason, VulnProvenanceAdapter`. A non-sorted insert is a hard test failure.
- [ ] **AC-8 — Module purity for BOTH new modules.**
  - `tests/unit/primitives/vuln_provenance/test_protocols_module_purity.py` AST-walks `protocols.py` and asserts imports are a subset of `{__future__, typing, codegenie.types.identifiers, codegenie.primitives.vuln_provenance.types}` (no logging, no filesystem, no I/O — the Protocol is pure type-level).
  - `tests/unit/primitives/vuln_provenance/test_errors_module_purity.py` AST-walks `errors.py` and asserts imports are a subset of `{__future__, codegenie.errors}` — the errors module re-uses the root `CodegenieError`; it does NOT pull in `typing`, `logging`, or sibling primitives. Symmetric with `protocols.py`'s fence and with `codegenie.errors` itself (no imports beyond `__future__`).
  - Both fences must reject `<relative-import>` — kernel-tier modules use absolute imports only (mirrors the existing `test_protocols_module_purity.py:52-58` precedent).
- [ ] **AC-9 — Gates (project-wide `make check`).** Project-wide `make check` is green: `make lint`, `make lint-imports`, `make typecheck` (`mypy --strict src/`), `make test`, `make fence`. Phase 0 → Phase 6.5 regression suite green (mirrors the S1-02 / S1-03 widening — narrow subdir gates miss cross-package drift). The `forbidden-patterns` pre-commit hook passes on both new files (no `subprocess.run(..., shell=True)`, no `eval(`, no `pickle.loads`, no bare `assert`).
- [ ] **AC-10 — Protocol, NOT ABC (ADR-0007).** `typing.Protocol in VulnProvenanceAdapter.__mro__` is `True`; `abc.ABC not in VulnProvenanceAdapter.__mro__` is `True`. The choice of `Protocol` over `ABC` is the Hexagonal-Port design seam — adapters in different plugin packages satisfy the contract via structural duck-typing without importing the Protocol (production ADR-0032 lineage). An executor who substitutes `class VulnProvenanceAdapter(ABC):` would pass AC-2's method-set check, pass AC-3's duck-type behavior, but break the design semantic this AC pins.
- [ ] **AC-11 — Markers-only errors convention.** AST-walk on `errors.py` asserts each of `ProvenanceError`, `RegistryError`, `AdapterError` has a body of **exactly one** `ast.Expr` (the docstring) — no `__init__`, no `__str__`, no class attributes. Mirrors the precedent in `src/codegenie/errors.py:20-27` ("Subclasses carry no `__init__`, no `__str__`, no class attributes — they are markers only. Adding behavior is a separate decision."). The structured detail S2-04 wants when catching `AdapterError` lives on `args[0]` (the message string), not on class state.
- [ ] The TDD plan's red test exists, was committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest` all pass on the touched files.

## Implementation outline

1. Create `src/codegenie/primitives/vuln_provenance/errors.py`:
   - Import `CodegenieError` from `codegenie.errors` (verify the existing module path before writing — read the existing root error module).
   - Declare `ProvenanceError(CodegenieError)`, then `RegistryError(ProvenanceError)`, then `AdapterError(ProvenanceError)`.
2. Create `src/codegenie/primitives/vuln_provenance/protocols.py`:
   - Imports: `Protocol`, `runtime_checkable` from `typing`; `CveId`, `PackageId`, `ImageRef` from `codegenie.types.identifiers`; `Provenance`, `AdapterConfidence` from `.types`.
   - `@runtime_checkable class VulnProvenanceAdapter(Protocol)` with exactly two methods.
   - `sbom: "SyftSbom"` as a string forward reference.
3. Extend `src/codegenie/primitives/vuln_provenance/__init__.py`:
   - Re-export `VulnProvenanceAdapter` from `.protocols`.
   - Re-export `ProvenanceError`, `RegistryError`, `AdapterError` from `.errors`.
4. Land tests (red-first).
5. Run `mypy --strict` + `make check`.

## TDD plan — red / green / refactor

### Red — write the failing test first
Test file path: `tests/unit/primitives/vuln_provenance/test_adapter_protocol_shape.py`

```python
from __future__ import annotations

import ast
import inspect
from pathlib import Path
from typing import get_type_hints

import pytest

from codegenie.errors import CodegenieError
from codegenie.primitives.vuln_provenance import (
    AdapterConfidence,
    AdapterError,
    ProvenanceError,
    RegistryError,
    VulnProvenanceAdapter,
)


# --- Protocol method set is exactly {attribute, confidence} (AC-2) ----------

PROTOCOL_FILE = Path("src/codegenie/primitives/vuln_provenance/protocols.py")


def _protocol_method_names() -> set[str]:
    tree = ast.parse(PROTOCOL_FILE.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "VulnProvenanceAdapter":
            return {
                child.name
                for child in node.body
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
    pytest.fail("VulnProvenanceAdapter class not found in protocols.py")


def test_protocol_method_set_is_exact():
    assert _protocol_method_names() == {"attribute", "confidence"}, (
        "VulnProvenanceAdapter must not gain cost_band, applies_when, or any "
        "other method (critic Perf-5)."
    )


# --- @runtime_checkable round-trip (AC-3) -----------------------------------

class _GoodAdapter:
    def attribute(self, cve_id, package_id, image_ref, sbom):
        ...
    def confidence(self):
        ...


class _BadAdapterMissingConfidence:
    def attribute(self, cve_id, package_id, image_ref, sbom):
        ...


def test_runtime_checkable_admits_good_adapter():
    assert isinstance(_GoodAdapter(), VulnProvenanceAdapter)


def test_runtime_checkable_rejects_missing_method():
    assert not isinstance(_BadAdapterMissingConfidence(), VulnProvenanceAdapter)


# --- Error hierarchy (AC-4, AC-5) --------------------------------------------

def test_error_hierarchy_is_subclass_of_codegenie_error():
    assert issubclass(ProvenanceError, CodegenieError)
    assert issubclass(RegistryError, ProvenanceError)
    assert issubclass(AdapterError, ProvenanceError)


def test_provenance_error_catches_subclasses():
    with pytest.raises(ProvenanceError):
        raise RegistryError("dup")
    with pytest.raises(ProvenanceError):
        raise AdapterError("kaboom")


def test_adapter_error_distinct_from_registry_error():
    assert AdapterError is not RegistryError


def test_provenance_error_does_not_catch_plain_exception():
    with pytest.raises(Exception):
        try:
            raise Exception("plain")
        except ProvenanceError:
            pytest.fail("ProvenanceError must not catch plain Exception")
        except Exception:
            raise


# --- Method signature shape (AC-1) ------------------------------------------

def test_attribute_signature():
    sig = inspect.signature(VulnProvenanceAdapter.attribute)
    params = list(sig.parameters.keys())
    # self, cve_id, package_id, image_ref, sbom
    assert params == ["self", "cve_id", "package_id", "image_ref", "sbom"]


def test_confidence_signature():
    sig = inspect.signature(VulnProvenanceAdapter.confidence)
    params = list(sig.parameters.keys())
    assert params == ["self"]


def test_confidence_returns_adapter_confidence():
    hints = get_type_hints(VulnProvenanceAdapter.confidence)
    assert hints.get("return") is AdapterConfidence
```

State why it fails: `ImportError` — `codegenie.primitives.vuln_provenance.protocols`, `codegenie.primitives.vuln_provenance.errors`, and the four names (`VulnProvenanceAdapter`, `ProvenanceError`, `RegistryError`, `AdapterError`) don't exist.

### Green — make it pass
- Create `errors.py` with the three-class hierarchy.
- Create `protocols.py` with the `@runtime_checkable VulnProvenanceAdapter` Protocol — exactly two methods.
- Extend `vuln_provenance/__init__.py` to re-export the four new names.

### Refactor — clean up
- Each error class carries a one-line docstring naming its provenance (registry-time vs adapter-time).
- `VulnProvenanceAdapter` carries a class-level docstring naming ADR-0007 ("Adapters are registered as classes; this Protocol is the duck-typed contract dispatch checks against").
- Confirm no `Any` annotations crept in (S1-06 will plant the AST fence, but this story should not regress it preemptively).

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/primitives/vuln_provenance/protocols.py` | NEW — `VulnProvenanceAdapter` Protocol (exactly 2 methods, `Protocol` not `ABC`). |
| `src/codegenie/primitives/vuln_provenance/errors.py` | NEW — `ProvenanceError` / `RegistryError` / `AdapterError` (markers-only — no `__init__`, no `__str__`). |
| `src/codegenie/primitives/vuln_provenance/__init__.py` | Extend re-exports with the 4 new names; preserve **ASCII-sorted `__all__`** invariant (AC-7). |
| `tests/unit/primitives/vuln_provenance/test_adapter_protocol_shape.py` | NEW — anchors TDD red; AST-walk Protocol method set + Protocol-not-ABC + annotation-completeness + symmetric missing-method rejection + sum-type exclusivity. |
| `tests/unit/primitives/vuln_provenance/test_protocols_module_purity.py` | NEW — module-purity fence on `protocols.py` imports. |
| `tests/unit/primitives/vuln_provenance/test_errors_module_purity.py` | NEW — module-purity fence on `errors.py` imports (AC-8 part 2). |
| `tests/unit/primitives/vuln_provenance/test_types_dunder_all.py` | EXTEND — lock the post-S1-04 ASCII-sorted `__all__` surface (AC-7). |

## Out of scope

- **`AdapterFactory` Protocol + DI vocabulary** — landed by S2-02 (this story's Protocol intentionally does not enumerate `__init__` kwargs; DI is the factory's job).
- **The `_REGISTRY` dict + `@register_provenance_adapter` decorator** — landed by S2-01.
- **Concrete adapter implementations** — landed by S3-02, S4-02, S4-03.
- **`SyftSbom` Pydantic model** — landed by S1-05 (this story uses a string forward reference).
- **Phase 7 LLM-SDK / no-`Any` fences** — landed by S1-06.
- **`assemble_provenance` free function** — landed by S2-04 (this story's `ProvenanceError` is the base class S2-04 catches).

## Notes for the implementer

### Design-pattern lineage (validator-surfaced)

- **Hexagonal Port + Adapter (ADR-0032 / production ADR-0032).** This Protocol IS the **port** in Hexagonal Architecture (Cockburn). Concrete adapters (S3-02 npm, S4-02 alpine, S4-03 distroless) live in plugin packages on the "outside"; the kernel sees only the Protocol. The choice of `typing.Protocol` over `abc.ABC` is load-bearing — adapters do not need to import the Protocol to satisfy it (structural duck typing). This is what makes Phase 7's plugin tree extension-by-addition (zero edits to the kernel when a new ecosystem ships).
- **`typing.Protocol`, never `abc.ABC` (ADR-0007).** Pinned by AC-10. Substituting `ABC` would compile, would pass the method-set AST check, would pass the `isinstance` behavior test (with `@runtime_checkable`), but would break the structural-typing contract — plugin adapters in another package would need to inherit, introducing the import-coupling the design rejects. ADR-0007 mandates `Protocol`.
- **Markers-only errors (`codegenie.errors` precedent).** AC-11 pins this structurally. Look at `src/codegenie/errors.py:20-27` — the docstring is the convention: "Subclasses carry no `__init__`, no `__str__`, no class attributes — they are markers only. Adding behavior is a separate decision (Rule 2, Rule 3)." If S2-04's catch site needs structured detail, it lives on `args[0]` as a string prefix (e.g., S2-01's eventual `RegistryError("duplicate adapter for (Layer.APP, Ecosystem.NPM)")`), not as class state.
- **Typed-error sum-type (closed boundary).** `RegistryError` and `AdapterError` are **two siblings** under `ProvenanceError`. AC-4's mutual-exclusivity sub-clause pins this — neither is a subclass of the other. Adding a third sibling (e.g., `FactoryError` from S2-02) is an ADR-0007 amendment, not a free edit; the catch-arm count in S2-04 depends on the sibling set being intentional.
- **Future-message-prefix convention for `RegistryError`.** When S2-01 raises `RegistryError`, the message will carry a structured prefix mirroring `DepGraphRegistryError`'s `no_strategy_for_ecosystem: <repr>` precedent — e.g., `duplicate_adapter_for_key: (Layer.APP, Ecosystem.NPM)`. This story ships the class only; S2-01 wires the message. Note the convention now so S2-01 mirrors `src/codegenie/depgraph/registry.py:178` shape.

### Operational notes

- **The Protocol has EXACTLY two methods.** Not three, not four. The arch and ADR-0007 are unambiguous: `attribute` and `confidence`. The AC-2 AST-walk test is the structural guard against drift. If a later story tries to add `cost_band()` or `applies_when()` to the Protocol, the AC-2 test fails — that's the design. The fix is to push the concern into the `AdapterFactory` (S2-02) or the registry policy (`_ADAPTER_DISPATCH_ORDER` in S2-03), not the kernel Protocol.
- **`@runtime_checkable` is load-bearing.** Without it, `isinstance(adapter, VulnProvenanceAdapter)` raises `TypeError`. The arch deliberately admits the duck-type check (tests use it; the registry decorator might use it). With `@runtime_checkable`, Python checks only that the method *names* match — not their signatures. ADR-0007 acknowledges this: signature mismatches surface at call time as typed errors, not at registration. `mypy --strict` is the gate for the signatures.
- **`CodegenieError` is the root.** Verify the existing module path before writing the import — the repo has a single root error class somewhere under `src/codegenie/`. Read first; do not invent a new root.
- **`AdapterError` is what `assemble_provenance` catches → converts to `Unknown(reason="adapter_error")`.** S2-04 will write the catch. Today, this story only ships the class; S2-04 wires the catch arm. Document this in the class docstring.
- **`RegistryError` is raised at decoration time (S2-01).** The duplicate-`(layer, ecosystem)` key case. This story ships the class; S2-01 raises it.
- **String forward reference `"SyftSbom"` + mypy-strict recipe.** S1-05 lands the real Pydantic model. Until then, AC-6(b) requires one of two routes to keep `mypy --strict` clean today:
  1. **Preferred** — `from __future__ import annotations` PLUS a `if TYPE_CHECKING: class SyftSbom: ...` placeholder declaration. The placeholder is a class (not `Any`); S1-05 replaces it with `from codegenie.primitives.vuln_provenance.models import SyftSbom`.
  2. **Alternative** — bare `from __future__ import annotations` + a narrowly-scoped `# type: ignore[name-defined]` on the `sbom` parameter line, removed in S1-05.
  Do NOT use `SyftSbom = Any` — Phase 7's S1-06 fence forbids `Any`. The existing red test at `tests/unit/primitives/vuln_provenance/test_adapter_protocol_shape.py:151-166` uses `inspect.get_annotations(..., eval_str=False)` so the runtime test does not require resolution — but mypy strict in CI WILL try to resolve, hence the placeholder.
- **No `__init__` kwargs in the Protocol.** ADR-0007 + the arch §Anti-patterns are explicit: the Protocol does not enumerate constructor parameters. DI happens at dispatch time via S2-02's `AdapterFactory`. Adapters declare `__init__` parameters individually (as plain method args); the factory inspects them and supplies the well-known DI vocabulary (`sbom_reader`, `logger`, `image_manifest_cache`).
- **Match Phase 2 / Phase 3 Protocol style.** Read `src/codegenie/probes/dep_graph_strategies/` (or the equivalent `@register_dep_graph_strategy` Protocol) before writing — same `@runtime_checkable`, same `class X(Protocol)` shape, same one-line method docstrings. Inconsistency is a Rule 11 violation.
- **Forward to S2-01.** S2-01's `_REGISTRY: Final[dict[ProvenanceAdapterId, type[VulnProvenanceAdapter]]] = {}` imports this story's `VulnProvenanceAdapter`. If S2-01 starts before this story is green, the registry's type annotation breaks. Land S1-04 first.
- **`__all__` ASCII-sort invariant.** The existing `__init__.py` docstring (lines 12-14) carries the load-bearing claim: "`__all__` is sorted and exact … future stories grow it additively in ASCII order." S1-03 validation pinned this for the union surface; S1-04 maintains it. Add `AdapterError, ProvenanceError, RegistryError, VulnProvenanceAdapter` into the existing list and re-sort — do not append. `test_types_dunder_all.py` enforces it.
- **`make check` is the gate, not subdir mypy.** AC-9 explicitly widens to project-wide `make check`. The S1-02 / S1-03 validation lineage established this — narrow `mypy --strict src/codegenie/primitives/vuln_provenance/` would miss cross-package drift (e.g., a downstream module importing `RegistryError` and discovering it's not in `__all__`). Run `make check` end-to-end before declaring AC-9 green.
