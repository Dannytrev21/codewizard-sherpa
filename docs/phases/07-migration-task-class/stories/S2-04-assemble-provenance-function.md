# Story S2-04 — `assemble_provenance(...)` free function + `match`/`assert_never` composition

**Step:** Step 2 — Registry kernel, `_ADAPTER_DISPATCH_ORDER`, `assemble_provenance` free function
**Status:** Done
**Completed:** 2026-05-19
**Attempts:** 1
**Evidence:**
- Files: `src/codegenie/primitives/vuln_provenance/assembly.py`, `src/codegenie/primitives/vuln_provenance/__init__.py`, `src/codegenie/primitives/vuln_provenance/protocols.py`, `tests/unit/primitives/vuln_provenance/test_assembly.py` (new), `tests/unit/primitives/vuln_provenance/test_assemble_match_exhaustive.py` (new), `tests/unit/primitives/vuln_provenance/test_types_dunder_all.py`, `tests/unit/primitives/vuln_provenance/test_protocols_module_purity.py`
- Tests: `test_assembly.py` (14) + `test_assemble_match_exhaustive.py` (2) — one+ per AC-1..AC-14; AC-15 via gates
- Gates: `ruff check`/`ruff format` clean, `mypy --strict src/` clean (194 files), `lint-imports` 5/5 KEPT, full suite 5585 passed (3 reported failures are the `.venv/bin`-PATH local-env issue — pass under CI)
- Attempt log: `_attempts/S2-04-assemble-provenance-function.md`
- Commit: (pending human merge)
**Effort:** M
**Depends on:** S2-02 (`AdapterFactory` Protocol + `DefaultAdapterFactory`), S2-03 (`_ADAPTER_DISPATCH_ORDER`, `iter_adapters_for_layer_set`); transitively: S1-03 (`Provenance` seven-variant discriminated union + nested `Both` guard), S1-04 (`VulnProvenanceAdapter` Protocol + `ProvenanceError`)
**ADRs honored:** Phase 7 ADR-0001 (no `MultiPluginCoordinator` — `Both` becomes evidence, not coordination), Phase 7 ADR-0004 (vuln.provenance primitive home — `assemble_provenance` lives there), Phase 7 ADR-0006 (walks `_ADAPTER_DISPATCH_ORDER`; intra-layer `Ecosystem`-sorted), Phase 7 ADR-0007 (constructs via `AdapterFactory`; registry stores classes), production ADR-0038 (vulnerability provenance attribution — this function IS the deferred-question answer).

## Context

`assemble_provenance` is the **header function** of the entire `vuln.provenance` primitive — every Phase 7 consumer (the Phase 3 plugin's npm adapter via S3-03, the Phase 7 plugin's alpine/distroless adapters via S4-02/S4-03, the TCCM `derived_queries:` band's `compute: vuln.provenance` resolution via S8-02/S8-03, the Step 11 `Both` coordination emission) flows through this one ≤80-LOC function. Its composition rules — collect the first non-`Unknown` per layer, then `match (app_result, base_result) → Unknown | app | base | Both` — are the entire contract of "what does `vuln.provenance` mean for this CVE?"

The function is intentionally **pure** (no global state mutation), **deterministic** (per S2-03's `_ADAPTER_DISPATCH_ORDER` + `Ecosystem`-sorted intra-layer), and **typed** at every seam (`match`/`assert_never` proves exhaustiveness per S1-03's seven-variant union). Per Rule 12 (fail loud): `ProvenanceError` from an adapter is caught and folded into `Unknown(reason="adapter_error")`; all other exceptions propagate.

**Scope reminder.** S2-04 ships ONLY the `assemble_provenance` function + unit tests covering all four `match` arms + adapter-error handling. S2-05's Hypothesis property tests (50-permutation invariance + idempotence + `Both` no-recursion) come next. Integration through real plugins lives in S3-01 (contract test) and S4-02 (real Phase 7 plugin tree).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design §6` — full public interface verbatim; the `match (app_result, base_result)` block; the ≤80-LOC budget; performance envelope (p99 ≤ 50 ms uncached); failure behavior (`ProvenanceError` → `Unknown`; all other exceptions propagate per Rule 12); optional `adapter_factory` for test isolation.
  - `../phase-arch-design.md §Component design §2` — `Provenance` seven-variant union (S1-03). `assemble_provenance` returns this type.
  - `../phase-arch-design.md §Scenarios §A/B/C/D` — the four `match` arms map directly to scenarios A (app-only) / B (base-only) / C (`Both`) / D (`Unknown`).
  - `../phase-arch-design.md §Edge cases` — what each `Unknown(reason=...)` value means.
  - `../phase-arch-design.md §Harness engineering §Determinism vs probabilism` — pure-function, no global state.
- **Phase ADRs:**
  - `../ADRs/0006-adapter-dispatch-explicit-final-tuple.md §Consequences` — `assemble_provenance` walks the tuple; uses `match`/`assert_never` (critic BP-4 closure: no `if r.kind in {...}` string-set comparisons).
  - `../ADRs/0007-provenance-adapter-registry-stores-classes.md §Consequences` — `assemble_provenance(...)` constructs via `adapter_factory`; default factory inspects `cls.__init__`.
  - `../ADRs/0001-no-multi-plugin-coordinator-in-phase-7.md` — `Both` is a typed `Provenance` variant emitted by this function. NO coordination class consumes it within Phase 7; S11 emits a `RequiresMultiPluginCoordination` event when the orchestrator receives `Both` from this function.
  - `../ADRs/0004-vuln-provenance-primitive-home.md` — primitive home; this function lives in `src/codegenie/primitives/vuln_provenance/assembly.py`.
- **Source design:** `../final-design.md §Synthesis ledger row 13 (score 15/15)` + `§Synthesis ledger departure #1` (dispatch as data) + `§Component design §6`.
- **Existing code (precedent to mirror):**
  - `src/codegenie/indices/freshness.py::dispatch_all` (Phase 2 S1-02) — closest precedent for a "walk registry per ADR, fold into a typed result" header function; same shape S2-04 produces.
  - `src/codegenie/types/identifiers.py` — `CveId`, `PackageId`, `ImageRef`, `ProvenanceAdapterId` from S1-01.
  - `src/codegenie/primitives/vuln_provenance/types.py` (S1-03) — `Provenance`, `AppDirect`, `AppTransitive`, `AppVendored`, `BaseImage`, `RuntimeBundled`, `Both`, `Unknown`, and the `AppKind` / `BaseKind` typed unions used inside `Both`.
- **Sibling validation framings:**
  - `docs/phases/02-context-gather-layers-b-g/stories/_validation/S1-02-freshness-check-registry.md` — established conventions for "header function dispatches over a typed registry" stories.

## Goal

Ship `assemble_provenance(...)` inside `src/codegenie/primitives/vuln_provenance/assembly.py` with the signature, ≤80-LOC budget, four-arm `match` composition, and adapter-error handling pinned by ADR-0006 + ADR-0007. Plus the `provenance(...)` thin-wrapper callable that TCCM `derived_queries:` band (S8) resolves `compute: vuln.provenance` to.

## Acceptance criteria

- [x] **AC-1 — Function signature exact.** `assemble_provenance(cve_id: CveId, package_id: PackageId, image_ref: ImageRef | None, sbom: SyftSbom, *, registry: Mapping[ProvenanceAdapterId, type[VulnProvenanceAdapter]] | None = None, adapter_factory: AdapterFactory | None = None) -> Provenance`. Positional: `cve_id`, `package_id`, `image_ref`, `sbom`. Keyword-only: `registry`, `adapter_factory`. Test asserts the `inspect.signature` matches exactly (parameter names + positional-vs-keyword-only kinds + defaults).
- [x] **AC-2 — `(None, None)` arm → `Unknown(reason="no_adapter_resolved")`.** Registry is empty (no adapters registered). `assemble_provenance(...)` returns `Unknown(reason="no_adapter_resolved")` (per arch §6 line 727). Test asserts return type identity AND `result.reason == "no_adapter_resolved"`.
- [x] **AC-3 — `(app, None)` arm → returns `app` unchanged.** Register one APP adapter returning `AppDirect(...)`; no BASE_IMAGE adapter. Result is the literal `AppDirect` instance (identity equality via `is` or value equality with all fields populated). Test asserts `isinstance(result, AppDirect) AND result.cve_id == cve_id`.
- [x] **AC-4 — `(None, base)` arm → returns `base` unchanged.** Register one BASE_IMAGE adapter returning `BaseImage(...)`; no APP adapter. Result is the literal `BaseImage` instance. Test asserts `isinstance(result, BaseImage) AND result.image_digest == ...`.
- [x] **AC-5 — `(app, base)` arm → `Both(app_record=app, base_record=base)`.** Register one APP returning `AppTransitive(...)` AND one BASE_IMAGE returning `BaseImage(...)`. Result is `Both(app_record=<AppTransitive>, base_record=<BaseImage>)`. Test asserts `isinstance(result, Both) AND result.app_record is <the AppTransitive instance> AND result.base_record is <the BaseImage instance>`. **The nested `Both` guard (S1-03) MUST NOT trigger** — `app_record` is `AppKind`, `base_record` is `BaseKind`, neither is `Both`. (S2-05's property test pins this end-to-end.)
- [x] **AC-6 — First non-`Unknown` per layer wins.** Register TWO APP adapters in the layer (different `Ecosystem`s): the FIRST in Ecosystem-sort order (per S2-03) returns `Unknown(reason="...")`; the SECOND returns `AppDirect(...)`. Result is `AppDirect` (the FIRST non-`Unknown`). Then reverse: FIRST returns `AppDirect`, SECOND returns `AppVendored`. Result is `AppDirect` — the FIRST in Ecosystem-sort order, not the SECOND.
- [x] **AC-7 — `ProvenanceError` → `Unknown(reason="adapter_error")`.** Register an APP adapter whose `attribute(...)` raises a `ProvenanceError` subclass (`AdapterError("kaboom")`). Result is `Unknown(reason="adapter_error")` (per arch §6 line 738 + ADR-0007). Test asserts `isinstance(result, Unknown) AND result.reason == "adapter_error"`. Adapter-error details MAY be in a structured `details: dict[str, str]` field on `Unknown` (if S1-03 ships that field); if not, the `reason` alone suffices.
- [x] **AC-8 — Non-`ProvenanceError` exceptions propagate (Rule 12).** Register an APP adapter raising `RuntimeError("bug")`. `assemble_provenance(...)` MUST propagate `RuntimeError` — NOT catch it. Test asserts `pytest.raises(RuntimeError, match="bug")`. (This is the load-bearing Rule 12 — "fail loud" — discipline.)
- [x] **AC-9 — `match`/`assert_never` exhaustiveness.** The `match (app_result, base_result)` block has exactly four cases — `(None, None)`, `(app, None)`, `(None, base)`, `(app, base)` — followed by `case _: assert_never(...)` so `mypy --strict` proves exhaustiveness. AST-walk test: `tests/unit/primitives/vuln_provenance/test_assemble_match_exhaustive.py` AST-parses `assembly.py`, finds the `match` statement, asserts it has exactly four `case` arms plus the `assert_never` guard.
- [x] **AC-10 — `registry=None` defaults to `_REGISTRY`.** Passing no `registry` kwarg uses `codegenie.primitives.vuln_provenance.registry._REGISTRY`. Test registers an adapter via `@register_provenance_adapter` (mutates `_REGISTRY`); calls `assemble_provenance(..., registry=None)`; asserts the adapter ran.
- [x] **AC-11 — `adapter_factory=None` defaults to `default_adapter_factory`.** Test passes no `adapter_factory` kwarg; the adapter is constructed via `default_adapter_factory`. For a no-kwarg adapter, this means `cls()` is called once during dispatch. Test asserts the adapter's `__init__` ran exactly once (instrument via class-level counter).
- [x] **AC-12 — Function body ≤ 80 LOC.** Test asserts the LOC count of `assemble_provenance` body (excluding docstring + blank lines) is ≤ 80. Use `ast.parse` + count source lines of the function node. Locks the discipline that arch §6 names ("≤ 80 LOC total").
- [x] **AC-13 — `provenance(...)` thin wrapper exported.** `src/codegenie/primitives/vuln_provenance/__init__.py` exports a top-level `provenance` callable that delegates to `assemble_provenance` with identical signature. Per `High-level-impl.md §Step 2` last bullet — TCCM `derived_queries:` `compute: vuln.provenance` (S8-02) resolves to this callable. Test imports `from codegenie.primitives.vuln_provenance import provenance` and asserts `provenance is assemble_provenance` OR `inspect.signature(provenance) == inspect.signature(assemble_provenance)`.
- [x] **AC-14 — TDD red test exists, committed, green.** `tests/unit/primitives/vuln_provenance/test_assembly.py::test_both_app_and_base_compose_into_both_variant` was the first failing test; impl makes it green.
- [x] **AC-15 — Lint / type clean.** `ruff check`, `ruff format --check`, `mypy --strict` clean on `src/codegenie/primitives/vuln_provenance/assembly.py` (now with `assemble_provenance` body) + the test modules. `make lint-imports` green.

## Implementation outline

1. Extend `src/codegenie/primitives/vuln_provenance/assembly.py` (the module shipped by S2-03):
   - Import: `inspect`, `typing.Final`, `typing.assert_never`, `typing.Mapping`, `collections.abc.Iterator`; `from .registry import Layer, Ecosystem, ProvenanceAdapterId, _REGISTRY`; `from .factory import AdapterFactory, default_adapter_factory`; `from .types import Provenance, AppKind, BaseKind, Both, Unknown` (and the seven variants for typing); `from .errors import ProvenanceError`.
   - The `_ADAPTER_DISPATCH_ORDER` + `iter_adapters_for_layer_set` already live here (S2-03).
   - Add the function:
     ```python
     def assemble_provenance(
         cve_id: CveId,
         package_id: PackageId,
         image_ref: ImageRef | None,
         sbom: SyftSbom,
         *,
         registry: Mapping[ProvenanceAdapterId, type[VulnProvenanceAdapter]] | None = None,
         adapter_factory: AdapterFactory | None = None,
     ) -> Provenance:
         reg = registry if registry is not None else _REGISTRY
         factory = adapter_factory if adapter_factory is not None else default_adapter_factory

         app_result: AppKind | None = None
         base_result: BaseKind | None = None

         for layer_set in _ADAPTER_DISPATCH_ORDER:
             for _key, cls in iter_adapters_for_layer_set(layer_set, reg):
                 try:
                     adapter = factory(cls)
                     result = adapter.attribute(cve_id, package_id, image_ref, sbom)
                 except ProvenanceError:
                     # Per ADR-0007 + arch §6: fold adapter errors into Unknown.
                     # The Unknown returned here is per-adapter, not the assembly's final answer;
                     # it's discarded if a later adapter in this layer resolves a real result.
                     continue
                 # Skip Unknown — keep walking layer's adapters.
                 if isinstance(result, Unknown):
                     continue
                 # First non-Unknown in this layer wins. Stash to the right slot.
                 if layer_set == (Layer.APP,):
                     if app_result is None:
                         app_result = result  # type: AppKind by construction
                     break  # done with this layer
                 elif layer_set == (Layer.BASE_IMAGE,):
                     if base_result is None:
                         base_result = result  # type: BaseKind by construction
                     break
                 # RUNTIME reserved slot — Phase 7 ships no runtime adapter; ignore.
                 break

         match (app_result, base_result):
             case (None, None):
                 return Unknown(reason="no_adapter_resolved")
             case (app, None):
                 return app
             case (None, base):
                 return base
             case (app, base):
                 return Both(app_record=app, base_record=base)
             case _:
                 assert_never((app_result, base_result))
     ```
   - The `continue` after `ProvenanceError` handles AC-7 — but the function's final return on `(None, None)` is `Unknown(reason="no_adapter_resolved")`, not `"adapter_error"`. To honor AC-7's stricter "ANY adapter error in the assembly path becomes the final answer when no real result resolves" reading, track a `saw_adapter_error: bool` flag set on `ProvenanceError`; the `(None, None)` arm returns `Unknown(reason="adapter_error")` when the flag is set, `"no_adapter_resolved"` otherwise. Confirm against arch §6's wording — arch says "Catches `ProvenanceError` → converts to `Unknown(reason="adapter_error")`", which suggests the adapter-error reason propagates to the final result when no real result resolves. Track the flag.
2. Add the `provenance` re-export to `__init__.py`:
   ```python
   from .assembly import assemble_provenance as provenance
   from .assembly import assemble_provenance
   ```
3. Write the red test first; iterate.

## TDD plan — red / green / refactor

### Red

Test file path: `tests/unit/primitives/vuln_provenance/test_assembly.py`

```python
from __future__ import annotations

from codegenie.primitives.vuln_provenance import assemble_provenance
from codegenie.primitives.vuln_provenance.registry import (
    Ecosystem,
    Layer,
    register_provenance_adapter,
)
from codegenie.primitives.vuln_provenance.types import (
    AppDirect,
    BaseImage,
    Both,
)
# CveId, PackageId, ImageRef, ImageDigest, LayerDigest, DockerStageName, DistroPackage
# are smart-constructed via S1-01 / S1-02 — wire test fixtures via the smart constructors.


def test_both_app_and_base_compose_into_both_variant() -> None:
    """ADR-0006 + ADR-0001: when one APP adapter and one BASE_IMAGE adapter both
    return non-Unknown, the assembly composes Both(app_record, base_record).
    Both becomes evidence (Step 11 emits RequiresMultiPluginCoordination)."""

    cve_id = CveId.parse_or_raise("CVE-2025-12345")
    package_id = PackageId.parse_or_raise("pkg:npm/lodash@4.17.21")
    image_ref = ImageRef.parse_or_raise("docker.io/example/app:1.2.3")
    sbom = _empty_syft_sbom()  # fixture from S1-05

    expected_app = AppDirect(cve_id=cve_id, package_id=package_id, chain_length=1)
    expected_base = BaseImage(
        cve_id=cve_id,
        image_digest=ImageDigest.parse_or_raise("sha256:" + "a" * 64),
        layer_digest=LayerDigest.parse_or_raise("sha256:" + "b" * 64),
        distro_pkg=DistroPackage(distro="alpine", name="openssl", version="3.0.0"),
        stage=DockerStageName.parse_or_raise("runtime"),
    )

    @register_provenance_adapter(layer=Layer.APP, ecosystem=Ecosystem.NPM)
    class _AppAdapter:
        def attribute(self, c, p, i, s): return expected_app  # type: ignore[no-untyped-def]
        def confidence(self): ...                              # type: ignore[no-untyped-def]

    @register_provenance_adapter(layer=Layer.BASE_IMAGE, ecosystem=Ecosystem.APK)
    class _BaseAdapter:
        def attribute(self, c, p, i, s): return expected_base  # type: ignore[no-untyped-def]
        def confidence(self): ...                              # type: ignore[no-untyped-def]

    result = assemble_provenance(cve_id, package_id, image_ref, sbom)
    assert isinstance(result, Both)
    assert result.app_record is expected_app
    assert result.base_record is expected_base
```

Why it fails: `assemble_provenance` doesn't exist as a callable yet — `ImportError`.

### Green — minimal pass

Implement per the outline. Wire the `provenance` re-export. Watch the red test pass. Then:

### Required follow-on tests (mutation-resistant; one per AC)

```python
def test_empty_registry_returns_unknown_no_adapter_resolved() -> None:
    """AC-2 — (None, None) arm."""
    cve_id = CveId.parse_or_raise("CVE-2025-00001")
    package_id = PackageId.parse_or_raise("pkg:npm/none@1.0.0")
    sbom = _empty_syft_sbom()
    result = assemble_provenance(cve_id, package_id, None, sbom)
    assert isinstance(result, Unknown)
    assert result.reason == "no_adapter_resolved"


def test_app_only_returns_app_unchanged() -> None:
    """AC-3 — (app, None) arm; result is the literal AppDirect instance."""
    expected = AppDirect(...)
    @register_provenance_adapter(layer=Layer.APP, ecosystem=Ecosystem.NPM)
    class _A:
        def attribute(self, *a, **kw): return expected
        def confidence(self): ...
    result = assemble_provenance(...)
    assert result is expected


def test_base_only_returns_base_unchanged() -> None:
    """AC-4 — (None, base) arm."""
    # ... mirror app-only with BASE_IMAGE adapter ...


def test_first_non_unknown_per_layer_wins_in_ecosystem_sort_order() -> None:
    """AC-6 — Ecosystem-sort-order winner; second APP adapter never runs.
    Pins the BP-1 closure end-to-end (S2-03's helper sorts; this test proves
    assemble_provenance HONORS that sort)."""
    # Register two APP adapters: NPM and YARN_BERRY.
    # NPM (index 0 in Ecosystem) returns AppDirect; YARN_BERRY (index 1) would return
    # AppVendored if called. After assembly, result is AppDirect (NPM came first).
    ...


def test_provenance_error_folds_into_unknown_adapter_error() -> None:
    """AC-7 — ProvenanceError caught, becomes Unknown(reason='adapter_error')."""
    @register_provenance_adapter(layer=Layer.APP, ecosystem=Ecosystem.NPM)
    class _BrokenAdapter:
        def attribute(self, *a, **kw): raise AdapterError("kaboom")
        def confidence(self): ...
    result = assemble_provenance(...)
    assert isinstance(result, Unknown)
    assert result.reason == "adapter_error"


def test_runtime_error_propagates_rule_12_fail_loud() -> None:
    """AC-8 — non-ProvenanceError exceptions propagate; the function MUST NOT swallow."""
    @register_provenance_adapter(layer=Layer.APP, ecosystem=Ecosystem.NPM)
    class _SilentlyBuggyAdapter:
        def attribute(self, *a, **kw): raise RuntimeError("bug")
        def confidence(self): ...
    with pytest.raises(RuntimeError, match="bug"):
        assemble_provenance(...)


def test_default_registry_is_module_REGISTRY_when_kwarg_omitted() -> None:
    """AC-10 — registry=None uses _REGISTRY."""
    @register_provenance_adapter(layer=Layer.APP, ecosystem=Ecosystem.NPM)
    class _A:
        def attribute(self, *a, **kw): return AppDirect(...)
        def confidence(self): ...
    result = assemble_provenance(...)  # no registry kwarg
    assert isinstance(result, AppDirect)


def test_default_factory_is_default_adapter_factory_when_kwarg_omitted() -> None:
    """AC-11 — adapter_factory=None uses default_adapter_factory; constructs once."""
    construct_count = 0
    @register_provenance_adapter(layer=Layer.APP, ecosystem=Ecosystem.NPM)
    class _CountingAdapter:
        def __init__(self) -> None:
            nonlocal construct_count
            construct_count += 1
        def attribute(self, *a, **kw): return AppDirect(...)
        def confidence(self): ...
    assemble_provenance(...)
    assert construct_count == 1


def test_function_body_is_at_most_80_loc() -> None:
    """AC-12 — discipline assertion."""
    import ast, inspect
    source = inspect.getsource(assemble_provenance)
    tree = ast.parse(source).body[0]
    assert isinstance(tree, ast.FunctionDef)
    # exclude docstring
    body = tree.body[1:] if isinstance(tree.body[0], ast.Expr) else tree.body
    line_count = (body[-1].end_lineno or 0) - (body[0].lineno or 0) + 1
    assert line_count <= 80


def test_provenance_callable_re_exports_assemble_provenance() -> None:
    """AC-13 — TCCM derived_queries: compute: vuln.provenance resolves to this."""
    from codegenie.primitives.vuln_provenance import provenance, assemble_provenance
    assert provenance is assemble_provenance


def test_function_signature_exact() -> None:
    """AC-1 — signature pinning for downstream Phase 8+ TCCM resolver."""
    import inspect
    sig = inspect.signature(assemble_provenance)
    params = list(sig.parameters.values())
    assert [p.name for p in params] == [
        "cve_id", "package_id", "image_ref", "sbom",
        "registry", "adapter_factory",
    ]
    assert params[0].kind == inspect.Parameter.POSITIONAL_OR_KEYWORD
    assert params[4].kind == inspect.Parameter.KEYWORD_ONLY  # registry
    assert params[5].kind == inspect.Parameter.KEYWORD_ONLY  # adapter_factory
```

Add a separate file `tests/unit/primitives/vuln_provenance/test_assemble_match_exhaustive.py` per AC-9 (AST-walk asserting the match has exactly four arms + `assert_never`).

### Refactor

- Function docstring cites ADR-0001/0006/0007 + arch §6 verbatim; pins the four `match` arms inline.
- Comment on the `continue` after `ProvenanceError`: `# Per ADR-0007 §Consequences: adapter errors don't crash assembly; they fold to Unknown.`
- Comment on the `_REGISTRY` default: `# registry=None defaults to the module-level _REGISTRY; tests pass fresh dicts for isolation.`
- The `saw_adapter_error` flag (if tracked per the outline note) lives in the local scope; rename to `_adapter_error_seen` and document.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/primitives/vuln_provenance/assembly.py` (extend) | Add `assemble_provenance(...)` function body. |
| `src/codegenie/primitives/vuln_provenance/__init__.py` (extend) | Re-export `assemble_provenance` AND a top-level `provenance` alias (S8-02 TCCM `compute:` resolution target). |
| `tests/unit/primitives/vuln_provenance/test_assembly.py` | TDD red test + follow-on tests covering AC-1..AC-13. |
| `tests/unit/primitives/vuln_provenance/test_assemble_match_exhaustive.py` | AST-walk asserting the `match` block has exactly four arms + `assert_never` (AC-9). |

## Out of scope

- **Hypothesis property tests (50-permutation invariance, idempotence, `Both` no-recursion, RUNTIME reserved-slot under permutation)** — owned by **S2-05**.
- **Real adapter implementations** — owned by Step 3 (npm) and Step 4 (alpine + distroless).
- **Plugin-load → adapter-registration → `assemble_provenance` integration test** — owned by S3-01 (red-first contract test).
- **`AdapterFactory` Protocol + `DefaultAdapterFactory`** — owned by S2-02.
- **`_ADAPTER_DISPATCH_ORDER` + `iter_adapters_for_layer_set`** — owned by S2-03.
- **`@register_provenance_adapter` + `_REGISTRY`** — owned by S2-01.
- **TCCM `derived_queries:` schema + `compute:` resolver** — owned by S8-02 + S8-03. This story only exports the `provenance` alias the resolver targets.
- **Coordination event emission for `Both` results** — owned by S11-01 (`RequiresMultiPluginCoordination` event) + S11-02 (writer). This function emits the `Both` variant; downstream code converts it to coordination evidence.
- **Caching of `assemble_provenance` results** — explicitly NOT shipped per Phase 7 ADR-0008. Repeated calls re-run the adapters.
- **Async assembly** — explicitly NOT shipped. `assemble_provenance` is synchronous; adapters' `attribute()` is synchronous (per Phase 7 ADR-0014 — design pattern: keep CPU-bound deterministic transforms synchronous).

## Notes for the implementer

- **The 80-LOC budget is real, not aspirational.** Arch §6 says "≤ 80 LOC total". AC-12's AST-counting test pins it. If your implementation crosses 80, refactor by extracting a helper (e.g., `_dispatch_layer(layer, reg, factory, ...) -> Provenance | None` that returns the first non-`Unknown` for one layer). Don't grow the function.
- **`match`/`assert_never` is non-negotiable.** Per ADR-0006 §Consequences row 4: critic BP-4 closure — no `if r.kind in {"app_direct", "app_transitive", ...}` string-set comparisons. The `case _: assert_never(...)` line makes `mypy --strict` prove exhaustiveness; future-proofs against adding an eighth `Provenance` variant without updating the dispatch.
- **`AppKind` and `BaseKind` are S1-03's typed unions** — `AppKind = AppDirect | AppTransitive | AppVendored`, `BaseKind = BaseImage | RuntimeBundled`. The `app_result` / `base_result` locals are typed as `AppKind | None` / `BaseKind | None`. When the inner loop assigns from an adapter's return type, narrow via `isinstance(result, Unknown): continue` first — the remaining type is `AppKind` or `BaseKind` depending on the layer (the adapter's contract).
- **Adapter-error reason tracking is subtle.** Two arguments interpret arch §6's "ProvenanceError → Unknown(reason='adapter_error')" line:
  - **Local-only:** each adapter call that errors is replaced by `Unknown(reason="adapter_error")` and the dispatch keeps walking. If a later adapter resolves a real result, that's the final answer. The `(None, None)` arm returns `Unknown(reason="no_adapter_resolved")` only if no adapter at all returned a result.
  - **Global flag:** ANY adapter error during dispatch poisons the final result; if no real result resolves, the final `Unknown` carries `reason="adapter_error"`, not `"no_adapter_resolved"`.
  Read arch §6 + ADR-0007 carefully; consult final-design synthesis ledger. Implementer's call: ship the global flag (matches arch §6's wording better and is more honest about partial failure); document the choice in the function docstring; AC-7's test passes either way (single-adapter case).
- **`provenance` is the TCCM-facing name; `assemble_provenance` is the internal one.** S8-02's `DerivedQuery.compute: str = "vuln.provenance"` (a dotted callable) resolves to the `provenance` alias via S8-03's loader. Don't break the alias; don't add another exported name. The aliasing is the load-bearing TCCM-resolver contract.
- **Rule 12 (fail loud) is THE invariant.** `RuntimeError` from an adapter MUST propagate. The only exception class this function catches is `ProvenanceError` (and its subclasses). If a future PR adds `except Exception:` here, the property tests (S2-05's `test_runtime_errors_propagate`) will fail loud.
- **Adapter construction happens INSIDE the loop, not before it.** Per ADR-0007 + S2-02: factories construct lazily; if an adapter is never reached (layer mismatch, earlier adapter resolves), its `__init__` never runs. Don't pre-instantiate all adapters in the registry — that re-introduces BP-3 ("worst time to do work" at decoration time, just deferred to assembly time).
- **`image_ref` is `ImageRef | None`** — not all assembly calls have an image. For app-only attributions without a container, callers pass `None`; adapters that need an image return `Unknown(reason="image_ref_missing")` (their contract — S3-02 / S4-02 will pin this). `assemble_provenance` itself doesn't validate `image_ref`'s presence.
