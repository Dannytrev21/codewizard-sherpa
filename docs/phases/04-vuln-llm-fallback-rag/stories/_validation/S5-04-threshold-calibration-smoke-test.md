# Validation report: S5-04 — Threshold-calibration smoke test (`test_phase4_threshold_smoke.py`)

**Validated:** 2026-05-22
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1

## Summary

S5-04 ships `tests/integration/test_phase4_threshold_smoke.py` — the Phase-4-merge-gating
calibration smoke test that pins the two-threshold band defaults (`high_floor=0.85`,
`degraded_floor=0.65`) against the four `vuln-major-bump/*` fixtures. The goal is sound
and traces cleanly to Gap 6 of the phase architecture, ADR-04-0008, ADR-04-0007, the
roadmap exit criterion #2 ("second run hits RAG"), and `High-level-impl.md §Step 5`.

The draft was **not** executor-ready. It carried five block-level defects, plus an
internal contradiction between two of its own acceptance criteria:

1. **AC-4 ⟂ AC-10 — the test as specified could not run.** AC-10 seeded all four
   fixtures into one module-scoped shared store; AC-4 said "seed only `fixture_a`,
   query with `fixture_b`". A store containing every fixture cannot produce a
   crossing-CVE `RagMiss` — `fixture_b`'s own record is present and scores a `RagHit`.
2. **`RagMiss` is bare.** AC-4 asserted `outcome.reason == "top1_below_floor"`. S1-04,
   S5-01, S5-02, and S5-03 all fixed `RagMiss` to **bare** per ADR-04-0008; it has no
   `reason` field. AC-4 even self-contradicted ("since `RagMiss` is bare").
3. **`StoreQueried` event does not exist.** AC-4/AC-9 read the candidate score "via an
   event-log spy on `StoreQueried`" — no such event is in the Phase-4 event taxonomy.
4. **No macOS CI exists.** The whole "CI-matrix drift envelope validation" section
   (AC-8, AC-9), a Context paragraph, and three Notes assumed a Linux+macOS CI matrix
   and a cross-arch "split-vote" test. ADR-04-0007 §Consequences pins Phase-4 CI to
   x86_64 `ubuntu-24.04` only; the empirical cross-arch validation is a Phase-6.5
   follow-up.
5. **`RecordProvenance.verify(...)` does not exist.** AC-11 called it; S4-05 ships a
   module-level `codegenie.rag.provenance.verify(record, spanning_log)` and
   `RecordProvenance` is frozen data with no methods.

Plus AC-6 used `model_dump_json(..., sort_keys=True)` — `sort_keys` is not a Pydantic v2
kwarg — and AC-6's "byte-compare a raw outcome dump" contradicted AC-7's hand-shaped
4-field golden schema.

All defects are fixable in place — none requires rewriting the story's goal — so the
verdict is **HARDENED**. 22 findings: 5 block, 13 harden, 4 nit.

## Context brief

- **Story promise:** an integration smoke test that seeds four fixtures into a real
  `ChromaPersistentStore` via a real `FastembedEmbedder` and asserts same-CVE re-run →
  `RagHit`, crossing-CVE → `RagMiss`/low-similarity, a stable golden, and clean cluster
  separation — failing Phase-4 merge loud if the defaults are wrong.
- **Codebase fact:** `src/codegenie/rag/` does not exist yet. Every dependency
  (S4-01..S4-08, S5-01, S5-02, S5-03) is **HARDENED, not GREEN**. The story is 100%
  integration — there is nothing partial to ship before that stack lands.
- **Sibling-pinned contracts (load-bearing):** `RagMiss` is bare (S1-04/S5-01/S5-02/
  S5-03); RAG events live in `src/codegenie/plugins/events.py`, not `rag/events.py`;
  `verify` is the module-level `codegenie.rag.provenance.verify`; S5-01 ships
  `query_candidates(..., embedding=...) -> Sequence[ScoredSolvedExample]` as the raw
  candidate-read surface; `RagHit.few_shot` carries a `SolvedExample`.
- **Project facts:** Phase-4 CI is `ubuntu-24.04` only (ADR-04-0007 §Consequences,
  CLAUDE.md); the golden convention is `scripts/regen_golden.py --update`/`--check`,
  not `pytest --update-goldens`; `asyncio_mode = "auto"`.
- **Open ambiguities after edit:** none. The one remaining cross-story item — the full
  dependency closure being GREEN — is now an explicit precondition AC (AC-17), not an
  ambiguity.

## Findings by critic

### Coverage critic

**C1 (block) — AC-4 ⟂ AC-10: the test could not run.** AC-10 seeds all four fixtures
into one module-scoped shared store and says "all 16 parametrized cases reuse the same
store"; AC-4 says "seed only `fixture_a`, query with `fixture_b.advisory`". A store
containing every fixture always hits the queried fixture itself → `RagHit`, never the
`RagMiss` AC-4 asserts. A crossing-CVE *outcome* `RagMiss` requires the matching record
*absent*.
**Fix:** AC-4 rewritten to use a **leave-one-out** store (the three non-matching
fixtures), parametrized over four held-out fixtures. AC-10 rewritten to split the
fixtures: a module-scoped `embedder` (the expensive resource) shared across
scenario-specific stores (the all-four store for hit/matrix/golden; per-case
leave-one-out stores for the crossing `RagMiss`).

**C3 (harden) — No precondition handling for the all-HARDENED-not-GREEN closure.**
S5-04 is 100% retriever-integration; every AC needs S4-01..S4-06 + S5-01/S5-02/S5-03
GREEN. Unlike S5-03 (which had standalone filter ACs and used `xfail`), S5-04 has
nothing partial to run, and AC-14 forbids `xfail`. The draft had no handling for the
executor reaching S5-04 before the stack is GREEN.
**Fix:** AC-17 added — an explicit precondition gate: verify the closure is GREEN; if
not, set the story `BLOCKED` with an `_attempts/` paper trail (consistent with AC-14,
which sanctions exactly that path).

**C4 (harden) — The `RagDegraded` middle band was wholly uncovered.** The smoke test
pins *both* defaults but the draft only tested above `high_floor` (`RagHit`) and below
`degraded_floor` (`RagMiss`). A crossing pair drifting *into* `[degraded_floor,
high_floor)` would be a calibration warning the test should surface, not silently pass.
**Fix:** AC-9 rewritten — it now records the full 4×4 matrix to pytest output and, if
any off-diagonal cell lands in the `RagDegraded` band, names the pair explicitly
("fixtures insufficiently discriminative"). AC-5's failure message also names the band
each off-diagonal score landed in.

**C2 (harden) — AC-5's "12 off-diagonal `RagMiss` outcomes" was the wrong granularity.**
A `RagMiss` *outcome* needs a store missing the record (4 leave-one-out cases — now
AC-4). The 12 off-diagonal assertions are *pairwise similarity* facts, read from the
candidate matrix.
**Fix:** AC-5 keeps the 12-pair parametrization + `id=f"{a}-vs-{b}"` naming but as
*similarity* assertions over the matrix, not outcome assertions.

### Test-Quality critic

**T1 (harden) — AC-6 used a non-existent Pydantic v2 kwarg.** `outcome.model_dump_json(
indent=2, sort_keys=True)` — Pydantic v2's `BaseModel.model_dump_json()` has no
`sort_keys` parameter; the executor hits a `TypeError`.
**Fix:** AC-6 builds an explicit projection dict and serializes it with
`json.dumps(projection, sort_keys=True, indent=2)`.

**T2 (block) — AC-6 ⟂ AC-7.** AC-6 said "dump the `RetrievalOutcome` via
`model_dump_json` and compare byte-for-byte to the golden"; AC-7 said the golden's
schema is `{store_digest, top1_id, top1_kind, score_band}` — which is *not* the shape
`RagHit.model_dump_json()` produces (`kind`, `few_shot`, `score`). You cannot
byte-compare a raw dump against a hand-shaped 4-field projection.
**Fix:** AC-6 rewritten around an explicit projection; the golden is that projection,
not a raw outcome dump.

**T3 (harden) — Golden generation named a non-existent command.** TDD Green step 4 said
"generated via `pytest --update-goldens` (project convention)". The project convention
is `scripts/regen_golden.py --update`/`--check` (`tests/golden/test_goldens_match.py`);
there is no `--update-goldens` pytest option.
**Fix:** the golden is a tiny hand-authored 4-key file committed directly — not wired
into the probe-portfolio regen harness. TDD Green step 6 + AC-7 updated.

**T4 (harden) — AC-8/AC-9 duplicated AC-1/AC-5 with no added mutation-kill.** The old
`test_score_margin_above_drift_envelope` (AC-8) re-asserted AC-1's
`score >= HIGH_FLOOR + DRIFT_MARGIN`; the old `test_crossing_cve_margin_below_degraded_
floor` (AC-9) re-asserted AC-5. Two tests with the identical predicate are not added
coverage.
**Fix:** AC-8 repurposed as the `similarity_matrix` construction + the four diagonal
(self-similarity) cell assertions — genuinely distinct candidate-level evidence. AC-9
repurposed as the cluster-*separation* assertion (`min(diagonal) - max(off-diagonal) >=
SEPARATION_GAP`) + the `RagDegraded`-band diagnostic — the real meaning of "calibrated
for this portfolio".

**T5 (harden) — The TDD Red scaffold carried the bare-`RagMiss` bug.** The draft's Red
test asserted `outcome.reason == "empty_store"`.
**Fix:** Red scaffold rewritten to assert `isinstance(outcome, RagMiss)` only, with a
comment that the reason rides S5-01's `RagMissEvent`; the scaffold is explicitly marked
"not a committed deliverable — deleted in Green step 8".

**T6 (nit) — Helper functions were referenced but unhomed.** `fixture_id`,
`load_advisory_and_ctx`, `load_solved_example`, `render_query_text` were used across
ACs but the Refactor step said extract a loader "if it grows past ~5 LOC".
**Fix:** `tests/fixtures/phase4_smoke/loader.py` is now a from-the-start deliverable in
Files-to-touch and the Refactor step.

### Consistency critic

**K1 (block) — `RagMiss(reason=...)` / `outcome.reason`.** AC-4 asserted
`outcome.reason == "top1_below_floor"`. S1-04, S5-01 (K1), S5-02 (K1), S5-03 (K2),
ADR-04-0008 §Decision/§Pattern fit, and arch edge case #10 all establish `RagMiss` as
**bare**.
**Fix:** AC-4 asserts `isinstance(outcome, RagMiss)` only; no attribute access. The
Context, Goal, Notes, and TDD Red scaffold all reconciled to bare `RagMiss`.

**K2 (block) — `StoreQueried` event does not exist.** AC-4 and AC-9 read candidate
scores "via an event-log spy on `StoreQueried`". The Phase-4 RAG event taxonomy is
`RagHit/Miss/Degraded`, `RagMissEvent`, `RagRecordChainOrphan`, `RagRecordModelMismatch`,
`RagCandidateSelectedEvent`, `QueryRenderedEvent` — no `StoreQueried`. Inventing one
would force a production code change outside this story's scope.
**Fix:** AC-5/AC-8 read candidate scores directly via S5-01's hardened
`store.query_candidates(embedding=...) -> Sequence[ScoredSolvedExample]` surface — a
real contract — assembled once into a 4×4 matrix.

**K3 (block) — No macOS CI exists.** The "CI-matrix drift envelope validation" section
(AC-8, AC-9), the Context paragraph ("runs ... on macOS in the nightly job"), and three
Notes all assumed a Linux+macOS CI matrix and a "split-vote" empirical cross-arch test.
ADR-04-0007 §Consequences: "Phase-4 CI runs x86_64 (ubuntu-24.04) only. arm64
cross-host determinism test is a known Phase-6.5 follow-up." CLAUDE.md confirms CI is
`Python 3.11/3.12 × ubuntu-24.04`.
**Fix:** AC-8/AC-9 rewritten with no macOS framing. `DRIFT_MARGIN` is reframed honestly
as a single-arch *headroom* margin (so a future Phase-6.5 cross-arch run cannot flip a
band); the *empirical* cross-arch validation is cross-referenced to Phase 6.5 in the
Context, the ADRs-honored line, Out-of-scope, and Notes.

**K4 (block) — `RecordProvenance.verify(...)` does not exist.** AC-11 called it; S4-05
(HARDENED) + S5-03 (K4) ship a module-level `codegenie.rag.provenance.verify(record,
spanning_log)`; `RecordProvenance` is frozen data with no behavior.
**Fix:** AC-11 + the Implementation outline import and call the module-level `verify`.

**K5 (harden) — The Implementation outline pinned a stale retriever constructor.** The
draft did `record_provenance=RecordProvenance()` and passed `query_builder=`; S5-01
(HARDENED) injects `spanning_log`, `record_verifier`, `query_text_builder`, etc.
**Fix:** the outline's `_make_retriever` helper carries an explicit warning to
reconcile against whatever S5-01 ships GREEN rather than copy a stale signature; a
Notes paragraph repeats it.

**K6 (harden) — Wrong golden convention.** See T3 — `pytest --update-goldens` is not a
project mechanism.
**Fix:** golden committed directly; convention pointer corrected in References + AC-7.

**K7 (nit) — `@pytest.mark.asyncio` is redundant** under `asyncio_mode = "auto"`. The
draft kept it "for clarity".
**Fix:** the outline omits the marker and the Refactor step says match the project
convention (Rule 11).

**K8 (nit) — `embeddings_model.lock` path.** The draft referenced a bare
`embeddings_model.lock`; ADR-04-0007 places it at `.codegenie/rag/embeddings_model.lock`.
**Fix:** References + AC-10 use the full path.

### Design-Patterns critic

**D1 (harden) — The monolithic `seeded_smoke_store` fixture coupled the expensive
resource to the cheap one.** AC-10 made one fixture that was both the `FastembedEmbedder`
(~180 MB RSS, ~500 ms cold) *and* the all-four-seeded store. The crossing-CVE `RagMiss`
test needs *different* store contents; the embedder is the only thing that must be
shared.
**Fix:** AC-10 split — module-scoped `embedder` fixture (shared, the load-bearing perf
optimization) + scenario-specific store fixtures built cheaply over it. This both
resolves C1 and is the correct dependency direction (the test composes scenario stores
over a shared embedder).

**D2 (harden) — The 4×4 similarity matrix is the real abstraction, computed once.** The
draft re-queried per parametrized case. The matrix (4 advisory embeddings ×
`query_candidates`) is pure data derivable in one module-scoped fixture; every band
assertion is then a thin read.
**Fix:** AC-8 defines a `similarity_matrix` module fixture (4 `query_candidates` calls
total); AC-5/AC-8/AC-9 are thin assertions over it — functional-core / imperative-shell.

**D3 (nit) — `DRIFT_MARGIN` vs S5-02's `MARGIN`.** Both exist, both exceed the ~0.005
drift envelope, but they serve different roles (smoke-test headroom `0.02` vs
classifier-interior property margin `0.01`).
**Fix:** AC-2's mandated comment now states *why* `0.02 ≠ 0.01` so a future reader does
not "unify" them.

**D4 (nit) — No premature abstraction.** The story correctly resists building a
calibration framework (Phase 6.5's job); the `loader.py` helper is the right small
extraction. Kept verbatim — correct application of Rule 2.

## Research briefs

None. No finding required external research — the test patterns (parametrized matrix,
projection golden, integration smoke test) are standard pytest, and every contract fix
came from in-repo ADRs, the three HARDENED sibling validation reports (S5-01, S5-02,
S5-03), `phase-arch-design.md`, and the current golden-test convention.

## Conflict resolutions

- **AC-4 (story) vs AC-10 (story):** an internal contradiction, not a critic conflict —
  resolved by the D1/D2 restructure (split fixtures + leave-one-out stores). Both ACs
  rewritten so they coexist.
- **Story "CI-matrix / macOS" framing vs ADR-04-0007 §Consequences:** Consistency wins
  (source of truth). The macOS framing is removed; the margin is kept but reframed as
  single-arch headroom.
- **Story `RagMiss.reason` vs S1-04/S5-01/S5-02/S5-03/ADR-04-0008:** the ADR + the four
  HARDENED siblings win — bare `RagMiss`.
- **Coverage C4 (test the `RagDegraded` band) vs scope:** the goal pins *both* floors,
  so middle-band visibility traces to the goal — added as a *diagnostic* in AC-9
  (records + flags), not as a new floor assertion, staying within scope.

## Edits applied

### Edit 1 — Header
- `Status: Ready → HARDENED`; `Depends on` line expanded (S5-03 added; the
  `query_candidates` surface and module-level `verify` named; "all HARDENED, not GREEN"
  flagged); `ADRs honored` line corrected (ADR-04-0007 reframed as single-arch +
  Phase-6.5 cross-arch follow-up).

### Edit 2 — `Validation notes` block
- Inserted under the header per the editor convention.

### Edit 3 — Context
- Rewrote the "ONNX float-drift envelope" paragraph: dropped the macOS / CI-matrix
  split-vote framing; reframed as a single-arch headroom margin with the empirical
  cross-arch validation cross-referenced to Phase 6.5. Reconciled the crossing-CVE
  description to "leave-one-out store".

### Edit 4 — References
- Replaced "Existing code" pointers that named stale APIs with sibling-validation-report
  pointers (S5-01/S5-02/S5-03) that pin the real contracts; added the golden-convention
  and `asyncio_mode` pointers; corrected the `embeddings_model.lock` path.

### Edit 5 — Goal
- Rewrote to five lettered clauses: outcome `RagHit` with margin; off-diagonal
  *similarity* from the matrix; crossing-CVE *outcome* `RagMiss` via leave-one-out;
  golden projection; cluster separation.

### Edit 6 — AC-17 added (Coverage C3)
- New "Execution precondition" section: the dependency closure must be GREEN or the
  story goes `BLOCKED` (no `xfail`).

### Edit 7 — AC-1 edited
- Wording reconciled to the module-scoped all-four store; `few_shot.id` confirmed
  against S5-01.

### Edit 8 — AC-2 edited
- Comment requirement rewritten: drift ~0.005, 4× headroom, single-arch CI, and the
  deliberate `0.02 > 0.01` rationale vs S5-02's `MARGIN`.

### Edit 9 — AC-4 rewritten (blocks K1, K2; C1)
- Leave-one-out store; `isinstance(outcome, RagMiss)` only; explicit "`RagMiss` is bare
  — do not access `outcome.reason`"; `StoreQueried` removed.

### Edit 10 — AC-5 rewritten (block K2; C2, D2)
- 12 off-diagonal *similarity* assertions over the `query_candidates`-built matrix;
  `id=f"{a}-vs-{b}"` kept; failure message names pair + score + band.

### Edit 11 — AC-6 rewritten (T1, T2)
- Explicit projection dict + `json.dumps(..., sort_keys=True, indent=2)`; `model_dump_
  json` explicitly ruled out.

### Edit 12 — AC-7 edited (T3, K6)
- `top1_kind → outcome_kind`; structural key-set guard; "AST check on JSON" removed;
  `store_digest` pinned to the content-addressed canonical digest (ADR-04-0016) with a
  flake-avoidance fallback; golden committed directly, not via the regen harness.

### Edit 13 — AC-8 rewritten (block K3; T4, D2)
- `similarity_matrix` module fixture + four diagonal-cell margin assertions; macOS
  split-vote framing removed.

### Edit 14 — AC-9 rewritten (block K3; C4, T4)
- Cluster-separation assertion (`SEPARATION_GAP`) + full-matrix diagnostic output +
  `RagDegraded`-band detection; macOS framing removed; duplicate-of-AC-5 removed.

### Edit 15 — AC-10 rewritten (C1, D1)
- Split into a module-scoped `embedder` fixture, a module-scoped all-four
  `seeded_smoke_store`, and per-case leave-one-out stores over the shared embedder.

### Edit 16 — AC-11 rewritten (block K4)
- Module-level `verify(record, spanning_log)`; `RecordProvenance.verify` removed.

### Edit 17 — AC-12 / AC-13 / AC-14 / AC-15 / AC-16
- AC-12/AC-13/AC-15/AC-16 light edits (path precision, message-template scope). AC-14
  reworded to cross-reference AC-17 as the only sanctioned non-run path.

### Edit 18 — Implementation outline
- Full rewrite: complete imports incl. module-level `verify`; `DRIFT_MARGIN` /
  `SEPARATION_GAP` constants with corrected comments; split `embedder` /
  `seeded_smoke_store` / `similarity_matrix` fixtures; `_build_store` (with the AC-11
  provenance assertion) and `_make_retriever` (with the "reconcile against S5-01 GREEN"
  warning) helpers; leave-one-out crossing test; no macOS, no `outcome.reason`.

### Edit 19 — TDD plan
- Red scaffold rewritten to bare `RagMiss` and marked not-a-deliverable; Green steps
  reordered around the matrix + leave-one-out stores; golden generated by hand-commit,
  not `pytest --update-goldens`; Refactor step extracts `loader.py` from the start and
  bans inline numeric literals.

### Edit 20 — Files to touch
- `loader.py` named with its four helpers; golden path `tests/golden/rag/threshold_
  smoke_express.json` with the 4-key projection schema.

### Edit 21 — Out of scope
- Added: empirical cross-arch drift validation (Phase 6.5); `RagMissEvent` /
  miss-cause observability (S5-01). Clarified the `model_digest_filter` is a
  pass-through here.

### Edit 22 — Notes for the implementer
- Replaced the macOS / `RagMiss.reason` / monolithic-fixture notes with: bare `RagMiss`;
  no macOS CI; the matrix-as-abstraction; embedder/store split; module-level `verify`;
  band-not-score golden; the `xfail` prohibition; AC-17 sequencing; "retriever
  construction not pinned here".

## Verdict rationale

**HARDENED.** The story's goal — a Phase-4-merge-gating calibration smoke test that
pins the band defaults against the shipped fixture portfolio and fails loud (never
relaxes) — is correct, valuable, and traces cleanly to Gap 6, ADR-04-0008, and the
roadmap exit criterion. Every defect was either a stale-contract contradiction against
an already-HARDENED sibling (bare `RagMiss`, the `query_candidates` surface, the
module-level `verify`), a factual error about the environment (no macOS CI, no
`pytest --update-goldens`, `model_dump_json` has no `sort_keys`), or a self-contradiction
the draft never reconciled (AC-4 ⟂ AC-10). All were fixable in place with no change to
the goal or scope, so this is not a RESCUE. The five block findings were genuine
executor-blockers — left unfixed, the test would not run at all (AC-4⟂AC-10), would
raise `AttributeError` on `outcome.reason`, would import a non-existent event, would
assume a non-existent CI runner, and would call a non-existent method — but each had a
clear in-place fix.

## Recommended next step

`phase-story-executor` to implement S5-04 — **but only after AC-17's precondition is
met**: S4-01..S4-06, S5-01, S5-02, S5-03 must all be GREEN (the `src/codegenie/rag/`
package must exist) and fixtures available (S7-05 GREEN or the AC-12 local fallback).
If the executor reaches S5-04 before that closure is GREEN, the correct action is to
set the story `BLOCKED` with an `_attempts/` entry — not to write a half-wired test and
not to `xfail` it. When the executor does run, it must reconcile `_make_retriever`'s
keyword set against the real `SolvedExampleRetriever.__init__` that S5-01 shipped GREEN,
rather than the illustrative signature in this story's outline.
