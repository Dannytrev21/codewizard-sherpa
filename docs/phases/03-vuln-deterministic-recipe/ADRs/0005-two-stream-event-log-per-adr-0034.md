# ADR-0005: Two-stream event log — `workflow_internal` + `workflow_spanning` — per ADR-0034 hybrid model

**Status:** Accepted
**Date:** 2026-05-17
**Tags:** event-sourcing · audit · phase-9-migration · durability · hybrid-model
**Related:** [0001](0001-ship-phase5-contract-surface-by-name.md), [0011](0011-honest-framing-capability-sandboxedpath-pluginslock.md), [production ADR-0034](../../../production/adrs/0034-event-sourcing-canonical-primitive.md)

## Context

Production ADR-0034 commits to event sourcing as the canonical primitive for agent runs, with a **hybrid model**: workflow-internal events (per-workflow state transitions; fold-replayable; relevant only inside one workflow) land in Temporal history, while workflow-spanning events (cross-workflow facts like cost, capability minting, audit-chain heads, bench-replayability) land in Postgres as the system-of-record. Phase 9 implements the hybrid backend; Phase 3 must emit events whose **categorical split mirrors that backend** or Phase 9 becomes a re-taxonomize-the-world migration.

All three Phase 3 lens designs proposed a single event stream and asserted "Phase 9 will lift the Phase 3 event log unchanged" (`final-design.md §Shared blind spots #2`). The critic correctly flagged this: a single stream means Phase 9 has to retroactively classify every event type into internal-vs-spanning, port the existing log into both backends, and resolve ambiguities — exactly the migration ADR-0034 was designed to avoid.

The architecture spec (`phase-arch-design.md §Component design C9` + §Departures from all three inputs #6) ships the split now: two on-disk files, two emission methods (`emit_internal` / `emit_spanning`), two distinct event taxonomies (`WorkflowInternalEvent` / `WorkflowSpanningEvent` discriminated unions).

## Options considered

- **Option A — Single stream, classify later.** One `.jsonl.zst` file per workflow holding every event; Phase 9 reads, classifies, and partitions during migration. **Pattern:** Event sourcing with lazy taxonomy. Defers the cost; eats it as a one-time migration headache.
- **Option B — Two streams, two on-disk files, two emission methods, two typed unions.** Per-workflow `.codegenie/events/workflow-internal/<workflow_id>.jsonl.zst` for fold-replayable state transitions; shared append-only `.codegenie/events/spanning/append.jsonl.zst` with BLAKE3 chain + `fcntl.flock` for cross-workflow facts. Phase 9 reads each stream into its destined backend. **Pattern:** Event sourcing with eager taxonomy aligned to the hybrid backend.
- **Option C — Single stream tagged by `category: Literal["internal","spanning"]`.** One file, one method, post-hoc filter. **Pattern:** Tag-and-dispatch — defers the split but doesn't reduce its cost; loses cross-workflow append-only durability semantics.

## Decision

Adopt **Option B.** Ship `EventLog` (`src/codegenie/plugins/events.py`) with two emission methods (`emit_internal(event: WorkflowInternalEvent) -> EventId` / `emit_spanning(event: WorkflowSpanningEvent) -> EventId`) writing to two distinct on-disk locations:

- **Workflow-internal:** `.codegenie/events/workflow-internal/<workflow_id>.jsonl.zst` — per-workflow file, fsync on workflow end. Phase 9 ports this to Temporal history.
- **Workflow-spanning:** `.codegenie/events/spanning/append.jsonl.zst` — single append-only file shared across workflows; BLAKE3-chained for tamper evidence; `fcntl.flock`-protected for cross-process safety. Phase 9 ports this to a Postgres `events` table.

The event taxonomies are two distinct Pydantic discriminated unions (see `phase-arch-design.md §Component design C9` for the exhaustive list of variants per stream). Crossing the taxonomy boundary requires an ADR amendment.

## Tradeoffs

| Gain | Cost |
|---|---|
| Phase 9 migration is mechanical: workflow-internal stream → Temporal history (per-workflow lift); spanning stream → Postgres `events` table (bulk load). No re-classification, no ambiguity resolution | Two files per workflow; slightly more I/O overhead at write time |
| The taxonomy is forced explicit at emission time — the engineer must answer "is this event internal or spanning?" when they add it, when the answer is fresh, not 18 months later | Two enums to maintain; cross-stream events (those that genuinely span workflows but encode workflow-internal causation) need a clear convention — we adopt "if Phase 9 needs to query it across workflows, it's spanning" |
| BLAKE3 chain on the spanning stream gives tamper-evidence across workflows — `codegenie audit verify` extends Phase 0's chain-verification primitive | The chain is a single shared file; one corruption breaks every downstream verification until the corruption point. `fcntl.flock` is mandatory; concurrent writers without it would interleave |
| Per-workflow fsync on the internal stream is cheap (one fsync per workflow end, not per emit); BLAKE3 chain on spanning is per-emit but amortized | The internal stream has at-most-one-workflow's-worth of data loss on crash; this is acceptable for fold-replay (the workflow itself failed, the log loss is bounded) |
| The two taxonomies make discoverability easy: a Phase 4 developer adding `LlmInvocationStarted` knows it's workflow-internal (causal within one workflow) by its semantics; adding it to `WorkflowInternalEvent` is the obvious choice | Naming discipline matters — `PluginsLoaded` is workflow-internal-but-on-first-import-it's-ambiguous; the convention "loaded means re-loaded per workflow process" must be documented |

## Pattern fit

Implements **Event sourcing for agent runs** (toolkit §Run-shape patterns) faithfully — "state is an immutable log of events; current state is a fold over events; replay = re-running the fold." The two-stream split aligns the local POC's persistence with the production hybrid backend ADR-0034 mandates, eliminating the canonical event-sourcing failure mode of "we used event sourcing but our backend wants different shapes." Also instantiates **Tagged union / sum type for state** (toolkit §Structural / typing patterns) at the event-type level — `WorkflowInternalEvent` and `WorkflowSpanningEvent` are typed discriminated unions, not free-form dicts.

## Consequences

- `src/codegenie/plugins/events.py` ships `EventLog`, `WorkflowInternalEvent`, `WorkflowSpanningEvent`, and the BLAKE3-chained writer for the spanning stream (lifts Phase 0's `audit_anchor` helper).
- The spanning stream is the seed source for Phase 6.5's `BenchReplayable` events — `codegenie eval backfill` reads it directly.
- `tests/integration/test_event_replay.py` asserts replay produces byte-equal post-state (modulo timestamps + `workflow_id`).
- `codegenie audit verify` extends to verify the BLAKE3 chain on the spanning stream and refuses startup on break.
- Phase 9 ingest jobs read from these two paths; the on-disk locations are themselves a stable contract (changing them requires an ADR amendment).
- Adding a new event variant requires editing the corresponding discriminated-union module + supplying a Pydantic `extra="forbid"` payload schema. Cross-cutting concerns (cost, capability minting, audit-chain heads, stale-vuln-index warnings) go on the spanning stream; per-workflow state transitions (plugin resolved, recipe applied, stage outcomes) go on the internal stream.
- `flush()` at workflow end is mandatory; the orchestrator's `finally` block invokes it before re-raising any exception.
- `TrustScorer` reads its own workflow's internal stream for `AdapterDegraded` markers — this is the ambient-state alternative rejected in ADR-0001 (constructor-injected EventLog instead).

## Reversibility

**Medium.** Merging the two streams into one would require Phase 9's Temporal-vs-Postgres routing logic to live in the local POC — a regression. Switching from two on-disk files to one shared file with a `category` discriminator is mechanical but loses the per-workflow fsync semantics that make the internal stream cheap. The split is hard to reverse because it's load-bearing for Phase 9's clean migration; that's the point.

## Evidence / sources

- `../phase-arch-design.md §Component design C9`, §Design patterns applied row 6, §Departures from all three inputs #6, §Path to production end state (Phase 9 row)
- `../final-design.md §Synthesis ledger row "Event log shape"` (score 15/15) and §Shared blind spots #2 (the "Phase 9 will lift unchanged" mistake)
- `../critique.md §Cross-design observations §Where do all three quietly agree on something questionable?` (single-stream blind spot)
- [production ADR-0034 — event sourcing as canonical primitive](../../../production/adrs/0034-event-sourcing-canonical-primitive.md)
- design-patterns-toolkit.md §Event sourcing for agent runs, §Tagged union / sum type for state
