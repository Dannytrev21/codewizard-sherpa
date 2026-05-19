# Research note — Agentic Systems as Boosting Weak Reasoning Models

**Status:** Review memo, non-canonical
**Paper:** Sunkaraneni, Beneventano, Neumarker, Poggio, Galanti — *Agentic Systems as Boosting Weak Reasoning Models*, arXiv:2605.14163 (13 May 2026)
**Scope:** What the paper proves, how it lands on the codewizard-sherpa application architecture (Phases 3, 6.5, 7, 15), and how it lands on the skill pipeline that *builds* codewizard-sherpa (`phase-story-writer`, `phase-story-validator`, `phase-story-executor`).
**Disposition:** Record learnings; cite from new ADRs / stories rather than amending canonical design docs in this pass.

## Why this paper matters here

The paper formalizes what an LLM-driven coding agent gets out of inference-time boosting and proves where the ceiling sits. Headline result on SWE-bench Verified: a single `GPT-5.4 nano` call solves 67.0% of tasks; the same nano model under a critic-then-comparator selector over k=8 proposals reaches 76.4% — matching `Gemini 3 Pro` and `Claude Opus 4.5 Thinking` standalone, and within 2.6 points of the 79.0% oracle best-of-8 ceiling. The mechanism factors into four quantities — *coverage*, *local identifiability*, *progress*, *diversity* — and proves that reliable amplification requires a **local soundness signal**: execution, proof checking, type checking, tests, or constraint solving. Without one of those, more samples and more selection compute cannot compose into reliable trajectories.

For this project, that is not abstract. Codewizard-sherpa's whole stance — *facts, not judgments; deterministic gather; recipes for structural transforms; LLM reserved for judgment calls* — already builds the substrate the paper says is necessary. The paper supplies a formal argument for several decisions that were previously stated as principles, and it points at one architectural pattern (committee search with verifier-backed selection) that the project has not yet adopted explicitly but is one short step from.

## What the paper actually proves (load-bearing details)

1. **Four-factor decomposition.** *Coverage* (does a good move appear in the proposal pool?), *local identifiability* (can the system recognize it without the hidden verifier?), *progress* (do local choices compose into a terminal trajectory?), *diversity* (do additional calls escape different failure modes, not just resample the same one?). The four are independent levers; pushing on the wrong one wastes compute.
2. **Coverage is bounded by the proposer.** Oracle best-of-k converges only to the mass of task slices on which the proposal system assigns nonzero useful probability. No amount of critic compute can pull a solution out of a pool that does not contain one.
3. **Selection requires a local soundness signal.** The reliability argument for composing selection over multiple steps holds only when the critic has access to execution, proof checking, type checking, tests, or constraint solving. Pure judgment without a soundness signal degrades to self-consistency.
4. **Critic and comparator do different jobs.** The reported architecture is hybrid: a binary critic gates proposals by yes-rate threshold; surviving proposals are then ranked by a pairwise comparator aggregated under Copeland round-robin or strict dominance (both tied at 74.6%). All-pairs aggregation preserved pairwise evidence better than cheaper tournament structures. Tie-breaks by lowest proposal index.
5. **The deployed selector does not see the hidden verifier.** On SWE-bench, candidate patches are scored by the harness for evaluation only; the selector decides from patch + repo context. The local soundness signal driving selection is the critic/comparator's own judgment over evidence, not test execution.
6. **Failure mode triage.** Residual failures after k=8 selection are dominated by *proposal-coverage failures* — shared blind spots across the pool. Selection compute past this point has diminishing returns; coverage widening (different temperatures, prompt diversity, multi-model proposers) is the lever.

Caveat: formal theorem statements in Section 3 (the rank-based bounds) and explicit cost-latency guidance were not pulled verbatim; the architectural reading below does not depend on those exact numbers.

## Application-level learnings (ledger)

| Tier | Confidence | Where it lands | Finding | Recommended disposition |
|---|---|---|---|---|
| 1 | high | `docs/production/design.md`; Phase 3 design | The Planner/Execution/Validation triad is structurally a committee-search loop with a missing explicit critic+comparator | New production ADR: *Patch generation as verifier-backed committee search* — sample k, critic-filter, comparator-rank, validation gates as the soundness signal |
| 1 | high | `docs/production/adrs/0011-recipe-first-rag-llm-fallback-planning.md` | Recipe-first is correct precisely because recipes have a perfect local soundness signal (transform applies cleanly or fails); committee search is wasted compute on tasks a recipe already covers | Amend the ADR rationale paragraph to cite this paper as external justification; do not change the decision |
| 1 | high | Phase 3 (vulnerability remediation) | The 67% → 76.4% nano-with-selection result argues against defaulting to frontier models for proposal generation at portfolio scale; the cost math compounds across vulns × repos × PRs | Story under `docs/phases/03-*/stories/`: *Coverage-vs-selection diagnostic* — emit oracle-best-of-k vs deployed-selector accuracy from Validation so we know which lever to pull |
| 1 | high | `IndexHealthProbe` (B2) | The "B2 is the single most important probe" claim in CLAUDE.md is restated formally: a corrupted local soundness signal collapses the selection-composition theorem; stale indices poison every downstream critic | One-line citation in B2's docstring referencing this memo; no behavior change |
| 1 | high | `docs/production/adrs/0008-objective-signal-trust-score.md` | The objective-signal trust score is exactly the kind of local soundness signal the paper requires — execution + test pass/fail + lint/type signals aggregated into a verifier surface | Cite this paper in the ADR's "Consequences" section as external evidence that this is the right shape; no change to the trust score itself |
| 1 | high | Phase 6.5 (benchmarking) | The paper supplies the right benchmark shape: report oracle best-of-k alongside selector accuracy, not just end-to-end pass rate | Stories should track both numbers; widen acceptance criteria to include the gap as a first-class metric |
| 1 | high | Phase 15 (agentic recipe authoring) | Recipe authoring is judgment + executable verification (does the recipe apply cleanly across a corpus?) — textbook committee-search shape | Pre-write a phase ADR before Phase 15 lands: recipes are sampled, executable corpus is the soundness signal, comparator picks for generalizability |
| 2 | medium | `docs/production/adrs/0014-three-retry-default-per-gate.md` | "Three retries per gate" is implicitly committee search with k=3 but no explicit critic/comparator; the paper suggests this leaves selection value on the table | Future ADR amendment once Phase 5 has runtime evidence — consider critic-scored retries instead of uniform retries |
| 2 | medium | Phase 5 (sandbox trust gates) | Sandbox execution *is* the local soundness signal that the paper says is necessary; this validates the entire Phase 5 stack as load-bearing for any future committee-search Planner | Cross-link this memo from Phase 5 design |
| 3 | low | Multi-family proposer | If coverage failures dominate residual error, mixing model families (Claude/GPT/Gemini) widens the proposal distribution; this is a cost question, not a correctness one | Defer — only relevant once Phase 3 has selection-vs-coverage telemetry |

### Why these are application-level, not skill-level

The application is "codewizard-sherpa opens PRs." Inside that runtime, the LLM lives in Planner / Execution; the deterministic substrate lives in gather + Validation. The paper's claim is that those two layers must be designed together: the substrate determines whether the LLM layer can be cheaply boosted. Every Tier-1 row above is a place where the substrate and the future LLM layer meet.

## Skill-pipeline learnings — the meta level

The pipeline that *builds* codewizard-sherpa already runs a near-textbook implementation of verifier-backed committee search; the paper makes that visible and points at the gaps.

| Skill | Paper role it plays | Already implemented | Gap the paper exposes |
|---|---|---|---|
| `phase-story-writer` Stage 2 | Proposer (parallel sampling) | N subagents in parallel, one per `High-level-impl.md` step | One sample per step, not k. There is no within-step diversity, so the validator cannot compare alternatives — it can only critic the single proposal |
| `phase-story-validator` four parallel critics | Critic — binary judge | STRONG / HARDENED / RESCUE verdicts; four critics per story | No comparator. With only one proposal per slot, pairwise ranking has nothing to compare |
| `phase-story-validator` _validation/ log | Audit anchor for selection decisions | Append-only, every edit logged | Today this logs critic decisions on a single proposal; if k>1 it would log selection across proposals |
| `phase-story-executor` 3-attempt loop | Mini committee search at code-write time | Up to 3 attempts; ReAct + red-green-refactor TDD; Ralph Wiggum naive-verification pass | Attempts are sequential and learn from each other (compounding) rather than parallel and ranked — both are valid; the paper's bounds favor parallel-with-selection when the soundness signal is fast and cheap |
| Red-green-refactor TDD + Ralph Wiggum verifier | The local soundness signal | `make check` + per-story acceptance-criterion runtime evidence | This is the strongest part of the pipeline — exactly the shape the paper says is necessary. The honesty of the tests determines whether the executor's loop is amplifying or just running in circles |

### The five concrete meta-learnings

1. **The skill pipeline is already committee-search-shaped.** Writer → validator → executor maps onto proposer → critic → execution-with-verifier. The architecture has been correct by intuition; the paper now provides external justification. This is worth a single-paragraph mention in each of the three SKILL.md files under a *Theoretical grounding* note so future maintainers understand why the shape is what it is.

2. **The story writer is leaving coverage on the table.** Stage 2 spawns N agents in parallel but each writes one story per slot. The paper's headline finding — many correct solutions are already in weak-model proposal pools, the problem is selection — suggests an alternative: each Stage 2 writer produces k=2–3 candidate story variants for the same slot, and the validator selects via pairwise comparison rather than just hardening a single proposal. Concrete experiment worth running: pick one phase, generate k=3 story variants per slot, have the validator comparator-rank them, measure whether the chosen variant produces better executor outcomes than the current k=1 baseline. Cost: one extra agent call per story slot. The paper's economics say this should pay back.

3. **The validator is doing critic-only work; adding a comparator mode is small.** Today the validator has STRONG / HARDENED / RESCUE verdicts on a single story. A second mode — *given k candidate stories for the same slot, pick the best* — is a natural extension. The pairwise comparator + Copeland-aggregation pattern from the paper transfers directly. Worth a SKILL.md amendment that adds `--mode comparator` alongside the existing default mode.

4. **The executor's 3-retry loop should be measured against committee-search alternatives.** Sequential retries with append-only attempt logs are a *learning* loop (each attempt sees the last one's failure). The paper's parallel-with-selection setup is a *diversity* loop (each sample is independent, comparator picks the best). Both have theoretical merit; which wins for `make check`-grade test signals is an empirical question. Phase 6.5 benchmarking should include this comparison: 3 sequential attempts vs 3 parallel attempts + critic-comparator selection, on a fixed story corpus.

5. **The local soundness signal in the meta pipeline is the test suite + `make check`.** This is *the* load-bearing assumption. If acceptance-criterion tests are weak, the validator can't tell a good story from a bad one and the executor's Ralph Wiggum pass can't tell good code from bad code. The validator's existing *test-quality* critic ("would the TDD plan catch an obviously wrong implementation?") is doing exactly the work the paper says must be done — it is policing the soundness signal itself. Worth explicitly framing in the validator SKILL.md: *the test-quality critic is non-optional; it protects the meta pipeline's amplification property*.

### Meta-meta: the project's "no LLM in gather" stance, restated

The fence (`tests/unit/test_pyproject_fence.py`, `make lint-imports`) ensures that the soundness signal feeding the future Planner is itself LLM-free. The paper proves this matters: a soundness signal that is itself an LLM judgment cannot reliably amplify a separate LLM proposer because there is no independent verifier. Stating that as a load-bearing commitment in `docs/production/adrs/0005-no-llm-in-gather-pipeline.md` already captured the right instinct; the paper supplies the formal reason.

## Recommended next moves

Cheap and high-leverage:

- **Memo citation pass.** Add one-line references to this memo from: `docs/production/adrs/0005`, `0008`, `0011`, `0014`, and from `IndexHealthProbe`'s module docstring. No content changes — just a pointer so future readers find the external argument.
- **Phase 3 story: coverage-vs-selection diagnostic.** Single story under `docs/phases/03-*/stories/`. Acceptance: Validation stage emits both oracle-best-of-k and deployed-selector accuracy per task; downstream Phase 6.5 benchmark consumes both numbers. This is the single most actionable item — without it we will not know whether Phase 3 cost overruns are coverage failures or selection failures.
- **Skill-pipeline experiment.** Pick one not-yet-written phase, run `phase-story-writer` with k=3 variants per slot, extend `phase-story-validator` with a one-shot comparator mode, measure executor outcomes vs the current pipeline. Result either justifies a SKILL.md amendment or kills the idea cheaply.

More expensive, defer until evidence:

- **New production ADR: *Patch generation as verifier-backed committee search*.** Drafted only after Phase 3 has runtime data showing where the coverage vs selection gap actually sits. Writing this ADR before evidence would over-commit to an architecture whose hyperparameters (k, threshold, aggregator) need empirical calibration.
- **Multi-family proposer.** Only relevant if coverage failures dominate after the diagnostic ships. Cost and operational complexity make this a Phase 8+ consideration.

## Pointers

- Paper: [arXiv:2605.14163](https://arxiv.org/abs/2605.14163)
- Related project commitments: `docs/production/adrs/0005-no-llm-in-gather-pipeline.md`, `0008-objective-signal-trust-score.md`, `0011-recipe-first-rag-llm-fallback-planning.md`
- Skill pipeline: `.claude/skills/phase-story-writer/SKILL.md`, `.claude/skills/phase-story-validator/SKILL.md`, `.claude/skills/phase-story-executor/SKILL.md`
