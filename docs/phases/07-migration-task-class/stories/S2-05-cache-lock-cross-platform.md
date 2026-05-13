# Story S2-05 — `cache_lock` cross-platform `flock(2)` wrapper

**Step:** Step 2 — Tool wrappers and the pre-rendered base catalog hot view
**Status:** Ready
**Effort:** M
**Depends on:** S2-04
**ADRs honored:** ADR-P7-002 (cache-lock primitive backs the new sandbox host code under the additive seam), ADR-0014 (regression-suite wall-clock canary — cache locking under contention must not exceed budget)

## Context

Gap 2 (`phase-arch-design.md §Gap analysis — Gap 2`) named a known under-specified concern from the critic: `flock(2)` semantics differ between macOS BSD and Linux fcntl, and the architecture didn't say *where* in the code the cache lock lives, *what* it locks, and *how* a stuck lock is detected. This story closes that gap by landing the lock primitive at `src/codegenie/sandbox/host/cache_lock.py` with three concrete properties: (a) a `with cache_lock(path, timeout_s=30) -> ContextManager` API; (b) a `CacheLockTimeout` typed raise on contention; (c) a cross-platform test matrix (macOS BSD + Linux fcntl + `pyfilelock` fallback) asserting identical behavior.

This primitive will be consumed at three sites (per Gap 2): `tools/buildkit.py` before `--cache-to=type=local`, `tools/grype.py` before DB update, `tools/dockerfile_parse.py` cache write. **None of those wirings happen in this story** — this story owns only the primitive + matrix test. Site wiring is each consumer's responsibility (Phase 5 / phase-arch-design §Component 14 cites the sites; consumers integrate in their own stories or as small follow-up edits inside the dependent stories).

Story S8-03 will re-exercise this matrix on the grype-DB concurrent-refresh path.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Gap analysis — Gap 2` (lines ~1409–1413) — the full specification for the lock primitive, the three consumer sites, the cross-platform test, and stuck-lock detection (`lsof`-on-POSIX PID surface).
  - `../phase-arch-design.md §Open questions deferred to implementation #2` — `flock(2)` cross-platform behavior; macOS BSD vs Linux fcntl semantics for shared-mode acquisition and fork-inheritance.
  - `../phase-arch-design.md §Risks specific to this step` (Step 2 risks) — "`pyfilelock` and native `fcntl.flock` semantics may diverge on edge cases; document the divergence in `cache_lock.py` docstring rather than papering over it."
  - `../phase-arch-design.md §Persisted-on-disk shapes` — `.codegenie/cache/buildkit/`, `.codegenie/cache/grype-db/`, `.codegenie/cache/dockerfile-parse/` are the lockable directories.
- **Phase ADRs:**
  - `../ADRs/0014-regression-suite-wall-clock-canary.md` — locking under contention must not blow the regression-suite wall-clock budget.
- **High-level impl:**
  - `../High-level-impl.md §Step 2` (lines 60–82) — features delivered; risks call out the BSD/fcntl divergence explicitly.

## Goal

`from codegenie.sandbox.host.cache_lock import cache_lock` provides a `with cache_lock(path, timeout_s=30): ...` context manager that acquires an exclusive POSIX lock on macOS BSD, Linux fcntl, and via the `pyfilelock` fallback — raising `CacheLockTimeout(holder_pid: int | None)` identically on each backend.

## Acceptance criteria

- [ ] `src/codegenie/sandbox/host/cache_lock.py` exports `cache_lock(path: Path, *, timeout_s: float = 30, mode: Literal["exclusive","shared"] = "exclusive") -> ContextManager[None]` and the `CacheLockTimeout` exception.
- [ ] When `timeout_s` elapses without acquiring the lock, the wrapper raises `CacheLockTimeout(holder_pid: int | None, lock_path: Path)`. `holder_pid` is best-effort from `lsof <path>` on POSIX (returns `None` if `lsof` unavailable or returns no holder).
- [ ] On contention, an `audit.cache.lock.stuck` event is emitted via `structlog` (per Gap 2) with `lock_path`, `holder_pid`, and `wall_clock_ms`. No raw `lsof` output goes to the logger.
- [ ] **Cross-platform test matrix** in `tests/integration/test_cache_lock_matrix.py` asserts identical behavior on macOS BSD `fcntl.flock` and Linux fcntl. The same scenario (Process A acquires → Process B blocks → A releases → B acquires within budget) passes on both. CI matrix-tags the test for both runner OSes.
- [ ] A fallback path using `pyfilelock` is invoked when `fcntl` is unavailable (Windows / hypothetical edge); a unit test patches the import to exercise the fallback branch.
- [ ] Module docstring documents *known semantic divergences* between BSD `fcntl.flock`, Linux fcntl, and `pyfilelock` (e.g., fork inheritance, shared-mode upgrades) — per High-level-impl §Step 2 risk.
- [ ] The TDD plan's red tests exist, were committed, and are green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, `pytest tests/unit/sandbox/host/test_cache_lock.py` and `pytest tests/integration/test_cache_lock_matrix.py` all pass.

## Implementation outline

1. Write failing tests in `tests/unit/sandbox/host/test_cache_lock.py` covering: happy acquire/release, timeout raises `CacheLockTimeout`, stuck-lock detection populates `holder_pid` on POSIX, fallback branch via `pyfilelock`. Commit.
2. Write `tests/integration/test_cache_lock_matrix.py` — multi-process scenario via `multiprocessing.Process`; the test self-parametrizes by `sys.platform` and is markered `@pytest.mark.cross_platform` so CI matrix lights up both runners (Gap 2).
3. Implement the context manager in `src/codegenie/sandbox/host/cache_lock.py`:
   - Detect `fcntl` availability at import time. If absent, route through `pyfilelock`.
   - On `fcntl` path: open the lock file with `os.open(path, O_RDWR | O_CREAT, 0o600)`; call `fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)` in a poll loop with `time.monotonic()` + a small sleep; on timeout, attempt `lsof <path>` to harvest holder PID; raise `CacheLockTimeout(holder_pid, lock_path)`.
   - On `__exit__`: release with `fcntl.flock(fd, fcntl.LOCK_UN)` and `os.close(fd)`.
4. Stuck-lock detection: a small helper `_holder_pid_via_lsof(path) -> int | None` running `subprocess.run(["lsof", str(path)], ...)` and parsing the second-line PID column. On `FileNotFoundError` (no `lsof`) → `None`.
5. Emit `structlog` `cache.lock.stuck` event on timeout (per Gap 2).
6. Refactor; add module docstring with the divergence notes; mypy strict.

## TDD plan — red / green / refactor

### Red — write the failing tests first

Test file path: `tests/unit/sandbox/host/test_cache_lock.py`

```python
# tests/unit/sandbox/host/test_cache_lock.py
import multiprocessing
import time
from pathlib import Path
import pytest
from codegenie.sandbox.host.cache_lock import cache_lock, CacheLockTimeout


def test_cache_lock_acquire_release_happy(tmp_path):
    """Single-process acquire + release within budget — no exception."""
    lockfile = tmp_path / "cache.lock"
    with cache_lock(lockfile, timeout_s=2):
        # critical section — file is locked here
        assert lockfile.exists()
    # released cleanly; second acquire should succeed immediately
    with cache_lock(lockfile, timeout_s=2):
        pass


def _holder(lockfile, ready, release):
    """Helper run in a child process: acquires the lock, signals ready,
    holds until told to release."""
    with cache_lock(Path(lockfile), timeout_s=5):
        ready.set()
        release.wait(timeout=10)


def test_cache_lock_timeout_raises_typed(tmp_path):
    """Contention beyond timeout → CacheLockTimeout (not generic TimeoutError)."""
    lockfile = tmp_path / "cache.lock"
    ctx = multiprocessing.get_context("spawn")
    ready = ctx.Event()
    release = ctx.Event()
    p = ctx.Process(target=_holder, args=(str(lockfile), ready, release))
    p.start()
    try:
        assert ready.wait(timeout=5), "child failed to acquire"
        # parent now tries with a small budget; child still holds → timeout
        with pytest.raises(CacheLockTimeout) as exc:
            with cache_lock(lockfile, timeout_s=0.5):
                pass
        assert exc.value.lock_path == lockfile
    finally:
        release.set()
        p.join(timeout=5)


def test_cache_lock_timeout_reports_holder_pid_when_lsof_available(tmp_path, monkeypatch):
    """holder_pid populated via lsof on POSIX; None when lsof absent."""
    lockfile = tmp_path / "cache.lock"
    # Force the lsof helper to return a known PID for this test
    monkeypatch.setattr(
        "codegenie.sandbox.host.cache_lock._holder_pid_via_lsof",
        lambda p: 12345,
    )
    ctx = multiprocessing.get_context("spawn")
    ready = ctx.Event()
    release = ctx.Event()
    p = ctx.Process(target=_holder, args=(str(lockfile), ready, release))
    p.start()
    try:
        assert ready.wait(timeout=5)
        with pytest.raises(CacheLockTimeout) as exc:
            with cache_lock(lockfile, timeout_s=0.5):
                pass
        assert exc.value.holder_pid == 12345
    finally:
        release.set()
        p.join(timeout=5)
```

Test file path: `tests/integration/test_cache_lock_matrix.py`

```python
# tests/integration/test_cache_lock_matrix.py
import multiprocessing
import sys
from pathlib import Path
import pytest
from codegenie.sandbox.host.cache_lock import cache_lock, CacheLockTimeout


@pytest.mark.cross_platform
@pytest.mark.parametrize("platform_marker", [sys.platform])
def test_cache_lock_matrix_acquire_then_release(tmp_path, platform_marker):
    """Same behavior on macOS BSD flock and Linux fcntl: A acquires → B blocks → A
    releases → B acquires within budget."""
    lockfile = tmp_path / "cache.lock"
    ctx = multiprocessing.get_context("spawn")
    ready_a = ctx.Event()
    release_a = ctx.Event()
    done_b = ctx.Event()

    def proc_a(lf, ready, release):
        with cache_lock(Path(lf), timeout_s=5):
            ready.set()
            release.wait(timeout=10)

    def proc_b(lf, done):
        with cache_lock(Path(lf), timeout_s=10):
            done.set()

    pa = ctx.Process(target=proc_a, args=(str(lockfile), ready_a, release_a))
    pb = ctx.Process(target=proc_b, args=(str(lockfile), done_b))
    pa.start()
    assert ready_a.wait(timeout=5)
    pb.start()
    # Give B a moment to confirm it is blocked
    assert not done_b.wait(timeout=0.5)
    release_a.set()
    pa.join(timeout=5)
    assert done_b.wait(timeout=5), "B failed to acquire after A released"
    pb.join(timeout=5)
```

The unit tests should fail with `ImportError`. The integration matrix test requires `pytest -k matrix --runslow`-style gating; ensure CI runs it under both macOS and Linux runners.

### Green — make it pass

- Implement `cache_lock` as a `@contextmanager` decorated function. Poll-and-sleep loop with `time.monotonic()` for the budget — do **not** use `time.time()` (clock-jumps).
- Backend selection at import time: `try: import fcntl` → on success, use the fcntl path; on `ImportError`, fall back to `pyfilelock`. Document both.
- `CacheLockTimeout` carries `holder_pid: int | None` and `lock_path: Path`.

### Refactor — clean up

- Type hints; module docstring documenting the BSD/fcntl/pyfilelock divergence (fork inheritance, shared-mode upgrade behavior, mandatory-locks-on-Linux caveat).
- `structlog` `cache.lock.stuck` audit event with the timeout context.
- Ensure the poll loop's sleep is bounded (e.g., 50 ms) so timeouts are honored within ~100 ms of `timeout_s`.
- The module exposes `mode="shared"` for read-mostly cache reads — but only `"exclusive"` is exercised by the consumers named in Gap 2. Mark `shared` as an intentional capability with an inline comment, and add a one-line test that acquires in shared mode successfully (no contention semantics asserted yet).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/sandbox/host/cache_lock.py` | New — primitive + `CacheLockTimeout`. |
| `src/codegenie/sandbox/host/__init__.py` | Confirm exports include `cache_lock`, `CacheLockTimeout`. |
| `tests/unit/sandbox/host/test_cache_lock.py` | New — unit tests: happy, timeout, holder PID, fallback branch. |
| `tests/integration/test_cache_lock_matrix.py` | New — Gap 2 cross-platform matrix. |
| `pyproject.toml` | Add `filelock` (the `pyfilelock` package — its PyPI name is `filelock`) under dependencies if not already present. |

## Out of scope

- **Wiring consumers** (`tools/buildkit.py`, `tools/grype.py`, `tools/dockerfile_parse.py`) — the three sites Gap 2 names are the consumers' responsibility. This story owns the primitive + matrix test only.
- **Grype-DB concurrent refresh** — S8-03 re-exercises this matrix in the grype context.
- **Distributed (cross-host) locking** — Phase 9 Temporal idempotency owns that; here we cover single-host cross-process only.
- **Shared-mode contention semantics** — `mode="shared"` is exposed but not exhaustively tested; if a future consumer relies on shared mode, the test matrix gets extended in that consumer's story.

## Notes for the implementer

- **macOS BSD vs Linux fcntl divergence is real.** Two known traps: (1) on macOS, `fcntl.flock` is the BSD `flock(2)` system call (advisory, file-descriptor-bound); on Linux, it's also `flock(2)` advisory locking via the `flock` syscall — but `pyfilelock`'s default backend on Linux uses `fcntl.fcntl` (POSIX advisory record locks, which are *process-bound*, not FD-bound). Pick one syscall (`fcntl.flock`) and use it consistently on both POSIX platforms; only fall back to `pyfilelock` when `fcntl` is unimportable.
- Document the divergence in the module docstring (Rule 12 — fail loud + document, don't paper over).
- The poll-loop sleep granularity matters. 50 ms is sane; 10 ms wastes CPU; 250 ms misses timeouts. Use `time.monotonic()` for the budget computation — `time.time()` jumps if the system clock is corrected.
- `lsof` may return rapidly or hang on busy systems. Cap its subprocess wall-clock at 1 s and treat overrun as "holder unknown" (`None`). Do not wait for `lsof` to return on the critical path.
- Per Gap 2, the audit event is `cache.lock.stuck` (not `cache.lock.timeout`). Wording matches the architecture doc — keep it stable; downstream Phase 11 (Handoff) reads audit events by exact name.
- `pyfilelock` on Linux defaults to a fcntl POSIX backend; that's *not* equivalent to `fcntl.flock` on macOS. The fallback path is intentionally lower-fidelity; the docstring must say so.
- Do not use `mode="shared"` for the consumers Gap 2 names — they all need exclusive access (buildkit `--cache-to`, grype DB update, dockerfile-parse cache write).
- The module **must not** import from `codegenie.coordinator` or any Phase 2 internal (fence-CI). The lock is host-side infrastructure, not a probe.
