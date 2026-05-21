# ADR-0006: Cold-storage fallback reads the same RepoContext the renderer rendered from

**Status:** Accepted
**Date:** 2026-05-21
**Tags:** Hexagonal / ports & adapters · content-addressed cache · fail-closed
**Related:** ADR-0003, ADR-0004, [production ADR-0013](../../../production/adrs/0013-pre-rendered-redis-hot-views.md)

## Context

[ADR-0003](0003-hot-view-integrity-by-gather-id-content-addressing.md) makes Redis untrusted-on-read and fail-closed: an integrity miss (stale, tampered, version-drift), or Redis being unreachable, falls through to a *cold-storage* read. Phase 8 must define exactly what "cold storage" is and guarantee the fallback returns the *same data* the hot view would have.

The phase has no Postgres (that is Phase 9). The renderer (`render_hot_views`) is a pure function of a `RepoContext` artifact plus the `must_read` query union across active TCCMs. For the fail-closed property to be *correct* — not just *slower* — the cold read must reconstruct the slice from the **identical artifact** the renderer used. [phase-arch-design.md §Open question 6](../phase-arch-design.md#open-questions-deferred-to-implementation) and [final-design.md §Open question 5](../final-design.md#open-questions-deferred-to-implementation) both flag this: if the `ColdStoreReader` reads a *different* artifact (a newer gather, a different on-disk path), warm/cold equivalence breaks and a hot-view miss silently changes the planner's answer.

## Options considered

- **Option A — Cold storage is a `ColdStoreReader` Protocol; the Phase-8 adapter reads the on-disk `RepoContext` artifact identified by `gather_id`.** The reader re-runs the same pure `render_hot_views` derivation on that artifact. **Pattern:** Hexagonal / ports & adapters — `ColdStoreReader` is a Port; Phase 8 ships the disk adapter, Phase 9 swaps in a Postgres adapter with no planner-code change.
- **Option B — Cold storage re-runs the gather pipeline.** On a miss, trigger a fresh gather and render. **Pattern:** none — a gather is seconds-to-minutes; this turns a cache miss into a workflow stall and makes warm/cold equivalence impossible (a fresh gather is a *different* `RepoContext`).
- **Option C — No cold-storage path; a hot-view miss is a hard error.** **Pattern:** none — violates ADR-0013's documented fall-through and turns any Redis hiccup into a workflow failure; fails the "fail-closed, not fail-hard" property.

## Decision

Cold storage is a `ColdStoreReader` **Port**. The Phase-8 adapter reads the on-disk `RepoContext` artifact (`.codegenie/context/`) identified by the `gather_id` the planner is working against, and re-derives the missed slice via the *same* pure `render_hot_views` function the renderer used. The implementer must verify (Open Question 6) that this is byte-for-byte the artifact the renderer rendered from. A Hypothesis property test asserts **warm/cold equivalence**: for the same inputs, a hot-view-served read and a cold-storage read produce identical planner context.

## Tradeoffs

| Gain | Cost |
|---|---|
| The cache changes latency, never the answer — warm/cold equivalence is a property-tested invariant | The cold path is tens of ms (disk read + re-derivation) versus ~1–2 ms warm — a real but bounded slowdown |
| `ColdStoreReader` as a Port means Phase 9 swaps a Postgres-backed adapter in with zero planner-code change | The Phase-8 adapter must be pinned to the *same* artifact identity (`gather_id`) the renderer used — an implementer verification step, not a free property |
| A miss self-heals — the next gather re-renders Redis; the cold path is a transient, not a permanent, cost | A portfolio-wide cold-path storm (Redis flush) is possible; bounded and self-healing, but Phase 9 owns a warm-up-on-start story |
| Re-using the pure `render_hot_views` derivation means one code path computes a slice — no second "cold renderer" to keep in sync | If `render_hot_views`'s inputs ever broaden beyond `RepoContext` + TCCM, the cold adapter must broaden too |

## Pattern fit

The toolkit's "Hexagonal / ports & adapters" entry: the core talks to the outside world through Ports; Adapters implement them per technology. `ColdStoreReader` is the Port for "where the authoritative slice data lives." Phase 8's technology is the on-disk `RepoContext` artifact; Phase 9's is Postgres. Defining the Port now means the planner's fail-closed logic never names a storage technology — Phase 9 is an additive adapter swap. Re-using the pure `render_hot_views` derivation keeps the **functional core** single-sourced: the warm renderer and the cold reader compute a slice the *same* way, so equivalence is structural rather than a matched pair of implementations.

## Consequences

- `ColdStoreReader` is a Protocol; the Phase-8 adapter is the disk-`RepoContext` implementation, injected into `HotViewStore`.
- The cold adapter must resolve the artifact by `gather_id` — the implementer verifies (Open Question 6) it is the renderer's source artifact.
- A warm/cold-equivalence Hypothesis property test is a Phase-8 deliverable — it is the test that proves the cache is safe.
- `HotViewStore.get` never returns `None` — a miss resolves through the cold reader to a valid `HotViewSlice`; the planner's warm path stays branchless.
- Phase 9 replaces the disk adapter with a Postgres adapter; the planner and `HotViewStore` are unchanged.
- A cold-path storm after a Redis flush is bounded (every repo cold-paths once) and self-heals; Phase 9 adds warm-up-on-start.

## Reversibility

**High.** `ColdStoreReader` is a Port by construction — swapping the backing technology is the pattern's whole point and is exactly what Phase 9 does. The Phase-8 disk adapter is small and self-contained. The load-bearing invariant — warm/cold equivalence — is enforced by a property test independent of which adapter is in use, so changing the adapter cannot silently break it.

## Evidence / sources

- ../phase-arch-design.md §C4 — HotViewStore; §C5 — HotViewRenderer
- ../phase-arch-design.md §Open question 6 — cold-storage read path identity
- ../phase-arch-design.md §Testing strategy — "Warm/cold equivalence" property test
- ../final-design.md §Open question 5 — cold-storage read path identity
- ../../../production/adrs/0013-pre-rendered-redis-hot-views.md §Consequences — documented fall-through
- `design-patterns-toolkit.md` §Hexagonal architecture / Ports and adapters
