# ADR-0010: `cost.sandbox.run` ledger entry schema is a Phase 5 contract

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** cost-ledger · phase-13-handoff · contract
**Related:** [ADR-0004](0004-dind-default-macos-with-gate-isolation-class.md), [production ADR-0024](../../../production/adrs/0024-cost-observability-end-to-end.md), [production ADR-0025](../../../production/adrs/0025-per-workflow-cost-cap.md)

## Context

The synthesis declares "Phase 5 emits `cost.sandbox.run` ledger entries." Phase 13 (cost ledger) consumes them. But no Pydantic schema is given, no file path is named, no contract test exists. If Phase 5 emits a different shape than Phase 13 expects, Phase 13's dashboard silently undercounts — a fail-loud violation. See [phase-arch-design.md §Gap analysis Gap 5](../phase-arch-design.md#gap-5-cost-ledger-emission-shape-is-not-specified--phase-13-reads-it-but-phase-5-doesnt-define-it).

## Options considered

- **Defer to Phase 13** — Phase 13 defines the schema; Phase 5 just appends to the ledger. Phase 5 ships without a contract; Phase 13 retroactively constrains Phase 5. Cross-phase break risk is high.
- **Free-form JSONL** — Phase 5 writes whatever fields it has; Phase 13 reads what it can. Loses fail-loud — schema drift produces silent undercounting.
- **Phase 5 owns the schema** — Pydantic `SandboxCostEntry` with `extra="forbid", frozen=True`; file path `.codegenie/cost/sandbox.jsonl`; one entry per attempt; contract test in Phase 5.

## Decision

Phase 5 owns the `SandboxCostEntry` Pydantic model and the file path `.codegenie/cost/sandbox.jsonl`. One entry per `GateRunner` attempt, emitted post-`RetryLedger.record` by a `CostEmitter` in `src/codegenie/sandbox/cost.py`. Schema is part of the Phase 5 stable contract surface.

## Tradeoffs

| Gain | Cost |
|---|---|
| Phase 13 reads a frozen contract; no silent undercounting | Phase 5 owns a cost-ledger shape Phase 13 will eventually want to extend (additive ADR amendments are the path) |
| `extra="forbid"` + contract test fail loudly on shape drift | Adding a backend-specific field (e.g., a Firecracker kernel feature flag) requires Pydantic field + ADR amendment |
| One entry per attempt aligns with `attempts.jsonl` (1:1) — joining is trivial | The ledger has `microvm_seconds` even when backend is `docker_in_docker` (always 0.0 for non-microVM) — readers must understand the semantic |
| Phase 13's per-workflow cost cap ([ADR-0025](../../../production/adrs/0025-per-workflow-cost-cap.md)) can sum sandbox cost without recomputing | Cost cap composition with retries is a Phase 13 design decision (open Q5); Phase 5 just emits |

## Consequences

- `src/codegenie/sandbox/cost.py` defines `SandboxCostEntry` and `CostEmitter`.
- `SandboxCostEntry` fields: `entry_type: Literal["cost.sandbox.run"]`, `workflow_id`, `run_id`, `gate_id`, `sandbox_run_id`, `backend`, `gate_isolation_class`, `microvm_seconds`, `image_pull_bytes`, `build_cache_hit`, `emitted_at`.
- `GateRunner.run` wires `CostEmitter.emit(entry)` post-attempt-record.
- `tests/sandbox/test_cost_emitter.py` asserts: one entry per attempt; byte-stable schema (golden file); append-only.
- Phase 13 reads from `.codegenie/cost/sandbox.jsonl` and aggregates by `(workflow_id, gate_isolation_class)` for the ROI dashboard ([ADR-0026](../../../production/adrs/0026-roi-kpi-model.md)).
- New invariant: any new backend implements `SandboxRun.microvm_seconds` and `image_pull_bytes`; absent values default to 0 (explicit, not `None`).

## Reversibility

**Medium.** Adding a field is an additive ADR amendment; removing a field breaks Phase 13. The file path and entry type are the load-bearing parts — both are easy to add a second emitter for if a parallel ledger is wanted, but renaming is a Phase 5 + Phase 13 dual-PR.

## Evidence / sources

- [phase-arch-design.md §Gap analysis Gap 5](../phase-arch-design.md#gap-5-cost-ledger-emission-shape-is-not-specified--phase-13-reads-it-but-phase-5-doesnt-define-it)
- [phase-arch-design.md §Goals 13](../phase-arch-design.md#goals)
- [phase-arch-design.md §Roadmap coherence check — Phase 13](../phase-arch-design.md#integration-with-phase-6-next-phase)
- [production ADR-0024](../../../production/adrs/0024-cost-observability-end-to-end.md)
- [production ADR-0025](../../../production/adrs/0025-per-workflow-cost-cap.md)
