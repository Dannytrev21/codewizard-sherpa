# ADR-0006: Bench cases split by `curation_class` — `rag-corpus-derived` vs `held-out` with fence-CI floor

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** memorization · judgment · curation · fence-ci · phase-7-precondition
**Related:** [ADR-0002](0002-promotion-gate-keys-on-lower-bound-95.md), [Phase 5 ADR-0016](../../05-sandbox-trust-gates/ADRs/0016-per-task-class-eval-harness-as-trust-evidence.md)

## Context

[Phase 5 ADR-0016 §Decision §1](../../05-sandbox-trust-gates/ADRs/0016-per-task-class-eval-harness-as-trust-evidence.md) commits each task class to ≥ 10 curated cases with `provenance.source ∈ {"curated", "outcome-ledger-derived", "regression-converted"}` before promotion off bronze. The best-practices Phase 6.5 input proposed drawing the first 10 vuln-remediation cases mechanically from Phase 4's RAG `promoted/` corpus — the same fixtures Phase 4 used to validate the LLM-fallback path. Phase 4 cassettes are deterministic and constructable into bench cases in hours, not weeks. The critic identified the load-bearing problem (critic shared blind spot #2): a benchmark drawn from the same corpus the LLM saw during fallback tuning measures *memorization*, not judgment. A high `bench_score` on RAG-corpus-derived cases is consistent with "the LLM learned the answers" — not "the LLM can solve this task class."

Phase 7's promotion precondition (`lower_bound_95 ≥ tier_threshold[bronze]` over ≥ 10 cases, [ADR-0002](0002-promotion-gate-keys-on-lower-bound-95.md)) is meaningful evidence only if some fraction of those cases are *outside* the LLM's training/few-shot distribution. The RAG-corpus-derived cases are not worthless — they verify the recipe-first/RAG-fallback pipeline ([production ADR-0011](../../../production/adrs/0011-recipe-first-rag-llm-fallback-planning.md)) does not regress against the corpus it was tuned on. But they cannot be the *whole* corpus, and the distinction must be structural — not aspirational — or curators will preferentially derive cases mechanically (cheap) and underweight held-out curation (weeks of work, per [ADR-0016 §Tradeoffs](../../05-sandbox-trust-gates/ADRs/0016-per-task-class-eval-harness-as-trust-evidence.md)).

The Phase 6.5 schedule constraint is also load-bearing: shipping the bench for vuln-remediation cannot wait on the held-out 5 to be curated start-to-finish, or Phase 7 slips. The compromise is a 5+5 split for Phase 6.5 landing — the RAG-corpus-derived 5 land mechanically; the held-out 5 land in parallel and must be present before fence-CI passes for any tier ≥ silver.

## Options considered

- **No split** (best-practices Phase 6.5 input — implicit). 10 cases, all from RAG corpus. Memorization-vs-judgment confounded. Critic blind spot #2.
- **All held-out** (critic-strict reading). 10 cases, all curated cold. Maximally rigorous; Phase 6.5 slips by weeks. Phase 7 precondition becomes unachievable on the roadmap timeline.
- **`curation_class: rag-corpus-derived | held-out` Literal on `BenchCase`** with a 5+5 floor for Phase 6.5 landing and a `held-out ≥ 5` fence-CI assertion at silver-tier eligibility. The 5 RAG-corpus-derived cases mechanically construct from `tests/cassettes/phase4/` (corpus reuse, low curation cost). The 5 held-out cases are hand-curated CVEs Phase 4's fallback path *did not* see. Phase 7 inherits the discipline; `migration-chainguard-distroless` ships 3 held-out seed cases in Phase 6.5 (no RAG-corpus-derived; the migration corpus is younger).

## Decision

`BenchCase` gains a required `curation_class: Literal["rag-corpus-derived", "held-out"]` field. `bench/vuln-remediation/` ships with **5 RAG-corpus-derived + 5 held-out** cases for Phase 6.5 landing. `bench/migration-chainguard-distroless/` ships with **3 held-out** seed cases (no RAG-corpus-derived class — the migration RAG corpus is not yet built). Fence-CI assertion #3 (`final-design.md §Fence-CI test`) enforces: for any task class whose `min_cases_for_promotion` declares any tier ≥ silver, `count(c for c in cases if c.curation_class == "held-out") ≥ 5`. Bronze accepts the mixed 5+5 floor for Phase 6.5; silver eligibility requires the held-out floor to hold.

## Tradeoffs

| Gain | Cost |
|---|---|
| Memorization-vs-judgment distinction is structural, not aspirational; the gate cannot promote to silver on memorization alone | Curation cost doubles per task class — the held-out cases are hand-built; Phase 7 inherits the cost |
| Phase 6.5 ships on schedule with mechanically constructed RAG-corpus-derived 5; held-out 5 land in parallel | Schedule risk shifts to the held-out curation; if curators slip, Phase 7 silver-promotion eligibility slips |
| Fence-CI structural enforcement: a contributor cannot register a silver-eligible task class without 5 held-out cases — the rule is data, checked at PR time | The fence assertion adds ~50 ms; cumulative budget across all six assertions stays within the 2 s fence-CI cap |
| Phase 7's `migration-chainguard-distroless` (held-out only at seed) sets the precedent: task classes without a RAG corpus ship pure-held-out and accept the cost | A bench for a task class whose RAG corpus is rich could be tempted to under-ship held-out; the fence is the only structural defense — CODEOWNERS reviewers must understand the discipline |
| `BenchRunReport` can stratify scores by `curation_class` in the future (Phase 13 dashboard); the data is already shaped for memorization-vs-judgment analysis | Phase 6.5 does not split the aggregate by curation class in the verdict; that data is available but not promoted in `lower_bound_95` |
| The split is durable: even when Phase 13 outcome-ledger reconciliation adds `regression-converted` cases, they get tagged `curation_class` separately from the original split | Three-way classification (rag-corpus-derived / held-out / regression-converted) is implicit if Phase 13 expands the field; this ADR commits only to the two values shipping in Phase 6.5 |

## Consequences

- `BenchCase.curation_class: Literal["rag-corpus-derived", "held-out"]` is mandatory; missing values fail Pydantic at load time.
- `bench/vuln-remediation/cases/` ships with case IDs marked `001-005-rag-corpus-derived-*` and `006-010-held-out-*` (naming convention; not enforced).
- The 5 RAG-corpus-derived cases are mechanically constructable from `tests/cassettes/phase4/` fixtures: a curator runs `scripts/derive_bench_case_from_cassette.py <cassette-path>` to scaffold `case.toml + input/ + expected/ + cassette_canary_pin + digest`. Output is reviewed and CODEOWNERS-approved like any other bench case.
- The 5 held-out cases for vuln-remediation are CVEs Phase 4's fallback path did not see during tuning; curator selection criterion is "CVE-YEAR-NNNN where YEAR ≥ Phase 4 corpus cutoff" (`final-design.md §Risks #1`).
- The 3 held-out cases for `migration-chainguard-distroless` are Chainguard-publicly-documented migrations (`final-design.md §Test plan` fixture portfolio).
- Fence-CI assertion #3 walks every registered task class, checks `min_cases_for_promotion` keys, and if any tier ≥ silver appears (`silver`, `gold`, `platinum`, or any future tier so-ordered in `docs/trust-tiers.yaml`), asserts ≥ 5 cases with `curation_class == "held-out"`. Failure is a CI-blocking diagnostic naming the task class and the held-out count.
- Phase 7's exit criterion explicitly demands the held-out 5 floor; Phase 7 cannot ship migration PRs at scale until `bench/migration-chainguard-distroless/` grows from 3 to ≥ 10 with ≥ 5 held-out.
- Future task classes (Phase 15 recipe authoring) inherit the discipline. Curation cost is a known load on the task-class introduction phase.
- The aggregate `lower_bound_95` is computed over the full corpus (both classes); future ADRs may stratify per `curation_class` if memorization-vs-judgment divergence becomes load-bearing for promotion decisions.

## Reversibility

**Medium-low.** Reverting the `curation_class` field is a Pydantic edit; the harder revert is the *commitment* — that silver-tier eligibility requires held-out cases. Removing the fence assertion re-opens the memorization-vs-judgment confound and undoes the load-bearing critic-blind-spot-#2 resolution. The bench cases themselves carry the classification and are durable. The forward-evolution direction (adding `"regression-converted"` from Phase 13 as a third class, stratifying `lower_bound_95` per class) is the realistic path; backing out to "10 cases, no class" loses evidence quality.

## Evidence / sources

- [final-design.md §Synthesis ledger row "Bench-case source"](../final-design.md#conflict-resolution-table)
- [final-design.md §Departures from all three inputs #6](../final-design.md#departures-from-all-three-inputs)
- [final-design.md §Shared blind spots considered #2](../final-design.md#shared-blind-spots-considered)
- [final-design.md §Risks #1](../final-design.md#risks-top-5)
- [phase-arch-design.md §Fence-CI test (assertion #3)](../phase-arch-design.md#fence-ci-test-testsunittest_eval_fencepy)
- [phase-arch-design.md §Edge cases #9](../phase-arch-design.md#edge-cases)
- [phase-arch-design.md §Testing strategy — Fixture portfolio](../phase-arch-design.md#fixture-portfolio)
- [critique.md §"Attacks on the best-practices design" — Things this design missed](../critique.md#things-this-design-missed-2)
- [critique.md §"Where do all three quietly agree on something questionable?" #3](../critique.md#where-do-all-three-quietly-agree-on-something-questionable)
- [Phase 5 ADR-0016 §Decision §1, §6](../../05-sandbox-trust-gates/ADRs/0016-per-task-class-eval-harness-as-trust-evidence.md)
