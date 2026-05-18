# Story S6-05 — `codegenie remediate` CLI + `.codegenie/.lock` flock + `audit verify` spanning-chain extension

**Step:** Step 6 — RemediationOrchestrator, TrustScorer, two-stream EventLog, SubgraphNode Protocol, end-to-end happy path
**Status:** Ready
**Effort:** M
**Depends on:** S6-04
**ADRs honored:** ADR-0005 (BLAKE3-chained spanning stream — `audit verify` walks it; refuses startup on break), ADR-0010 (`RemediationOutcome` tagged union; `WorkflowConcurrent` is a typed spanning-stream variant)

## Context

This story is the CLI surface that turns the orchestrator (S6-04) into a runnable command. Three concerns are bundled:

1. **The click subcommand `codegenie remediate <repo> --cve <id>`** — entry point under `src/codegenie/cli/remediate.py`. Wires up: `PluginRegistry` load, `VulnIndex` open, `EventLog` construct, `RemediationOrchestrator` construct + `run(...)`, exit-code translation from `RemediationOutcome` variant.
2. **`.codegenie/.lock` `fcntl.flock` exclusive lock** (per architecture spec §Edge cases E13 + §Harness engineering §Idempotence): the *first* thing `remediate` does after parsing args is acquire an `LOCK_EX | LOCK_NB` lock on `<repo>/.codegenie/.lock`. If acquisition fails (another `codegenie remediate` is running on the same repo), the second invocation emits a `WorkflowConcurrent` spanning event (variant added in S6-01) and exits with code **8**. This is a different lock than the `EventLog`'s internal `fcntl.flock` on the spanning stream — that one is a deep defense for write interleaving; this one is the outer mutex on the workflow itself.
3. **`codegenie audit verify` extension** to walk the BLAKE3 chain on the spanning stream (`.codegenie/events/spanning/append.jsonl.zst`) — refusing startup on chain break. Phase 0's existing `codegenie audit verify` already walks the per-run audit anchors (`tests/integration/test_audit_chain_extension.py` precedent); this extension adds the spanning-stream walk as a new check inside the same command.

Exit codes (per architecture spec §Control flow — Decision points + §Edge cases):
- `0` — `RemediationOutcome.Validated(passed=True)`
- `3` — `RemediationOutcome.NotApplicable(reason)` (Phase 4 fallback territory)
- `4` — `RemediationOutcome.Failed(...)` (recipe failed, network denied, filesystem race, plugin integrity mismatch, audit chain corrupted)
- `7` — `RemediationOutcome.RequiresHumanReview(reason)` (universal HITL fallback fired)
- `8` — `WorkflowConcurrent` (lock contention)

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Control flow` — full 11-step happy path; the CLI is step 1 (parse + mint `WorkflowId`) and step 11 (flush + exit).
  - `../phase-arch-design.md §Control flow — Decision points` — exit code matrix per `RemediationOutcome` variant.
  - `../phase-arch-design.md §Harness engineering §Idempotence` — *"second run aborts with `WorkflowConcurrent` (the `.codegenie/.lock` `flock`)"*. Exact semantics: re-running against an unchanged repo + unchanged `vuln-index.sqlite` would cache-hit and create the same branch; the flock makes the second invocation explicit-fail rather than silent-re-apply.
  - `../phase-arch-design.md §Edge cases E13` — concurrent invocation: `.codegenie/.lock` `fcntl.flock`; second exits immediately with `WorkflowConcurrent`.
  - `../phase-arch-design.md §Harness engineering — Replay / debuggability` — *"`codegenie audit verify` (extended from Phase 0) verifies BLAKE3 chain on the spanning stream and refuses startup on break"*.
- **Phase ADRs:**
  - `../ADRs/0005-two-stream-event-log-per-adr-0034.md` §Consequences — *"`codegenie audit verify` extends to verify the BLAKE3 chain on the spanning stream and refuses startup on break."*
  - `../ADRs/0010-domain-modeling-discipline-scope-sum-type-and-newtypes.md` §Decision (3) — `RemediationOutcome` tagged-union dispatch via `match` + `assert_never` (the CLI's exit-code translation is the textbook example).
- **Existing code to reuse / extend:**
  - `src/codegenie/cli/__main__.py` (or `cli/main.py` — verify via `ls src/codegenie/cli/`) — the click group `codegenie` and `codegenie audit verify` precedent.
  - `src/codegenie/audit.py` — `chain_verify` primitive that the spanning-stream walker reuses.
  - `src/codegenie/plugins/events.py` (S6-01) — `EventLog` + `WorkflowConcurrent` variant.
  - `src/codegenie/transforms/orchestrator.py` (S6-04) — `RemediationOrchestrator` constructed and `run(...)` here.
  - Phase 0's `tests/integration/test_audit_*` — precedent for verify-chain integration tests.
- **This phase, parallel stories:**
  - S6-01 — the `WorkflowConcurrent` event variant must exist on the spanning-stream union; the BLAKE3 chain this story walks.
  - S6-04 — the orchestrator; this CLI wires it up.
  - S6-06 — the contract snapshot test; this story does NOT modify it (the CLI surface is internal to Phase 3, not contracted to Phase 5).

## Goal

Land `src/codegenie/cli/remediate.py` exposing `remediate` click subcommand wired to `RemediationOrchestrator.run(...)`; an exit-code translator over `RemediationOutcome`; `.codegenie/.lock` `fcntl.flock` exclusive lock with `WorkflowConcurrent` + exit 8 on contention; extend `codegenie audit verify` to walk the spanning-stream BLAKE3 chain and refuse startup on break.

## Acceptance criteria

- [ ] `src/codegenie/cli/remediate.py` exists; `codegenie remediate --help` prints usage with `<repo>` positional arg and `--cve <id>` required option.
- [ ] `codegenie remediate ./path/to/repo --cve CVE-2024-21501` runs end-to-end against the Express CVE fixture (S8-01 / stub from S6-04) and exits `0` on success.
- [ ] **Exit-code matrix is exhaustive over `RemediationOutcome`** (uses `match` + `assert_never`):
  - `Validated(passed=True)` → `0`
  - `Validated(passed=False)` → `4` (per ADR-0007; Phase 3 alone does not retry)
  - `NotApplicable(reason)` → `3`
  - `Failed(error, partial_report_path)` → `4`
  - `RequiresHumanReview(reason, handoff_path)` → `7`
- [ ] **`.codegenie/.lock` flock acquisition**: before constructing the orchestrator, the CLI opens `<repo>/.codegenie/.lock` (creating the file if absent), acquires `fcntl.flock(LOCK_EX | LOCK_NB)`, and holds it for the entire workflow duration.
- [ ] **On contention** (`fcntl.flock` raises `BlockingIOError`): emit one `WorkflowConcurrent(workflow_id=<new>, lock_holder_pid=<best-effort PID from lockfile>, contested_at=<now>)` spanning event, print a one-line operator-facing message (`workflow_concurrent: another `codegenie remediate` is running against <repo>; exiting`), exit code `8`. **No partial report**, **no branch creation**.
- [ ] The lock is **released in a `finally` block** so kill -9 / panic / `KeyboardInterrupt` does not orphan the lock — `fcntl.flock` is FD-scoped so process exit releases automatically, but the explicit `LOCK_UN` is documented at the call site as the contract.
- [ ] **`codegenie audit verify` extension**: the existing subcommand additionally walks `<repo>/.codegenie/events/spanning/append.jsonl.zst` (if present) recomputing BLAKE3 chain hashes. On mismatch: exit non-zero (existing `audit verify` exit code 4) with a structured error naming the first divergent event ID + line number + the file path.
- [ ] If the spanning stream is **absent or empty**, `audit verify` reports success for that check (genesis = nothing to verify).
- [ ] The lock-acquire happens **before** constructing the `EventLog` for the new workflow (otherwise the spanning stream's own `fcntl.flock` cross-process safety would mask the outer contention).
- [ ] The minted `WorkflowId` (ULID) and `WorkflowStarted` spanning event are written **after** the lock is acquired; the lock is the precondition.
- [ ] Operator-facing messages on stdout / stderr are sanitized: no absolute paths outside the jail, no env values, no capability bundles (per architecture spec §Harness engineering — Logging). The sanitizer reuses the Phase 0 / Phase 2 path scrubber where possible.
- [ ] `--repo-context-path <path>` is an optional flag pointing to a non-standard `repo-context.yaml` location (default: `<repo>/.codegenie/context/repo-context.yaml` per Phase 1 convention); the CLI warns on staleness using existing freshness primitives.
- [ ] An integration test in `tests/integration/test_concurrent_remediate.py` spawns two `codegenie remediate` subprocesses against the same repo; asserts one exits 0 (or the orchestrator-determined success code), the other exits 8 with `workflow_concurrent` on stderr.
- [ ] An integration test in `tests/integration/test_audit_verify_spanning_chain.py` writes a valid spanning stream, runs `codegenie audit verify` → exit 0; flips one byte in the spanning file → exit 4 with the chain-tamper diagnostic.
- [ ] TDD red test exists, committed, green.
- [ ] `ruff format`, `ruff check`, `mypy --strict` clean.

## Implementation outline

1. Write `tests/unit/cli/test_remediate.py` + `tests/integration/test_concurrent_remediate.py` + `tests/integration/test_audit_verify_spanning_chain.py` (red).
2. Create `src/codegenie/cli/remediate.py`:
   - `@click.command(name="remediate")`, `@click.argument("repo", type=click.Path(...))`, `@click.option("--cve", required=True)`, optional `--repo-context-path`.
   - In the command body:
     - Validate `<repo>/.codegenie/` exists (Phase 0+ assumption); create if absent (mirror existing `codegenie gather` behavior).
     - Open `<repo>/.codegenie/.lock` (touch-create), `fcntl.flock(fd, LOCK_EX | LOCK_NB)`. On `BlockingIOError`: emit `WorkflowConcurrent` via a *minimal* `EventLog` (which itself takes `fcntl.flock` on the spanning stream — confirm this nested-lock pattern is safe; if it deadlocks, write the event using a synchronous direct-write helper that bypasses the EventLog's own lock since we already failed to take the outer lock).
     - Mint `WorkflowId` (ULID via `ulid-py` or stdlib equiv).
     - Construct `EventLog(root=repo / ".codegenie", workflow_id=wf)`.
     - Emit `WorkflowStarted` spanning event.
     - Load `PluginRegistry`, `VulnIndex`, construct `RemediationOrchestrator(...)`.
     - `outcome = asyncio.run(orchestrator.run(repo=SandboxedPath.create(...).unwrap(), cve=CveId.parse(cve).unwrap()))`.
     - Match over `outcome.kind`, map to exit code via the matrix above (use `match` + `assert_never`).
     - In `finally`: `event_log.flush()`, `fcntl.flock(fd, LOCK_UN)`, close FD, raise `SystemExit(exit_code)`.
3. Extend `src/codegenie/cli/audit.py` (or wherever `codegenie audit verify` lives):
   - Add a new check function `_verify_spanning_chain(events_dir: Path) -> VerifyResult` mirroring the existing per-run anchor verification.
   - Walk `<root>/events/spanning/append.jsonl.zst` if present; decompress; per line, recompute `BLAKE3(prev_chain_head || canonical_json(event - {prev_hash}))` and compare to the recorded `prev_hash`. First mismatch → `ChainTamperDetected(path, line_number, expected_prev, computed_prev)` → exit 4.
   - The existing `audit verify` aggregates results; add this check to the aggregation.
4. Add `WorkflowConcurrent` payload schema (deferred to S6-01's spanning union — if not present, add a minimal variant in this story and surface the addition in S6-01's notes).
5. Run `ruff format`, `ruff check`, `mypy --strict`, `pytest`.

## TDD plan — red / green / refactor

### Red — write the failing test first

```python
# tests/unit/cli/test_remediate.py
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from codegenie.cli.remediate import remediate


def test_remediate_help_includes_repo_and_cve():
    runner = CliRunner()
    result = runner.invoke(remediate, ["--help"])
    assert result.exit_code == 0
    assert "repo" in result.output.lower()
    assert "--cve" in result.output


def test_remediate_against_express_fixture_exits_zero(tmp_path, monkeypatch):
    """Smoke test: orchestrator returns Validated(passed=True) → exit 0."""
    # Copy fixture into tmp; run remediate; assert exit 0.
    ...


def test_exit_codes_exhaustive_over_remediation_outcome():
    """Inspect the CLI source for the exit-code match block.

    Must have all 5 RemediationOutcome arms (Validated passed=True,
    Validated passed=False, NotApplicable, Failed, RequiresHumanReview).
    """
    import inspect
    from codegenie.cli import remediate as mod
    src = inspect.getsource(mod)
    assert "case Validated" in src
    assert "case NotApplicable" in src
    assert "case Failed" in src
    assert "case RequiresHumanReview" in src
    assert "assert_never" in src


# tests/integration/test_concurrent_remediate.py
@pytest.mark.integration
def test_second_invocation_exits_8_with_workflow_concurrent(tmp_path):
    repo = _copy_fixture_to(tmp_path)
    # Start first invocation in background (subprocess.Popen, slow fixture
    # or monkeypatch the orchestrator to sleep 5s).
    first = subprocess.Popen(["python", "-m", "codegenie", "remediate",
                              str(repo), "--cve", "CVE-2024-21501"])
    try:
        # Brief sleep to let first acquire the lock.
        time.sleep(0.5)
        second = subprocess.run(
            ["python", "-m", "codegenie", "remediate",
             str(repo), "--cve", "CVE-2024-21501"],
            capture_output=True, text=True, timeout=5,
        )
        assert second.returncode == 8
        assert "workflow_concurrent" in second.stderr.lower()
    finally:
        first.wait()


# tests/integration/test_audit_verify_spanning_chain.py
@pytest.mark.integration
def test_audit_verify_passes_on_intact_spanning_chain(tmp_path):
    _seed_valid_spanning_stream(tmp_path)
    result = subprocess.run(
        ["python", "-m", "codegenie", "audit", "verify",
         "--runs-dir", str(tmp_path / "context" / "runs"),
         "--cache-dir", str(tmp_path / "cache"),
         "--yaml-path", str(tmp_path / "context" / "repo-context.yaml"),
         "--spanning-events-path", str(tmp_path / "events" / "spanning" / "append.jsonl.zst")],
        capture_output=True, text=True,
    )
    assert result.returncode == 0


@pytest.mark.integration
def test_audit_verify_fails_on_tampered_spanning_chain(tmp_path):
    _seed_valid_spanning_stream(tmp_path)
    _flip_one_byte(tmp_path / "events" / "spanning" / "append.jsonl.zst")
    result = subprocess.run(
        ["python", "-m", "codegenie", "audit", "verify", ...],
        capture_output=True, text=True,
    )
    assert result.returncode == 4
    assert "chain" in result.stderr.lower()
```

Run; confirm `ImportError` / `ClickException`. Commit the red marker.

### Green — make it pass

- The click command body is ~60 lines: arg parsing, lock acquisition, EventLog construct, orchestrator construct, `asyncio.run(...)`, exit-code translation, `finally` cleanup.
- The `audit verify` extension is ~30 lines: decompress, walk, recompute, compare.
- The `WorkflowConcurrent` direct-write path (when the EventLog itself can't be safely constructed) is ~15 lines: open file, append one canonical-JSON line with the genesis `prev_hash`, close.

### Refactor — clean up

- Extract the lock-acquisition into a context manager: `with _workflow_lock(repo) as lock_fd:` so the `finally` cleanup is implicit.
- The `match` exit-code translator into a helper: `def _exit_code_for(outcome: RemediationOutcome) -> int` — single source of truth for the exit-code matrix.
- Operator-facing messages routed through a single `_emit_operator_message(text, *, stream)` helper that runs the path scrubber.
- The `WorkflowConcurrent` direct-write helper has a docstring explaining why it bypasses `EventLog`: outer-lock contention means the workflow itself can't run; we still want the event recorded; the spanning stream's own `flock` ordering is well-defined.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/cli/remediate.py` | New file — click subcommand, lock, orchestrator wiring, exit-code translator |
| `src/codegenie/cli/__main__.py` (or `main.py`) | Register the `remediate` subcommand on the `codegenie` click group |
| `src/codegenie/cli/audit.py` (or wherever `audit verify` lives) | Extend with `_verify_spanning_chain` check |
| `tests/unit/cli/test_remediate.py` | New file — CLI help, exit-code match exhaustiveness via source inspection |
| `tests/integration/test_concurrent_remediate.py` | New file — two subprocesses, second exits 8 |
| `tests/integration/test_audit_verify_spanning_chain.py` | New file — intact-chain pass, tampered-chain fail |

## Out of scope

- **The orchestrator implementation** — S6-04.
- **The `WorkflowConcurrent` variant's payload schema definition** — owned by S6-01 (this story exercises it; if the variant is missing, surface to S6-01).
- **The Phase 5 contract snapshot test** — S6-06.
- **Per-run audit anchors** — Phase 0's existing `codegenie audit verify` already handles them; this story does not modify that path.
- **`codegenie remediate --watch` / polling mode** — out of scope; one-shot only.
- **Multi-CVE batched remediation in one invocation** — out of scope; one `--cve` per invocation. Phase 10's portfolio discovery is the wrapper.
- **PR creation (real `git push` + GitHub API)** — Phase 11. This story writes a local branch only.

## Notes for the implementer

- **The lock is the FIRST thing the CLI does after parsing.** Constructing the `EventLog` before lock acquisition risks two concurrent EventLogs holding their own `fcntl.flock` on the spanning stream and serializing on it — which would mask the outer contention behind I/O latency. Lock first, then construct.
- **Nested-lock deadlock risk**: when the outer lock acquisition fails and we want to emit `WorkflowConcurrent`, the natural approach is to construct an `EventLog` and call `emit_spanning(...)`. But `emit_spanning` itself takes `fcntl.flock(LOCK_EX)` on the spanning stream — which on Linux is process-scoped (so the second process can acquire it even though the first holds the outer lock; this is fine). If you observe a hang, write `WorkflowConcurrent` via a direct-append helper that *does* acquire the spanning-stream lock but does NOT depend on the orchestrator-owned `EventLog` instance. Document the choice.
- **`fcntl.flock` is advisory.** A determined process can ignore it. The lock is best-effort cooperative mutex; the architecture spec accepts this (ADR-0011 honest-framing — Phase 3 does not promise unforgeable isolation). Document this in the operator runbook (Phase 9+ may swap to a more robust mechanism).
- **The `WorkflowConcurrent` event MUST land on the spanning stream**, not internal. Rationale: the contended workflow never advances past lock acquisition, so there is no per-workflow internal stream to write to (or, if one is created, it's empty modulo the start event). The spanning stream is the natural home for cross-workflow facts (per ADR-0005 §Decision).
- **Exit code 8 is not arbitrary** — it slots into the existing matrix without collision: 0 (success), 3 (NotApplicable / Phase 4 territory), 4 (Failed), 7 (RequiresHumanReview). 8 is one above, signaling "didn't even start." If the codebase already uses 8 for something else, surface the conflict.
- **`asyncio.run(orchestrator.run(...))`** is the single async boundary. Click is synchronous; the orchestrator is async; `asyncio.run` bridges. Do NOT make the click command itself async via a third-party plugin — the codebase convention is sync click commands that bridge to async via `asyncio.run` (mirrors Phase 0 / Phase 2 patterns).
- **`audit verify` extension reuses the chain-verification primitive from `src/codegenie/audit.py`.** Read it first; do not reimplement the BLAKE3 chain walk. The spanning-stream walk is the *same algorithm* — just over a different file with zstd decompression.
- **The path-scrubber regex for operator-facing messages** must already exist in Phase 0 / Phase 2 (search `src/codegenie/output/sanitizer.py` or similar). Reuse; do not reinvent.
- **`--cve` is required and validated via `CveId.parse(...)`** smart constructor (S1-01). Invalid format → click usage error → exit code 2 (click convention) with the parse error message. Do not silently coerce.
- **Repo-context staleness warning** is a *warning*, not an error: per Phase 1's freshness convention, a stale `repo-context.yaml` does not block remediation but is logged at WARN. Reuse the existing freshness-check API; do not duplicate.
- **The integration test for concurrent invocation is timing-sensitive.** Use a fixture that monkey-patches the orchestrator to `await asyncio.sleep(2.0)` mid-workflow so the second subprocess reliably hits the lock. Document this in the test docstring so a future reader doesn't "optimize" the sleep away.
