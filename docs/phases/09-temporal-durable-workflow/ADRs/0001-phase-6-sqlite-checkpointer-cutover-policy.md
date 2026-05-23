# ADR-0001: Phase-6 SQLite checkpointer drain-don't-cutover policy

**Status:** Accepted
**Date:** 2026-05-23
**Tags:** Adapter · migration · backward-compatibility
**Related:** [ADR-0011](0011-checkpointer-backend-postgres.md), [production ADR-0016](../../../production/adrs/0016-checkpointer-backend.md)

## Context

Phase 6 ships the SHERPA subgraph with a SQLite checkpointer (per production ADR-0016's default-for-local-dev). Phase 9 replaces that with `langgraph-checkpoint-postgres` so workflows survive activity-worker SIGKILL across processes. At cutover, some in-flight Phase-6 workflows already have checkpoints on disk in the old SQLite file. The critic's roadmap critique flagged: a hard cutover would either (a) leave those workflows stranded with no checkpointer adapter that knows how to read them, or (b) require a one-shot SQLite→Postgres data migration tool that is itself a build target and a source of risk.

The choice shapes the upgrade story for every future production cluster as well: does Phase 9 own a forward-migrate script, or does it lean on the existing two checkpointer implementations co-existing?

## Options considered

- **Hard cutover with one-shot migration script.** Build `codegenie migrate-checkpoints` that reads SQLite files, transforms node-state JSON, writes to Postgres, and swaps the workflow's stored `checkpointer = <name>` field. **Pattern:** big-bang migration.
- **Parallel writes (dual-writing) during a window.** Every checkpoint write goes to both stores; reads prefer Postgres. **Pattern:** strangler-fig dual write.
- **Drain-don't-cutover.** Existing SQLite-backed workflows complete on SQLite using the existing Phase-6 saver; new workflows start on Postgres via the new `PostgresCheckpointerAdapter`. Each workflow carries its checkpointer type in its stored config so the right saver is selected on resume. After the longest-running workflow drains, the SQLite path is removed in a follow-up phase. **Pattern:** strangler-fig with natural drain.

## Decision

Phase-9 workers select the checkpointer per-workflow from the workflow's stored config field; existing Phase-6 SQLite workflows continue on `SqliteSaver`, new workflows start on `PostgresCheckpointerAdapter`. No migration script is written. A CI canary asserts no SQLite-backed workflow is in flight before any follow-up phase can land the deletion PR. **Pattern: strangler-fig with natural drain.**

## Tradeoffs

| Gain | Cost |
|---|---|
| Zero migration code — the riskiest piece doesn't exist | Two checkpointer implementations live in-tree for one phase window |
| No "freeze cluster, migrate, thaw" outage in production | Phase-9 worker has a runtime branch on saver type at workflow startup (not in workflow body — selected once when the workflow is rehydrated) |
| In-flight Phase-6 workflows are byte-stable; no risk of subtle JSON-shape drift on migrated state | Cutover window length = longest-running workflow's residual duration (bounded by the workflow's `start_to_close_timeout`) |
| Easy rollback — if Postgres adapter has a bug, new workflows can flip back to SQLite without touching the old ones | A CI canary must enforce "no SQLite-backed workflow in flight" before the deletion PR — operational coupling between phases |
| Adheres to ADR-0043 "extension by addition" — Postgres saver added, SQLite saver removed only when empirically unused | The follow-up phase that removes the SQLite saver becomes a coordination point |

## Pattern fit

Strangler-fig (Fowler) is the canonical pattern for "two implementations, one is being phased out, traffic naturally drains from old to new". The toolkit's `design-patterns-toolkit.md §Migration patterns` calls out strangler-fig as the default when "the cost of a hard cutover is higher than the cost of carrying two implementations briefly". Both implementations conform to the same `LangGraphCheckpointerPort` Protocol — the selection happens at the workflow boundary, not inside the body.

## Consequences

- Phase 9 ships `PostgresCheckpointerAdapter` ([phase-arch-design.md §C4](../phase-arch-design.md#c4--postgres-checkpointer-adapter-codegeniedurablecheckpointer)); the existing `SqliteSaver` from Phase 6 is untouched.
- Workflow stored config carries a `checkpointer_kind` field; new workflows write `"postgres"`, in-flight Phase-6 workflows already have `"sqlite"` (or `null` → default-`sqlite`).
- A CI canary (`tests/durability/test_no_sqlite_workflow_in_flight.py`) blocks any deletion PR that would remove the SQLite path while a workflow still depends on it.
- Phase 10's first PR (per ADR-0002's neighbor cutover) can include the SQLite saver removal if the canary is green.
- No SQLite→Postgres data-migration tool is written — operational simplicity at the cost of one extra checkpointer in-tree.
- Production cluster upgrades inherit the same pattern: never migrate workflow checkpoint state; drain.

## Reversibility

**High.** The Phase-6 `SqliteSaver` is unchanged code; reverting Phase 9's saver-selection branch to always-SQLite is one config flip. Postgres data is not load-bearing during the drain (only new workflows write there); if Postgres path is found broken at week-1 of Phase 9, we revert and continue on SQLite while fixing the Postgres adapter.

## Evidence / sources

- [`../final-design.md §Synthesis ledger — Phase-6 SQLite cutover row`](../final-design.md)
- [`../final-design.md §4 Postgres checkpointer adapter — Phase-6 SQLite migration bullet`](../final-design.md)
- [`../phase-arch-design.md §C4`](../phase-arch-design.md#c4--postgres-checkpointer-adapter-codegeniedurablecheckpointer)
- [`../phase-arch-design.md §Edge case 18`](../phase-arch-design.md#edge-cases)
- [production ADR-0016](../../../production/adrs/0016-checkpointer-backend.md) (deferred — Phase 9 resolves; see [ADR-0011](0011-checkpointer-backend-postgres.md))
- Fowler, *Strangler Fig Application* — pattern reference
