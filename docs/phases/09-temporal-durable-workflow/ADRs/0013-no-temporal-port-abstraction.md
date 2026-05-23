# ADR-0013: No `TemporalPort` / durable-execution abstraction (premature pluggability)

**Status:** Accepted
**Date:** 2026-05-23
**Tags:** anti-decision · premature-abstraction · YAGNI · pattern-soup
**Related:** [ADR-0011](0011-checkpointer-backend-postgres.md), [production ADR-0003](../../../production/adrs/0003-temporal-as-workflow-substrate.md)

## Context

A tempting architectural move when adopting Temporal is to introduce a `TemporalPort` / `DurableExecutionPort` Protocol so the application code talks to "some durable workflow substrate" rather than to Temporal directly. This buys, in theory, substrate-swap reversibility: if Temporal turns out to be wrong, the application can swap to AWS Step Functions, Cadence, or a homegrown alternative by writing a new Adapter.

The toolkit calls this **premature pluggability**: a Port with one implementation is shape-only, has no validating second implementation that would actually catch interface drift, and pays ceremony on every Temporal API surface. Production ADR-0003 already named the substrate (Temporal) and costed substrate-swap reversibility as "Medium" — known cost, acknowledged once, not re-litigated on every phase.

The critic-design-pattern review flagged the absence of a `TemporalPort` as the strongest "missed Port" candidate in the parallel designs; on inspection, all three parallel designs ([P], [B], [S]) declined to introduce one. The synthesis reaffirms the no-Port stance with the toolkit anti-pattern citation.

## Options considered

- **Introduce `TemporalPort` Protocol with `TemporalAdapter` as the only implementation.** Application code talks to the Port. **Pattern:** Port-and-Adapter / Hexagonal. Shape-only with one impl; pays ceremony on every workflow/activity API; no second implementation to validate the interface.
- **Introduce `TemporalPort` Protocol AND a `LocalTestDurableAdapter` for tests.** Two implementations — one production, one for tests. **Pattern:** Port-and-Adapter with test double. The test double would re-implement Temporal's replay-determinism and durability semantics — non-trivial; tests would diverge from production behavior.
- **No Port; talk to `temporalio` directly.** Application code uses `temporalio.workflow.execute_activity`, `temporalio.client.Client`, `@workflow.defn`, etc. **Pattern:** direct dependency. Acknowledges the substrate; ADR-0003's reversibility cost is documented, not amortized via Port ceremony.

## Decision

Phase 9 introduces **no `TemporalPort` / `DurableExecutionPort`**. Workflow and activity code uses `temporalio` directly. The substrate-swap reversibility cost is documented in [production ADR-0003](../../../production/adrs/0003-temporal-as-workflow-substrate.md) (Medium) and not pre-paid here. **Pattern: anti-decision — premature pluggability rejected; direct dependency embraced.**

## Tradeoffs

| Gain | Cost |
|---|---|
| No ceremony on every Temporal API surface (`workflow.execute_activity`, `workflow.signal`, `workflow.query`, `client.start_workflow`, etc.) | Substrate swap is a multi-phase rewrite, not a one-Adapter swap |
| One implementation, no shape-only Protocol with no validating second impl | Auditors expecting "we abstract over our durable substrate" need education on why a single-impl Port is worse, not better |
| Tests can use `temporalio.testing.WorkflowEnvironment` directly — the real Temporal SDK has built-in test support | Tests cannot run without `temporalio` installed; production-dependency in test-time path |
| `temporalio` SDK idioms (`@workflow.defn`, `@activity.defn`, `RetryPolicy`, `Worker`, `Client`) are visible at the application surface — engineers learn the SDK | If the engineering team rotates and "we abstract over Temporal" sounded clean in the abstract, the no-Port stance must be re-defended |
| Phase 16's production cluster topology change ([phase-arch-design.md §Non-goals](../phase-arch-design.md#non-goals)) is *internal* to Temporal — does not require an Adapter change | Phase 9 cannot dual-write to a hypothetical second substrate during a migration; the production ADR-0003 substrate decision is load-bearing |

## Pattern fit

The toolkit's `design-patterns-toolkit.md §Premature pluggability` is the explicit anti-pattern this rejects: "a Port with one implementation that doesn't translate or unify multiple backends is shape-only ceremony — it pays cost on every API surface and buys nothing because no second implementation pressure-tests the interface". The critic-design-pattern review of the parallel designs explicitly flagged this as the strongest "missed Port" candidate; on inspection, the parallel-design consensus was correct to omit it. Production ADR-0003 named the substrate; further amortization is over-design.

The genuine Adapters Phase 9 *does* introduce (`PostgresCheckpointerAdapter` per [ADR-0011](0011-checkpointer-backend-postgres.md); `TemporalVulnRemediationSut` per [phase-arch-design.md §C3](../phase-arch-design.md#c3--langgraph--temporal-bridge-codegeniedurablebridge)) translate — they earn the pattern name. A `TemporalPort` would not.

## Consequences

- `codegenie.durable.workflows.*` imports `temporalio.workflow` directly.
- `codegenie.durable.activities.*` imports `temporalio.activity` directly.
- `codegenie.durable.bridge.TemporalVulnRemediationSut` uses `temporalio.client.Client` directly.
- `codegenie.durable.workers.*` uses `temporalio.worker.Worker` directly.
- The `import-linter` contract for workflow-body determinism ([ADR-0004](0004-workflow-determinism-enforcement-three-layers.md)) operates on the Temporal-direct imports — no Port indirection to fence past.
- Tests use `temporalio.testing.WorkflowEnvironment` and `temporalio.testing.WorkflowReplayer` directly.
- If a future phase actually needs to swap durable substrate, the work is in scope of that phase — multi-phase rewrite acknowledged.
- The `TemporalVulnRemediationSut` adapter (which *does* translate Phase-6's `VulnRemediationSut` Protocol to the Temporal substrate) is the genuine port — proves the no-`TemporalPort` decision doesn't preclude having narrower, translating Adapters where they earn their keep.

## Reversibility

**High.** Introducing a `TemporalPort` later is additive — wrap `temporalio` calls in a Port, point application code at it. The work scales with API surface, but each step is local. This ADR is reversible by adding the Port; it is not reversible by un-removing it (you can't un-introduce ceremony cheaply).

## Evidence / sources

- [`../phase-arch-design.md §Non-goals — TemporalPort / durable-execution Port abstraction`](../phase-arch-design.md#non-goals)
- [`../phase-arch-design.md §Design patterns applied — Patterns considered and deliberately rejected`](../phase-arch-design.md#patterns-considered-and-deliberately-rejected)
- [`../final-design.md §Shared blind spots considered #1 — No TemporalPort`](../final-design.md)
- [`../final-design.md §Patterns considered and deliberately rejected`](../final-design.md)
- [`../critique.md §Design-pattern critiques — Missed patterns / Pattern claims that don't survive scrutiny`](../critique.md)
- [production ADR-0003](../../../production/adrs/0003-temporal-as-workflow-substrate.md) — substrate decision
- Toolkit: `~/.claude/skills/phase-architect/references/design-patterns-toolkit.md §Premature pluggability`
