# Story S8-01 — Replay-after-kill multiprocessing canary

**Step:** Step 8 — Replay-after-kill canary (G2)
**Status:** Ready
**Effort:** M
**Depends on:** S2-04, S6-03
**ADRs honored:** ADR-0006, ADR-0007, ADR-0011

## Context
This is the load-bearing test for the roadmap exit criterion *"Mid-run kill + resume works without state loss"* (G2). Every prior story in Phase 6 — the checkpointer, the chain extension, the per-gate retry counter, the HITL plumbing — exists so that *this test* can pass: a process is SIGKILL'd while `validate_in_sandbox` is running (Phase 5's longest node — sandbox boot is ~50 s wall clock), a fresh subprocess re-invokes `build_vuln_loop(...).ainvoke(None, config={"configurable": {"thread_id": workflow_id}})` against the same per-workflow `.sqlite3` file, and the final `report.json` + `attempts.jsonl` come out **byte-identical** to a non-killed reference run.

The Scenario-3 sequence diagram in the arch design (`phase-arch-design.md §Process view — Scenario 3`) describes the durability invariant: at any node boundary, the last fsync'd checkpoint frame is intact, and the in-flight WAL frame is rolled back by aiosqlite on the next process open. There is **no application-level fsync, no background flush, no delta encoding** — ADR-0011 is explicit that WAL+NORMAL inside aiosqlite is the only durability primitive. If this story fails, the most likely root cause is *somebody added an `os.fsync` somewhere*, or the canonical-JSON serializer dropped a key — not the test infrastructure.

The kill harness uses `multiprocessing.Process` (not `subprocess`) so the parent can `os.kill(child.pid, signal.SIGKILL)` deterministically at a parametrized delay, and the child runs `asyncio.run(_run_child(workflow_id, tmp_root))` directly without an extra CLI shell round-trip. Parametrize the kill delay over `1s`, `10s`, `50s` to cover (a) "killed during entry checkpoint", (b) "killed mid-sandbox-boot", (c) "killed near the end of `validate_in_sandbox`". All three must produce byte-identical artifacts; if any one diverges, the failure surface is sharp.

This test is `@pytest.mark.slow` — the Phase 5 sandbox boot dominates wall-clock and the kill-then-resume cycle re-boots the sandbox once. Expected total runtime ~3–5 minutes for the parametrized set; runs only on the merge queue, not every PR.

## References — where to look
- **Architecture:** `../phase-arch-design.md §Process view — Scenario 3: Mid-run SIGKILL + resume from checkpointer` — sequence diagram is the spec for what the test instruments.
- **Architecture:** `../phase-arch-design.md §Edge cases #1, #2` — "Worker SIGKILLed mid-node" + "mid-checkpoint-write"; both must be covered (the parametrized delays cover them implicitly).
- **Architecture:** `../phase-arch-design.md §Testing strategy — Layer 3 Replay`.
- **Phase ADRs:** `../ADRs/0006-audited-sqlite-saver-per-workflow-fsync.md` — fsync-per-node-boundary is what makes the replay deterministic.
- **Phase ADRs:** `../ADRs/0007-blake3-chain-extension-and-tamper-evidence.md` — the audit chain head must verify on resume; a mid-write SIGKILL must NOT advance the chain.
- **Phase ADRs:** `../ADRs/0011-sqlite-throughput-watch-and-postgres-escalation.md` — durability discipline (no application fsync).
- **High-level plan:** `../High-level-impl.md §Step 8` — features delivered + done criteria + the macOS/Linux risk note.
- **Existing code:** `src/codegenie/graph/checkpointer.py` (S2-01–S2-04), `src/codegenie/graph/loop.py` (S5-01), `src/codegenie/cli/loop.py` (S6-02), the Phase 5 `validate_in_sandbox` node (S4-06).

## Goal
Land `tests/integration/test_replay_after_kill.py` that, for each delay in `{1.0, 10.0, 50.0}` seconds, spawns a child running the full vuln loop against the `cve-fixture`, SIGKILLs it during `validate_in_sandbox`, then re-invokes a fresh subprocess with the same `workflow_id` against the same `.sqlite3` file, and asserts that the resulting `report.json` and `attempts.jsonl` are **byte-identical** to a single committed reference run produced by the same fixture without any kill.

## Acceptance criteria
- [ ] `tests/integration/test_replay_after_kill.py` exists and is decorated `@pytest.mark.slow` + `@pytest.mark.integration`; runs only on the merge queue, not on every PR (`pytest.ini` / `pyproject.toml` already has the marker registered from earlier steps).
- [ ] The test is parametrized over `kill_delay_s ∈ [1.0, 10.0, 50.0]`; each parametrization is its own test ID so a failure isolates the timing bucket.
- [ ] The child process is launched via `multiprocessing.Process(target=_run_child, args=(workflow_id, tmp_root))` (not `subprocess.Popen`) so the parent can `os.kill(child.pid, signal.SIGKILL)` deterministically; `start_method="spawn"` is forced for macOS/Linux consistency.
- [ ] The child function `_run_child(workflow_id, tmp_root)` constructs the same initial `VulnLedger` the CLI would, builds the loop via `build_vuln_loop(checkpointer=make_checkpointer(workflow_id, base=tmp_root / ".codegenie/loop/checkpoints"))`, and calls `asyncio.run(graph.ainvoke(initial, config={"configurable": {"thread_id": workflow_id}}))`. No CLI shell round-trip.
- [ ] Parent waits `kill_delay_s` then issues `os.kill(child.pid, signal.SIGKILL)`; `child.join(timeout=5.0)` confirms termination; `child.exitcode` is `-signal.SIGKILL` (i.e., `-9`) — assertion checks this so the test fails loud if the kill missed.
- [ ] After kill, a **fresh `multiprocessing.Process`** (new PID, no state inherited) is spawned with the same `workflow_id` against the same `tmp_root`; the resume runs to `END` and produces `report.json` + `attempts.jsonl` under `tmp_root / ".codegenie/remediation/<run-id>/"`.
- [ ] The reference run (no kill) is produced inside the same test via a third `multiprocessing.Process` against a separate `tmp_root_ref` — or, if pre-computed, committed under `tests/fixtures/replay_reference/cve_fixture_3retries/` with a regeneration script documented in `tests/integration/README.md`. The default acceptance is "produced inline" to avoid drift across LangGraph/aiosqlite minor bumps.
- [ ] `assert (resumed_root / ".codegenie/remediation" / run_id / "report.json").read_bytes() == (ref_root / ".codegenie/remediation" / run_id / "report.json").read_bytes()` — true byte-identity, no JSON-normalization, no whitespace tolerance.
- [ ] Same byte-identity assertion for `attempts.jsonl`.
- [ ] An additional assertion confirms the post-kill `.sqlite3` file opens cleanly (no `database disk image is malformed`) — i.e., aiosqlite's WAL recovery rolled back the in-flight frame instead of corrupting the DB. Tested by opening the DB read-only via `sqlite3` stdlib and reading `PRAGMA integrity_check;` — must return `"ok"`.
- [ ] The audit chain at `.codegenie/remediation/<run-id>/audit/<run-id>.jsonl` is verified post-resume: the last `checkpoint.write` event's `prev` field points at the previous event's BLAKE3 digest, and no `checkpoint.tamper.detected` event was written during resume.
- [ ] Non-determinism sources are explicitly neutralized: wall-clock timestamps in `attempts.jsonl` are normalized via the conftest's existing `freeze_time` (or equivalent) fixture from S7-02; `run_id` is content-addressed from `(repo_root_blake3, advisory_canonical_id)` so it matches across runs; VCR cassettes for any Phase 4 LLM calls are reused.
- [ ] A platform-skip is documented but not used by default: the test must run on Linux and macOS; if a future LangGraph or aiosqlite minor bump genuinely diverges on one platform, the skip is added with a linked GitHub issue, not silently.
- [ ] The TDD plan's red test exists, was committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest -m "slow and integration"` all pass on the touched files.

## Implementation outline
1. Read `src/codegenie/graph/loop.py`, `src/codegenie/graph/checkpointer.py`, and `src/codegenie/cli/loop.py` first so the test reproduces the production invocation shape exactly (same factory, same config dict, same initial-`VulnLedger` construction). If the CLI does any wiring the test would otherwise miss, prefer importing a shared helper from `src/codegenie/cli/loop.py` over duplicating logic.
2. Add `tests/integration/test_replay_after_kill.py` with a module-level docstring linking ADR-0006 + ADR-0011 and Scenario 3 of the arch design.
3. Define `_run_child(workflow_id: str, tmp_root: Path) -> None` at module level (must be picklable for `spawn` start method); inside it: `asyncio.run(_run_child_async(...))`. Wrap any uncaught exception in `sys.exit(99)` so the parent can distinguish "killed" (`-9`) from "child died on its own" (`99`).
4. Define `_run_reference(workflow_id: str, tmp_root: Path) -> None` similarly — same logic but with no expectation of being killed.
5. The pytest function: parametrize over the three delays; in each: spin up reference (or use cached), kill the child, spin up resume, compare bytes, check `PRAGMA integrity_check`, verify chain.
6. Use `tmp_path_factory` (session-scoped) for the reference run + per-test `tmp_path` for the kill+resume; the audit chain assertion reads `.codegenie/remediation/<run-id>/audit/<run-id>.jsonl` from the test's `tmp_root`.
7. Confirm `mypy --strict` clean on the new test module — give the `Process` target functions explicit type annotations and use `multiprocessing.get_context("spawn")` instead of the module-level API (typing is cleaner).

## TDD plan — red / green / refactor

### Red — write the failing test first
Test file path: `tests/integration/test_replay_after_kill.py`

```python
"""Replay-after-kill canary — G2 exit criterion.

Why this test exists: roadmap Phase 6 commits to "mid-run kill + resume works
without state loss". The arch design's Scenario 3 (phase-arch-design.md
§Process view) is the spec — the in-flight WAL frame is rolled back by aiosqlite
on next open, the last fsync'd checkpoint is intact, and the loop re-runs from
the last node boundary. ADR-0006 forbids background flushing; ADR-0011 forbids
application-level fsync. If either is violated, this test goes red.
"""

from __future__ import annotations

import multiprocessing as mp
import os
import signal
import sqlite3
import sys
from pathlib import Path

import pytest

# Imported only by the parent process — child uses fresh imports under spawn.
from codegenie.graph.checkpointer import make_checkpointer  # noqa: F401  (smoke)
from codegenie.graph.loop import build_vuln_loop  # noqa: F401  (smoke)


def _run_child(workflow_id: str, tmp_root: Path) -> None:
    """Child entrypoint — picklable under `spawn`. Re-imports cleanly."""
    import asyncio

    from codegenie.cli.loop import build_initial_ledger_for_test  # shared helper
    from codegenie.graph.checkpointer import make_checkpointer
    from codegenie.graph.loop import build_vuln_loop

    async def _go() -> None:
        ckpt_base = tmp_root / ".codegenie/loop/checkpoints"
        ckpt_base.mkdir(parents=True, exist_ok=True)
        saver = make_checkpointer(workflow_id, base=ckpt_base)
        graph = build_vuln_loop(checkpointer=saver, max_attempts=3, force_rebuild=True)
        initial = build_initial_ledger_for_test(workflow_id=workflow_id, tmp_root=tmp_root)
        await graph.ainvoke(initial, config={"configurable": {"thread_id": workflow_id}})

    try:
        asyncio.run(_go())
    except SystemExit:
        raise
    except BaseException:  # pragma: no cover — child diagnostic
        import traceback

        traceback.print_exc()
        sys.exit(99)


def _run_reference(workflow_id: str, tmp_root: Path) -> None:
    """Reference entrypoint — same as child but never gets killed."""
    _run_child(workflow_id, tmp_root)


@pytest.fixture(scope="module")
def reference_artifacts(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, str]:
    """A single non-killed reference run; reused across parametrizations."""
    ref_root = tmp_path_factory.mktemp("ref")
    workflow_id = "wfdeadbeefdeadbeef"  # content-addressed in real flow; fixed here
    ctx = mp.get_context("spawn")
    proc = ctx.Process(target=_run_reference, args=(workflow_id, ref_root))
    proc.start()
    proc.join(timeout=300)
    assert proc.exitcode == 0, f"reference run failed with exitcode={proc.exitcode}"
    return ref_root, workflow_id


@pytest.mark.slow
@pytest.mark.integration
@pytest.mark.parametrize("kill_delay_s", [1.0, 10.0, 50.0], ids=["t=1s", "t=10s", "t=50s"])
def test_replay_after_sigkill_byte_identical_to_reference(
    tmp_path: Path,
    kill_delay_s: float,
    reference_artifacts: tuple[Path, str],
) -> None:
    """SIGKILL during validate_in_sandbox; resume; byte-identical artifacts.

    The kill must NOT corrupt the DB (PRAGMA integrity_check returns 'ok'),
    must NOT silently advance the audit chain, and the resumed run must
    produce report.json + attempts.jsonl whose bytes equal the reference run's.
    """
    ref_root, workflow_id = reference_artifacts
    ctx = mp.get_context("spawn")

    # First leg — start, then SIGKILL after kill_delay_s.
    child = ctx.Process(target=_run_child, args=(workflow_id, tmp_path))
    child.start()
    child.join(timeout=kill_delay_s)  # wait up to the delay
    assert child.is_alive(), f"child finished too fast — expected to still be running at {kill_delay_s}s"
    os.kill(child.pid, signal.SIGKILL)
    child.join(timeout=10.0)
    assert child.exitcode == -signal.SIGKILL, (
        f"expected exitcode -9 (SIGKILL), got {child.exitcode} "
        "(child died on its own — kill harness is broken)"
    )

    # DB must survive the kill.
    db_path = tmp_path / ".codegenie/loop/checkpoints" / f"{workflow_id}.sqlite3"
    assert db_path.exists(), "checkpoint DB missing post-kill — fsync discipline violated"
    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
        (result,) = conn.execute("PRAGMA integrity_check").fetchone()
    assert result == "ok", f"PRAGMA integrity_check failed: {result}"

    # Second leg — fresh process, same workflow_id, same tmp_path.
    resume = ctx.Process(target=_run_child, args=(workflow_id, tmp_path))
    resume.start()
    resume.join(timeout=180)
    assert resume.exitcode == 0, f"resume failed with exitcode={resume.exitcode}"

    # Locate artifacts. run_id is content-addressed; matches across runs.
    rem_dirs_ref = sorted((ref_root / ".codegenie/remediation").iterdir())
    rem_dirs_res = sorted((tmp_path / ".codegenie/remediation").iterdir())
    assert [d.name for d in rem_dirs_ref] == [d.name for d in rem_dirs_res], (
        "run_id mismatch — content-addressing broken"
    )
    run_id = rem_dirs_ref[0].name

    ref_report = (ref_root / ".codegenie/remediation" / run_id / "report.json").read_bytes()
    res_report = (tmp_path / ".codegenie/remediation" / run_id / "report.json").read_bytes()
    assert res_report == ref_report, "report.json bytes diverged after replay-after-kill"

    ref_attempts = (ref_root / ".codegenie/remediation" / run_id / "attempts.jsonl").read_bytes()
    res_attempts = (tmp_path / ".codegenie/remediation" / run_id / "attempts.jsonl").read_bytes()
    assert res_attempts == ref_attempts, "attempts.jsonl bytes diverged after replay-after-kill"

    # Audit chain must NOT contain a tamper event.
    chain_path = tmp_path / ".codegenie/remediation" / run_id / "audit" / f"{run_id}.jsonl"
    chain_bytes = chain_path.read_bytes()
    assert b'"checkpoint.tamper.detected"' not in chain_bytes, (
        "kill-then-resume falsely flagged tamper — chain extension is non-idempotent"
    )
```

### Green — make it pass
The test will go green if every prerequisite story (S2-01 through S2-04, S4-06, S5-01, S6-02, S6-03) is correctly implemented. Most likely greenfield work needed:
- Export `build_initial_ledger_for_test(workflow_id, tmp_root) -> VulnLedger` from `src/codegenie/cli/loop.py` (or a sibling test-helper module) so the test does not duplicate the CLI's ledger-construction logic. If the CLI does not yet expose a clean seam, surface that as a small refactor under this story (one helper function, no behavior change).
- Confirm `run_id` is deterministic across processes — derived from `(repo_root_blake3, advisory_canonical_id)` only, not from `datetime.now()` or `uuid4()`. If the current CLI passes a fresh UUID anywhere, that is a bug this test discovers — fix it here.
- Confirm wall-clock fields in `attempts.jsonl` are either absent or normalized via the shared `freeze_time` fixture from `tests/integration/conftest.py` (added by S7-02). If S7-02 hasn't landed yet, this story must add the minimal `freeze_time` shim with a back-reference to S7-02.

### Refactor — clean up
- Factor the `(spawn, run, kill)` harness into a tiny `KillHarness` context manager under `tests/integration/_kill_harness.py` so S8-02 (and any future replay tests) reuse it.
- Move the run-id-discovery helper (`sorted(rem_dir.iterdir())`) to the same module.
- Document the macOS vs Linux note from `High-level-impl.md §Step 8` directly in the test module docstring; if a platform skip is ever needed, the diff is one decorator and the reasoning lives next to it.

## Files to touch
| Path | Why |
|---|---|
| `tests/integration/test_replay_after_kill.py` | New — the canary itself. |
| `tests/integration/_kill_harness.py` | New (if extracted in refactor) — reusable spawn+kill helper. |
| `tests/integration/conftest.py` | Possibly extended — share `freeze_time` / `module`-scoped reference fixture; do not duplicate S7-02's shim. |
| `tests/integration/README.md` | New section documenting how to regenerate reference artifacts if the inline-reference strategy is swapped for committed fixtures later. |
| `src/codegenie/cli/loop.py` | Possibly add `build_initial_ledger_for_test` helper (small, additive) if the CLI does not already expose a clean seam. If added, the helper is `_`-prefixed and documented as test-only. |
| `pyproject.toml` / `pytest.ini` | Confirm `slow` and `integration` markers are registered (should already be from earlier steps; verify, do not re-register). |

## Out of scope
- The byte-identical run-twice reference test without a kill (S8-02).
- Concurrent-workflow throughput (S9-03).
- Tamper / world-readable / schema-drift adversarial flows (S2-03 already covers them; this story does not duplicate).
- macOS/Linux CI-matrix wiring beyond what is already configured at the repo level.
- Any change to the checkpointer, the audit chain, or the loop topology — if this test goes red, fix the implementation; do not weaken the test.

## Notes for the implementer
- **Do not** add an `os.fsync` to make this pass. If WAL+NORMAL is insufficient for byte-identity on your hardware, the right answer is to escalate to ADR-P6-006 (Postgres pull-forward), not to layer application-level fsync — that would silently corrupt the throughput baseline measured by S9-02. Surface the failure loudly.
- The `child.is_alive()` check before `os.kill` matters: if the child finished before `kill_delay_s` (because the fixture is too small or the sandbox is mocked), the kill targets a dead PID and the test is meaningless. The assertion catches that and fails loud.
- `multiprocessing.Process` with `start_method="spawn"` re-imports the target's module in the child; module-level imports must therefore be importable in isolation (no test-only globals). Hence the `_run_child` body re-imports under the function — picklable and isolated.
- `child.exitcode == -signal.SIGKILL` is `-9` on POSIX; do not write `child.exitcode != 0` because a clean exit ALSO satisfies that and would hide a kill-harness bug.
- aiosqlite WAL recovery is best-effort if `synchronous=OFF`; ADR-0011 sets `synchronous=NORMAL` precisely so that the rollback-on-next-open guarantee holds. If `PRAGMA integrity_check` ever returns anything other than `"ok"`, the failure is in the checkpointer (likely a missed PRAGMA in S2-01), not in this test.
- The audit-chain assertion looks for the absence of `checkpoint.tamper.detected`; do **not** also assert "the chain extends across resume" — that's S2-02's contract and S2-03's adversarial test. Keep this test focused on the replay-byte-identity property.
- If a Phase 4 LLM call happens during the killed leg, the VCR cassette must be in `record_mode="none"` so a stale cassette doesn't silently get re-recorded mid-test. Confirm in the conftest.
- Expect the `50s` parametrization to be the slowest by far — it consumes a full sandbox boot. If CI wall-clock budget becomes tight, consider lowering the `50.0` value rather than dropping it; the goal is to cover *late-in-validate* kills, and any value > the sandbox-boot threshold suffices.
