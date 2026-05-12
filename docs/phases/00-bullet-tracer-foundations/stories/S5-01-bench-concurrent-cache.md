# Story S5-01 — Performance canaries + concurrent-cache test

**Step:** Step 5 — Close the remaining CI gates and project conventions
**Status:** Ready
**Effort:** S
**Depends on:** S4-04
**ADRs honored:** ADR-0001, ADR-0003, ADR-0009, ADR-0011

## Context

Phase 0's CI gate set is nearly complete after Step 4 — `lint`, `typecheck`, `test`, `security`, `docs`, and `fence` are green and the bullet tracer's cache-hit assertion lives in `tests/smoke/`. Two gaps remain on the testing surface: (1) the system has no visibility on the three latency metrics the architecture flagged as load-bearing for contributor-experience (cold start, dispatch overhead, cache-hit dispatch ratio), and (2) the concurrent-write invariant called out as edge case #12 — two `codegenie gather` invocations appending to the same `.codegenie/cache/index.jsonl` — is asserted nowhere. This story closes both: three advisory benchmarks under `tests/bench/` that *post* PR comments without gating merge (per the explicit L3 #12 decision against flaky cold-start gating), and one real unit test that pins the `O_APPEND`-is-atomic-for-records-under-4096B invariant the cache store depends on.

This is downstream, contributor-facing work — it doesn't unblock anything; it closes signals.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Testing strategy / Performance regression tests` — the three canaries, advisory-only posture, structural defense lives in `import-linter`, not the canary.
  - `../phase-arch-design.md §Edge cases row 12` — concurrent gather → `O_APPEND` atomic for ≤ 4096B records; JSONL parses line-by-line; blob writes atomic via `<dest>.tmp → os.replace`.
  - `../phase-arch-design.md §CacheStore` — append-only `index.jsonl`, sharded BLAKE3 blobs, atomic publish.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0001-cache-content-hash-algorithm.md` — ADR-0001 — blobs are content-addressed by BLAKE3; do not bypass `hashing.content_hash` in the concurrent test fixtures.
  - `../ADRs/0003-two-level-cache-key-schema-versioning.md` — ADR-0003 — both concurrent gathers must hit the same cache key for the test to actually test contention; do not vary `per_probe_schema_version` between them.
  - `../ADRs/0009-cache-hit-pass-through-coordinator-output.md` — ADR-0009 — the `ProbeExecution` union (`Ran | CacheHit | Skipped`) is the surface the bench tests assert on for the dispatch-ratio canary.
  - `../ADRs/0011-codegenie-directory-permissions-model.md` — ADR-0011 — both concurrent gathers must leave `.codegenie/cache/` directories `0700` and files `0600` after they finish; assert in the test, not just trust it.
- **High-level impl plan:**
  - `../High-level-impl.md §Step 5` — the three bench files and the concurrent-cache test are bullets 2–5 of Step 5's features.
  - `../High-level-impl.md §Implementation-level risks #3` — performance canaries on shared CI runners are variance-prone; advisory-only is the explicit decision (L3 row 12).
- **Manifest:**
  - `../stories/README.md` — S5-01 row; Definition of done section #2 (the TDD plan's red test exists, is committed, and is green); cross-cutting concern bullet "Permission discipline (ADR-0011)".
- **Existing code (consumed by these tests):**
  - `src/codegenie/cli.py` — `codegenie gather` entry point the cold-start canary invokes.
  - `src/codegenie/cache/store.py` — `CacheStore.put` writes JSONL index + sharded blobs.
  - `src/codegenie/cache/keys.py` — `key_for(probe, snapshot, task)`; both concurrent gathers will produce the same key on `js_only` fixture.
  - `src/codegenie/coordinator/coordinator.py` — `GatherResult.executions["language_detection"]` is `CacheHit | Ran` for dispatch-ratio assertions.
  - `tests/fixtures/js_only/` — the canary and concurrent test reuse this fixture.

## Goal

Three advisory benchmark tests post PR-comment numbers for cold start, dispatch overhead, and cache-hit dispatch ratio (no merge gate), and one unit test verifies two concurrent `codegenie gather` invocations against the same `.codegenie/cache/index.jsonl` both succeed and the index parses cleanly line-by-line.

## Acceptance criteria

- [ ] `tests/bench/test_cli_cold_start.py` exists, runs `codegenie --help` five times via `subprocess.run`, computes the median wall-clock, and writes the number to `bench-results.json` (CI uploads as a PR comment artifact). The test **never** asserts a threshold — it is advisory and always green.
- [ ] `tests/bench/test_coordinator_overhead.py` exists, dispatches one no-op probe through the real coordinator + sanitizer + validator + writer, captures the wall-clock, writes to `bench-results.json`. Advisory only.
- [ ] `tests/bench/test_cache_hit_dispatch.py` exists, runs `gather` on `tests/fixtures/js_only/` twice, computes the second-run-over-first-run ratio, writes to `bench-results.json`. Advisory only.
- [ ] `tests/unit/test_cache_concurrent.py` exists; the TDD red test (below) passes; two concurrent gathers against the same cache directory both report `outputs["language_detection"]` populated and `executions["language_detection"]` is exactly one `Ran` and one `CacheHit` *or* two `Ran`s (depending on ordering) — never a failure for either.
- [ ] `tests/unit/test_cache_concurrent.py` asserts every line in `.codegenie/cache/index.jsonl` parses as valid JSON after the concurrent runs — no interleaved/torn records.
- [ ] `tests/unit/test_cache_concurrent.py` asserts post-run that every file under `.codegenie/cache/` is mode `0600` and every directory is `0700` (ADR-0011 enforcement; CI gates this rule on a PR that drops the `os.chmod` re-application).
- [ ] CI workflow file (`.github/workflows/ci.yml`) routes `tests/bench/` runs into the `test` job under a `bench` step that does not fail the job; the step writes `bench-results.json` as a workflow artifact uploaded via `actions/upload-artifact` (SHA-pinned).
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest tests/unit/test_cache_concurrent.py tests/bench/` all pass on the touched files.

## Implementation outline

1. Write the TDD red test for `test_cache_concurrent.py` first; commit it failing because the assertion shape (post-run mode bits + interleaved-record-free JSONL) doesn't yet exist as a single asserted invariant.
2. Verify the existing `CacheStore` already satisfies the invariant under concurrent writes (it should — `O_APPEND` is atomic for ≤ 4096B records per edge case #12 + atomic blob writes via `<dest>.tmp → os.replace`); if it does, the only "green" work is wiring up the test mechanics (two `asyncio.gather`'d gathers, post-run mode-bit assertions, JSONL line parser).
3. Write `tests/bench/test_cli_cold_start.py` — subprocess invocation of `codegenie --help` × 5 runs, statistics.median, JSON output writer. Use `pytest_benchmark` only if it adds clarity; the manual median is fine for advisory output.
4. Write `tests/bench/test_coordinator_overhead.py` — register a `NoopProbe(Probe)` inside the test file (don't pollute the production registry), construct a synthetic `RepoSnapshot`, call `coordinator.gather(...)` directly, capture timing.
5. Write `tests/bench/test_cache_hit_dispatch.py` — `subprocess.run` two `codegenie gather <fixture>` calls; assert the second wall-clock divided by the first is computed and written to `bench-results.json` (no threshold).
6. Update `.github/workflows/ci.yml`: add a `bench` step to the `test` job after the main pytest invocation; `pytest tests/bench/ -q --tb=short` and `actions/upload-artifact@<sha>` for `bench-results.json`. The step uses `continue-on-error: true` so a bench crash doesn't gate merge.
7. Run `make check` locally; commit.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/test_cache_concurrent.py`

```python
# tests/unit/test_cache_concurrent.py
import asyncio
import json
import os
import stat
from pathlib import Path

import pytest

from codegenie.cache.store import CacheStore
from codegenie.coordinator.coordinator import gather
from codegenie.probes import default_registry
from codegenie.coordinator.snapshot import construct_snapshot


@pytest.mark.asyncio
async def test_two_concurrent_gathers_leave_consistent_cache(tmp_path: Path):
    """
    Edge case #12: two `codegenie gather` invocations against the same
    .codegenie/cache/index.jsonl must both succeed; the JSONL must parse
    line-by-line; and post-run mode bits must remain 0600 / 0700 (ADR-0011).
    """
    # arrange: a single fixture repo; both gathers use the same cache root.
    fixture = Path(__file__).parent.parent / "fixtures" / "js_only"
    cache_root = tmp_path / ".codegenie" / "cache"
    snapshot = construct_snapshot(fixture)
    probes = default_registry.for_task("__bullet_tracer__", frozenset({"unknown"}))
    cache = CacheStore(root=cache_root)

    # act: dispatch both gathers concurrently with no synchronization.
    results = await asyncio.gather(
        gather(snapshot, task="__bullet_tracer__", probes=probes, cache=cache),
        gather(snapshot, task="__bullet_tracer__", probes=probes, cache=cache),
    )

    # assert 1: both gathers succeeded; the language_detection slice is populated for both.
    for result in results:
        assert "language_detection" in result.outputs
        assert result.outputs["language_detection"].errors == []

    # assert 2: index.jsonl parses line-by-line — no torn records.
    index_path = cache_root / "index.jsonl"
    with index_path.open("rb") as fh:
        for raw_line in fh:
            json.loads(raw_line)  # raises if any line is half-written

    # assert 3: ADR-0011 — every file 0600, every dir 0700, after both runs.
    for entry in cache_root.rglob("*"):
        mode = stat.S_IMODE(entry.stat().st_mode)
        expected = 0o700 if entry.is_dir() else 0o600
        assert mode == expected, f"{entry}: expected {oct(expected)}, got {oct(mode)}"
```

The test fails initially because either (a) no such test was committed before, so the assertion surface is novel, or (b) if the `CacheStore` implementation lacks the post-write `os.chmod` discipline at any path the concurrent test exercises (orphan blob paths, index path on creation), the mode-bit assertion fails. Either is a valid red. Run it, confirm failure, commit the failing test as a marker.

The three bench files do not have a "red" phase in the TDD sense — they are observation harnesses, not behavior tests. Write them green; they assert *nothing* about thresholds.

### Green — make it pass

For `test_cache_concurrent.py`: if the assertions fail for the mode-bit reason, the fix lives in `CacheStore` (re-apply `os.chmod(0o600)` on the blob and `os.chmod(0o700)` on the shard dir after every `put`); this should already be in place from S3-01, so this story should **not** modify `CacheStore` — surface as a regression bug if discovered. If the JSONL line-parse fails, the bug is in `CacheStore.put`'s record-length discipline (records must fit in `PIPE_BUF=4096B`); same surfacing rule. The test is the gate; it does not introduce code under `src/`.

For the three bench files: each is ~30–40 lines. Use `time.perf_counter`, write a single `bench-results.json` keyed by test name. Place output under `tmp_path` and copy/print to a workflow-accessible location at session teardown using `pytest`'s `request.node.config` for stable paths.

### Refactor — clean up

- Extract the mode-bit-walk into a `_assert_codegenie_perms(root: Path)` helper at the module level so future stories can reuse it.
- Type hints throughout; `mypy --strict` clean.
- Docstrings on `_assert_codegenie_perms` and on each bench test's top-level docstring (explaining "advisory only, no merge gate").
- Add `pytest.mark.bench` to the three bench tests; configure `pyproject.toml` markers so `pytest -m "not bench"` is the default local invocation and `pytest -m bench` runs only the canaries.
- Confirm the bench tests honor `--no-network` style invariants — none of them should reach `httpx`/`socket`; `tests/adv/test_no_network_imports.py` from S2 already scans `src/`; for `tests/`, leave a comment that bench tests are exempt from the AST scan but must not network-import.

## Files to touch

| Path | Why |
|---|---|
| `tests/unit/test_cache_concurrent.py` | New file — pins concurrent-write invariant per edge case #12 and ADR-0011. |
| `tests/bench/__init__.py` | New file — empty, marks `tests/bench/` as a package. |
| `tests/bench/test_cli_cold_start.py` | New file — advisory cold-start canary (median of 5 runs). |
| `tests/bench/test_coordinator_overhead.py` | New file — advisory dispatch-overhead canary (one no-op probe). |
| `tests/bench/test_cache_hit_dispatch.py` | New file — advisory cache-hit ratio canary (second-run / first-run wall-clock). |
| `.github/workflows/ci.yml` | Modify — add `bench` step to the `test` job with `continue-on-error: true` + `actions/upload-artifact` for `bench-results.json`. |
| `pyproject.toml` | Modify — register `bench` marker under `[tool.pytest.ini_options]` markers. |

## Out of scope

- **Cold-start *gating*** — explicitly deferred; L3 #12 chose `import-linter` as the structural defense in S1-05. Bench is advisory forever; if a future phase wants a gate, it lands then with the ADR amendment.
- **PR-comment posting mechanics (bot wiring, formatting)** — the canaries emit `bench-results.json`; an out-of-scope GitHub Action (filed as a Phase 1 follow-up by S5-02) consumes the artifact and posts the comment. Phase 0 only generates the JSON.
- **Property-based concurrent-write fuzzing** — Phase 5's trust gates are the first phase where property tests earn their keep (`phase-arch-design.md §Property tests`); Phase 0 ships one focused concurrent-write test, not a Hypothesis suite.
- **Concurrent writes to the same blob path** — the test ensures both gathers hit the same *cache key*; the underlying blob-write atomicity is asserted in S3-01's `test_cache_store.py`. This story does not re-test the blob-write path.

## Notes for the implementer

- The concurrent test uses `asyncio.gather` to start both gathers from the same event loop; if you instead spawn two processes via `subprocess.run`, you're testing process-level concurrency (more realistic) but you can't reuse the in-process `default_registry`. Pick the async version — it exercises the `O_APPEND` invariant at the file-system level just as effectively because `open(... , 'a')` uses `O_APPEND` under the hood.
- `bench-results.json` should be written atomically (`<tmp> → fsync → os.replace`) so a flaky test doesn't truncate the artifact mid-CI. Reuse `Writer`'s atomic-write helper if convenient; otherwise inline.
- Per edge case #12 in `phase-arch-design.md`: records ≤ 4096B is the `O_APPEND`-atomic threshold; if `CacheStore.put` ever writes longer JSONL records, the invariant breaks. The test does not separately assert record length — that's S3-01's territory — but if the line-parse assertion fails, suspect the record-length discipline before suspecting `O_APPEND` itself.
- Do not import `pytest_benchmark`. It's not in `dev` extras; adding it would expand the dependency closure for an advisory-only signal. Manual `time.perf_counter` is sufficient.
- The bench tests will be the first tests in `tests/bench/`. The directory does not exist yet; the `__init__.py` marker file plus the three test files create it. CI's `pytest` invocation in the `test` job auto-discovers them unless markers exclude — make sure the `bench` marker in `pyproject.toml` does **not** filter them out by default *within* the `bench` step (it filters them out of the local-default `make test` invocation, which is the user-facing UX).
- The CI workflow change must keep the actions SHA-pinned per ADR-0002 / `phase-arch-design.md §CI gates`. Look up `actions/upload-artifact`'s current SHA; do not use `@v4`.
