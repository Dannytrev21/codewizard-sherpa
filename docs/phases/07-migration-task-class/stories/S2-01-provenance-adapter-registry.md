# Story S2-01 — `Layer` + `Ecosystem` enums + `_REGISTRY` + `@register_provenance_adapter` decorator

**Step:** Step 2 — Registry kernel, `_ADAPTER_DISPATCH_ORDER`, `assemble_provenance` free function
**Status:** HARDENED (phase-story-validator, 2026-06-05 — retrospective pass on shipped GREEN story; see `_validation/S2-01-provenance-adapter-registry.md`) — originally shipped GREEN 2026-05-19 (see `_attempts/S2-01-provenance-adapter-registry.md`)
**Effort:** M
**Depends on:** S1-01 (`ProvenanceAdapterId` newtype, `CveId`, `PackageId`, `ImageRef`), S1-03 (seven-variant `Provenance` discriminated union — referenced only via `type[VulnProvenanceAdapter]`), S1-04 (`VulnProvenanceAdapter` Protocol + `ProvenanceError` / `RegistryError` typed exception hierarchy)
**ADRs honored:** Phase 7 ADR-0001 (no `MultiPluginCoordinator` — this registry is the only Phase 7 plugin/registry seam for adapters), Phase 7 ADR-0004 (vuln.provenance primitive home — registry lives under the primitive tree), Phase 7 ADR-0006 (framing only — dispatch policy lives in S2-03's `Final` tuple, NOT in this registry), Phase 7 ADR-0007 (registry stores **classes**, not instances), production ADR-0031 (Plugin/Registry), production ADR-0032 (DepGraphAdapter Protocol — adapter shape precedent), production ADR-0038 (vulnerability provenance attribution — the deferred ADR this resolves).

## Validation notes

Validated: 2026-06-05 (retrospective — story shipped GREEN 2026-05-19; this pass documents the audit trail and applies tightening edits that would have hardened the story pre-execution)
Verdict: HARDENED
Findings addressed: 5 total — 0 blocks, 4 hardens, 1 nit

Changes applied (full audit log: `_validation/S2-01-provenance-adapter-registry.md`):

- **AC-1/AC-2 enum syntax synced with shipped code (HARDEN, F-CON-1):** the original story spec'd `class Layer(str, Enum)` and `class Ecosystem(str, Enum)`; shipped code uses `class Layer(StrEnum)` / `class Ecosystem(StrEnum)` (Python 3.11+ idiom; `StrEnum` is the canonical replacement for the `str, Enum` multiple-inheritance trick — see [PEP 663](https://docs.python.org/3.11/library/enum.html#enum.StrEnum)). Story-vs-code drift would have surfaced as a mypy noise or a contributor confused about which idiom is canonical. AC-1 + AC-2 + Implementation outline §2 + the TDD-plan red-test imports now spec `StrEnum`. Avoids the drift surface for future sibling stories (Phase 7.5 language ecosystem enum, etc.).
- **New AC-13 — decorator is keyword-only (HARDEN, F-TQ-1):** original ACs did not pin the kwarg-only `*, layer, ecosystem` signature. A positional-arg mutation (`def register_provenance_adapter(layer, ecosystem)`) would silently land and break the call-site contract; every downstream `@register_provenance_adapter(layer=..., ecosystem=...)` callsite would still pass, but a contributor invoking positionally would slip in. New test `test_decorator_signature_is_keyword_only` asserts `pytest.raises(TypeError)` when invoked positionally. Mirrors the pinning discipline applied to S5-02 of Phase 6.5 for signature contracts.
- **New AC-14 — distinct-keys-coexist (HARDEN, F-COV-1):** original AC-3 pinned the `_REGISTRY` shape but no AC pinned the "registry stores both adapters when keys differ" contract. The shipped test (`test_distinct_keys_coexist`) covers it but was implicit; promoting to an AC closes the cover gap and prevents a future mutant `_REGISTRY[key] = cls; _REGISTRY.clear(); _REGISTRY[key] = cls` from passing the other ACs.
- **AC-6 collision-message specificity tightened (HARDEN, F-TQ-2):** original AC-6 asserted `str(exc).count(".") >= 2` (two `module.qualname` strings). That assertion would pass on a message that happens to mention `RegistryError` twice or contains incidental dots. Tightened to: the message must contain BOTH literal qualified names (`existing_qualname` AND `duplicate_qualname` substrings) — the shipped test already does this, the AC now matches the implementation surface exactly.
- **`StrEnum` import in TDD plan red-test (NIT, F-CON-2):** the TDD-plan red-test snippet didn't import `StrEnum`; the test only needs `Layer` and `Ecosystem` *enum-instance* access, so no change required, but the Implementation outline §2 now says `from enum import StrEnum` for clarity.

Design endorsements (no edit; surfaced in Notes-for-implementer):
- **Plugin/Registry kernel pattern** — fifth instance of the decorator-registry family (`probes`, `indices`, `depgraph`, `plugins`, this). Rule-of-three deferral correctly recorded — the four prior sites diverge non-trivially in dispatch shape (already documented in the shipped `registry.py` docstring), so kernel-extract is *not* prescribed here. Recorded as an N≥5 cleanup candidate for a future story (matches the codebase's standing convention from Phase 1 ADR-0013 and `depgraph/registry.py` precedent).
- **Class-as-token + lazy construction** — load-bearing for the DI seam S2-02 ships. The AC-7 BP-3 regression test (`_AdapterWithExplodingInit`) is the canary that protects this; do not delete.
- **Open/Closed at the registry** — adding a `Layer` or `Ecosystem` value is an ADR amendment, never a silent edit (CLAUDE.md "Extension by addition" + ADR-0043). The declaration-order ACs (AC-1, AC-2) enforce this structurally; a PR adding a member would surface in code review against the AC contract.

No `NEEDS RESEARCH` items — every pattern is precedented in this repo (Phase 2 S1-10 `@register_dep_graph_strategy` validation, Phase 7 S1-04 protocol validation, Phase 3 S2-01 plugin kernel validation).

## Context

Step 2 lands the **kernel** of the `vuln.provenance` primitive's adapter seam. S2-01 ships the registry half: two enums (`Layer`, `Ecosystem`), the module-level `_REGISTRY` dict, and the `@register_provenance_adapter(*, layer, ecosystem)` decorator. Per Phase 7 ADR-0007 the registry stores **classes** (`type[VulnProvenanceAdapter]`), not instances — construction is dispatch-time and DI-aware via S2-02's `AdapterFactory`. Per Phase 7 ADR-0006 dispatch order is NOT a registry concern — it lives in `_ADAPTER_DISPATCH_ORDER` (S2-03) and `assemble_provenance` (S2-04) walks that tuple, not registration order.

This story mirrors the three existing decorator-registry precedents in the codebase (`probes/registry.py`, `indices/registry.py`, `depgraph/registry.py`) and the Phase 3 plugin registry (`plugins/registry.py`). Reviewers should not have to context-switch between idioms.

**Scope reminder.** S2-01 ships ONLY: enums + `_REGISTRY` + `@register_provenance_adapter` + `RegistryError` collision behavior + per-test isolation fixture. `AdapterFactory` Protocol lives in S2-02. `_ADAPTER_DISPATCH_ORDER` tuple + `Ecosystem`-sorted iteration lives in S2-03. `assemble_provenance` lives in S2-04. The 50-permutation Hypothesis property test lives in S2-05.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design §4` — full public interface for `Layer`, `Ecosystem`, `ProvenanceAdapterId`, `_REGISTRY`, `register_provenance_adapter` decorator. Cite verbatim: registry stores `type[VulnProvenanceAdapter]`, not instances; duplicate key raises `RegistryError` at import time.
  - `../phase-arch-design.md §Component design §3` — `VulnProvenanceAdapter` Protocol shape that the decorator's `cls` argument must satisfy.
  - `../phase-arch-design.md §Design patterns applied` — Plugin/Registry + Class-as-token + Lazy construction; mirrors `@register_dep_graph_strategy`.
  - `../phase-arch-design.md §Anti-patterns avoided` — "Side effects in constructors / module import time" (no `cls()` at decoration time).
- **Phase ADRs:**
  - `../ADRs/0007-provenance-adapter-registry-stores-classes.md` — Option C is the decision. `_REGISTRY: Final[dict[ProvenanceAdapterId, type[VulnProvenanceAdapter]]]`. Duplicate registration raises `RegistryError` at import time. No `isinstance(cls(), VulnProvenanceAdapter)` runtime check (gives false safety per ADR §Tradeoffs row 4).
  - `../ADRs/0006-adapter-dispatch-explicit-final-tuple.md` — framing only. This story's registry must NOT impose any ordering; ordering lives in S2-03's `_ADAPTER_DISPATCH_ORDER`. The registry is a plain `dict[ProvenanceAdapterId, type[...]]`.
  - `../ADRs/0004-vuln-provenance-primitive-home.md` — primitive lives at `src/codegenie/primitives/vuln_provenance/`; this story's `registry.py` lands there.
  - `../ADRs/0001-no-multi-plugin-coordinator-in-phase-7.md` — framing only. The registry is the only plugin/registry seam Phase 7 ships for adapters; there is no parallel coordinator class.
- **Source design:** `../final-design.md §Synthesis ledger row 11 (score 14/15) + departure #2` — the "registry stores classes, not instances" decision.
- **Existing code (precedent to mirror):**
  - `src/codegenie/depgraph/registry.py:1-90` — closest sibling: `@register_dep_graph_strategy(eco: PackageManager)` keyed on a single enum. Mirror its shape: module-level dict, decorator returns `_wrap`, `RegistryError` on duplicate, no construction at decoration time.
  - `src/codegenie/indices/registry.py:26-31` + `:198-208` — the deferral docstring (rule-of-three observation) + `unregister_for_tests` shape (we do NOT add `unregister_for_tests` here; the conftest fixture handles isolation).
  - `src/codegenie/probes/registry.py:139` + `:154-158` — the dual-name collision message precedent (existing + duplicate `module.qualname`).
  - `src/codegenie/plugins/registry.py` — Phase 3 plugin kernel; same `default_registry` placement convention but `register_plugin` is a function call, not a decorator. This story uses the decorator shape (closer to `@register_dep_graph_strategy`) because adapters are classes, not instances.
  - `src/codegenie/types/identifiers.py` — `ProvenanceAdapterId` is the `tuple[Layer, Ecosystem]` newtype added in S1-01; import it.
  - `tests/unit/depgraph/test_registry.py` — canonical test idioms (fresh-instance fixture, dual-name collision message, restore autouse).
- **Sibling validation framings:**
  - `docs/phases/02-context-gather-layers-b-g/stories/_validation/S1-10-depgraph-strategy-registry.md` — established hardening conventions for single-enum-keyed registries.

## Goal

Ship `src/codegenie/primitives/vuln_provenance/registry.py` containing: (1) `Layer` and `Ecosystem` string enums per arch §4; (2) a module-level `_REGISTRY: Final[dict[ProvenanceAdapterId, type[VulnProvenanceAdapter]]] = {}`; (3) a `@register_provenance_adapter(*, layer, ecosystem)` decorator that stores the **class** in `_REGISTRY` and raises `RegistryError` at decoration time on duplicate `(layer, ecosystem)` keys; (4) an autouse `provenance_registry_reset` pytest fixture (under `tests/conftest.py` or `tests/unit/primitives/vuln_provenance/conftest.py`) that snapshots `_REGISTRY` per test and restores it on teardown.

## Acceptance criteria

- [ ] **AC-1 — `Layer` enum.** `src/codegenie/primitives/vuln_provenance/registry.py` exports `class Layer(StrEnum)` (Python 3.11+ `enum.StrEnum`; not the legacy `class Layer(str, Enum)` multiple-inheritance idiom) with **exactly three** members in this declaration order: `APP = "app"`, `BASE_IMAGE = "base_image"`, `RUNTIME = "runtime"`. Test asserts `tuple(Layer) == (Layer.APP, Layer.BASE_IMAGE, Layer.RUNTIME)` AND each `.value` equals its lowercase string. The `StrEnum` choice is load-bearing: `Layer.APP == "app"` evaluates `True` (required for the YAML-driven catalog readers in S9 that compare string keys against `Layer` members).
- [ ] **AC-2 — `Ecosystem` enum.** Exports `class Ecosystem(StrEnum)` with **exactly six** members: `NPM = "npm"`, `YARN_BERRY = "yarn-berry"`, `PNPM = "pnpm"`, `APK = "apk"`, `DPKG = "dpkg"`, `RPM = "rpm"`. Test asserts `tuple(Ecosystem) == (Ecosystem.NPM, Ecosystem.YARN_BERRY, Ecosystem.PNPM, Ecosystem.APK, Ecosystem.DPKG, Ecosystem.RPM)` AND each `.value` equals its kebab-case string. Adding a value is an ADR amendment (arch §4 line `# open to additive enum values via ADR amendment`).
- [ ] **AC-3 — `_REGISTRY` shape.** Module-level `_REGISTRY: Final[dict[ProvenanceAdapterId, type[VulnProvenanceAdapter]]] = {}`. `ProvenanceAdapterId` is imported from `codegenie.types.identifiers` (S1-01). Test asserts `_REGISTRY == {}` at import time (when the autouse reset fixture is active).
- [ ] **AC-4 — `@register_provenance_adapter` decorator stores the CLASS, not an instance.** Decorator signature: `def register_provenance_adapter(*, layer: Layer, ecosystem: Ecosystem) -> Callable[[type[VulnProvenanceAdapter]], type[VulnProvenanceAdapter]]`. After decoration, `_REGISTRY[(layer, ecosystem)] is cls` (identity check — NOT `isinstance` of an instance). The decorator MUST NOT call `cls()` (catches BP-3 regression).
- [ ] **AC-5 — Decorator returns `cls` unchanged.** `@register_provenance_adapter(layer=Layer.APP, ecosystem=Ecosystem.NPM)` applied to `class Foo: ...` yields `Foo` (identity). Test: `assert register_provenance_adapter(layer=Layer.APP, ecosystem=Ecosystem.NPM)(Foo) is Foo`. Catches `return None` and `return wrapper` mutants.
- [ ] **AC-6 — Duplicate key raises `RegistryError` at decoration time.** Two adapter classes decorated with the same `(layer, ecosystem)` pair: the SECOND decoration raises `RegistryError`. The message contains both colliding `module.qualname` strings (mirror `probes/registry.py:154-158`). Typed payload: `exc.key: ProvenanceAdapterId == (layer, ecosystem)`. Test asserts `exc_info.value.key == (Layer.APP, Ecosystem.NPM)` AND **both** the existing class's `__qualname__` substring (e.g. `"_FirstNpmAdapter"`) AND the duplicate class's `__qualname__` substring (e.g. `"_DuplicateNpmAdapter"`) appear in `str(exc_info.value)` — exact substring match, not a dot-count heuristic. Kills "message only carries the existing qualname" and "message only carries the duplicate qualname" mutants.
- [ ] **AC-7 — No instance construction at decoration time.** A test registers a class whose `__init__` raises `RuntimeError("must not be called")`; the decoration completes without raising. This is the BP-3 regression check — if the decorator ever calls `cls()`, this test fails loud.
- [ ] **AC-8 — No `isinstance` runtime contract guard.** A test registers a class with the wrong method-signature shape (right method names, wrong signatures) — decoration succeeds. Per ADR-0007 §Tradeoffs row 4: `Protocol.__runtime_checkable__` only checks method NAMES not signatures, so the runtime check would give false safety. The CI gate is `mypy --strict` at the registration site, not a runtime guard.
- [ ] **AC-9 — `provenance_registry_reset` autouse fixture.** A conftest-level autouse function-scoped fixture snapshots `_REGISTRY` pre-test (via `dict.copy()`) and restores it post-test. Located at `tests/unit/primitives/vuln_provenance/conftest.py` (mirrors Phase 2 `freshness` registry isolation per ADR-0007 §Consequences). A test that registers an adapter, then a second test that asserts `_REGISTRY == {}` both pass — proving isolation works.
- [ ] **AC-10 — Public surface export.** `src/codegenie/primitives/vuln_provenance/__init__.py` re-exports `Layer`, `Ecosystem`, `register_provenance_adapter`. `_REGISTRY` itself is module-private (leading underscore); tests reach it via the module path `from codegenie.primitives.vuln_provenance import registry as _registry_mod; _registry_mod._REGISTRY`.
- [ ] **AC-11 — TDD red test exists, committed, green.** `tests/unit/primitives/vuln_provenance/test_registry.py::test_duplicate_registration_raises_registry_error` was the first failing test; the impl makes it green.
- [ ] **AC-12 — Lint / type clean.** `ruff check`, `ruff format --check`, `mypy --strict` clean on `src/codegenie/primitives/vuln_provenance/registry.py`, `src/codegenie/primitives/vuln_provenance/__init__.py`, `tests/unit/primitives/vuln_provenance/test_registry.py`, `tests/unit/primitives/vuln_provenance/conftest.py`. `make lint-imports` green (no new LLM-SDK import path through the primitive — S1-06 fence still holds).

- [ ] **AC-13 — Decorator is keyword-only (signature contract).** `register_provenance_adapter(*, layer, ecosystem)` is invoked **only** via keyword arguments. Test `test_decorator_signature_is_keyword_only` asserts both: (a) `register_provenance_adapter(Layer.APP, Ecosystem.NPM)` (positional) raises `TypeError`; (b) `register_provenance_adapter(layer=Layer.APP, ecosystem=Ecosystem.NPM)` (keyword) succeeds. Kills a "drop the `*`" mutation that would silently land a positional-arg overload — every Phase 8+ plugin's adapter registration relies on the keyword form for readability and refactor-safety.

- [ ] **AC-14 — Distinct keys coexist.** Two adapter classes with different `(layer, ecosystem)` pairs register without collision; both lookups return their respective classes by identity. Test `test_distinct_keys_coexist` registers `(Layer.APP, Ecosystem.NPM)` and `(Layer.BASE_IMAGE, Ecosystem.APK)`, asserts `_REGISTRY[(Layer.APP, Ecosystem.NPM)] is _A`, `_REGISTRY[(Layer.BASE_IMAGE, Ecosystem.APK)] is _B`, AND `len(_REGISTRY) == 2`. Kills a hypothetical "_REGISTRY.clear() before assign" mutant where every new registration evicts the prior one — that mutant would pass AC-3/AC-4 individually but a multi-registration sweep (which the property test in S2-05 relies on) would silently produce a one-entry registry. Catches the regression at the unit boundary instead of waiting for S2-05's Hypothesis sweep.

## Implementation outline

1. Confirm `src/codegenie/primitives/vuln_provenance/` exists from Step 1 (S1-01 + S1-03 + S1-04); confirm `ProvenanceAdapterId` and `VulnProvenanceAdapter` Protocol + `RegistryError` import paths.
2. Create `src/codegenie/primitives/vuln_provenance/registry.py`:
   - Module docstring cites Phase 7 ADR-0007 § Consequences and names the four-precedent registry pattern (`probes/registry.py`, `indices/registry.py`, `depgraph/registry.py`, `plugins/registry.py`).
   - `from __future__ import annotations` + `from enum import StrEnum` + `TYPE_CHECKING` import for `VulnProvenanceAdapter`.
   - `class Layer(StrEnum)` + `class Ecosystem(StrEnum)` per AC-1 / AC-2 declaration order.
   - `_REGISTRY: Final[dict[ProvenanceAdapterId, type[VulnProvenanceAdapter]]] = {}`.
   - `def register_provenance_adapter(*, layer: Layer, ecosystem: Ecosystem)`:
     ```python
     def _wrap(cls: type[VulnProvenanceAdapter]) -> type[VulnProvenanceAdapter]:
         key: ProvenanceAdapterId = (layer, ecosystem)
         if key in _REGISTRY:
             existing = _REGISTRY[key]
             raise RegistryError.duplicate(
                 key=key,
                 existing_qualname=f"{existing.__module__}.{existing.__qualname__}",
                 duplicate_qualname=f"{cls.__module__}.{cls.__qualname__}",
             )
         _REGISTRY[key] = cls       # CLASS, NOT cls()
         return cls
     return _wrap
     ```
   - Resist the urge to inspect `cls.__init__` signature here (S2-02's `AdapterFactory` owns DI-aware kwargs). The decorator does ONE thing: collision check + assign + return.
3. Add `RegistryError.duplicate(*, key, existing_qualname, duplicate_qualname)` classmethod to the `RegistryError` shipped by S1-04 (if S1-04 left it as a plain `Exception` subclass, extend with a `.key: ProvenanceAdapterId` attribute and a classmethod constructor — small surgical edit; coordinate with S1-04 attempt log).
4. Extend `src/codegenie/primitives/vuln_provenance/__init__.py` to re-export `Layer`, `Ecosystem`, `register_provenance_adapter`.
5. Create `tests/unit/primitives/vuln_provenance/conftest.py` with the autouse `provenance_registry_reset` fixture:
   ```python
   import pytest
   from codegenie.primitives.vuln_provenance import registry as _registry_mod

   @pytest.fixture(autouse=True)
   def provenance_registry_reset() -> Generator[None, None, None]:
       snapshot = _registry_mod._REGISTRY.copy()
       try:
           _registry_mod._REGISTRY.clear()
           yield
       finally:
           _registry_mod._REGISTRY.clear()
           _registry_mod._REGISTRY.update(snapshot)
   ```
6. Write the red test first (`test_duplicate_registration_raises_registry_error`), watch it fail (likely `ImportError` on `register_provenance_adapter`), implement minimum, watch it pass. Add the rest of the TDD plan's tests in order.

## TDD plan — red / green / refactor

### Red

Test file path: `tests/unit/primitives/vuln_provenance/test_registry.py`

```python
from __future__ import annotations

import pytest

from codegenie.primitives.vuln_provenance import (
    Ecosystem,
    Layer,
    register_provenance_adapter,
)
from codegenie.primitives.vuln_provenance import registry as _registry_mod
from codegenie.primitives.vuln_provenance.errors import RegistryError


def test_duplicate_registration_raises_registry_error() -> None:
    """ADR-0007 §Consequences: duplicate (Layer, Ecosystem) → RegistryError at
    decoration time (plugin loader fast-fails at Supervisor startup).
    Both colliding module.qualname strings appear in the message."""

    @register_provenance_adapter(layer=Layer.APP, ecosystem=Ecosystem.NPM)
    class _FirstNpmAdapter:
        def attribute(self, cve_id, package_id, image_ref, sbom):  # type: ignore[no-untyped-def]
            ...
        def confidence(self):  # type: ignore[no-untyped-def]
            ...

    with pytest.raises(RegistryError) as exc_info:
        @register_provenance_adapter(layer=Layer.APP, ecosystem=Ecosystem.NPM)
        class _DuplicateNpmAdapter:
            def attribute(self, cve_id, package_id, image_ref, sbom):  # type: ignore[no-untyped-def]
                ...
            def confidence(self):  # type: ignore[no-untyped-def]
                ...

    assert exc_info.value.key == (Layer.APP, Ecosystem.NPM)
    assert "_FirstNpmAdapter" in str(exc_info.value)
    assert "_DuplicateNpmAdapter" in str(exc_info.value)
```

Why it fails: `register_provenance_adapter` doesn't exist yet — `ImportError` on the test's first import line.

### Green — minimal pass

- Create `registry.py` with `Layer`, `Ecosystem`, `_REGISTRY`, `register_provenance_adapter`.
- Decorator: collision check by key; raise `RegistryError.duplicate(...)`; else `_REGISTRY[key] = cls; return cls`.
- Wire `__init__.py` re-exports.
- Create the autouse `provenance_registry_reset` fixture in `conftest.py`.

### Required follow-on tests (one per AC; pin each with mutation-resistant assertions)

```python
def test_layer_enum_declaration_order() -> None:
    """AC-1 — declaration order is load-bearing for ADR-0006's dispatch tuple."""
    assert tuple(Layer) == (Layer.APP, Layer.BASE_IMAGE, Layer.RUNTIME)


def test_ecosystem_enum_declaration_order() -> None:
    """AC-2 — declaration order pins the Ecosystem-enum-sort iteration (S2-03 reads this)."""
    assert tuple(Ecosystem) == (
        Ecosystem.NPM, Ecosystem.YARN_BERRY, Ecosystem.PNPM,
        Ecosystem.APK, Ecosystem.DPKG, Ecosystem.RPM,
    )


def test_registry_stores_the_class_not_an_instance() -> None:
    """AC-4 — BP-3 regression check; the registry value IS the class (identity)."""
    @register_provenance_adapter(layer=Layer.APP, ecosystem=Ecosystem.NPM)
    class _Adapter:
        def attribute(self, *a, **kw):  # type: ignore[no-untyped-def]
            ...
        def confidence(self):  # type: ignore[no-untyped-def]
            ...
    assert _registry_mod._REGISTRY[(Layer.APP, Ecosystem.NPM)] is _Adapter


def test_decorator_returns_class_unchanged() -> None:
    """AC-5 — identity return (catches `return None` / `return wrapper` mutants)."""
    class _Adapter:
        def attribute(self, *a, **kw):  # type: ignore[no-untyped-def]
            ...
        def confidence(self):  # type: ignore[no-untyped-def]
            ...
    decorated = register_provenance_adapter(layer=Layer.BASE_IMAGE, ecosystem=Ecosystem.APK)(_Adapter)
    assert decorated is _Adapter


def test_no_instance_construction_at_decoration_time() -> None:
    """AC-7 — ADR-0007: 'no cls() at decoration time' (BP-3). If the decorator
    ever calls cls(), this __init__ raises and the test fails loud."""
    @register_provenance_adapter(layer=Layer.RUNTIME, ecosystem=Ecosystem.RPM)
    class _AdapterWithExplodingInit:
        def __init__(self) -> None:
            raise RuntimeError("decorator must not construct instances")
        def attribute(self, *a, **kw):  # type: ignore[no-untyped-def]
            ...
        def confidence(self):  # type: ignore[no-untyped-def]
            ...
    # No exception raised — decoration succeeded without calling __init__.
    assert _registry_mod._REGISTRY[(Layer.RUNTIME, Ecosystem.RPM)] is _AdapterWithExplodingInit


def test_registry_is_empty_at_test_start(  # demonstrates AC-9 isolation
) -> None:
    """AC-9 — autouse fixture clears the registry between tests."""
    assert _registry_mod._REGISTRY == {}


def test_registry_is_empty_again_after_other_test(  # paired with above; runs after
) -> None:
    """AC-9 — even after test_registry_stores_the_class_not_an_instance registered
    an adapter, this test sees an empty registry (proving fixture isolation works)."""
    assert _registry_mod._REGISTRY == {}


def test_decorator_signature_is_keyword_only() -> None:
    """AC-13 — decorator MUST be invoked with `*, layer, ecosystem` keywords.
    Catches a 'drop the `*`' mutation that would silently permit positional invocation."""

    class _Adapter:
        def attribute(self, *a, **kw):  # type: ignore[no-untyped-def]
            ...
        def confidence(self):  # type: ignore[no-untyped-def]
            ...

    with pytest.raises(TypeError):
        register_provenance_adapter(Layer.APP, Ecosystem.NPM)(_Adapter)  # type: ignore[misc]

    decorated = register_provenance_adapter(layer=Layer.APP, ecosystem=Ecosystem.NPM)(_Adapter)
    assert decorated is _Adapter


def test_distinct_keys_coexist() -> None:
    """AC-14 — two adapters under different keys coexist. Catches a hypothetical
    `_REGISTRY.clear(); _REGISTRY[key] = cls` mutant that would silently evict
    every prior registration (would pass AC-3/AC-4 individually but break S2-05's
    Hypothesis sweep)."""

    @register_provenance_adapter(layer=Layer.APP, ecosystem=Ecosystem.NPM)
    class _A:
        def attribute(self, *a, **kw):  # type: ignore[no-untyped-def]
            ...
        def confidence(self):  # type: ignore[no-untyped-def]
            ...

    @register_provenance_adapter(layer=Layer.BASE_IMAGE, ecosystem=Ecosystem.APK)
    class _B:
        def attribute(self, *a, **kw):  # type: ignore[no-untyped-def]
            ...
        def confidence(self):  # type: ignore[no-untyped-def]
            ...

    assert _registry_mod._REGISTRY[(Layer.APP, Ecosystem.NPM)] is _A
    assert _registry_mod._REGISTRY[(Layer.BASE_IMAGE, Ecosystem.APK)] is _B
    assert len(_registry_mod._REGISTRY) == 2
```

### Refactor

- Module docstring on `registry.py`: cite ADR-0007 § Consequences; name the four-precedent registry pattern; pin the rule-of-three deferral observation (now N=5 with this kernel).
- `RegistryError.duplicate` classmethod has its own docstring naming both `existing_qualname` and `duplicate_qualname` formatter expectations.
- `from __future__ import annotations` everywhere; `TYPE_CHECKING` import for `VulnProvenanceAdapter` to avoid a circular import (`protocols.py` may eventually want to import enums for typing).
- Inline comment on the `_REGISTRY[key] = cls` line: `# CLASS, NOT cls() — see ADR-0007 §Decision; BP-3 regression guard`.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/primitives/vuln_provenance/registry.py` | New module: `Layer`, `Ecosystem`, `_REGISTRY`, `@register_provenance_adapter`. |
| `src/codegenie/primitives/vuln_provenance/__init__.py` | Re-export `Layer`, `Ecosystem`, `register_provenance_adapter`. |
| `src/codegenie/primitives/vuln_provenance/errors.py` (extend) | Add `RegistryError.duplicate(*, key, existing_qualname, duplicate_qualname)` classmethod + `.key: ProvenanceAdapterId` typed attribute. |
| `tests/unit/primitives/vuln_provenance/__init__.py` | Test package marker (if not already shipped by Step 1). |
| `tests/unit/primitives/vuln_provenance/conftest.py` | Autouse `provenance_registry_reset` fixture. |
| `tests/unit/primitives/vuln_provenance/test_registry.py` | TDD red test + follow-on tests (one per AC). |

## Out of scope

- **`AdapterFactory` Protocol + DI-aware construction** — handled by **S2-02**. This story's decorator stores classes; instantiation is dispatch-time.
- **`_ADAPTER_DISPATCH_ORDER` tuple + `Ecosystem`-sorted iteration** — handled by **S2-03**. This story does NOT impose ordering; `_REGISTRY` is a plain dict.
- **`assemble_provenance(...)` free function** — handled by **S2-04**. This story ships no consumer of `_REGISTRY`.
- **Hypothesis property tests (50 registration-order permutations, idempotence)** — handled by **S2-05**. This story ships happy-path + collision + isolation unit tests only.
- **Plugin-load → adapter-registration → `assemble_provenance` integration test** — handled by S3-01 (red-first contract test for the npm adapter).
- **`isinstance(cls(), VulnProvenanceAdapter)` runtime guard** — explicitly NOT shipped per ADR-0007 §Tradeoffs row 4; `mypy --strict` is the CI gate.
- **Module-reload semantics** — re-importing a plugin module that calls `@register_provenance_adapter` raises `RegistryError` (the desired behavior — reload is developer-only; duplicate registration is correctly an error). No special-casing.

## Notes for the implementer

- **The decorator is intentionally tiny.** Three lines of behavior: collision-check, assign, return. Resist the urge to add `mypy`-style structural validation, logging, or `inspect.signature` calls — those concerns belong to S2-02's `AdapterFactory` (dispatch-time DI) and `mypy --strict` (CI-time type check).
- **`Layer` declaration order is load-bearing.** S2-03's `_ADAPTER_DISPATCH_ORDER` tuple iterates `Layer.APP → BASE_IMAGE → RUNTIME` in that order. Don't reorder the enum members.
- **`Ecosystem` declaration order is load-bearing.** S2-03 iterates intra-layer adapters in `Ecosystem`-enum-sorted order. The default Python enum sort is by declaration order (`tuple(Ecosystem)`); the AC-2 test pins this contract. S2-03 will write `sorted(..., key=lambda key: tuple(Ecosystem).index(key[1]))` or equivalent.
- **`RegistryError.duplicate` classmethod payload is load-bearing.** The loader (S8-03) and the supervisor's exit-code-4 formatter will read `exc.key` to print a structured diagnostic. Naming both `existing_qualname` and `duplicate_qualname` in the message is the operator-facing contract (mirror `probes/registry.py:154-158`).
- **Autouse fixture lives in conftest, not the test module.** Mirrors `tests/unit/depgraph/conftest.py` precedent. Function-scoped + autouse is the right combination — every test in the package sees a fresh `_REGISTRY` without explicit fixture parameters.
- **Do NOT add `unregister_for_tests()` to the registry module.** `indices/registry.py` ships that explicitly because production code registers into the default registry. In this phase, production registration is S3-03's `from .adapters import npm_provenance  # noqa: F401` import-line in the Phase 3 plugin's `api.py` — that's the only call site. Tests use the snapshot/restore fixture; no helper needed on the registry surface.
- **The "BP-3 regression guard" test (AC-7) is non-optional.** It's the only test that would catch a `_REGISTRY[key] = cls()` regression (constructing the instance at decoration time). Every Phase 8+ adapter relies on lazy construction; if a future PR accidentally re-introduces eager `cls()` calls, this test is the canary.
