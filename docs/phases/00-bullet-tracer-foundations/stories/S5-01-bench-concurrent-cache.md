# Story S5-01 — Performance canaries + concurrent-cache test

**Step:** Step 5 — Close the remaining CI gates and project conventions
**Status:** Ready — HARDENED
**Effort:** S
**Depends on:** S4-04
**ADRs honored:** ADR-0001, ADR-0003, ADR-0009, ADR-0011

## Validation notes

**Validated:** 2026-05-13
**Verdict:** HARDENED
**Findings addressed:** 22 (12 block, 8 harden, 2 nit) — see `_validation/S5-01-bench-concurrent-cache.md`

**Changes applied (summary):**
- Concurrent test pivots from `asyncio.gather` to two-process `subprocess.Popen` invocations of the installed CLI. Arch (edge case #12 — `phase-arch-design.md §789`) says "two-process test"; async same-event-loop tasks share one OS thread and do not exercise the `O_APPEND` kernel-atomicity invariant the edge case names. The story's original Notes claim that `open(..., 'a')` made async "just as effective" is technically false and is removed.
- TDD red test rewritten to import real symbols (`build_snapshot`, not the non-existent `construct_snapshot`), pass the full `gather(snapshot, task, probes, config, cache, sanitizer)` signature, instantiate probe classes returned by `default_registry.for_task(...)`, and construct `CacheStore` with its real constructor — all four were API-mismatched in the original draft and would have failed at import.
- AC-3 strengthened: dispatch-ratio canary must additionally assert that the second invocation produced a `CacheHit` (ADR-0009), so a "cache silently never hits" regression cannot pass through as a small ratio.
- AC-4 disjunction kept ("two `Ran`s or one `Ran` + one `CacheHit`") — now reachable under the two-process choice (both processes can read-miss before either writes; with serialized scheduling, the later writer reads the earlier's blob).
- AC-6 wording re-scoped: assertion is "after both subprocesses have exited", matching ADR-0011's "post-`gather`" framing. Note added that this *extends* ADR-0011 to the concurrent-gather case rather than restating it.
- New ACs added: (a) `bench-results.json` schema with per-test top-level key and atomic write; (b) `pytest --collect-only -m bench tests/bench/ -q` reports exactly three tests (guards against marker-config regression silently disabling all canaries); (c) `tests/fixtures/js_only/` byte-immutability check post-concurrent-runs; (d) cold-start canary invokes `sys.executable -m codegenie --help` (not a bare `codegenie` on `$PATH`) to prevent stale-install bias; (e) sequential-control follow-up gather after the concurrent pair asserts `CacheHit` (catches "cache write happens but read path is broken").
- New AC added: metamorphic perm-restoration test inside `test_cache_concurrent.py` — dirty one cached-blob file's mode to `0644` between gathers, assert it is restored to `0600`. Catches the "chmod-on-construction-but-never-after" mutation that AC-6 alone would not.

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

- [ ] `tests/bench/test_cli_cold_start.py` exists, invokes the CLI via `subprocess.run([sys.executable, "-m", "codegenie", "--help"], ...)` (NOT a bare `codegenie` on `$PATH` — guards against stale globally-installed wheels biasing numbers) five times, computes the median wall-clock, and writes the number to `bench-results.json["cold_start"] = {"wall_clock_s_median": <float>, "samples": [<5 floats>]}`. The test **never** asserts a threshold — it is advisory and always green. (validator: hardened from "via `subprocess.run`" — `sys.executable -m` form guarantees the under-test interpreter and package are exercised.)
- [ ] `tests/bench/test_coordinator_overhead.py` exists, dispatches one in-test `NoopProbe(Probe)` instance through the real `coordinator.gather(...)` (with real `OutputSanitizer`, real `_ProbeOutputValidator` inside the coordinator, and real `CacheStore` against `tmp_path`), captures the wall-clock from before `gather` to after, writes to `bench-results.json["coordinator_overhead"] = {"wall_clock_s": <float>}`. Advisory only.
- [ ] `tests/bench/test_cache_hit_dispatch.py` exists, runs `gather` on `tests/fixtures/js_only/` twice in the same Python process (so the second-run state is observable as `GatherResult.executions`), AND asserts `isinstance(result_run2.executions["language_detection"], CacheHit)` (per ADR-0009) — this is the **one** non-advisory assertion in the bench suite because a silent "cache never hits" defect would otherwise produce a small ratio that looks healthy. Computes the second-run-over-first-run wall-clock ratio and writes to `bench-results.json["cache_hit_dispatch"] = {"ratio": <float>, "cold_s": <float>, "warm_s": <float>}`. Ratio is advisory; the `CacheHit` assertion is gating.
- [ ] All three bench files write to `bench-results.json` via an atomic helper (`<tmp> → fsync → os.replace`) that loads existing contents (if any), merges under a unique per-test top-level key, and writes back — so concurrent or sequential bench runs never truncate each other's keys. The path is resolvable from CI (`os.environ.get("GITHUB_WORKSPACE", ".")` fallback), and a final assertion in each test re-reads the JSON to confirm its top-level key is present with a positive float `wall_clock_s*` value. (validator: added — without this, a `try/except: pass` regression in the bench harness silently produces empty output and CI stays green forever.)
- [ ] `tests/unit/test_cache_concurrent.py` exists. The TDD red test (below) launches **two `codegenie gather <fixture>` invocations as independent OS processes via `subprocess.Popen`**, waits for both to exit, and asserts: (a) both exit code 0; (b) both wrote `.codegenie/context/repo-context.yaml` (or shared one, depending on output-dir choice — see implementer notes); (c) the merged `.codegenie/cache/index.jsonl` parses line-by-line. Process-level is the choice arch §789 names ("Phase 0's two-process test") — it actually exercises `O_APPEND`'s kernel-atomicity guarantee for ≤ `PIPE_BUF=4096`B records, which two asyncio tasks sharing one OS thread do not.
- [ ] `tests/unit/test_cache_concurrent.py` asserts that across the audit records both subprocesses wrote (`.codegenie/runs/<utc-iso>-<short>.json` files), the union of `ProbeExecutionRecord` exit-statuses for `language_detection` is either (`ok`, `ok`-with-`cache_hit=True`) OR (`ok`, `ok`) — never any other shape, never `failed`/`error` for either invocation. Both branches are reachable under process-level concurrency: if both processes read-miss before either writes, both are `Ran`; if the first writes before the second reads, the second is `CacheHit`. (validator: hardened — re-anchored to the audit records that are the persisted surface, not the in-memory `GatherResult` which is per-process under subprocess concurrency.)
- [ ] `tests/unit/test_cache_concurrent.py` asserts every line in `.codegenie/cache/index.jsonl` parses as valid JSON after the concurrent runs — no interleaved/torn records, no two adjacent JSON objects on the same line with no separating `\n` (per edge case #12 line-by-line invariant). (validator: hardened — explicit "no two JSON on one line" check rules out a mutation where records are concatenated without newlines but each individually parses.)
- [ ] `tests/unit/test_cache_concurrent.py` asserts that **after both subprocesses have exited**, every file under `.codegenie/cache/` is mode `0600` and every directory is `0700`. (validator: re-scoped — this extends ADR-0011's "post-`gather`" invariant to the concurrent-gather case; ADR-0011 itself does not contemplate concurrent gathers but the same chmod-after-every-write discipline must hold. The transient `0755`/`0644` window after a future `actions/cache` restore is explicitly NOT asserted here.)
- [ ] `tests/unit/test_cache_concurrent.py` includes a **perm-restoration metamorphic check**: after the concurrent pair completes, the test picks one cache blob file via `next(cache_root.rglob("blobs/**/*.json"))`, chmods it to `0644`, runs a third `codegenie gather` against the same fixture, and asserts the file is restored to `0600`. Catches the "chmod-on-CacheStore-init-only" mutation that the post-run mode walk alone does not. (validator: added — Test-Quality mutation M4.)
- [ ] `tests/unit/test_cache_concurrent.py` asserts that `tests/fixtures/js_only/` is byte-for-byte unchanged across both concurrent runs (compare a recursive SHA-256 manifest taken before and after). Guards against a probe silently writing into the analyzed-repo tree. (validator: added — Coverage gap.)
- [ ] `tests/unit/test_cache_concurrent.py` includes a **sequential-control assertion**: after the concurrent pair, a fourth in-process `await gather(...)` invocation against the same cache returns `executions["language_detection"]` as `CacheHit`. Catches "cache write happens but cache read path is broken" — a regression where AC-4 alone would still pass with two `Ran`s. (validator: added — Test-Quality mutation M5.)
- [ ] CI workflow file (`.github/workflows/ci.yml`) routes `tests/bench/` runs into the `test` job under a `bench` step that does not fail the job (`continue-on-error: true`); the step writes `bench-results.json` as a workflow artifact uploaded via `actions/upload-artifact@<sha>` (SHA-pinned per ADR-0002, NOT `@v4`). The step's pytest invocation is `pytest tests/bench/ -m bench -q --tb=short` so the `bench` marker is the explicit selector.
- [ ] CI workflow includes a **non-advisory** `bench-collection-guard` step (before the `bench` step) that runs `pytest --collect-only -m bench tests/bench/ -q` and fails the job if fewer than three tests are collected. Guards against a future PR that silently disables canaries by renaming or filtering the `bench` marker. (validator: added — Coverage gap.)
- [ ] `pyproject.toml` registers the `bench` marker under `[tool.pytest.ini_options]` markers. The default `make test` invocation is `pytest -m "not bench"` so canaries do not run on every contributor's local loop. The CI `bench` step explicitly uses `-m bench` (not the default).
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest tests/unit/test_cache_concurrent.py tests/bench/` all pass on the touched files.

## Implementation outline

1. Write the TDD red test for `test_cache_concurrent.py` first (the three test functions in the TDD plan below — concurrent-pair, metamorphic third-gather, perm-restoration). Commit it failing because the file does not yet exist, the assertion surface is novel, and the third-gather metamorphic partner is the only place "cache actually hits after concurrent population" is asserted in the entire suite.
2. Verify the existing `CacheStore` already satisfies the invariants under process-level concurrent writes (it should — `O_APPEND` is atomic for ≤ 4096B records per edge case #12 + atomic blob writes via `<dest>.tmp → os.replace` + chmod-after-write per ADR-0011). If any assertion fails for a production-code reason (not test-mechanics), surface it as a regression bug against S3-01 — **this story does not modify `src/codegenie/cache/store.py`**.
3. Write `tests/bench/test_cli_cold_start.py` — `subprocess.run([sys.executable, "-m", "codegenie", "--help"], ...)` × 5 runs, `statistics.median`, atomic JSON output writer keyed under `cold_start`. Manual `time.perf_counter` (no `pytest_benchmark` — see implementer notes / ADR-0006).
4. Write `tests/bench/test_coordinator_overhead.py` — define a `NoopProbe(Probe)` inside the test file (do NOT register on the production `default_registry`), construct a `RepoSnapshot` via `build_snapshot(tmp_path, Config())`, call `await coordinator.gather(snap, task, [NoopProbe()], cfg, CacheStore(tmp_path/"cache", ...), OutputSanitizer())` directly, capture timing, write under `coordinator_overhead`.
5. Write `tests/bench/test_cache_hit_dispatch.py` — run `gather` **in-process** twice against `tests/fixtures/js_only/` (so the second run's `GatherResult.executions` is observable in Python), assert `isinstance(result_run2.executions["language_detection"], CacheHit)` (the non-advisory gate per ADR-0009), compute `ratio = warm_s / cold_s`, write under `cache_hit_dispatch`.
6. Write the atomic `bench-results.json` helper (`load-or-init → merge → <tmp> → fsync → os.replace`); use it in all three bench tests.
7. Update `.github/workflows/ci.yml`:
   - Add a `bench-collection-guard` step (gating): `pytest --collect-only -m bench tests/bench/ -q` with a post-step `grep`/`wc` that fails the job if collected count ≠ 3.
   - Add a `bench` step (advisory): `pytest tests/bench/ -m bench -q --tb=short` with `continue-on-error: true`.
   - Add `actions/upload-artifact@<sha>` (SHA-pinned per ADR-0002, NOT `@v4`) for `bench-results.json`.
8. Update `pyproject.toml`: register the `bench` marker; update the default test target to `pytest -m "not bench"`.
9. Run `make check` locally; commit.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/test_cache_concurrent.py`

```python
# tests/unit/test_cache_concurrent.py
"""S5-01 — edge case #12 (phase-arch-design.md §789): two-process concurrent
gather against the same .codegenie/cache/index.jsonl.

This test is process-level, not asyncio-task-level. Edge case #12's invariant
("O_APPEND atomic for records ≤ PIPE_BUF=4096B; JSONL parses line-by-line")
is a *kernel* guarantee that requires real concurrent processes/threads —
two asyncio tasks share one OS thread and would serialize at the Python
level, never exercising the kernel guarantee. Subprocess invocations of the
real CLI also test the end-to-end install (`sys.executable -m codegenie`)
which is what edge case #12 actually contemplates.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from codegenie.cache.store import CacheStore
from codegenie.config.defaults import Config
from codegenie.coordinator.coordinator import CacheHit, gather
from codegenie.coordinator.snapshot import build_snapshot
from codegenie.output.sanitizer import OutputSanitizer
from codegenie.probes import default_registry


def _hash_tree(root: Path) -> dict[str, str]:
    """Recursive SHA-256 manifest for fixture-immutability assertions."""
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def _run_gather(repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "codegenie", "gather", "--no-gitignore", str(repo)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def test_two_concurrent_gathers_leave_consistent_cache(tmp_path: Path) -> None:
    """Edge case #12: two `codegenie gather` *processes* against the same
    .codegenie/cache/index.jsonl must both exit 0; index.jsonl parses
    line-by-line; post-finish mode bits are 0600/0700; fixture is unchanged.
    """
    # arrange: copy fixture under tmp_path so cache lives next to it
    fixture_src = Path(__file__).parent.parent / "fixtures" / "js_only"
    fixture = tmp_path / "js_only"
    shutil.copytree(fixture_src, fixture)
    pre_hashes = _hash_tree(fixture)

    # act: two real OS processes, started without synchronization
    p1 = subprocess.Popen(
        [sys.executable, "-m", "codegenie", "gather", "--no-gitignore", str(fixture)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    p2 = subprocess.Popen(
        [sys.executable, "-m", "codegenie", "gather", "--no-gitignore", str(fixture)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    out1, err1 = p1.communicate(timeout=60)
    out2, err2 = p2.communicate(timeout=60)

    # assert 1: both processes exited 0
    assert p1.returncode == 0, f"p1 stderr: {err1!r}"
    assert p2.returncode == 0, f"p2 stderr: {err2!r}"

    cache_root = fixture / ".codegenie" / "cache"

    # assert 2: index.jsonl parses line-by-line — no torn records, no two
    # JSON objects concatenated on one line with no separating newline.
    index_path = cache_root / "index.jsonl"
    assert index_path.exists()
    with index_path.open("rb") as fh:
        for raw_line in fh:
            # one JSON object per line; trailing newline allowed but not multiple objects
            line = raw_line.rstrip(b"\n")
            json.loads(line)
            assert b"}{" not in line, f"two JSON on one line: {line!r}"

    # assert 3: ADR-0011 — every file 0600, every dir 0700, after BOTH
    # subprocesses have fully exited. Extends ADR-0011's post-gather invariant
    # to the concurrent-gather case.
    for entry in cache_root.rglob("*"):
        mode = stat.S_IMODE(entry.stat().st_mode)
        expected = 0o700 if entry.is_dir() else 0o600
        assert mode == expected, f"{entry}: expected {oct(expected)}, got {oct(mode)}"

    # assert 4: audit records — both runs recorded language_detection with
    # cache_hit ∈ {True, False}; combined shape is (False, False) OR
    # (False, True) — never any other combination, never errors.
    runs_dir = fixture / ".codegenie" / "context" / "runs"
    run_files = sorted(runs_dir.glob("*.json"))
    assert len(run_files) >= 2, f"expected ≥2 audit records, got {len(run_files)}"
    cache_hits: list[bool] = []
    for rf in run_files[-2:]:
        record = json.loads(rf.read_text())
        ld = next(
            (pe for pe in record["probe_executions"] if pe["probe"] == "language_detection"),
            None,
        )
        assert ld is not None, f"language_detection missing from {rf}"
        assert ld["exit_status"] == "ok", ld
        cache_hits.append(bool(ld.get("cache_hit", False)))
    assert sorted(cache_hits) in ([False, False], [False, True]), cache_hits

    # assert 5: fixture immutability — neither process wrote into the
    # analyzed-repo tree (excluding the .codegenie/ outputs we created).
    post_hashes = {
        k: v for k, v in _hash_tree(fixture).items() if not k.startswith(".codegenie/")
    }
    pre_filtered = {k: v for k, v in pre_hashes.items() if not k.startswith(".codegenie/")}
    assert post_hashes == pre_filtered, "fixture mutated by gather"


def test_concurrent_then_in_process_third_gather_is_cache_hit(tmp_path: Path) -> None:
    """Metamorphic partner to the concurrent test. Without this, AC-4's
    'two Ran or one Ran + one CacheHit' admits a cache-never-hits regression.

    After the concurrent pair, an in-process third gather against the same
    cache MUST return CacheHit — the cache write path on at least one of
    the two processes wrote a valid blob the third gather can read.
    """
    fixture_src = Path(__file__).parent.parent / "fixtures" / "js_only"
    fixture = tmp_path / "js_only"
    shutil.copytree(fixture_src, fixture)

    # Two concurrent CLI gathers populate the on-disk cache
    p1 = subprocess.Popen([sys.executable, "-m", "codegenie", "gather", "--no-gitignore", str(fixture)])
    p2 = subprocess.Popen([sys.executable, "-m", "codegenie", "gather", "--no-gitignore", str(fixture)])
    assert p1.wait(timeout=60) == 0
    assert p2.wait(timeout=60) == 0

    # Now run a third gather in-process and inspect executions
    cfg = Config()
    snap = build_snapshot(fixture, cfg)
    cache = CacheStore(cache_dir=fixture / ".codegenie" / "cache", ttl_hours=cfg.cache_ttl_hours)
    san = OutputSanitizer()
    probe_classes = default_registry.for_task("__bullet_tracer__", frozenset({"javascript"}))
    probes = [cls() for cls in probe_classes]  # instantiate — for_task returns classes
    result = asyncio.run(gather(snap, "__bullet_tracer__", probes, cfg, cache, san))
    assert isinstance(result.executions["language_detection"], CacheHit), result.executions


def test_perm_restoration_after_concurrent_runs(tmp_path: Path) -> None:
    """After concurrent gathers, dirty one blob's mode to 0644; a subsequent
    gather MUST restore it to 0600. Catches a 'chmod on CacheStore.__init__
    only, never on subsequent puts' regression that the post-run mode walk
    by itself would not catch on a fresh cache directory.
    """
    fixture_src = Path(__file__).parent.parent / "fixtures" / "js_only"
    fixture = tmp_path / "js_only"
    shutil.copytree(fixture_src, fixture)
    assert _run_gather(fixture).returncode == 0
    assert _run_gather(fixture).returncode == 0  # ensure ≥1 blob exists

    cache_root = fixture / ".codegenie" / "cache"
    blob = next(cache_root.rglob("blobs/**/*.json"))
    os.chmod(blob, 0o644)
    assert stat.S_IMODE(blob.stat().st_mode) == 0o644

    # Force a cache write by editing a tracked input so the next gather re-puts
    (fixture / "a.js").write_text((fixture / "a.js").read_text() + "// change\n")
    assert _run_gather(fixture).returncode == 0

    # Either the same blob path was overwritten and re-chmodded, OR a new
    # blob path was written and ALL blob files end up at 0600. Assert the
    # all-blobs-0600 invariant which is the actual ADR-0011 contract.
    for entry in cache_root.rglob("blobs/**/*.json"):
        assert stat.S_IMODE(entry.stat().st_mode) == 0o600, f"{entry}: {oct(stat.S_IMODE(entry.stat().st_mode))}"
```

The test fails initially because either (a) the file does not yet exist (red-on-add), or (b) the under-test surface — process-level concurrent writes to `index.jsonl`, the cross-run `ProbeExecutionRecord` shape, the post-concurrent perm invariant, the fixture-immutability check — is not yet asserted anywhere else in the suite. Run it, confirm failure, commit the failing test as a marker. The green phase should be **test-mechanics only** — the existing `CacheStore` already satisfies the kernel-atomicity invariant per edge case #12 and the chmod discipline per ADR-0011; if any assertion fails for a production-code reason, surface it as a regression bug against S3-01 rather than patching `CacheStore` from this story.

The three bench files do not have a "red" phase in the TDD sense — they are observation harnesses, not behavior tests. Write them green; they assert *nothing* about thresholds.

### Green — make it pass

For `test_cache_concurrent.py`: if the assertions fail for the mode-bit reason, the fix lives in `CacheStore` (re-apply `os.chmod(0o600)` on the blob and `os.chmod(0o700)` on the shard dir after every `put`); this should already be in place from S3-01, so this story should **not** modify `CacheStore` — surface as a regression bug if discovered. If the JSONL line-parse fails, the bug is in `CacheStore.put`'s record-length discipline (records must fit in `PIPE_BUF=4096B`); same surfacing rule. If the metamorphic third-gather is not a `CacheHit`, the bug is in the cache read path — also surface as an S3-01 regression. The test is the gate; it does not introduce code under `src/`.

For the three bench files: each is ~40–60 lines. Use `time.perf_counter`, write to a single shared `bench-results.json` via the atomic merge helper, keyed by per-test top-level keys (`cold_start`, `coordinator_overhead`, `cache_hit_dispatch`). The output path is resolved as `Path(os.environ.get("GITHUB_WORKSPACE", str(tmp_path))) / "bench-results.json"` so locally it lands under tmp_path and in CI it lands at the workflow root for `actions/upload-artifact` to pick up. Each test re-reads the JSON before exit and asserts its key is present with `wall_clock_s > 0` (the bench-not-silently-no-op invariant).

### Refactor — clean up

- Extract the mode-bit-walk into a `_assert_codegenie_perms(root: Path)` helper at the module level so future stories can reuse it.
- Extract the recursive SHA-256 tree-manifest helper into a module-level `_hash_tree(root: Path) -> dict[str, str]` so the fixture-immutability check can be reused by future concurrent-write tests (Phase 14's webhook fan-out).
- Extract the atomic-merge `bench-results.json` writer into a `_merge_bench_result(path: Path, key: str, payload: dict) -> None` helper shared by the three bench test files (place under `tests/bench/_helpers.py`; not under `src/` because it is test-only).
- Type hints throughout; `mypy --strict` clean.
- Docstrings on `_assert_codegenie_perms`, `_hash_tree`, `_merge_bench_result`, and on each bench test's top-level docstring (explaining "advisory only, no merge gate").
- Add `pytest.mark.bench` to the three bench tests; configure `pyproject.toml` markers so `pytest -m "not bench"` is the default local invocation and `pytest -m bench` runs only the canaries.
- Confirm the bench tests honor `--no-network` style invariants — none of them should reach `httpx`/`socket`; `tests/adv/test_no_network_imports.py` from S2 already scans `src/`; for `tests/`, leave a comment that bench tests are exempt from the AST scan but must not network-import.

## Files to touch

| Path | Why |
|---|---|
| `tests/unit/test_cache_concurrent.py` | New file — pins process-level concurrent-write invariant per edge case #12 and ADR-0011; includes metamorphic third-gather + perm-restoration partners. |
| `tests/bench/__init__.py` | New file — empty, marks `tests/bench/` as a package. |
| `tests/bench/_helpers.py` | New file — atomic `bench-results.json` merge writer shared by all three bench tests. |
| `tests/bench/test_cli_cold_start.py` | New file — advisory cold-start canary (median of 5 `sys.executable -m codegenie --help` runs); writes under key `cold_start`. |
| `tests/bench/test_coordinator_overhead.py` | New file — advisory dispatch-overhead canary (one no-op probe through the real coordinator); writes under key `coordinator_overhead`. |
| `tests/bench/test_cache_hit_dispatch.py` | New file — advisory cache-hit ratio canary (second-run / first-run wall-clock) PLUS a non-advisory `isinstance(..., CacheHit)` assertion per ADR-0009; writes under key `cache_hit_dispatch`. |
| `.github/workflows/ci.yml` | Modify — add `bench-collection-guard` step (gating, asserts exactly 3 tests collected) + `bench` step (`continue-on-error: true`) + `actions/upload-artifact@<sha>` for `bench-results.json`. |
| `pyproject.toml` | Modify — register `bench` marker under `[tool.pytest.ini_options]` markers; switch default test selection to `-m "not bench"`. |

## Out of scope

- **Cold-start *gating*** — explicitly deferred; L3 #12 chose `import-linter` as the structural defense in S1-05. Bench is advisory forever; if a future phase wants a gate, it lands then with the ADR amendment.
- **PR-comment posting mechanics (bot wiring, formatting)** — the canaries emit `bench-results.json`; an out-of-scope GitHub Action (filed as a Phase 1 follow-up by S5-02) consumes the artifact and posts the comment. Phase 0 only generates the JSON.
- **Property-based concurrent-write fuzzing** — Phase 5's trust gates are the first phase where property tests earn their keep (`phase-arch-design.md §Property tests`); Phase 0 ships one focused concurrent-write test plus a metamorphic third-gather partner, not a Hypothesis suite.
- **Concurrent writes to the same blob path** — the test ensures both gathers hit the same *cache key*; the underlying blob-write atomicity is asserted in S3-01's `test_cache_store.py`. This story does not re-test the blob-write path.
- **Deterministic interleaving assertions** — asserting that the two subprocess gathers actually ran with overlapping kernel-level file-system contention (rather than the OS scheduler serializing them) would require timestamp instrumentation inside `CacheStore.put` or a `pytest-trio`-style deterministic scheduler. Phase 0 ships the invariant ("both succeed AND the index is consistent AND the audit shape is reachable from both branches") without proving the interleaving happened on every run. Filed as a Phase 5 trust-gate follow-up for property-based concurrent-write fuzzing.
- **NFS / case-insensitive / non-POSIX filesystems** — the test runs under `tmp_path` (local tmpfs in CI, local disk locally). NFS / case-insensitive FS behavior of `O_APPEND` is out of scope for Phase 0; documented here so a future contributor reaching for it knows it is intentional.

## Notes for the implementer

- The concurrent test uses **`subprocess.Popen` two-process invocation** of `sys.executable -m codegenie gather <fixture>`, not `asyncio.gather`. Two asyncio tasks share one OS thread and do not exercise the `O_APPEND` kernel-atomicity guarantee that edge case #12 in `phase-arch-design.md §789` actually names ("Phase 0's two-process test is in `tests/unit/test_cache_concurrent.py`"). Each subprocess bootstraps its own `default_registry` via the CLI entry point — independent processes are how the in-process registry concern resolves, not a reason to avoid them. (validator: prior draft chose async with the rationale that `open(..., 'a')` "uses O_APPEND under the hood and is just as effective" — that conflates the file-mode flag with the contention scenario the invariant is about. Removed.)
- `bench-results.json` should be written atomically (`<tmp> → fsync → os.replace`) so a flaky test doesn't truncate the artifact mid-CI. Reuse `Writer`'s atomic-write helper if convenient; otherwise inline. Each bench test merges under its own top-level key (`cold_start`, `coordinator_overhead`, `cache_hit_dispatch`) so the three tests can run in any order or in parallel and never clobber each other.
- Per edge case #12 in `phase-arch-design.md`: records ≤ 4096B is the `O_APPEND`-atomic threshold; if `CacheStore.put` ever writes longer JSONL records, the invariant breaks. The test does not separately assert record length — that's S3-01's territory — but if the line-parse assertion fails, suspect the record-length discipline before suspecting `O_APPEND` itself.
- Do not import `pytest_benchmark`. It's not in `dev` extras (ADR-0006); adding it would expand the dependency closure for an advisory-only signal. Manual `time.perf_counter` is sufficient.
- The bench tests will be the first tests in `tests/bench/`. The directory does not exist yet; the `__init__.py` marker file plus the three test files create it. The default `make test` invocation must use `-m "not bench"` (filtered out of contributor's local loop). CI's bench step uses `-m bench` explicitly so the marker decides selection, not auto-discovery.
- The `bench-collection-guard` CI step (gating, not advisory) runs `pytest --collect-only -m bench tests/bench/ -q` and asserts the collection count is exactly 3. If a future contributor renames the marker, deletes a bench file, or filters via a glob, this step fails the build before the canaries silently no-op. This is one of two non-advisory invariants the story introduces (the other is the ADR-0009 `CacheHit` assertion inside the dispatch-ratio canary).
- The CI workflow change must keep the actions SHA-pinned per ADR-0002 / `phase-arch-design.md §CI gates`. Look up `actions/upload-artifact`'s current SHA; do not use `@v4`.
- (validator) `default_registry.for_task(...)` returns `tuple[type[Probe], ...]` — probe **classes**. Instantiate before passing to `coordinator.gather`: `probes = [cls() for cls in probe_classes]`. The original red test passed classes directly; that would have raised on first probe attribute access.
- (validator) The real `coordinator.gather` signature is `gather(snapshot, task, probes, config, cache, sanitizer)` — all six are required. The snapshot constructor is `build_snapshot(repo_root, config)`, not `construct_snapshot(fixture)`. `CacheStore` constructor is `CacheStore(cache_dir, ttl_hours)`, not `CacheStore(root=...)`. See `src/codegenie/coordinator/coordinator.py:420`, `src/codegenie/coordinator/snapshot.py:39`, `src/codegenie/cache/store.py` for the authoritative signatures.
