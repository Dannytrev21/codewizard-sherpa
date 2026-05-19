# ADR-0007: `@register_provenance_adapter` stores adapter classes, not instances

**Status:** Accepted
**Date:** 2026-05-19
**Tags:** di · registry · open-closed · critic-bp3 · adr-0032
**Related:** [0006](0006-adapter-dispatch-explicit-final-tuple.md), [0004](0004-vuln-provenance-primitive-home.md), [production ADR-0032](../../../production/adrs/0032-dep-graph-adapter-protocol.md), [production ADR-0038](../../../production/adrs/0038-vulnerability-provenance-attribution.md), [Phase 3 ADR-0010](../../03-vuln-deterministic-recipe/ADRs/0010-domain-modeling-discipline-scope-sum-type-and-newtypes.md)

## Context

Best-practices' lens design for `@register_provenance_adapter` called `cls()` at decorator-application time and stored the resulting **instance** in the registry. The critic landed BP-3 against this: constructing an instance at decorator time forces every adapter to have a no-arg constructor and forbids constructor injection — but [production ADR-0032](../../../production/adrs/0032-dep-graph-adapter-protocol.md) (the precedent for adapter protocols) and ADR-0031 want adapters to receive dependencies (e.g., an SBOM reader, a logger, an image-manifest cache). Storing instances at decorator time also performs the worst possible work at the worst possible time: every plugin module's import becomes load-bearing because every adapter's `__init__` runs then.

`final-design.md §Synthesis ledger departure #2` and `final-design.md §Component design §3` are explicit: the registry stores **classes**, not instances. Construction happens lazily in `assemble_provenance`, with DI-aware kwargs honored by an `AdapterFactory`.

Mirrors how the Phase 3 `RecipeEngine` registry (Phase 3 ADR-0009) and the `@register_dep_graph_strategy` registry handle adapter contribution.

## Options considered

- **Option A — Store instances at decorator time (`_REGISTRY[key] = cls()`).** Best-practices' original position. **Pattern:** Singleton-at-import. Forces no-arg `__init__`; runs work at import; DI-hostile; "construct at the worst time" anti-pattern.
- **Option B — Store classes; consumers construct on every call (`_REGISTRY[key] = cls; adapter = cls()` at each `attribute()` call site).** **Pattern:** Class-as-token. Defers construction to call time; allows DI; trivial cost.
- **Option C — Store classes plus a separate `AdapterFactory` Protocol that handles DI kwargs (`sbom_reader`, `logger`, `image_manifest_cache`).** **Pattern:** Class-as-token + Factory. The factory honors well-known DI kwarg names if the adapter's `__init__` declares them; otherwise plain `cls()`.

## Decision

Adopt **Option C.** `_REGISTRY: Final[dict[ProvenanceAdapterId, type[VulnProvenanceAdapter]]] = {}` stores **classes**. `@register_provenance_adapter(*, layer, ecosystem)` writes `_REGISTRY[(layer, ecosystem)] = cls` — no instance construction at import time. `assemble_provenance(...)` accepts an optional `adapter_factory: AdapterFactory | None = None` parameter; the default factory inspects `cls.__init__`'s signature and passes a known closed set of DI kwargs (`sbom_reader`, `logger`, `image_manifest_cache`) if the adapter declares them. Otherwise it falls back to `cls()`. Adapters that need other dependencies must either declare them as well-known kwargs (ADR amendment to the closed set) or accept the default. The factory is overridable for test isolation.

## Tradeoffs

| Gain | Cost |
|---|---|
| Adapters use constructor injection — `sbom_reader`, `logger`, `image_manifest_cache` are passed in at dispatch time, not pulled from globals | The closed DI-kwarg vocabulary (`sbom_reader`, `logger`, `image_manifest_cache`) is load-bearing across all adapters; growing the vocabulary requires an ADR amendment |
| Module import is fast: only `_REGISTRY[key] = cls` runs at import; no `__init__` work — fixes critic BP-3's "worst time to do work" complaint | Per-call adapter construction (a few `__init__` calls per `assemble_provenance`) is a small cost — measured ≤ 1 ms per non-matching adapter; acceptable per the perf envelope (≤ 50 ms uncached overall) |
| Test isolation is clean: a pytest fixture snapshots and restores `_REGISTRY` per test; the `adapter_factory` parameter allows substituting a deterministic fixture factory in tests | The factory parameter adds optional complexity at the call site; resolved by defaulting to the production factory |
| `isinstance(cls(), VulnProvenanceAdapter)` runtime check at decorator time (best-practices' approach) is eliminated — Protocols' `@runtime_checkable` only checks method names, not signatures, so the check gave false safety. Synthesis relies on `mypy --strict` at registration site instead | Without the runtime check, a mis-typed adapter that has the right method names but wrong signatures lands in the registry and fails at call time. Mitigated: `mypy --strict` is the CI gate; the failure mode is loud (typed `ValidationError` or `TypeError`), not silent |
| Mirrors the established pattern from Phase 3 `RecipeEngine` registry, `@register_dep_graph_strategy`, `@register_signal_kind` — engineers read four examples and know the shape | One more example to keep consistent; the convention is now a load-bearing repository pattern |

## Pattern fit

Implements **Plugin / Registry** ([production ADR-0031](../../../production/adrs/0031-plugin-architecture.md)) plus **Class-as-token + Factory** (toolkit §Composition / coupling — Dependency injection via factory): the registry holds types, not instances; the factory constructs at dispatch time with the dependencies the call site has. Also instantiates **Lazy construction** — work is deferred from import time to call time, where context (the workflow's `sbom_reader`, `logger`) is available. Mirrors [production ADR-0032](../../../production/adrs/0032-dep-graph-adapter-protocol.md)'s adapter-protocol shape verbatim plus the lazy-construction discipline.

## Consequences

- `_REGISTRY: Final[dict[ProvenanceAdapterId, type[VulnProvenanceAdapter]]] = {}` lives in `src/codegenie/primitives/vuln_provenance/registry.py`.
- `@register_provenance_adapter(*, layer: Layer, ecosystem: Ecosystem)` writes `_REGISTRY[key] = cls` (no `cls()` call). Duplicate registration raises `RegistryError` at import time.
- `AdapterFactory` Protocol lives next to the registry; its default implementation inspects `cls.__init__.__annotations__` and matches well-known kwarg names from the closed set.
- Adapter `__init__` signatures may declare any subset of `{sbom_reader, logger, image_manifest_cache}` as kwargs; the factory passes what the adapter requests. **The closed kwarg set is an additive enum-shaped vocabulary**; growing it requires an ADR amendment.
- A pytest fixture (`tests/conftest.py` for the primitive tree) snapshots `_REGISTRY` per test and restores it on teardown — test isolation pattern mirrors Phase 2's `@register_index_freshness_check` fixture.
- `tests/unit/primitives/vuln_provenance/test_registry.py` asserts: duplicate registration raises `RegistryError`; non-conforming class registration is rejected by `mypy --strict` at type-check time; lookup by `(Layer, Ecosystem)` works; the registry is empty after fixture teardown.
- Integration test `tests/integration/test_provenance_assembly_via_plugins.py` proves the full plugin-load → adapter-registration → `assemble_provenance(...)` → typed-result path with both Phase 3 and Phase 7 plugins loaded.
- The performance-first adapter Protocol extension with `cost_band + applies_when` ([critic Perf-5]) is **structurally closed off**: the registry stores plain `type[VulnProvenanceAdapter]` and `assemble_provenance` does not inspect `cost_band` or `applies_when`. Adding them would require editing the Protocol — which would be a kernel-contract amendment per ADR-0039.

## Reversibility

**Medium.** The "classes not instances" decision is internal to the registry module and could be reversed by changing `_REGISTRY` to store instances — but every adapter would need a no-arg constructor migration, and the DI-friendly contract would break for every adapter currently using it. The closed DI-kwarg vocabulary is harder to reverse: once Phase 8+ adapters depend on the set, removing a name forces an ADR amendment plus consumer migration.

## Evidence / sources

- `../final-design.md §Synthesis ledger row 11 (score 14/15) + departure #2`, §Component design §3 (registry stores classes)
- `../phase-arch-design.md §Component design §4` (`@register_provenance_adapter` + `_REGISTRY`), §Component design §3 (`VulnProvenanceAdapter` Protocol)
- `../critique.md §Attacks on the best-practices design §3` (BP-3 — `cls()` at decorator time is DI-hostile), §Pattern claims that don't survive scrutiny (Protocol misused as a contract guard)
- [production ADR-0032 — DepGraphAdapter Protocol](../../../production/adrs/0032-dep-graph-adapter-protocol.md)
- [production ADR-0031 — Plugin architecture](../../../production/adrs/0031-plugin-architecture.md)
- [Phase 3 ADR-0010 — Domain modeling discipline](../../03-vuln-deterministic-recipe/ADRs/0010-domain-modeling-discipline-scope-sum-type-and-newtypes.md)
