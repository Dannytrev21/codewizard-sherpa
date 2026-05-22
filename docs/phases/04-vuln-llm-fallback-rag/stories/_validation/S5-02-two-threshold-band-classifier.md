# Validation report: S5-02 — Two-threshold band classifier (`rag/confidence.py`)

**Validated:** 2026-05-22 (scheduled story-validation pass)
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1

## Summary

S5-02 ships the pure band classifier that turns S5-01's verified, fenced candidate
set into the closed `RetrievalOutcome` discriminated union via two configurable
floors. The goal is sound and traces cleanly to ADR-04-0008, ADR-04-0007,
production ADR-0033, `phase-arch-design.md §G6 / §Component 9 / §Confidence
handling / §Edge case #10`, and `High-level-impl.md §Step 5`.

The draft was **not** executor-ready. It carried three block-level contradictions
against already-hardened sibling stories, plus a process-nondeterminism bug and a
property test that would fail on a *correct* implementation:

1. The whole story was built on `RagMiss(reason=...)`, but S1-04 (HARDENED, F5)
   and S5-01 (HARDENED, K1) both fixed `RagMiss` to **bare** per ADR-04-0008.
2. `BandClassifier.classify` used `list[tuple[FencedSegment, SolvedExample,
   Similarity]]`, but the hardened S5-01 Protocol (AC-16 + D1) is
   `classify(candidates: Sequence[FencedRetrievalCandidate]) -> RetrievalOutcome`.
3. The story named its confidence type `AdapterConfidence` and explicitly told
   the implementer to define it — but `AdapterConfidence` is already a shipped,
   load-bearing cross-phase contract (two different shapes, neither with a
   `medium` value).
4. The implementation outline's tiebreak used `hash()` of a string —
   `PYTHONHASHSEED`-salted, so non-deterministic per process — contradicting the
   story's own AC-8 and the S6-07 50-run determinism replay.
5. AC-11's drift-envelope property used `ε = drift = 0.005` as the band-interior
   margin, so at `s = high_floor - ε` the `+0.005` perturbation lands exactly on
   `high_floor` and re-classifies — the property fails on correct code.

All five are fixable in place — none requires rewriting the story's goal — so the
verdict is **HARDENED**. 15 findings: 3 block, 10 harden, 2 nit.

## Context brief

- **Story promise:** a pure `BandClassifier` + `classify_similarity` mapping a
  similarity score to a three-value confidence band, dispatched onto the closed
  `RagHit | RagDegraded | RagMiss` union; thresholds injected (from `plugin.yaml`
  in production), no I/O, no event emission.
- **Sibling constraints (load-bearing):** S1-04 ships `RagMiss` **bare**; S5-01
  ships the `ConfidenceClassifier` Protocol over `Sequence[FencedRetrievalCandidate]`
  and the `FencedRetrievalCandidate(fenced, record, score)` DTO. S5-02 *is* the
  concrete implementation of that Protocol and must match it byte-for-byte.
- **Codebase fact:** `AdapterConfidence` already exists twice —
  `codegenie.transforms.outcomes.AdapterConfidence` (tagged union
  `Trusted | Degraded | Unavailable`, re-exported by `codegenie.adapters.confidence`)
  and `codegenie.primitives.vuln_provenance.types.AdapterConfidence` (`StrEnum`).
- **`Similarity` / `SolvedExampleId`** both ship in `codegenie.types.identifiers`
  (confirmed by reading the module).
- **Open ambiguities after edit:** none for this story. AC-14's integration test
  depends on S5-01 being GREEN; S5-01 is HARDENED but blocked on the S4-03
  candidate-read amendment — the story now carries an explicit `xfail` deferral
  path for that case.

## Findings by critic

### Coverage critic

**C1 (harden) — AC-9's deliberate-failure test had no home.** AC-9 mandated a
mypy-exhaustiveness negative test but `Files to touch` named no file for it.
**Fix:** AC-9 and `Files to touch` now route it through
`tests/unit/rag/test_classifier_typecheck_negative.py`, shared with AC-12.

**C2 (harden) — Negative cosine similarity uncovered.** Cosine similarity is
legitimately negative; the `Similarity` newtype domain is `[-1.0, 1.0]`. The AC-4
band table started at `0.00`.
**Fix:** Added `-0.50 → "low"` and `-1.00 → "low"` rows to the AC-4 table.

### Test-Quality critic

**T1 (harden) — AC-11 drift-envelope property fails on a correct impl.** With
`ε = DRIFT = 0.005` as the interior margin, `s = high_floor - ε` perturbed by
`+0.005` equals `high_floor`, which classifies as `"high"`, not `"medium"` — the
"band absorbs ±drift" property is violated at the interval endpoint. The property
also covered only the medium-band interior.
**Fix:** AC-11 rewritten — interior margin `MARGIN = 0.01` strictly greater than
`DRIFT = 0.005`; property covers all three band interiors (high / medium / low);
boundaries explicitly excluded with a rationale.

**T2 (harden) — AC-8 tiebreak test was mutation-weak and would be flaky.** A
two-id (`"a"`/`"b"`) example test cannot reliably kill the `hash()`-based mutant
(see D1) — it passes or fails per process. It also did not exercise insertion
order.
**Fix:** AC-8 now requires a reversed-insertion-order case plus a Hypothesis
property (`test_band_classifier_tiebreak_lexicographic.py`) asserting the chosen
id is always `min(ids)` over generated tied-candidate sets.

**T3 (harden) — AC-2 pinned an exact error-message string the outline did not
produce.** The outline's `__post_init__` raised a richer message (with the
offending values) than AC-2's quoted literal.
**Fix:** AC-2 now asserts the message *contains* the phrase and *names the
values* — `pytest.raises(ValueError, match=...)` — keeping the richer, fail-loud
message (Rule 12).

**T4 (nit→harden) — Hypothesis float strategies unbounded for nan/inf.** AC-10 /
AC-11 generate floats; without `allow_nan=False, allow_infinity=False` the
strategies can emit nan/inf and produce noisy shrinks.
**Fix:** Both ACs now pin `allow_nan=False, allow_infinity=False`.

### Consistency critic

**K1 (block) — `RagMiss(reason=...)` contradicts S1-04 + S5-01 + ADR-04-0008.**
The entire story (Context, AC-7, AC-13, implementation outline, TDD plan) was
built on a `RagMiss` carrying an enumerated `reason`. S1-04 (HARDENED F5) ships
`RagMiss` **bare**; S5-01 (HARDENED K1) reaffirmed it; ADR-04-0008 §Decision +
§Pattern fit specify it; arch §Component 9 line 600 confirms.
**Fix:** Every site now constructs bare `RagMiss()`. AC-13 fully rewritten — there
is no `RagMiss.reason`. Miss-cause observability is S5-01's `RagMissEvent`.

**K2 (block) — Classifier signature contradicts the hardened S5-01 Protocol.**
The story used `classify(candidates: list[tuple[FencedSegment, SolvedExample,
Similarity]])`. S5-01 (HARDENED AC-16 + D1) ships
`classify(candidates: Sequence[FencedRetrievalCandidate]) -> RetrievalOutcome`
and replaced the anonymous tuple with the frozen `FencedRetrievalCandidate` DTO.
A `list[tuple[...]]` parameter is also narrower than the Protocol's `Sequence`,
so mypy --strict would reject `BandClassifier` as a Protocol implementation.
**Fix:** AC-7, AC-8, AC-14 and the outline consume
`Sequence[FencedRetrievalCandidate]` and read `.record` / `.score`.

**K3 (block) — `AdapterConfidence` name collision with a shipped contract.** The
story defined a local `AdapterConfidence = Literal["high","medium","low"]` and a
Note explicitly told the implementer to "resist the temptation to use an enum."
But `AdapterConfidence` is already a shipped, load-bearing, cross-phase contract:
a tagged union `Trusted | Degraded | Unavailable` in `codegenie.transforms.outcomes`
(re-exported by `codegenie.adapters.confidence`; discriminator strings are a
documented cross-ADR contract) and a `StrEnum{HIGH,DEGRADED,UNAVAILABLE}` in
`codegenie.primitives.vuln_provenance.types`. Neither carries `"medium"`. A third,
differently-shaped type under the same name is a real consistency violation
(Rule 11, Rule 7, ADR-0043 "extension by addition is not cloning").
**Fix:** Renamed to `RagConfidence` (grep-confirmed collision-free), kept
`confidence.py`-local, added to `__all__`. The `Literal["high","medium","low"]`
*value set* is correct and arch-sanctioned (`phase-arch-design.md §Confidence
handling`, line 862) — only the name was wrong. The Note that claimed production
ADR-0008 commits to the literal was corrected: production ADR-0008 does not
mention it (grep-verified).

**K4 (nit) — ADR-04-0008 §Pattern fit names `RetrievalOutcome.classify(...)`.**
The ADR sketches band classification as Pydantic validators on a
`RetrievalOutcome.classify` method. S1-04 shipped `RetrievalOutcome` as a plain
`Annotated[... , Field(discriminator="kind")]` union (no method possible), and
S5-01 + S5-02 put the classifier in a separate `BandClassifier` behind the
`ConfidenceClassifier` Protocol. The story's approach is the more recent and more
tested (Rule 7); recorded as drift, no story edit.

**K5 (nit) — Test filename drift.** ADR-04-0008 §Consequences names
`tests/unit/rag/test_retriever_thresholds.py`; the story uses the more specific
`test_band_classifier_table.py`. The story's name is fine; recorded, no edit.

### Design-Patterns critic

**D1 (harden) — Non-deterministic tiebreak via `hash()`.** The implementation
outline's `max(candidates, key=lambda c: (c[2], -hash(c[1].id)))` used `hash()`
of a `str`. Python salts string hashing per process via `PYTHONHASHSEED`, so the
tiebreak order changes every run — and `-hash(id)` is not lexicographic anyway.
This silently contradicts AC-8 ("lexicographic order on id") and the S6-07 50-run
determinism replay (cited in the story's own Notes).
**Fix:** Outline now uses `min(candidates, key=lambda c: (-c.score, c.record.id))`
— true lexicographic string ordering. AC-3's purity AST-walk additionally bans
`hash(` so the mutant cannot land structurally.

**D2 (harden) — `_CONFIDENCE_RANK` is dead module state.** The outline defined a
module-level `_CONFIDENCE_RANK` dict that nothing in the module used — it existed
only for the AC-10 monotonicity test's rank helper (Rule 2 — no unused
abstraction).
**Fix:** Removed from the outline; AC-10 now states the rank map is a test-local
helper.

**D3 (harden) — `BandClassifier` outline contradicted AC-2's keyword-only
constructor.** AC-2 mandated `__init__(*, high_floor, degraded_floor)` but the
outline used a bare `@dataclass(frozen=True)`, which generates a *positional*
constructor.
**Fix:** Outline + AC-2 now specify `@dataclass(frozen=True, kw_only=True)`; AC-2
adds a `pytest.raises(TypeError)` test for a positional-construction attempt.

**D4 (harden) — Implementation-outline imports incomplete.** The outline used
`assert_never`, `FencedSegment`, `SolvedExample` without importing them, and (with
the K2 fix) needed `FencedRetrievalCandidate` + `Sequence`.
**Fix:** Outline rewritten with a complete, correct import block
(`assert_never` from `typing`, `FencedRetrievalCandidate` from
`codegenie.rag.retriever`, `Sequence` from `collections.abc`).

## Research briefs

None. No finding required external research — every fix came from in-repo ADRs,
hardened sibling stories (S1-04, S5-01), and current source
(`identifiers.py`, `adapters/confidence.py`, `vuln_provenance/types.py`,
`phase-arch-design.md`).

## Conflict resolutions

- **Story Notes vs codebase on `AdapterConfidence`:** the codebase wins
  (Rule 11). The story's Note asserting a `Literal` `AdapterConfidence` and citing
  production ADR-0008 was factually wrong — corrected; type renamed `RagConfidence`.
- **Story `AC-13` (`RagMiss.reason`) vs S1-04/ADR-04-0008:** S1-04 + the ADR win
  (Consistency > Coverage). AC-13 rewritten around a bare `RagMiss`.
- **Story outline `hash()` tiebreak vs story AC-8 + S6-07 determinism:** the
  determinism commitment wins; outline corrected, AST guard added.
- **ADR-04-0008's `RetrievalOutcome.classify` framing vs S5-01's Protocol:** the
  more recent, tested S5-01 approach wins (Rule 7); recorded as ADR drift (K4),
  no story rewrite.

## Edits applied

1. Header `Status: Ready → HARDENED`; `Depends on` + `ADRs honored` lines
   corrected (bare `RagMiss`; S5-01 Protocol shape; literal source is the arch,
   not production ADR-0008).
2. `Validation notes` block inserted under the header.
3. Context paragraph 4 rewritten — bare `RagMiss()`, reason carried by S5-01's
   `RagMissEvent`.
4. Goal rewritten — `RagConfidence`, hardened-Protocol signature, bare `RagMiss`.
5. AC-1 — three public names incl. `RagConfidence`; explicit "no local
   `AdapterConfidence`".
6. AC-2 — `kw_only=True`; substring + offending-values message; positional
   `TypeError` test; `nan` high_floor case.
7. AC-3 — return type `RagConfidence`; AST-walk also bans `hash(` and asserts
   argument-less `RagMiss(...)`.
8. AC-4 — two negative-cosine rows added.
9. AC-7 — `Sequence[FencedRetrievalCandidate]` signature; bare `RagMiss()`;
   `.record` / `.score` access.
10. AC-8 — reversed-order case + Hypothesis lexicographic-tiebreak property;
    `hash()` explicitly forbidden.
11. AC-9 — `match`/`assert_never` over `RagConfidence`; negative test homed in
    `test_classifier_typecheck_negative.py`.
12. AC-10 — test-local `_rank` helper; Hypothesis `allow_nan/allow_infinity=False`.
13. AC-11 — `MARGIN=0.01 > DRIFT=0.005`; all three band interiors; boundaries
    excluded with rationale.
14. AC-13 — fully rewritten: `RagMiss` is bare; AST-walk asserts argument-less
    construction.
15. AC-14 — `FencedRetrievalCandidate` inputs; bare `RagMiss()`; S5-01-GREEN
    precondition + `xfail` deferral pointer.
16. Implementation outline — full rewrite: complete imports, `RagConfidence`,
    `kw_only=True`, `Sequence[FencedRetrievalCandidate]`, `min(...)` tiebreak,
    bare `RagMiss()`, `_CONFIDENCE_RANK` removed.
17. TDD plan Green/Refactor steps updated; `__all__` three names; AST guards.
18. `Files to touch` — added `test_band_classifier_tiebreak_lexicographic.py`;
    AC-9/AC-12 share `test_classifier_typecheck_negative.py`; purity test scope
    extended.
19. References — `models.py` line corrected to bare `RagMiss`; `identifiers.py`
    line confirms `Similarity` + `SolvedExampleId`; added the two existing
    `AdapterConfidence` declarations as read-this-first; arch line-862 quote fixed.
20. Notes — replaced the wrong `RagMiss.reason` and `AdapterConfidence`-Literal
    notes; added the name-collision, determinism, and bare-`RagMiss` notes.

## Verdict rationale

**HARDENED.** The story's goal — a pure two-threshold band classifier behind the
`ConfidenceClassifier` Protocol — is correct and well-traced. Every defect was a
contract drift against an *already-hardened* sibling (S1-04, S5-01) or a
self-contradiction (the `hash()` tiebreak vs the story's own determinism claim;
the AC-11 property vs a correct implementation). All were fixable in place with no
change to the goal or scope, so this is not a RESCUE. The three block findings
were genuine executor-blockers — left unfixed, `BandClassifier` would not satisfy
the S5-01 Protocol, would construct an illegal `RagMiss`, and would collide with a
shipped type — but each had a clear in-place fix.

## Recommended next step

`phase-story-executor` to implement S5-02. Two sequencing notes for the executor:

- AC-14 (`test_retriever_with_real_classifier.py`) requires S5-01 to be GREEN.
  S5-01 is HARDENED but blocked on the S4-03 candidate-read amendment. If S5-01 is
  not GREEN at execution time, land AC-14's test as `xfail(strict=True)` and
  record the deferral in the attempt log.
- The Phase-4 doc drift surfaced by K3 (`phase-arch-design.md §297` and
  `High-level-impl.md §148` both write "AdapterConfidence") should be corrected in
  a separate docs pass — it is out of scope for this story but will mislead the
  next reader if left.
