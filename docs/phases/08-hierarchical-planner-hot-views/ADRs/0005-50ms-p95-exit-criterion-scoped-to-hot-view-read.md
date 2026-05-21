# ADR-0005: The <50ms p95 exit criterion is scoped to the hot-view read

**Status:** Accepted
**Date:** 2026-05-21
**Tags:** Functional core / imperative shell · performance SLO · testability
**Related:** ADR-0003, [production ADR-0013](../../../production/adrs/0013-pre-rendered-redis-hot-views.md), [production ADR-0030](../../../production/adrs/0030-graph-aware-context-queries.md)

## Context

The roadmap's Phase 8 exit criterion 2 reads: "Hot views serve agent context in <50ms p95." The phrase "serve agent context" is ambiguous — it could mean (a) the `HotViewStore.get_all` read plus deserialization, or (b) the whole workflow-trigger-to-context-in-hand path including plugin resolution, Bundle building, and the routing decision.

This is not a cosmetic ambiguity. Per [critique.md §Where do all three quietly agree on something questionable](../critique.md#where-do-all-three-quietly-agree-on-something-questionable), *all three* lens designs converged on the narrow reading (the Redis read SLO) — each citing the others' framing. The critic flags this as unverified convergence: "three designs converging on the *convenient* reading of an ambiguous exit criterion, each citing the others, is not verification. If a reviewer reads 'serve agent context' as 'from workflow trigger to context-in-hand,' all three miss the bar." Bundle building is dominated by ADR-0030 graph queries (potentially tens of ms); folding it into the 50 ms budget would make the SLO untestable at Phase 8's exit and conflate a cache-read latency with an upstream-query latency. The synthesis [carries this forward and pins it as a definition](../final-design.md#shared-blind-spots-considered), recording an implied ADR so the pin is durable.

## Options considered

- **Option A — Pin the SLO to `HotViewStore.get_all` + deserialization.** The 50 ms covers the four-key pipelined Redis round-trip and the Pydantic deserialization of the four slices — and nothing else. **Pattern:** Functional core / imperative shell — the SLO measures one isolated, falsifiable shell operation.
- **Option B — Pin the SLO to the full trigger-to-context path.** The 50 ms covers resolution + Bundle building + routing + the hot-view read. **Pattern:** none — bundles a deterministic ~5 ms resolution, an unbounded ADR-0030 graph-query Bundle build, and a cache read into one number; the SLO becomes a proxy for graph-query performance, untestable at Phase 8 exit.
- **Option C — Leave it ambiguous; measure whatever the implementer finds convenient.** **Pattern:** none — the exact failure mode the critic warns about; the exit criterion would be unfalsifiable.

## Decision

The Phase 8 `<50 ms p95` exit criterion is **pinned to `HotViewStore.get_all` plus Pydantic deserialization of the four slices** — explicitly *excluding* plugin resolution, Bundle building, and the routing decision. The `phase08_e2e` latency test measures exactly that scope: 200 sequential `get_all` calls after a real render against a `redis:7-alpine` container, asserting `p95 < 50 ms`. A `@pytest.mark.bench` canary measures the same. This is the **Functional core, imperative shell** discipline applied to an SLO — the measured surface is one isolated shell operation.

## Tradeoffs

| Gain | Cost |
|---|---|
| The exit criterion is a single, falsifiable, automated measurement — `get_all` + deserialize, nothing else | The pin narrows the roadmap's prose; a reader who expected an end-to-end SLO must read this ADR to see the scope |
| The 50 ms is not contaminated by ADR-0030 graph-query latency, which is upstream, unbounded, and not a Phase-8 deliverable | Workflow-trigger-to-context-in-hand latency is *not* covered by any Phase-8 exit gate — it is observed but not asserted |
| Bundle building's cost is governed by ADR-0030's own budget arithmetic, where it belongs — not smuggled into a cache SLO | Phase 9 must re-verify the 50 ms under its own topology (Redis on a separate host, not a local socket) — this number is a dev-substrate number |
| Warm-path Supervisor overhead gets its own separate bench (`p95 < 5 ms`) — the two latencies are measured independently, not averaged | Two SLO numbers to track instead of one |

## Pattern fit

The toolkit's "Functional core, imperative shell" entry: side effects pushed to the edges, "given inputs, compute outputs deterministically." `HotViewStore.get_all` is a single, well-bounded *shell* operation — one pipelined Redis read plus a pure deserialization. Pinning the SLO to exactly that surface makes it the kind of falsifiable, automated test the pattern enables. Folding in resolution and Bundle building (Option B) would make the SLO a proxy for an unbounded graph-query cost — the toolkit's "pipeline where each stage has 14 ways to mutate shared state" failure mode applied to a latency budget.

## Consequences

- The `phase08_e2e` latency test and the `@pytest.mark.bench` canary both measure `get_all` + deserialization only; a > 20 % regression fails the advisory bench gate with a CI annotation.
- Warm-path Supervisor overhead (`resolve → build_bundle → route` minus the hot-view read) is measured by a *separate* bench asserting `p95 < 5 ms`.
- Bundle-building latency is governed by ADR-0030's budget arithmetic; it is upstream of the hot-view read and outside this SLO.
- Phase 9 re-runs the 50 ms canary under its production topology (Redis relocated to its own host) — the dev-substrate ~25× headroom is not assumed to survive that move.
- A reviewer evaluating "is exit criterion 2 met?" has an unambiguous, automated answer — the e2e test result.
- This ADR makes the roadmap's "serve agent context" prose precise; it does not amend the roadmap, it pins its intent.

## Reversibility

**High.** The scope is a test-definition decision. Widening it (to include resolution, or to measure end-to-end) is changing what the `phase08_e2e` latency test wraps — a localized test edit. No production code or contract depends on the SLO *scope*; only the bench and e2e tests do. Phase 9 already re-verifies under a new topology, so revisiting the scope is an expected, low-cost activity.

## Evidence / sources

- ../final-design.md §Shared blind spots considered — "<50ms p95 scope ambiguity"
- ../final-design.md §Exit-criteria checklist — exit criterion 2
- ../phase-arch-design.md §G2 — "Hot-view serving < 50 ms p95… Scope is pinned"
- ../phase-arch-design.md §Testing strategy — Performance regression tests
- ../critique.md §Where do all three quietly agree — convergence on the convenient reading
- ../../../production/adrs/0013-pre-rendered-redis-hot-views.md
- `design-patterns-toolkit.md` §Functional core, imperative shell
