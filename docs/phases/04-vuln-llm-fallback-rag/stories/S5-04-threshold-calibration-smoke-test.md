# Story S5-04 — Threshold-calibration smoke test (`test_phase4_threshold_smoke.py`)

**Step:** Step 5 — Ship SolvedExampleRetriever + two-threshold band + calibration smoke test
**Status:** HARDENED
**Effort:** M
**Depends on:** S5-02 (`BandClassifier` shipped with defaults `high_floor=0.85`, `degraded_floor=0.65`), S5-01 (`SolvedExampleRetriever` composes; ships the `query_candidates(..., embedding=...) -> Sequence[ScoredSolvedExample]` raw-candidate store surface), S5-03 (`EmbeddingModelMismatchFilter` — the retriever's `model_digest_filter`), S4-01 (`FastembedEmbedder` + `codegenie embeddings bootstrap` so the smoke test can produce real embeddings), S4-03 (`ChromaPersistentStore` so the smoke test can seed records into a real store), S4-04 (canonical YAML + manifest so records have valid provenance for chain-verify), S4-05 (module-level `codegenie.rag.provenance.verify(record, spanning_log)`), S4-06 (capability-minted ingest path so records land legitimately), S7-05 (fixtures — this story takes the four `vuln-major-bump/*` fixture solved examples; if S7-05 has not landed yet, this story ships a minimal Phase-5-local fixture set under `tests/fixtures/phase4_smoke/` per AC-12 and S7-05 wires the production fixtures later). **All of the above are currently HARDENED, not GREEN — see AC-17 (execution precondition).**
**ADRs honored:** ADR-04-0008 (two-threshold band — this test pins the *defaults* against the shipped fixture portfolio; a fail means the defaults are wrong and an ADR amendment updates them *before* merge per Global Rule 12), ADR-04-0007 (`fastembed` BGE-small is the pinned model; cross-architecture ONNX drift envelope ~0.005 — the smoke test asserts a *headroom margin* so a future cross-arch run cannot flip a band; the *empirical* cross-arch validation is explicitly a Phase-6.5 follow-up, ADR-04-0007 §Consequences, because Phase-4 CI runs x86_64 `ubuntu-24.04` only), Gap 6 from arch design (calibration smoke test is the load-bearing assurance Phase 4 doesn't merge with wrong defaults), production ADR-0008 (honest confidence — defaults must be defensibly calibrated, not aspirational)

## Validation notes

Validated: 2026-05-22
Verdict: HARDENED
Findings addressed: 22 total — 5 blocks, 13 hardens, 4 nits

Changes applied:
- AC-4 rewritten — `RagMiss` is **bare**; dropped `outcome.reason == "top1_below_floor"` and the non-existent `StoreQueried` event spy; the crossing-CVE *outcome* test now uses a leave-one-out store — Consistency K1/K2, Coverage C1
- AC-5 rewritten — the 12 off-diagonal *similarity* assertions now read a real 4×4 matrix from S5-01's `query_candidates` surface, not an invented event — Consistency K2, Design-Patterns D2
- AC-6 rewritten — `model_dump_json(..., sort_keys=True)` is not a Pydantic v2 kwarg; the golden is now an explicit projection serialized with `json.dumps(..., sort_keys=True)` — Test-Quality T1/T2
- AC-7 edited — `top1_kind` → `outcome_kind` (real union discriminator); dropped the nonsensical "AST" check; golden committed directly (not via the probe-portfolio regen harness) — Test-Quality T3, Consistency K6
- AC-8 rewritten — dropped the non-existent macOS CI / split-vote framing; now the diagonal-cell margin assertion over the AC-5 matrix — Consistency K3, Test-Quality T4
- AC-9 rewritten — dropped the duplicate macOS crossing-margin test; now the fixture-*separation* assertion (the real meaning of "calibration smoke test") + full-matrix diagnostic, covering the `RagDegraded` middle band — Coverage C4, Test-Quality T4
- AC-10 rewritten — split the monolithic fixture: module-scoped `embedder` (the expensive resource) vs scenario-specific stores (cheap) — resolves the AC-4⟂AC-10 unrunnable contradiction — Coverage C1, Design-Patterns D1
- AC-11 rewritten — `RecordProvenance.verify(...)` does not exist; `verify` is a module-level function and `RecordProvenance` is frozen data — Consistency K4
- AC-17 added — explicit execution-precondition gate (dependency closure must be GREEN, else `BLOCKED`) — Coverage C3
- Context, Goal, References, Implementation outline, TDD plan, Files-to-touch, Out-of-scope, Notes all reconciled to bare `RagMiss`, the `query_candidates` matrix, single-arch CI, and the `verify` module function.

Full audit log: docs/phases/04-vuln-llm-fallback-rag/stories/_validation/S5-04-threshold-calibration-smoke-test.md

## Context

Gap 6 of the phase architecture (lines 1144–1148) frames the problem precisely:

> Defaults are `high_floor=0.85`, `degraded_floor=0.65`. The design says Phase 6.5 will calibrate, but **Phase 4 ships before Phase 6.5**. The roadmap exit criterion ("second run hits RAG") depends on the same-CVE re-run scoring above `high_floor`. There is no Phase-4-internal evidence that 0.85 is the right floor for `fastembed` BGE-small on the Phase-4 fixture set.

The remedy is a calibration **smoke test** — not the Phase-6.5 full calibration harness, but a Phase-4-merge-gating sanity check that the shipped defaults actually classify the four `vuln-major-bump/*` fixtures correctly: each fixture's re-run against itself scores `RagHit` (≥ `high_floor`), and crossing-CVE queries (one fixture's advisory against a store from which that fixture's record has been held out) score `RagMiss` (< `degraded_floor`). If the smoke test fails, **Phase 4 does not merge until either the defaults are amended (ADR-04-0008 amendment with evidence) or the fixtures are made more discriminative** — never by relaxing the test (Global Rule 12: fail loud).

This is the most production-equivalent test in Step 5: real `FastembedEmbedder` (not a mock), real `ChromaPersistentStore` (not a fake), real records with real chain provenance, real `BandClassifier` with the YAML-loaded defaults. The only thing simulated is the orchestrator that would invoke the retriever — the test instantiates the retriever directly and calls `query(advisory, repo_ctx)`.

This story also pins the **golden retrieval** Gap 6 mentions — a recorded projection of one canonical fixture's `RetrievalOutcome` so a future embedder pin bump, chroma index format change, or hash function swap can't silently shift the top-1 ordering without the operator noticing.

A second responsibility: this story **empirically pins the score margin against the drift envelope**. ADR-04-0008 commits to "the band width itself must be wider than the cross-arch drift envelope; if drift is 0.005, a band of 0.001 reintroduces the failure." Phase-4 CI runs **x86_64 `ubuntu-24.04` only** (ADR-04-0007 §Consequences; CLAUDE.md "CI runs across Python 3.11 / 3.12 × `ubuntu-24.04`") — there is **no macOS runner**, and the *empirical* cross-architecture determinism validation is explicitly deferred to Phase 6.5's bench harness (ADR-04-0007 §Consequences, Open Question 8 in `final-design.md`). What this story does on single-arch CI is assert a **headroom margin**: each `RagHit` similarity must be ≥ `high_floor + DRIFT_MARGIN` and each crossing-CVE similarity ≤ `degraded_floor - DRIFT_MARGIN`. The margin (`0.02`, ~4× the estimated 0.005 drift envelope) means that when Phase 6.5 *does* run this corpus cross-arch, a ±0.005 perturbation cannot flip a band. The smoke test is the *headroom* assurance; Phase 6.5 is the *empirical* assurance.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Gap analysis — Gap 6` (lines 1144–1148) — the canonical motivation for this story.
  - `../phase-arch-design.md §Edge cases #10` — top-1 below floor is bare `RagMiss` ("LLM invoked without few-shot"); the smoke test validates this for crossing-CVE queries.
  - `../phase-arch-design.md §Goals — G6` — `high_floor=0.85`, `degraded_floor=0.65` defaults; `RetrievalOutcome = RagHit | RagMiss | RagDegraded`.
  - `../phase-arch-design.md §Idempotence` (lines 827–831) — RAG queries idempotent under `(cve_id, manifest_digest, embedding_model_digest, store_digest)`; the smoke test seeds a known store and asserts the projected outcome is stable across CI runs.
- **Phase ADRs:**
  - `../ADRs/0008-two-threshold-calibration-band.md` — the defaults this test pins; the "calibration is config, not code" rationale; `RagMiss` is **bare** (§Decision, §Pattern fit).
  - `../ADRs/0007-fastembed-onnx-over-sentence-transformers.md` — `BAAI/bge-small-en-v1.5` is the pinned model; drift envelope ~0.005 at the 5th decimal; **§Consequences: "Phase-4 CI runs x86_64 (ubuntu-24.04) only. arm64 cross-host determinism test is a known Phase-6.5 follow-up."**
- **Source design:**
  - `../final-design.md §Component 11 — SolvedExampleRetriever` ("Calibration band").
  - `../final-design.md §Gap analysis` Gap 6.
- **High-level impl:**
  - `../High-level-impl.md §Step 5` (lines 142–166); §Risks — "Calibration smoke test failing at merge time means the defaults are wrong."
- **Sibling validation reports (READ BEFORE WRITING — these pin the contracts this test consumes):**
  - `_validation/S5-01-retriever-query-composition.md` — `RagMiss` is bare; reason rides `RagMissEvent`; RAG events live in `src/codegenie/plugins/events.py`; the store exposes `query_candidates(..., embedding=...) -> Sequence[ScoredSolvedExample]`; `RagHit.few_shot` carries a `SolvedExample`.
  - `_validation/S5-02-two-threshold-band-classifier.md` — `BandClassifier(*, high_floor, degraded_floor)` is `kw_only`, pure, emits no events; its interior property margin is `MARGIN=0.01` (distinct from this story's `DRIFT_MARGIN=0.02`).
  - `_validation/S5-03-model-mismatch-and-orphan-exclusion.md` — `verify` is the module-level `codegenie.rag.provenance.verify(record, spanning_log)`; `RecordProvenance` is frozen data with **no methods**.
- **Existing code (READ BEFORE WRITING — Rule 8; note `src/codegenie/rag/` does not exist until the S4/S5 stack is GREEN):**
  - `src/codegenie/rag/retriever.py` (S5-01) + `src/codegenie/rag/confidence.py` (S5-02) — composed in the test; the retriever constructor signature is whatever S5-01 ships GREEN (do **not** pin a stale signature — see Implementation outline note).
  - `src/codegenie/rag/embedder.py` (S4-01) + `.codegenie/rag/embeddings_model.lock` — the model digest the test depends on; running on CI requires `codegenie embeddings bootstrap` to have populated the model cache.
  - `src/codegenie/rag/store.py` (S4-03) + `src/codegenie/rag/ingest.py` (S4-06) — the seeding + raw-candidate-read paths the test uses.
  - `src/codegenie/rag/provenance.py` (S4-05) — the module-level `verify(record, spanning_log)`.
  - `fixtures/vuln-major-bump/express-cve-2026-1234/`, `.../lodash-cve-2026-9876/` (S7-05) — the canonical fixtures. If S7-05 has not landed at execution time, this story creates a minimal pair under `tests/fixtures/phase4_smoke/` per AC-12.
  - `tests/golden/test_goldens_match.py` — the project golden convention is `scripts/regen_golden.py --update` / `--check`; there is **no** `pytest --update-goldens` option (AC-7).
  - `tests/conftest.py` / `pyproject.toml` — `pytest-asyncio` `asyncio_mode = "auto"` (no `@pytest.mark.asyncio` needed); `--cov-fail-under=85` means narrow subsets need `--no-cov`.

## Goal

Land `tests/integration/test_phase4_threshold_smoke.py` — an integration test that seeds the four `vuln-major-bump/*` fixtures into a real `ChromaPersistentStore` via a real `FastembedEmbedder`, then asserts: (a) each fixture's same-CVE re-run scores `RagHit` with `score >= high_floor + DRIFT_MARGIN`; (b) every off-diagonal crossing-CVE *similarity* (read from the raw-candidate matrix) is `<= degraded_floor - DRIFT_MARGIN`; (c) a crossing-CVE *query* against a leave-one-out store dispatches a bare `RagMiss`; (d) a recorded golden projection of one canonical fixture's outcome is byte-identical across CI runs; (e) the hit cluster and miss cluster are cleanly separated, so the defaults are evidence-backed for the shipped portfolio.

## Acceptance criteria

### Execution precondition

- [ ] AC-17 — **S5-04 is 100% integration and must not be executed until its entire dependency closure is GREEN.** Before the executor writes any test, it verifies S4-01..S4-06, S5-01, S5-02, S5-03 are GREEN (the `src/codegenie/rag/` package exists and its sibling stories report `GREEN`/`Done`) and that fixtures are available (S7-05 GREEN **or** the AC-12 local-fallback path is taken). If any dependency is not GREEN, the story status becomes `BLOCKED` with an `_attempts/S5-04-*.md` entry naming the missing dependency — `pytest.mark.xfail`/`skip` is **forbidden** (AC-14). Rationale: unlike S5-03 (which has standalone filter ACs and legitimately defers retriever ACs via `xfail`), S5-04 has nothing partial to ship — a half-wired smoke test is worse than an absent one. (validator: added — Coverage C3; the story previously had no precondition handling for the all-HARDENED-not-GREEN closure.)

### Same-CVE re-run = `RagHit` (the roadmap exit criterion #2 dependency)

- [ ] AC-1 — `tests/integration/test_phase4_threshold_smoke.py::test_same_cve_rerun_is_rag_hit` — parametrized over the four fixtures. For each fixture, against the module-scoped `seeded_smoke_store` (all four fixtures seeded — AC-10), build a `Query`/advisory + `repo_ctx` via the plugin's `rag_query_builder` (S7-02; or a fixture-local minimal builder if S7-02 unlanded), call `await retriever.query(advisory, repo_ctx)`, assert: `isinstance(outcome, RagHit)`, `outcome.score >= HIGH_FLOOR + DRIFT_MARGIN` (`0.87`), `outcome.few_shot.id == fixture_id(fixture)`. (validator: edited — wording reconciled to the module-scoped all-four store; `few_shot` is the `SolvedExample` per S5-01.)
- [ ] AC-2 — The `0.02` margin is a module-level `Final` constant `DRIFT_MARGIN: Final[float] = 0.02` with an inline comment: drift envelope ~`0.005` (ADR-04-0007); `0.02` is ~4× headroom; Phase-4 CI is single-arch (`ubuntu-24.04`) so this is a *headroom* assertion, and `0.02` is deliberately wider than S5-02's classifier-interior `MARGIN=0.01` (a smoke test wants more headroom than the band-interior property). If a future ADR amendment changes the margin, the change is in one place; AC-2's Refactor check (see TDD plan) bans inline `0.02` / `0.85 + 0.02` literals. (validator: edited — comment corrected; the macOS justification removed.)
- [ ] AC-3 — Test runs successfully under both `make test` and `pytest tests/integration/test_phase4_threshold_smoke.py --no-cov` (per project pytest config note: narrow subsets falsely fail the `--cov-fail-under=85` gate).

### Crossing-CVE query = `RagMiss` (outcome dispatch)

- [ ] AC-4 — `tests/integration/test_phase4_threshold_smoke.py::test_crossing_cve_query_is_rag_miss` — parametrized over the four fixtures as `held_out`. For each `held_out`, build a **leave-one-out store** seeded with the *other three* fixtures only (over the shared `embedder` — AC-10), call `await retriever.query(held_out.advisory, held_out.repo_ctx)`, assert `isinstance(outcome, RagMiss)`. `RagMiss` is **bare** — it carries no `reason` field (S1-04, S5-01, S5-02, S5-03, ADR-04-0008 §Decision, arch edge case #10); the test asserts the type only and must **not** access `outcome.reason` or any attribute. Miss-cause observability is S5-01's `RagMissEvent` and is out of scope here. The leave-one-out store proves the band classifier dispatches a sub-`degraded_floor` top-1 to `RagMiss` end-to-end on real embeddings. (validator: rewritten — Consistency K1 [`RagMiss` is bare] + K2 [no `StoreQueried` event] + Coverage C1 [the old "seed only fixture_a" contradicted the all-four module store]; the held-out store is the correct shape for a `RagMiss` *outcome*.)

### Off-diagonal similarity — the 12 crossing pairs

- [ ] AC-5 — `tests/integration/test_phase4_threshold_smoke.py::test_crossing_similarity_below_degraded_floor` — for each ordered pair `(advisory_a, record_b)` with `a != b` (all `4 * 3 = 12`), read the cross-similarity from the `similarity_matrix` module fixture (AC-8) and assert `matrix[a][b] <= DEGRADED_FLOOR - DRIFT_MARGIN` (`0.63`). The matrix is built from S5-01's raw-candidate store surface — `store.query_candidates(embedding=embed(advisory_a))` against the all-four `seeded_smoke_store` returns `Sequence[ScoredSolvedExample]`; `matrix[a][b]` is the `.score` of the candidate whose `.record.id == fixture_id(b)`. Each pair is a `pytest.param(..., id=f"{a}-vs-{b}")` so a failing pair surfaces by name. The assertion message names the pair, the actual score, and which band the score landed in (`high` / `degraded` / `miss`) — a pair landing in the `RagDegraded` band is diagnosed precisely, not silently passed. (validator: rewritten — Consistency K2: the score is read from the real `query_candidates` surface, not a non-existent `StoreQueried` event; `RagMiss` being bare means off-diagonal *similarity* cannot be read off an outcome and must come from the candidate matrix.)

### Golden retrieval (deterministic across CI runs)

- [ ] AC-6 — `tests/integration/test_phase4_threshold_smoke.py::test_golden_retrieval_stable` — for one canonical fixture (`express-cve-2026-1234`), against `seeded_smoke_store` (all four seeded), call `await retriever.query(...)`, build an **explicit projection dict** `{"store_digest": ..., "top1_id": str(outcome.few_shot.id), "outcome_kind": outcome.kind, "score_band": "high"}`, serialize it with `json.dumps(projection, sort_keys=True, indent=2)`, and compare byte-for-byte to `tests/golden/rag/threshold_smoke_express.json`. Note: `BaseModel.model_dump_json()` is **not** used and has **no** `sort_keys` argument in Pydantic v2 — deterministic key ordering comes from `json.dumps(..., sort_keys=True)` over the hand-built projection. (validator: rewritten — Test-Quality T1 [`sort_keys` is not a Pydantic v2 kwarg] + T2 [a raw `model_dump_json` byte-compare contradicts AC-7's 4-field golden schema].)
- [ ] AC-7 — The golden file `tests/golden/rag/threshold_smoke_express.json` contains **exactly** the keys `{store_digest, top1_id, outcome_kind, score_band}` and **no raw `score` float** (cross-architecture float instability would flake a raw-`score` golden). The test asserts `set(json.loads(golden_text)) == {"store_digest", "top1_id", "outcome_kind", "score_band"}` as a structural guard against a future raw-score creep. `store_digest` must be the content-addressed canonical-store digest (ADR-04-0016 — a digest of the canonical YAML records, deterministic across runs), **not** a digest of chroma's on-disk files; if a stable `store_digest` is not cheaply available at execution time, drop it from the projection rather than let the golden flake (record the decision in the attempt log). The golden is a small hand-readable file committed directly — it is **not** wired into `scripts/regen_golden.py` (that harness owns the probe-output portfolio). (validator: edited — `top1_kind` → `outcome_kind` [the real `RetrievalOutcome` union discriminator; `SolvedExample` has no guaranteed `kind`]; dropped the nonsensical "AST" check on a JSON file; pinned the golden convention.)

### Pairwise similarity matrix — diagonal margin + fixture separation

- [ ] AC-8 — `tests/integration/test_phase4_threshold_smoke.py` defines a module-scoped `similarity_matrix` fixture: for each of the four advisories, call `store.query_candidates(embedding=embed(advisory))` against `seeded_smoke_store` once and collect `{record_id: score}` → a 4×4 `dict[FixtureId, dict[FixtureId, float]]`. `test_self_similarity_above_high_floor` is parametrized over the four diagonal cells and asserts `matrix[f][f] >= HIGH_FLOOR + DRIFT_MARGIN` — the candidate-level evidence behind AC-1's outcome-level `RagHit`. The matrix is computed once (4 `query_candidates` calls total) and reused by AC-5 and AC-9 — `query_candidates` is called 4 times for the whole module, not per parametrized case. (validator: rewritten — Consistency K3: the old `test_score_margin_above_drift_envelope` assumed a Linux-vs-macOS split-vote on a CI matrix that does not exist; Design-Patterns D2: the matrix is pure data derived once, the test functions are thin assertions over it.)
- [ ] AC-9 — `tests/integration/test_phase4_threshold_smoke.py::test_fixture_clusters_are_separated` — over the `similarity_matrix`, assert `min(diagonal scores) - max(off-diagonal scores) >= SEPARATION_GAP` where `SEPARATION_GAP: Final[float] = 0.10` (the hit cluster and the miss cluster must be cleanly separated — this is the real meaning of a calibration smoke test: not just "above/below a floor" but "the fixtures discriminate"). The test also writes the full 4×4 matrix to the pytest output (one line per advisory, scores rounded to 4 dp) so a reviewer sees the actual distribution. If **any** off-diagonal cell lands in `[degraded_floor, high_floor)` (the `RagDegraded` middle band), the failure message explicitly flags "crossing pair {a}-vs-{b} landed in the RagDegraded band — fixtures insufficiently discriminative" — the middle band is otherwise untested by AC-1 (high) and AC-5 (miss). (validator: rewritten — Coverage C4 [the `RagDegraded` band was wholly uncovered]; Test-Quality T4 [the old `test_crossing_cve_margin_below_degraded_floor` duplicated AC-5]; this AC now has a genuinely distinct job.)

### Fixtures + seeding

- [ ] AC-10 — Test setup splits the expensive resource from the cheap one:
  - a module-scoped `embedder` fixture constructs **one** `FastembedEmbedder` (bootstrapped against `.codegenie/rag/embeddings_model.lock`; CI runs `codegenie embeddings bootstrap` once before pytest — AC-16). `FastembedEmbedder` is the load-bearing cost (~180 MB RSS, ~500 ms cold start) and **must** be module-scoped and shared.
  - a module-scoped `seeded_smoke_store` fixture creates a temp `ChromaPersistentStore` and `ingest_solved_example` (S4-06)s **all four** fixtures into it (used by AC-1, AC-6, AC-8). `ChromaPersistentStore` construction + seeding 4 records is cheap.
  - AC-4's four leave-one-out stores are built per-case (each seeded with three fixtures) over the **same shared `embedder`** — cheap because the embedder, not the store, is the cost.
  - every store fixture cleans up its temp dir on teardown.
  This split is what makes AC-4 (a store *missing* a record) and AC-1/AC-6/AC-8 (a store *with all* records) coexist. (validator: rewritten — Coverage C1 + Design-Patterns D1: the previous "one module store shared by all 16 cases" was unrunnable — a store containing every fixture cannot produce a crossing-CVE `RagMiss`.)
- [ ] AC-11 — Each store fixture asserts, before yielding, that `verify(record, spanning_log) is True` for every seeded record — `verify` is the **module-level function** `codegenie.rag.provenance.verify(record, spanning_log)` (S4-05; `RecordProvenance` is frozen data with no methods — there is no `RecordProvenance.verify`). This is a pre-condition assertion inside the fixture, not a separate test — it eliminates "test failed because of provenance, not because of similarity" false signals. (validator: rewritten — Consistency K4: `RecordProvenance.verify(...)` does not exist.)
- [ ] AC-12 — If S7-05's fixture portfolio has not landed at execution time, the smoke test uses minimal local fixtures under `tests/fixtures/phase4_smoke/{express,lodash,axios,debug}.yaml` (four canonical `SolvedExample` YAML records with valid chain provenance). The local-fixture path is gated behind `if not (FIXTURES_DIR / "vuln-major-bump").exists(): use_local_fixtures()` — once S7-05 lands, this branch is dead code and a follow-up cleanup ticket removes it. The choice taken (production vs local fixtures) is recorded in the `_attempts/` log.

### Failure-mode honesty (Global Rule 12)

- [ ] AC-13 — On test failure, the pytest output names: (a) which fixture or crossing pair failed, (b) the actual score, (c) the band the score landed in (`high` / `degraded` / `miss`), (d) the remediation path: "If this is the first failure on this fixture, the ADR-04-0008 defaults are wrong for the shipped fixtures. Amend the ADR (with the new floors + evidence-quoted scores) before merge; do NOT relax this test." The assertion-message template is shared by AC-1, AC-4, AC-5, AC-8, AC-9.
- [ ] AC-14 — The test module contains **no** `pytest.mark.xfail` and **no** `pytest.mark.skip` modifier. The smoke test is unconditionally CI-gating once it lands. The only sanctioned way to not run it is the `BLOCKED` story-status path of AC-17, which leaves a paper trail in `_attempts/`.

### Performance + CI hygiene

- [ ] AC-15 — Total runtime of the test module ≤ 30 seconds on CI (fastembed cold start dominates; the module-scoped `embedder` amortizes it across every case). If > 30 s, surface as a Phase-4 perf regression — not a story scope edit.
- [ ] AC-16 — `codegenie embeddings bootstrap` must run before this test in CI. CI workflow file edit: ensure `make test` is preceded by the bootstrap call (cached model weights between runs). The test docstring documents that local-dev runs must `python -m codegenie embeddings bootstrap` once.

## Implementation outline

```python
# tests/integration/test_phase4_threshold_smoke.py
"""Calibration smoke test — Gap 6 + ADR-04-0008.

Pins that the shipped defaults (high_floor=0.85, degraded_floor=0.65) classify
the Phase-4 fixture portfolio correctly. If this test fails, the defaults are
wrong for the shipped fixtures — Phase 4 must NOT merge until ADR-04-0008 is
amended with evidence-quoted scores (not until the test is relaxed).

Phase-4 CI is single-architecture (ubuntu-24.04). The DRIFT_MARGIN below is a
*headroom* margin; the empirical cross-architecture validation is a Phase-6.5
follow-up (ADR-04-0007 §Consequences).

Local runs: `pytest tests/integration/test_phase4_threshold_smoke.py --no-cov`
           (and `python -m codegenie embeddings bootstrap` once beforehand)."""

from __future__ import annotations

import json
from typing import Final

import pytest

from codegenie.rag.retriever import SolvedExampleRetriever
from codegenie.rag.confidence import BandClassifier
from codegenie.rag.store import ChromaPersistentStore
from codegenie.rag.embedder import FastembedEmbedder
from codegenie.rag.provenance import verify  # module-level — S4-05
from codegenie.rag.models import RagHit, RagDegraded, RagMiss

HIGH_FLOOR: Final[float] = 0.85
DEGRADED_FLOOR: Final[float] = 0.65
# Cross-architecture ONNX drift envelope is ~0.005 (ADR-04-0007). 0.02 is ~4x
# headroom — and deliberately wider than S5-02's classifier-interior MARGIN
# (0.01): a smoke test wants more slack than a band-interior property. Phase-4
# CI is single-arch; the empirical cross-arch run is a Phase-6.5 follow-up.
DRIFT_MARGIN: Final[float] = 0.02
# The hit cluster and miss cluster must be cleanly separated, not merely on the
# right side of a floor — this is what "calibrated for the portfolio" means.
SEPARATION_GAP: Final[float] = 0.10

FIXTURES: Final[tuple[str, ...]] = (
    "express-cve-2026-1234", "lodash-cve-2026-9876",
    "axios-cve-2026-5555",   "debug-cve-2026-7777",
)


@pytest.fixture(scope="module")
def embedder() -> FastembedEmbedder:
    """The expensive resource (~180 MB RSS, ~500 ms cold start). Shared by
    every store fixture in this module — do NOT make this function-scoped."""
    return FastembedEmbedder()  # refuse-start on embeddings_model.lock drift


@pytest.fixture(scope="module")
def seeded_smoke_store(tmp_path_factory, embedder):
    """One real chroma store with ALL FOUR fixtures seeded. Used by the
    same-CVE-hit, golden, and similarity-matrix tests."""
    store = _build_store(tmp_path_factory.mktemp("smoke_all"), embedder, FIXTURES)
    yield store
    store.close()


def _build_store(persist_dir, embedder, fixture_names):
    """Seed `fixture_names` into a fresh ChromaPersistentStore. Asserts
    provenance for every seeded record (AC-11) before returning."""
    store = ChromaPersistentStore(persist_dir=persist_dir / "chroma")
    capability = _phase4_local_capability_mint(...)   # S4-06 interim shim
    for name in fixture_names:
        example = load_solved_example(name)
        ingest_solved_example(example, store, embedder, capability)
        assert verify(example, store.spanning_log) is True, (  # AC-11
            f"seed precondition failed: {name} did not chain-verify"
        )
    return store


def _make_retriever(store, embedder) -> SolvedExampleRetriever:
    """Construct a real retriever. IMPORTANT: the constructor keyword set must
    match whatever S5-01 ships GREEN — do not pin a stale signature here. As of
    S5-01's hardened spec it injects a store, embedder, spanning_log,
    record_verifier, query_text_builder, query_builder, confidence_classifier,
    event_log, and model_digest_filter. Reconcile at execution time."""
    return SolvedExampleRetriever(
        store=store, embedder=embedder,
        confidence_classifier=BandClassifier(
            high_floor=HIGH_FLOOR, degraded_floor=DEGRADED_FLOOR),
        ...,  # remaining injected deps per S5-01 GREEN
    )


@pytest.fixture(scope="module")
def similarity_matrix(seeded_smoke_store, embedder):
    """4x4 cross-similarity, computed once via S5-01's raw-candidate surface."""
    matrix: dict[str, dict[str, float]] = {}
    for advisory_name in FIXTURES:
        advisory, _ = load_advisory_and_ctx(advisory_name)
        candidates = seeded_smoke_store.query_candidates(
            embedding=embedder.embed(render_query_text(advisory)))
        matrix[advisory_name] = {
            str(c.record.id): c.score for c in candidates
        }
    return matrix


async def test_same_cve_rerun_is_rag_hit(seeded_smoke_store, embedder):
    """Roadmap exit criterion #2 ('second run hits RAG'). Parametrized over
    FIXTURES (see pytest_generate_tests / @parametrize in the real file)."""
    retriever = _make_retriever(seeded_smoke_store, embedder)
    advisory, repo_ctx = load_advisory_and_ctx(fixture)
    outcome = await retriever.query(advisory, repo_ctx)
    assert isinstance(outcome, RagHit), _fail_msg(fixture, outcome)
    assert outcome.score >= HIGH_FLOOR + DRIFT_MARGIN, _fail_msg(fixture, outcome)
    assert outcome.few_shot.id == fixture_id(fixture)


async def test_crossing_cve_query_is_rag_miss(tmp_path_factory, embedder):
    """held_out's advisory against a store of the OTHER THREE fixtures only."""
    others = tuple(f for f in FIXTURES if f != held_out)
    store = _build_store(tmp_path_factory.mktemp(f"loo_{held_out}"),
                         embedder, others)
    retriever = _make_retriever(store, embedder)
    advisory, repo_ctx = load_advisory_and_ctx(held_out)
    outcome = await retriever.query(advisory, repo_ctx)
    assert isinstance(outcome, RagMiss), _fail_msg(held_out, outcome)
    # RagMiss is BARE — no `outcome.reason`. Do not access any attribute.
    store.close()
```

## TDD plan — red / green / refactor

### Red — write the failing test first

```python
# Red-phase scaffold ONLY — not a committed deliverable. Confirms the test
# infrastructure produces a RED before fixtures are seeded. Once the
# seeded_smoke_store fixture and the parametrized green tests land, this is
# DELETED (it is not part of the shipped module).

async def test_smoke_red_empty_store_is_rag_miss(tmp_path, embedder):
    store = ChromaPersistentStore(persist_dir=tmp_path / "chroma")
    retriever = _make_retriever(store, embedder)
    advisory, repo_ctx = load_advisory_and_ctx("express-cve-2026-1234")
    outcome = await retriever.query(advisory, repo_ctx)
    assert isinstance(outcome, RagMiss)   # bare — empty store ⇒ RagMiss
    # (the "empty_store" reason rides S5-01's RagMissEvent, not RagMiss itself)
```

### Green — make it pass

1. Land the `embedder` + `seeded_smoke_store` + `similarity_matrix` module-scoped fixtures and the `_build_store` / `_make_retriever` helpers per the implementation outline.
2. Land `test_same_cve_rerun_is_rag_hit` parametrized over `FIXTURES`. Run; if a fixture fails, the test output names the failing fixture + actual score + remediation path (Global Rule 12 / AC-13).
3. Land `test_crossing_cve_query_is_rag_miss` parametrized over the four held-out fixtures (leave-one-out stores).
4. Land `test_crossing_similarity_below_degraded_floor` parametrized over the 12 off-diagonal pairs (reads `similarity_matrix`).
5. Land `test_self_similarity_above_high_floor` (4 diagonal cells) and `test_fixture_clusters_are_separated`.
6. Land `test_golden_retrieval_stable`. The golden `tests/golden/rag/threshold_smoke_express.json` is a small hand-authored 4-key JSON file — generate it once by running the test with the projection printed, eyeball it, commit it directly. It is **not** registered with `scripts/regen_golden.py`.
7. Confirm the CI workflow runs `codegenie embeddings bootstrap` before `make test`.
8. Delete the Red-phase scaffold test.

If any test in step 2–5 is RED at this point: **do not relax the test**. Open an ADR-04-0008 amendment proposal with the actual scores and proposed new floors. The PR includes the ADR amendment, not a test loosening.

### Refactor — clean up

- Extract `load_solved_example` / `load_advisory_and_ctx` / `fixture_id` / `render_query_text` into `tests/fixtures/phase4_smoke/loader.py` — the ACs already depend on all four, so the helper module exists from the start, not "if it grows past ~5 LOC".
- Confirm the golden file is human-readable JSON (`sort_keys=True`, `indent=2`) so a future diff reviewer can read it.
- Keep the module docstring's verbatim Gap-6 quote — the next reader who sees this test fail must understand it is a deliberate Phase-4-merge gate, not an over-zealous assertion.
- Verify `DRIFT_MARGIN` / `HIGH_FLOOR` / `DEGRADED_FLOOR` / `SEPARATION_GAP` are the only places those numbers appear; no inline `0.02` / `0.85 + 0.02` / `0.63` literals in test bodies.
- Confirm the test module follows the project `asyncio_mode = "auto"` convention — `async def test_...` without `@pytest.mark.asyncio` (the outline omits the marker; match the project convention).

## Files to touch

| Path | Why |
|---|---|
| `tests/integration/test_phase4_threshold_smoke.py` | NEW — the smoke test module (the deliverable). |
| `tests/fixtures/phase4_smoke/{express,lodash,axios,debug}.yaml` | NEW (conditional) — local minimal `SolvedExample` records if S7-05 has not landed. |
| `tests/fixtures/phase4_smoke/loader.py` | NEW — helpers: `load_solved_example`, `load_advisory_and_ctx`, `fixture_id`, `render_query_text`. |
| `tests/golden/rag/threshold_smoke_express.json` | NEW — golden projection `{store_digest, top1_id, outcome_kind, score_band}` for `express-cve-2026-1234`; committed directly. |
| `.github/workflows/*.yml` (CI workflow file) | EXT — ensure `codegenie embeddings bootstrap` runs before `make test`. |
| `docs/operations/embeddings.md` (S7-10 owns; this story may stub) | EXT — note that local-dev runs require `codegenie embeddings bootstrap` once. |

## Out of scope

- **Phase-6.5 calibration harness** — this is the *smoke* test, not the *full calibration*. Phase 6.5 ships per-`(task_class, language, build_system)` calibration with labeled evidence; this story only pins the four-fixture defaults.
- **Empirical cross-architecture drift validation** — Phase-4 CI is x86_64 `ubuntu-24.04` only (ADR-04-0007 §Consequences). This story asserts a *headroom* margin; the cross-arch (arm64/macOS) determinism test is a Phase-6.5 bench-harness follow-up (`final-design.md` Open Question 8). Do not add a macOS CI job in this story.
- **ADR-04-0008 amendment** — if the smoke test fails on merge, the amendment is a separate PR with the actual scores. This story does not pre-amend the ADR.
- **`plugin.yaml` schema** — S7-04 lands the schema. This story takes thresholds as constants in the test module; production wiring lives in S7-01.
- **Fixture portfolio creation** — S7-05 owns the canonical fixtures. This story creates a minimal-fallback set (AC-12) only if S7-05 hasn't landed at execution time.
- **Embedder-mismatch / chain-orphan exclusion paths** — S5-03 + S4-05 cover those; this story exercises only the happy path (all records embedded under the current model, all chain-verified). The retriever's `model_digest_filter` is a pass-through here.
- **`RagMissEvent` / miss-cause observability** — S5-01 owns the typed reason event. This story asserts `RagMiss` *type* only.
- **Cassette-based integration with the leaf LLM** — this is a *retrieval-only* smoke test. The LLM-side path is exercised by S7-06's E2E.

## Notes for the implementer

- **The most important test in Step 5.** A reviewer reading the Step-5 PRs should be able to point at `test_phase4_threshold_smoke.py` and ask "does this pass on CI?" — if yes, the band defaults are evidence-backed for the shipped fixtures; if no, Phase 4 doesn't merge. There is no in-between. Treat it as the merge gate.
- **`RagMiss` is bare.** It carries no `reason`, no `score`, no fields. This was corrected across S1-04, S5-01, S5-02, and S5-03 — do not reintroduce `RagMiss(reason=...)` or `outcome.reason`. A crossing-CVE *outcome* is asserted by `isinstance(outcome, RagMiss)`; a crossing-CVE *similarity* is read from the `query_candidates` candidate matrix, never from the outcome.
- **There is no macOS CI.** ADR-04-0007 §Consequences and CLAUDE.md both pin Phase-4 CI to `ubuntu-24.04`. `DRIFT_MARGIN` exists so that *when Phase 6.5 runs this corpus cross-arch*, a ±0.005 perturbation cannot flip a band — it is headroom, not an empirical cross-arch test. Do not write a "passes on Linux, fails on macOS" assertion; that scenario cannot occur in Phase-4 CI.
- **The similarity matrix is the load-bearing abstraction.** Compute the 4×4 cross-similarity once (4 `query_candidates` calls in a module-scoped fixture); every band assertion (diagonal margin, off-diagonal margin, cluster separation, `RagDegraded` detection) is a thin read over that pure data. Do not re-query per parametrized case.
- **Split the embedder from the store.** `FastembedEmbedder` is the ~180 MB / ~500 ms cost — module-scoped, shared. `ChromaPersistentStore` seeding is cheap — build scenario-specific stores (all-four for hit/matrix/golden; leave-one-out for the crossing-CVE `RagMiss`). The previous draft's single all-four store could not produce a crossing-CVE `RagMiss` at all (every fixture's record was present).
- **`verify` is a module-level function.** `from codegenie.rag.provenance import verify` — `verify(record, spanning_log) -> bool`. `RecordProvenance` is frozen data with no behavior; there is no `RecordProvenance.verify`.
- **The golden carries a band, not a score.** Cross-architecture float instability would flake a raw-`score` golden every other CI run; pinning the *band* (`score_band: "high"`) plus `top1_id` is the stable contract. Use `json.dumps(projection, sort_keys=True, indent=2)` — Pydantic v2's `model_dump_json()` has no `sort_keys` argument.
- **The xfail/skip prohibition (AC-14) is intentional.** A future engineer encountering a flaky smoke test will be tempted to `xfail` "until Phase 6.5 lands." That is the failure mode this story exists to prevent. If the test is genuinely flaky, the resolution is *fix the flakiness* (margin widening via ADR amendment, fixture re-engineering) — not a skip marker. The only sanctioned non-run is the `BLOCKED` story-status path (AC-17).
- **Execution sequencing (AC-17).** S5-04 is the last story in Step 5; by the time the executor reaches it, S5-01/S5-02/S5-03 and the S4 stack should be GREEN. If they are not, do not write a half-wired test — set the story `BLOCKED` and log the missing dependency. The `src/codegenie/rag/` package does not exist until that stack lands.
- **Retriever construction is not pinned here.** The `_make_retriever` helper in the outline is illustrative — the exact constructor keyword set is whatever S5-01 ships GREEN. Reconcile at execution time against the real `SolvedExampleRetriever.__init__`; do not copy a stale signature from this story.
- **Fixture availability sequencing.** S7-05 may not have landed when this story executes. AC-12 prescribes a local-minimal fallback under `tests/fixtures/phase4_smoke/`. Once S7-05 lands, those local fixtures become dead code; the cleanup is in S7-05's PR (or a follow-up). Document the dependency explicitly in this story's `_attempts/` log.
- **The `codegenie embeddings bootstrap` precondition.** Without it, `FastembedEmbedder.__init__` refuses to start (lock-hash mismatch). CI must run the bootstrap once and cache the model weights. A CI-green run is the only evidence that the smoke test actually executes against real embeddings, not a mock.
- **Failure messages quote the remediation path.** AC-13's failure-message template is the load-bearing UX for the next engineer who breaks the smoke test: which fixture/pair, what score, what band, and *what to do* (amend the ADR, not the test). Get the wording right.
