# Story S7-03 — Recall@3 ≥ 0.85 + perf canaries (G6/G7/G8) + nightly cost canary

**Step:** Step 7 — Harden — adversarial corpus, recall@3, perf canaries, E2E exit criterion, Phase-3 regression, Phase-5 handoff, CI gates
**Status:** Ready
**Effort:** L
**Depends on:** S7-01
**ADRs honored:** ADR-P4-005, ADR-P4-006, ADR-P4-007, ADR-P4-009, ADR-P4-010

## Context

This story turns Phase 4's measurable goals (G6/G7/G8/G13) into merge-gating canaries. Recall@3 ≥ 0.85 against the 30 labeled-triples fixture (S7-01) audits the embedding-model + query-text construction + metadata-filter chain in one assertion. The three perf canaries lock the latency contracts: tier-1 query-key cache replay ≤ 5 ms p95 (G8), selector chain tier-1-miss → tier-2-hit ≤ 250 ms p95 (G7), LLM-cold cassette-replayed E2E ≤ 180 s p95 (G6). The nightly cost canary recomputes $/PR across the fixture portfolio against cassette-replayed token counts and fails CI if it drifts > 10% vs baseline. Two property tests round out the planner totality + trust-score strict-AND invariants.

## Context for failure modes: the recall@3 canary is the single highest-value-per-LOC test in the phase — it catches embedding-model drift, query-text construction drift, and metadata-filter drift simultaneously.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Performance regression tests"` — names every canary file, with the metric and budget per goal (G6/G7/G8).
  - `../phase-arch-design.md §"Property tests (Hypothesis)"` — `test_planner_is_total.py` and `test_trust_score_strict_and_phase4.py` invariants.
  - `../phase-arch-design.md §"Goals"` G6/G7/G8/G13 — concrete budget numbers.
  - `../phase-arch-design.md §"CI gates"` — `recall_at_k_canary` and `nightly_cost_canary` are merge gates; this story authors them, S7-06 wires the gating.
- **Phase ADRs:**
  - `../ADRs/0005-chromadb-in-process-with-stale-lock-detection.md` — ADR-P4-005; the store the recall canary queries.
  - `../ADRs/0006-bge-small-en-embedding-model-sha-pinned.md` — ADR-P4-006; query-time digest filter (Gap 2) is the recall canary's load-bearing dependency.
  - `../ADRs/0007-anthropic-model-pin-via-versioned-alias.md` — ADR-P4-007; cassette + model pin underpin the cost-canary token counts.
  - `../ADRs/0009-prompts-as-versioned-yaml-data.md` — ADR-P4-009; prompt-cache breakpoint layout golden test depends on stable rendered system block.
  - `../ADRs/0010-llm-invocation-guard-running-total-with-override.md` — ADR-P4-010; cost-canary reads the cost-ledger this guard emits.
- **Source design:** `../final-design.md §"Performance canaries (CI-gated)"` — original four-test plan, plus the cost-canary's 10% drift threshold.
- **Existing code:**
  - `src/codegenie/rag/store.py` (S4-04) — `SolvedExampleStore.query` is what recall@3 measures.
  - `src/codegenie/planner/fallback_tier.py` (S5-01) — the selector chain the p95 canary times.
  - `src/codegenie/planner/query_key_cache.py` (S4-05) — the tier-1 cache the 5 ms canary times.
  - `src/codegenie/llm/cost_emitter.py` (S2-04 / S3-01) — `cost-ledger.jsonl` writer the cost canary reads.
  - `src/codegenie/recipes/engines/rag_llm.py` (S5-02) — the end-to-end engine the LLM-cold wall-clock canary drives.
  - `tests/fixtures/rag_labeled/` (S7-01) — 30 triples corpus.
  - `tests/fixtures/seeded_chromadb/size_100/` (S7-01) — the store the recall canary loads.
  - `tests/fixtures/cassettes/` (S7-01) — LLM-cold wall-clock canary's cassettes.

## Goal

Author the four perf canaries, the recall@3 canary, the prompt-cache breakpoint-layout golden, the nightly cost canary, and the two property tests — all merge-gating under the `recall_at_k_canary`/`nightly_cost_canary` CI lights S7-06 wires.

## Acceptance criteria

- [ ] `tests/canaries/test_rag_retrieval_recall_at_k.py` green: loads all 30 triples from `tests/fixtures/rag_labeled/`; queries `seeded_store_100`; reports recall@3; asserts ≥ **0.85** (G13). Fails loudly with per-triple miss diagnostics on regression.
- [ ] `tests/canaries/test_selector_chain_p95_under_250ms.py` green: 100 iterations of tier-1-miss → tier-2-hit through a warm-embed worker against `seeded_store_50`; asserts **p95 ≤ 250 ms** (G7). Reports p50/p95/p99 on failure.
- [ ] `tests/canaries/test_query_key_replay_under_5ms.py` green: 1000 iterations of tier-1 hits against a pre-warmed `QueryKeyCache`; asserts **p95 ≤ 5 ms** (G8). 1000 iterations is the sample size required to make 5 ms p95 statistically stable.
- [ ] `tests/canaries/test_e2e_llm_path_under_180s.py` green: cassette-replayed LLM-cold path against an empty seeded store; runs 5 iterations (cassette ensures byte-stable replay); asserts **p95 ≤ 180 s** (G6). Cassette-replayed wall-clock includes embed-overlap latency.
- [ ] `tests/canaries/test_prompt_cache_breakpoint_layout.py` green: golden on rendered system-block bytes for the frozen `prompts/system.v1.yaml` fixture; CI red on byte-level drift — closes Edge case #21 (legitimate edits land via `cassettes-reviewed` PR + golden re-record).
- [ ] `tests/canaries/test_nightly_cost_canary.py` runs nightly (also runnable on-demand): replays the full cassette portfolio's token counts; computes $/PR; compares to baseline in `tests/canaries/baseline_cost_per_pr.json`; asserts **drift ≤ 10%** vs baseline (G6 cost discipline).
- [ ] `tests/property/test_planner_is_total.py` green: Hypothesis-driven; any well-formed `(advisory, repo_ctx, recipe_selection)` produces a `RecipeApplication` (success or typed error); the planner never raises.
- [ ] `tests/property/test_trust_score_strict_and_phase4.py` green: any-false Phase-4 signal (`rag.top1_cosine`, `llm.output_passes_schema_validator`, `llm.output_passes_canary`, `llm.tokens_used ≤ budget`) → low confidence; strict-AND invariant.
- [ ] All canaries fail with **a structured diagnostic payload** (JSON written to `tests/canaries/_last_run.json` on failure) so the CI summary surfaces the exact regression dimension.
- [ ] TDD red test exists, committed, green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict` on `tests/canaries/` + `tests/property/` clean.
- [ ] `pytest tests/canaries/ tests/property/` green offline.

## Implementation outline

1. Author `tests/canaries/_harness.py` with a `percentile(values: list[float], p: float) -> float` helper, a `Timer` context manager, and a `write_diagnostic(payload: dict)` writer (so every canary failure produces `tests/canaries/_last_run.json` for CI summary).
2. **Recall test** loads `LabeledTriple` rows via `tests.fixtures.rag_labeled.loader.load_all()`; opens `seeded_store_100`; for each triple runs `store.read().query(query_text=t.query_text, k=3)`; counts hits where `t.expected_top1_id ∈ ids[:3]`; asserts `hits / 30 ≥ 0.85`.
3. **Selector p95 canary** uses `pytest-benchmark` is not required — manual `time.perf_counter_ns()` works fine; 100 iterations, warm the embed worker first, then loop. Time only the selector chain (`FallbackTier.select(...)` against a tier-1-miss-tier-2-hit fixture).
4. **Query-key replay canary** pre-warms `QueryKeyCache` with one entry, then loops 1000 times; the value is read-only `dict`-style; assert all reads under 5 ms p95.
5. **LLM-cold E2E canary** runs against the `test_e2e_major_version_breaking_change.py` cassette (or its sibling) but only times wall-clock; 5 iterations is enough because the cassette replay is deterministic — the variance is process-spawn + flock + chromadb cold-open.
6. **Prompt-cache golden** loads `prompts/system.v1.yaml`, renders against a frozen context (`tests/fixtures/prompt_cache_golden/context.json`), bytes-compared against `tests/golden/prompts/system.v1.rendered.bytes` (raw bytes, not str — newline discipline matters).
7. **Cost canary** is the longest: open every cassette under `tests/fixtures/cassettes/`; extract `input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`; compute $/call using the model-rate constants in `src/codegenie/llm/cost_emitter.py`; average across the fixture portfolio for $/PR; compare to baseline.
8. **Property tests** use Hypothesis strategies for the planner's input types (mirror the Pydantic schemas).
9. Write `tests/canaries/README.md` documenting how to re-baseline the cost canary (it's an ADR-amendment-gated operation; not a "just bump it" workflow).
10. Ensure each canary writes its diagnostic JSON on failure, not on success (don't churn the repo).

## TDD plan — red / green / refactor

### Red

`tests/canaries/test_rag_retrieval_recall_at_k.py`

```python
def test_recall_at_3_on_thirty_labeled_triples(seeded_store_100):
    """G13: recall@3 ≥ 0.85 against the labeled corpus. This single test catches
    embedding-model drift, query-text construction drift, and metadata-filter
    drift in one pass — the highest value-per-LOC assertion in Phase 4."""
    from tests.fixtures.rag_labeled.loader import load_all
    from tests.canaries._harness import write_diagnostic

    triples = load_all()
    hits, misses = 0, []
    with seeded_store_100.read() as store:
        for t in triples:
            results = store.query(query_text=t.query_text, k=3)
            top3_ids = [r.id for r in results]
            if t.expected_top1_id in top3_ids:
                hits += 1
            else:
                misses.append({
                    "query": t.query_text,
                    "expected_top1": t.expected_top1_id,
                    "got_top3": top3_ids,
                })

    recall = hits / len(triples)
    if recall < 0.85:
        write_diagnostic({"recall_at_3": recall, "misses": misses})
    assert recall >= 0.85, f"recall@3={recall:.3f} < 0.85; {len(misses)} misses"
```

`tests/canaries/test_query_key_replay_under_5ms.py`

```python
def test_query_key_replay_p95_under_5ms(tmp_path):
    """G8: 1000 iterations of tier-1 cache reads p95 ≤ 5ms. 1000 is the
    sample size that makes 5ms p95 statistically meaningful — fewer
    iterations and the tail is noise."""
    import time
    from codegenie.planner.query_key_cache import QueryKeyCache
    from tests.canaries._harness import percentile, write_diagnostic

    cache = QueryKeyCache(root=tmp_path)
    cache.put(qk="abc123", plan_payload={"kind": "recipe_invocation"})

    latencies_ms: list[float] = []
    for _ in range(1000):
        t0 = time.perf_counter_ns()
        _ = cache.get(qk="abc123")
        latencies_ms.append((time.perf_counter_ns() - t0) / 1_000_000.0)

    p95 = percentile(latencies_ms, 0.95)
    if p95 > 5.0:
        write_diagnostic({
            "p50": percentile(latencies_ms, 0.50),
            "p95": p95,
            "p99": percentile(latencies_ms, 0.99),
        })
    assert p95 <= 5.0, f"query-key replay p95={p95:.2f}ms > 5ms"
```

`tests/property/test_planner_is_total.py`

```python
from hypothesis import given, strategies as st

@given(
    advisory=st.builds(...),       # mirror Advisory Pydantic
    repo_ctx=st.builds(...),       # mirror RepoContext Pydantic
    selection=st.builds(...),      # mirror RecipeSelection (fallback shapes)
)
def test_planner_never_raises(advisory, repo_ctx, selection):
    """Any well-formed input must produce a RecipeApplication, success or
    typed error, never an unhandled exception. The planner is total."""
    from codegenie.planner.fallback_tier import FallbackTier
    from codegenie.recipes.types import RecipeApplication

    result = FallbackTier.select(advisory, repo_ctx, selection)
    assert isinstance(result, RecipeApplication)
```

`tests/canaries/test_nightly_cost_canary.py`

```python
def test_cost_per_pr_drift_within_10pct():
    """G6: $/PR ≤ $0.08 with ≥80% prompt-cache hit rate. The canary replays
    the cassette portfolio's token counts and compares to the committed
    baseline; >10% drift fails CI. Re-baselining is an ADR-amendment workflow,
    not 'just bump the number'."""
    import json
    from pathlib import Path
    from tests.canaries._cost import compute_dollars_per_pr_from_cassettes
    from tests.canaries._harness import write_diagnostic

    baseline = json.loads(Path("tests/canaries/baseline_cost_per_pr.json").read_text())
    current = compute_dollars_per_pr_from_cassettes(Path("tests/fixtures/cassettes/"))

    drift = abs(current["dollars_per_pr"] - baseline["dollars_per_pr"]) / baseline["dollars_per_pr"]
    if drift > 0.10:
        write_diagnostic({
            "baseline": baseline,
            "current": current,
            "drift_pct": drift * 100,
        })
    assert drift <= 0.10, f"cost drift {drift*100:.1f}% > 10% vs baseline"
    assert current["dollars_per_pr"] <= 0.08, f"$/PR = ${current['dollars_per_pr']:.3f} > $0.08"
    assert current["cache_hit_rate"] >= 0.80, f"cache hit {current['cache_hit_rate']*100:.1f}% < 80%"
```

(Analogous failing tests for `test_selector_chain_p95_under_250ms.py`, `test_e2e_llm_path_under_180s.py`, `test_prompt_cache_breakpoint_layout.py`, `test_trust_score_strict_and_phase4.py`.)

### Green

For each canary: thin shim against the already-shipped component (`SolvedExampleStore`, `QueryKeyCache`, `FallbackTier`, `RagLlmEngine`, `PromptLoader`). The work is mostly fixture-loading + percentile math, not new production code.

Commit `tests/canaries/baseline_cost_per_pr.json` with the initial baseline computed from the first cassette portfolio (the value lands when the cassettes do; it's a one-shot calibration step).

### Refactor

- Extract the percentile + diagnostic-writer helpers into `tests/canaries/_harness.py`.
- The cost-canary's token-count parsing belongs in `tests/canaries/_cost.py`, not inlined.
- Each canary gets a one-line `pytest.mark` (`@pytest.mark.canary`, `@pytest.mark.slow` for the LLM-cold E2E) so CI can route them onto the right runners.
- Property tests get explicit `@settings(max_examples=200, deadline=None)` to make the runtime bounded.
- Document the baseline-update workflow in `tests/canaries/README.md` (ADR-amendment-gated, not a freeform PR).

## Files to touch

| Path | Why |
|---|---|
| `tests/canaries/_harness.py` | `percentile`, `Timer`, `write_diagnostic`. |
| `tests/canaries/_cost.py` | Cassette token-count → $/PR computation. |
| `tests/canaries/test_rag_retrieval_recall_at_k.py` | G13 recall@3. |
| `tests/canaries/test_selector_chain_p95_under_250ms.py` | G7 selector p95. |
| `tests/canaries/test_query_key_replay_under_5ms.py` | G8 tier-1 replay p95. |
| `tests/canaries/test_e2e_llm_path_under_180s.py` | G6 LLM-cold p95. |
| `tests/canaries/test_prompt_cache_breakpoint_layout.py` | Prompt-cache golden. |
| `tests/canaries/test_nightly_cost_canary.py` | $/PR drift gate. |
| `tests/canaries/baseline_cost_per_pr.json` | Cost baseline (initial calibration). |
| `tests/canaries/README.md` | Re-baseline workflow docs. |
| `tests/property/test_planner_is_total.py` | Hypothesis — planner totality. |
| `tests/property/test_trust_score_strict_and_phase4.py` | Hypothesis — strict-AND. |
| `tests/golden/prompts/system.v1.rendered.bytes` | Prompt-cache golden bytes. |
| `tests/fixtures/prompt_cache_golden/context.json` | Frozen prompt-render context. |

## Out of scope

- **CI gate wiring** — S7-06 wires `recall_at_k_canary` and `nightly_cost_canary` as merge-blocking jobs.
- **`pytest-benchmark`** — explicitly not adopted (extra dep, larger surface than needed; `time.perf_counter_ns` + percentile is sufficient).
- **Tracing the cause of any specific recall miss** — diagnostic JSON exists for the next engineer to triage; this story doesn't fix recall, only asserts the floor.
- **Cassette re-record on token-rate change** — runbook workflow in S7-06.
- **Live-Anthropic call canary** — Phase 4 cost canary is offline-only; nightly Anthropic ping is in `../final-design.md §"VCR cassette discipline"` "cassette freshness" — that lands in S7-06 or later.
- **Mutation testing on the canary suite** — out of phase scope; consider for Phase 13 maturity.

## Notes for the implementer

- The 1000-iteration count for the query-key replay canary is **not arbitrary** — fewer iterations make p95 noisy enough that a real regression hides under variance. Don't drop to 100 to make CI faster; if the canary is too slow, profile the cache, don't shrink the sample.
- Per Rule 12 (fail loud): every canary writes a diagnostic JSON **on failure only**. Don't write on success — it churns the working tree on every CI run. The diagnostic must be the **minimum** payload that lets the next engineer triage without rerunning: percentile distribution, top-5 misses, etc.
- The recall@3 fixture is hand-constructed (S7-01) and the floor is 0.85. If recall *drops to 0.84*, the fix is not to lower the threshold — it's to either (a) reindex against the current pinned model (Gap 2 workflow) or (b) propose an ADR amendment + quarterly rotation per `../final-design.md` row "30 labeled-triples corpus rotation policy". Lowering the threshold silently is a Rule-12 violation.
- The cost canary's baseline lives in JSON, not YAML, because diff-noise is structural in YAML and we want diffs to be 1-line numeric. Re-baselining is human-reviewed.
- The prompt-cache golden compares **bytes**, not strings — newline / encoding drift is exactly the kind of subtle regression that breaks Anthropic's prefix-cache hits without breaking semantics. The golden is the canary for that class of bug (Edge case #21).
- The `test_e2e_llm_path_under_180s.py` 5-iteration sample size is intentional. The cassette replay is deterministic; the variance is process-spawn + flock + chromadb cold-open. 5 iterations × cold-start is enough to surface a regression; more is unnecessary and makes the suite slower.
- The two property tests are deliberately separate files because they exercise different invariants — keep them that way for traceability against the exit-criteria mapping in `../High-level-impl.md §"Exit-criteria mapping"`.
- Don't import `anthropic` from this story's files — the perf canaries replay cassettes through `LeafLlmAgent`, the cost canary parses cassette YAML directly. Fence-CI (S1-07) will reject `anthropic` imports here.
