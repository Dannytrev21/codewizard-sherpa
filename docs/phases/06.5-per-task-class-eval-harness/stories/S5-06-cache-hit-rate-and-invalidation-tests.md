# Story S5-06 — Cache hit-rate + invalidation integration tests

**Step:** Step 5 — Backfill `bench/vuln-remediation/` with ≥10 cases + rubric + taxonomies
**Status:** Ready
**Effort:** S
**Depends on:** S5-05 (10 signed cases + E2E green run is the substrate these tests rerun against)
**ADRs honored:** ADR-0001 (rubric subprocess invocation contributes to `rubric_digest` — the cache key feels every byte), ADR-0002 (cache hit means the report's `lower_bound_95` is byte-identical across reruns — determinism is load-bearing for promotion evidence)

## Context

The harness's cache key per case is `BLAKE3(case_digest || sut_digest || rubric_digest || cassette_corpus_digest || harness_version || cassette_canary_pin)` (S2-03). If any input changes, the key changes. If none changes, every case is a cache hit, every `cost_usd` is `0.0`, and a warm rerun is bounded by the cache I/O rather than by SUT invocation. The harness's cost discipline (CI budget, contributor dev-loop latency) hinges on this being true.

Two failure modes the integration test must catch:
- **False misses** — a warm rerun re-invokes the SUT. Cache key derivation is wrong; cost regression silent.
- **False hits** — a case is edited but the cache serves the stale score. Cache key is missing an input. Promotion evidence becomes lies.

ADR-0002 + ADR-0001 don't *say* "cache must be correct" explicitly, but the promotion gate's `lower_bound_95` is only meaningful if the score producing it is reproducible **and** invalidated when any input shifts. The 10-case vuln-remediation bench is the first concrete corpus to test this on.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design → src/codegenie/eval/cache.py` — `get/put/gc`; corrupt-file-on-read treated as miss; `fcntl.flock` on sentinel.
  - `../phase-arch-design.md §Testing strategy → Integration → test_cache_hit_rate.py / test_cache_invalidation.py` — names this story's tests; specifies "second run ≤ 8 s" and "all 10 `cost_usd == 0.0`"; whitespace edits to `rubric.py` invalidate all; whitespace edits to one `case.toml` invalidate only that case.
  - `../phase-arch-design.md §Property tests → Cache-key determinism` — the Hypothesis-property substrate this integration test concretizes against the 10-case corpus.
- **Phase ADRs:**
  - `../ADRs/0001-rubric-execution-isolation-via-subprocess.md §Consequences` — the rubric file is bytewise part of `rubric_digest`; any edit (whitespace included) bumps it.
  - `../ADRs/0002-promotion-gate-keys-on-lower-bound-95.md §Consequences` — deterministic `lower_bound_95` requires deterministic cache; this test enforces both.
- **Source design:** `../High-level-impl.md §Step 5` "Done criteria" — "Re-running the same task class with no source changes is a 100% cache hit (10/10 cases `cost_usd == 0.0`, wall-clock ≤ 8 s)"; "whitespace edit to `rubric.py` invalidates all 10 cache entries; whitespace edit to one `case.toml` invalidates exactly that case".

## Goal

Land two integration tests that exercise the full cache contract on the 10-case vuln-remediation bench: `test_cache_hit_rate.py` asserts 10/10 `cost_usd == 0.0` and ≤ 8 s wall-clock on a warm rerun; `test_cache_invalidation.py` asserts whitespace-edit to `rubric.py` invalidates all 10 entries while a whitespace-edit to one `case.toml` invalidates exactly that case.

## Acceptance criteria

- [ ] `tests/integration/test_cache_hit_rate.py` exists; running it: (a) executes a cold-cache `codegenie eval run --task-class=vuln-remediation` against the stub deterministic SUT, (b) immediately re-executes the same command, (c) asserts the second run's `BenchRunReport.per_case` has all 10 `cost_usd == 0.0`, (d) asserts the second run's wall-clock is ≤ 8 s.
- [ ] `tests/integration/test_cache_invalidation.py` exists with two scenarios:
  - **All-invalidation** scenario: warm the cache; append `"\n"` to `bench/vuln-remediation/rubric.py`; rerun; assert all 10 cases re-invoke the SUT (`cost_usd > 0.0` for all 10, or — if the stub SUT itself reports `cost_usd=0.0` — a different cache-miss signal: the per-case `wall_clock_ms` exceeds a "definitely re-invoked" floor; document the chosen invariant).
  - **Single-invalidation** scenario: warm the cache; append `"\n"` to one case's `case.toml` (e.g., `bench/vuln-remediation/cases/001-*/case.toml`); rerun; assert exactly 1 case re-invoked the SUT (or its digest mismatch produces a `BenchCaseDigestMismatch` error — see §Notes for the implementer); the other 9 cache-hit cleanly.
- [ ] Both tests restore the edited file in a `try`/`finally` so a failure mid-test does not leave the working tree dirty.
- [ ] The "cache hit" detection is **not** based on time alone — it asserts the per-case `cost_usd` signal *and* an explicit `cache_hit: bool` (or equivalent) field on the per-case JSONL output if S3-02 exposes one. If S3-02 doesn't expose a `cache_hit` field, add a feature: `BenchRunReport.per_case[*]` carries a `BenchScore.cache_hit: bool = False` (default; runner sets True on serve-from-cache).
- [ ] The warm rerun wall-clock budget is asserted as ≤ 8 s; if it regresses past 12 s, the test fails with a diagnostic naming the cache-hit rate.
- [ ] Both tests run in CI within the standard test suite; they are not nightly-canary-only.
- [ ] Red versions of both tests exist, were committed at red, are now green; `ruff check`, `ruff format --check`, `pytest tests/integration/test_cache_hit_rate.py tests/integration/test_cache_invalidation.py -v` pass.

## Implementation outline

1. Write `tests/integration/test_cache_hit_rate.py` first (red) — see §TDD plan.
2. Write `tests/integration/test_cache_invalidation.py` next (red).
3. Determine the cache-hit signal:
   - **Preferred:** `BenchScore.cache_hit: bool` (default `False`; runner sets `True` when serving from cache). If S1-02 didn't include it, add it now under `extra="forbid"` semantics. Document on `BenchScore`.
   - **Fallback:** assert `cost_usd == 0.0` AND `wall_clock_ms < <threshold>` (the stub SUT's hand-coded cost is 0.0 always, so `cost_usd` alone is insufficient; the `wall_clock_ms` threshold proxy works for the stub SUT but is fragile).
4. Pick the preferred path; extend `BenchScore` if needed.
5. Iterate to green for both tests.
6. Documentation: a short section in `bench/vuln-remediation/README.md` ("Cache behavior") names the two integration tests and the cache-key composition.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/integration/test_cache_hit_rate.py`

```python
# tests/integration/test_cache_hit_rate.py
"""Cache contract on the 10-case vuln-remediation bench.
S2-03 + High-level-impl.md §Step 5 "Done criteria"."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).parents[2]


@pytest.fixture()
def fresh_eval_env(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEGENIE_EVAL_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("CODEGENIE_EVAL_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("CODEGENIE_EVAL_SUT", "tests.fixtures.sut.deterministic_vuln_sut")
    return tmp_path


def _run():
    start = time.monotonic()
    result = subprocess.run(
        [sys.executable, "-m", "codegenie", "eval", "run",
         "--task-class=vuln-remediation", "--format=jsonl"],
        capture_output=True, text=True, cwd=REPO_ROOT, check=True,
    )
    return result, time.monotonic() - start


def _per_case_lines(result):
    return [json.loads(l) for l in result.stdout.splitlines()
            if l.strip() and json.loads(l).get("kind") == "case"]


def test_warm_rerun_is_100_percent_cache_hit(fresh_eval_env):
    _ = _run()  # cold
    result, elapsed = _run()  # warm
    cases = _per_case_lines(result)
    assert len(cases) == 10
    # ADR-0002 + S2-03: warm rerun = byte-identical scores at zero cost.
    assert all(c["score"]["cost_usd"] == 0.0 for c in cases), (
        f"expected all cost_usd=0.0; got {[c['score']['cost_usd'] for c in cases]}"
    )
    assert all(c["score"].get("cache_hit") is True for c in cases), (
        "expected cache_hit=True on every per_case entry"
    )
    assert elapsed <= 8.0, f"warm rerun took {elapsed:.2f}s; budget 8s"
```

Test file path: `tests/integration/test_cache_invalidation.py`

```python
# tests/integration/test_cache_invalidation.py
"""Cache invalidation contract: rubric edit invalidates everything;
single-case edit invalidates only that case. ADR-0002 §Consequences."""

import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).parents[2]
BENCH = REPO_ROOT / "bench" / "vuln-remediation"


@pytest.fixture()
def fresh_eval_env(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEGENIE_EVAL_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("CODEGENIE_EVAL_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("CODEGENIE_EVAL_SUT", "tests.fixtures.sut.deterministic_vuln_sut")
    return tmp_path


def _run():
    return subprocess.run(
        [sys.executable, "-m", "codegenie", "eval", "run",
         "--task-class=vuln-remediation", "--format=jsonl"],
        capture_output=True, text=True, cwd=REPO_ROOT, check=False,
    )


def _per_case(result):
    return [json.loads(l) for l in result.stdout.splitlines()
            if l.strip() and json.loads(l).get("kind") == "case"]


def test_whitespace_edit_to_rubric_invalidates_all_ten(fresh_eval_env):
    _run()  # cold; warm cache
    rubric = BENCH / "rubric.py"
    original = rubric.read_bytes()
    try:
        rubric.write_bytes(original + b"\n# cache-bust\n")
        result = _run()
        cases = _per_case(result)
        assert len(cases) == 10
        cache_hits = sum(1 for c in cases if c["score"].get("cache_hit") is True)
        assert cache_hits == 0, (
            f"expected 0 cache hits after rubric edit; got {cache_hits}/10"
        )
    finally:
        rubric.write_bytes(original)


def test_whitespace_edit_to_one_case_invalidates_only_that_case(fresh_eval_env):
    _run()  # warm cache
    target_dir = next(d for d in (BENCH / "cases").iterdir() if d.is_dir())
    target_id = target_dir.name
    case_toml = target_dir / "case.toml"
    # Edit a file under input/ (changing case.toml itself would also bump digest,
    # but it would be caught by the digest-mismatch raise; whitespace edit to
    # input/<f> changes case_digest, which propagates into cache_key only for
    # this case_id).
    input_file = next(p for p in (target_dir / "input").rglob("*") if p.is_file())
    original = input_file.read_bytes()
    try:
        input_file.write_bytes(original + b"\n")
        # case_digest is now stale relative to digests.yaml; the loader will
        # raise BenchCaseDigestMismatch (exit 6). This is the correct behavior:
        # "single-case invalidation" is structurally surfaced as a digest error,
        # not a silent cache miss.
        result = _run()
        assert result.returncode == 6, (
            f"expected exit 6 on case digest mismatch; got {result.returncode}; "
            f"stderr={result.stderr[-1000:]}"
        )
        assert target_id in result.stderr, (
            f"diagnostic must name the offending case_id {target_id}"
        )
    finally:
        input_file.write_bytes(original)
```

Run both; confirm failures. Commit as red marker.

### Green — smallest impl shape

1. If `BenchScore.cache_hit: bool = False` doesn't exist on the wire type (S1-02), add it (with `extra="forbid"` and default `False`); have the runner (S3-02) set `True` when serving cached.
2. Ensure the CLI's JSONL output (S4-02) emits per-case lines with a `"score": {..., "cache_hit": bool}` shape; if it's already structured but `cache_hit` is missing, surface it.
3. Confirm cache invalidation works as designed: an edit to `bench/vuln-remediation/rubric.py` changes `rubric_digest`, which is one input to every per-case cache key. The change propagates to all 10 cases.
4. Confirm single-case invalidation works structurally: a `case.toml` (or input/) edit changes `case_digest`, which is recomputed by the loader against `digests.yaml`. The mismatch raises `BenchCaseDigestMismatch` (exit 6), which is the *correct* behavior — silent cache miss would be the bug.
5. If S2-02 currently allows "single case digest changes silently" (no digests.yaml check), that is a separate bug; this story's single-case test asserts the **structurally-correct** behavior (exit 6 with the case_id in stderr) — see §Notes for the implementer.

### Refactor — clean up

- Document the "single-case invalidation = digest mismatch error" decision in `bench/vuln-remediation/README.md`'s Cache behavior section. The semantics differ from naive caches: bench cases are signed; you cannot edit one and "let the cache invalidate" — you must re-sign in `digests.yaml`. The cache is signed-content-addressed.
- The `cache_hit` field is part of the wire contract; document on `BenchScore` and add a property test (Hypothesis): `cache_hit=True implies cost_usd == 0.0`.
- The 8-s warm-budget is the High-level-impl.md §Step 5 floor. If CI machines are slow, the test will flake — surface as a benchmark, not a hard fail (mark `@pytest.mark.benchmark` if needed; budget stays in the assertion).
- Cross-reference S7-02's "audit chain extension integration" test — both reuse the `fresh_eval_env` fixture; consider hoisting to `tests/integration/conftest.py`.

## Files to touch

| Path | Why |
|---|---|
| `tests/integration/test_cache_hit_rate.py` | New — warm-rerun 100% cache hit + ≤ 8 s budget |
| `tests/integration/test_cache_invalidation.py` | New — rubric-edit invalidates all; case-edit invalidates one (digest mismatch) |
| `src/codegenie/eval/models.py` (maybe) | Extend — add `BenchScore.cache_hit: bool = False` if not extant |
| `src/codegenie/eval/runner.py` (maybe) | Extend — set `cache_hit=True` on serve-from-cache |
| `src/codegenie/eval/cli.py` (maybe) | Verify — JSONL emits the field |
| `bench/vuln-remediation/README.md` | Extend — "Cache behavior" section documenting the contract |
| `tests/integration/conftest.py` (maybe) | New — `fresh_eval_env` fixture if shared with S7-02 |

## Out of scope

- **Hypothesis property tests for cache-key determinism.** Listed in `phase-arch-design.md §Property tests`; lives in `tests/unit/test_cache.py` (S2-03 / property-test story, separate); this story is the *integration*-level concretization.
- **Cache GC behavior.** S2-03's `gc(retain_days=90)` is unit-tested there; not in scope here.
- **Cross-host cache sharing.** Gap #5 (parallel-eval across hosts) is deferred; the cache is per-host in Phase 6.5.
- **Concurrent eval-run race.** Edge case #17 is fence-CI / runner-level; the cache uses `fcntl.flock` to serialize writers but the integration test does not exercise concurrency here.

## Notes for the implementer

- The "single-case invalidation" semantics are subtle. Two valid interpretations:
  1. **Edit `input/`/`expected/` of one case** → `case_digest` recomputation by loader → mismatch with `digests.yaml` → `BenchCaseDigestMismatch` (exit 6). This is what the test asserts. The cache never even gets a chance to serve a stale entry because the loader refuses the case.
  2. **Re-sign `digests.yaml` after the edit** → `case_digest` matches → cache key includes the new `case_digest` → cache miss for *this* case only → 1 SUT re-invocation, 9 cache hits. This is the "single-case invalidation = single cache miss" semantics; assertable as `cache_hits=9, misses=1`.

   The story's primary assertion is (1) because it tests the load-bearing structural defense (signed digests). A secondary test of (2) is welcome but optional — note that it requires running the digest-signing script mid-test.
- If `BenchScore.cache_hit` is added, surface it everywhere the score is JSON-serialized: stdout JSONL, audit record, snapshot tests. S7-02's golden-file snapshot will need a regen if the field is new.
- The warm rerun in `test_warm_rerun_is_100_percent_cache_hit` is a *subprocess*-launch of the CLI. Python interpreter startup itself takes ~150 ms; module imports add another ~300 ms; cache I/O is small but non-zero. The 8 s budget is generous; if you find yourself at 7.5 s, profile cold-imports — S4-01's "deferred heavy imports" discipline applies.
- If the `EVAL_CACHE_DIR` env contract doesn't exist, add it in S2-03 or here — the test needs a way to point the cache at `tmp_path` for isolation.
- The "cache-bust" edit must change *byte content*, not just `mtime`. The cache is content-addressed (BLAKE3 over inputs); `touch rubric.py` would not invalidate. The test appends a newline; document this.
- `tests/fixtures/sut/deterministic_vuln_sut.py` (from S5-05) must produce **byte-stable** `harness_output` for each case across runs, or the integration test will appear to pass spuriously (the cache might serve stale entries that happen to match). Verify determinism by running the stub twice in isolation and `diff`-ing JSON dumps.
- If the test failures reveal that the cache key doesn't include `rubric_digest` (i.e., a rubric edit *doesn't* invalidate), that is the bug S2-03 must fix. Surface to S2-03's owner; don't kludge the test.
