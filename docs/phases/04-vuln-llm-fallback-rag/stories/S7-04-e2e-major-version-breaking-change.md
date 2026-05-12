# Story S7-04 — E2E `test_e2e_major_version_breaking_change.py` — the roadmap exit criterion

**Step:** Step 7 — Harden — adversarial corpus, recall@3, perf canaries, E2E exit criterion, Phase-3 regression, Phase-5 handoff, CI gates
**Status:** Ready
**Effort:** L
**Depends on:** S6-03, S7-01, S6-04
**ADRs honored:** ADR-P4-001, ADR-P4-002, ADR-P4-003, ADR-P4-004, ADR-P4-007, ADR-P4-008, ADR-P4-010, ADR-P4-012, ADR-P4-015

## Context

This is **the single most-load-bearing test in Phase 4**. The roadmap exit criterion reads: *"A breaking-change vuln (e.g., a major-version-bump CVE) is solved end-to-end with the LLM fallback and recorded into the solved-example store. Re-running the same case hits RAG, not LLM, and produces an equivalent fix at lower cost."* This story lands the cassette-recorded E2E that verifies all three clauses in one fixture — run 1 takes the LLM-cold path against an empty store, writes back a `SolvedExample`, and produces a green branch; run 2 with the same `lockfile_blake3` hits the tier-1 query-key cache in p95 ≤ 5 ms, makes zero LLM calls, and produces an **equivalent** diff. Merges block on this fixture being green on both runs.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Testing strategy" → "Test pyramid" → "E2E"` — names the exit-criterion fixture as the one E2E.
  - `../phase-arch-design.md §"Scenarios — 4 representative" → "S1 / S2 / S3"` — sequence diagrams for tier-1 / tier-2 / tier-3 paths; this fixture exercises S2/S3 (cold) on run 1 and S1 (cache hit) on run 2.
  - `../phase-arch-design.md §"Gap 1"` — `rag_exact` fires only on `Plan.kind=="recipe_invocation"`; manual_patch diffs from a different repo re-route to fewshot-LLM. This shapes the run-2 cost-equivalence assertion (writeback wrote a `Plan` with the right `kind`).
  - `../phase-arch-design.md §"Goals"` G1 (exit criterion verified), G2 (re-run hits RAG zero LLM cost), G6 (LLM-cold ≤ 180 s p95), G8 (tier-1 ≤ 5 ms p95).
  - `../phase-arch-design.md §"Edge cases"` rows 14 (worker crashes between trust-pass and writeback) and row "lockfile_blake3 drift" — both must NOT trip in the happy path this fixture asserts.
- **Phase ADRs:**
  - `../ADRs/0001-recipe-engine-literal-extends-with-rag-llm.md` — ADR-P4-001; `rag_llm` is the engine used on the LLM-cold run.
  - `../ADRs/0002-two-tier-writeback-pending-promoted.md` — ADR-P4-002; the writeback that makes run 2 cheap.
  - `../ADRs/0003-plan-envelope-kind-and-target-files-allowlist.md` — ADR-P4-003; `target_files` allowlist (manifest+lockfile only) makes the CVE fit within Phase-4 scope.
  - `../ADRs/0007-anthropic-model-pin-via-versioned-alias.md` — ADR-P4-007; model pin underpins the cassette stability.
  - `../ADRs/0010-llm-invocation-guard-running-total-with-override.md` — ADR-P4-010; cost-ledger entries the test asserts on.
  - `../ADRs/0012-vcr-cassette-discipline.md` — ADR-P4-012; cassette recording + canary-rewrite-on-replay.
  - `../ADRs/0015-solved-example-schema-task-class-generic.md` — ADR-P4-015; `SolvedExample v0.4.0` row the writeback creates.
- **Production ADRs:**
  - `docs/production/adrs/0011-recipe-rag-llm-decision-chain.md` — the production-level shape this test verifies at a Phase-4-sized scope.
- **Source design:**
  - `../final-design.md §"Data flow" → "Scenario B: RAG miss → LLM → writeback"` — sequence for run 1.
  - `../final-design.md §"Data flow" → "Scenario A: RAG hit"` — sequence for run 2.
  - `../final-design.md §"Exit-criteria checklist"` — clause-by-clause mapping; this test is the consolidator.
- **Existing code:**
  - `src/codegenie/recipes/engines/rag_llm.py` (S5-02) — the three-tier `apply()` the run drives.
  - `src/codegenie/rag/writeback.py` (S6-01) — the writeback path that makes run 2 cheap.
  - `src/codegenie/orchestrator/remediate.py` (S6-03, S1-05) — the orchestrator that S7-04 invokes end-to-end.
  - `tests/fixtures/seeded_chromadb/empty/` (S7-01) — the store run 1 starts against.
  - `tests/fixtures/cassettes/` (S7-01) — where the test's cassette lands.

## Goal

Land `tests/e2e/test_e2e_major_version_breaking_change.py` — a cassette-driven two-run E2E against a `react-router@5 → @6`-shaped CVE fixture — that hard-asserts (1) run 1 LLM-cold succeeds end-to-end with a green branch, (2) run 2 with the same `lockfile_blake3` hits tier-1 in p95 ≤ 5 ms with **zero** Anthropic requests, and (3) the diffs from run 1 and run 2 are **equivalent** (G1+G2).

## Acceptance criteria

- [ ] `tests/e2e/test_e2e_major_version_breaking_change.py` exists with two run assertions and is marked merge-gating (`@pytest.mark.exit_criterion`).
- [ ] **Run 1 assertions:** orchestrator exits 0; `engine_used="rag_llm"`; `plan_source="llm_cold"`; `Plan.kind` ∈ {`recipe_invocation`, `manual_patch`} (whichever the cassette returns — both valid for Phase 4); `Plan.target_files ⊆ {package.json, package-lock.json, yarn.lock, pnpm-lock.yaml, npm-shrinkwrap.json}` (ADR-P4-003); `npm ci` + `npm test` pass on the post-apply tree; a `SolvedExample` row was written to `.codegenie/rag/solved-examples/` with `merge_status="pending"` (ADR-P4-002); `cost-ledger.jsonl` records exactly one `cost.llm.invoked` event; the canary token was echoed (`Plan.canary_echo == ` the minted canary).
- [ ] **Run 2 assertions:** same orchestrator invocation against the same fixture (same `lockfile_blake3`); exits 0; **zero** Anthropic requests recorded (cassette interaction count == 0); `engine_used="rag_llm"`, `plan_source="query_cache"`; per-run wall-clock ≤ 5 ms on the selector chain (consume p95 from canary harness) OR a direct timing assertion ≤ 50 ms total run-budget; `cost-ledger.jsonl` has zero new `cost.llm.invoked` events; **no new** `SolvedExample` row was written (ADR-P4-002 writeback skipped on `plan_source="query_cache"`).
- [ ] **Equivalence assertion:** the post-apply diffs from run 1 and run 2 are byte-identical OR satisfy a documented `is_equivalent_diff(diff1, diff2) -> bool` helper that allows lockfile-ordering-only differences (which are semantic no-ops). The chosen path is documented in the fixture README.
- [ ] If no real CVE fits the "breaking-change npm CVE resolvable with `package.json` + lockfile only" shape, a synthetic CVE fixture is constructed under `tests/fixtures/repos/cve-breaking-change-major-bump/` with **explicit documentation** in `tests/fixtures/repos/cve-breaking-change-major-bump/README.md` covering (a) why synthetic, (b) what real CVE shape it mimics, (c) the fix Phase 4 produces.
- [ ] Cassette under `tests/fixtures/cassettes/test_e2e_major_version_breaking_change/run_1.yaml` committed under `cassettes-reviewed` label workflow; `before_record_response` canary-rewrite hook from S3-06 applied.
- [ ] The fixture repo's working tree post-run-1 differs from pre-run by exactly the manifest+lockfile delta (no other file modified — re-asserts the G3 action-surface invariant at exit-criterion level).
- [ ] TDD red test exists, committed, green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict` on the test + helpers clean.
- [ ] `pytest tests/e2e/test_e2e_major_version_breaking_change.py --record-mode=none` green offline; integrated into the merge gate per S7-06.

## Implementation outline

1. Build the fixture repo `tests/fixtures/repos/cve-breaking-change-major-bump/` — a minimal Node project with `package.json` pinning a deliberately-vulnerable major version of `react-router` (or, if synthetic, a similar-shaped peer-dep), the matching `package-lock.json`, and a passing `npm test` baseline. Commit a `README.md` documenting the chosen shape and any synthetic-fixture justification.
2. Write the test as **one** function `test_breaking_change_exit_criterion` that runs the orchestrator twice against a `tmp_path` copy of the fixture; do not split into two test functions (the second run **depends on** the first; pytest's isolation would invalidate the assertion).
3. Record `run_1.yaml` once locally with `pytest --record-mode=once`; commit through the `cassettes-reviewed` label gate.
4. The "equivalence" check is the subtle part: lockfile reorderings are real and benign. Implement `tests/e2e/_diff_equivalence.py` with `is_equivalent_diff(d1, d2) -> bool` that normalizes lockfile JSON by `(name, version)` tuples before comparing; document the normalization rules in the helper docstring.
5. Wire the assertion that the post-apply diff modifies **only** files inside the npm-manifest+lockfile allowlist (re-uses `NpmPathAllowlistProvider` from S1-08; do not hard-code the list).
6. Run 1's writeback is synchronous (per ADR-P4-002); assert the `SolvedExample` row is queryable via `SolvedExampleStore.read().query(query_text=...)` immediately after run 1 returns; this is the contract run 2 depends on.
7. For run 2, capture cassette interactions via a `pytest-recording` matcher that fails the test if any recorded request is replayed (cassette interaction-count must be 0 for run 2).
8. Mark the test `@pytest.mark.exit_criterion` so S7-06 can wire it as a separate merge-gating job.
9. On any failure, write a diagnostic dump under `tests/e2e/_last_run_diagnostics.json` (analogous to S7-03's canaries).

## TDD plan — red / green / refactor

### Red

`tests/e2e/test_e2e_major_version_breaking_change.py`

```python
import pytest

@pytest.mark.exit_criterion
def test_breaking_change_exit_criterion(tmp_path, seeded_store_empty_factory,
                                         orchestrator_factory, cassette,
                                         audit_events, recorded_anthropic_requests):
    """The roadmap exit criterion. One fixture, two runs, three assertions:
    (1) LLM-cold path succeeds end-to-end on an empty store and writes back;
    (2) re-run with same lockfile_blake3 hits tier-1, zero LLM cost;
    (3) diffs from run 1 and run 2 are equivalent.

    This is the single load-bearing test in Phase 4. Merges block on it."""
    import shutil
    from pathlib import Path
    from tests.e2e._diff_equivalence import is_equivalent_diff

    # --- arrange: copy the breaking-change fixture into a tmp tree
    fixture = Path("tests/fixtures/repos/cve-breaking-change-major-bump")
    repo = tmp_path / "repo"
    shutil.copytree(fixture, repo)
    store_dir = tmp_path / "rag" / "solved-examples"
    seeded_store_empty_factory(store_dir)

    pre_tree = _hash_worktree(repo)
    orchestrator = orchestrator_factory(repo, store_dir)

    # --- run 1: LLM-cold
    with cassette("test_e2e_major_version_breaking_change/run_1.yaml"):
        result1 = orchestrator.remediate(advisory_id="GHSA-fixture-breaking")
    diff_1 = _capture_branch_diff(repo)

    assert result1.exit_code == 0
    assert result1.engine_used == "rag_llm"
    assert result1.plan_source == "llm_cold"
    assert set(result1.plan.target_files).issubset({
        "package.json", "package-lock.json", "yarn.lock",
        "pnpm-lock.yaml", "npm-shrinkwrap.json",
    }), f"target_files leaked outside allowlist: {result1.plan.target_files}"
    invoked = [e for e in audit_events() if e["event"] == "cost.llm.invoked"]
    assert len(invoked) == 1, f"expected exactly one LLM invocation, got {len(invoked)}"
    written = [e for e in audit_events() if e["event"] == "solved_example.written"]
    assert len(written) == 1
    assert written[0]["merge_status"] == "pending"

    post_run1_tree = _hash_worktree(repo)
    assert pre_tree != post_run1_tree, "run 1 modified nothing"

    # reset the repo tree but keep the rag store so run 2 sees the writeback
    shutil.rmtree(repo)
    shutil.copytree(fixture, repo)

    # --- run 2: same lockfile_blake3 → tier-1 cache hit
    audit_events.reset()
    recorded_anthropic_requests.reset()
    with cassette("test_e2e_major_version_breaking_change/run_1.yaml"):
        result2 = orchestrator.remediate(advisory_id="GHSA-fixture-breaking")
    diff_2 = _capture_branch_diff(repo)

    assert result2.exit_code == 0
    assert result2.engine_used == "rag_llm"
    assert result2.plan_source == "query_cache"
    assert recorded_anthropic_requests.count == 0, \
        f"run 2 made {recorded_anthropic_requests.count} anthropic calls; expected 0"
    new_invoked = [e for e in audit_events() if e["event"] == "cost.llm.invoked"]
    assert new_invoked == [], "run 2 emitted a cost.llm.invoked event"
    new_written = [e for e in audit_events() if e["event"] == "solved_example.written"]
    assert new_written == [], "run 2 wrote a duplicate SolvedExample"

    # --- equivalence
    assert is_equivalent_diff(diff_1, diff_2), \
        "run 1 and run 2 produced non-equivalent diffs — G1 violated"
```

### Green

Wire the test against the orchestrator + cassette helpers already shipped in S6-03 / S3-06. Build the synthetic CVE fixture if no real CVE fits. Record run_1.yaml locally and commit it under `cassettes-reviewed`.

`tests/e2e/_diff_equivalence.py` lands with the `is_equivalent_diff(d1, d2)` helper — its docstring spells out the normalization rules (sort lockfile entries by `(name, resolved_version)`, ignore key-order in JSON objects).

### Refactor

- Hoist `_hash_worktree` and `_capture_branch_diff` into `tests/e2e/conftest.py`.
- Add a fixture-level docstring describing the threat-model coverage: G1, G2, G3 (via the allowlist subset assertion), G6 (the perf canary owns the tighter assertion), ADR-P4-002 (writeback skipped on query_cache).
- Add a flake-resistance pre-check: assert the embed sidecar is responsive **before** run 1; skip with a clear message if the sidecar isn't up (the test isn't useful in that case and shouldn't false-negative).
- The diagnostic JSON written on failure should include: pre/post tree hashes, audit-event list, recorded-anthropic-request count, both diffs.

## Files to touch

| Path | Why |
|---|---|
| `tests/e2e/test_e2e_major_version_breaking_change.py` | The exit-criterion test. |
| `tests/e2e/_diff_equivalence.py` | `is_equivalent_diff(d1, d2)` helper + docs. |
| `tests/e2e/conftest.py` | Shared `_hash_worktree`, `_capture_branch_diff`, `recorded_anthropic_requests` fixture. |
| `tests/fixtures/repos/cve-breaking-change-major-bump/{package.json,package-lock.json,test/...}` | Synthetic-or-real CVE fixture repo. |
| `tests/fixtures/repos/cve-breaking-change-major-bump/README.md` | Synthetic justification + real-CVE shape it mimics. |
| `tests/fixtures/cassettes/test_e2e_major_version_breaking_change/run_1.yaml` | The single recorded cassette (under `cassettes-reviewed`). |

## Out of scope

- **The perf-level `≤ 180 s` / `≤ 5 ms` assertions** — owned by S7-03 canaries; this story owns correctness, not the latency budget.
- **Phase-3 regression sweep** — S7-05 (`test_phase3_unchanged.py`).
- **Phase-5 handoff snapshot** — S7-05 (`test_phase5_handoff_contract.py`).
- **A real GitHub PR / webhook-driven promotion** — Phase 11. Run 1's writeback lands `merge_status="pending"`; we do not assert promotion.
- **Cassette re-record workflow** — runbook content in S7-06.
- **Equivalence for non-lockfile-only diffs** — the helper's domain is npm manifest+lockfile only; if a future CVE breaks that boundary the test is out of scope per G3 / NG1.

## Notes for the implementer

- This test is **load-bearing**. Per Rule 12 (fail loud), every assertion must be specific — "the cassette interaction count is 0" is the right shape; "no LLM was called" is the wrong one. The first is observable; the second is unverifiable from inside the test process.
- The fixture must be a **breaking-change** CVE shape — minor or patch bumps are not the exit criterion. If synthetic, the README must explain *which* real CVE shape it mimics (e.g. `react-router@5 → @6` requires `Switch → Routes` source-code edits in real code, but this fixture stages a scenario where the manifest+lockfile bump alone satisfies `npm test` — that's deliberate, and it's why Phase 4's action-surface bound `manual_patch ∋ {package.json, lockfile}` is sufficient).
- The two runs share a tmp directory **for the chromadb store** but get separate copies of the repo tree. Conflating the two breaks the test's logical structure.
- Per Gap 1 (`../phase-arch-design.md §"Gap analysis"`): if the writeback wrote a `Plan.kind="manual_patch"` (which is the more likely case for a real breaking-change diff), run 2 routes via tier-2 fewshot-LLM, NOT tier-1 cache, because the cached `Plan.kind="recipe_invocation"` branch is the only short-circuit. **However**, S6-01 synchronously `put`s a `QueryKeyCache` entry inside writeback regardless of `Plan.kind` — so run 2 with the same `lockfile_blake3` and `qk` hits tier-1 by QK identity, not by RAG cosine. The test asserts `plan_source="query_cache"` (tier-1 by QK), not `plan_source="rag_exact"`. This is the cleanest reading of `../High-level-impl.md §"Step 6"` and the `--no-rag still writebacks LLM-cold` invariant. If the assertion proves wrong in practice, that's a Gap-1-amendment ADR.
- The cassette is recorded **once**, committed once, and never re-recorded silently. The `cassettes-reviewed` label is the workflow; the model-pin deprecation (ADR-P4-007) is when a coordinated re-record happens, and S7-06's runbook captures the steps.
- The `is_equivalent_diff` helper is **deliberately conservative**. If you find yourself extending it to allow more variants, write an ADR — equivalence is exactly the surface where "we just relaxed the check to make CI green" creates compounding bugs.
- The test runs offline (`--record-mode=none`) under CI but **does** record-once locally during development. The `tests/canaries/test_e2e_llm_path_under_180s.py` from S7-03 piggybacks on this cassette for its wall-clock canary; keep the cassette location stable.
- Do NOT mark this `@pytest.mark.slow` — it's the exit-criterion test and should be in the **default** suite, not behind an optional flag. If wall-clock becomes a problem, the perf canary owns it, not the correctness test.
- Per `../High-level-impl.md §"Implementation-level risks"` row 2 (synchronous-triple-write writeback partial failure): if run 1 succeeds but run 2 reads back an inconsistent store (orphan body, missing chromadb row), the failure is in S6-01's writeback path, not in this test. Surface the failure with the diagnostic JSON, then re-run S6-01's writeback unit tests against the failing state.
- The orchestrator invocation is **the same six calls** for both runs (Phase-3 synchronous-linear discipline holds — `../phase-arch-design.md §"Process view"` Note: "Phase 4 changes nothing about that"). The only behavioral difference is which tier of `RagLlmEngine.apply()` fires.
