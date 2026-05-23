# ADR-0010: Asymmetric activity granularity — 1:1 for Phase-8 Supervisor; one fat Activity for Phase-6 SHERPA subgraph

**Status:** Accepted
**Date:** 2026-05-23
**Tags:** activity-decomposition · adapter · SutDigest · backward-compatibility
**Related:** [ADR-0011](0011-checkpointer-backend-postgres.md), [ADR-0014](0014-multi-plugin-parent-workflow-as-temporal-shape.md)

## Context

The fundamental wrap-vs-decompose decision for Phase 9 is: how granular should Temporal Activities be relative to the existing LangGraph node structure? Three positions emerged in the parallel designs:

- **[P]/[B] position:** One Activity per LangGraph node. Maximum observability via Temporal-history; per-node retry; per-node compactness. The Phase-8 Supervisor (`resolve_plugin`, `build_bundle`, `route`) was designed *to be* the Temporal seam — its three nodes map cleanly to three Activities.
- **[S] position:** One fat Activity for the whole LangGraph subgraph. Minimum churn to the inner Phase-6 SHERPA code; the LangGraph state machine survives intact.

The critic's destruction surfaced the load-bearing constraint: the **Phase-6 `SutDigest` contract** depends on the in-process LangGraph checkpoint structure. The Phase-6.5 conformance harness (`tests/conformance/sut/*`) hashes the workflow's intermediate state into a deterministic `SutDigest`; this digest must be byte-identical across every Phase-6 canonical case when run through either `LocalVulnRemediationSut` or the Phase-9-wrapped `TemporalVulnRemediationSut` (G5 exit criterion). Decomposing the SHERPA subgraph into one-Activity-per-node would shatter the checkpoint structure: each node would have its own Temporal-history record, the LangGraph state machine would be reconstructed from those records, and the resulting checkpoint shape would not match the in-process baseline.

The Phase-8 Supervisor has no such constraint — it was designed to be the Temporal seam from the start.

## Options considered

- **Uniform 1:1 decomposition.** Every LangGraph node → its own Activity. **Pattern:** uniform Adapter granularity. Optimal observability; shatters `SutDigest`; non-trivial Phase-6 churn.
- **Uniform fat-Activity wrap.** Every LangGraph subgraph wrapped in one Activity. **Pattern:** uniform Adapter coarseness. Preserves `SutDigest`; loses the Phase-8 Supervisor's natural per-node seam; Temporal-history is coarse for Supervisor decisions that are inherently three-step.
- **Asymmetric: 1:1 for Phase-8 Supervisor; one fat Activity for Phase-6 SHERPA subgraph.** Each lens applied where it earns its keep. **Pattern:** context-sensitive Adapter granularity.

## Decision

The Phase-8 Supervisor's three nodes (`resolve_plugin`, `build_bundle`, `route`) map **1:1 to Activities** (the [P]/[B] shape); the Phase-6 SHERPA subgraph runs inside **one fat `run_vuln_subgraph` Activity** (the [S] shape) which preserves the `SutDigest` contract. The LangGraph checkpoint structure inside `run_vuln_subgraph` is unchanged; the Phase-6 hash-chained log mirrors forward into the canonical event log via `emit_event` calls inside the Activity. **Pattern: context-sensitive Adapter granularity, driven by an existing typed contract.**

## Tradeoffs

| Gain | Cost |
|---|---|
| `SutDigest` invariance — G5 exit criterion is reachable | Temporal cannot see *which* LangGraph node failed inside `run_vuln_subgraph` — only that the Activity failed |
| Phase-6 SHERPA code is unchanged — minimum migration risk | Node-level audit detail comes from the Phase-6 hash-chained log mirrored forward, not Temporal history |
| Phase-8 Supervisor's per-node observability is preserved (three Activities, three history records) | Two different patterns coexist in the codebase; engineers must remember why |
| `run_vuln_subgraph` has its own 20-min `start_to_close_timeout` — appropriately coarse for a multi-minute subgraph | The fat Activity is closer to the 2 MiB-per-event Temporal cap; payload-by-reference ([ADR-0005](0005-payload-by-reference-blobref-threshold.md)) is more load-bearing here |
| `run_vuln_subgraph`'s heartbeat (every 5 s) + LangGraph PostgresSaver checkpoints give node-level resume on activity-worker SIGKILL | Heartbeat overhead is non-zero; ~5 ms / 5 s while the activity runs |
| Phase 7.5 / Phase 10 may apply the [P]/[B] shape to *new* Supervisor stages without disrupting existing SHERPA subgraphs | The decision is per-subgraph; new subgraphs need a written rationale for which shape applies |

## Pattern fit

Context-sensitive Adapter granularity (toolkit `design-patterns-toolkit.md §Adapter pattern variants`) is the right shape when "the same Port has implementations with very different internal contracts to preserve". The Phase-8 Supervisor and the Phase-6 SHERPA subgraph are both LangGraph subgraphs, but only one of them has a downstream `SutDigest` contract pinning its checkpoint structure. Applying one pattern uniformly to both would either (a) shatter the digest contract (1:1) or (b) lose the natural seam in the Supervisor (fat). Asymmetric application earns the right pattern in each context.

## Consequences

- `codegenie.durable.activities.run_vuln_subgraph` is one Activity ~20-min `start_to_close_timeout`, heartbeating every 5 s.
- Inside `run_vuln_subgraph`, the Phase-6 LangGraph + `PostgresCheckpointerAdapter` ([ADR-0011](0011-checkpointer-backend-postgres.md)) provides node-level checkpoints; the Phase-8 hash-chained log emits forward via `emit_event` so node-level audit lands in the canonical log.
- `codegenie.durable.activities.{resolve_plugin, build_bundle, route}` are three separate Activities, each with its own `RetryPolicy`.
- The G5 exit-criterion test (`tests/durability/test_sut_digest_invariance.py`) runs every Phase-6 canonical case through both `LocalVulnRemediationSut` and `TemporalVulnRemediationSut` under `freezegun` and asserts byte-equal `SutDigest`.
- Temporal-history granularity is **coarser** than per-node for the SHERPA subgraph; auditors must read the canonical event log for node-level detail.
- Phase 10's continue-as-new question (deferred, [phase-arch-design.md §Open questions #1](../phase-arch-design.md#open-questions-deferred-to-implementation)) is specific to `run_vuln_subgraph` — the fat-Activity shape forces this question; the 1:1 shape would have made it moot.
- Phase 7.5 / Phase 10 / new task classes that introduce new Supervisor-style subgraphs may apply the 1:1 shape; new SHERPA-style subgraphs with `SutDigest` contracts apply the fat-Activity shape.

## Reversibility

**Medium.** Decomposing `run_vuln_subgraph` into per-node Activities later is a refactor that necessarily breaks `SutDigest` invariance — Phase-6.5 conformance fixtures must be regenerated, which is exactly the work the asymmetric shape avoids paying now. Going the other direction (collapsing the Supervisor's three Activities into one) is cheaper but loses observability.

## Evidence / sources

- [`../phase-arch-design.md §Executive summary — asymmetric shape choice`](../phase-arch-design.md#executive-summary)
- [`../phase-arch-design.md §Goals G5 — SutDigest invariance`](../phase-arch-design.md#goals)
- [`../phase-arch-design.md §C3 — LangGraph ↔ Temporal bridge`](../phase-arch-design.md#c3--langgraph--temporal-bridge-codegeniedurablebridge)
- [`../phase-arch-design.md §Tradeoffs (consolidated)`](../phase-arch-design.md#tradeoffs-consolidated)
- [`../final-design.md §Departures from all three inputs #1`](../final-design.md)
- [`../final-design.md §Synthesis ledger — workflow body composition row`](../final-design.md)
