# ADR-0004: `FallbackTier.run` gains `task_type: str | None = None` kwarg

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** phase4-contract · planner · task-class-routing · additive-seam
**Related:** [ADR-0001](0001-six-named-additive-seams-and-adr-0028-amendment.md), [ADR-0009](0009-contract-surface-snapshot-canary.md), [production ADR-0011](../../../production/adrs/0011-recipe-first-rag-llm-fallback-planning.md)

## Context

Phase 4 shipped `FallbackTier.run(advisory, repo_ctx, recipe_selection, *, run_id, include_pending, auto_promote, prior_attempts=[]) -> FallbackTierResult` — a vuln-shaped signature with no notion of task class (`critique.md §best-practices.1`). All three Phase 7 lens designs assume task-class-routed prompts and corpora exist:

- `[P]` hand-waves it as "a distroless solved-example corpus shard."
- `[S]` says "Phase 4 LLM fallback (called only on retry-2)" without explaining routing.
- `[B]` explicitly flags it as Open Question #3 and proposes an explicit `task_type` kwarg.

The critic landed (`§best-practices.1`): without Phase 4 routing on task type, the RAG-fallback and LLM-fallback paths in Phase 7 produce vuln-shaped patches for distroless inputs — the gate fails consistently and every fallback workflow escalates to retry-3 → human. Production ADR-0011 (recipe-first → RAG → LLM-fallback) is broken at the third stage for distroless.

The synthesizer must either (a) edit Phase 4's signature additively, (b) ship a parallel `MigrationFallbackTier` mirroring `FallbackTier.run` (the strict-zero-edit alternative — `final-design.md §"Departures #5"`), or (c) route by call-site monkey-patching the prompt selection. Option (c) is rejected on transparency grounds; option (b) doubles Phase 8's merge work; option (a) is one default-`None` kwarg.

## Options considered

- **Parallel `MigrationFallbackTier` class with the same signature plus `task_type`.** Zero Phase 4 edit; doubles Phase 8's merge surface. The synthesizer-documented strict-zero-edit alternative.
- **New required positional `task_type` argument.** Behavior-breaking for every existing Phase 4/6 callsite — fails contract-surface snapshot loudly and is not a *behavior-preserving* additive change.
- **New kwarg `task_type: str | None = None`.** Default keeps every existing vuln callsite byte-identical; explicit `task_type="distroless_migration"` opts in to the distroless prompt + corpus. The synthesizer's pick.
- **Corpus-level routing (no API edit).** Phase 4 silently looks up `task_type` from `repo_ctx` or `advisory`. Implicit; brittle on cross-task supervisor bugs; rejected on transparency.

## Decision

Edit `src/codegenie/planner/fallback_tier.py` additively: add `task_type: str | None = None` as a keyword-only argument to `FallbackTier.run`. When `task_type` is non-`None`, the tier (a) selects the prompt template by `task_type` (Phase 7 ships `prompts/migration_distroless.v1.yaml`), and (b) searches the `{task_type}_solved_examples_promoted` collection instead of the default vuln collection. When `task_type` is `None`, behavior is byte-identical to the pre-Phase-7 implementation.

## Tradeoffs

| Gain | Cost |
|---|---|
| One `FallbackTier` covers both task classes; Phase 8's supervisor passes `task_type` per dispatched workflow — no parallel tier to merge | Phase 4's `model_json_schema()`-equivalent — `inspect.signature(FallbackTier.run)` — drifts; contract-surface snapshot (ADR-0009) regenerates in the same PR |
| Default-`None` means every existing Phase 6 vuln callsite (`replan_with_phase4` in `vuln_loop.py`) is byte-identical — no Phase 6 edit forced by this change | The "additive" claim holds only if all consumers handle `task_type=None` identically; `tests/integration/test_phase4_default_task_type_behavior_unchanged.py` is the mechanical enforcement |
| Explicit `task_type` at the call site is transparent — Phase 8's supervisor will log it; `tests/integration/test_supervisor_logs_task_type.py` (Gap 6) is the future enforcement | One kwarg of API surface added to Phase 4 — readers must understand its semantics; the prompt-bleed anti-case (vuln advisory with `task_type="distroless_migration"`) must be tested (Gap 6 → `test_phase4_task_type_mismatch_safety.py`) |
| Phase 8's supervisor (and any future task class) inherits a single, named extension point — adding a third task class is a new prompt YAML + a new RAG collection + the same kwarg value | The kwarg is `str`, not a closed `Literal` — future task classes don't fail-loud on typos; the prompt-template loader must reject unknown values |

## Consequences

- `src/codegenie/planner/fallback_tier.py` receives a single signature change; `prompts/migration_distroless.v1.yaml` is a new data file under Phase 4's existing `prompts/` directory.
- `tests/integration/test_phase4_default_task_type_behavior_unchanged.py` asserts that calling `FallbackTier.run` without `task_type` against existing Phase 4 fixtures produces byte-identical `FallbackTierResult`.
- `tests/integration/test_rag_distroless_top1.py` asserts the distroless query returns a distroless example as top-1 (Risk #2 in `final-design.md`).
- `tests/integration/test_phase4_task_type_mismatch_safety.py` (Gap 6) asserts that mismatched `task_type` (vuln advisory + `task_type="distroless_migration"`) fails *loudly* — either at `TrustScorer.score` or at `OutputValidator`'s engine-reference check.
- Phase 8's supervisor adopts `task_type` as the dispatch key (`wf:vuln:` / `wf:distroless:` workflow prefixes in `phase-arch-design §Gap 1`).
- Phase 14 (continuous gather) and Phase 15 (recipe authoring) reuse the kwarg shape for their task classes.

## Reversibility

**High.** Removing the kwarg is mechanical (one signature line, one prompt-loader switch). Phase 4's existing tests continue to pass throughout because the default is `None`. The cost of reversal is that Phase 7's `replan_with_phase4` callsite would need to route prompt selection itself — a worse coupling, but tractable. The asymmetry favors *not* reverting, which is why the synthesizer picked the kwarg.

## Evidence / sources

- `../final-design.md §Conflict-resolution row 10` (Phase 4 task-class routing)
- `../final-design.md §"Departures #3 ADR-P7-003"` (the seam definition)
- `../phase-arch-design.md §Component 13 ADR-P7-003` (exact signature diff)
- `../phase-arch-design.md §Gap 6` (prompt-bleed anti-case)
- `../critique.md §best-practices.1` (the missing kwarg)
- `../critique.md §"Where do all three quietly agree on something questionable?" #2` (silent extension of Phase 4)
- [production ADR-0011](../../../production/adrs/0011-recipe-first-rag-llm-fallback-planning.md) — Recipe → RAG → LLM-fallback
