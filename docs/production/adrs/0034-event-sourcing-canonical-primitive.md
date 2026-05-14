# ADR-0034: Event sourcing as canonical primitive for agent runs

**Status:** Accepted
**Date:** 2026-05-13
**Tags:** event-sourcing · audit · replay · observability · learning
**Related:** ADR-0003, ADR-0024, ADR-0026, ADR-0027, ADR-0029, ADR-0033

## Context

Multiple production concerns will each need an append-only log of "what happened during this workflow":

- **Cost ledger** (ADR-0024) — already append-only by design
- **Stage 7 Learning** — needs an event stream to project into the knowledge graph
- **Workflow audit trail** — needs replay capability for security and compliance
- **Trust gate decisions** — need full provenance (which evidence, which adapters, which outcomes)
- **Plugin resolution** ([ADR-0031](0031-plugin-architecture.md)) — needs an audit trail (which plugin matched, which `extends` chain, was the fallback used)
- **Adapter degradation** ([ADR-0032](0032-language-search-adapters.md)) — needs a visible history (when did SCIP go stale, when did we fall back to tree-sitter)
- **ROI dashboard** (ADR-0026) — aggregates outcomes, and outcomes are events

Each of these concerns *could* implement its own append-only log. That would mean 6+ distinct storage layers, 6+ schemas, 6+ query patterns, and 6+ chances to get the audit story wrong. Worse, cross-cutting queries (e.g., "show me every workflow that hit the universal fallback plugin in the last 30 days") become 6-way joins across heterogeneous stores.

Two layers in the architecture *already* provide event sourcing without us choosing it explicitly:

- **Temporal workflow history** ([ADR-0003](0003-temporal-as-workflow-substrate.md)) — every workflow has a complete event log natively; replay is a first-class feature
- **LangGraph checkpointer** ([ADR-0016](0016-checkpointer-backend.md)) — every state machine transition is checkpointed; state reconstruction is replay

The architecture is *already half-event-sourced*. The choice in this ADR is whether to make event sourcing the **canonical primitive** — a single typed event log that every concern projects from — or to let each concern grow its own structure.

This ADR depends on [ADR-0033](0033-domain-modeling-discipline.md) (domain modeling discipline). Typed events are dramatically more valuable than untyped events; without that discipline, the event stream is a soup of unstructured payloads that consumers re-parse defensively at every boundary.

## Options considered

- **Option A — each concern implements its own append-only log.** Cost ledger has its own table; Stage 7 Learning has its own stream; audit trail has its own. Each storage optimized for its access pattern. Most flexible; least cohesive; cross-cutting queries painful.
- **Option B — single canonical event log; every concern is a projection.** One typed event stream, multiple projections (cost ledger, KG, ROI dashboard, audit trail). High cohesion; some access-pattern compromises; one storage layer to operate.
- **Option C — hybrid.** Temporal handles workflow-internal events natively (state transitions, retries, gate decisions); a typed side-channel event log in Postgres handles workflow-spanning events (cost rollups, portfolio-level signals, KG writes). Projections materialize from both sources.

## Decision

**Adopt Option C — hybrid event sourcing with Temporal workflow history as the workflow-internal event store, plus a typed side-channel Postgres event log for workflow-spanning concerns.**

### Event types

All events are well-typed Pydantic models, respecting [ADR-0033](0033-domain-modeling-discipline.md) discipline. Every event has a common envelope:

- `event_id: EventId` (newtype on UUID)
- `event_type: EventType` (sum-type discriminator)
- `workflow_id: WorkflowId | None` (workflow-scoped events have one; portfolio events don't)
- `timestamp: datetime` (UTC, monotonic where Temporal supplies it)
- `payload: EventPayload` (tagged-union variant typed by `event_type`)
- `correlation_id: CorrelationId | None` (for tracing chains across workflows)

Illustrative event variants (the full catalog grows phase-by-phase):

```python
class PluginResolved(BaseModel):
    kind: Literal["plugin_resolved"] = "plugin_resolved"
    plugin_id: PluginId
    extends_chain: list[PluginId]
    matched_scope: PluginScope
    fallback_used: bool

class AdapterDegraded(BaseModel):
    kind: Literal["adapter_degraded"] = "adapter_degraded"
    primitive: PrimitiveName
    primary_adapter: AdapterId
    primary_confidence: float
    fallback_adapter: AdapterId | None

class TrustGatePassed(BaseModel):
    kind: Literal["trust_gate_passed"] = "trust_gate_passed"
    gate: GateId
    signals: dict[SignalKind, SignalValue]
    score: TrustScore

class TrustGateFailed(BaseModel):
    kind: Literal["trust_gate_failed"] = "trust_gate_failed"
    gate: GateId
    failing_signals: list[SignalKind]
    score: TrustScore
    retry_count: int

class CostIncurred(BaseModel):
    kind: Literal["cost_incurred"] = "cost_incurred"
    tier: CostTier               # direct | amortized | overhead
    amount_usd: Decimal
    source: CostSource

class MergeOutcome(BaseModel):
    kind: Literal["merge_outcome"] = "merge_outcome"
    pr_url: str
    decision: Literal["merged", "closed", "modified"]
    reviewer: str | None
```

Workflow state at any time = `fold(events.filter(workflow_id=X))`. The fold function is pure and exhaustively handles every event variant (enforced by `mypy --strict` + `assert_never` per [ADR-0033](0033-domain-modeling-discipline.md)).

### Projections (consumers)

Each consumer of the event stream is a *projection*. The same event can feed multiple projections; projections are idempotent — running one twice produces the same materialized state.

| Projection | Reads | Materializes |
|---|---|---|
| **Cost ledger** ([ADR-0024](0024-cost-observability-end-to-end.md), [ADR-0027](0027-cost-attribution-model.md)) | `CostIncurred` events | ledger rows by `(workflow, tier, source)` |
| **ROI dashboard** ([ADR-0026](0026-roi-kpi-model.md)) | `CostIncurred` + `MergeOutcome` events | headline ratios + diagnostics |
| **Stage 7 Learning** | `SolutionFound` + `AttemptCompleted` events | KG write-back |
| **Audit trail** | all events filtered by `workflow_id` | chronological event log per workflow |
| **Plugin telemetry** | `PluginResolved` + `MergeOutcome` events | per-plugin merge rate, cost/PR, fallback rate |
| **Trust gate observability** | `TrustGate*` events | retry-cause histograms, score distributions |

Each projection is independently testable: given a fixture event stream, assert the projection's output. This is the test pattern for the entire observability surface — no need for end-to-end workflow runs to test that the cost ledger or ROI dashboard works.

### Storage

| Scope | Storage | Source of truth |
|---|---|---|
| Workflow-internal (state transitions, retries, gate decisions) | **Temporal workflow history** | Temporal cluster (ADR-0003) |
| Workflow-spanning (cost rollups, KG writes, portfolio-level signals) | **Postgres event log** (`events` table) | App-managed, retention policy mirroring Temporal's |
| Materialized views (cost ledger, ROI, KG, …) | Postgres / Redis | Derived from the above two — not source of truth |

Projections subscribe to both sources. For workflow-scoped projections, Temporal's history-stream API is the input. For workflow-spanning projections, the Postgres event log is the input. For projections needing both (e.g., the audit trail rendering everything chronologically per workflow), the two streams are merged on `timestamp`.

### Replay

Given a `workflow_id`:

- **Temporal replay** reconstructs workflow-internal state via Temporal's native replay
- **Side-channel events** filtered by `workflow_id` reconstruct workflow-spanning artifacts (cost ledger entries, KG writes, plugin-resolution decisions)
- Merging the two on `timestamp` gives a complete chronological audit view

Replay is also a *test* primitive: every workflow's stored event history can be replayed in CI to verify the system reaches the same final state. Nondeterminism bugs that would otherwise reach production are caught at this layer.

## Tradeoffs

| Gain | Cost |
|---|---|
| 6+ ADRs (cost, ROI, learning, audit, replay, plugin telemetry) share one storage primitive | Event schema discipline is required; depends on the [ADR-0033](0033-domain-modeling-discipline.md) typed-events foundation |
| Replay-driven debugging — point at any workflow, get the full history, project any state | Storage cost grows with retention window; eventually need snapshots for long-running workflows (out of scope for v1) |
| Projections independently testable from fixture event streams — no end-to-end workflow runs needed for observability tests | Read patterns can be slower for ad-hoc queries that don't match any projection — design pressure to anticipate access patterns and materialize them |
| New observability features become projections — no new storage layer per feature | More design effort upfront defining events and discriminators |
| Cross-workflow analytics work naturally — same query language across the event log | Workflow-internal Temporal events and workflow-spanning Postgres events live in two stores — projection logic spans both |
| Trust gate "why did it decide that?" is a query, not a recovery exercise — full evidence is in the event payload | The temptation to put *everything* in events must be resisted; the event log is for *decisions and outcomes*, not for general state mutation |

## Consequences

- **Phases 0–8 use ad-hoc append-only structures** where they need them (attempt logs from `phase-story-executor`, draft cost ledgers, etc.). No retroactive disruption.
- **Phase 9 (Temporal) formalizes the canonical event log.** Temporal workflow history is the workflow-scoped substrate; the Postgres side-channel event log is added in Phase 9 (or Phase 13 alongside the cost-ledger formalization — whichever comes first).
- **ADR-0024 (cost observability) projection.** Cost ledger becomes `fold(CostIncurred events)`. Migration is straightforward because the existing draft format is already append-only.
- **ADR-0026 (ROI KPIs) projection.** Headline ratios + supporting metrics derive from event-stream folds; the dashboard reads materialized projections.
- **Stage 7 Learning projection.** KG writes derive from `SolutionFound` + `AttemptCompleted` event streams. The KG itself doesn't need to be append-only — only the events feeding it do.
- **Plugin telemetry projection.** Per-plugin merge rate, fallback rate, and ROI all derive from `PluginResolved` + `MergeOutcome` events.
- **Trust gate audit becomes free.** Every `TrustGatePassed` / `TrustGateFailed` event captures the full signal set. "Why did the gate decide what it decided?" is a `SELECT * FROM events WHERE event_type IN (...) AND workflow_id = ?` query.
- **Domain modeling discipline ([ADR-0033](0033-domain-modeling-discipline.md)) becomes load-bearing.** Without typed events, the event stream is a soup. With typed events, every consumer pattern-matches exhaustively and the type checker enforces handling of every event variant.
- **Schema evolution discipline required.** Adding a new event variant is non-breaking; renaming or removing fields requires a migration window and a record in this ADR's evidence section.

## Reversibility

**Medium.** Removing event sourcing as the canonical primitive would mean each projection migrating to its own storage with its own schema — feasible but loses cohesion, replay capability, and cross-cutting analytics. Reverse migration (re-introducing event sourcing after removal) would need to backfill events from the per-concern storage layers — possible but lossy. The compounding benefits (cheap-to-add projections, replay debugging) accrue over time; removing event sourcing after Phase 11 (when Stage 7 Learning is live) would be expensive.

## Evidence / sources

- Greg Young, "Event Sourcing" — https://eventstore.com/blog/what-is-event-sourcing
- Martin Fowler, "Event Sourcing" — https://martinfowler.com/eaaDev/EventSourcing.html
- Pat Helland, "Immutability Changes Everything" — CIDR 2015
- Temporal docs, workflow history and replay — https://docs.temporal.io/encyclopedia/event-history
- ADR-0003 — Temporal as workflow substrate (Phase 9 anchor)
- ADR-0024 — Cost observability end-to-end
- ADR-0033 — Domain modeling discipline (typed-events foundation; this ADR depends on it)
