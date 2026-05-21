# ADR-0008: RouteDecided/RouteDescended belong in the workflow-internal event stream

**Status:** Accepted
**Date:** 2026-05-21
**Tags:** Tagged union / sum type · event modeling · stream placement
**Related:** ADR-0007, [production ADR-0034](../../../production/adrs/0034-event-sourcing-canonical-primitive.md), [production ADR-0033](../../../production/adrs/0033-domain-modeling-discipline.md)

## Context

[ADR-0007](0007-routing-events-into-existing-event-log.md) commits Phase 8 to emitting `RouteDecided`/`RouteDescended` into the existing `codegenie.plugins.events` log rather than a new store. But that log is **not one stream**. Per [phase-arch-design.md §Gap 4](../phase-arch-design.md#gap-4--the-event-log-is-two-stream-the-synthesis-treats-it-as-one-chained-log), `events.py` ships *two non-fungible streams* (Phase 3 ADR-0005):

- `WorkflowInternalEvent` — per-workflow, **not** BLAKE3-chained, written via `emit_internal`, `fcntl.flock`-free.
- `WorkflowSpanningEvent` — cross-workflow, **BLAKE3-chained**, written via `emit_spanning`, one `fcntl.flock` per append.

`final-design.md` describes the log as a single "hash-chained append-only log" and calls the new events "additive variants of the existing chained log" — conflating the two streams. The shipped `PluginResolved` and `BundleBuilt` events are *both* `WorkflowInternalEvent`s — not chained. If a Phase-8 implementer follows the synthesis verbatim and adds `RouteDecided` to the *spanning* stream to get the chain, they would mis-place a workflow-scoped event and pay an `fcntl.flock` per routing decision for no benefit.

## Options considered

- **Option A — Add `RouteDecided`/`RouteDescended` to `WorkflowSpanningEvent` (the BLAKE3-chained stream).** **Pattern:** none — mis-models a workflow-scoped event as a cross-workflow one; pays a file-lock per routing decision; the chain adds tamper-evidence the completeness guarantee does not need.
- **Option B — Add them to `WorkflowInternalEvent` (the per-workflow, unchained stream), via `emit_internal`.** Matches the `PluginResolved`/`BundleBuilt` precedent exactly. **Pattern:** Tagged union / sum type — a `Literal`-tagged additive variant of the correct discriminated union.
- **Option C — Invent a third stream for routing events.** **Pattern:** none — a new stream for two event types is premature pluggability; the two existing streams already partition the space (per-workflow vs spanning) correctly.

## Decision

`RouteDecided` and `RouteDescended` are **`WorkflowInternalEvent`s** — added to the `WorkflowInternalEvent` discriminated union, the `_INTERNAL_CLASSES` registry, and `__all__` (three reviewable wiring lines), and emitted via `emit_internal`. They are workflow-scoped, so they belong in the per-workflow, unchained stream — matching the `PluginResolved` precedent. They do **not** ride the BLAKE3-chained spanning stream. This is the **Tagged union / sum type** pattern — an additive `Literal`-tagged variant of the *correct* union.

## Tradeoffs

| Gain | Cost |
|---|---|
| Routing events are placed in the stream whose scope (per-workflow) actually matches them — consistent with `PluginResolved`/`BundleBuilt` | No BLAKE3 chain on routing events — tamper-evidence for them is deferred to Phase 9's canonical log |
| No `fcntl.flock` per routing decision — `emit_internal` is lock-free; routing stays on the warm path's fast lane | The decision-log completeness test must assert *N events in the internal stream*, not "the hash chain verifies" — a corrected test shape |
| The internal stream is exactly what Phase 9 ports to Temporal workflow history — a natural, scope-matched migration | A reviewer who read `final-design.md`'s "chained log" prose must read this ADR to learn the two-stream reality |
| "Logged on every workflow" holds without chaining — `emit_internal` is the append-before-transition precondition; completeness ≠ chaining | Cross-workflow routing analytics (if ever needed) would require a projection, not a direct spanning-stream read |

## Pattern fit

The toolkit's "Tagged union / sum type for state" entry: model a `kind`-discriminated set of variants as a discriminated union; add new variants additively. The correctness question here is *which* union — and the answer is determined by the event's *scope*, not by a desire for a hash chain. A routing decision is a fact *about one workflow*; the `WorkflowInternalEvent` union is the type whose members are workflow-scoped facts. Adding `RouteDecided` there is the additive `Literal`-tagged variant the pattern prescribes. Putting it in the spanning stream would be modeling a per-workflow fact as a cross-workflow one — a type error of placement, even though both streams are "events."

## Consequences

- `RouteDecided`/`RouteDescended` are added to `WorkflowInternalEvent`, `_INTERNAL_CLASSES`, and `__all__` — three loud, compiler-policed wiring lines.
- Routing events are emitted via `emit_internal` — lock-free, per-workflow.
- The decision-log completeness adversarial test asserts *N `RouteDecided` events in the internal stream* for N workflows; it uses the *spanning* stream's `ChainTamperDetected` path only for events that actually ride the chain.
- Phase 9 ports the `WorkflowInternalEvent` stream to Temporal workflow history — routing events migrate there naturally.
- The "logged on every workflow by construction" guarantee holds via the `emit_internal` precondition; BLAKE3 chaining is not required for completeness and Phase 9's canonical log inherits completeness regardless of stream.
- A reviewer reading `final-design.md`'s "chained log" phrasing is corrected by this ADR — the two-stream reality is the codebase fact.

## Reversibility

**High.** Moving an event variant between streams later is a localized edit — remove it from one union/registry/`__all__`, add it to the other. No cross-phase contract depends on *which* stream a routing event rides; Phase 9 re-homes both streams anyway. The placement is chosen for correctness (scope match) and cost (no needless lock), and either could be revisited cheaply.

## Evidence / sources

- ../phase-arch-design.md §Gap 4 — the event log is two-stream
- ../phase-arch-design.md §C7 — Routing/resolution event emission
- ../phase-arch-design.md §Integration with Phase 9 — "Note (Gap 4)"
- ../final-design.md §C7 framing — the "hash-chained log" description corrected here
- ../../../production/adrs/0034-event-sourcing-canonical-primitive.md
- ../../../production/adrs/0033-domain-modeling-discipline.md — typed Pydantic events
- `design-patterns-toolkit.md` §Tagged union / sum type for state
