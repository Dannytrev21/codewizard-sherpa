# Story S2-02 — `AdapterFactory` Protocol + DI kwarg vocabulary

**Status:** Done — HARDENED (validator 2026-07-25)
**Completed:** 2026-05-19
**Attempts:** 1
**Evidence:**
- Files: `src/codegenie/primitives/vuln_provenance/factory.py` (new), `src/codegenie/primitives/vuln_provenance/__init__.py`, `tests/unit/primitives/vuln_provenance/test_factory.py` (new), `tests/unit/primitives/vuln_provenance/test_types_dunder_all.py`
- Tests: `tests/unit/primitives/vuln_provenance/test_factory.py` — 10 tests, one+ per AC; `factory.py` 100% coverage
- Gates: `ruff check` / `ruff format` clean, `mypy --strict` clean, `lint-imports` 5/5 contracts KEPT
- Attempt log: none — story landed in a single commit; no multi-attempt debugging occurred
- Commit: `a6e7071 — feat(phase7/S2-02): GREEN — AdapterFactory Protocol + DI kwarg vocabulary`

## Validation notes

Retrospective four-critic validation on 2026-07-25 by `/phase-story-validator` (report: [`_validation/S2-02-adapter-factory-di-protocol.md`](_validation/S2-02-adapter-factory-di-protocol.md)). Verdict: **STRONG**. No blockers; all `harden`-severity findings resolved as either (a) Evidence-block corrections (missing attempt log, stale Refactor bullet) or (b) `Notes for the implementer` additions covering `**kwargs`/MRO/positional-only conventions, metamorphic-and-powerset test opportunities for the S2 family, and the "three parallel edit-sites" growth hazard that surfaces when the DI vocabulary needs to grow. Checked-off ACs are preserved — shipped evidence is authoritative (Rule 12).

**Step:** Step 2 — Registry kernel, `_ADAPTER_DISPATCH_ORDER`, `assemble_provenance` free function
**Effort:** S
**Depends on:** S2-01 (`Layer`, `Ecosystem`, `_REGISTRY`, `register_provenance_adapter`; `VulnProvenanceAdapter` Protocol from S1-04 transitively)
**ADRs honored:** Phase 7 ADR-0007 (registry stores classes — `AdapterFactory` is how dispatch-time construction happens with DI kwargs), Phase 7 ADR-0004 (vuln.provenance primitive home — Factory lives in the same primitive tree), production ADR-0031 (Plugin/Registry), production ADR-0033 (Domain modeling discipline — closed kwarg vocabulary is enum-shaped).

## Context

Phase 7 ADR-0007 stores adapter **classes** in `_REGISTRY` (S2-01) — but adapters need dependencies (`sbom_reader`, `logger`, `image_manifest_cache`). The `AdapterFactory` Protocol is how `assemble_provenance` (S2-04) hands those dependencies to an adapter at dispatch time. The factory inspects the adapter class's `__init__` signature, matches well-known kwarg names from a **closed vocabulary**, and constructs the instance — or falls back to `cls()` if the adapter declares no DI kwargs.

The closed kwarg set — `{sbom_reader, logger, image_manifest_cache}` — is the pinning of `phase-arch-design.md §Open questions §3` (and the answer to `High-level-impl.md §Step 2` line `well-known kwarg names {sbom_reader, logger, image_manifest_cache} (Phase 7 ADR-0010 draft; final names pinned here)`). Growing this set requires an ADR amendment — that's the load-bearing constraint. Adapters that need other dependencies must either declare them as well-known kwargs (and pay the ADR-amendment cost) or accept the default factory's empty-kwarg path.

**Scope reminder.** S2-02 ships ONLY: `AdapterFactory` Protocol + default factory implementation + the closed-vocabulary `_DI_KWARGS` constant + unit tests. The factory is *consumed* by S2-04's `assemble_provenance`; no consumer ships here.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design §3` — `VulnProvenanceAdapter` Protocol. The factory constructs instances of these types.
  - `../phase-arch-design.md §Component design §4` last bullet ("State: Adapters MAY hold construction-time state (`sbom_reader`, `logger`, `image_manifest_cache`); the `AdapterFactory` honors well-known DI names").
  - `../phase-arch-design.md §Component design §6` `assemble_provenance` line `adapter_factory: AdapterFactory | None = None` — the call site that consumes this story's output.
  - `../phase-arch-design.md §Open questions §3` — DI-kwarg vocabulary; this story is where it's pinned.
  - `../phase-arch-design.md §Design patterns applied` — Class-as-token + Factory pattern.
- **Phase ADRs:**
  - `../ADRs/0007-provenance-adapter-registry-stores-classes.md §Decision` — "`assemble_provenance(...)` accepts an optional `adapter_factory: AdapterFactory | None = None` parameter; the default factory inspects `cls.__init__`'s signature and passes a known closed set of DI kwargs … Adapters that need other dependencies must either declare them as well-known kwargs (ADR amendment to the closed set) or accept the default."
  - `../ADRs/0007-provenance-adapter-registry-stores-classes.md §Tradeoffs row 1` — closed DI-kwarg vocabulary is load-bearing; growing it is an ADR amendment.
  - `../ADRs/0007-provenance-adapter-registry-stores-classes.md §Consequences` rows for `AdapterFactory` + the well-known kwarg-set discipline.
- **Source design:** `../final-design.md §Synthesis ledger row 11 + departure #2` (registry stores classes; factory honors DI kwargs).
- **Existing code (precedent to mirror):**
  - `src/codegenie/depgraph/strategies.py` — adapter classes accept DI kwargs at construction; the `@register_dep_graph_strategy` precedent doesn't ship a `Factory` because depgraph strategies all have no-arg constructors. The Phase 7 factory is the next-step refinement.
  - `src/codegenie/probes/registry.py:sorted_for_dispatch` — closest precedent for "factory walks signature" reasoning (heaviness inspection); shape mirrored.
  - Python stdlib `inspect.signature` — the only stdlib API the default factory uses.

## Goal

Ship `src/codegenie/primitives/vuln_provenance/factory.py` containing: (1) a `@runtime_checkable` `AdapterFactory` Protocol with one method `__call__(self, cls: type[VulnProvenanceAdapter], /) -> VulnProvenanceAdapter`; (2) a module-level `_DI_KWARGS: Final[frozenset[str]] = frozenset({"sbom_reader", "logger", "image_manifest_cache"})` (the closed vocabulary); (3) a `DefaultAdapterFactory` callable class that inspects `cls.__init__`'s signature, matches declared parameters against `_DI_KWARGS`, and calls `cls(**matched_kwargs)`; (4) a module-level `default_adapter_factory` instance held against constructor DI dependencies it received itself; and (5) unit tests covering happy path, partial-kwarg adapters, no-kwarg adapters, and factory override for test isolation.

## Acceptance criteria

- [x] **AC-1 — `AdapterFactory` Protocol.** `src/codegenie/primitives/vuln_provenance/factory.py` exports a `@runtime_checkable` `Protocol` named `AdapterFactory` with **exactly one** non-dunder method: `__call__(self, cls: type[VulnProvenanceAdapter], /) -> VulnProvenanceAdapter`. The signature is positional-only (the `/`). Test asserts `{n for n in dir(AdapterFactory) if not n.startswith("_")} == set()` (no public attributes beyond dunders) AND `inspect.isfunction(AdapterFactory.__call__)`.
- [x] **AC-2 — `_DI_KWARGS` closed vocabulary.** Module-level `_DI_KWARGS: Final[frozenset[str]] = frozenset({"sbom_reader", "logger", "image_manifest_cache"})`. Test asserts `_DI_KWARGS == frozenset({"sbom_reader", "logger", "image_manifest_cache"})` (exact-set equality; catches additions and removals). Module docstring cites ADR-0007 §Decision and names "growing this set is an ADR amendment".
- [x] **AC-3 — `DefaultAdapterFactory` accepts the closed kwarg vocabulary at construction.** `class DefaultAdapterFactory:` with `__init__(self, *, sbom_reader: SbomReader | None = None, logger: Logger | None = None, image_manifest_cache: ImageManifestCache | None = None) -> None` (forward-referenced types from S1-05 / stdlib / Phase 2 image-digest cache; missing types may be `object` placeholders that S1-05 / Phase 2 fence-tests resolve via `mypy --strict`). The factory stores them in private attributes (`self._sbom_reader`, etc.).
- [x] **AC-4 — `DefaultAdapterFactory.__call__` matches `cls.__init__` against `_DI_KWARGS`.** Given `class _Adapter: def __init__(self, *, sbom_reader, logger): ...`, calling `factory(_Adapter)` invokes `_Adapter(sbom_reader=self._sbom_reader, logger=self._logger)` — only the kwargs the adapter declares are passed. Test asserts the constructed instance's attributes equal the factory's stored DI values.
- [x] **AC-5 — Adapter with no DI kwargs gets no kwargs.** Given `class _Adapter: def __init__(self): ...`, calling `factory(_Adapter)` invokes `_Adapter()` with NO kwargs (catches "passes everything always" mutant). Test: `_Adapter` declares `__init__(self) -> None`; factory call succeeds; no `TypeError`.
- [x] **AC-6 — Adapter declaring an unknown kwarg falls back.** Given `class _Adapter: def __init__(self, *, sbom_reader, unknown_kwarg=None): ...`, the factory passes ONLY `sbom_reader` (unknown is left unset — the adapter's default applies). The factory MUST NOT pass `unknown_kwarg=...` (it would smuggle dynamism past the closed vocabulary). Test asserts the adapter's `unknown_kwarg` attribute equals the adapter's declared default.
- [x] **AC-7 — `default_adapter_factory` module-level instance.** `default_adapter_factory: Final[AdapterFactory] = DefaultAdapterFactory()` is exported. All three DI dependencies default to `None` at the module-level instance — meaning real production code MUST pass an explicit factory with non-None deps. Test asserts `default_adapter_factory(_NoKwargAdapter)` works (no-op DI); asserts `default_adapter_factory(_RequiresSbomReaderAdapter)` raises a clear `TypeError` (or the adapter's own validation error) because `None` is passed.
- [x] **AC-8 — Factory is `@runtime_checkable` compatible.** `isinstance(DefaultAdapterFactory(), AdapterFactory) is True`; `isinstance(object(), AdapterFactory) is False`. Smoke test sufficient evidence the Protocol is correctly `@runtime_checkable`.
- [x] **AC-9 — Test substitution path.** A test defines a deterministic `class FixtureFactory: def __call__(self, cls): return cls(...)` that satisfies the `AdapterFactory` Protocol via duck typing; `isinstance(FixtureFactory(), AdapterFactory)` is True. This is the contract S2-04's `adapter_factory: AdapterFactory | None = None` parameter relies on for test isolation.
- [x] **AC-10 — TDD red test exists, committed, green.** `tests/unit/primitives/vuln_provenance/test_factory.py::test_default_factory_passes_only_declared_di_kwargs` was the first failing test; impl makes it green.
- [x] **AC-11 — Lint / type clean.** `ruff check`, `ruff format --check`, `mypy --strict` clean on `src/codegenie/primitives/vuln_provenance/factory.py` + the test module + the conftest. `make lint-imports` green.

## Implementation outline

1. Create `src/codegenie/primitives/vuln_provenance/factory.py`:
   - Module docstring cites ADR-0007 §Decision and §Tradeoffs row 1; names the closed-vocabulary discipline and the ADR-amendment cost of growing it.
   - `from __future__ import annotations` + `TYPE_CHECKING` imports for `SbomReader` (S1-05), `Logger` (stdlib), `ImageManifestCache` (Phase 2 ADR-0004 ctx-attr — may be `object` placeholder if Phase 2 ctx-cache isn't yet a typed module export).
   - `_DI_KWARGS: Final[frozenset[str]] = frozenset({"sbom_reader", "logger", "image_manifest_cache"})`.
   - `@runtime_checkable class AdapterFactory(Protocol)` with one method `__call__(self, cls, /) -> VulnProvenanceAdapter`.
   - `class DefaultAdapterFactory:` with `__init__(*, sbom_reader=None, logger=None, image_manifest_cache=None)` storing private attributes; `__call__(self, cls)`:
     ```python
     def __call__(self, cls: type[VulnProvenanceAdapter], /) -> VulnProvenanceAdapter:
         sig = inspect.signature(cls.__init__)
         declared = {p.name for p in sig.parameters.values() if p.name != "self"}
         passed: dict[str, object] = {}
         if "sbom_reader" in declared and "sbom_reader" in _DI_KWARGS:
             passed["sbom_reader"] = self._sbom_reader
         if "logger" in declared and "logger" in _DI_KWARGS:
             passed["logger"] = self._logger
         if "image_manifest_cache" in declared and "image_manifest_cache" in _DI_KWARGS:
             passed["image_manifest_cache"] = self._image_manifest_cache
         return cls(**passed)
     ```
   - `default_adapter_factory: Final[AdapterFactory] = DefaultAdapterFactory()` module-level — for tests that don't need real DI.
2. Extend `src/codegenie/primitives/vuln_provenance/__init__.py` to re-export `AdapterFactory`, `DefaultAdapterFactory`, `default_adapter_factory`.
3. Write the red test first; watch `ImportError`; implement minimum; watch green; add follow-on tests in order.

## TDD plan — red / green / refactor

### Red

Test file path: `tests/unit/primitives/vuln_provenance/test_factory.py`

```python
from __future__ import annotations

from codegenie.primitives.vuln_provenance.factory import DefaultAdapterFactory


def test_default_factory_passes_only_declared_di_kwargs() -> None:
    """ADR-0007 §Decision: factory inspects cls.__init__ and passes only the DI
    kwargs the adapter declares. Closed vocabulary {sbom_reader, logger,
    image_manifest_cache} is the only thing the factory ever passes."""

    class _ProbeReader: ...
    class _ProbeLogger: ...

    reader = _ProbeReader()
    logger = _ProbeLogger()

    class _AdapterDeclaringTwo:
        def __init__(self, *, sbom_reader: object, logger: object) -> None:
            self.sbom_reader = sbom_reader
            self.logger = logger
            self.constructed = True

        def attribute(self, *a: object, **kw: object) -> object: ...  # type: ignore[empty-body]
        def confidence(self) -> object: ...  # type: ignore[empty-body]

    factory = DefaultAdapterFactory(sbom_reader=reader, logger=logger)
    adapter = factory(_AdapterDeclaringTwo)

    assert adapter.sbom_reader is reader
    assert adapter.logger is logger
    assert adapter.constructed is True
```

Why it fails: `factory.py` doesn't exist — `ImportError`.

### Green — minimal pass

Create `factory.py` with the shape in the implementation outline. Wire `__init__.py` re-exports. Watch the red test pass.

### Required follow-on tests (mutation-resistant; one per AC)

```python
import inspect
import pytest

from codegenie.primitives.vuln_provenance import (
    AdapterFactory,
    DefaultAdapterFactory,
    default_adapter_factory,
)
from codegenie.primitives.vuln_provenance import factory as _factory_mod


def test_di_kwargs_is_exact_closed_vocabulary() -> None:
    """AC-2 — exact-set equality (catches additions and removals).
    Growing this set is an ADR amendment per ADR-0007 §Tradeoffs row 1."""
    assert _factory_mod._DI_KWARGS == frozenset({"sbom_reader", "logger", "image_manifest_cache"})


def test_adapter_factory_protocol_surface() -> None:
    """AC-1 — Protocol has exactly __call__ (no other public attrs)."""
    public = {n for n in dir(AdapterFactory) if not n.startswith("_")}
    assert public == set()
    # __call__ is a function on the Protocol body:
    assert inspect.isfunction(AdapterFactory.__call__)


def test_adapter_with_no_kwargs_constructed_cleanly() -> None:
    """AC-5 — bare __init__(self) adapter gets cls() — catches 'passes everything' mutant."""
    class _NoKwargAdapter:
        def __init__(self) -> None:
            self.constructed = True
        def attribute(self, *a, **kw):  # type: ignore[no-untyped-def]
            ...
        def confidence(self):  # type: ignore[no-untyped-def]
            ...
    factory = DefaultAdapterFactory()
    a = factory(_NoKwargAdapter)
    assert a.constructed is True


def test_adapter_declaring_unknown_kwarg_is_not_passed_it() -> None:
    """AC-6 — unknown kwarg names are NEVER passed (closed vocabulary discipline)."""
    sentinel = object()
    class _AdapterWithUnknown:
        def __init__(self, *, sbom_reader: object, unknown_kwarg: object = "default") -> None:
            self.sbom_reader = sbom_reader
            self.unknown_kwarg = unknown_kwarg
        def attribute(self, *a, **kw):  # type: ignore[no-untyped-def]
            ...
        def confidence(self):  # type: ignore[no-untyped-def]
            ...
    factory = DefaultAdapterFactory(sbom_reader=sentinel)
    a = factory(_AdapterWithUnknown)
    assert a.sbom_reader is sentinel
    assert a.unknown_kwarg == "default"  # adapter's declared default — factory did NOT pass it


def test_default_adapter_factory_module_singleton_works_for_no_kwarg_adapters() -> None:
    """AC-7 — module-level default_adapter_factory has all-None DI; works for no-kwarg adapters."""
    class _NoKwargAdapter:
        def __init__(self) -> None:
            self.ok = True
        def attribute(self, *a, **kw):  # type: ignore[no-untyped-def]
            ...
        def confidence(self):  # type: ignore[no-untyped-def]
            ...
    a = default_adapter_factory(_NoKwargAdapter)
    assert a.ok is True


def test_runtime_checkable_protocol_smoke() -> None:
    """AC-8 — runtime-checkable AdapterFactory Protocol; downstream S2-04 relies on isinstance."""
    assert isinstance(DefaultAdapterFactory(), AdapterFactory) is True
    assert isinstance(object(), AdapterFactory) is False


def test_test_substitute_factory_satisfies_protocol_via_duck_typing() -> None:
    """AC-9 — S2-04's `adapter_factory: AdapterFactory | None` param relies on this contract."""
    class _FixtureFactory:
        def __call__(self, cls, /):  # type: ignore[no-untyped-def]
            return cls()
    assert isinstance(_FixtureFactory(), AdapterFactory)
```

### Refactor

- **Deviation accepted (validator 2026-07-25):** the private DI attributes on `DefaultAdapterFactory` stay typed `object | None` — S1-05 shipped `SyftSbom` models, not a `SbomReader` port; the module docstring commits to `object | None` on principle (the factory is a pure pass-through that never invokes a dependency). Introducing a concrete `SbomReader` Protocol is out of scope until a consumer needs one, at which point `mypy --strict` at the adapter's own `__init__` will enforce the real type where it's actually used.
- Inline comment on the closed-vocabulary iteration: `# iterate _DI_KWARGS (the closed set) → membership check IS the vocabulary — a name outside the set is structurally unreachable (ADR-0007 §Tradeoffs row 1)`.
- Module docstring is the canonical document for "how to grow the DI vocabulary": "(1) propose an ADR amendment to 0007's closed set; (2) extend `_DI_KWARGS`; (3) extend `DefaultAdapterFactory.__init__` **and the `available` mapping in `__call__`**; (4) update this docstring; (5) update the ADR's §Consequences." (See DP-1 in the validation report — this is currently a three-parallel-edit-site pattern.)

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/primitives/vuln_provenance/factory.py` | New: `AdapterFactory` Protocol, `_DI_KWARGS`, `DefaultAdapterFactory`, `default_adapter_factory`. |
| `src/codegenie/primitives/vuln_provenance/__init__.py` (extend) | Re-export `AdapterFactory`, `DefaultAdapterFactory`, `default_adapter_factory`. |
| `tests/unit/primitives/vuln_provenance/test_factory.py` | TDD red test + follow-on tests. |

## Out of scope

- **`_REGISTRY` shape and decorator** — owned by **S2-01**.
- **`_ADAPTER_DISPATCH_ORDER` tuple + Ecosystem-sorted iteration** — owned by **S2-03**.
- **`assemble_provenance(...)` free function** — owned by **S2-04**. The factory is a *parameter* to that function, not the function itself.
- **Concrete adapter implementations** — owned by Step 3 (`NpmVulnProvenanceAdapter`) and Step 4 (`Alpine` + `Distroless`).
- **Real `SbomReader` / `ImageManifestCache` types** — S1-05 (sbom reader) and Phase 2 ADR-0004 (image-digest-resolver ctx-attr) are already shipped; this story imports them under `TYPE_CHECKING` only. The factory itself doesn't construct or consume them — it just passes them through.
- **Growing the closed DI vocabulary** — requires an ADR amendment to Phase 7 ADR-0007. Not a story-level concern.
- **Async factory (`async __call__`)** — explicitly NOT shipped. The factory constructs at dispatch time inside `assemble_provenance`, which is synchronous (per `final-design.md §Component design §6` — the assembly itself is < 1 ms; adapter calls dominate). If a future adapter requires async construction, an ADR amendment is the path.

## Notes for the implementer

- **The closed-vocabulary discipline is the entire point of this story.** Without `_DI_KWARGS` membership-check, the factory could "helpfully" pass any kwarg with a matching name to any adapter — and the codebase would silently accumulate undocumented DI kwargs. The double-check (`"name" in declared AND "name" in _DI_KWARGS`) is the load-bearing assertion.
- **`@runtime_checkable` on `AdapterFactory` is cheap and load-bearing.** S2-04's `adapter_factory: AdapterFactory | None = None` parameter relies on `isinstance(factory, AdapterFactory)` for fixture-substitution support. The Protocol has one method (`__call__`); the runtime check is negligible.
- **The factory does NOT validate the constructed adapter's Protocol conformance.** Per ADR-0007 §Tradeoffs row 4: `Protocol.__runtime_checkable__` only checks method NAMES not signatures. The CI gate is `mypy --strict` at the registration site (the `cls: type[VulnProvenanceAdapter]` parameter of `@register_provenance_adapter`'s `_wrap` from S2-01). If a future adapter has wrong method signatures, `mypy --strict` catches it before `inspect.signature` ever runs.
- **`default_adapter_factory` with all-None DI is intentional.** Production code path is: `Supervisor` constructs a real `DefaultAdapterFactory(sbom_reader=..., logger=..., image_manifest_cache=...)` and passes it to `assemble_provenance(..., adapter_factory=factory)`. The module-level singleton is for unit-test convenience and for adapters that genuinely need no dependencies (rare — even `NpmVulnProvenanceAdapter` will want a logger).
- **The `inspect.signature` cost is paid once per `assemble_provenance` call per non-matching adapter.** S2-04's perf envelope is p99 ≤ 50 ms uncached; `inspect.signature` is sub-100 µs per adapter — negligible. Don't cache the signature inspection; the adapter classes are stable across a process lifetime, but caching adds complexity for no measurable win.
- **Resist adding `register_adapter_factory` or `set_default_adapter_factory`.** Mutation of the module-level singleton is the toolkit's "side effects at module import time" anti-pattern. S2-04's `adapter_factory: AdapterFactory | None = None` parameter is the substitution seam — caller injects, factory is local.

### Notes carried forward from validator 2026-07-25

Adapter-signature conventions that the closed-vocabulary discipline relies on but the current AC set does not pin. Follow-on adapter stories (S3-01, S3-02, S4-02, S4-03) should treat these as house rules:

- **Adapters declaring `**kwargs` receive NO DI.** `inspect.signature` maps `**kwargs` under key `"kwargs"`, so no `_DI_KWARGS` name matches. This is correct (closed vocabulary wins), but the convention is: adapters that want DI MUST declare each kwarg explicitly.
- **DI kwargs MUST be keyword-accessible (declared after `*,` or as ordinary named params).** A positional-only signature like `def __init__(self, sbom_reader, /)` would `TypeError` at `cls(**kwargs)`. All shipped and planned adapters use the `*,` convention.
- **Inherited `__init__` via MRO is honored.** A subclass that doesn't override `__init__` inherits the parent's DI declarations — the factory injects the parent's declared kwargs into the subclass. Correct today; document at the point a real adapter hierarchy emerges.

Test-hardening opportunities for the S2 story family (S2-03, S2-04) — not required for S2-02 since it shipped GREEN with 100% coverage:

- **Positional-only `/` marker check.** Assert `inspect.signature(AdapterFactory.__call__).parameters["cls"].kind is inspect.Parameter.POSITIONAL_ONLY`. The `/` is load-bearing for future keyword-collision immunity.
- **Metamorphic — no aliasing / no cached state.** Two `factory(_SameClass)` calls MUST return two distinct instances. Would kill a memoizing-mutant.
- **Powerset property test** over `{sbom_reader, logger, image_manifest_cache}` — synthesize an adapter per subset, assert received keys equal the subset. Currently four of the eight subsets are unexercised.
- **All-positional adapter fixture.** `def __init__(self, sbom_reader, logger, image_manifest_cache):` (no `*`) works by Python's keyword-to-positional binding; pin it so future refactors can't regress silently.

Growth-hazard note (design-patterns critic DP-1):

- **Growing `_DI_KWARGS` today requires editing three parallel sites** — the frozenset, `DefaultAdapterFactory.__init__` params, and the `available` dict in `__call__`. Rule 2 says three sites is fine; Rule of three says when the *third* new DI kwarg lands, elevate to a `DIBundle` dataclass (or `TypedDict`) so growth becomes single-edit. Not premature-abstraction to signal; premature-abstraction to fix before a real third consumer exists.
