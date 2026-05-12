# ADR-0002: Two-tier solved-example writeback — `pending/` shelf + `promoted/` corpus + `provenance.merge_status` lifecycle

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** writeback · trust-gate · phase-11-handoff · synthesizer-departure · adr-0009-fit
**Related:** [ADR-0001](0001-recipe-engine-literal-extends-with-rag-llm.md), [ADR-0005](0005-chromadb-in-process-with-stale-lock-detection.md), [production ADR-0009](../../../production/adrs/0009-humans-always-merge.md), [production ADR-0011](../../../production/adrs/0011-recipe-first-rag-llm-fallback-planning.md)

## Context

The roadmap Phase 4 exit criterion says: "A breaking-change vuln is solved end-to-end with the LLM fallback and recorded into the solved-example store. Re-running the same case hits RAG, not LLM." [Production ADR-0009](../../../production/adrs/0009-humans-always-merge.md) says humans always merge. Phase 4 ships locally — no PR opens, no human merges anything. Three lens designs reached three incompatible answers (`final-design.md §"Synthesis ledger"` row "Writeback timing"):

- Performance: fire-and-forget at `TrustScorer.passed`. Meets the exit criterion but writes un-merged LLM output into the corpus that gates every future workflow — a literal ADR-0009 violation that Phase 11 would have to roll back.
- Best-practices: synchronous write at `TrustScorer.passed`. Same ADR-0009 problem; differs only in durability.
- Security: gate writeback on operator `codegenie rag accept --merge-sha ... --reviewer ...`. Honors ADR-0009 but cannot meet the exit criterion locally because Phase 4 has no merge SHA.

The critic flagged this as the load-bearing disagreement (`critique.md §"Which disagreement matters most"`): the synthesizer must structurally pick which way the criterion is met *and* document the Phase 11 migration.

## Options considered

- **Single corpus, fire-and-forget on validation pass.** Performance-lens. Meets the exit criterion at the cost of an un-merged corpus gating every future workflow.
- **Single corpus, gated on human merge.** Security-lens. Honors ADR-0009 but Phase 4 has no merge SHA available; the exit criterion is unmeetable locally without an out-of-band manual fake-merge step.
- **Two-tier corpus with merge-status lifecycle.** Solved examples land in a `pending/` shelf on `TrustScorer.passed`. A separate `promoted/` corpus is the one production portfolio scans default to. Phase 11's `pull_request.closed` webhook is the real promoter. Phase 4 ships an opt-in `--auto-promote-on-validation-pass` flag (off by default; on for the E2E exit-criterion fixture).
- **No writeback in Phase 4, exit criterion reinterpreted.** Defer the writeback entirely to Phase 11. Cleanest ADR-0009 fit but means the "compounding savings" story stays unmeasurable until Phase 11 ships.

## Decision

Solved examples write to a two-tier store. `SolvedExampleWriter.write_pending` lands them in `.codegenie/rag/pending/<id>.json` with `provenance.merge_status="pending_human"` after `TrustScorer.passed && engine_used == "rag_llm"`. Production portfolio scans query `promoted/` only (default `include_pending=False`). The E2E exit-criterion fixture enables `--auto-promote-on-validation-pass`, which calls `SolvedExamplePromoter.promote(reason="validation_pass_auto")` to move the example to `promoted/` *and* emits a loud `solved_example.promoted_without_merge` audit event so any production use is conspicuously visible. Phase 11 ships the real promoter `promote(reason="human_merge", merge_sha=..., reviewer=...)` — same API, different `reason` argument.

## Tradeoffs

| Gain | Cost |
|---|---|
| Exit criterion is locally provable without violating ADR-0009 in spirit — production defaults never gate on un-merged output | Two corpus directories, two chromadb collections, one extra flag — operational surface area grows |
| Phase 11 promoter is a straight swap of `reason="human_merge"` for `reason="validation_pass_auto"` — no rewrite, no rollback of Phase 4 data | The `pending/` shelf is a *temporary* corpus operators must understand; misuse via `--include-pending` in portfolio scans is plausible (mitigated by audit events + dashboard alerts) |
| `provenance.merge_status` lifecycle (`pending_human` → `merged` → `withdrawn`) is the durable schema Phase 11's webhook writes into | Same-workflow re-runs and the E2E test require an explicit `--include-pending` flag; default-off means most operators never see the shelf |
| Every promotion emits `solved_example.promoted_without_merge` when `reason != "human_merge"` — audit trail captures every auto-promote | `SolvedExamplePromoter` is a new public method that didn't exist before; one more API surface to maintain |
| Strict writeback guard (`engine_used == "rag_llm"` AND `TrustScorer.passed` AND `plan_source ∈ {rag_fewshot_llm, llm_cold}`) prevents cache hits or RAG-exact replays from double-counting | Two collections in chromadb instead of one; ~50 MB additional disk per 1k examples |

## Consequences

- `SolvedExample.provenance.merge_status: Literal["pending_human","merged","withdrawn"]` is a stable contract Phase 11's webhook writes to. Phase 4 never writes anything other than `pending_human`.
- `writeback_solved_example` refuses to write when `engine_used != "rag_llm"`, `TrustScorer.passed != True`, or `plan_source ∈ {query_cache, rag_exact}` (the example already exists). Emits `solved_example.writeback_refused(reason)` audit event.
- The `--auto-promote-on-validation-pass` flag defaults *off*; the E2E fixture flips it. A blanket-enabled portfolio wrapper script triggers `solved_example.promoted_without_merge` audit events at scale — dashboard alert at first threshold breach.
- Phase 11's promoter cross-references `merge_sha` against the run's BLAKE3 audit chain and the repo's git history before promoting. The verification logic ships in Phase 11; Phase 4's `promote(reason="validation_pass_auto")` skips it (audit captures the skip).
- Cross-repo retrieval is double-gated: same-repo OR `provenance.public == True` by default; widening requires both `--allow-cross-repo-rag` AND env `CODEGENIE_ALLOW_PRIVATE_CROSS_REPO=1`.
- `SolvedExample.engine_trajectory` records the full path (`ncu/range_break → openrewrite/catalog_miss → rag_llm/llm_cold`); Phase 15's recipe-clusterer reads this to detect candidate recipes.

## Reversibility

**Medium.** Removing the two-tier model means migrating `pending/` content into `promoted/` (the Phase 11 promoter does this on real merges anyway) and dropping one collection + one flag. The decision is durable on the schema side (`provenance.merge_status`) but the *split* is conceptual — collapsing back to one corpus is a script-and-an-ADR-amendment. Phase 11's contract assumes the split exists; reverting would require a Phase 11 amendment too.

## Evidence / sources

- `../final-design.md §"Synthesis ledger" §"Conflict-resolution table"` row "Writeback timing" — winner sum 12/12
- `../final-design.md §"Departures from all three inputs"` #1
- `../final-design.md §"Components"` #7 — Two-tier corpus, promoter API
- `../phase-arch-design.md §"Component design"` #6 — `writeback_solved_example` strict guard
- `../phase-arch-design.md §"Gap analysis"` Gap 4 — `--no-rag` / `--no-llm` interaction
- `../critique.md §"Which disagreement matters most"` — writeback timing is the load-bearing fight
- Production [ADR-0009](../../../production/adrs/0009-humans-always-merge.md) — humans always merge
- Production [ADR-0011](../../../production/adrs/0011-recipe-first-rag-llm-fallback-planning.md) — three-tier planning shape
