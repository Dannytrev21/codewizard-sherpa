# ADR-0009: Inline auto-harvest gated by `TrustOutcome.passed AND confidence == "high"`; capability via Module Boundary

**Status:** Accepted
**Date:** 2026-05-18
**Tags:** specification-pattern · module-boundary · ci-enforcement · exit-criterion · honest-naming
**Related:** ADR-0008 (this phase) · ADR-0003 (this phase) · [production ADR-0034](../../../production/adrs/0034-event-sourcing-canonical-primitive.md)

## Context

The roadmap Phase 4 exit criterion requires that "re-running the same case hits RAG, not LLM" — meaning the solved-example store must contain the harvested outcome by the time the second workflow runs. The three design lenses split: performance shipped unconditional inline harvest; security shipped capability-gated harvest fired by Phase 5's `GateRunner`; best-practices deferred harvest to Phase 11's post-merge webhook with an operator CLI escape.

The critic was specific (`critique.md §"[B] §4"`): if harvest is operator-invoked CLI-only (best-practices), the exit criterion is met *only by test scaffolding* — the integration test manually invokes `codegenie rag harvest` between runs. Production behavior doesn't satisfy the criterion. Unconditional inline harvest (performance) risks poisoning the corpus with low-confidence outcomes that pass build/test but are wrong in subtle ways.

The synthesis must thread a needle: harvest inline (production behavior satisfies exit criterion) *and* gate the harvest (don't poison the corpus) *and* honestly model the capability (Python doesn't have runtime-unforgeable capabilities).

The second sub-problem is the capability. The security design called the `SolvedExampleWriteCapability` a "Capability pattern" with unforgeability via "private-by-convention name" + `import-linter`. The critic correctly flagged this as overclaim (`critique.md §"[S] §4"`): import-linter is a *lint* (CI-time), not a runtime control; Pydantic constructors are public; a local-CI-off run can forge the capability. The honest pattern name is "Module Boundary with CI enforcement," not "Capability."

## Options considered

- **Unconditional inline harvest** (performance lens). Every validated outcome harvested. **Pattern:** Eager ingestion. Risks poisoning corpus with confidence==medium outcomes.
- **Capability-gated by Phase 5 `GateRunner` only** (security lens). `GateRunner` mints capability on validated outcome; without Phase 5's mint, no harvest. **Pattern:** Capability (claimed) / Module Boundary (actual). Phase 5 hadn't shipped at design time; created an unwritten dep chain.
- **Operator-only CLI** (`codegenie rag harvest <workflow_id>`, best-practices). Operator runs harvest manually post-validation. **Pattern:** Manual workflow step. Fails roadmap exit criterion in production behavior.
- **Inline + confidence gate + Phase-4-local interim mint + CI-enforced module boundary** (synthesis). `FallbackTier.on_validated(outcome, trust)` checks `trust.passed AND trust.confidence == "high"`; mints `SolvedExampleWriteCapability` via `_phase4_local_capability_mint(workflow_id, chain_head)`; Phase 5 supersedes the mint when it ships. **Pattern:** Specification (named gate rule) + Module Boundary (mint location is bounded by `import-linter`).

## Decision

Inline auto-harvest is wired into `FallbackTier.on_validated(outcome, trust)` and fires *iff* `trust.passed AND trust.confidence == "high"`. Capability is `SolvedExampleWriteCapability`, constructed via the module-private factory `_phase4_local_capability_mint(workflow_id, chain_head)` in `src/codegenie/rag/ingest.py` (interim) — superseded by Phase 5's `GateRunner._mint_solved_example_capability(...)` when Phase 5 ships. **`import-linter` contracts + `tests/fence/test_solved_example_capability_mint_bounded.py`** block any module outside `{src/codegenie/gates/, src/codegenie/rag/ingest.py}` from importing the mint symbol. **Pattern:** Specification pattern (composable, named harvest rule) + Module Boundary with CI enforcement (named honestly — NOT GoF Capability).

The integration test `tests/integration/test_phase4_e2e_replay_lands_rag.py` runs the same CVE case twice with *no operator step between runs* — the second run must hit RAG with the inline-harvested record.

## Tradeoffs

| Gain | Cost |
|---|---|
| Roadmap exit criterion is met by production behavior, not test scaffolding | `confidence == "high"` is one knob; rare edge cases that should harvest but classify "medium" need a Phase-6.5 second-knob refinement (recorded as Open Question 7) |
| The capability is named honestly — Module Boundary, not Capability — no overclaim of runtime unforgeability | Without runtime enforcement, a contributor running CI checks locally with import-linter disabled can forge the capability; documented; CI is the backstop |
| Phase 5's eventual `GateRunner` mint slots in by swapping the import — no consumer change | Phase 4 ships *two* mint paths (`_phase4_local_capability_mint` and Phase 5's eventual mint); the interim mint must be removed when Phase 5 lands; tracked as a Phase-5 implementation TODO |
| Poisoned-corpus risk is bounded by Phase 5's strict-AND gate (build + install + tests + lockfile_policy + cve_delta + typecheck.typescript all pass) | Even strict-AND can pass on subtly-wrong fixes; mitigated by per-record BLAKE3 chain head (ADR-0012 — provenance gate) and the future operator quarantine path |
| Inline harvest is a single audit event (`SolvedExampleHarvested`) emitted from a single code path; no operator-portal-driven workflow step | If Phase 11's post-merge webhook (the second ingestion path) and inline harvest both fire on the same record, dedup by canonical YAML path is the mechanism; idempotent by `(plan_outcome_digest, repo_snapshot_sha)` |
| The harvest gate is a *named* `ConfidenceGate.passes(trust)` Specification — testable in isolation; future second-knob amendments are additive AND-clauses | Composable Specifications must remain *named* and *testable*; a free-form `if trust.passed and trust.confidence == "high" and …` ladder violates the pattern; a `tests/unit/fallback/test_confidence_gate.py` covers each clause separately |

## Pattern fit

The toolkit's Specification pattern explicitly names "trust-tier promotion conditions" as the canonical use: each clause is a named Specification, composed with AND/OR/NOT. `ConfidenceGate.passes(trust) ≡ TrustPassed AND HighConfidence` is the same shape — named, composable, testable.

The Module Boundary naming honors the critic's correction. True GoF Capability requires the constructor to be private at the language level; Python doesn't provide that. The honest pattern is "the mint symbol lives in *one* module; `import-linter` enforces every other module cannot import it; a CI test asserts the contract holds." That's the lint-level guarantee; the toolkit recognizes lint-as-architecture-enforcement as legitimate when the alternative (object-capability runtime) doesn't exist in the language.

## Consequences

- The roadmap exit-criterion integration test (`tests/integration/test_phase4_e2e_replay_lands_rag.py`) is a production-behavior test, not a scaffolding test.
- Phase 5's `GateRunner` consumes `FallbackTier.on_validated(...)` as the hook the orchestrator calls post-validate; the capability mint moves to `src/codegenie/gates/_capability_mint.py` when Phase 5 ships.
- Phase 11's merge-webhook adds a *second* ingestion path; both call the same `ingest_solved_example` primitive with different capabilities (Phase 5 vs Phase 11 mints).
- Ingestion is single-writer (per ADR-0013); `asyncio.Lock` around `store.add` is enforced inside `SolvedExampleStore`.
- `tests/fence/test_solved_example_capability_mint_bounded.py` is a load-bearing test; deleting it loses the architectural invariant.
- `HarvestSkipped(reason=low_confidence)` event fires on `trust.confidence != "high"` outcomes — operator-portal-visible signal that the gate held.
- The interim `_phase4_local_capability_mint` is removed in Phase 5 (Phase 5 implementer TODO recorded in `_attempts/Phase5-S1-01.md` when Phase 5 stories land).

## Reversibility

**Medium.** Removing the confidence gate (going to unconditional harvest) is one line of code change but reintroduces the poisoning risk; would require a Phase-4 ADR amendment. Removing inline harvest entirely (going to operator-CLI-only) breaks the production-behavior exit criterion; would require a roadmap re-interpretation. Swapping the Module Boundary enforcement to a true object-capability scheme would require a language-level capability runtime — out of scope; the lint-time enforcement is the durable shape.

## Evidence / sources

- `../final-design.md §Component 9 — SolvedExampleWriter`
- `../final-design.md §Departures from all three inputs` item 4
- `../final-design.md §Goal "Inline auto-harvest gate"`
- `../phase-arch-design.md §Component 10 — SolvedExampleWriter`
- `../phase-arch-design.md §Design patterns applied` row 12 (Specification + Capability gate)
- `../critique.md §"[B] §4"` (operator-CLI only fails the exit criterion in production behavior)
- `../critique.md §"[S] §4"` (capability overclaim)
- [production ADR-0034](../../../production/adrs/0034-event-sourcing-canonical-primitive.md) (audit event sourcing primitive)
