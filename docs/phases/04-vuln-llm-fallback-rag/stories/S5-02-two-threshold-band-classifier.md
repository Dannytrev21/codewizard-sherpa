# Story S5-02 — Two-threshold band classifier (`rag/confidence.py`)

**Step:** Step 5 — Ship SolvedExampleRetriever + two-threshold band + calibration smoke test
**Status:** Ready
**Effort:** S
**Depends on:** S5-01 (`ConfidenceClassifier` Protocol; retriever consumes), S1-04 (`RagHit`, `RagDegraded`, `RagMiss`, `Similarity` newtype, `AdapterConfidence` if available), S7-04 (`plugin.yaml` thresholds — the classifier reads `(high_floor, degraded_floor)` injected as values, not raw paths)
**ADRs honored:** ADR-04-0008 (two-threshold calibration band — `high_floor=0.85`, `degraded_floor=0.65` defaults in `plugin.yaml`; classification is a named, composable Specification-pattern rule), ADR-04-0007 (cross-architecture ONNX 5th-decimal float drift — the band absorbs drift, single-threshold would not), production ADR-0008 (objective signal trust score — `AdapterConfidence` is a `Literal["high","medium","low"]` that flows through the system, never a raw float), production ADR-0033 (domain-modeling discipline — closed sum return; named bands instead of magic numbers)

## Context

This is the load-bearing classifier that turns a candidate set (the verified, fenced output of S5-01's retriever) into the closed `RetrievalOutcome` discriminated union. The decision shape — *two* thresholds, not one — is the central architectural commitment of Step 5: a single global float threshold buckets `score=0.84` and `score=0.86` identically based on which side of an unprincipled cutoff they land, silently. ADR-04-0008 frames the cure: three named bands (`hit`, `degraded`, `miss`) defined by two floors, classification expressed as a Specification-pattern rule (composable, testable in isolation), and the thresholds living in `plugin.yaml` so calibration is config-as-data rather than code edits.

The cross-architecture ONNX float drift (ADR-04-0007) is the second motivator: BGE-small embedding cosine similarity can differ by ~0.005 at the 5th decimal between x86_64 and arm64. A single-threshold classifier at 0.85 would split-vote a record at `0.8498` (Linux) vs `0.8501` (macOS); the band absorbs it — both land in `RagHit` or both in `RagDegraded`, never split.

This story ships **only** the pure classifier — no I/O, no event emission, no store interaction. It is consumed by S5-01's retriever via the `ConfidenceClassifier` Protocol. Tests are table-driven on (score → expected variant) plus a Hypothesis monotonicity property: higher similarity must never yield lower confidence. The classifier's purity is structurally enforced — `tests/property/test_classifier_pure.py` AST-walks the module and asserts no logging, no I/O, no event emission.

A critical detail: when the candidate list is non-empty but the **top-1** similarity is below `degraded_floor`, the classifier returns `RagMiss(reason="top1_below_floor")` rather than fabricating a fourth state. This is edge case #10 in the arch design. The `RagMiss` variant carries an enumerated `reason` so audit consumers can distinguish "no candidates returned" (S5-01) from "candidates returned but all below band" (this story).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Goals — G6` (line 23) — `RetrievalOutcome = RagHit | RagMiss | RagDegraded` two-threshold band; defaults `high_floor=0.85`, `degraded_floor=0.65`.
  - `../phase-arch-design.md §Component design §9 — SolvedExampleRetriever` (lines 598–605) — band classification is the final step of the read pipeline.
  - `../phase-arch-design.md §Edge cases #10` — "RAG retriever returns top-1 below floor → `RagMiss`; LLM invoked without few-shot; harvested if validate passes (cold start)."
  - `../phase-arch-design.md §Design patterns applied` row referencing `RetrievalOutcome` — Tagged union + named bands + Specification pattern.
  - `../phase-arch-design.md §Confidence handling` (line 862) — "`AdapterConfidence` flows out as `Literal["high","medium","low"]`. Harvest gate fires on `confidence == "high"` only; `RagDegraded` feeds the LLM with an explicit 'low-confidence' tag."
- **Phase ADRs:**
  - `../ADRs/0008-two-threshold-calibration-band.md` — the canonical decision; "thresholds live in `plugin.yaml`, not in code"; band rules: `similarity >= high_floor → RagHit`, `degraded_floor <= similarity < high_floor → RagDegraded`, `similarity < degraded_floor → RagMiss`.
  - `../ADRs/0007-fastembed-onnx-over-sentence-transformers.md` — cross-architecture drift envelope; the band must be wider than drift.
- **Production ADRs:**
  - `../../../production/adrs/0008-objective-signal-trust-score.md` — `AdapterConfidence` literal contract for honest-confidence.
  - `../../../production/adrs/0033-domain-modeling-discipline.md` — closed sum types; named bands instead of magic numbers.
- **Source design:**
  - `../final-design.md §Component 11 — SolvedExampleRetriever — "Calibration band"`.
  - `../final-design.md §Departures from all three inputs` item 2 — the synthesis rationale for two thresholds rather than one.
- **High-level impl:**
  - `../High-level-impl.md §Step 5` — `rag/confidence.py` houses the pure similarity-to-AdapterConfidence mapping.
- **Existing code (READ BEFORE WRITING — Rule 8):**
  - `src/codegenie/rag/retriever.py` (S5-01) — the `ConfidenceClassifier` Protocol this story implements.
  - `src/codegenie/rag/models.py` (S1-04) — `RagHit(few_shot, score)`, `RagDegraded(near_match, score)`, `RagMiss(reason: Literal["empty_store","top1_below_floor","all_candidates_chain_orphan","all_candidates_model_mismatch"])`. If S1-04 shipped `RagMiss` as a bare class with no `reason`, surface per Global Rule 7 and amend S1-04 in this story's PR — the enumerated `reason` is load-bearing for audit consumers and is required by AC-7 below.
  - `src/codegenie/types/identifiers.py` (Phase 2/3) — `Similarity` newtype if available; if not, this story does not invent it (S1-04's responsibility).

## Goal

Ship `src/codegenie/rag/confidence.py` exporting a pure `BandClassifier` implementing the S5-01 `ConfidenceClassifier` Protocol, mapping `(score, high_floor, degraded_floor) → AdapterConfidence` via three named, table-driven bands, with closed-sum dispatch onto `RagHit | RagDegraded | RagMiss` and a Hypothesis-asserted monotonicity property.

## Acceptance criteria

### Module shape

- [ ] AC-1 — `src/codegenie/rag/confidence.py` exports exactly two public names: `BandClassifier` (concrete class implementing `ConfidenceClassifier`) and `classify_similarity` (pure function for unit-testing in isolation). `__all__` is pinned to these two. No other public symbols.
- [ ] AC-2 — `BandClassifier.__init__(*, high_floor: float, degraded_floor: float)` validates `0.0 <= degraded_floor < high_floor <= 1.0` at construction time; raises `ValueError("degraded_floor must be strictly less than high_floor")` otherwise. Test: parametrized rejection cases `(high=0.5, deg=0.6)`, `(high=0.5, deg=0.5)`, `(high=1.1, deg=0.0)`, `(high=0.5, deg=-0.1)`, `(high=0.5, deg=float("nan"))`.
- [ ] AC-3 — `classify_similarity(score: Similarity, *, high_floor: float, degraded_floor: float) -> Literal["high","medium","low"]` is a pure function — no module-level state read, no logger, no event emission. AST-walk test (`tests/property/test_classifier_pure.py`) asserts: no `import logging`, `import structlog`, no `logger`/`log`/`emit` symbol references in `confidence.py`, no file I/O calls.

### Band rule (Specification pattern; explicit, table-driven)

- [ ] AC-4 — `tests/unit/rag/test_band_classifier_table.py` parametrizes the canonical band table with defaults `(high_floor=0.85, degraded_floor=0.65)`:
  - score `1.00` → `"high"`
  - score `0.85` (exactly at `high_floor`) → `"high"`
  - score `0.8499` → `"medium"`
  - score `0.75` → `"medium"`
  - score `0.65` (exactly at `degraded_floor`) → `"medium"`
  - score `0.6499` → `"low"`
  - score `0.30` → `"low"`
  - score `0.00` → `"low"`
- [ ] AC-5 — **Inclusive at the high boundary, inclusive at the degraded boundary.** `similarity >= high_floor → "high"`; `degraded_floor <= similarity < high_floor → "medium"`; `similarity < degraded_floor → "low"`. Documented in the function docstring and pinned by the table above.
- [ ] AC-6 — **Ties go to the lower band on the high boundary, and to the medium band on the degraded boundary** — encoded by the `>=` inclusivity rule above. The "ties go to the lower band" framing in the manifest is *between RagHit and RagDegraded* (a score exactly at `high_floor` is `RagHit`, not `RagDegraded`); this story makes the rule explicit in the docstring and tests both boundaries verbatim.

### `BandClassifier.classify` (Protocol implementation)

- [ ] AC-7 — `BandClassifier.classify(candidates: list[tuple[FencedSegment, SolvedExample, Similarity]]) -> RetrievalOutcome` behavior:
  - `candidates == []` → `RagMiss(reason="empty_store")` (S5-01 short-circuits before reaching here on empty store; this is a defensive return so the Protocol is total).
  - non-empty: `top = max(candidates, key=lambda c: c[2])` (highest similarity).
  - If `classify_similarity(top.score, ...)` is `"high"` → `RagHit(few_shot=top.solved_example, score=top.score)`.
  - If `"medium"` → `RagDegraded(near_match=top.solved_example, score=top.score)`.
  - If `"low"` → `RagMiss(reason="top1_below_floor")` (edge case #10).
- [ ] AC-8 — When ties exist among candidates with equal similarity at the top, the classifier picks **deterministically**: highest score, then lexicographic order on `solved_example.id` (`SolvedExampleId` is a string newtype). Test: two candidates with `score=0.92` and ids `"a"`/`"b"` → `RagHit.few_shot.id == "a"`.
- [ ] AC-9 — The classifier dispatches via `match status` over the three `Literal` values with `assert_never` exhaustiveness on the impossible fourth arm. A deliberate-failure test injects a synthetic fourth literal at the type level and asserts mypy --strict diagnoses the missing arm.

### Monotonicity property (Hypothesis)

- [ ] AC-10 — `tests/property/test_retriever_threshold_monotonicity.py` — Hypothesis strategy generates `(score_low, score_high, high_floor, degraded_floor)` with `0 <= score_low <= score_high <= 1` and `0 <= degraded_floor < high_floor <= 1`. Property: `confidence_rank(classify_similarity(score_high, ...)) >= confidence_rank(classify_similarity(score_low, ...))` where `confidence_rank("high")=2, "medium"=1, "low"=0`. 1000+ runs green; no shrunken counterexample.
- [ ] AC-11 — `tests/property/test_band_classifier_drift_envelope.py` — given any score `s ∈ [degraded_floor + ε, high_floor - ε]` where `ε = 0.005` (the documented ONNX drift envelope from ADR-04-0007), `classify_similarity(s ± 0.005, ...)` always returns the *same* band as `classify_similarity(s, ...)`. Property asserts the band absorbs the documented drift at any score in the interior of a band — never on the boundaries (boundaries are pinned by the table tests, not by the property).

### Cross-newtype + closed sum invariants

- [ ] AC-12 — `classify_similarity` accepts the `Similarity` newtype (`NewType("Similarity", float)`); calling with a raw `float` is a mypy --strict error. Subprocess-mypy negative test in `tests/unit/rag/test_classifier_typecheck_negative.py` asserts the diagnostic.
- [ ] AC-13 — `RagMiss.reason` is `Literal["empty_store","top1_below_floor","all_candidates_chain_orphan","all_candidates_model_mismatch"]`; this story's classifier emits **only** `"empty_store"` (defensive) or `"top1_below_floor"`. The other two come from S5-01 (chain-orphan path) and S5-03 (model-mismatch path); verified by AST-walk that `confidence.py` only constructs `RagMiss` with these two reasons.

### Integration with S5-01

- [ ] AC-14 — `tests/unit/rag/test_retriever_with_real_classifier.py` — S5-01's `SolvedExampleRetriever` constructed with `BandClassifier(high_floor=0.85, degraded_floor=0.65)`; three table-driven inputs (single candidate with `score=0.90`, `0.75`, `0.40`) produce `RagHit`, `RagDegraded`, `RagMiss(reason="top1_below_floor")` respectively. The retriever-level event sequence is preserved.

## Implementation outline

```python
# src/codegenie/rag/confidence.py
"""Two-threshold band classifier for RAG retrieval.

Pure module — no I/O, no logging, no event emission. The classifier reads
band thresholds at construction time (from plugin.yaml in production) and
maps similarity scores to a closed AdapterConfidence literal, then to the
RetrievalOutcome variant.

ADR-04-0008 — band thresholds live in plugin.yaml, not in code.
"""

from typing import Literal, Final
from dataclasses import dataclass

from codegenie.rag.models import RagHit, RagDegraded, RagMiss, RetrievalOutcome
from codegenie.types.identifiers import Similarity, SolvedExampleId

AdapterConfidence = Literal["high", "medium", "low"]

_CONFIDENCE_RANK: Final[dict[AdapterConfidence, int]] = {
    "low": 0, "medium": 1, "high": 2,
}


def classify_similarity(
    score: Similarity,
    *,
    high_floor: float,
    degraded_floor: float,
) -> AdapterConfidence:
    """Pure score-to-band classifier.

    Bands (inclusive at lower boundary):
        score >= high_floor                          -> "high"
        degraded_floor <= score < high_floor         -> "medium"
        score < degraded_floor                       -> "low"
    """
    if score >= high_floor:
        return "high"
    if score >= degraded_floor:
        return "medium"
    return "low"


@dataclass(frozen=True)
class BandClassifier:
    high_floor: float
    degraded_floor: float

    def __post_init__(self) -> None:
        if not (0.0 <= self.degraded_floor < self.high_floor <= 1.0):
            raise ValueError(
                "degraded_floor must be strictly less than high_floor; "
                f"got high_floor={self.high_floor}, degraded_floor={self.degraded_floor}"
            )

    def classify(
        self,
        candidates: list[tuple[FencedSegment, SolvedExample, Similarity]],
    ) -> RetrievalOutcome:
        if not candidates:
            return RagMiss(reason="empty_store")
        top = max(candidates, key=lambda c: (c[2], -hash(c[1].id)))  # see AC-8 for tiebreak
        # Deterministic tiebreak: highest similarity, then lexicographic id.
        top_score = top[2]
        confidence = classify_similarity(
            top_score, high_floor=self.high_floor, degraded_floor=self.degraded_floor,
        )
        match confidence:
            case "high":
                return RagHit(few_shot=top[1], score=top_score)
            case "medium":
                return RagDegraded(near_match=top[1], score=top_score)
            case "low":
                return RagMiss(reason="top1_below_floor")
            case _:
                assert_never(confidence)
```

## TDD plan — red / green / refactor

### Red — write the failing test first

```python
# tests/unit/rag/test_band_classifier_table.py
import pytest
from codegenie.rag.confidence import classify_similarity
from codegenie.types.identifiers import Similarity

@pytest.mark.parametrize("score,expected", [
    (Similarity(1.00), "high"),
    (Similarity(0.85), "high"),     # inclusive at high_floor
    (Similarity(0.8499), "medium"),
    (Similarity(0.75), "medium"),
    (Similarity(0.65), "medium"),   # inclusive at degraded_floor
    (Similarity(0.6499), "low"),
    (Similarity(0.30), "low"),
    (Similarity(0.00), "low"),
])
def test_band_classifier_boundaries_are_inclusive_at_lower(score, expected):
    """ADR-04-0008 fixes the boundary semantics: `>=` at both floors.
    A score exactly at high_floor is 'high' (NOT degraded). A score
    exactly at degraded_floor is 'medium' (NOT miss). This pins the
    boundary so cross-architecture ONNX drift cannot silently re-classify
    a record."""
    assert classify_similarity(
        score, high_floor=0.85, degraded_floor=0.65,
    ) == expected
```

### Green — make it pass

1. Land `src/codegenie/rag/confidence.py` per the implementation outline — pure module, no logging/IO.
2. Land the band table tests verbatim; assert boundary inclusivity.
3. Land `BandClassifier.__post_init__` validation; parametrize rejection cases for invalid floor ordering / out-of-range / NaN.
4. Wire `BandClassifier.classify` to the three-arm dispatch with `assert_never`.
5. Add the Hypothesis monotonicity property under `tests/property/`.
6. Confirm `tests/unit/rag/test_retriever_with_real_classifier.py` (the S5-01 integration) passes — retriever + real classifier produce the right `RetrievalOutcome` for three canonical inputs.

### Refactor — clean up

- If the dispatch `match` expression grows past three arms, that's a smell — the band is exactly three. Resist adding a fourth.
- Confirm `__all__ = ("BandClassifier", "classify_similarity")`; no other public names.
- AST-purity test: `tests/property/test_classifier_pure.py` walks `confidence.py` and asserts no `import logging`, `import structlog`, `open(`, `Path(`, `os.`, `sys.stdout`/`sys.stderr` references.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/rag/confidence.py` | NEW — `BandClassifier` + `classify_similarity` (pure). |
| `tests/unit/rag/test_band_classifier_table.py` | NEW — boundary inclusivity table. |
| `tests/unit/rag/test_band_classifier_construction.py` | NEW — `__post_init__` validation (rejection cases). |
| `tests/unit/rag/test_band_classifier_dispatch.py` | NEW — empty list, single candidate, tiebreak determinism. |
| `tests/property/test_retriever_threshold_monotonicity.py` | NEW — Hypothesis: higher similarity never yields lower confidence. |
| `tests/property/test_band_classifier_drift_envelope.py` | NEW — Hypothesis: ±0.005 perturbation inside a band's interior never changes the band. |
| `tests/property/test_classifier_pure.py` | NEW — AST-walk: no logging/I/O in `confidence.py`. |
| `tests/unit/rag/test_classifier_typecheck_negative.py` | NEW — subprocess-mypy: raw `float` rejected; only `Similarity` accepted. |
| `tests/unit/rag/test_retriever_with_real_classifier.py` | NEW — S5-01 retriever + S5-02 classifier produce right variants for canonical inputs. |

## Out of scope

- **Reading `plugin.yaml`** — S7-04 owns the plugin manifest schema; this story takes thresholds as keyword arguments. The wiring (`BandClassifier(**plugin.yaml.thresholds)`) lives in the plugin's `FallbackTierPlanRecipeEngine` construction site (S7-01).
- **Per-task-class threshold tables** — ADR-04-0008 mentions future per-`(task_class, language, build_system)` thresholds; Phase 4 ships one global pair. This story does not generalize.
- **Calibration smoke test** — S5-04 seeds real fixtures + real embeddings and asserts the *defaults* land each fixture in the right band; this story tests the classifier *given* arbitrary thresholds.
- **Model-mismatch / chain-orphan exclusion** — these produce `RagMiss(reason=...)` from S5-01 and S5-03 respectively; this story emits only `"empty_store"` (defensive) and `"top1_below_floor"`.
- **Phase 6.5 evidence-based calibration** — the synthesis ledger defers this; Phase 4 ships conservative defaults, Phase 6.5 calibrates with evidence.

## Notes for the implementer

- **Purity is load-bearing.** The classifier is the most reused decision in the read pipeline; it gets called once per workflow, but the determinism property (S6-07) replays this dispatch 50 times under cassette replay. Any hidden state (cached threshold, lazy-loaded config, mutable singleton) would re-introduce non-determinism. Keep it a pure function + frozen dataclass.
- **Boundary inclusivity is the bug-prone choice.** Inclusive at the lower boundary means `score == high_floor` is `"high"`, not `"medium"`. Inclusive at the *upper* boundary would be wrong — it would let `score < degraded_floor` slip into `"medium"` at exactly the lower edge. The arch table uses `>=` at both floors; the boundary test pins it.
- **`Similarity` newtype.** S1-04 ships it; if it's missing, surface per Global Rule 7 and add it as part of S1-04 (smart-constructed `[-1.0, 1.0]`, mypy --strict newtype). Do not invent a local `Similarity` here.
- **`RagMiss.reason` enumeration.** S1-04 should ship `RagMiss(reason: Literal[...])` with the four-value union. If S1-04 shipped a bare `RagMiss`, surface per Global Rule 7 and add the enumeration as part of S1-04 — downstream audit consumers (operator portal, Phase 6.5 calibration harness) read this `reason` field. AC-13 depends on this shape.
- **Tiebreak determinism.** Two candidates at exact same `score=0.92` is rare but possible (especially in seeded fixtures). The arch design doesn't prescribe a tiebreaker; AC-8 picks lexicographic on `id` to make the choice deterministic for the determinism-replay property in S6-07. Document the choice in the function docstring so a future reader understands why the `max(...)` `key` is non-trivial.
- **Where the thresholds come from at production.** `plugin.yaml` carries `rag.high_floor` and `rag.degraded_floor`; S7-01's plugin engine reads them and constructs `BandClassifier(**values)` once at plugin load time. The classifier is then re-used across workflows. The "config-as-data" framing in ADR-04-0008 lives entirely in the plugin manifest schema; the classifier is unaware of YAML.
- **`AdapterConfidence` is a Literal, not an enum.** Production ADR-0008 commits to `Literal["high","medium","low"]` because it composes with `TrustOutcome.confidence` (Phase 3) by exact-string equality. An `Enum` would not — the Phase 3 surface is the string literal. Resist the temptation to "improve" with an enum.
- **The synthesis ledger framing.** ADR-04-0008's tradeoff table is worth keeping next to your editor: the band absorbs ONNX drift, makes the failure mode explicit, and turns calibration into a YAML bump. The cost is the third match arm — cheap. If a reviewer asks "why two thresholds instead of one," the ledger entry is the answer.
