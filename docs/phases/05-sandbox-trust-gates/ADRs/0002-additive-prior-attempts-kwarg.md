# ADR-0002: Additive `prior_attempts` kwarg on Phase 3 `ApplyContext` and Phase 4 `FallbackTier.run`

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** retry · phase-boundary · contract · extension-by-addition
**Related:** [ADR-0001](0001-two-chokepoint-sandbox-seam.md), [ADR-0003](0003-trustscorer-extension-via-signal-kind-registry.md), [ADR-0005](0005-phase4-chain-head-compatibility.md), [production ADR-0011](../../../production/adrs/0011-recipe-first-rag-llm-fallback-planning.md), [production ADR-0014](../../../production/adrs/0014-three-retry-default-per-gate.md)

## Context

Phase 5's three-retry loop only matters if retry-N can produce a *different* patch than retry-(N-1). The Konveyor Kai prior art and ADR-0011's recipe-first/RAG/LLM-fallback shape both depend on feeding the planner what just failed. All three input designs assumed Phase 4 would accept "the failed-gate error log as a clean retry input" — none verified Phase 4's `FallbackTier.run` signature actually accepts that, none specified the shape, and none addressed prompt-injection risk in raw sandbox logs. See [final-design.md §Synthesis ledger row: Retry feedback transport](../final-design.md#synthesis-ledger) and [final-design.md §Shared blind spots considered](../final-design.md#synthesis-ledger) §3.

## Options considered

- **Raw error log kwarg** — Phase 4 accepts `prior_failure_log: str`. Simplest; injects raw sandbox stderr into the LLM prompt. Fails security on prompt-injection in test stderr; fails auditability (no structured retrieval).
- **Replace `FallbackTier.run` signature** — New method `run_with_retry(...)` alongside the old. Two callsites, two contract-snapshot tests, and a deprecation path. Violates extension by addition.
- **Additive `prior_attempts: list[AttemptSummary] = []` kwarg** — Default-empty kwarg on existing `FallbackTier.run` (and Phase 3's `ApplyContext`). `AttemptSummary` is a Pydantic model with a sanitized `prior_failure_summary` field (fence-wrapped via Phase 4's existing `FenceWrapper`, canary-pattern checked, ≤ 4 KB). Existing callsites unchanged.

## Decision

Amend `ApplyContext` (Phase 3) and `FallbackTier.run` (Phase 4) to accept `prior_attempts: list[AttemptSummary] = []` as a default-empty kwarg. `AttemptSummary` carries `attempt_id`, `sandbox_run_id`, `failing_signals`, `prior_failure_summary` (sanitized), and `evidence_paths`. Phase 4's prompt builder appends the fence-wrapped summary on attempt 2+; the orchestrator's `replan_hook` is the only caller that ever passes a non-empty list.

## Tradeoffs

| Gain | Cost |
|---|---|
| Default-empty kwarg means Phase 3/4's existing callsites are byte-unchanged | Phase 4's contract-snapshot test regenerates (loud, intentional) |
| Structured `AttemptSummary` is auditable, type-safe, and fence-wrappable — closes the prompt-injection vector from raw sandbox stderr | A new Pydantic model owned by Phase 5 is now referenced by Phase 3 and Phase 4 — cross-phase coupling |
| Phase 4's existing `FenceWrapper` + canary-pattern matcher is reused — no new defense to maintain | `prior_failure_summary` truncation policy (≤ 4 KB) lives in Phase 5; injecting attacker-shaped text past 4 KB is *not* a Phase 5 defense |
| Honors the load-bearing "extension by addition" commitment from [CLAUDE.md](../../../../CLAUDE.md) | A new kwarg is, technically, an interface change — visible in any IDE/type-stub diff |

## Consequences

- Phase 4's prompt builder gains a code path: if `prior_attempts` is non-empty, append a fence-wrapped block to the LLM prompt with each attempt's `failing_signals` and `prior_failure_summary`.
- `AttemptSummary` becomes part of Phase 5's stable contract — Phase 6 lifts it into its state ledger; Phase 11's reviewer UI reads `evidence_paths`.
- Phase 5 imports Phase 4's `FenceWrapper` (it does not re-implement fence/canary).
- `tests/integration/gates/test_stage6_retry_recovers.py` is the load-bearing exit-criterion test: asserts the Phase 4 prompt on attempt 2 demonstrably contains the fence-wrapped summary; asserts attempt 1 and attempt 2 produce distinct `patch_blake3`.
- Phase 3 and Phase 4 contract-snapshot tests regenerate as part of the Phase 5 PR — loud, ADR-referenced diff.
- New invariant: no raw sandbox stdout/stderr bytes ever reach Phase 4's prompt. The summary is the only carrier.
- Adding a future field to `AttemptSummary` requires an ADR amendment plus contract-snapshot regeneration (Phase 5 is the schema owner).

## Reversibility

**Medium.** Reverting the kwarg means losing retry-N learning — the three-retry loop degrades to three identical-input shots. Reverting the model (moving back to a raw string) loses the structured audit trail and re-opens prompt injection. The kwarg signature itself is easy to remove; the data shape's downstream consumers (Phase 6 state, Phase 11 evidence) are the cost. ADR-amend rather than delete is the realistic path.

## Evidence / sources

- [final-design.md §Synthesis ledger — Retry feedback transport row](../final-design.md#synthesis-ledger) (winner score 12)
- [final-design.md §Departures from all three inputs §3](../final-design.md#departures-from-all-three-inputs)
- [final-design.md §Shared blind spots considered §3](../final-design.md#synthesis-ledger)
- [phase-arch-design.md §Component design — `GateContext`, `AttemptSummary`](../phase-arch-design.md#data-model)
- [phase-arch-design.md §Gap analysis Gap 2](../phase-arch-design.md#gap-2-the-replan_hook-interface-between-graterunner-and-phase-4s-fallbacktier-is-described-in-prose-but-not-signature-pinned) — `ReplanHook` Protocol formalization
- [production ADR-0011](../../../production/adrs/0011-recipe-first-rag-llm-fallback-planning.md) — recipe→RAG→LLM fallback target the kwarg feeds
- [production ADR-0014](../../../production/adrs/0014-three-retry-default-per-gate.md) — three-retry semantics this enables
