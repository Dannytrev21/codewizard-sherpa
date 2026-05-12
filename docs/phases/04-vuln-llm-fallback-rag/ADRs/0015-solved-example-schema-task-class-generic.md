# ADR-0015: `SolvedExample` schema is task-class-generic (`task_class` as a field) so Phase 7 (Chainguard) and Phase 15 (recipe authoring) reuse the corpus

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** schema · task-class · phase-7-handoff · phase-15-handoff · synthesizer-departure
**Related:** [ADR-0002](0002-two-tier-writeback-pending-promoted.md), [ADR-0003](0003-plan-envelope-kind-and-target-files-allowlist.md), [production ADR-0028](../../../production/adrs/0028-task-class-introduction-order.md)

## Context

Phase 4 ships the first solved-example corpus. Phase 7 (Chainguard distroless migration) and Phase 15 (agentic recipe authoring) both consume it. The shape of the `SolvedExample` schema determines whether each later phase extends *by addition* or by *editing the schema*. The critic (`critique.md §roadmap.1`) attacked all three lens designs for missing `(recipe_failure_reason, retrieved_example_ids, engine_used_trajectory)` — the three fields Phase 15 needs to cluster examples into recipe-promotion candidates.

The design picks a single schema with `task_class: Literal["vuln","chainguard","recipe_authoring"]` as a field — not a type. Phase 7 uses the same schema with `task_class="chainguard"`; Phase 15 reads the trajectory metadata that Phase 4 ships now.

## Options considered

- **One schema per task class (`VulnSolvedExample`, `ChainguardSolvedExample`, ...).** Each task class owns its types. Clean isolation but duplication of common fields and a Phase-7-time decision about which schema fields to share.
- **One schema with `task_class` as a Literal field.** Synth. Phase 7 extends by adding a value to the Literal and registering a `PathAllowlistProvider`. The chromadb collection stores task-class as metadata for filtering. Phase 15's clusterer queries by `(recipe_failure_reason, engine_used_trajectory)` across all task classes.
- **One schema with `task_class` as a string (no Literal).** No type discipline; Phase 7 won't catch typos at import time.

## Decision

`SolvedExample` carries `task_class: Literal["vuln","chainguard","recipe_authoring"]` (the values that exist as of Phase 4; Phase 7 extends). The full schema, frozen at v0.4.0 and snapshot-tested:

```python
class SolvedExample(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str
    schema_version: Literal["0.4.0"]
    task_class: Literal["vuln","chainguard","recipe_authoring"]
    ecosystem: Literal["npm","yarn","pnpm"]
    language: Literal["javascript","typescript"]
    advisory: AdvisoryRef
    repo_fingerprint: Fingerprint
    recipe_failure_reason: Literal[...]              # which Phase-3 engine skipped, and why
    engine_trajectory: list[EngineAttempt]           # for Phase 15 clustering
    plan: Plan
    diff_path: str
    embedding_model: str
    embedding_digest: str
    dimensions: int
    provenance: Provenance                           # carries merge_status lifecycle
    created_at: datetime
```

The chromadb collection stores `task_class` as filterable metadata. Phase 4 queries default to `task_class="vuln"`; Phase 7 will query `task_class="chainguard"`. Phase 15's clusterer queries by `(recipe_failure_reason, engine_trajectory)` across `task_class` if the recipe-promotion candidate is cross-class.

## Tradeoffs

| Gain | Cost |
|---|---|
| Phase 7 extends by adding a Literal value + registering `PathAllowlistProvider` — no `SolvedExample` schema edit | The Literal grows linearly with task classes; future Literal value adds touch the schema-version-pinned model — surfaced as a known concession |
| Phase 15 reads `(recipe_failure_reason, engine_trajectory, retrieved_example_ids)` from the corpus Phase 4 ships — no schema migration | Phase 4 must populate all three fields correctly from day one; engineer discipline matters |
| One chromadb collection per merge_status (pending/promoted) instead of one per task class — fewer collections, simpler swap to qdrant | Cross-task-class queries are filtered, not separated; mild query-complexity cost |
| `task_class` as a filterable metadata field means Phase 7's Chainguard queries don't accidentally surface vuln examples (and vice versa) | Operators must understand the filter; default is `task_class="vuln"` in Phase 4's CLI |
| Schema frozen at v0.4.0 with snapshot test means Phase 7+ extensions are conspicuous, not silent | Every Literal extension regenerates the snapshot test; same precedent as [ADR-0001](0001-recipe-engine-literal-extends-with-rag-llm.md) |
| `engine_trajectory: list[EngineAttempt]` captures the full path (`ncu/range_break → openrewrite/catalog_miss → rag_llm/llm_cold`) — Phase 15 can detect example clusters that consistently solve the same problem shape | One more field to populate; engineer must remember to record all attempts, not just the successful one |

## Consequences

- `SolvedExample`, `Provenance`, `Plan`, `LlmRequest`, `LlmResponse`, `QueryKey`, `EngineAttempt`, `Fingerprint`, `AdvisoryRef` — the public contracts frozen at v0.4.0. Snapshot tests cover all.
- `task_class` is in the `QueryKey` tuple ([phase-arch-design.md §"Component design"](../phase-arch-design.md) #5) so Phase 7's Chainguard cache doesn't collide with Phase 4's vuln cache.
- Phase 7 lands `vuln_solved_examples_promoted` → `solved_examples_promoted` collection rename + `task_class` filter migration. Done as a Phase 7 ADR amendment with a one-time migration script.
- Phase 15's recipe-authoring clusterer reads `(recipe_failure_reason, engine_trajectory)` to detect candidate recipes. The trajectory must include all attempted engines, not just the successful one — `RecipeApplication` already carries this from Phase 3.
- `RecipeFailureReason` Literal values: `{catalog_miss, range_break, peer_dep_conflict, no_engine, unsupported_dialect}`. Phase 4 surfaces all five; Phase 7 may add Chainguard-specific reasons.
- The `negative` collection (failed-apply examples) shares the schema. Phase 15 may use negatives as anti-patterns; the `provenance.merge_status="withdrawn"` value covers retraction.

## Reversibility

**Low.** Splitting `SolvedExample` per task class means migrating every stored example, regenerating every chromadb collection, and editing every Phase 4+ consumer. The Literal expansion mechanism is durable; the *one-schema* commitment is the load-bearing piece.

## Evidence / sources

- `../final-design.md §"Components"` #7 — `SolvedExample` schema (task-class-generic)
- `../final-design.md §"Roadmap coherence check"` — Phase 7, 15 consumption
- `../phase-arch-design.md §"Data model"` — `SolvedExample` + frozen contracts
- `../phase-arch-design.md §"Integration with Phase 5"` — schema as future-phase consumption surface
- `../critique.md §roadmap.1` — Phase 15 needs all three fields
- Production [ADR-0028](../../../production/adrs/0028-task-class-introduction-order.md) — task-class introduction order
