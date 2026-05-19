# Agent orchestration — 2025–2026 survey and recommendations

**Status:** Review memo, non-canonical
**Scope:** Survey of recent (2025–2026) agent-orchestration techniques that have moved accuracy or lowered error rate on reasoning and code-agent benchmarks, plus specific recommendations on where each lands in codewizard-sherpa's phase structure and ADR set.
**Disposition:** Record findings + 17 ranked recommendations. Cite from new ADRs / stories rather than amending canonical design docs in this pass.
**Companion memo:** [`2026-05-18-research-committee-search-paper.md`](2026-05-18-research-committee-search-paper.md) — the Sunkaraneni et al. paper that prompted this broader survey.

## TL;DR — highest-effect / lowest-cost moves

If you ship only three things from this memo, ship these. Each names a single landing point, is low-risk, and addresses a known failure mode that the 2025–2026 literature has triangulated independently.

| # | Move | Landing point | Effect | Cost | Risk |
|---|---|---|---|---|---|
| 1 | **Hierarchical localization sub-stage** between Planning and Execution, using deterministic RepoContext + a narrowed RAG pass before any patch proposal | Phase 3 ADR (new) | High — addresses the dominant residual failure mode in committee search (shared-blind-spot proposal-coverage failures) | Low — one ADR + one story; the substrate (RepoContext indexed by path) already exists | Low — additive to the 7-stage pipeline, no existing component changes |
| 2 | **Retries as bounded MCTS** rather than three flat independent attempts; each retry sees the verifier signal and expands a subtree | Phase 5 ADR amending ADR-0014 | High — SWE-Search's 23% relative gain across five base models on SWE-bench is the largest scaffold-only result in 2025 | Medium — one ADR + a contained controller; wraps the existing retry loop rather than replacing it | Medium — touches Phase 5's gate runner; needs careful contract with TrustScorer |
| 3 | **Audit-anchor schema designed for future critic training** — `(proposal, evidence_seen_by_critic, critic_decision, verifier_outcome)` rows recorded from day one | Phase 3 High-level-impl.md (audit anchor section) | High — preserves the option of CTRL-style RL critic training (up to +106% relative on code in published results) | Trivial — one Pydantic class, one schema entry; no behavior change | Trivial — pure logging; doesn't commit to ever training a critic |

The rationale for ordering: (1) is the cheapest insurance against the worst residual failure mode and the literature is unanimous; (2) is the largest single architectural win available and your Phase 5 retry semantics make it a structural amendment rather than a new system; (3) costs nothing now and is painful to retrofit later.

## Recommendations ledger

Seventeen recommendations, organized by readiness. Effect and cost are both 1–5; risk is qualitative. Sorted within each section by effect:cost ratio.

### Now — cheap doc-level moves

| # | Recommendation | Landing | Effect | Cost | Risk | Source(s) |
|---|---|---|---|---|---|---|
| 1 | Pre-draft Phase 3 Localization sub-stage ADR (deterministic ranking via RepoContext, then narrowed RAG, then patch proposer) | `docs/phases/03-*/ADRs/` (new) | 5 | 1 | Low | Agentless (arXiv:2407.01489); Kimi-Dev (arXiv:2509.23045) |
| 2 | Anti-debate marker on the validator — explicit "Non-goals" paragraph in `phase-story-validator/SKILL.md` stating critic is one-way; failed hardening → RESCUE, not back-and-forth with writer | `.claude/skills/phase-story-validator/SKILL.md` | 3 | 1 | None | "Can LLM Agents Really Debate?" (arXiv:2511.07784); Latent Agents (arXiv:2604.24881); MAST (arXiv:2503.13657) |
| 3 | ADR-0008 amendment paragraph citing the 2025 PRM survey as external evidence for the executable-only trust signal | `docs/production/adrs/0008-objective-signal-trust-score.md` | 2 | 1 | None | PRM survey (arXiv:2510.08049); FunPRM (arXiv:2601.22249); DreamPRM-Code (arXiv:2512.15000) |
| 4 | ADR-0011 amendment paragraph framing retrieval as soundness substrate (constrains proposal surface), not just cost optimization | `docs/production/adrs/0011-recipe-first-rag-llm-fallback-planning.md` | 2 | 1 | None | Agentless; The Reasoning Trap (arXiv:2510.22977) |
| 5 | Phase 6.5 reference update — SWE-bench Pro as canonical leaderboard, not Verified | `docs/phases/06-*/` Phase 6.5 docs | 2 | 1 | None | SWE-bench Verified contamination openly acknowledged in 2026; SWE-bench Pro (Scale AI) is the cleaner signal |
| 6 | One-sentence non-direction in `docs/production/design.md` — codewizard-sherpa will not introduce multi-agent debate at any layer | `docs/production/design.md` | 2 | 1 | None | Same as #2; protects against future scope creep |

### During Phase 3 design (vulnerability remediation)

| # | Recommendation | Landing | Effect | Cost | Risk | Source(s) |
|---|---|---|---|---|---|---|
| 7 | Audit-anchor schema with `(proposal, evidence_seen_by_critic, critic_decision, verifier_outcome)` rows from day one — preserves the option of CTRL-style RL critic training later | Phase 3 High-level-impl.md (audit anchor section) | 5 | 1 | Trivial | CTRL (arXiv:2502.03492); Critique-RL (Oct 2025) |
| 8 | Grammar-constrained tool calls for the patch proposer from the first commit — Pydantic + outlines / lm-format-enforcer pattern | Phase 3 patch-proposer module | 4 | 2 | Low | JSONSchemaBench (arXiv:2501.10868); CRANE (arXiv:2502.09061) |
| 9 | Patch-proposer prompting policy: no intermediate CoT before tool calls (emit patch directly); reserve CoT for the critic where reasoning over evidence is the right thing | Phase 3 design doc, prompt-engineering section | 3 | 1 | Low | The Reasoning Trap (arXiv:2510.22977); Agentless / CodeAct conventions |
| 10 | Coverage-vs-selection diagnostic — Phase 3 Validation emits oracle-best-of-k vs deployed-selector accuracy per task (carried forward from the prior memo) | `docs/phases/03-*/stories/` (new) | 5 | 2 | Low | Sunkaraneni et al. (arXiv:2605.14163); Snell et al. (arXiv:2408.03314) |

### During Phase 5 (sandbox trust gates)

| # | Recommendation | Landing | Effect | Cost | Risk | Source(s) |
|---|---|---|---|---|---|---|
| 11 | Retries-as-MCTS — wrap the existing 3-retry loop with a bounded tree-search controller; value estimate from trust score, expansion choices from critic | Phase 5 ADR (new) amending ADR-0014 | 5 | 3 | Medium | SWE-Search (arXiv:2410.20285) — 23% relative on SWE-bench; Koh et al. (arXiv:2407.01476) |
| 12 | Adaptive retry budget — `budget = adaptive(trust_score, gate_class)` rather than flat k=3 | Phase 5 follow-up ADR (defer until runtime evidence) | 3 | 2 | Low | FrugalGPT (arXiv:2305.05176); step-level hybrid scaling (EMNLP 2025, 2025.emnlp-main.931) |

### During Phase 6.5 (benchmarking)

| # | Recommendation | Landing | Effect | Cost | Risk | Source(s) |
|---|---|---|---|---|---|---|
| 13 | Three-way benchmark harness: SWE-Search + plain k=8 committee + your stack, on identical task set | Phase 6.5 stories | 4 | 3 | Low | Confucius Code Agent (arXiv:2512.10398); "Inside the Scaffold" (arXiv:2604.03515) — scaffolding alone accounts for ~30pp of variance |
| 14 | CISC-style confidence-weighted aggregation in the trust-score formula (post-Phase-3 runtime data) | Amendment to ADR-0015 (defer) | 2 | 2 | Low | CISC (arXiv:2502.06233 — ACL 2025) |

### During Phase 15 (recipe authoring) — defer implementation, draft ADR stub now

| # | Recommendation | Landing | Effect | Cost | Risk | Source(s) |
|---|---|---|---|---|---|---|
| 15 | Phase 15 ADR stub: recipe authoring is committee search + executable corpus verification (k candidate recipes; soundness = does each apply cleanly across N reference repos; comparator picks for generalizability) | `docs/phases/15-*/ADRs/` (new stub) | 3 | 1 | Low | Sunkaraneni et al. (arXiv:2605.14163) |

### Don't do

| # | Non-direction | Why | Source(s) |
|---|---|---|---|
| 16 | Don't train a process reward model for code paths — executable tests beat learned PRMs on code tasks in 2025–2026. If learned signal is ever pursued, train an outcome critic (CTRL-style), not a PRM | PRM survey (arXiv:2510.08049); FunPRM (arXiv:2601.22249); Socratic-PRMBench brittleness across reasoning patterns (arXiv:2505.23474) |
| 17 | Don't add Mixture-of-Agents as a parallel orchestration mode — heterogeneous-model aggregation underperforms verifier-backed committee search whenever a verifier exists, which is every task class in the roadmap | Mixture-of-Agents (arXiv:2406.04692 — ICLR 2025 Spotlight) — much of the reported gain reduces to ensembling; no competitive SWE-bench MoA result published |

## Supporting research — what's working in 2025–2026

This section is the evidence base for the ledger above. Organized into three buckets: techniques that compound with verifier-backed committee search, techniques that compete with it and have been losing, and hygiene that's worth doing but doesn't move accuracy.

### What compounds with committee search

**Tree search over tool-call trajectories.** The strongest 2025 code-specific result is SWE-Search (Antoniades et al., arXiv:2410.20285 — ICLR 2025) — MCTS plus a value agent over the agent's action sequence yields ~23% relative gain across five base models on SWE-bench without retraining. The general-purpose analog is Koh et al. "Tree Search for Language Model Agents" (arXiv:2407.01476). Committee search is breadth at the patch level; MCTS is depth over the debug loop; they compose cleanly — each leaf of the tree can itself host a small committee.

**Trained critic models (not frozen ones).** CTRL (Xie et al., arXiv:2502.03492) trains a critic with RL against correction-utility and reports up to +106% relative on code benchmarks via iterative critique-revision. Critique-RL (Oct 2025) uses a two-stage curriculum (discriminability then helpfulness). OpenAI's CriticGPT lineage demonstrated critics catching bugs in LLM-written code that humans miss. The Sunkaraneni paper uses a *frozen* nano critic; RL-trained critics are the obvious next step once enough verifier-grounded outcome data is collected.

**Hierarchical localization (Agentless pattern).** Agentless (Xia et al., arXiv:2407.01489) — three-phase *localize → repair → validate*, no agent loop — still benchmarks competitively (~50.8% Verified with Sonnet 3.5) at roughly $0.34/issue. Kimi-Dev (arXiv:2509.23045) shows agentless-style training transfers to agentic skill priors. Diverse-k proposals are wasted on the wrong file; localization before propose-k strictly dominates propose-k blind.

**Adaptive / cascading test-time scaling.** FrugalGPT (Chen et al., arXiv:2305.05176 — TMLR 2024) reports up to 98% cost reduction at matched accuracy via cascade + judger threshold. The EMNLP 2025 step-level verifier-guided hybrid scaling paper (2025.emnlp-main.931) splits budget between parallel and sequential refinement by problem difficulty. Snell et al. (arXiv:2408.03314 — ICLR 2025) make the same argument theoretically: compute-optimal allocation beats fixed-k best-of-N by ~4× on revision tasks.

**Confidence-weighted self-consistency.** CISC (Taubenfeld et al., arXiv:2502.06233 — ACL 2025) gives 40–50% cost reduction with mild accuracy gains over plain self-consistency. PROVE (arXiv:2410.12608) uses programs as verifiers (essentially committee search in miniature for math, e.g. GSM8K 73.4% → 79.6% on Gemma-2-2b).

### What competes with committee search and has been losing

**Multi-agent debate.** Largely deflated in 2025–2026. Smit et al. ("Should we be going MAD?", arXiv:2311.17371) and the 2025 controlled study (arXiv:2511.07784) both find debate gains reduce to plain ensembling or majority vote, with bias amplification in homogeneous panels. Latent Agents (arXiv:2604.24881) distills debate into a single model with 93% fewer tokens at matched accuracy — the orchestration overhead was wasted. The MAST taxonomy (Cemri et al., arXiv:2503.13657) catalogs 14 failure modes and reports production failure rates of 41–87%, mostly specification ambiguity and verification gaps. The mechanism that makes committee search work — an *external* verifier — is exactly what debate lacks.

**Intrinsic self-correction.** The 2024 negative results (Huang et al. ICLR 2024; Stechly et al.; Kamoi et al. TACL 2024 survey, arXiv:2406.01297) all replicate on 2025 frontier models. RefineBench (2025) measured a +1.8pp ceiling on GPT-5 / Gemini 2.5 Pro / DeepSeek-R1 under self-only feedback. With external feedback (tests, retrieval, oracle), +80% within 5 turns. The qualifier matters: refinement only works with external signal. The `phase-story-executor` 3-attempt loop is correct precisely because it surfaces test failures back to the next attempt.

**Mixture-of-Agents (heterogeneous model aggregation).** MoA (Wang et al., arXiv:2406.04692 — ICLR 2025 Spotlight) reports 65.1% on AlpacaEval 2.0 beating GPT-4o using open models only. But the empirical foundation has been challenged on the same grounds as multi-agent debate — much of the gain is ensembling. Successors (RMoA arXiv:2505.24442, Attention-MoA arXiv:2601.16596) report only single-digit gains, and no public SWE-bench MoA result is competitive with strong single-model agents. For tasks with executable signals (every task class in the codewizard-sherpa roadmap), verifier-backed committee search wins.

### Hygiene — worth doing, doesn't move accuracy much

**Constrained / structured generation.** JSONSchemaBench (arXiv:2501.10868) and CRANE (arXiv:2502.09061) frame the question. Empirical answer: constrained decoding ranges from neutral to mildly helpful on accuracy and decisively helpful on parse-success. For code agents the practical win is fewer malformed tool calls, not raw accuracy. Worth landing day one of Phase 3 because retrofitting it later is painful (audit anchors will assume parseable tool calls).

### Negative results worth knowing

- **CoT can amplify tool hallucination in agents** (The Reasoning Trap, arXiv:2510.22977) — relevant to Phase 3 prompting choices; reserve CoT for the critic, not the tool-emitting proposer.
- **SWE-bench Verified contamination** is openly acknowledged across frontier models in 2026 — Phase 6.5 should cite SWE-bench Pro as the canonical reference.
- **Multi-agent system failure rates in production** are 41–87% per MAST (arXiv:2503.13657), dominated by specification ambiguity and verification gaps — single-agent o1-class baselines often outperform multi-agent setups when the task is well-specified.
- **Process reward models for code are not yet competitive with executable tests** — the survey + benchmark literature is consistent on this through 2026.

## How this maps to the project — synthesis

Three deep takeaways from the survey, expressed in codewizard-sherpa terms:

1. **The project is structurally well-positioned for verifier-backed orchestration.** The deterministic gather pipeline, the LLM fence (ADR-0005), the objective-signal trust score (ADR-0008), recipe-first planning (ADR-0011), and the sandbox trust gates (Phase 5) all exist for reasons that the 2025–2026 literature has now triangulated independently. Most of the recommendations in this memo are amendments and additions, not redirections.

2. **The biggest residual win is structural — adding bounded MCTS to the retry loop and hierarchical localization before the proposer.** Both are pure additions that respect existing contracts. Together they address the two dominant failure modes the literature has identified: shared-blind-spot proposal-coverage failures (localization) and inefficient retry budgets (MCTS).

3. **The longest-horizon move is data-shaped.** Designing the audit-anchor schema today so that every proposal-outcome pair is recorded in a training-ready format costs nothing and preserves the option of CTRL-style RL critic training later. This is the kind of decision that compounds silently for years.

## Pointers

### Companion memo
- [`2026-05-18-research-committee-search-paper.md`](2026-05-18-research-committee-search-paper.md) — Sunkaraneni et al. paper-specific learnings; the application-ledger and skill-pipeline ledger live there

### Existing project artifacts referenced
- `docs/production/design.md`
- `docs/production/adrs/0005-no-llm-in-gather-pipeline.md`
- `docs/production/adrs/0008-objective-signal-trust-score.md`
- `docs/production/adrs/0011-recipe-first-rag-llm-fallback-planning.md`
- `docs/production/adrs/0014-three-retry-default-per-gate.md`
- `docs/production/adrs/0015-trust-score-threshold-calibration.md`
- `docs/roadmap.md` (Phase 3 / Phase 5 / Phase 6.5 / Phase 15)
- `.claude/skills/phase-story-writer/SKILL.md`
- `.claude/skills/phase-story-validator/SKILL.md`
- `.claude/skills/phase-story-executor/SKILL.md`

### Headline sources
- [Sunkaraneni et al. — Agentic Systems as Boosting Weak Reasoning Models](https://arxiv.org/abs/2605.14163)
- [Snell et al. — Scaling LLM Test-Time Compute Optimally (ICLR 2025)](https://arxiv.org/abs/2408.03314)
- [Kinetics — Rethinking Test-Time Scaling Laws (2026)](https://arxiv.org/abs/2506.05333)
- [SWE-Search — MCTS for SWE-Agents (ICLR 2025)](https://arxiv.org/abs/2410.20285)
- [Koh et al. — Tree Search for Language Model Agents](https://arxiv.org/abs/2407.01476)
- [CTRL — Teaching LMs to Critique via RL](https://arxiv.org/abs/2502.03492)
- [Agentless (Xia et al.)](https://arxiv.org/abs/2407.01489)
- [Kimi-Dev — Agentless Training as Skill Prior](https://arxiv.org/abs/2509.23045)
- [CISC — Confidence Improves Self-Consistency (ACL 2025)](https://arxiv.org/abs/2502.06233)
- [PROVE — Programs as Verifiers](https://arxiv.org/abs/2410.12608)
- [FrugalGPT (TMLR 2024)](https://arxiv.org/abs/2305.05176)
- [Step-level verifier-guided hybrid scaling (EMNLP 2025)](https://aclanthology.org/2025.emnlp-main.931.pdf)

### Negative-result and competing-technique sources
- [Cemri et al. — Why Do Multi-Agent LLM Systems Fail? (MAST)](https://arxiv.org/abs/2503.13657)
- [Can LLM Agents Really Debate? (2025)](https://arxiv.org/abs/2511.07784)
- [Latent Agents — debate distillation (2026)](https://arxiv.org/abs/2604.24881)
- [Kamoi et al. — Critical Survey of Self-Correction (TACL 2024)](https://arxiv.org/abs/2406.01297)
- [Mixture-of-Agents (ICLR 2025)](https://arxiv.org/abs/2406.04692)
- [The Reasoning Trap — CoT amplifies tool hallucination](https://arxiv.org/abs/2510.22977)
- [A Survey of Process Reward Models](https://arxiv.org/abs/2510.08049)

### Survey / benchmark context
- [Inside the Scaffold — Coding Agent Architectures](https://arxiv.org/abs/2604.03515)
- [Confucius Code Agent](https://arxiv.org/abs/2512.10398)
- [JSONSchemaBench](https://arxiv.org/abs/2501.10868)
- [CRANE — Constrained Reasoning](https://arxiv.org/abs/2502.09061)
