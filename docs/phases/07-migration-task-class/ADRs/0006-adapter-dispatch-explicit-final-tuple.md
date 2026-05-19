# ADR-0006: Adapter dispatch order is an explicit `Final` tuple, not implicit `dict.items()` iteration

**Status:** Accepted
**Date:** 2026-05-19
**Tags:** strategy-via-data · determinism · critic-bp1 · final-tuple
**Related:** [0007](0007-provenance-adapter-registry-stores-classes.md), [0004](0004-vuln-provenance-primitive-home.md), [production ADR-0033](../../../production/adrs/0033-domain-modeling-discipline.md), [production ADR-0038](../../../production/adrs/0038-vulnerability-provenance-attribution.md)

## Context

[Production ADR-0038](../../../production/adrs/0038-vulnerability-provenance-attribution.md) defers the adapter-chain-assembly policy question. The three lens designs answered it differently:

- **Performance-first** proposed a `VulnProvenanceChainAssembler` class with runtime `confidence × cost_band × applies_when` ordering — and admitted in the same paragraph that adding a new adapter family requires editing the class. CoR claim, Strategy reality.
- **Security-first** proposed a `chain.py` class with deterministic order plus a `SbomVerifier` cross-check. Over-engineered for two adapters.
- **Best-practices** proposed a free function `assemble_provenance(...)` that walked `registry.items()` — and **acknowledged in Acknowledged blind spots #5** that "'declared order' semantics depend on `dict` insertion order." That is a load-bearing global-state ordering invariant smuggled in via implementation detail. The order an adapter registers is the order plugins import, which depends on plugin-loader iteration order, which depends on filesystem ordering or `sorted()` discipline neither of which is specified. The critic landed BP-1 hard.

`final-design.md §Synthesis ledger departure #1` and §Synthesis ledger row 13 (score **15/15**) lock the answer: dispatch order is **explicit data**, declared in code as a module-level `Final` tuple, decoupled from registration order.

## Options considered

- **Option A — Runtime sort by `confidence × cost_band × applies_when`.** Performance-first. **Pattern:** Strategy with runtime ordering. Extends the adapter `Protocol` with two new fields; adding `RhelVulnProvenanceAdapter` requires editing the chain assembler.
- **Option B — Implicit `for k, v in registry.items()` iteration.** Best-practices. **Pattern:** Implicit-order-as-policy. Smuggles `dict` insertion order (which is plugin-import order) as the dispatch policy.
- **Option C — Module-level `Final` tuple `_ADAPTER_DISPATCH_ORDER` declaring the layer-set walk order; within a layer-set, iterate in `Ecosystem`-enum-sorted order.** **Pattern:** Strategy via data — data declares policy; code reads it.

## Decision

Adopt **Option C.** `src/codegenie/primitives/vuln_provenance/assembly.py` declares at module top:

```python
_ADAPTER_DISPATCH_ORDER: Final[tuple[tuple[Layer, ...], ...]] = (
    (Layer.APP,),          # app-layer adapters first
    (Layer.BASE_IMAGE,),   # then base-image adapters
    (Layer.RUNTIME,),      # then runtime-bundled adapters
)
```

`assemble_provenance(...)` walks `_ADAPTER_DISPATCH_ORDER`; within each layer-set, it iterates the registry in `Ecosystem`-enum-sorted order (not `dict.items()` order). Adding a new `Layer` family (e.g., `Layer.SIDECAR`) requires touching this tuple — explicit, ADR-worthy. Adding a new `Ecosystem` to an existing layer is free (registry-only). **Registration order is not load-bearing.**

## Tradeoffs

| Gain | Cost |
|---|---|
| Closes critic BP-1: registration order, plugin-import order, and filesystem iteration order are no longer load-bearing for routing | Adding a new `Layer.SIDECAR` (or similar) is genuinely cross-cutting and requires touching the tuple + an ADR — slightly more friction than "just register an adapter" |
| Operators predict behavior by reading **one tuple** of three rows; no DSL, no class hierarchy, no runtime sort | The tuple is hardcoded in the assembly module; rebuilding the dispatch order at runtime (e.g., per-CVE-class — performance's `[P-v33]`) is rejected. Acceptable per critic ("premature pluggability") |
| A property test (`tests/property/vuln_provenance/test_dispatch_order_invariant.py`) shuffles registration order across 50 permutations and asserts `assemble_provenance` result is byte-identical — locks the discipline at the property level | The property test is non-trivial (Hypothesis-driven) but is high-signal; the test is on the load-bearing roadmap-coherence path |
| Within a layer, `Ecosystem`-enum-sorted order is deterministic across runs (no `set` or `dict.items()` order) — operators reason about polyglot tiebreakers by reading the `Ecosystem` enum definition | Adding a new `Ecosystem` value re-orders the within-layer iteration if it sorts before existing values; mitigated by the practical observation that polyglot tiebreakers are rare and the property test pins the order |
| Fits **Strategy via data** (toolkit) — data declares policy, code reads it; no `if/elif` branches on layer | One extra indirection: the dispatch loop walks two levels (layer-set, then within-layer); slightly harder to single-step in a debugger than a flat loop |

## Pattern fit

Implements **Strategy via data** (toolkit §Behavioral — Strategy expressed as a typed table, not a parallel class hierarchy): the dispatch policy is a typed `Final` tuple iterated at one call site; new policies are data additions, not code branches. Also instantiates **Final-tuple marker catalog** — the codebase's existing pattern (`_GENERATOR_HEADER_MARKERS`, `_REFLECTION_QUERIES`, `_LOCKFILE_PRECEDENCE`) used for similar dispatch tables. Newtype + sum-type discipline per [production ADR-0033](../../../production/adrs/0033-domain-modeling-discipline.md).

## Consequences

- `_ADAPTER_DISPATCH_ORDER: Final[tuple[tuple[Layer, ...], ...]]` is the module-level constant in `assembly.py`. Any change requires an ADR amendment.
- The `(Layer.RUNTIME,)` row is reserved (Phase 7 ships no runtime adapter). First runtime adapter (JRE-bundled, future phase) exercises it; Phase 7 includes a property test asserting the empty runtime layer behaves correctly.
- Within-layer iteration is `sorted(adapters_for_layer, key=lambda a: a.ecosystem)` — explicit, by `Ecosystem` enum value.
- `assemble_provenance` uses `match`/`assert_never` on `(app_result, base_result)` (critic BP-4) — no `if r.kind in {"app_direct", "app_transitive", ...}` string-set comparisons.
- Property test `test_dispatch_order_invariant.py` shuffles registration order across 50 permutations and asserts byte-identical results.
- Property test `test_both_invariant.py` asserts that for any `(AppKind, BaseKind)` pair where both are non-`Unknown`, `assemble_provenance` returns `Both(app_record, base_record)` with no recursion.
- Adding a new `Layer` value to the tuple is an ADR-worthy event; the assembly module's docstring lists this as the extension protocol.
- Performance-first's `[P-v9]` adapter Protocol extension with `cost_band + applies_when` is **rejected as kernel-contract drift**; see [0007](0007-provenance-adapter-registry-stores-classes.md) for the registry-side discipline.

## Reversibility

**Medium.** The constant's name (`_ADAPTER_DISPATCH_ORDER`) and shape are internal to the assembly module; changing the shape (e.g., adding per-CVE-class dispatch) is one file's change, plus a property test update. However, downstream consumers (Phase 8's Planner) read `assemble_provenance` outputs without caring about the dispatch order itself, so the shape change does not propagate. The discipline of "registration order is not load-bearing" is what's truly hard to reverse — operators would have to be re-trained, and a regression that re-introduced implicit ordering would be a silent correctness bug.

## Evidence / sources

- `../final-design.md §Lens summary` (non-obvious choice #2), §Synthesis ledger row 6 + row 13 (score 15/15), §Departures from all three inputs #1
- `../phase-arch-design.md §Component design §5` (`_ADAPTER_DISPATCH_ORDER`), §Component design §6 (`assemble_provenance(...)`)
- `../critique.md §Attacks on the best-practices design §1` (BP-1 — `dict.items()` smuggles registration order), §Anti-patterns from the toolkit's "flag on sight" list (Stringly-typed identifiers, Premature pluggability)
- [production ADR-0038 — Vulnerability provenance attribution](../../../production/adrs/0038-vulnerability-provenance-attribution.md)
- [production ADR-0033 — Domain modeling discipline](../../../production/adrs/0033-domain-modeling-discipline.md)
