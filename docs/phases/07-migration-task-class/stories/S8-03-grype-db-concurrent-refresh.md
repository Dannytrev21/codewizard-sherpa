# Story S8-03 — Grype-DB concurrent-refresh cross-OS matrix

**Step:** Step 8 — Pre-flight final regression and snapshot-discipline rehearsal
**Status:** Ready
**Effort:** S
**Depends on:** S8-02
**ADRs honored:** ADR-P7-002, ADR-0009

## Context

Two distroless workflows running concurrently on the same machine can race on the Grype vulnerability database's `.last_update` sentinel — the file that signals when the local DB was last refreshed. Phase 7 leans on `flock(2)` to serialize those refreshes (see `phase-arch-design.md §Edge cases #9`), but `flock(2)`'s semantics differ subtly between macOS (BSD `flock`) and Linux (`fcntl.flock` / `fcntl.lockf`): on macOS, BSD flock locks are per-open-file-handle, not per-process, and fork-inheritance differs. The critic flagged this as a documented blind spot (`critique.md §performance.assumption.1`).

S2-05 (`cache_lock` cross-platform wrapper) already lights up a generic flock matrix test. This story is the **task-specific** application of that test to the Grype DB case: launch N workers under the same `cache_lock(grype_db_sentinel, timeout_s=...)` and assert exactly one performs the refresh while the rest wait, observe the fresh sentinel, and skip. The test runs on both macOS and Linux CI matrices. This closes the documented blind spot before merge and is the third of four Step-8 pre-flight gates.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Edge cases #9` — "Grype DB update race across workflows → `flock(2)` on sentinel; first arriver wins; CI matrix includes macOS BSD flock + Linux fcntl flock."
  - `../phase-arch-design.md §Testing strategy ›Test pyramid ›Integration tests` — names `tests/integration/test_grype_db_concurrent_refresh.py` as part of the Phase 7 integration suite.
  - `../phase-arch-design.md §Open questions deferred to implementation #2` — "`flock(2)` cross-platform behavior; macOS BSD vs Linux fcntl semantics for shared-mode acquisition and fork-inheritance. CI matrix per Gap 2."
  - `../phase-arch-design.md §Gap 2` — the canonical motivation for `cache_lock` as the `flock` chokepoint that all Phase 7 callers go through.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0003-objective-signals-widening-and-allowlists.md` — ADR-P7-002 — `grype` binary must be on `ALLOWED_BINARIES` (verify via S1-03's allowlist).
  - `../ADRs/0009-contract-surface-snapshot-canary.md` — ADR-0009 — this test is new file only; do not touch `tools/contract-surface.snapshot.json`.
- **Existing code:**
  - `src/codegenie/sandbox/host/cache_lock.py` (from S2-05) — the chokepoint this test exercises. Read its docstring for the documented macOS-vs-Linux divergences.
  - `tests/integration/test_cache_lock_matrix.py` (from S2-05) — the generic matrix test. This story's test is the *task-specific* twin.
  - `src/codegenie/sandbox/host/allowed_binaries.py` — confirm `grype` is allowlisted (it should already be; if not, surface as a blocker).
  - `.codegenie/cache/grype-db/` — the on-disk shape; the sentinel filename (`.last_update` or whatever the codebase actually uses).
- **External docs:**
  - https://man7.org/linux/man-pages/man2/flock.2.html — Linux `flock(2)`.
  - https://www.freebsd.org/cgi/man.cgi?flock(2) — BSD `flock(2)` (the macOS surface).

## Goal

`pytest tests/integration/test_grype_db_concurrent_refresh.py` is green on both macOS and Linux CI runners; concurrent workers race the Grype DB refresh and exactly one performs it while the rest see a fresh sentinel.

## Acceptance criteria

- [ ] `tests/integration/test_grype_db_concurrent_refresh.py` exists and runs the same scenario under macOS BSD flock + Linux fcntl flock via the existing CI matrix that S2-05 set up (`runs-on: [ubuntu-latest, macos-latest]` or repo equivalent).
- [ ] Test launches N ≥ 4 concurrent workers (via `multiprocessing` or `subprocess`) that each call into the Grype-DB refresh path under `cache_lock`.
- [ ] Test asserts exactly one worker actually invokes `grype db update` (or whatever the codebase's refresh entry is) — verified by inspecting a side-effect counter (file-write count, log line count, or process-spawn count).
- [ ] Test asserts the other N-1 workers either (a) observed a fresh `.last_update` sentinel before acquiring the lock and skipped, or (b) acquired the lock after the winner and saw the freshly-written sentinel and skipped.
- [ ] Test asserts the post-test `.last_update` mtime is `> test_start_time` and `<= test_end_time` — i.e., the refresh actually happened exactly once.
- [ ] Test imports and uses `src/codegenie/sandbox/host/cache_lock.py` directly — does **not** re-implement `flock` semantics inline.
- [ ] CI matrix is wired such that the test runs on `macos-latest` and `ubuntu-latest` (or repo equivalents); failure on either blocks merge.
- [ ] The TDD plan's red test exists, was committed, and is green.
- [ ] `ruff check`, `ruff format --check`, and `mypy --strict` all pass on the touched files.

## Implementation outline

1. Write the failing red test that asserts the file exists, runs N workers, and that exactly one performs the refresh.
2. Build a small `_grype_refresh_worker.py` helper (subprocess entry point) that takes `(sentinel_path, lock_path)`, uses `cache_lock(lock_path, timeout_s=30)` from S2-05, double-checks the sentinel inside the lock for freshness, and either refreshes (writing the sentinel + emitting a side-effect marker) or skips.
3. The test fixture pre-creates a stale `.last_update` (mtime older than the refresh threshold) so refresh must trigger.
4. Spawn N workers in parallel using `multiprocessing.Pool` or `subprocess.Popen`; wait for all; assert exactly one wrote the side-effect marker.
5. Add CI matrix entries (or confirm S2-05's matrix already covers this test via path glob).
6. Refactor: factor out the worker into a fixture module if used by other Step 8 stories.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/integration/test_grype_db_concurrent_refresh.py`

```python
# tests/integration/test_grype_db_concurrent_refresh.py
"""Cross-OS matrix: concurrent workers race the Grype DB refresh under cache_lock.

Closes phase-arch-design.md §Edge cases #9 and the critic blind spot
perf.assumption.1 (macOS BSD flock vs Linux fcntl flock divergence).
Pairs with S2-05's generic test_cache_lock_matrix.py."""
import multiprocessing as mp
import os
import sys
import time
from pathlib import Path

import pytest

# Helper that S2-05 already exposes; this test's worker calls into it.
from codegenie.sandbox.host.cache_lock import cache_lock

N_WORKERS = 4
REFRESH_THRESHOLD_S = 60  # the codebase's "stale if older than" threshold


def _worker(args: tuple[str, str, str]) -> bool:
    sentinel_path_s, lock_path_s, marker_dir_s = args
    sentinel = Path(sentinel_path_s)
    marker_dir = Path(marker_dir_s)
    with cache_lock(Path(lock_path_s), timeout_s=30):
        # Double-check freshness inside the lock — first arriver refreshes, rest skip.
        now = time.time()
        try:
            age = now - sentinel.stat().st_mtime
        except FileNotFoundError:
            age = float("inf")
        if age > REFRESH_THRESHOLD_S:
            # "Refresh" — write the sentinel and emit a unique marker file.
            sentinel.write_text(str(now))
            (marker_dir / f"refreshed-{os.getpid()}").write_text("ok")
            return True
        return False


@pytest.mark.integration
def test_grype_db_refresh_runs_exactly_once_under_concurrent_workers(tmp_path: Path) -> None:
    sentinel = tmp_path / ".last_update"
    lock = tmp_path / ".last_update.lock"
    marker_dir = tmp_path / "markers"
    marker_dir.mkdir()
    # Pre-create a stale sentinel.
    sentinel.write_text("stale")
    os.utime(sentinel, (time.time() - 3600, time.time() - 3600))

    started = time.time()
    args = [(str(sentinel), str(lock), str(marker_dir))] * N_WORKERS
    ctx = mp.get_context("spawn")  # explicit; macOS default differs from Linux
    with ctx.Pool(N_WORKERS) as pool:
        results = pool.map(_worker, args)
    ended = time.time()

    refresher_count = sum(1 for r in results if r)
    assert refresher_count == 1, (
        f"Expected exactly one refresh under cache_lock; got {refresher_count}. "
        f"This indicates flock semantics differ on this platform "
        f"({sys.platform}) from the Phase 7 assumption."
    )
    markers = list(marker_dir.iterdir())
    assert len(markers) == 1, f"Expected one marker file; got {[m.name for m in markers]}"
    mtime = sentinel.stat().st_mtime
    assert started <= mtime <= ended, (
        f"Sentinel mtime {mtime} not within test window [{started}, {ended}]"
    )
```

Run it. It will fail with `ImportError` on `cache_lock` (if S2-05 isn't fully wired into the package surface yet) or with `ModuleNotFoundError`. Either is a valid red. Commit.

### Green — make it pass

There's no new product code to write — `cache_lock` is from S2-05. The "green" step is wiring imports correctly and confirming the test passes on the local platform.

If the test fails on macOS but passes on Linux (or vice versa), do **not** weaken the test — surface it. The point of this test is to catch exactly that divergence. The remediation belongs in `cache_lock.py` (S2-05's responsibility), not here. File a defect against `cache_lock.py`, fix it there, and rerun.

### Refactor — clean up

- Add the CI matrix wiring: confirm `.github/workflows/<integration-lane>.yml` (or repo equivalent) runs `tests/integration/test_grype_db_concurrent_refresh.py` on both `macos-latest` and `ubuntu-latest`. If S2-05 already added `tests/integration/test_cache_lock_*.py` to the matrix via a glob, this file inherits the matrix; otherwise add an explicit entry.
- Type-hint the worker function fully.
- Docstring referencing edge case #9 and Gap 2.
- Add a `pytest.mark.integration` marker if the repo convention separates integration tests from unit tests.

## Files to touch

| Path | Why |
|---|---|
| `tests/integration/test_grype_db_concurrent_refresh.py` | New file — closes critic blind spot perf.assumption.1; the task-specific twin of S2-05's generic flock matrix test. |
| `.github/workflows/<integration-lane>.yml` (if needed) | Ensure macOS + Linux CI matrix runs this file. |
| `docs/phases/07-migration-task-class/stories/S8-03-grype-db-concurrent-refresh.md` | Status update on completion. |

## Out of scope

- **Implementing or fixing `cache_lock`'s cross-platform semantics.** S2-05 owns `cache_lock.py`. If this story's test fails on one platform, file a defect against S2-05, do not patch the lock here.
- **Generic flock matrix coverage.** S2-05's `test_cache_lock_matrix.py` is that test. This story is task-specific.
- **Buildkit cache-IO race.** Edge case #8; not the same race as #9. Out of scope here.
- **Running an actual `grype` binary.** The test exercises the *lock contract*, not the Grype CLI. A side-effect-emitting fake refresher is sufficient.

## Notes for the implementer

- macOS BSD `flock` and Linux `fcntl.flock` have one famously asymmetric behavior: when a process opens the same lock file twice from two threads and calls `flock`, BSD allows both to hold (per-fd locks) while Linux's `flock` is per-open-file-description. The `_worker` here forks via `spawn` to dodge both — fresh process, fresh open. If a future refactor switches to `mp.get_context("fork")` on Linux for speed, this test may start passing for the wrong reason.
- The `multiprocessing.spawn` context is mandatory on macOS (it's the default there); making it explicit on Linux too means the test behaves identically across platforms.
- If `cache_lock` uses `pyfilelock` as a cross-platform fallback (per S2-05's docstring), the test should still pass — `pyfilelock` serializes correctly even where native `flock` semantics differ.
- The "refresh threshold" (60 s in the example) should match whatever the codebase actually uses for staleness; check `src/codegenie/sandbox/host/` for the canonical constant and import it rather than hardcoding.
- Per CLAUDE.md Rule 12 (Fail loud): if the test passes with `refresher_count == 0` on some platform (e.g., everyone saw a fresh sentinel because timing was unlucky), the assertion `== 1` correctly red-fails. Resist the urge to weaken to `<= 1`.
- The `tmp_path` fixture creates a fresh directory per test, so prior test state cannot leak. If you're tempted to use `.codegenie/cache/grype-db/` for "realism," don't — that pollutes the dev machine's actual cache.
- Per `phase-arch-design.md §Open questions deferred to implementation #2`, this test is the on-disk witness that the Phase 7 assumption about cross-platform flock holds. If it fails, the deferred question is *resolved*: bump `cache_lock` to use `pyfilelock` unconditionally (S2-05's call) rather than papering over it here.
