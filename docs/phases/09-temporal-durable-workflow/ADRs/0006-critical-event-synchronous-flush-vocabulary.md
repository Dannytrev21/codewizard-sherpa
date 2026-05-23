# ADR-0006: `@critical_event` synchronous-flush vocabulary

**Status:** Accepted
**Date:** 2026-05-23
**Tags:** Open/Closed · decorator-registry · event-sourcing · durability
**Related:** [ADR-0003](0003-per-workflow-blake3-prev-hash-chain.md), [production ADR-0034](../../../production/adrs/0034-event-sourcing-canonical-primitive.md)

## Context

The `EventBatchWriter` flushes events to Postgres on a 20 ms / 256-event boundary to hit the G6 throughput target (≥ 3k events/sec). Some events, however, cannot afford to be lost in a worker crash mid-batch: a `MergeOutcome` that doesn't reach Postgres means a PR was merged but the audit log has no record; a `BudgetExhausted` that doesn't reach Postgres means the workflow looks under-budget on resume; a `TrustGateFailed` that doesn't reach Postgres weakens the safety claim. These events need synchronous-flush semantics: the activity returning means the event is durably stored.

The performance-first design [P] proposed extending synchronous-flush to a dozen events; the critic-correctness review trimmed the set to the events whose loss would compromise audit, safety, or cost claims. The vocabulary is small *and* stable enough to live in a registry; new critical events in future phases must be additive, not edits to the writer's flush logic.

## Options considered

- **All events synchronous.** Every append flushes immediately. **Pattern:** uniform sync. Kills throughput; G6 unreachable.
- **All events batched.** Every append rides the 20 ms / 256 batch. **Pattern:** uniform batch. Throughput great; audit-critical events lose durability guarantees on crash.
- **Hardcoded if-chain inside `EventBatchWriter`.** `if isinstance(e, MergeOutcome | BudgetExhausted | TrustGateFailed | WorkflowTerminated | ChainTamperDetected): flush_now()`. **Pattern:** none — closed enumeration as branches. New critical events require editing the writer.
- **Decorator-registry: `@critical_event` adds to a `_CRITICAL_EVENTS: Final[set[str]]` populated at import.** Writer checks `type(e).__name__ in _CRITICAL_EVENTS`. **Pattern:** Open/Closed via decorator-populated registry. New critical events are one decorator line on the Pydantic class.

## Decision

Five `@critical_event`-marked variants (`MergeOutcome`, `BudgetExhausted`, `TrustGateFailed`, `WorkflowTerminated`, `ChainTamperDetected`) take the synchronous-flush path; everything else rides the 20 ms / 256-event batched COPY-binary path. The decorator populates a module-level frozen registry at import time; the writer reads it on each append. **Pattern: Open/Closed via decorator-populated registry, same shape as `@register_probe` from Phase 0.**

## Tradeoffs

| Gain | Cost |
|---|---|
| Audit-critical events are durably stored when their activity returns — no "merged but unlogged" scenarios | Five events take ~10 ms commit instead of <1 ms batched; activities emitting them have wider latency |
| Throughput preserved for the other 16 event variants — G6 reachable | The decision of "what is critical" must be made once per event variant; promotion requires a code change |
| New critical events in future phases are one decorator line; the writer code is unchanged | The decorator-populated registry is global mutable state at module-import time — must be `Final` after import |
| Closed vocabulary in Phase 9 (~5 events) is enumerable; auditors can review the list at a glance | If the decorator is silently removed by a refactor, an event silently loses its sync flush — caught by `tests/fence/test_critical_event_vocabulary.py` (asserts the set against a hard-coded golden) |
| The vocabulary is the contract: "these five events cannot be silently lost" is a one-line statement | If a contributor adds `@critical_event` to a high-throughput event (`emit_event` for trace events), throughput regresses without an obvious failure |

## Pattern fit

Open/Closed via decorator-populated registries is the canonical pattern in this codebase (`@register_probe`, `@register_dep_graph_strategy`, `@register_index_freshness_check`). The toolkit calls this out (`design-patterns-toolkit.md §Open/Closed at the file boundary`) as the right shape when the set is "small, additive, and the decision of membership is local to the entity itself". The Pydantic event class declares its own criticality next to its definition — locality of decision matches locality of declaration.

## Consequences

- `codegenie.events.payloads` defines `critical_event(cls: type[T]) -> type[T]` that adds `cls.__name__` to `_CRITICAL_EVENTS: Final[set[str]]`.
- `EventBatchWriter.append` checks `type(event).__name__ in _CRITICAL_EVENTS`; if true, flush is immediate.
- `tests/fence/test_critical_event_vocabulary.py` asserts the set is exactly `{"MergeOutcome", "BudgetExhausted", "TrustGateFailed", "WorkflowTerminated", "ChainTamperDetected"}` — golden file; adding to the set requires updating the golden, which forces a code-review conversation about cost.
- Phase 10 / 11 / 13 may add critical events additively by the decorator + golden-file update; no edit to the writer.
- Synchronous-flush failure propagates to the activity caller; Temporal retries per the activity's `RetryPolicy`.
- An open question (deferred to implementation, [phase-arch-design.md §Open questions #2](../phase-arch-design.md#open-questions-deferred-to-implementation)) is whether `@critical_event` events should also write through the batcher for redundancy; current design does not.

## Reversibility

**High.** The decorator and registry are localized; switching to hardcoded if-chain (or to all-sync) is a small refactor. The vocabulary is data; promotion/demotion is a one-line move.

## Evidence / sources

- [`../phase-arch-design.md §C5 — EventBatchWriter`](../phase-arch-design.md#c5--canonical-event-log-codegenievntslog-codegenievntspayloads-codegenievntsblob_refs)
- [`../phase-arch-design.md §Data model — `@critical_event` decorator`](../phase-arch-design.md#eventpayload--discriminated-union-contract)
- [`../phase-arch-design.md §Design patterns applied — #8`](../phase-arch-design.md#design-patterns-applied)
- [`../final-design.md §Synthesis ledger — synchronous-flush vocabulary row`](../final-design.md)
- Precedent: `@register_probe` from `src/codegenie/probes/registry.py` (production codebase)
