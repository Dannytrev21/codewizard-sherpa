# Story S5-08 — Replay-after-SIGKILL integration test

**Step:** Step 5 — `DistrolessLedger`, `build_distroless_loop()`, `cli/migrate.py`, and Node.js Express E2E
**Status:** Ready
**Effort:** M
**Depends on:** S5-06
**ADRs honored:** ADR-P7-001 (parallel ledger; `extra="forbid"` + runtime mutation hook; per-node checkpoint fsync), ADR-P7-005 (CLI replay verb), Phase 6 ADR-0003 (`AuditedSqliteSaver` fsync-per-node), Phase 6 ADR-0008 (replay-after-kill idempotence)

## Context

Per `phase-arch-design.md §Harness engineering — Replay / debugability` and `§Process view`, the distroless loop's per-node checkpoint fsync — inherited verbatim from Phase 6's `AuditedSqliteSaver` — is the load-bearing durability guarantee. The contract: a SIGKILL during `validate_in_sandbox` (the longest-running node) loses no committed state; restarting `codegenie migrate` against the same inputs rehydrates from the last fsync'd checkpoint and produces a **byte-identical final ledger**.

This story exercises that contract. It launches a distroless workflow, SIGKILLs the process during `validate_in_sandbox`, restarts the workflow with the same inputs, and asserts the final `DistrolessLedger` (and the patch, and the report) is byte-identical to a non-interrupted reference run.

This is also the place where `extra="forbid"` on `DistrolessLedger` earns its keep — any extra field, any field drift, any schema bump silently lost between fsync and resume would fail loudly here via the Pydantic re-validation on checkpoint reload.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Harness engineering — Replay / debugability` (lines 1160–1163) — SIGKILL → restart → rehydrate from last fsync'd checkpoint → byte-identical final state.
  - `../phase-arch-design.md §Process view` (lines 207–245) — per-node fsync discipline.
  - `../phase-arch-design.md §Testing strategy — Integration tests` — `test_migrate_replay_after_kill.py` named explicitly.
  - `../phase-arch-design.md §Goals — G3 (audit invariants)`.
- **Phase ADRs:**
  - `../ADRs/0011-distroless-ledger-parallel-to-vuln-ledger.md` — ADR-P7-001 — `extra="forbid"` rejects unknown fields on resume; runtime mutation hook fires on in-place changes.
  - `../ADRs/0012-parallel-cli-verbs-no-shared-dispatcher.md` — ADR-P7-005 — `codegenie migrate replay <thread_id> [--from <checkpoint_id>]` is the replay surface.
- **Source design:**
  - `../final-design.md §Harness engineering replay`.
- **Existing code:**
  - `src/codegenie/graph/checkpointer.py` (Phase 6) — `AuditedSqliteSaver` with fsync-per-`put`.
  - `tests/integration/test_replay_after_kill.py` (Phase 6 — if it exists; check for the vuln-side analog) — mirror the SIGKILL discipline.
  - `src/codegenie/cli/migrate.py` (S5-05) — `replay` subcommand.
  - `tests/integration/test_migrate_node_e2e.py` (S5-06) — reuse the Express fixture; this story is the replay-shaped variant.

## Goal

Land `tests/integration/test_migrate_replay_after_kill.py` proving that SIGKILL during `validate_in_sandbox` followed by `codegenie migrate run` (resume from checkpoint) produces a byte-identical final `DistrolessLedger`, byte-identical patch, and byte-identical `migration-report.yaml` versus a non-interrupted reference run.

## Acceptance criteria

- [ ] `tests/integration/test_migrate_replay_after_kill.py` exists with at least two tests:
  1. `test_sigkill_during_validate_in_sandbox_resumes_byte_identical` — runs the Express E2E to a checkpoint mid-`validate_in_sandbox`, SIGKILLs the process, resumes, asserts final state == reference.
  2. `test_sigkill_does_not_corrupt_checkpoint` — same setup; asserts the SQLite checkpoint file passes `PRAGMA integrity_check` after kill.
- [ ] The test uses subprocess invocation (not `CliRunner`) — only a real subprocess can be SIGKILL'd; in-process exceptions don't exercise the fsync discipline.
- [ ] SIGKILL is triggered mid-`validate_in_sandbox` via a monkey-patched hook in the test (e.g., set an env var the node respects) or by timing (sleep + kill after sandbox spawn). The test must reliably hit the kill window.
- [ ] The reference run produces a "ground-truth" final ledger; the replay must produce the same byte-for-byte `model_dump_json()` after normalizing volatile fields (`resolved_at`, `chain_head`, `workflow_id` — wait, `chain_head` should be deterministic if replay is). Document explicitly which fields are normalized and why.
- [ ] `model_validate_json` on the rehydrated checkpoint blob succeeds — `extra="forbid"` does not trip.
- [ ] After resume, `last_engine == "dockerfile_recipe"`, `runtime_shell_count == 0`, the gate passes — the *outcome* is byte-identical, not just the schema.
- [ ] The test marks itself `@pytest.mark.integration` and `@pytest.mark.requires_docker`.
- [ ] `mypy --strict tests/integration/test_migrate_replay_after_kill.py` is clean.

## Implementation outline

1. Reuse the `express_fixture` from S5-06.
2. **Reference run**: subprocess-invoke `codegenie migrate run <fixture> --target distroless --cve CVE-2025-XXXX`, wait to completion, capture the final ledger JSON from the last checkpoint, capture the patch and report. This is the "ground truth".
3. **Killed run**: subprocess-invoke the same command, with an env var (e.g., `CODEGENIE_TEST_SLEEP_IN_VALIDATE=5`) the `validate_in_sandbox` node respects to sleep mid-execution; after ~3 s, send SIGKILL to the process.
4. **Resume run**: subprocess-invoke `codegenie migrate run <fixture> --target distroless --cve CVE-2025-XXXX` again. Because `workflow_id` is content-addressed (S5-05), the CLI rehydrates from the existing SQLite checkpoint at `.codegenie/migration/checkpoints/<workflow_id>.sqlite3` and continues. (Alternative: explicitly use `codegenie migrate replay <thread_id>`; document the choice.)
5. Capture the resumed final ledger, patch, and report. Compare byte-for-byte to the reference run (after normalizing `resolved_at` and any wall-clock timestamps).
6. Run `sqlite3 <checkpoint> "PRAGMA integrity_check"` and assert `"ok"`.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file: `tests/integration/test_migrate_replay_after_kill.py`.

```python
import json
import signal
import sqlite3
import subprocess
import time
from pathlib import Path

import pytest
import yaml


@pytest.mark.integration
@pytest.mark.requires_docker
def test_sigkill_during_validate_in_sandbox_resumes_byte_identical(
    express_fixture: Path,
) -> None:
    """Arch §Harness eng — replay-after-kill produces byte-identical final state."""
    # Reference run (no kill)
    _reset_fixture(express_fixture)
    ref_proc = subprocess.run(
        ["codegenie", "migrate", "run", str(express_fixture), "--target", "distroless", "--cve", "CVE-2025-XXXX"],
        check=True,
        capture_output=True,
    )
    ref_ledger = _read_final_ledger(express_fixture)
    ref_patch = _read_patch(express_fixture)
    ref_report = _read_report(express_fixture)
    _move_fixture_aside(express_fixture)

    # Killed run
    _reset_fixture(express_fixture)
    proc = subprocess.Popen(
        ["codegenie", "migrate", "run", str(express_fixture), "--target", "distroless", "--cve", "CVE-2025-XXXX"],
        env={**os.environ, "CODEGENIE_TEST_SLEEP_IN_VALIDATE": "5"},
    )
    # Wait until validate_in_sandbox is in the sleep window
    _wait_for_validate_node_entry(express_fixture, timeout_s=20)
    proc.send_signal(signal.SIGKILL)
    proc.wait(timeout=5)
    assert proc.returncode == -signal.SIGKILL

    # Resume run
    resume_proc = subprocess.run(
        ["codegenie", "migrate", "run", str(express_fixture), "--target", "distroless", "--cve", "CVE-2025-XXXX"],
        check=True,
        capture_output=True,
    )
    resumed_ledger = _read_final_ledger(express_fixture)
    resumed_patch = _read_patch(express_fixture)
    resumed_report = _read_report(express_fixture)

    # Byte-identical comparison (after normalizing volatile fields)
    _normalize(ref_ledger); _normalize(resumed_ledger)
    _normalize(ref_report); _normalize(resumed_report)
    assert resumed_ledger == ref_ledger, "Final DistrolessLedger drifted across SIGKILL + resume"
    assert resumed_patch == ref_patch, "Patch bytes drifted across SIGKILL + resume"
    assert resumed_report == ref_report, "Migration report drifted across SIGKILL + resume"


@pytest.mark.integration
@pytest.mark.requires_docker
def test_sigkill_does_not_corrupt_checkpoint(express_fixture: Path) -> None:
    """SQLite integrity holds across SIGKILL — Phase 6 fsync-per-put discipline."""
    _reset_fixture(express_fixture)
    proc = subprocess.Popen(
        ["codegenie", "migrate", "run", str(express_fixture), "--target", "distroless", "--cve", "CVE-2025-XXXX"],
        env={**os.environ, "CODEGENIE_TEST_SLEEP_IN_VALIDATE": "5"},
    )
    _wait_for_validate_node_entry(express_fixture, timeout_s=20)
    proc.send_signal(signal.SIGKILL)
    proc.wait(timeout=5)

    checkpoint_files = list((express_fixture / ".codegenie/migration/checkpoints").glob("*.sqlite3"))
    assert checkpoint_files, "No checkpoint file emitted before SIGKILL"
    for cp in checkpoint_files:
        conn = sqlite3.connect(cp)
        result = conn.execute("PRAGMA integrity_check").fetchone()
        conn.close()
        assert result == ("ok",), f"Checkpoint {cp} corrupted: {result}"


@pytest.mark.integration
@pytest.mark.requires_docker
def test_resumed_ledger_passes_extra_forbid_validation(express_fixture: Path) -> None:
    """ADR-P7-001 / Phase 6 ADR-0002 — resume re-validates via extra='forbid'."""
    # ... kill-and-resume setup as above ...
    # On resume, the loop must rehydrate without raising; model_validate_json on the checkpoint blob succeeds.
    resume_proc = subprocess.run([...], check=True, capture_output=True)
    # If extra=forbid caught silent drift, exit code would be 13 (checkpoint integrity)
    assert resume_proc.returncode == 0
```

Run; confirm fails (likely `FileNotFoundError` on test file or assertion failure if SIGKILL hits the wrong window). Commit.

### Green — make it pass

Author the test; add the `CODEGENIE_TEST_SLEEP_IN_VALIDATE` env-var hook in `validate_in_sandbox` (S5-03). The hook **must be test-only** — guarded by `if os.environ.get("CODEGENIE_TEST_SLEEP_IN_VALIDATE"):`, otherwise the node body is unchanged. Iterate until reliably green.

### Refactor — clean up

- Add `_normalize` and `_read_final_ledger` helpers in `tests/integration/conftest.py`.
- Document the env-var hook in the `validate_in_sandbox` docstring; cite this test by name as the consumer.
- Add a timeout on the SIGKILL window (the `_wait_for_validate_node_entry` helper) to fail fast if the node never enters.
- Per cross-cutting determinism: no `random` / no `time` imports in production code; the test may use `time.sleep` only in the test file, not in `graph/`.
- Per `CLAUDE.md` Rule 9 ("Tests verify intent"): the test verifies *the durability invariant* — fsync per node + Pydantic re-validation + content-addressed workflow_id work together. The docstring must state the invariant; the assertions must encode why it matters (Phase 8 supervisor reliability, operator-side resume).

## Files to touch

| Path | Why |
|---|---|
| `tests/integration/test_migrate_replay_after_kill.py` | NEW — the SIGKILL replay test. |
| `tests/integration/conftest.py` | UPDATE — `_normalize`, `_read_final_ledger`, `_wait_for_validate_node_entry` helpers. |
| `src/codegenie/graph/nodes/distroless/validate_in_sandbox.py` | UPDATE (small) — test-only env-var sleep hook, gated by `CODEGENIE_TEST_SLEEP_IN_VALIDATE`. |

## Out of scope

- **The happy-path E2E test (`test_migrate_node_e2e.py`)** — owned by S5-06.
- **Cross-task chain-no-collision** — owned by S5-07.
- **Replay from arbitrary `<checkpoint_id>`** — the `--from` flag of `codegenie migrate replay`; the *implementation* is in S5-05 (CLI), but a dedicated arbitrary-replay test is deferred to S6 / later.
- **Cross-process audit-chain locking under SIGKILL** — Phase 9 Temporal owns the cross-process case; this story is single-process.
- **Concurrent SIGKILLs on multiple workers** — Phase 9.
- **`PRAGMA wal_checkpoint(FULL)` semantics on disk** — Phase 6's checkpointer fsync discipline (ADR-0003 / S2-04 WAL durability test) is the upstream guarantee; this story consumes it.
- **Network-level failure replay (registry timeout mid-pull)** — covered indirectly by S2-02 buildkit wrapper's `RegistryAuthFailed` handling; out of scope here.

## Notes for the implementer

- **The env-var hook in `validate_in_sandbox` is *only* for tests.** Production code paths must not call `time.sleep` (fence-CI under `graph/` would flag a top-level `import time`). Gate the hook with an explicit env-var check; if the env var is absent, no `time.sleep` is invoked.
- **Subprocess SIGKILL is the only way to test fsync durability.** `CliRunner` runs in-process; an in-process exception cleans up via Python's normal teardown and *does not* leave a representative crash signature. The test must use `subprocess.Popen` + `send_signal(SIGKILL)`.
- **The "killed run" + "resume run" produces *the same* `workflow_id`** because the workflow_id is content-addressed (`blake3(repo|wf:distroless:cve)[:16]`). The CLI on the second invocation finds the existing checkpoint at `.codegenie/migration/checkpoints/<workflow_id>.sqlite3` and rehydrates from it. This is the load-bearing replay mechanism.
- **`<run-id>` is *not* the same as `workflow_id`** (per arch §Gap 1). `<run-id>` is per-CLI-invocation; the artifact directory `.codegenie/migration/<run-id>/` may differ between the killed run and the resume run, but the *workflow_id* (and thus the checkpoint file) is the same. The test must handle this carefully — the report path may live under a different `<run-id>` directory; the comparison is on *content*, not path.
- **Normalize `resolved_at` and `workflow_id` before byte-comparison.** Across the reference and replay runs, `resolved_at` (the catalog lookup timestamp) may differ by milliseconds. `workflow_id` should be *identical* if replay is true to its name; if it differs, you have a bug. Asserting on `workflow_id` equality is a load-bearing check.
- **Per arch §Process view, fsync is per-node-boundary.** SIGKILL between node boundaries loses no committed state; SIGKILL *mid-node* (e.g., during the `docker buildx build` subprocess) may lose the partial sandbox output but the node-entry checkpoint is intact, so on resume the node re-runs from its entry frame. The test must SIGKILL between the entry checkpoint and the exit checkpoint — that's the discriminating window.
- **`extra="forbid"` catches silent schema drift on resume.** If Phase 8 (or any future phase) silently adds a field to `DistrolessLedger`, the rehydrated checkpoint from before the schema bump fails `model_validate_json` loudly. The third test pins this — exit code 13 (`CheckpointTampered` or equivalent) would surface; in this story's expected behavior, exit code 0 (no drift).
- **Per CLAUDE.md Rule 12 ("Fail loud"), the assertion message on byte-mismatch must show a diff**, not just "differ". Add a `_diff(ref, resumed)` helper that pretty-prints the field-level divergence.
- **Per `CLAUDE.md` Rule 9 ("Tests verify intent"), the test's docstring must answer "why does this matter?".** Answer: Phase 8's supervisor will run unattended in production; an operator restarting after a crash must get the same final state, not a divergent one. The fsync-per-node discipline (Phase 6 ADR-0003) is what makes that true; this test is its mechanical proof.
