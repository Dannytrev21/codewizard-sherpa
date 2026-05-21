# ADR-0009: A ConcreteResolution → BundleResolution adapter bridges the resolver and the Bundle builder

**Status:** Accepted
**Date:** 2026-05-21
**Tags:** Adapter pattern · fail-loud · type-system bridging
**Related:** ADR-0001, [production ADR-0029](../../../production/adrs/0029-task-class-context-manifests.md), [production ADR-0030](../../../production/adrs/0030-graph-aware-context-queries.md), [production ADR-0031](../../../production/adrs/0031-plugin-architecture.md), [production ADR-0043](../../../production/adrs/0043-extension-by-addition-means-no-silent-edits.md)

## Context

The Supervisor must turn a resolved plugin into a Context Bundle. `final-design.md` §BundleBuilder calls this "a *thin call* into the shipped builder" — "the resolver already returns `composed_adapters`/`composed_dispatch` pre-merged."

This is **wrong against the codebase** — see [phase-arch-design.md §Gap 2](../phase-arch-design.md#gap-2--concreteresolution-does-not-structurally-satisfy-bundlebuilderbuilds-input-protocol). The shipped `BundleBuilder.build(resolution: BundleResolution, ...)` requires a `BundleResolution` Protocol with `composed_tccm: TCCM` (the rich `codegenie.plugins.tccm.TCCM` with `must_read`/`should_read`/`may_read` bands) and `composed_dispatch: Mapping[PrimitiveName, AdapterDispatch]` (async **callables**). The shipped `resolver.resolve` returns `ConcreteResolution` with `composed_tccm: ComposedTccm` (a documented *placeholder* with only `provides`/`requires`) and `composed_adapters: dict[PrimitiveName, Adapter]` (**objects**, not callables). Three concrete mismatches: `ComposedTccm` ≠ `TCCM`; `composed_adapters` ≠ `composed_dispatch` (field name *and* value type differ); and `ComposedTccm` has no `must_read` band at all, so a "thin call" would build an empty Bundle. The two types do not structurally line up — and reusing the shipped `BundleBuilder` is non-negotiable (commitment §5 forbids forking a tested public component).

## Options considered

- **Option A — A `ConcreteResolution → BundleResolution` adapter component (`codegenie.supervisor.bundle_resolution`).** A first-class, named, tested component: `to_bundle_resolution(resolution: ConcreteResolution) -> ResolvedBundleInput`. **Pattern:** Adapter pattern — wraps an incompatible interface to match the one the client (`BundleBuilder.build`) expects.
- **Option B — Treat the mismatch as a footnote; have the `build_bundle` node inline the conversion.** **Pattern:** none — an inline, untested transform buried in a node; the type mismatch the synthesis under-stated stays under-stated; no clean place to fail loud on the placeholder.
- **Option C — Fork the `BundleBuilder` so it accepts `ConcreteResolution` directly.** **Pattern:** none — forks a shipped, tested public component; a silent semantic fork commitment §5 and Rule 11 forbid; the critic [proved](../critique.md#attacks-on-the-best-practices-design) the "build a second builder" proposals mis-modeled the resolver.

## Decision

Phase 8 adds **Component C2 — `codegenie.supervisor.bundle_resolution`** — a first-class `ConcreteResolution → BundleResolution` **Adapter**. `to_bundle_resolution` (a) maps each `Adapter` object in `composed_adapters` to its primitive-method callable to satisfy `composed_dispatch`; (b) consumes `ConcreteResolution.composed_tccm` as the rich `TCCM` *once the resolver hands the real `TCCM`*; (c) raises a typed `ResolverTccmPlaceholder` error — naming S3-01 as the prerequisite — if it still receives the `ComposedTccm` placeholder. The shipped `BundleBuilder` is reused unchanged; the adapter is the only new type at that boundary.

## Tradeoffs

| Gain | Cost |
|---|---|
| The shipped, tested `BundleBuilder` is reused — no fork of a public component (commitment §5) | A genuine new component (`ResolvedBundleInput` + `to_bundle_resolution`) exists where the synthesis claimed "a thin call" — the design surface grew |
| The type mismatch the synthesis under-stated is now visible, named, and unit-tested over a `ConcreteResolution` fixture | The adapter must track *two* upstream shapes (`ConcreteResolution`, `BundleResolution`) — if either evolves, the adapter is the edit site |
| `ResolverTccmPlaceholder` fails loud (Rule 12) — Phase 8 never silently builds an empty Bundle from a placeholder TCCM | A real Phase-8 prerequisite is surfaced: the resolver's S3-01 substitution (real `TCCM` from `tccm.yaml`) must ship, or be in the Phase-8 story plan |
| The Bundle-building boundary has exactly one named seam — the adapter — instead of a mismatch papered over in a node | The adapter is load-bearing per-workflow — a bug affects every Bundle; mitigated by being a pure transform, fully unit-tested |

## Pattern fit

The toolkit's "Adapter pattern" entry: "wrap an incompatible interface to make it match the one your client expects… wrapping Anthropic/OpenAI SDKs behind one common port." The resolver's output and the builder's input are two incompatible interfaces in the *same codebase* — exactly the Adapter's job. The toolkit's failure mode for Adapter is "an Adapter that re-exports the same interface unchanged" — `to_bundle_resolution` is *not* that: it genuinely translates (`Adapter` objects → `AdapterDispatch` callables; `ComposedTccm` → `TCCM`), so it is a real adapter, not a forwarder. Option B (inline) and Option C (fork) are both rejected — one hides the seam, the other forks a tested component.

## Consequences

- `codegenie.supervisor.bundle_resolution` ships `ResolvedBundleInput` (satisfies the `BundleResolution` Protocol) and `to_bundle_resolution`.
- The Supervisor's `build_bundle_node` calls `to_bundle_resolution`, then the shipped `BundleBuilder.build` — the builder is reused, not forked.
- `ResolverTccmPlaceholder` is a typed error raised when the resolver still returns the `ComposedTccm` placeholder — fail loud, naming S3-01.
- **A Phase-8 gating prerequisite is surfaced** (Open Question 1): the implementer must verify `resolver.resolve` hands the real `TCCM`. If it still hands the placeholder, the resolver-internal S3-01 substitution is a Phase-8 prerequisite and must be in the story plan — not worked around.
- The adapter is pure (microsecond transform) and fully unit-tested over a `ConcreteResolution` fixture.
- If the resolver's S3-01 ships the real `TCCM`, the `ResolverTccmPlaceholder` branch becomes a defensive guard; the adapter's mapping logic stays.

## Reversibility

**Medium.** The adapter exists because two shipped types do not line up. If the resolver were ever refactored to return a `BundleResolution`-shaped value directly, the adapter would become a thin pass-through and could be removed — a localized deletion. But as long as `resolver.resolve` returns `ConcreteResolution` and `BundleBuilder.build` expects `BundleResolution`, the adapter is structurally required; it cannot be removed without changing one of those two shipped surfaces. The `ResolverTccmPlaceholder` guard is cheap to retire once S3-01 lands.

## Evidence / sources

- ../phase-arch-design.md §Gap 2 — `ConcreteResolution` does not satisfy `BundleResolution`
- ../phase-arch-design.md §C2 — the adapter component
- ../phase-arch-design.md §Open question 1 — resolver → BundleBuilder TCCM handoff
- ../phase-arch-design.md §Edge case 2 — `ComposedTccm` placeholder
- ../final-design.md §Synthesis ledger — Conflict-resolution row "Bundle Builder ownership"
- ../critique.md §Attacks on the best-practices design, problems 1–2 — the resolver mis-modeling
- ../../../production/adrs/0031-plugin-architecture.md; ../../../production/adrs/0029-task-class-context-manifests.md
- `design-patterns-toolkit.md` §Adapter pattern
