# ADR-0002: Phase-8 `codegenie.plugins.events` log → canonical event log cutover schedule

**Status:** Accepted
**Date:** 2026-05-23
**Tags:** strangler-fig · event-sourcing · cutover
**Related:** [ADR-0003](0003-per-workflow-blake3-prev-hash-chain.md), [ADR-0012](0012-event-store-topology-temporal-history-plus-postgres-events.md), [production ADR-0034](../../../production/adrs/0034-event-sourcing-canonical-primitive.md), [production ADR-0043](../../../production/adrs/0043-extension-by-addition-means-no-silent-edits.md)

## Context

Phase 8 ships an internal hash-chained append-only log at `codegenie.plugins.events` that the Phase-8 Supervisor uses for plugin-level node-by-node decisions. Phase 9 introduces the canonical Postgres-backed event log mandated by [ADR-0034](../../../production/adrs/0034-event-sourcing-canonical-primitive.md). There are now *two* log substrates in-tree. Three options exist for how they relate during the Phase-9 window. The critic's roadmap-1 attack flagged that running them in parallel indefinitely would create a "which log is canonical?" maintenance debt and a real risk that downstream projections accidentally read from the wrong one.

## Options considered

- **Parallel-forever.** Keep both logs; project off whichever fits each consumer. **Pattern:** none — anti-pattern, accreted redundancy.
- **Hard cutover at Phase-9 commit-1.** Delete the Phase-8 log; any in-flight workflow on Phase-6/8 silently loses audit history. **Pattern:** big-bang cutover.
- **One-way forward emit during a bounded drain window.** The Phase-8 log keeps running unchanged inside `run_vuln_subgraph` for Phase 9; its terminal records (`PluginResolved`, `BundleBuilt`, `RouteDecided`) are *also* emitted forward via the `emit_event` Activity into the canonical log. Projections consume only the canonical log from day one. Phase 10's first commit deletes the Phase-8 log after a 30-day drain. **Pattern:** strangler-fig with explicit termination date.

## Decision

The Phase-8 log runs unchanged inside `run_vuln_subgraph` and emits forward into the canonical event log via `emit_event`; projections read only the canonical log; **Phase 10's first commit deletes `codegenie.plugins.events`** after a 30-day drain. A CI canary asserts no Phase-8-log-only workflow is in flight before the deletion PR can land. **Pattern: strangler-fig with explicit termination.**

## Tradeoffs

| Gain | Cost |
|---|---|
| Projections consume one log from Phase-9 day one — no "two-source-of-truth" ambiguity | Phase-9 window has a redundant writer (Phase-8 log still appends inside the Activity) |
| No silent loss of Phase-8-style node-level detail during the transition | Engineers must remember the Phase-8 log is *not* a read target — only a Phase-9-internal writer |
| Deletion is dated (Phase 10 first commit, 30-day drain) rather than vague | CI canary becomes a coordination point between Phase-9 and Phase-10 |
| Satisfies ADR-0043 — no `NotImplementedError` stub for the canonical log; both logs are real | Code carries a comment-grade "TODO: delete in Phase 10" marker for one phase |
| Phase-6 hash-chain semantics survive byte-identically through the drain | Two chain-verification disciplines run side by side until Phase-10 |

## Pattern fit

Strangler-fig with explicit termination: the new system (canonical event log) is built around the old one (Phase-8 log); writes funnel forward into the new; the old is removed on a named date. The toolkit calls this out as the canonical replacement-with-known-cost pattern. The 30-day drain length matches production ADR-0040's audit-class retention floor and the Phase-9-to-10 cadence.

## Consequences

- The `emit_event` Activity is the single forward path; the Phase-8 log code is untouched in Phase 9.
- All Phase-9+ projections (`audit_trail`, `retry_histogram`, `plugin_telemetry`) read from `events.events` only.
- Phase 10 acquires an explicit precondition: "delete `codegenie.plugins.events` in PR #1; canary green for ≥ 14 days prior".
- The Phase-8 hash chain's audit value is preserved through forward emit — node-level detail lands as Phase-9 events even though Phase-9 records the SHERPA subgraph at activity-granularity.
- New consumers (Phase 11 Learning, Phase 13 cost ledger) only ever see one log. They cannot accidentally couple to the deprecated log.
- If the 30-day drain canary stays red beyond Phase 10's window, Phase 10's deletion PR is blocked until the residual workflows complete.

## Reversibility

**Medium.** Reverting requires un-deleting `codegenie.plugins.events` (recoverable from git) and rewriting projections to read from it. The cost is non-trivial because by then Phase 10/11 projections exist. After the Phase-10 deletion lands, reversibility drops to **low** — Phase 11 projections will assume the canonical log shape.

## Evidence / sources

- [`../final-design.md §Synthesis ledger — Phase-8 cutover row`](../final-design.md)
- [`../final-design.md §6 — The Phase-8 `codegenie.plugins.events` cutover bullet`](../final-design.md)
- [`../final-design.md §Risks #5`](../final-design.md)
- [`../phase-arch-design.md §Non-goals — Parallel-running Phase-8 log`](../phase-arch-design.md#non-goals)
- [`../phase-arch-design.md §Integration with Phase 10`](../phase-arch-design.md#integration-with-phase-10-stage-0-discovery--stage-1-assessment)
- [production ADR-0034](../../../production/adrs/0034-event-sourcing-canonical-primitive.md)
- [production ADR-0043](../../../production/adrs/0043-extension-by-addition-means-no-silent-edits.md)
