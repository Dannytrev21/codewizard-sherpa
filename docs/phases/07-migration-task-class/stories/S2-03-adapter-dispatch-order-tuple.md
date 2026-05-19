# Story S2-03 — `_ADAPTER_DISPATCH_ORDER` `Final` tuple + `Ecosystem`-sorted intra-layer iteration

**Step:** Step 2 — Registry kernel, `_ADAPTER_DISPATCH_ORDER`, `assemble_provenance` free function
**Status:** Ready
**Effort:** S
**Depends on:** S2-01 (`Layer`, `Ecosystem`, `_REGISTRY`)
**ADRs honored:** Phase 7 ADR-0006 (dispatch order is explicit `Final` tuple, NOT implicit `dict.items()` — closes critic BP-1), Phase 7 ADR-0007 (registry-stores-classes — this story's iteration helper returns classes), Phase 7 ADR-0004 (vuln.provenance primitive home — assembly module lives there), production ADR-0038 (vulnerability provenance attribution — the deferred order-policy question).

## Context

Phase 7 ADR-0006 lands the answer to the order-policy question deferred by production ADR-0038: dispatch order is **explicit data**, declared as a module-level `Final` tuple. The best-practices lens design walked `registry.items()` in dict-insertion order, which smuggled plugin-import order — which depends on filesystem ordering or `sorted()` discipline — as the dispatch policy. The critic landed BP-1 hard. The synthesis answer is `_ADAPTER_DISPATCH_ORDER: Final[tuple[tuple[Layer, ...], ...]]`: walk layer-sets explicitly; within each layer-set, iterate the matching subset of `_REGISTRY` in `Ecosystem`-enum-sorted order (NOT `dict.items()` order — Gap 4 polyglot tiebreaker).

S2-04's `assemble_provenance` consumes this tuple and the sort helper. S2-05's Hypothesis property test (50 permutations of registration order) is what locks the discipline — but the discipline lives here.

**Scope reminder.** S2-03 ships ONLY: the `Final` tuple constant + a small typed iteration helper (`iter_adapters_for_layer_set`) + unit tests verifying tuple shape, declaration order, and intra-layer Ecosystem-sorted iteration. `assemble_provenance` lives in S2-04. The 50-permutation property test lives in S2-05. The `RUNTIME` reserved-slot property test (empty layer behaves correctly) lives in S2-05.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design §5` — verbatim definition of `_ADAPTER_DISPATCH_ORDER`. The tuple has exactly three rows in declaration order: `(Layer.APP,), (Layer.BASE_IMAGE,), (Layer.RUNTIME,)`.
  - `../phase-arch-design.md §Component design §5` last bullet — "Within a layer-set, registry is iterated in `Ecosystem`-enum-sorted order (deterministic), NOT `dict.items()` order."
  - `../phase-arch-design.md §Component design §6` — `assemble_provenance` walks the tuple; this story provides the data + the iteration helper that S2-04 consumes.
  - `../phase-arch-design.md §Design patterns applied` — "Strategy via data" + "Final-tuple marker catalog" (sibling pattern to `_GENERATOR_HEADER_MARKERS`, `_REFLECTION_QUERIES`, `_LOCKFILE_PRECEDENCE`).
  - `../phase-arch-design.md §Edge cases` — Gap 4 (polyglot tiebreaker): `Ecosystem`-enum-sorted within a layer.
- **Phase ADRs:**
  - `../ADRs/0006-adapter-dispatch-explicit-final-tuple.md` — full decision rationale. `Final` tuple in declaration order; `Ecosystem`-enum-sorted intra-layer; `Layer.RUNTIME` reserved slot is part of Phase 7's shape (no runtime adapter ships, but the row is there).
  - `../ADRs/0006-adapter-dispatch-explicit-final-tuple.md §Consequences` — every consequence row maps to a test (declaration order, Ecosystem-sort, RUNTIME reserved slot, property-test placement).
- **Existing code (precedent to mirror):**
  - `src/codegenie/probes/lockfile_precedence.py` (or wherever `_LOCKFILE_PRECEDENCE` lives — Phase 1) — closest precedent for a module-level `Final` tuple driving deterministic iteration.
  - `src/codegenie/probes/_GENERATOR_HEADER_MARKERS` — sibling marker-catalog pattern, same `Final` tuple shape.
- **Sibling tests:**
  - `tests/unit/probes/test_lockfile_precedence.py` (Phase 1) — canonical idiom for testing a declaration-order `Final` tuple.

## Goal

Ship `src/codegenie/primitives/vuln_provenance/assembly.py` containing: (1) `_ADAPTER_DISPATCH_ORDER: Final[tuple[tuple[Layer, ...], ...]] = ((Layer.APP,), (Layer.BASE_IMAGE,), (Layer.RUNTIME,))`; (2) a typed helper `iter_adapters_for_layer_set(layer_set: tuple[Layer, ...], registry: Mapping[ProvenanceAdapterId, type[VulnProvenanceAdapter]]) -> Iterator[tuple[ProvenanceAdapterId, type[VulnProvenanceAdapter]]]` that yields `(key, cls)` pairs filtered to the layer set and sorted by `Ecosystem` declaration order; (3) unit tests proving both. S2-04 imports both symbols.

## Acceptance criteria

- [ ] **AC-1 — `_ADAPTER_DISPATCH_ORDER` shape and order.** `assembly.py` declares `_ADAPTER_DISPATCH_ORDER: Final[tuple[tuple[Layer, ...], ...]] = ((Layer.APP,), (Layer.BASE_IMAGE,), (Layer.RUNTIME,))`. Test asserts `_ADAPTER_DISPATCH_ORDER == ((Layer.APP,), (Layer.BASE_IMAGE,), (Layer.RUNTIME,))` (exact-tuple equality; catches reordering and member-set changes).
- [ ] **AC-2 — Tuple is `Final`-typed and immutable in practice.** Test asserts `assembly._ADAPTER_DISPATCH_ORDER` is a `tuple`, not `list`, and each inner element is `tuple`, not `list`. (Python doesn't enforce `Final` at runtime; the test pins the shape.)
- [ ] **AC-3 — `iter_adapters_for_layer_set` filters by layer.** Given a registry populated with three classes — `(Layer.APP, Ecosystem.NPM, _A)`, `(Layer.BASE_IMAGE, Ecosystem.APK, _B)`, `(Layer.BASE_IMAGE, Ecosystem.DPKG, _C)` — calling `iter_adapters_for_layer_set((Layer.APP,), registry)` yields ONLY the APP entry. Calling with `(Layer.BASE_IMAGE,)` yields ONLY APK and DPKG. Catches "yields everything" and "yields wrong-layer" mutants.
- [ ] **AC-4 — Intra-layer iteration is `Ecosystem`-declaration-sorted.** Register entries in non-declaration order: `(Layer.BASE_IMAGE, Ecosystem.DPKG, _C)` first, then `(Layer.BASE_IMAGE, Ecosystem.APK, _B)`. Calling `iter_adapters_for_layer_set((Layer.BASE_IMAGE,), registry)` MUST yield APK (index 3 in `tuple(Ecosystem)`) BEFORE DPKG (index 4). Test asserts the order is `(APK_key, DPKG_key)` regardless of registration order. **This is the load-bearing Gap 4 polyglot-tiebreaker assertion** — locks BP-1 at the helper level (S2-05's property test locks it end-to-end).
- [ ] **AC-5 — Empty layer yields nothing.** `iter_adapters_for_layer_set((Layer.RUNTIME,), registry)` on an empty `RUNTIME` layer yields zero items. Test exhausts the iterator and asserts the resulting list is `[]`. This is the `RUNTIME` reserved-slot smoke check (Phase 7 ADR-0006 §Consequences row 2 — Phase 7 ships no runtime adapter, but the row is reserved).
- [ ] **AC-6 — Multi-layer layer-set yields filtered + sorted union.** Future-proofing for hypothetical `(Layer.APP, Layer.BASE_IMAGE)` layer-sets: the helper concatenates per-layer iterations in `_ADAPTER_DISPATCH_ORDER`-tuple order, each intra-layer sorted by `Ecosystem`. Test with a synthetic `layer_set = (Layer.APP, Layer.BASE_IMAGE)` registers one APP and two BASE_IMAGE entries; asserts the yielded order is `(APP_key, BASE_IMAGE_APK_key, BASE_IMAGE_DPKG_key)`. (Phase 7's `_ADAPTER_DISPATCH_ORDER` never uses multi-element layer-sets, but the helper supports them — preserving the tuple-of-tuples shape per ADR-0006.)
- [ ] **AC-7 — `iter_adapters_for_layer_set` is `mypy --strict` clean with `Mapping[ProvenanceAdapterId, type[VulnProvenanceAdapter]]` parameter typing.** Allows callers to pass either `_REGISTRY` (real) or test fixtures (any `Mapping`).
- [ ] **AC-8 — TDD red test exists, committed, green.** `tests/unit/primitives/vuln_provenance/test_assembly_dispatch_order.py::test_intra_layer_iteration_is_ecosystem_sorted_not_registration_sorted` was the first failing test; impl makes it green.
- [ ] **AC-9 — Lint / type clean.** `ruff check`, `ruff format --check`, `mypy --strict` clean on `src/codegenie/primitives/vuln_provenance/assembly.py` and the test module. `make lint-imports` green.

## Implementation outline

1. Create `src/codegenie/primitives/vuln_provenance/assembly.py`:
   - Module docstring cites ADR-0006 §Decision + §Consequences row "Within-layer iteration is `sorted(adapters_for_layer, key=lambda a: a.ecosystem)`". Names the tuple as the operator-facing dispatch policy.
   - `from __future__ import annotations` + imports: `Final`, `Iterator`, `Mapping`, `TYPE_CHECKING`.
   - `from .registry import Layer, Ecosystem, ProvenanceAdapterId` (and `VulnProvenanceAdapter` from `protocols.py` under `TYPE_CHECKING`).
   - `_ADAPTER_DISPATCH_ORDER: Final[tuple[tuple[Layer, ...], ...]] = ((Layer.APP,), (Layer.BASE_IMAGE,), (Layer.RUNTIME,))`.
   - Module-level constant for the Ecosystem sort key:
     ```python
     _ECOSYSTEM_SORT_KEY: Final[Mapping[Ecosystem, int]] = {
         eco: i for i, eco in enumerate(Ecosystem)
     }
     ```
     (Built once at import time from `tuple(Ecosystem)` declaration order; `iter_adapters_for_layer_set` looks up here instead of calling `tuple(Ecosystem).index(...)` per item.)
   - `def iter_adapters_for_layer_set(layer_set: tuple[Layer, ...], registry: Mapping[ProvenanceAdapterId, type[VulnProvenanceAdapter]]) -> Iterator[tuple[ProvenanceAdapterId, type[VulnProvenanceAdapter]]]:`
     ```python
     for layer in layer_set:                                # outer order: by layer_set tuple
         matching = [(key, cls) for key, cls in registry.items() if key[0] == layer]
         matching.sort(key=lambda kv: _ECOSYSTEM_SORT_KEY[kv[0][1]])
         for kv in matching:
             yield kv
     ```
2. Extend `src/codegenie/primitives/vuln_provenance/__init__.py` to re-export `_ADAPTER_DISPATCH_ORDER` and `iter_adapters_for_layer_set` (S2-04 imports both).
   - Note: `_ADAPTER_DISPATCH_ORDER` is module-private by leading underscore. Re-export via the module path (`from codegenie.primitives.vuln_provenance import assembly as _assembly_mod`) — same convention as S2-01's `_REGISTRY`.
3. Write the red test (`test_intra_layer_iteration_is_ecosystem_sorted_not_registration_sorted`); watch import-error; implement; watch green; add follow-on tests.

## TDD plan — red / green / refactor

### Red

Test file path: `tests/unit/primitives/vuln_provenance/test_assembly_dispatch_order.py`

```python
from __future__ import annotations

from codegenie.primitives.vuln_provenance.assembly import iter_adapters_for_layer_set
from codegenie.primitives.vuln_provenance.registry import Ecosystem, Layer


def test_intra_layer_iteration_is_ecosystem_sorted_not_registration_sorted() -> None:
    """ADR-0006 §Consequences: 'Within-layer iteration is sorted(adapters_for_layer,
    key=lambda a: a.ecosystem) — explicit, by Ecosystem enum value.'
    BP-1 closure: registration order is NOT load-bearing."""

    class _DpkgAdapter: ...
    class _ApkAdapter: ...

    # Register DPKG (index 4 in Ecosystem) BEFORE APK (index 3 in Ecosystem)
    # — registration order is reversed from declaration order.
    registry = {
        (Layer.BASE_IMAGE, Ecosystem.DPKG): _DpkgAdapter,
        (Layer.BASE_IMAGE, Ecosystem.APK): _ApkAdapter,
    }

    yielded = list(iter_adapters_for_layer_set((Layer.BASE_IMAGE,), registry))
    yielded_eco = [key[1] for key, _ in yielded]

    # APK comes first because Ecosystem.APK is declared before Ecosystem.DPKG.
    assert yielded_eco == [Ecosystem.APK, Ecosystem.DPKG]
```

Why it fails: `iter_adapters_for_layer_set` doesn't exist — `ImportError`.

### Green — minimal pass

Create `assembly.py` per the implementation outline. Wire `__init__.py` re-exports. Watch the red test pass.

### Required follow-on tests

```python
from codegenie.primitives.vuln_provenance import assembly as _assembly_mod


def test_dispatch_order_tuple_shape_and_declaration_order() -> None:
    """AC-1 + AC-2 — exact tuple equality + tuple-not-list shape."""
    assert _assembly_mod._ADAPTER_DISPATCH_ORDER == (
        (Layer.APP,), (Layer.BASE_IMAGE,), (Layer.RUNTIME,),
    )
    assert isinstance(_assembly_mod._ADAPTER_DISPATCH_ORDER, tuple)
    for layer_set in _assembly_mod._ADAPTER_DISPATCH_ORDER:
        assert isinstance(layer_set, tuple)


def test_iter_filters_by_layer() -> None:
    """AC-3 — yields only matching-layer entries (catches 'yields everything' mutant)."""
    class _Npm: ...
    class _Apk: ...
    class _Dpkg: ...
    registry = {
        (Layer.APP, Ecosystem.NPM): _Npm,
        (Layer.BASE_IMAGE, Ecosystem.APK): _Apk,
        (Layer.BASE_IMAGE, Ecosystem.DPKG): _Dpkg,
    }
    app_only = list(iter_adapters_for_layer_set((Layer.APP,), registry))
    assert [key[0] for key, _ in app_only] == [Layer.APP]
    assert [cls for _, cls in app_only] == [_Npm]

    base_only = list(iter_adapters_for_layer_set((Layer.BASE_IMAGE,), registry))
    assert {key[1] for key, _ in base_only} == {Ecosystem.APK, Ecosystem.DPKG}


def test_empty_runtime_layer_yields_nothing() -> None:
    """AC-5 — RUNTIME reserved slot smoke; Phase 7 ships no runtime adapter."""
    class _Npm: ...
    registry = {(Layer.APP, Ecosystem.NPM): _Npm}
    yielded = list(iter_adapters_for_layer_set((Layer.RUNTIME,), registry))
    assert yielded == []


def test_multi_layer_layer_set_preserves_layer_set_tuple_order() -> None:
    """AC-6 — future-proof multi-element layer-set; outer order is the layer_set tuple."""
    class _Npm: ...
    class _Apk: ...
    class _Dpkg: ...
    registry = {
        (Layer.APP, Ecosystem.NPM): _Npm,
        (Layer.BASE_IMAGE, Ecosystem.APK): _Apk,
        (Layer.BASE_IMAGE, Ecosystem.DPKG): _Dpkg,
    }
    yielded = list(iter_adapters_for_layer_set((Layer.APP, Layer.BASE_IMAGE), registry))
    keys = [key for key, _ in yielded]
    assert keys == [
        (Layer.APP, Ecosystem.NPM),
        (Layer.BASE_IMAGE, Ecosystem.APK),
        (Layer.BASE_IMAGE, Ecosystem.DPKG),
    ]


def test_iter_returns_classes_not_instances() -> None:
    """ADR-0007 cross-check: the helper yields type[VulnProvenanceAdapter], not instances."""
    class _Npm: ...
    registry = {(Layer.APP, Ecosystem.NPM): _Npm}
    yielded = list(iter_adapters_for_layer_set((Layer.APP,), registry))
    _, cls = yielded[0]
    assert cls is _Npm                                  # identity — it's the CLASS
    assert isinstance(cls, type)                        # confirm class-not-instance
```

### Refactor

- Module docstring on `assembly.py`: cite ADR-0006 + ADR-0007 cross-reference; name BP-1 closure as the test discipline `iter_adapters_for_layer_set` enables.
- `_ECOSYSTEM_SORT_KEY` is built from `tuple(Ecosystem)` at import time, so adding/reordering `Ecosystem` enum members re-derives the sort automatically (Ecosystem declaration order remains the source of truth — AC-2 in S2-01 pins it).
- Inline comment on the `matching.sort(...)` line: `# Ecosystem-enum-declaration order, NOT dict.items() order (ADR-0006 §Consequences row 3; BP-1 closure)`.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/primitives/vuln_provenance/assembly.py` | New module: `_ADAPTER_DISPATCH_ORDER`, `_ECOSYSTEM_SORT_KEY`, `iter_adapters_for_layer_set`. |
| `src/codegenie/primitives/vuln_provenance/__init__.py` (extend) | Re-export `iter_adapters_for_layer_set` (S2-04 imports). |
| `tests/unit/primitives/vuln_provenance/test_assembly_dispatch_order.py` | TDD red test + follow-on tests covering AC-1..AC-7. |

## Out of scope

- **`assemble_provenance(...)` free function** — owned by **S2-04**. This story ships ONLY the dispatch policy + iteration helper.
- **Hypothesis property test (50 registration-order permutations)** — owned by **S2-05**. This story's unit test covers the two-element APK/DPKG case; the property test covers arbitrary permutations.
- **`Both` variant composition (`match (app, base)`)** — owned by S2-04. This story doesn't compose results — it just iterates adapters.
- **Adapter-error catching (`ProvenanceError` → `Unknown(reason="adapter_error")`)** — owned by S2-04.
- **`Layer.RUNTIME` reserved-slot property test (empty layer behaves under permutation)** — owned by S2-05 (Hypothesis-driven). This story's AC-5 covers the smoke case.
- **`AdapterFactory`-driven construction** — owned by S2-02 (Protocol) + S2-04 (call site). The iteration helper yields classes; construction happens later.

## Notes for the implementer

- **The `_ECOSYSTEM_SORT_KEY` dict is built once at import time** from `enumerate(Ecosystem)`. This binds the sort to `Ecosystem`'s declaration order (S2-01 AC-2 pins that). If a future ADR amendment adds an `Ecosystem` value, the sort order auto-updates without touching this module — but a new value sorting before existing values would re-order intra-layer iteration. Phase 7 ADR-0006 §Tradeoffs row 3 acknowledges this; mitigated by S2-05's property test pinning the byte-identical-result invariant per registration order, not per Ecosystem-set.
- **Do NOT use `tuple(Ecosystem).index(...)` per item** in the sort key. `index()` is O(n); on a hot path that matters. The precomputed `_ECOSYSTEM_SORT_KEY` is O(1) per lookup.
- **The helper accepts `Mapping`, not `dict`.** This is deliberate: tests pass plain `dict` fixtures; production passes `_REGISTRY` (also a dict, but the contract is `Mapping`). S2-04 will likely call `iter_adapters_for_layer_set(layer_set, registry or _REGISTRY)` with the optional `registry` param flowing through.
- **The helper yields `(key, cls)` tuples** — not just `cls`. S2-04 will want the key for diagnostics (e.g., logging which adapter ran first when composing the result), and the key carries the `Layer` + `Ecosystem` enum values which the audit log will pin.
- **`Layer.RUNTIME` reserved-slot row is intentional.** First runtime adapter (JRE-bundled, future phase) registers `@register_provenance_adapter(layer=Layer.RUNTIME, ecosystem=...)` and the empty-tuple iteration starts yielding. No code change to this module — the discipline is open/closed for extension on Ecosystem additions, closed on Layer additions (which require an ADR amendment per ADR-0006 §Consequences).
- **Module-level `Final`-tuple cataloging is a load-bearing codebase convention.** Sibling patterns: `_GENERATOR_HEADER_MARKERS` (Phase 1), `_REFLECTION_QUERIES` (Phase 1 node-reflection probe), `_LOCKFILE_PRECEDENCE` (Phase 1). Reviewers know the shape — keep it boring.
