# ADR-0007: Routing decisions emit into the existing event log — no standalone event store

**Status:** Accepted
**Date:** 2026-05-21
**Tags:** Open/Closed at the file boundary · event emission · roadmap phasing
**Related:** ADR-0008, [production ADR-0034](../../../production/adrs/0034-event-sourcing-canonical-primitive.md), [production ADR-0033](../../../production/adrs/0033-domain-modeling-discipline.md)

## Context

Phase 8 exit criterion 1 requires "the chosen path is logged on every workflow." Phase 8 must decide *where* the routing/resolution decisions are recorded.

`codegenie.plugins.events` already ships a two-stream typed `EventLog` (Phase 3 ADR-0005). [critique.md §Which disagreement matters most](../critique.md#which-disagreement-matters-most-for-this-phase) names this as "the disagreement most likely to produce a wrong final design": the security lens proposes a standalone, BLAKE3-chained, KMS-signed event-sourced `PlannerDecisionLog`. That position is *seductive* — "logged by construction" sounds like exactly the exit criterion — but it directly contradicts the roadmap. [roadmap.md §Phase 9](../../../roadmap.md) states that ADR-0034 "lands operationally" in Phase 9, and names "plugin-resolution records" among the structures that "migrate to event-stream projections from this point [Phase 9]." A Phase-8 `PlannerDecisionLog` builds the Phase-9 canonical event log a phase early, under a different name, and gives Phase 11 (Learning) and Phase 13 (cost ledger) — both roadmap-committed to be *projections* of the Phase-9 log — two sources of truth.

## Options considered

- **Option A — Build a standalone event-sourced `PlannerDecisionLog`.** A new BLAKE3-chained, KMS-signed store for routing/resolution decisions. **Pattern:** Event sourcing — but applied a phase early; front-runs ADR-0034 and the roadmap's explicit Phase-9 boundary. The exit criterion ("logged on every workflow") is satisfied by *any* durable emission; it does not demand event sourcing.
- **Option B — Emit `Literal`-tagged routing events into the existing `codegenie.plugins.events` log; the append is a precondition of the routing transition.** **Pattern:** Open/Closed at the file boundary — two new `Literal`-tagged variants *added* to an existing discriminated union; no new store, no new module.
- **Option C — A fire-and-forget log line (`structlog` only), no typed event.** **Pattern:** none — an unstructured log line is not queryable, not replayable, and not the shape Phase 9's canonical log adopts; "logged on every workflow" would not be true *by construction*.

## Decision

Phase 8 **does not build a standalone event store.** Routing and resolution decisions emit `RouteDecided` and `RouteDescended` — two `Literal`-tagged Pydantic variants *added* to the existing `codegenie.plugins.events` discriminated union — via the shipped `EventLog`. The `RouteDecided` append is a **precondition of the routing transition**: `PlannerNode.route` appends the event, *then* returns the `RouteDecision`. ADR-0034's canonical event log lands in Phase 9; Phase 8 emits in the shape Phase 9 will project. This is the **Open/Closed at the file boundary** pattern — extension by an additive, compiler-policed variant, not a new subsystem.

## Tradeoffs

| Gain | Cost |
|---|---|
| "Logged on every workflow" is true *by construction* — `emit_internal` is the append-before-transition precondition | The event log is workflow/plugin-scoped until Phase 9 projects it into the canonical Postgres log — Phase 8 does not get a portfolio-wide query surface |
| Phase 9 *re-points* the log as a projection — it does not *re-build* one; "ADR-0034 lands operationally" stays an honest Phase-9 sentence | Phase 8 emits into a log Phase 9 will re-home; the events must already be shaped the way Phase 9 adopts (typed Pydantic per ADR-0033) — a forward-compat constraint |
| Phase 11 and Phase 13 read one canonical event stream, not two — no split-source-of-truth | No cryptographic signing of routing events in Phase 8 — that rides Phase 9's canonical-log infrastructure |
| Adding two `Literal`-tagged variants is a loud, three-line, compiler-policed edit (union + `_INTERNAL_CLASSES` + `__all__`) — the sanctioned additive shape | A standalone store's "log by construction" guarantee is given up in favour of the precondition-of-transition discipline — enforced by a static test, not a separate subsystem |

## Pattern fit

The toolkit's "Open/Closed Principle" entry: "adding a new feature should not require editing existing code… a new task class lands as new files." Adding `RouteDecided`/`RouteDescended` to the existing `WorkflowInternalEvent` union is the *sanctioned* additive edit `production/design.md §2` commitment §5 describes — "a new `Literal` member… is the enforcement mechanism, not a violation." A standalone `PlannerDecisionLog` is the toolkit's "speculative subsystem" applied to event sourcing: a new store for a guarantee an additive variant already provides, built before its enabling phase (9) arrives. Event sourcing is the *right* pattern — at the *right* phase.

## Consequences

- Two `Literal`-tagged variants are added to `codegenie.plugins.events`: `RouteDecided` and `RouteDescended` — see [ADR-0008](0008-route-events-in-the-workflow-internal-stream.md) for which stream.
- The `RouteDecided` append is a precondition of the routing transition; a static AST test asserts no routing edge is reachable on a code path that skips the append.
- Phase 8 builds *no* new event-store module — `roadmap.md §Phase 9`'s "plugin-resolution records migrate to event-stream projections" stays true.
- Phase 9 re-points `codegenie.plugins.events` as a projection of the canonical Postgres log; because Phase 8 emits via the *existing* `EventLog` in the *existing* shape, this is a re-pointing, not a re-build.
- Phase 11 (Learning) and Phase 13 (cost ledger) become projections of one canonical log — Phase 8 contributes events, not a competing store.
- A decision-log completeness adversarial test runs N fixture workflows and asserts exactly N `RouteDecided` events.

## Reversibility

**Medium.** Not building a thing is cheap to revisit — if a future phase proved a standalone routing store was needed, it could be added. But the *direction* — emit into the canonical lineage, let Phase 9 own event sourcing — is load-bearing for the roadmap's Phase 9/11/13 phasing. Reversing it (building a separate store) would re-introduce the split-source-of-truth this ADR exists to prevent and would require an explicit roadmap amendment. The additive `Literal` variants themselves are trivially reversible (remove three wiring lines), but the architectural stance is not.

## Evidence / sources

- ../final-design.md §Synthesis ledger — Conflict-resolution row "Routing-decision log"
- ../final-design.md §New ADRs implied, item 5
- ../phase-arch-design.md §C7 — Routing/resolution event emission; §Non-goals
- ../critique.md §Which disagreement matters most for this phase
- ../critique.md §Roadmap-level critiques, item 1(b)
- ../../../roadmap.md §Phase 9 — "Canonical event log anchored here"
- ../../../production/adrs/0034-event-sourcing-canonical-primitive.md
- `design-patterns-toolkit.md` §Open/Closed Principle
