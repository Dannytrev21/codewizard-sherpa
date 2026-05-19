# ADR-0001: No `MultiPluginCoordinator` in Phase 7 — emit `Both` + `RequiresMultiPluginCoordination` and stop

**Status:** Accepted
**Date:** 2026-05-19
**Tags:** phase-boundary · adr-0042 · event-sourcing · anti-decision · planner
**Related:** [0006](0006-adapter-dispatch-explicit-final-tuple.md), [0017](0017-both-provenance-exits-code-8-with-coordination-summary.md), [production ADR-0042](../../../production/adrs/0042-multi-plugin-coordination-for-both-workflows.md), [production ADR-0034](../../../production/adrs/0034-event-sourcing-canonical-primitive.md), [production ADR-0038](../../../production/adrs/0038-vulnerability-provenance-attribution.md)

## Context

Two of the three lens designs (performance-first and security-first) proposed shipping a `MultiPluginCoordinator` class in Phase 7 — performance with PR-ordering policy, partial-success semantics, and pre-Phase-9 `asyncio.gather` plumbing; security with a `CoordinationState` sum, a 24-hour partial-application watchdog, and a Phase 11 merge-gate dependency. Both designs invent the Phase 8 Planner's load-bearing component one phase early.

[production ADR-0042](../../../production/adrs/0042-multi-plugin-coordination-for-both-workflows.md) is unambiguous: "**The Planner owns sequencing, shared evidence, and cross-PR status**." The Planner is Phase 8. Phase 7 ships zero real PRs (Phase 11 is "first PR at scale" per the roadmap), so any PR-ordering policy, partial-application watchdog, or atomic-or-nothing merge guarantee in Phase 7 observes an empty set.

The critic landed Perf-1, Sec-1, and roadmap-1 on this in [`critique.md`](../critique.md). The synthesis (`final-design.md §Synthesis ledger row 1`, score **15/15**) takes best-practices' position: Phase 7 emits a typed `Both` provenance variant plus a `RequiresMultiPluginCoordination` event into the spanning event log, and stops.

## Options considered

- **Option A — Ship `MultiPluginCoordinator` in Phase 7 with PR-ordering policy + watchdog.** Performance-first / security-first position. **Pattern:** Mediator + State-machine. Inverts ADR-0042's phase ownership; depends on Phase 11 merge-gate behavior that doesn't exist; runs PR-ordering policy against zero PRs.
- **Option B — Ship a stub `MultiPluginCoordinator` that records `Both` events but doesn't sequence.** Halfway position. **Pattern:** Null-object. Forces Phase 8 to inherit a structural shape it did not design (premature pluggability for an owner one phase late).
- **Option C — Emit `Both` + typed `RequiresMultiPluginCoordination` event; CLI exits code 8 with `coordination-summary.yaml`; no Phase-7-owned coordinator at all.** **Pattern:** Event sourcing — Phase 7 produces evidence; Phase 8's Planner projects it.

## Decision

Adopt **Option C.** When `assemble_provenance` returns `Both`, the migration plugin's subgraph emits exactly one `RequiresMultiPluginCoordination(workflow_id, app_record, base_record, summary_path, emitted_at)` event into the spanning event log (per [ADR-0034](../../../production/adrs/0034-event-sourcing-canonical-primitive.md)), writes `coordination-summary.yaml`, returns `Applicability.PendingCoordination` to the orchestrator, and the CLI exits with code 8. No `MultiPluginCoordinator` class. No watchdog. No `asyncio.gather` over child workflows. No PR-ordering policy. Sequencing, partial-application semantics, atomic-or-nothing merge — all Phase 8's job per ADR-0042.

## Tradeoffs

| Gain | Cost |
|---|---|
| Phase 7 respects the phase boundary ADR-0042 set; Phase 8's Planner arrives to a problem it gets to design, not a half-solved one | `Both`-variant events accumulate in the spanning log unread for ~3 months until Phase 8 lands; operators need the `codegenie list-coordination-candidates` CLI ([0017](0017-both-provenance-exits-code-8-with-coordination-summary.md)) to see them |
| No new top-level package (`src/codegenie/multiplugin/`); the only Phase 7 addition for the `Both` path is one event variant + one YAML writer | The `Both`-path e2e test (`tests/e2e/test_both_provenance_emits_coordination_event_e2e.py`) only proves "evidence emitted," not "atomic-or-nothing enforced" — that proof lands in Phase 11 |
| Phase 11's merge-gate (when it lands) gets a clean, typed spanning-log stream to project; no Phase-7 coordinator state to reconcile with | Operators reading the spanning log directly see `RequiresMultiPluginCoordination` events with no consumer for months; mitigated by the `_index.tsv` rollup writer (Gap 5 mitigation in arch spec) |
| Critic-rejection of two-thirds of the lens designs preserved as a load-bearing veto, not a footnote — the synthesis is explicit | The decision must be re-justified to anyone who reads only the perf/security designs and not the critic |
| Zero risk of Phase 7 owning Phase 8's `CoordinationState` sum type incorrectly; Phase 8 designs that type cold | Phase 7 must publish `Both.app_record` + `Both.base_record` with enough fidelity that Phase 8 can route without re-running adapters — locked by the typed event payload |

## Pattern fit

Implements **Event sourcing** (toolkit §Behavioral patterns; [production ADR-0034](../../../production/adrs/0034-event-sourcing-canonical-primitive.md)): the spanning log is the source of truth; Phase 8's projection is the consumer. Also instantiates **Anti-decision / Phase-boundary discipline** (toolkit §Composition / coupling): the cheapest abstraction is the one you don't ship. Rejects **Mediator** + **State-machine** (toolkit §Behavioral) on the grounds that there is nothing to mediate in Phase 7 (no two PRs to coordinate) and nothing to transition (the `Both` event is terminal until Phase 8 reads it).

## Consequences

- `src/codegenie/multiplugin/` is **not created** in Phase 7. The fence allowlist ([0009](0009-phase-7-byte-edit-allowlist-fence.md)) does not authorize it; any PR adding such a directory fails CI.
- `RequiresMultiPluginCoordination` event variant ships in `src/codegenie/primitives/vuln_provenance/events.py` (typed Pydantic per ADR-0034); writer is pure; append-only spanning log.
- CLI exit code 8 is reserved for "requires multi-plugin coordination — awaiting Phase 8 Planner"; documented in the CLI help text and pinned by `tests/e2e/test_both_provenance_emits_coordination_event_e2e.py`.
- A property test (`tests/property/vuln_provenance/test_both_always_emits_coordination.py`) asserts: for every workflow where `assemble_provenance` returns `Both`, the spanning log contains exactly one `RequiresMultiPluginCoordination` event and the process exits code 8. This is the load-bearing roadmap-coherence invariant.
- `codegenie list-coordination-candidates` ships as a tiny operator-facing CLI subcommand so the pre-Phase-8 visibility surface exists.
- Phase 8's Planner story inherits a clean projector contract: read the spanning log, filter on `kind == "requires_multi_plugin_coordination"`, project. No mutation; no Phase-7 state to reconcile.
- If Phase 7 implementation work surfaces a real need for coordinator behavior earlier (e.g., a CVE pattern that requires synchronous resolution), the response is an ADR amendment to ADR-0042 — not a quiet Phase-7 addition.

## Reversibility

**Low.** Once Phase 8 lands a Planner against the `RequiresMultiPluginCoordination` event shape, restructuring Phase 7 to ship a coordinator would force Phase 8 to migrate. The cost of the reversal compounds with every consumer (Phase 11 merge-gate, Phase 13.5 operator portal). The contract-style fence on Phase 7's `events.py` makes drift visible at every PR — that's a feature.

## Evidence / sources

- `../final-design.md §Lens summary §1`, §Synthesis ledger row 1 (score 15/15), §Departures from all three inputs #1
- `../phase-arch-design.md §Executive summary`, §Component design §13 (`RequiresMultiPluginCoordination` event), §Patterns considered and deliberately rejected
- `../critique.md §Attacks on the performance-first design §1`, §Attacks on the security-first design §1, §Cross-design observations "Which disagreement matters most for this phase?", §Roadmap-level critiques §1
- [production ADR-0042 — Multi-plugin coordination for `Both` workflows](../../../production/adrs/0042-multi-plugin-coordination-for-both-workflows.md)
- [production ADR-0034 — Event sourcing canonical primitive](../../../production/adrs/0034-event-sourcing-canonical-primitive.md)
- [production ADR-0038 — Vulnerability provenance attribution](../../../production/adrs/0038-vulnerability-provenance-attribution.md)
