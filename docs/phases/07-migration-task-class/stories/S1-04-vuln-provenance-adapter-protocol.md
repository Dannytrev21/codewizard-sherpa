# Story S1-04 — `VulnProvenanceAdapter` Protocol + `ProvenanceError` hierarchy

**Step:** Step 1 — Scaffold `vuln.provenance` primitive — newtypes, Provenance union, Protocol, errors, SyftSbom reader, fences
**Status:** Ready
**Effort:** S
**Depends on:** S1-01
**ADRs honored:** ADR-0004 (the Protocol + errors live under `src/codegenie/primitives/vuln_provenance/`), ADR-0007 (registry stores classes — the Protocol is a structural duck-typed contract, no ABC inheritance), production ADR-0032 (Adapter Protocol pattern; this story instantiates it for vuln provenance), production ADR-0038 (the Protocol shape is part of the contract)

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

- [ ] **AC-1 — Protocol shape verbatim.** `src/codegenie/primitives/vuln_provenance/protocols.py` carries:
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
- [ ] **AC-2 — NO `cost_band`, NO `applies_when`.** Parametrized AST-walk test: `tests/unit/primitives/vuln_provenance/test_adapter_protocol_shape.py` parses `protocols.py` via `ast`, walks `VulnProvenanceAdapter`'s body, and asserts the set of method names is exactly `{"attribute", "confidence"}` (no fourth method, no extra attribute). Adding either field is a hard CI failure — pins critic Perf-5.
- [ ] **AC-3 — `@runtime_checkable` decorator present.** Test asserts `isinstance(some_obj, VulnProvenanceAdapter)` works at runtime (Protocol must be `@runtime_checkable` to admit duck-type checks in tests). A stub class with both methods passes `isinstance`; a stub missing `confidence()` fails.
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
- [ ] **AC-5 — Errors are catch-shaped.** Test pins the catch idiom S2-04 will use:
  ```python
  with pytest.raises(ProvenanceError):
      raise RegistryError("dup")
  with pytest.raises(ProvenanceError):
      raise AdapterError("kaboom")
  with pytest.raises(AdapterError):
      raise AdapterError("kaboom")
  ```
  A bare `Exception` does NOT pass `pytest.raises(ProvenanceError)` (negative test — confirms `ProvenanceError` is not just `Exception`).
- [ ] **AC-6 — Protocol forward-reference for `SyftSbom`.** The `attribute` signature uses `"SyftSbom"` as a string annotation (S1-05 lands the real model). After S1-05 lands, the forward reference resolves; mypy `--strict` must be clean **today** with the forward reference and **tomorrow** with the resolved import. Test asserts `typing.get_type_hints(VulnProvenanceAdapter.attribute, include_extras=True)` (with a fixture that pre-imports `SyftSbom` once it exists) eventually returns the resolved type. Today: a `# TODO(S1-05)` marker in the test guards the eventual tightening.
- [ ] **AC-7 — `__init__.py` re-exports.** `from codegenie.primitives.vuln_provenance import VulnProvenanceAdapter, ProvenanceError, RegistryError, AdapterError` succeeds.
- [ ] **AC-8 — Module purity.** `tests/unit/primitives/vuln_provenance/test_protocols_module_purity.py` AST-walks `protocols.py` and asserts imports are a subset of `{__future__, typing, codegenie.types.identifiers, codegenie.primitives.vuln_provenance.types}` (no logging, no filesystem, no I/O — the Protocol is pure type-level).
- [ ] **AC-9 — Gates.** `mypy --strict src/codegenie/primitives/vuln_provenance/` clean; `ruff check`, `ruff format --check` clean; `make lint-imports` green; Phase 3 + Phase 0/1/2 regression suite green.
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
| `src/codegenie/primitives/vuln_provenance/protocols.py` | NEW — `VulnProvenanceAdapter` Protocol (exactly 2 methods). |
| `src/codegenie/primitives/vuln_provenance/errors.py` | NEW — `ProvenanceError` / `RegistryError` / `AdapterError`. |
| `src/codegenie/primitives/vuln_provenance/__init__.py` | Extend re-exports with the 4 new names. |
| `tests/unit/primitives/vuln_provenance/test_adapter_protocol_shape.py` | NEW — anchors TDD red; AST-walk the Protocol method set. |
| `tests/unit/primitives/vuln_provenance/test_protocols_module_purity.py` | NEW — module-purity fence on `protocols.py` imports. |

## Out of scope

- **`AdapterFactory` Protocol + DI vocabulary** — landed by S2-02 (this story's Protocol intentionally does not enumerate `__init__` kwargs; DI is the factory's job).
- **The `_REGISTRY` dict + `@register_provenance_adapter` decorator** — landed by S2-01.
- **Concrete adapter implementations** — landed by S3-02, S4-02, S4-03.
- **`SyftSbom` Pydantic model** — landed by S1-05 (this story uses a string forward reference).
- **Phase 7 LLM-SDK / no-`Any` fences** — landed by S1-06.
- **`assemble_provenance` free function** — landed by S2-04 (this story's `ProvenanceError` is the base class S2-04 catches).

## Notes for the implementer

- **The Protocol has EXACTLY two methods.** Not three, not four. The arch and ADR-0007 are unambiguous: `attribute` and `confidence`. The AC-2 AST-walk test is the structural guard against drift. If a later story tries to add `cost_band()` or `applies_when()` to the Protocol, the AC-2 test fails — that's the design. The fix is to push the concern into the `AdapterFactory` (S2-02) or the registry policy (`_ADAPTER_DISPATCH_ORDER` in S2-03), not the kernel Protocol.
- **`@runtime_checkable` is load-bearing.** Without it, `isinstance(adapter, VulnProvenanceAdapter)` raises `TypeError`. The arch deliberately admits the duck-type check (tests use it; the registry decorator might use it). With `@runtime_checkable`, Python checks only that the method *names* match — not their signatures. ADR-0007 acknowledges this: signature mismatches surface at call time as typed errors, not at registration. `mypy --strict` is the gate for the signatures.
- **`CodegenieError` is the root.** Verify the existing module path before writing the import — the repo has a single root error class somewhere under `src/codegenie/`. Read first; do not invent a new root.
- **`AdapterError` is what `assemble_provenance` catches → converts to `Unknown(reason="adapter_error")`.** S2-04 will write the catch. Today, this story only ships the class; S2-04 wires the catch arm. Document this in the class docstring.
- **`RegistryError` is raised at decoration time (S2-01).** The duplicate-`(layer, ecosystem)` key case. This story ships the class; S2-01 raises it.
- **String forward reference `"SyftSbom"`.** S1-05 lands the real Pydantic model. Until then, mypy --strict needs `from __future__ import annotations` at the top of `protocols.py` and the forward reference will be a string. Once S1-05 ships, the string becomes resolvable at runtime via `get_type_hints` (which is what AC-6's "tomorrow" path tests). Do not import `SyftSbom` from a not-yet-existing module today — that would force this story to depend on S1-05.
- **No `__init__` kwargs in the Protocol.** ADR-0007 + the arch §Anti-patterns are explicit: the Protocol does not enumerate constructor parameters. DI happens at dispatch time via S2-02's `AdapterFactory`. Adapters declare `__init__` parameters individually (as plain method args); the factory inspects them and supplies the well-known DI vocabulary (`sbom_reader`, `logger`, `image_manifest_cache`).
- **Match Phase 2 / Phase 3 Protocol style.** Read `src/codegenie/probes/dep_graph_strategies/` (or the equivalent `@register_dep_graph_strategy` Protocol) before writing — same `@runtime_checkable`, same `class X(Protocol)` shape, same one-line method docstrings. Inconsistency is a Rule 11 violation.
- **Forward to S2-01.** S2-01's `_REGISTRY: Final[dict[ProvenanceAdapterId, type[VulnProvenanceAdapter]]] = {}` imports this story's `VulnProvenanceAdapter`. If S2-01 starts before this story is green, the registry's type annotation breaks. Land S1-04 first.
