# Story S7-04 — Concurrent-remediate `fcntl.flock` + `RepoAlreadyInProgress`

**Step:** Step 7 — Adversarial test suite + performance regression gates
**Status:** Ready
**Effort:** S
**Depends on:** S7-03
**ADRs honored:** ADR-0007 (pre-execute marker — lock must be acquired before the marker)

## Context

`phase-arch-design.md §Edge case 18` documents that two concurrent `codegenie remediate` invocations against the same repo would race on `.codegenie/` writes — the `attempts.jsonl`, the cost ledger, and the per-attempt sandbox dirs all assume a single writer. This story adds a `fcntl.flock`-based exclusive lock at `.codegenie/remediation/.lock` acquired before any sandbox call, a `RepoAlreadyInProgress` typed error raised on contention, and the integration test that boots two processes against the same fixture to prove the second one refuses cleanly.

## References — where to look

- **Architecture:** `../phase-arch-design.md §Edge cases` row 18 — exact behavior spec
- **Architecture:** `../phase-arch-design.md §Component 5 GateRunner` — wiring point (constructor-level lock acquisition before `run()` is callable)
- **Phase ADRs:** `../ADRs/0007-pre-execute-marker-for-resume-safety.md` — the lock must wrap the marker, not the other way
- **Implementation plan:** `../High-level-impl.md §Step 7` — names `tests/integration/sandbox/test_concurrent_remediate.py`
- **Existing code:** `src/codegenie/sandbox/errors.py` (from S1-01) — add `RepoAlreadyInProgress(CodegenieError)`
- **Existing code:** `src/codegenie/gates/runner.py` (from S5-02, S7-03) — lock acquisition site
- **Existing code:** `src/codegenie/cli/remediate.py` (the operator-entry, lands in Step 8 for full flag wiring; lock is acquired at orchestrator entry regardless)

## Goal

Land `fcntl.flock(LOCK_EX | LOCK_NB)` acquisition at `.codegenie/remediation/.lock` on `GateRunner` (or orchestrator) start, with a `RepoAlreadyInProgress` error raised on contention and a real-process integration test that proves the second `codegenie remediate` exits cleanly.

## Acceptance criteria

- [ ] `src/codegenie/sandbox/errors.py` (or equivalent existing errors module) exports `class RepoAlreadyInProgress(CodegenieError)` with a `lock_path: Path` and `holder_pid: int | None` attribute (PID best-effort; `None` if not readable).
- [ ] A new module `src/codegenie/sandbox/repo_lock.py` exposes `acquire_repo_lock(repo_root: Path) -> AbstractContextManager[None]` that opens (creates if needed) `.codegenie/remediation/.lock`, calls `fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)`, writes the current PID to the file body, and releases on `__exit__`.
- [ ] On `BlockingIOError` from `flock`, `acquire_repo_lock` reads the existing file body to extract `holder_pid` (best-effort) and raises `RepoAlreadyInProgress(lock_path=..., holder_pid=...)`.
- [ ] `GateRunner.__init__` (or the orchestrator wrapper) acquires the lock via `contextlib.ExitStack`; the lock is held for the lifetime of the `GateRunner` instance and released at process exit. The lock acquisition happens *before* any `RetryLedger.record_pre_execute` call (ADR-0007 invariant — marker is inside the lock).
- [ ] `tests/sandbox/test_repo_lock.py` (unit, ≤ 80 lines): asserts (a) acquiring on a fresh repo writes the current PID; (b) acquiring twice in the same process is rejected with `RepoAlreadyInProgress`; (c) releasing the lock allows re-acquisition; (d) the lock file is left on disk after release (the file is the lock target — not the holder marker).
- [ ] `tests/integration/sandbox/test_concurrent_remediate.py` (integration, real subprocess): spawns two `codegenie remediate --cve <fixture-cve> --sandbox-backend did` processes targeting the same repo with a small artificial delay between them; asserts the second process exits with code 14 (mapped from `RepoAlreadyInProgress`) and stderr containing `repo already in progress`; the first process's gate run completes normally and produces a `attempts.jsonl` with at least one row.
- [ ] CLI exit-code mapping for `RepoAlreadyInProgress` is `14` (declared in `cli/exit_codes.py` constants); a unit test pins the integer.
- [ ] Lock acquisition emits a structured `repo_lock.acquired` event with `{lock_path, pid}`; lock release emits `repo_lock.released`.
- [ ] TDD plan's red test exists, is committed, and is green.
- [ ] `ruff`, `mypy --strict`, `pytest` pass.

## Implementation outline

1. Add `RepoAlreadyInProgress` to the errors module. It is **not** a `SandboxBackendError` — it precedes any sandbox call.
2. Add `EXIT_REPO_ALREADY_IN_PROGRESS = 14` to `cli/exit_codes.py`.
3. Write `src/codegenie/sandbox/repo_lock.py`:
   - `acquire_repo_lock(repo_root)` opens `repo_root / ".codegenie/remediation/.lock"` with `os.O_CREAT | os.O_RDWR`, calls `fcntl.flock(fd, LOCK_EX | LOCK_NB)`, on success truncates and writes `f"{os.getpid()}\n"`, fsyncs, yields, then `flock(fd, LOCK_UN)` and `close(fd)` on exit.
   - On `BlockingIOError`, read existing body, parse first line as int (try/except), raise `RepoAlreadyInProgress`.
   - Use `contextlib.contextmanager`.
4. Wire the lock at the orchestrator entry point. Two options: (a) inside `GateRunner.__init__` if the runner is the orchestration root; (b) inside `cli/remediate.py` if the runner is constructed per-gate. Pick whichever currently constructs the per-run `.codegenie/remediation/<run-id>/` dir; that is the natural lock owner. Wire via `ExitStack.enter_context(acquire_repo_lock(repo_root))` so cleanup happens on any exit path.
5. Map the typed error to CLI exit 14 in the top-level Click error handler.
6. Write the unit test first against `acquire_repo_lock` in isolation.
7. Write the integration test: use `subprocess.Popen` for the second process; assert via `proc.wait(timeout=...)` and `proc.returncode == 14`. Use `tests/fixtures/repos/hello-node/` so the test does not require the breaking-change-cve LLM cassette.
8. Confirm the lock survives `KeyboardInterrupt` mid-run — covered by the `ExitStack` wrapping; add a unit test that raises mid-context and asserts the lock is released.

## TDD plan — red / green / refactor

### Red

Test file path: `tests/sandbox/test_repo_lock.py`

```python
import os
from pathlib import Path

import pytest

from codegenie.sandbox.repo_lock import acquire_repo_lock
from codegenie.sandbox.errors import RepoAlreadyInProgress


def test_double_acquire_raises_repo_already_in_progress(tmp_path: Path) -> None:
    """Edge case 18 — concurrent remediates on the same repo refuse cleanly.

    Why this matters: without the lock, two concurrent runs would interleave
    writes to attempts.jsonl, corrupting the BLAKE3 chain silently. The
    refusal is the contract: 'no silent races on .codegenie/'.
    """
    (tmp_path / ".codegenie/remediation").mkdir(parents=True)

    with acquire_repo_lock(tmp_path) as _outer:
        with pytest.raises(RepoAlreadyInProgress) as excinfo:
            with acquire_repo_lock(tmp_path):
                pytest.fail("second acquire must not succeed")

        assert excinfo.value.lock_path == tmp_path / ".codegenie/remediation/.lock"
        assert excinfo.value.holder_pid == os.getpid()


def test_release_allows_reacquire(tmp_path: Path) -> None:
    (tmp_path / ".codegenie/remediation").mkdir(parents=True)
    with acquire_repo_lock(tmp_path):
        pass
    with acquire_repo_lock(tmp_path):
        pass  # no raise — lock was released


def test_exception_in_context_still_releases_lock(tmp_path: Path) -> None:
    (tmp_path / ".codegenie/remediation").mkdir(parents=True)
    with pytest.raises(RuntimeError):
        with acquire_repo_lock(tmp_path):
            raise RuntimeError("oops")
    # If the lock leaked, the next acquire would raise RepoAlreadyInProgress.
    with acquire_repo_lock(tmp_path):
        pass
```

### Green

1. Implement `acquire_repo_lock`.
2. Confirm the unit tests pass.
3. Wire into orchestrator entry; add a test that constructing two `GateRunner` instances in the same process against the same `repo_root` raises `RepoAlreadyInProgress`.
4. Write the subprocess integration test; assert exit 14 on the contender.

### Refactor

- Move the PID-write/parse to a tiny `_pid_marker.py` helper if it grows beyond ~15 lines (it should not).
- Confirm `fcntl` is imported lazily so Windows test collection (even though Phase 5 is POSIX-only) does not break import-time discovery.
- Add a `# POSIX-only: fcntl` comment at the top of `repo_lock.py`.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/sandbox/errors.py` | Add `RepoAlreadyInProgress` |
| `src/codegenie/cli/exit_codes.py` | Add `EXIT_REPO_ALREADY_IN_PROGRESS = 14` |
| `src/codegenie/sandbox/repo_lock.py` | New — `acquire_repo_lock` context manager |
| `src/codegenie/gates/runner.py` (or `cli/remediate.py`) | Wire `ExitStack.enter_context(acquire_repo_lock(...))` at run entry |
| `src/codegenie/cli/_errors.py` | Map `RepoAlreadyInProgress` → exit 14 |
| `tests/sandbox/test_repo_lock.py` | Unit suite for lock semantics |
| `tests/integration/sandbox/test_concurrent_remediate.py` | Real-subprocess integration test |

## Out of scope

- Cross-host locking. Phase 5 is single-host; concurrent runs across machines on a shared filesystem are a Phase 9 (Temporal) concern.
- Lock breaking / `--force-unlock`. If a stale lock from a crashed process blocks new runs, the operator's manual remediation is `rm .codegenie/remediation/.lock`. A future `codegenie sandbox unlock` command may land in Step 8 if needed.
- Lock-holder identity beyond PID (e.g., hostname, start-time). PID-only is enough to surface in the error message; richer fields are deferred.
- Migrating non-locked legacy runs. Phase 5 is greenfield; no migration needed.

## Notes for the implementer

1. **`fcntl.flock` is advisory.** A process that does not call `flock` can still write to `.codegenie/`. The lock protects only against other `codegenie` invocations — that is the threat model; do not over-engineer to defend against rogue editors.
2. **`LOCK_NB` is required.** Without it, the second process blocks indefinitely waiting for the first to finish. The architecture wants explicit refusal, not patient waiting.
3. **Lock must be acquired BEFORE `RetryLedger.record_pre_execute`** (ADR-0007). The marker is inside the lock; otherwise two processes could race on marker writes before either knows it lost the lock.
4. **Write the PID after flock, not before.** Otherwise a torn write could surface a stale PID to the contender.
5. **`tmp_path` in tests must not be on a filesystem that does not support flock** (e.g., some FUSE mounts). pytest's `tmp_path` is local — fine. If CI uses a non-flock filesystem, surface the issue rather than monkey-patching.
6. **The integration test must not depend on Phase 4's LLM cassette.** Use `hello-node` and let the first process succeed normally; the contention happens on the lock acquisition, which is well before the LLM ever runs.
