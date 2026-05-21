# ADR-0004: Per-slice hot-view schema versioning

**Status:** Accepted
**Date:** 2026-05-21
**Tags:** content-addressed cache · make-illegal-states-unrepresentable · schema evolution
**Related:** ADR-0003, [production ADR-0013](../../../production/adrs/0013-pre-rendered-redis-hot-views.md)

## Context

[production ADR-0013](../../../production/adrs/0013-pre-rendered-redis-hot-views.md) §Consequences specifies that "when the slice shape changes, the version bumps and stale entries are evicted on read." Phase 8 must choose the *granularity* of that version: one global integer for all four slices, or one version per slice.

The four slices — `available_skills`, `entrypoint`, `risk_flags`, `confidence_summary` — evolve independently. They are fed by different probes and consumed by different parts of the planner; there is no reason a shape change to `risk_flags` should imply anything about `entrypoint`. [critique.md §Attacks on the best-practices design, problem 5](../critique.md#attacks-on-the-best-practices-design) shows best-practices picked a single `HotViewKey.schema_version: int` — "the coarsest possible versioning granularity" — and the critic names the missed pattern: "the natural model is a version *per slice name* (a `Mapping[HotViewSliceName, int]`)… the inverse of primitive obsession, call it scalar-where-a-map-belongs." The synthesis [departs from all three inputs](../final-design.md#departures-from-all-three-inputs) to version each slice independently.

## Options considered

- **Option A — One global `schema_version: int` across all four slices.** A shape change to any slice bumps the global version. **Pattern:** none — a scalar where a small map belongs. Bumping the version to evolve `risk_flags` cold-evicts `available_skills`, `entrypoint`, and `confidence_summary` for *every repo in the portfolio*, triggering a portfolio-wide cold-path storm for an unrelated change.
- **Option B — A version per slice — `slice_schema_versions: Mapping[HotViewSliceName, int]`.** Each slice carries its own `slice_schema_version`; a shape change bumps only that slice's version. **Pattern:** content-addressed cache + make-illegal-states-unrepresentable — the version is part of the per-slice cache key, so a version-drift on one slice is a miss for that slice only.
- **Option C — No explicit version; rely on Pydantic `extra="forbid"` to reject an old shape.** **Pattern:** none — `extra="forbid"` catches an *added* field but not a *removed* or *re-typed* one, and gives no clean eviction signal; a silently-wrong-but-parseable old value would reach the planner.

## Decision

Each of the four hot-view slices carries its own `slice_schema_version: int`. `HotViewStore` is injected with a `slice_schema_versions: Mapping[HotViewSliceName, int]` (a module-level `Final` dict is the production default); the version is part of the `(repo, slice_name, gather_id, slice_schema_version)` integrity binding ([ADR-0003](0003-hot-view-integrity-by-gather-id-content-addressing.md)) and the `HotViewKey.redis_key()`. A shape change to one slice bumps only that slice's version. This is a refinement of ADR-0013's "versioned, evicted on read" to **per-slice** granularity.

## Tradeoffs

| Gain | Cost |
|---|---|
| One slice's shape change does not cold-evict the other three — a `risk_flags` bump leaves `available_skills`/`entrypoint`/`confidence_summary` warm | A `Mapping[HotViewSliceName, int]` to maintain instead of a scalar `int` |
| The blast radius of a schema evolution is one slice, not the whole hot-view set | Four version numbers to keep in sync between the renderer and the store — a renderer/store contract |
| Version-drift on a slice is a clean per-slice cache miss → cold read → re-render at the current version (edge case 6) | The `slice_schema_versions` mapping must be injected, not read at import — one more DI argument on `HotViewStore` |
| The version rides in `redis_key()`, so old-version values are never read, never need active deletion — they age out naturally | A reviewer must remember to bump *only* the affected slice; bumping all four "to be safe" silently re-introduces Option A's cost |

## Pattern fit

The toolkit flags "primitive obsession" and the critic names this case as its inverse — *scalar-where-a-map-belongs*. A slice's shape is a per-slice contract; modeling four independent contracts with one shared scalar conflates them. The per-slice `Mapping` makes each slice's version an independent, named value — the **make-illegal-states-unrepresentable** discipline applied to schema evolution: a value at the wrong version for *its* slice is structurally a miss, and a correct value for a sibling slice is unaffected. The version-in-the-key is the **content-addressed cache** idiom — the same way `cache/keys.py` derives keys from content identity.

## Consequences

- `HotViewKey` carries `slice_schema_version`; `HotViewSlice` carries it too (so the value self-describes its version) — the store cross-checks both.
- `HotViewStore` gains a `slice_schema_versions: Mapping[HotViewSliceName, int]` constructor argument; the production default is a module-level `Final` dict.
- A schema evolution is a one-slice edit: bump that slice's entry in the `Final` dict, update its payload model — the other three slices are untouched and stay warm.
- Edge case 6 (one slice's shape changes) is handled structurally — only the changed slice cold-paths once, then self-heals on the next gather.
- 100% branch coverage is required on the integrity/version-compare path (it is part of an exit-criteria-bearing function).
- A reviewer discipline: bump only the slice whose shape actually changed — bumping all four re-creates the global-version cost this ADR exists to avoid.

## Reversibility

**High.** The granularity is an internal cache-key detail. Collapsing back to a global version (or widening to a richer version object) is a localized change to `HotViewKey`, `HotViewSlice`, and the `slice_schema_versions` injection — no cross-phase contract depends on the *number* of version counters. The hot-view cache is fully reconstructable from the next gather, so even a botched version change self-heals.

## Evidence / sources

- ../final-design.md §Departures from all three inputs, item 3 — per-slice hot-view versioning
- ../phase-arch-design.md §C4 — HotViewStore; §Data model — `HotViewKey`, `HotViewSlice`
- ../phase-arch-design.md §Edge case 6 — one slice's schema shape changes
- ../critique.md §Attacks on the best-practices design, problem 5 — "scalar-where-a-map-belongs"
- ../../../production/adrs/0013-pre-rendered-redis-hot-views.md §Consequences
- `design-patterns-toolkit.md` §Make illegal states unrepresentable
