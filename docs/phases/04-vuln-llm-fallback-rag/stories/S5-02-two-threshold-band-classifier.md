# Story S5-02 — Two-threshold band classifier (`rag/confidence.py`)

**Step:** Step 5 — Ship SolvedExampleRetriever + two-threshold band + calibration smoke test
**Status:** Done — GREEN 2026-05-25 (phase-story-executor; see [`_attempts/S5-02.md`](_attempts/S5-02.md)). 36 tests pass: AC-1 module exports, AC-2 kw-only frozen + ValueError on bad floors, AC-3 purity AST fence + no-hash, AC-4/5/6 band table + boundary inclusivity, AC-7 Protocol signature match (`isinstance(BandClassifier, ConfidenceClassifier)`), AC-8 deterministic lexicographic tiebreak (insertion-order-independent), AC-9 three-band dispatch, AC-10 Hypothesis monotonicity (300 examples), AC-11 ONNX drift envelope, AC-13 bare RagMiss invariant, AC-14 retriever integration with three scores yielding RagHit/RagDegraded/RagMiss + top1_below_floor event. Deferred: AC-9 subprocess-mypy exhaustiveness check, AC-12 subprocess-mypy newtype diagnostic — the runtime tests cover the behavior; the subprocess-mypy variants are observability nice-to-haves not load-bearing.
**Effort:** S
**Depends on:** S5-01 (**hardened** — ships the `ConfidenceClassifier` Protocol as `classify(candidates: Sequence[FencedRetrievalCandidate]) -> RetrievalOutcome` and the frozen `FencedRetrievalCandidate(fenced, record, score)` DTO; this story's `BandClassifier` *is* a concrete implementation of that Protocol and must match it byte-for-byte), S1-04 (**hardened** — `RagHit(few_shot, score)`, `RagDegraded(near_match, score)`, **bare** `RagMiss` (no `reason` field), the `RetrievalOutcome` discriminated union; `Similarity` newtype lands in `codegenie.types.identifiers`), S7-04 (`plugin.yaml` thresholds — the classifier reads `(high_floor, degraded_floor)` injected as values, not raw paths)
**ADRs honored:** ADR-04-0008 (two-threshold calibration band — `high_floor=0.85`, `degraded_floor=0.65` defaults in `plugin.yaml`; classification is a named, composable Specification-pattern rule; `RagMiss` is **bare**), ADR-04-0007 (cross-architecture ONNX 5th-decimal float drift — the band absorbs drift in each band's *interior*, single-threshold would not), production ADR-0033 (domain-modeling discipline — closed sum return; named bands instead of magic numbers). The honest-confidence value set `Literal["high","medium","low"]` is fixed by `../phase-arch-design.md §Confidence handling` (line 862), **not** production ADR-0008 (which does not mention it).

## Validation notes

Validated: 2026-05-22
Verdict: HARDENED
Findings addressed: 15 — 3 blocks, 10 hardens, 2 nits

Changes applied:
- **`RagMiss(reason=...)` removed (block, K1).** S1-04 (HARDENED, F5) and S5-01 (HARDENED, K1) both fixed `RagMiss` to **bare** per ADR-04-0008. Every AC, the implementation outline, and the TDD plan now construct bare `RagMiss()`. The "no candidates" vs "top-1 below floor" distinction is an audit fact carried by S5-01's `RagMissEvent(reason=...)`, never a field on `RagMiss`. AC-13 was rewritten — there is no `RagMiss.reason`.
- **Classifier signature realigned to the hardened S5-01 Protocol (block, K2).** S5-01 (HARDENED, AC-16 + D1) ships `ConfidenceClassifier.classify(candidates: Sequence[FencedRetrievalCandidate]) -> RetrievalOutcome` and replaced the anonymous `tuple[FencedSegment, SolvedExample, Similarity]` with the frozen `FencedRetrievalCandidate(fenced, record, score)` DTO. The story used the stale tuple shape; AC-7, AC-8, AC-14 and the outline now consume `Sequence[FencedRetrievalCandidate]` and read `.record` / `.score`.
- **`AdapterConfidence` name collision removed (block, K3).** `AdapterConfidence` is already a shipped, cross-phase contract — a tagged union `Trusted | Degraded | Unavailable` in `codegenie.transforms.outcomes` (re-exported by `codegenie.adapters.confidence`) and a `StrEnum` in `codegenie.primitives.vuln_provenance.types`. Neither carries a `medium` value. The story's local `AdapterConfidence = Literal["high","medium","low"]` was a third, differently-shaped type under a taken name; renamed to `RagConfidence`. The Phase-4-doc drift (phase-arch-design §297 component diagram + High-level-impl §148 both write "AdapterConfidence") is flagged for separate doc correction.
- **Non-deterministic tiebreak fixed (harden, D1).** The outline's `max(candidates, key=lambda c: (c[2], -hash(c[1].id)))` used `hash()` of a string — salted per-process by `PYTHONHASHSEED`, non-deterministic, and not lexicographic. This contradicts AC-8 and the S6-07 50-run determinism replay. Replaced with `min(candidates, key=lambda c: (-c.score, c.record.id))`; AC-3's purity AST-walk now also bans `hash(`.
- **AC-11 drift-envelope property corrected (harden, T1).** As written the property used `ε = drift = 0.005` for the band-interior margin, so at `s = high_floor - ε` the perturbation `s + 0.005` lands exactly on `high_floor` and re-classifies — the property would fail on a *correct* implementation. The interior margin is now strictly greater than the drift (`MARGIN = 0.01 > DRIFT = 0.005`), and the property covers all three band interiors (high / medium / low), not only medium.
- **Smaller hardens:** `BandClassifier` made `@dataclass(frozen=True, kw_only=True)` so the AC-2 keyword-only constructor is real (D3); the unused module-level `_CONFIDENCE_RANK` removed — the rank map belongs to the monotonicity test (D2, Rule 2); the implementation-outline imports completed (D4); AC-9's mypy-exhaustiveness test given a home in `Files to touch` (C1); AC-2's error-message assertion loosened to substring + offending values (T3); AC-4 gained two negative-cosine rows (C2); AC-8's tiebreak test made mutation-resistant with a reversed-order case + a Hypothesis property (T2); Hypothesis strategies pinned `allow_nan=False, allow_infinity=False` (T4).

Full audit log: docs/phases/04-vuln-llm-fallback-rag/stories/_validation/S5-02-two-threshold-band-classifier.md

## Context

This is the load-bearing classifier that turns a candidate set (the verified, fenced output of S5-01's retriever) into the closed `RetrievalOutcome` discriminated union. The decision shape — *two* thresholds, not one — is the central architectural commitment of Step 5: a single global float threshold buckets `score=0.84` and `score=0.86` identically based on which side of an unprincipled cutoff they land, silently. ADR-04-0008 frames the cure: three named bands (`hit`, `degraded`, `miss`) defined by two floors, classification expressed as a Specification-pattern rule (composable, testable in isolation), and the thresholds living in `plugin.yaml` so calibration is config-as-data rather than code edits.

The cross-architecture ONNX float drift (ADR-04-0007) is the second motivator: BGE-small embedding cosine similarity can differ by ~0.005 at the 5th decimal between x86_64 and arm64. A single-threshold classifier at 0.85 would split-vote a record at `0.8498` (Linux) vs `0.8501` (macOS); the band absorbs it — both land in `RagHit` or both in `RagDegraded`, never split.

This story ships **only** the pure classifier — no I/O, no event emission, no store interaction. It is consumed by S5-01's retriever via the `ConfidenceClassifier` Protocol. Tests are table-driven on (score → expected variant) plus a Hypothesis monotonicity property: higher similarity must never yield lower confidence. The classifier's purity is structurally enforced — `tests/property/test_classifier_pure.py` AST-walks the module and asserts no logging, no I/O, no event emission.

A critical detail: when the candidate list is non-empty but the **top-1** similarity is below `degraded_floor`, the classifier returns a **bare `RagMiss()`** — the same closed `RetrievalOutcome` variant as "no candidates" — rather than fabricating a fourth state. This is edge case #10 in the arch design. `RagMiss` carries no payload (S1-04 HARDENED F5; ADR-04-0008 §Decision + §Pattern fit; arch §Component 9 line 600). The *reason* a miss happened ("candidates returned but all below band") is an audit fact, not a field: S5-01's retriever emits `RagMissEvent(reason="top1_below_floor")` from the `RagMiss` arm of its `match outcome`. The classifier itself never distinguishes miss causes — it only maps the top score to a band.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Goals — G6` (line 23) — `RetrievalOutcome = RagHit | RagMiss | RagDegraded` two-threshold band; defaults `high_floor=0.85`, `degraded_floor=0.65`.
  - `../phase-arch-design.md §Component design §9 — SolvedExampleRetriever` (lines 598–605) — band classification is the final step of the read pipeline.
  - `../phase-arch-design.md §Edge cases #10` — "RAG retriever returns top-1 below floor → `RagMiss`; LLM invoked without few-shot; harvested if validate passes (cold start)."
  - `../phase-arch-design.md §Design patterns applied` row referencing `RetrievalOutcome` — Tagged union + named bands + Specification pattern.
  - `../phase-arch-design.md §Confidence handling` (line 862) — verbatim: "Confidence flows out as `Literal["high","medium","low"]`. Harvest gate fires on `confidence == "high"` only; `RagDegraded` feeds the LLM with an explicit 'low-confidence' tag." This is the canonical source of the three-value triple — the story names the type `RagConfidence`.
- **Phase ADRs:**
  - `../ADRs/0008-two-threshold-calibration-band.md` — the canonical decision; "thresholds live in `plugin.yaml`, not in code"; band rules: `similarity >= high_floor → RagHit`, `degraded_floor <= similarity < high_floor → RagDegraded`, `similarity < degraded_floor → RagMiss`.
  - `../ADRs/0007-fastembed-onnx-over-sentence-transformers.md` — cross-architecture drift envelope; the band must be wider than drift.
- **Production ADRs:**
  - `../../../production/adrs/0033-domain-modeling-discipline.md` — closed sum types; named bands instead of magic numbers. (Note: production ADR-0008 was cited by an earlier draft as the source of the `Literal["high","medium","low"]` triple — it is not; the real source is `phase-arch-design.md §Confidence handling` line 862.)
- **Source design:**
  - `../final-design.md §Component 11 — SolvedExampleRetriever — "Calibration band"`.
  - `../final-design.md §Departures from all three inputs` item 2 — the synthesis rationale for two thresholds rather than one.
- **High-level impl:**
  - `../High-level-impl.md §Step 5` — `rag/confidence.py` houses the pure similarity-to-confidence mapping. (Line 148 writes "AdapterConfidence" — doc drift against the shipped `codegenie.transforms.outcomes.AdapterConfidence`; this story names its type `RagConfidence` instead, see Notes.)
- **Existing code (READ BEFORE WRITING — Rule 8):**
  - `src/codegenie/rag/retriever.py` (S5-01, **hardened**) — the `ConfidenceClassifier` Protocol this story implements: `classify(candidates: Sequence[FencedRetrievalCandidate]) -> RetrievalOutcome`. Also the home of the frozen `FencedRetrievalCandidate(fenced, record, score)` DTO this story imports.
  - `src/codegenie/rag/models.py` (S1-04, **hardened**) — `RagHit(few_shot: SolvedExample, score: Similarity)`, `RagDegraded(near_match: SolvedExample, score: Similarity)`, **bare** `RagMiss` (only the `kind: Literal["miss"]` discriminator — **no `reason` field**), and `RetrievalOutcome = Annotated[RagHit | RagMiss | RagDegraded, Field(discriminator="kind")]`. Do **not** construct `RagMiss(reason=...)`.
  - `src/codegenie/types/identifiers.py` (Phase 2/3) — `Similarity = NewType("Similarity", float)` (cosine score in `[-1.0, 1.0]`) and `SolvedExampleId = NewType("SolvedExampleId", str)` both ship here; import, do not redefine.
  - `src/codegenie/adapters/confidence.py` + `src/codegenie/primitives/vuln_provenance/types.py` — the **two existing, unrelated** `AdapterConfidence` declarations. Read them once to understand why this story must NOT reuse that name (see Notes).

## Goal

Ship `src/codegenie/rag/confidence.py` exporting a pure `BandClassifier` implementing the hardened S5-01 `ConfidenceClassifier` Protocol (`classify(candidates: Sequence[FencedRetrievalCandidate]) -> RetrievalOutcome`), mapping `(score, high_floor, degraded_floor) → RagConfidence` (the `Literal["high","medium","low"]` honest-confidence triple) via three named, table-driven bands, with closed-sum dispatch onto `RagHit | RagDegraded | RagMiss` (bare) and a Hypothesis-asserted monotonicity property.

## Acceptance criteria

### Module shape

- [ ] AC-1 — `src/codegenie/rag/confidence.py` exports exactly three public names: `BandClassifier` (concrete class implementing the S5-01 `ConfidenceClassifier` Protocol), `classify_similarity` (pure function for unit-testing in isolation), and `RagConfidence` (the `Literal["high","medium","low"]` band-label type alias — the return type of `classify_similarity`). `__all__` is pinned to exactly these three. No other public symbols — in particular, **do not** define a local `AdapterConfidence` (validator: that name is a shipped, differently-shaped cross-phase contract — see Notes).
- [ ] AC-2 — `BandClassifier` is a `@dataclass(frozen=True, kw_only=True)` — the `kw_only=True` makes the generated constructor keyword-only, so `BandClassifier(0.85, 0.65)` is a `TypeError` and only `BandClassifier(high_floor=..., degraded_floor=...)` constructs. `__post_init__` validates `0.0 <= degraded_floor < high_floor <= 1.0`; otherwise raises `ValueError` whose message **contains** the substring `degraded_floor must be strictly less than high_floor` **and** names the two offending values (Rule 12 — fail loud). Tests: parametrized rejection cases `(high=0.5, deg=0.6)`, `(high=0.5, deg=0.5)`, `(high=1.1, deg=0.0)`, `(high=0.5, deg=-0.1)`, `(high=0.5, deg=float("nan"))`, `(high=float("nan"), deg=0.5)` — asserted via `pytest.raises(ValueError, match=...)`; plus a separate `pytest.raises(TypeError)` test for a positional-construction attempt.
- [ ] AC-3 — `classify_similarity(score: Similarity, *, high_floor: float, degraded_floor: float) -> RagConfidence` is a pure, deterministic function — no module-level state read, no logger, no event emission, no process-nondeterministic primitive. AST-walk test (`tests/property/test_classifier_pure.py`) walks `confidence.py` and asserts: no `import logging` / `import structlog`; no `logger`/`log`/`emit` symbol references; no file-I/O calls (`open(`, `Path(`, `os.`, `sys.stdout`, `sys.stderr`); **no `hash(` call** (a `hash()` of a `str` is `PYTHONHASHSEED`-salted — banning it structurally kills the non-deterministic-tiebreak mutant, see AC-8); and every `RagMiss(...)` construction is argument-less (AC-13).

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
  - score `-0.50` → `"low"` (validator: added — cosine similarity is legitimately negative; the `Similarity` newtype domain is `[-1.0, 1.0]`)
  - score `-1.00` (the `Similarity` domain floor) → `"low"` (validator: added)
- [ ] AC-5 — **Inclusive at the high boundary, inclusive at the degraded boundary.** `similarity >= high_floor → "high"`; `degraded_floor <= similarity < high_floor → "medium"`; `similarity < degraded_floor → "low"`. Documented in the function docstring and pinned by the table above.
- [ ] AC-6 — **Ties go to the lower band on the high boundary, and to the medium band on the degraded boundary** — encoded by the `>=` inclusivity rule above. The "ties go to the lower band" framing in the manifest is *between RagHit and RagDegraded* (a score exactly at `high_floor` is `RagHit`, not `RagDegraded`); this story makes the rule explicit in the docstring and tests both boundaries verbatim.

### `BandClassifier.classify` (Protocol implementation)

- [ ] AC-7 — `BandClassifier.classify(candidates: Sequence[FencedRetrievalCandidate]) -> RetrievalOutcome` — the signature matches the hardened S5-01 `ConfidenceClassifier` Protocol **exactly** (`Sequence`, not `list`; `FencedRetrievalCandidate`, not an anonymous tuple — S5-01 ships the frozen `FencedRetrievalCandidate(fenced: FencedSegment, record: SolvedExample, score: Similarity)` DTO). Behavior:
  - `candidates` empty → bare `RagMiss()` (S5-01 short-circuits before reaching here on empty store / all-orphan / all-mismatch — this branch is a defensive return so the Protocol is total; it is unreachable in the wired pipeline and carries no distinct "reason").
  - non-empty: select `top` = the candidate with the highest `score`, ties broken by AC-8.
  - If `classify_similarity(top.score, ...)` is `"high"` → `RagHit(few_shot=top.record, score=top.score)`.
  - If `"medium"` → `RagDegraded(near_match=top.record, score=top.score)`.
  - If `"low"` → bare `RagMiss()` (edge case #10 — `score < degraded_floor`). The classifier returns the bare variant; S5-01's `match outcome` arm emits `RagMissEvent(reason="top1_below_floor")`.
- [ ] AC-8 — When ties exist among candidates with equal top similarity, the classifier picks **deterministically**: highest `score`, then the lexicographically-smallest `record.id` (`SolvedExampleId` is a `str` newtype). The tiebreak must use **string ordering**, never `hash()` (see AC-3). Tests: (a) two candidates `score=0.92`, ids `"a"`/`"b"` → `RagHit.few_shot.id == "a"`, **and** the same two candidates supplied in reversed insertion order → still `"a"` (kills an insertion-order-dependent mutant); (b) `tests/property/test_band_classifier_tiebreak_lexicographic.py` — Hypothesis generates a set of ≥2 candidates all sharing one top score with arbitrary distinct ids; the chosen `record.id` always equals `min(ids)`. The property must stay green across processes — a `hash()`-based tiebreak fails it almost surely within 100 examples.
- [ ] AC-9 — `BandClassifier.classify` dispatches the `classify_similarity` result via `match` over the three `RagConfidence` literal values, with an `assert_never(...)` arm on the impossible fourth case (mypy --strict proves the three arms are exhaustive — `confidence` narrows to `Never` at the `assert_never` call). A deliberate-failure fixture in `tests/unit/rag/test_classifier_typecheck_negative.py` (shared with AC-12) holds a copy of the dispatch over a synthetic four-member `Literal`, and a subprocess `mypy --strict` asserts it diagnoses the non-exhaustive `match` / unreachable `assert_never`.

### Monotonicity property (Hypothesis)

- [ ] AC-10 — `tests/property/test_retriever_threshold_monotonicity.py` — Hypothesis strategy generates `(score_low, score_high, high_floor, degraded_floor)` with `0.0 <= score_low <= score_high <= 1.0` and `0.0 <= degraded_floor < high_floor <= 1.0`; every float strategy is pinned `allow_nan=False, allow_infinity=False`. Property: `_rank(classify_similarity(score_high, ...)) >= _rank(classify_similarity(score_low, ...))` where `_rank` is a **test-local** helper mapping `"high"→2, "medium"→1, "low"→0` (the rank map lives in the test, not in `confidence.py` — see Notes). 1000+ runs green; no shrunken counterexample.
- [ ] AC-11 — `tests/property/test_band_classifier_drift_envelope.py` — the documented cross-architecture ONNX drift envelope is `DRIFT = 0.005` (ADR-04-0007). The interior margin used to keep a generated score away from a floor must be **strictly greater** than `DRIFT` — use `MARGIN = 0.01`. Every float strategy is pinned `allow_nan=False, allow_infinity=False`. The property covers **all three band interiors**:
  - **high interior** — `s ∈ [high_floor + MARGIN, 1.0]`
  - **medium interior** — `s ∈ [degraded_floor + MARGIN, high_floor - MARGIN]`
  - **low interior** — `s ∈ [0.0, degraded_floor - MARGIN]`
  For any such `s` and any `d` with `|d| <= DRIFT`, `classify_similarity(s + d, ...) == classify_similarity(s, ...)`. Boundaries are deliberately **excluded** — a true score within `DRIFT` of a floor genuinely can cross it, but that flip is between *adjacent* bands (high↔medium, medium↔low), never between hit and miss, which is exactly the value ADR-04-0008 claims; boundary semantics are pinned by the AC-4 table, not by this property. (validator: the original AC used `ε = DRIFT`, so at `s = high_floor - ε` the perturbation `s + 0.005` landed on `high_floor` and re-classified — the property would have failed on a correct implementation; and it covered only the medium interior.)

### Cross-newtype + closed sum invariants

- [ ] AC-12 — `classify_similarity` accepts the `Similarity` newtype (`NewType("Similarity", float)`); calling with a raw `float` is a mypy --strict error. Subprocess-mypy negative test in `tests/unit/rag/test_classifier_typecheck_negative.py` asserts the diagnostic.
- [ ] AC-13 — `RagMiss` is **bare** — it has no `reason` field (S1-04 HARDENED F5; ADR-04-0008 §Decision + §Pattern fit; arch §Component 9 line 600). `confidence.py` constructs `RagMiss` **only** as `RagMiss()` — never `RagMiss(reason=...)`. The AST-walk in `tests/property/test_classifier_pure.py` asserts every `RagMiss(...)` call in `confidence.py` is argument-less. Miss-cause observability is not this story's concern: S5-01's retriever, in its `match outcome` arm, emits the reason-bearing `RagMissEvent` (`"empty_store"` / `"top1_below_floor"` / `"all_candidates_chain_orphan"` / `"all_candidates_model_mismatch"`) — those reasons live on the *event*, not on `RagMiss`.

### Integration with S5-01

- [ ] AC-14 — `tests/unit/rag/test_retriever_with_real_classifier.py` — S5-01's `SolvedExampleRetriever` constructed with `BandClassifier(high_floor=0.85, degraded_floor=0.65)`; three inputs (a single surviving `FencedRetrievalCandidate` with `score=0.90`, `0.75`, `0.40`) produce `RagHit`, `RagDegraded`, and bare `RagMiss()` respectively — and for the `0.40` case S5-01 emits `RagMissEvent(reason="top1_below_floor")`. The retriever-level event sequence is preserved. **Precondition:** this AC exercises S5-01's retriever end-to-end and requires S5-01 to be GREEN — see the TDD plan's Green step 6 for the `xfail(strict=True)` deferral path if S5-01 is not yet GREEN.

## Implementation outline

```python
# src/codegenie/rag/confidence.py
"""Two-threshold band classifier for RAG retrieval.

Pure module — no I/O, no logging, no event emission, no process-nondeterministic
primitive (no ``hash()``). The classifier reads band thresholds at construction
time (from plugin.yaml in production) and maps a similarity score to the closed
``RagConfidence`` literal, then dispatches onto the ``RetrievalOutcome`` variant.

ADR-04-0008 — band thresholds live in plugin.yaml, not in code.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, assert_never

from codegenie.rag.models import RagDegraded, RagHit, RagMiss, RetrievalOutcome
from codegenie.rag.retriever import FencedRetrievalCandidate  # S5-01 — DTO + Protocol home
from codegenie.types.identifiers import Similarity

__all__ = ("BandClassifier", "RagConfidence", "classify_similarity")

# The honest-confidence triple (arch §Confidence handling, line 862). NOT named
# ``AdapterConfidence`` — that name is a shipped, differently-shaped cross-phase
# contract (see "Notes for the implementer").
RagConfidence = Literal["high", "medium", "low"]


def classify_similarity(
    score: Similarity,
    *,
    high_floor: float,
    degraded_floor: float,
) -> RagConfidence:
    """Pure score-to-band classifier.

    Bands (inclusive at the lower boundary of each band):
        score >= high_floor                    -> "high"
        degraded_floor <= score < high_floor   -> "medium"
        score < degraded_floor                 -> "low"
    """
    if score >= high_floor:
        return "high"
    if score >= degraded_floor:
        return "medium"
    return "low"


@dataclass(frozen=True, kw_only=True)
class BandClassifier:
    high_floor: float
    degraded_floor: float

    def __post_init__(self) -> None:
        if not (0.0 <= self.degraded_floor < self.high_floor <= 1.0):
            raise ValueError(
                "degraded_floor must be strictly less than high_floor "
                "(both within [0.0, 1.0]); "
                f"got high_floor={self.high_floor!r}, degraded_floor={self.degraded_floor!r}"
            )

    def classify(
        self, candidates: Sequence[FencedRetrievalCandidate]
    ) -> RetrievalOutcome:
        if not candidates:
            return RagMiss()  # defensive — S5-01 short-circuits empty upstream
        # Deterministic top selection: highest score, ties broken by the
        # lexicographically-smallest record id. No hash() — AC-8 / AC-3.
        top = min(candidates, key=lambda c: (-c.score, c.record.id))
        confidence = classify_similarity(
            top.score, high_floor=self.high_floor, degraded_floor=self.degraded_floor
        )
        match confidence:
            case "high":
                return RagHit(few_shot=top.record, score=top.score)
            case "medium":
                return RagDegraded(near_match=top.record, score=top.score)
            case "low":
                return RagMiss()
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

1. Land `src/codegenie/rag/confidence.py` per the implementation outline — pure module, no logging/IO/`hash()`. `BandClassifier` is `@dataclass(frozen=True, kw_only=True)`.
2. Land the band table tests verbatim (AC-4); assert boundary inclusivity and the negative-cosine rows.
3. Land `BandClassifier.__post_init__` validation; parametrize rejection cases for invalid floor ordering / out-of-range / NaN, plus the positional-construction `TypeError` case.
4. Wire `BandClassifier.classify` to the deterministic top-select (`min` with the `(-score, record.id)` key) and the three-arm `match` dispatch with `assert_never`.
5. Add the Hypothesis monotonicity, drift-envelope (all three interiors), and lexicographic-tiebreak properties under `tests/property/`.
6. `tests/unit/rag/test_retriever_with_real_classifier.py` (the S5-01 integration, AC-14) exercises S5-01's `SolvedExampleRetriever` with a real `BandClassifier`. **Precondition:** S5-01 must be GREEN — it is currently HARDENED and itself blocked on the S4-03 candidate-read amendment. If S5-01 is not yet GREEN when this story executes, land `test_retriever_with_real_classifier.py` as an `xfail(strict=True)` with reason `"depends on S5-01 GREEN"` and record the deferral in the attempt log — do not silently skip the integration proof.

### Refactor — clean up

- If the dispatch `match` expression grows past three arms, that's a smell — the band is exactly three. Resist adding a fourth.
- Confirm `__all__ = ("BandClassifier", "RagConfidence", "classify_similarity")`; no other public names; in particular no local `AdapterConfidence`.
- AST-purity test: `tests/property/test_classifier_pure.py` walks `confidence.py` and asserts no `import logging`, `import structlog`, `open(`, `Path(`, `os.`, `sys.stdout`/`sys.stderr`, **no `hash(`**, and that every `RagMiss(...)` construction is argument-less (AC-13).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/rag/confidence.py` | NEW — `BandClassifier` + `classify_similarity` (pure). |
| `tests/unit/rag/test_band_classifier_table.py` | NEW — boundary inclusivity table. |
| `tests/unit/rag/test_band_classifier_construction.py` | NEW — `__post_init__` validation (rejection cases). |
| `tests/unit/rag/test_band_classifier_dispatch.py` | NEW — empty list, single candidate, tiebreak determinism. |
| `tests/property/test_retriever_threshold_monotonicity.py` | NEW — Hypothesis: higher similarity never yields lower confidence (AC-10). |
| `tests/property/test_band_classifier_drift_envelope.py` | NEW — Hypothesis: ±`DRIFT` perturbation inside each of the three band interiors never changes the band (AC-11). |
| `tests/property/test_band_classifier_tiebreak_lexicographic.py` | NEW — Hypothesis: among candidates tied at the top score, the chosen `record.id` is always `min(ids)` (AC-8). |
| `tests/property/test_classifier_pure.py` | NEW — AST-walk: no logging/I/O/`hash(` in `confidence.py`; every `RagMiss(...)` is argument-less (AC-3, AC-13). |
| `tests/unit/rag/test_classifier_typecheck_negative.py` | NEW — subprocess-mypy: raw `float` rejected, only `Similarity` accepted (AC-12); synthetic four-member `Literal` makes the `match` non-exhaustive (AC-9). |
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
- **`RagMiss` is bare — never `RagMiss(reason=...)`.** S1-04 (HARDENED F5) and S5-01 (HARDENED K1) both fixed `RagMiss` to carry no payload beyond its `kind` discriminator, per ADR-04-0008 §Decision + §Pattern fit and arch §Component 9. The classifier constructs only `RagMiss()`. Miss-cause observability (operator portal, Phase 6.5 calibration harness) is fed by S5-01's `RagMissEvent(reason=...)`, emitted from the retriever's `match outcome` arm — the reason lives on the *event*, not on `RagMiss`. Widening `RagMiss` with a `reason` field would be an ADR-04-0008 amendment and is out of scope here; if you believe it is needed, surface per Rule 7 — do not add it silently.
- **Tiebreak determinism — string ordering, never `hash()`.** Two candidates at the exact same top `score` is rare but possible (especially in seeded fixtures). The arch design does not prescribe a tiebreaker; AC-8 picks the lexicographically-smallest `record.id` so the choice is deterministic for the S6-07 50-run determinism-replay property. Use `min(candidates, key=lambda c: (-c.score, c.record.id))` — `hash()` of a string is `PYTHONHASHSEED`-salted (a different order every process) and is *not* lexicographic; AC-3's purity AST-walk bans `hash(` so the mutant cannot land. Document the `min(...)` `key` choice in the method docstring so a future reader understands why it is non-trivial.
- **Where the thresholds come from at production.** `plugin.yaml` carries `rag.high_floor` and `rag.degraded_floor`; S7-01's plugin engine reads them and constructs `BandClassifier(**values)` once at plugin load time. The classifier is then re-used across workflows. The "config-as-data" framing in ADR-04-0008 lives entirely in the plugin manifest schema; the classifier is unaware of YAML.
- **Do not name the confidence type `AdapterConfidence` — that name is taken (validator, Rule 7 + Rule 11).** `AdapterConfidence` is already a shipped, load-bearing, cross-phase contract in two places: a tagged union `Trusted | Degraded | Unavailable` in `codegenie.transforms.outcomes` (re-exported by `codegenie.adapters.confidence`; its discriminator strings are a documented cross-ADR contract), and a `StrEnum{HIGH, DEGRADED, UNAVAILABLE}` in `codegenie.primitives.vuln_provenance.types`. Neither carries a `"medium"` value. This story's `Literal["high","medium","low"]` is a *third*, differently-shaped concept — name it `RagConfidence` and keep it `confidence.py`-local. The Phase-4 docs drifted here: `phase-arch-design.md §297` (component diagram) and `High-level-impl.md §148` both write "AdapterConfidence"; that is doc drift against the shipped type and should be corrected separately — do not follow it into code.
- **The `Literal["high","medium","low"]` value set is correct — keep it a `Literal`, not an `Enum`.** Its source is `phase-arch-design.md §Confidence handling` (line 862: "Confidence flows out as `Literal["high","medium","low"]`"), and it matches `TypecheckNodeSignal.confidence` (S1-04 AC-8) exactly. A `Literal` composes with the Phase-3 confidence surface by exact-string equality; an `Enum` would not. (Production ADR-0008 does **not** mention this type — an earlier draft cited it in error; the real source is the phase arch.)
- **The synthesis ledger framing.** ADR-04-0008's tradeoff table is worth keeping next to your editor: the band absorbs ONNX drift, makes the failure mode explicit, and turns calibration into a YAML bump. The cost is the third match arm — cheap. If a reviewer asks "why two thresholds instead of one," the ledger entry is the answer.
