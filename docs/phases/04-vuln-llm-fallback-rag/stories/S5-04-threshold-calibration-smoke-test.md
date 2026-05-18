# Story S5-04 — Threshold-calibration smoke test (`test_phase4_threshold_smoke.py`)

**Step:** Step 5 — Ship SolvedExampleRetriever + two-threshold band + calibration smoke test
**Status:** Ready
**Effort:** M
**Depends on:** S5-02 (`BandClassifier` shipped with defaults `high_floor=0.85`, `degraded_floor=0.65`), S5-01 (`SolvedExampleRetriever` composes), S4-01 (`FastembedEmbedder` + bootstrap CLI so the smoke test can produce real embeddings), S4-03 (`ChromaPersistentStore` so the smoke test can seed records into a real store), S4-04 (canonical YAML + manifest so records have valid provenance for chain-verify), S4-05 (chain verification), S4-06 (capability-minted ingest path so records land legitimately), S7-05 (fixtures — this story takes the four `vuln-major-bump/*` fixture solved examples; if S7-05 has not landed yet, this story ships a minimal Phase-5-local fixture set under `tests/fixtures/phase4_smoke/` and S7-05 wires the production fixtures later)
**ADRs honored:** ADR-04-0008 (two-threshold band — this test pins the *defaults* against the shipped fixture portfolio; a fail means the defaults are wrong and an ADR amendment updates them *before* merge per Global Rule 12), ADR-04-0007 (cross-architecture ONNX drift envelope; the smoke test runs on the CI matrix and must pass on both Linux + macOS), Gap 6 from arch design (calibration smoke test is the load-bearing assurance Phase 4 doesn't merge with wrong defaults), production ADR-0008 (honest confidence — defaults must be defensibly calibrated, not aspirational)

## Context

Gap 6 of the phase architecture (lines 1140–1145) frames the problem precisely:

> Defaults are `high_floor=0.85`, `degraded_floor=0.65`. The design says Phase 6.5 will calibrate, but **Phase 4 ships before Phase 6.5**. The roadmap exit criterion ("second run hits RAG") depends on the same-CVE re-run scoring above `high_floor`. There is no Phase-4-internal evidence that 0.85 is the right floor for `fastembed` BGE-small on the Phase-4 fixture set.

The remedy is a calibration **smoke test** — not the Phase-6.5 full calibration harness, but a Phase-4-merge-gating sanity check that the shipped defaults actually classify the four `vuln-major-bump/*` fixtures correctly: each fixture's re-run against itself scores `RagHit` (≥ `high_floor`), and crossing-CVE queries (one fixture's advisory against a different fixture's seeded record) score `RagMiss` (< `degraded_floor`). If the smoke test fails, **Phase 4 does not merge until either the defaults are amended (ADR-04-0008 amendment with evidence) or the fixtures are made more discriminative** — never by relaxing the test (Global Rule 12: fail loud).

This is the most production-equivalent test in Step 5: real `FastembedEmbedder` (not a mock), real `ChromaPersistentStore` (not a fake), real records with real chain provenance, real `BandClassifier` with the YAML-loaded defaults. The only thing simulated is the orchestrator that would invoke the retriever — the test instantiates the retriever directly and calls `query(advisory, repo_ctx)`.

This story also pins the **golden retrieval** Gap 6 mentions — a recorded `RetrievalOutcome.model_dump_json()` for one canonical fixture so a future embedder pin bump, chroma index format change, or hash function swap can't silently shift the top-1 ordering without the operator noticing.

A second responsibility: this story is the place where **the ONNX float-drift envelope is empirically validated**. ADR-04-0008 commits to "the band width itself must be wider than the cross-arch drift envelope; if drift is 0.005, a band of 0.001 reintroduces the failure." The smoke test runs in CI on `ubuntu-24.04` and (per project CI matrix) on macOS in the nightly job. If a fixture's `RagHit` score is `0.851` on Linux and `0.849` on macOS, the smoke test would split-vote — that is the signal the band is narrower than drift. The test asserts a *margin* (each `RagHit` score must be ≥ `high_floor + 0.02` and each `RagMiss` score must be ≤ `degraded_floor - 0.02`) so a 0.005 drift can't flip a band.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Gap analysis — Gap 6` (lines 1140–1145) — the canonical motivation for this story.
  - `../phase-arch-design.md §Edge cases #10` — top-1 below floor is `RagMiss`; the smoke test validates this for crossing-CVE queries.
  - `../phase-arch-design.md §Goals — G6` (line 23) — `high_floor=0.85`, `degraded_floor=0.65` defaults.
  - `../phase-arch-design.md §Idempotence + replayability` (lines 826–844) — RAG queries idempotent under `(cve_id, manifest_digest, embedding_model_digest, store_digest)`; the smoke test seeds a known store_digest and asserts the outcome is stable across CI runs.
- **Phase ADRs:**
  - `../ADRs/0008-two-threshold-calibration-band.md` — the defaults this test pins; the "calibration is config, not code" rationale.
  - `../ADRs/0007-fastembed-onnx-over-sentence-transformers.md` — `BAAI/bge-small-en-v1.5` is the pinned model; drift envelope ~0.005 at the 5th decimal.
- **Source design:**
  - `../final-design.md §Component 11 — SolvedExampleRetriever — "Calibration band"`.
  - `../final-design.md §Gap analysis` Gap 6.
- **High-level impl:**
  - `../High-level-impl.md §Step 5` (lines 142–166); §Implementation-level risks item 4 — "Calibration smoke test failure at Phase-4 merge."
- **Existing code (READ BEFORE WRITING — Rule 8):**
  - `src/codegenie/rag/retriever.py` (S5-01) + `src/codegenie/rag/confidence.py` (S5-02) — composed in the test.
  - `src/codegenie/rag/embedder.py` (S4-01) + `embeddings_model.lock` — the model digest the test depends on; running on CI requires `codegenie embeddings bootstrap` to have populated the model cache.
  - `src/codegenie/rag/store.py` (S4-03) + `src/codegenie/rag/ingest.py` (S4-06) — the seeding path the test uses to land records.
  - `fixtures/vuln-major-bump/express-cve-2026-1234/`, `fixtures/vuln-major-bump/lodash-cve-2026-9876/` (S7-05) — the canonical fixtures. If S7-05 has not landed at execution time, this story creates a minimal pair under `tests/fixtures/phase4_smoke/` covering: (a) two same-CVE re-run cases, (b) two crossing-CVE cases.
  - `tests/conftest.py` — `pytest-asyncio` `asyncio_mode = "auto"` (per project pytest config); `--cov-fail-under=85` means narrow subsets need `--no-cov`.

## Goal

Land `tests/integration/test_phase4_threshold_smoke.py` — an integration test seeding the four `vuln-major-bump/*` fixtures into a real `ChromaPersistentStore` via `FastembedEmbedder`, then asserting: (a) each fixture's same-CVE re-run scores `RagHit` with `score >= high_floor + 0.02`; (b) crossing-CVE queries (every off-diagonal pair) score `RagMiss` with `score <= degraded_floor - 0.02`; (c) a recorded golden retrieval is byte-identical across CI runs.

## Acceptance criteria

### Same-CVE re-run = `RagHit` (the roadmap exit criterion #2 dependency)

- [ ] AC-1 — `tests/integration/test_phase4_threshold_smoke.py::test_same_cve_rerun_is_rag_hit` — parametrized over the four fixtures. For each fixture, seed its `SolvedExample` into a fresh `ChromaPersistentStore` (temp dir; cleanup), build a `Query` from the same fixture's advisory + repo_ctx via the plugin's `rag_query_builder` (S7-02; or a fixture-local minimal builder if S7-02 unlanded), call `retriever.query(advisory, repo_ctx)`, assert: `isinstance(outcome, RagHit)`, `outcome.score >= 0.85 + 0.02 = 0.87`, `outcome.few_shot.id == seeded_id`.
- [ ] AC-2 — The `0.02` margin is encoded as a module-level `Final` constant `DRIFT_MARGIN = 0.02` with an inline comment citing ADR-04-0007 (drift envelope ~0.005; margin is 4× to give headroom across CI matrix). If a future ADR amendment shrinks the margin, the change is in one place.
- [ ] AC-3 — Test runs successfully under both `make test` and `pytest tests/integration/test_phase4_threshold_smoke.py --no-cov` (per project pytest config note: narrow subsets can falsely fail the `--cov-fail-under=85` gate).

### Crossing-CVE query = `RagMiss` (band-bottom assertion)

- [ ] AC-4 — `tests/integration/test_phase4_threshold_smoke.py::test_crossing_cve_query_is_rag_miss` — for each pair `(fixture_a, fixture_b)` with `a != b`, seed only `fixture_a`, query with `fixture_b.advisory`, assert: `isinstance(outcome, RagMiss)`, `outcome.reason == "top1_below_floor"`. The "below floor" is asserted by inspecting the *candidate* score (not via `outcome.score`, since `RagMiss` is bare) — capture via an event-log spy on `StoreQueried` or by mocking the classifier to expose its input. Choose the event-log approach: parametrize the test to assert that the `StoreQueried` event's max candidate score is `<= 0.65 - 0.02 = 0.63`.
- [ ] AC-5 — All `4 * 3 = 12` off-diagonal pairs are exercised (parametrized). Failure on any single pair surfaces the failing pair name in the pytest output (use `pytest.param(fixture_a, fixture_b, id=f"{a.cve_id}-vs-{b.cve_id}")`).

### Golden retrieval (deterministic across CI runs)

- [ ] AC-6 — `tests/integration/test_phase4_threshold_smoke.py::test_golden_retrieval_stable` — for one canonical fixture (`express-cve-2026-1234`), seed all four fixtures into the store, query with `express-cve-2026-1234.advisory`, dump the `RetrievalOutcome` via `outcome.model_dump_json(indent=2, sort_keys=True)`, compare byte-for-byte to `tests/golden/rag/threshold_smoke_express.json`. Modulo `outcome.score` (which is per-architecture float — see AC-7), the rest of the outcome must be byte-identical.
- [ ] AC-7 — The golden file does **not** include the exact `score` float (cross-architecture instability); instead, the golden carries `score_band: "high"`, `top1_id`, `top1_kind`. The test asserts the score *band* is identical, not the score value. AST + JSON-schema check: `tests/golden/rag/threshold_smoke_express.json` schema is `{store_digest, top1_id, top1_kind, score_band}` — no raw float.

### CI-matrix drift envelope validation

- [ ] AC-8 — `tests/integration/test_phase4_threshold_smoke.py::test_score_margin_above_drift_envelope` — for each same-CVE re-run, capture the score and assert `score >= high_floor + DRIFT_MARGIN`. The test is the empirical evidence backing ADR-04-0008's "band wider than drift" tradeoff entry. If the test passes on Linux but fails on macOS (or vice versa), the margin is too tight for the drift — surface per Global Rule 12 (the resolution is an ADR-04-0008 amendment, not a margin shrink).
- [ ] AC-9 — `tests/integration/test_phase4_threshold_smoke.py::test_crossing_cve_margin_below_degraded_floor` — for each crossing pair, capture the candidate score and assert `candidate_score <= degraded_floor - DRIFT_MARGIN = 0.63`. Symmetric to AC-8 on the lower edge.

### Fixtures + seeding

- [ ] AC-10 — Test setup uses a `pytest` fixture `seeded_smoke_store` that: (a) creates a temp `ChromaPersistentStore`, (b) bootstraps the `FastembedEmbedder` against the project-pinned `embeddings_model.lock` (CI step `codegenie embeddings bootstrap` runs once before pytest), (c) invokes `ingest_solved_example` (S4-06) for each fixture's `SolvedExample`, (d) cleans up the temp dir on test teardown. The fixture's scope is `module` (one store per test module) so the 16 parametrized cases reuse the same store — significant CI time saving.
- [ ] AC-11 — Each test asserts `RecordProvenance.verify(...)` returns `True` for every seeded record before the query — eliminates "test failed because of provenance, not because of similarity" false signals. This is a pre-condition assertion, not a separate test.
- [ ] AC-12 — If S7-05's fixture portfolio has not landed at execution time, the smoke test uses minimal local fixtures under `tests/fixtures/phase4_smoke/{express,lodash,axios,debug}.yaml` (four canonical `SolvedExample` YAML records). The minimal-local-fixture path is gated behind `if not (FIXTURES_DIR / "vuln-major-bump").exists(): use_local_fixtures()` — once S7-05 lands, this branch is dead code and a follow-up cleanup ticket removes it.

### Failure-mode honesty (Global Rule 12)

- [ ] AC-13 — On test failure, the pytest output names: (a) which fixture failed, (b) the actual score, (c) the band the score landed in, (d) the remediation path: "If this is the first failure on this fixture, the ADR-04-0008 defaults are wrong for the shipped fixtures. Amend the ADR (with the new floors + evidence-quoted scores) before merge; do NOT relax this test."
- [ ] AC-14 — The test does **not** include a `pytest.mark.xfail` or `pytest.mark.skip` modifier. The smoke test is unconditionally CI-gating. A `BLOCKED` story status amendment is the only path to skip it, with a paper trail.

### Performance + CI hygiene

- [ ] AC-15 — Total runtime of the test module ≤ 30 seconds on CI (fastembed cold start dominates; module-scoped `seeded_smoke_store` amortizes). If > 30s, surface as a Phase-4 perf regression — not a story scope edit.
- [ ] AC-16 — `codegenie embeddings bootstrap` must run before this test in CI. CI workflow file edit: ensure `make test` is preceded by the bootstrap call; document in the test docstring that local-dev runs must `python -m codegenie embeddings bootstrap` once.

## Implementation outline

```python
# tests/integration/test_phase4_threshold_smoke.py
"""Calibration smoke test — Gap 6 + ADR-04-0008.

Pins that the shipped defaults (high_floor=0.85, degraded_floor=0.65) classify
the Phase-4 fixture portfolio correctly. If this test fails, the defaults are
wrong for the shipped fixtures — Phase 4 must NOT merge until the ADR is
amended with evidence-quoted scores (not until the test is relaxed)."""

from typing import Final
import pytest

from codegenie.rag.retriever import SolvedExampleRetriever
from codegenie.rag.confidence import BandClassifier
from codegenie.rag.exclusion import EmbeddingModelMismatchFilter
from codegenie.rag.store import ChromaPersistentStore
from codegenie.rag.embedder import FastembedEmbedder
from codegenie.rag.provenance import RecordProvenance
from codegenie.fallback.fence.wrapper import FenceWrapper
from codegenie.rag.models import RagHit, RagDegraded, RagMiss

HIGH_FLOOR: Final[float] = 0.85
DEGRADED_FLOOR: Final[float] = 0.65
# Cross-architecture ONNX drift envelope is ~0.005 (ADR-04-0007).
# 4× margin gives headroom across the Linux/macOS CI matrix.
DRIFT_MARGIN: Final[float] = 0.02

FIXTURES = ["express-cve-2026-1234", "lodash-cve-2026-9876",
            "axios-cve-2026-5555",  "debug-cve-2026-7777"]


@pytest.fixture(scope="module")
def seeded_smoke_store(tmp_path_factory):
    """Module-scoped: one real chroma store, FastembedEmbedder bootstrapped
    once. All 16 parametrized tests share the seeded state."""
    tmp = tmp_path_factory.mktemp("phase4_smoke")
    store = ChromaPersistentStore(persist_dir=tmp / "chroma")
    embedder = FastembedEmbedder()  # refuse-start on lock-hash drift
    event_log = TestEventLog()
    capability = _phase4_local_capability_mint(workflow_id=WorkflowId("test"),
                                                chain_head=ChainHead("0"*64))
    for fixture in FIXTURES:
        example = load_solved_example(fixture)
        ingest_solved_example(example, store, embedder, capability)
    yield store, embedder, event_log
    store.close()


@pytest.fixture
def retriever(seeded_smoke_store):
    store, embedder, event_log = seeded_smoke_store
    classifier = BandClassifier(high_floor=HIGH_FLOOR, degraded_floor=DEGRADED_FLOOR)
    return SolvedExampleRetriever(
        store=store, embedder=embedder,
        record_provenance=RecordProvenance(),
        fence_wrapper=FenceWrapper(),
        query_builder=plugin_rag_query_builder,
        confidence_classifier=classifier,
        event_log=event_log,
        model_digest_filter=EmbeddingModelMismatchFilter(embedder, event_log),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("fixture", FIXTURES)
async def test_same_cve_rerun_is_rag_hit(retriever, fixture):
    """Roadmap exit criterion #2 ('second run hits RAG') depends on the same-CVE
    re-run scoring above high_floor. Margin of DRIFT_MARGIN guards against
    cross-architecture ONNX float drift (ADR-04-0007)."""
    advisory, repo_ctx = load_advisory_and_ctx(fixture)
    outcome = await retriever.query(advisory, repo_ctx)
    assert isinstance(outcome, RagHit), (
        f"Fixture {fixture!r}: expected RagHit, got {type(outcome).__name__}. "
        f"If this is the first failure on this fixture, the ADR-04-0008 defaults "
        f"are wrong for the shipped fixtures. Amend the ADR (with new floors + "
        f"evidence-quoted scores) before merge; do NOT relax this test."
    )
    assert outcome.score >= HIGH_FLOOR + DRIFT_MARGIN, (
        f"Score {outcome.score:.4f} is too close to high_floor={HIGH_FLOOR}; "
        f"need >= {HIGH_FLOOR + DRIFT_MARGIN:.4f} to clear the {DRIFT_MARGIN} "
        f"drift envelope. See ADR-04-0007."
    )
    assert outcome.few_shot.id == fixture_id(fixture)
```

## TDD plan — red / green / refactor

### Red — write the failing test first

```python
# (the test IS the deliverable — Step 5's load-bearing assurance)
# Write test_same_cve_rerun_is_rag_hit first; it MUST fail before any
# fixture is seeded (no records → RagMiss(reason="empty_store"), not RagHit).

@pytest.mark.asyncio
async def test_smoke_red_no_records_seeded_yet():
    """Confirm the test infrastructure produces a RED before fixtures land.
    Once S7-05 (or local fixtures from AC-12) lands and seeded_smoke_store
    runs, this test is removed and the parametrized green tests take over."""
    store = ChromaPersistentStore(persist_dir=tmp_path / "chroma")
    embedder = FastembedEmbedder()
    classifier = BandClassifier(high_floor=0.85, degraded_floor=0.65)
    retriever = SolvedExampleRetriever(
        store=store, embedder=embedder, ...
    )
    advisory, repo_ctx = load_advisory_and_ctx("express-cve-2026-1234")
    outcome = await retriever.query(advisory, repo_ctx)
    assert isinstance(outcome, RagMiss)
    assert outcome.reason == "empty_store"
```

### Green — make it pass

1. Land the `seeded_smoke_store` module-scoped fixture per the implementation outline; bootstrap the embedder; ingest all four fixtures via `ingest_solved_example`.
2. Land `test_same_cve_rerun_is_rag_hit` parametrized over `FIXTURES`. Run; if a fixture fails, the test output names the failing fixture + the actual score + the remediation path (Global Rule 12).
3. Land `test_crossing_cve_query_is_rag_miss` parametrized over the 12 off-diagonal pairs.
4. Land `test_golden_retrieval_stable` against `tests/golden/rag/threshold_smoke_express.json`. Initial golden is generated via `pytest --update-goldens` (project convention); subsequent runs assert byte-identity.
5. Land `test_score_margin_above_drift_envelope` and `test_crossing_cve_margin_below_degraded_floor`.
6. Confirm the CI workflow runs `codegenie embeddings bootstrap` before `make test`.

If any test in step 2/3 is RED at this point: **do not relax the test**. Open an ADR-04-0008 amendment proposal with the actual scores and proposed new floors. The PR includes the ADR amendment, not a test loosening.

### Refactor — clean up

- Extract the `(advisory, repo_ctx, fixture_id)` loading into a `tests/fixtures/phase4_smoke/loader.py` helper if the loading shape grows past ~5 LOC.
- Confirm the golden file is human-readable JSON (sorted keys, `indent=2`) so a future diff reviewer can read it.
- Add a docstring at the top of `test_phase4_threshold_smoke.py` quoting Gap 6 verbatim — the next reader who sees this test fail must understand it's a deliberate Phase-4-merge gate, not an over-zealous assertion.
- Verify the `DRIFT_MARGIN` constant is the only place a band-width number appears in this module; no inline `0.02` or `0.85 + 0.02` literals in test bodies.

## Files to touch

| Path | Why |
|---|---|
| `tests/integration/test_phase4_threshold_smoke.py` | NEW — the smoke test module (the deliverable). |
| `tests/fixtures/phase4_smoke/{express,lodash,axios,debug}.yaml` | NEW (conditional) — local minimal `SolvedExample` records if S7-05 has not landed. |
| `tests/fixtures/phase4_smoke/loader.py` | NEW — helper to load fixture + advisory + repo_ctx. |
| `tests/golden/rag/threshold_smoke_express.json` | NEW — golden retrieval for `express-cve-2026-1234`. |
| `tests/fixtures/phase4_smoke/conftest.py` (or extend) | NEW/EXT — `seeded_smoke_store` module-scoped fixture. |
| `.github/workflows/*.yml` (CI workflow file) | EXT — ensure `codegenie embeddings bootstrap` runs before `make test`. |
| `docs/operations/embeddings.md` (S7-10 owns; this story may stub) | EXT — note that local-dev runs require `codegenie embeddings bootstrap` once. |

## Out of scope

- **Phase-6.5 calibration harness** — this is the *smoke* test, not the *full calibration*. Phase 6.5 ships per-`(task_class, language, build_system)` calibration with labeled evidence; this story only pins the four-fixture defaults.
- **ADR-04-0008 amendment** — if the smoke test fails on merge, the amendment is a separate PR with the actual scores. This story does not pre-amend the ADR.
- **`plugin.yaml` schema** — S7-04 lands the schema. This story takes thresholds as constants in the test module (or reads them via test-local YAML); production wiring lives in S7-01.
- **Fixture portfolio creation** — S7-05 owns the canonical fixtures. This story creates a minimal-fallback set (AC-12) only if S7-05 hasn't landed at execution time.
- **Embedder-mismatch / chain-orphan paths** — S5-03 covers; this story exercises only the happy path.
- **Cassette-based integration with leaf LLM** — this is a *retrieval-only* smoke test. The LLM-side path is exercised by S7-06's E2E.

## Notes for the implementer

- **The most important test in Step 5.** A reviewer reading the Step-5 PRs should be able to point at `test_phase4_threshold_smoke.py` and ask "does this pass on CI?" — if yes, the band defaults are evidence-backed for the shipped fixtures; if no, Phase 4 doesn't merge. There is no in-between. Treat it as the merge gate.
- **The drift envelope is empirical.** ADR-04-0007 says "drift ~0.005 at the 5th decimal," but the smoke test running on the CI matrix is where that claim is *empirically validated*. If the test passes on Linux but fails on macOS, the 0.005 estimate is wrong. Surface per Global Rule 12 — don't shrink `DRIFT_MARGIN` to make the test pass; widen the *band* (degraded_floor lower, high_floor higher) via ADR amendment, or accept that BGE-small is too unstable for this corpus and surface the architectural problem.
- **Why `score_band` in the golden, not `score`.** Cross-architecture float instability would make a raw-`score` golden flake every other CI run; pinning the *band* (and asserting the score is in that band with margin) is the stable contract.
- **Module-scoped `seeded_smoke_store` is load-bearing.** Each `FastembedEmbedder()` construction loads ~180 MB of ONNX into RSS and ~500 ms cold-start. Sixteen test cases × 500 ms × N retries = test module timeout territory. Module scope amortizes; **don't** rewrite to function scope without a perf justification.
- **The xfail/skip prohibition (AC-14) is intentional.** A future engineer encountering a flaky smoke test will be tempted to `xfail` "until Phase 6.5 lands." That is the failure mode this story exists to prevent. If the test is genuinely flaky, the resolution is *fix the flakiness* (margin widening via ADR amendment, fixture re-engineering, or BLOCKED-PARTIAL story amendment with paper trail) — not a skip marker.
- **Fixture availability sequencing.** S7-05 may not have landed when this story executes. AC-12 prescribes a local-minimal fallback under `tests/fixtures/phase4_smoke/`. Once S7-05 lands, those local fixtures become dead code; the cleanup is in S7-05's PR (or a follow-up). Document the dependency explicitly in this story's `_attempts/` log.
- **The `codegenie embeddings bootstrap` precondition.** Without it, `FastembedEmbedder.__init__` refuses to start (lock-hash mismatch). CI must run the bootstrap once and cache the model weights. Verify the workflow file edits this before merging this story — a CI-green run is the only evidence that the smoke test actually executes against real embeddings, not a mock.
- **Failure messages quote the remediation path.** AC-13's failure-message template is the load-bearing UX for the next engineer who breaks the smoke test. The template includes: which fixture, what score, what band, and *what to do* (amend the ADR, not the test). Get the wording right.
- **`async`/`pytest-asyncio`.** Project pytest config has `asyncio_mode = "auto"`, so `async def test_...` works without `@pytest.mark.asyncio`. The implementation outline uses the marker for clarity; if the project convention is unmarked, follow the project convention.
- **`--no-cov` for local subset runs.** The project's `--cov-fail-under=85` `addopts` will false-fail a narrow `pytest tests/integration/test_phase4_threshold_smoke.py` run. Document in the test docstring: "local runs: `pytest tests/integration/test_phase4_threshold_smoke.py --no-cov`."
