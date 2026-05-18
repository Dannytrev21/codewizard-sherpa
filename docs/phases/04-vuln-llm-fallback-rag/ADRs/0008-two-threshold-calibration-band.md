# ADR-0008: Two-threshold calibration band for RAG retrieval — `high_floor`, `degraded_floor` in `plugin.yaml`

**Status:** Accepted
**Date:** 2026-05-18
**Tags:** tagged-union · honest-confidence · config-as-data · specification-pattern · adr-0008
**Related:** ADR-0009 (this phase) · [production ADR-0008](../../../production/adrs/0008-objective-signal-trust-score.md)

## Context

All three design lenses chose RAG retrieval thresholds as single global floats: performance picked 0.92/0.97, security picked 0.85, best-practices picked 0.78. The critic identified this as a shared blind spot (`critique.md §"Where do all three quietly agree on something questionable" item 1`): "retrieval quality at Phase-4-corpus-size (≤200 examples) is a different problem than retrieval quality at portfolio scale. With <50 examples, *every* cosine-similarity threshold is gameable; the 'top-K with threshold' pattern is a stand-in for 'the corpus is too small for any retrieval to matter.'"

A single float threshold also makes the failure mode silent: `score=0.84` and `score=0.86` get bucketed identically as miss/hit depending on which side of an unprincipled cutoff they land. Phase 6.5 (per-task-class eval harness) is where calibration evidence will live, but Phase 4 has to ship a shape that *Phase 6.5 can calibrate against*.

The honest model is three retrieval outcomes — confident hit, near-match (use with caution), miss — encoded as a discriminated union, with the two thresholds living in plugin configuration rather than in code.

Cross-architecture ONNX drift (ADR-0007 of this phase) at the 5th decimal exacerbates the single-threshold fragility: 0.85001 on x86_64 and 0.84998 on arm64 produce different retrieval outcomes. A *band* with explicit "degraded" middle absorbs this.

## Options considered

- **Single global float threshold** (all three design lenses). One number; values above hit, values below miss. **Pattern:** Magic-number cutoff. Silent failure mode at the boundary; gameable on small corpora; sensitive to cross-arch float drift.
- **Single threshold + `Optional[SolvedExample]` return** (implicit alternative). Distinguishes hit-with-example vs no-example via Optional, but doesn't model degraded. **Pattern:** Optional-field overload. The toolkit's "make illegal states unrepresentable" flag fires — `Optional[float]` for similarity score lets `Optional[SolvedExample]` and `Optional[float]` disagree on hit/miss.
- **Two thresholds + three-variant discriminated union** (`RagHit | RagDegraded | RagMiss`) with bands defined in `plugin.yaml`. **Pattern:** Tagged union + named bands + Specification pattern (band membership is a composable rule).
- **Learned classifier instead of thresholds** (e.g., train a small classifier per task class on labeled hit/miss examples). **Pattern:** ML classifier replaces heuristic. Rejected for Phase 4 — labeled training data doesn't exist yet (Phase 6.5's job); over-engineered for the corpus size; an ML decision boundary is still calibrated thresholds wearing a different hat at this scale.

## Decision

`SolvedExampleRetriever.query(...)` returns `RetrievalOutcome = RagHit(few_shot, score) | RagDegraded(near_match, score) | RagMiss`. Classification is by two floats living in `plugins/.../plugin.yaml`:

- `similarity ≥ high_floor` (default `0.85`) → `RagHit(few_shot=record)`
- `degraded_floor ≤ similarity < high_floor` (default `0.65`) → `RagDegraded(near_match=record)` — fed to LLM as few-shot with a `"low-confidence"` tag in the prompt template
- `similarity < degraded_floor` → `RagMiss`

Defaults are conservative initial values; Phase 6.5's calibration harness owns evidence-based tuning. **Thresholds live in `plugin.yaml`, not in code** — calibration is config, not a code edit. **Pattern:** Tagged union + named bands instead of magic numbers + Specification pattern (band classification is a named, composable rule).

## Tradeoffs

| Gain | Cost |
|---|---|
| The single-threshold silent failure at the boundary is replaced by an explicit `RagDegraded` state — the LLM is told the few-shot is near-match, not certain-match | Three outcomes means three consumer code paths in `FallbackTier` (vs two for hit/miss); the additional `match` arm is cheap |
| Calibration is config-as-data — Phase 6.5 ships new evidence and operators bump `plugin.yaml` without a code release | Calibration *quality* still depends on Phase 6.5 evidence; until that lands, the defaults are conservative guesses |
| Cross-architecture ONNX drift at 5th decimal is absorbed by the band — `0.8501` and `0.8498` are both either `RagHit` or `RagDegraded`, never split | The band width itself must be wider than the cross-arch drift envelope; if drift is 0.005, a band of 0.001 reintroduces the failure |
| The honest-confidence commitment (commitment §2.3) is honored — `RagDegraded` is the audit signal analogous to `IndexHealthProbe`'s degraded state | LLM few-shot output is shaped by the few-shot it sees; a `RagDegraded` near-match may bias the LLM toward a *wrong* shape — mitigated by the prompt template's explicit "low-confidence" tag and Phase 5 strict-AND validation |
| Per-`(task_class, language, build_system)` thresholds can differ as Phase 6.5 calibrates — heterogeneous corpora get heterogeneous bands | More configuration surface to maintain; documented in `plugins/.../plugin.yaml` per plugin |

## Pattern fit

The toolkit's tagged union / sum type pattern applies cleanly: `RagHit` carries a `few_shot` example; `RagMiss` is bare; `RagDegraded` carries a `near_match`. The three shapes are genuinely different — modeling them as `Optional[SolvedExample] + Optional[float]` lets illegal states (`few_shot=None, score=0.95`) be representable, which is the anti-pattern the discipline forbids ([ADR-0033](../../../production/adrs/0033-domain-modeling-discipline.md)).

The Specification pattern applies to band classification: "the band a similarity falls into" is a named, composable rule (`is_high_confidence ⇔ score ≥ high_floor`; `is_degraded ⇔ degraded_floor ≤ score < high_floor`). Both rules are exposed as Pydantic validators on `RetrievalOutcome.classify(score, high_floor, degraded_floor)`; the rule composition is one place and is testable in isolation.

## Consequences

- `RetrievalOutcome` is a stable contract Phase 5 and Phase 6 consume; widening it (e.g., a future `RagAmbiguous` for multi-hit ties) is a Phase-amendment ADR.
- The inline-harvest gate ([ADR-0009](0009-inline-auto-harvest-confidence-gate.md)) reads `TrustOutcome.confidence == "high"` rather than a numeric threshold — the band shape and the harvest shape both speak the same vocabulary.
- Phase 6.5's calibration harness reads `RetrievalOutcome` events from the spanning event log and produces evidence-backed threshold proposals per `(task_class, language, build_system)`; operators bump `plugin.yaml` accordingly.
- A `RagDegraded` outcome shows up in audit as a typed event (`RagDegraded(score, near_match_id)`); the operator portal renders it distinctly from `RagHit`.
- The prompt template (`plugins/.../skills/leaf-llm-instruction.md`) has a conditional block for "this few-shot is low-confidence; treat as guidance, not template" that fires on `RagDegraded`.
- Tests: `tests/unit/rag/test_retriever_thresholds.py` covers band classification (0.95→hit, 0.75→degraded, 0.40→miss); `tests/property/test_retriever_band_monotonic.py` Hypothesis-asserts that higher similarity never yields lower confidence.
- The contract `Phase 6.5 sees retrieval band evidence shaped as typed events` lets the harness work without parsing prose logs.

## Reversibility

**High.** Threshold values are config; bumping them is one YAML edit, zero code change. Collapsing the band back to a single threshold would require deleting `RagDegraded` from the union and removing the `match` arm — Phase-4-local edits; but loses the honest-confidence signal Phase 6.5 builds on. Promoting to a learned classifier (Phase 11+) lands behind the same `RetrievalOutcome` Protocol — adapter swap, no consumer change.

## Evidence / sources

- `../final-design.md §Component 11 — SolvedExampleRetriever` ("Calibration band")
- `../final-design.md §Departures from all three inputs` item 2
- `../final-design.md §Goal "Honest confidence"` (§Load-bearing commitments check §2.3)
- `../phase-arch-design.md §Goals — G6`
- `../phase-arch-design.md §Component 9 — SolvedExampleRetriever`
- `../critique.md §"Where do all three quietly agree on something questionable" item 1`
- [production ADR-0008](../../../production/adrs/0008-objective-signal-trust-score.md) (honest confidence as objective signal)
- [production ADR-0033](../../../production/adrs/0033-domain-modeling-discipline.md) (sum-type discipline)
