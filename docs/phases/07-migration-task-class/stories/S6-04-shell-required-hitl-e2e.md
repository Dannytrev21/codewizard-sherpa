# Story S6-04 — Shell-required HITL E2E

**Step:** Step 6 — Broaden coverage: adversarial Dockerfile corpus, second E2E fixture, HITL path, LLM-fallback path
**Status:** Ready
**Effort:** M
**Depends on:** S5-08
**ADRs honored:** ADR-P7-001 (`@register_gate_probe`), ADR-P7-009 (`DistrolessLedger`), ADR-P7-012 (parallel CLI verbs), ADR-P7-013 (shell trace runs gate-time)

## Context

Some services *cannot* migrate to distroless because they shell out at runtime — `/admin` routes that spawn `sh -c "..."`, init scripts, anything that requires `/bin/sh`. Phase 7's strict-AND gate must catch these before a broken patch lands. This story lands the third E2E flow (after the Node happy path S5-06 and the static-Go path S6-03): a Node service whose `/admin` route conditionally shells out, the strace gate observes `runtime_shell_count > 0`, the strict-AND gate fails non-retryable, the loop routes to `await_human`, and a mocked `HumanDecision(action="abort")` returns the loop cleanly to CLI exit code 12.

The story is the canonical *failure* path: the loop did its job by refusing to ship a patch that would break the service in production. It's also the load-bearing fixture for Risk #1 — that strict-AND on three independent signals (CVE delta, dive, shell trace) is what makes the distroless gate trustworthy.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Scenarios ›Scenario 3` (lines 439–475) — strace failure → retry → HITL control flow
  - `../phase-arch-design.md §Component 2 ›ShellInvocationTraceProbe` — what the probe emits and how it lights up the strict-AND gate
  - `../phase-arch-design.md §Component 8 ›Signal collectors` — `ShellInvocationTraceSignal`: `observed shell → passed=False, retryable=False` (non-retryable failure routes directly to HITL once retries exhaust, but observed-shell skips the retries)
  - `../phase-arch-design.md §Testing strategy ›Integration tests ›test_migrate_shell_required_hitl` (line 1232) — assertion shape
  - `../phase-arch-design.md §Fixture portfolio ›shell-required-distroless` (line 1268)
  - `../phase-arch-design.md §Implementation-level risks #1` — Risk #1 = false-negative shell detection; this fixture is its existence proof
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0002-register-gate-probe-new-registry.md` — ADR-P7-001 — `ShellInvocationTraceProbe` only runs at gate-time via the new registry
  - `../ADRs/0013-shell-trace-runs-gate-time-in-phase5-chokepoint.md` — ADR-P7-014 — trace runs *inside* the Phase 5 sandbox chokepoint
  - `../ADRs/0011-distroless-ledger-parallel-to-vuln-ledger.md` — ADR-P7-009 — `await_human` interrupt and `HumanRequest`/`HumanDecision` are reused verbatim from Phase 6
- **Existing code:**
  - `src/codegenie/probes/shell_invocation_trace.py` (S3-02) — emits `runtime_shell_count`, `confidence`, `entrypoint_steady`
  - `src/codegenie/sandbox/signals/shell_invocation_trace.py` (S3-05) — strict-AND collector
  - `src/codegenie/graph/nodes/distroless/{validate_in_sandbox,record_attempt,await_human,escalate}.py` (S5-03) — HITL routing
  - `src/codegenie/cli/migrate.py` (S5-05) — CLI exit codes; `12 = paused_at_human`
  - `src/codegenie/graph/distroless_loop.py` (S5-04) — `interrupt_before=["await_human"]`
- **Phase 6 prior art:**
  - Phase 6's vuln HITL E2E pattern — `HumanRequest`/`HumanDecision` shape is reused verbatim

## Goal

`tests/integration/test_migrate_shell_required_hitl.py` migrates a Node service whose runtime shells out, the strict-AND gate fails with `shell_invocation_trace.passed=False`, the loop routes to `await_human` with `HumanRequest.reason` correctly set, and a mocked `HumanDecision(action="abort")` aborts the migration cleanly with CLI exit code 12.

## Acceptance criteria

- [ ] `tests/fixtures/repos/shell-required-distroless/` exists with: minimal Node Express service whose `/admin` route invokes `child_process.exec("sh -c 'date'")` *conditionally* (so the probe must actually run the container long enough to catch it), `package.json`, single-stage `Dockerfile` (base `node:20-bullseye-slim`), `.dockerignore`, git-initialised state. A `README.md` documents *why* this fixture exists (Risk #1).
- [ ] `tests/integration/test_migrate_shell_required_hitl.py` exists and is green on Linux DinD.
- [ ] The test invokes `codegenie migrate run` and asserts:
  - The loop *enters* `await_human` (not `emit_artifact`).
  - The `HumanRequest.reason` matches the format `"shell_required:<runtime_shell_count>:<top_invoking_path>"` (or whatever S3-02's contract says — fail loudly if it doesn't match).
  - The `DistrolessLedger.last_outcome.signals.shell_invocation_trace.passed == False` and `retryable == False`.
  - `ledger.failing_signals == ["shell_invocation_trace"]`.
  - CLI exits with code `12` (`paused_at_human`) on first run.
- [ ] After receiving a mocked `HumanDecision(action="abort", note="acknowledged: service requires shell")`:
  - `codegenie migrate resume` returns and exits cleanly (exit code per the CLI exit-code table; per S5-05 `13` is `aborted_by_human`).
  - `ledger.retry_count` is not incremented past the abort.
  - No patch is written to disk (`patch.diff` absent under `.codegenie/migration/<run-id>/`).
  - The `migration-report.yaml` final status is `"aborted_by_human"` with the operator's note preserved.
- [ ] The test does **not** retry: `ShellInvocationTraceSignal.retryable=False` for observed-shell (per S3-05's contract) means the loop short-circuits to `await_human` on the first attempt, not after three retries.
- [ ] If the test author chooses the post-3-retry route (because S3-05's contract sets `retryable=True` on `confidence != "high"` only, and a clear `runtime_shell_count > 0` *is* high-confidence and therefore non-retryable), document the assertion clearly in a test docstring and align with `phase-arch-design.md §Component 8`.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict` clean on touched files.

## Implementation outline

1. Build the fixture repo. The Node service exposes `GET /healthz` (no shell) and `GET /admin/debug` (shells out via `child_process.exec("sh -c 'date'")`). The container's CMD is `["node", "server.js"]`. The strace probe needs to observe the shell invocation: either the probe synthesizes a `GET /admin/debug` call (via the gate-time sandbox runner's HTTP probe), or the test fixture's `Dockerfile.test` includes a `HEALTHCHECK` that hits `/admin/debug` so a shell invocation happens during the probe window.
2. Decide how the gate-time probe observes the shell — read S3-02's contract carefully. If the probe relies on `entrypoint_steady` alone, the fixture must shell out at startup (init script). If it includes an HTTP synthetic probe, the `/admin/debug` route is fine. Align with S3-02.
3. Write the red test asserting `await_human` was entered with the correct `HumanRequest.reason`. Run; red because no fixture or because the contract isn't wired through.
4. Materialize the fixture; run; observe the `await_human` interrupt; record the `HumanRequest` shape; encode the assertion.
5. Mock the `HumanDecision(action="abort")` by either (a) injecting via `graph.update_state(config, {"human_decision": ...})` and resuming, or (b) using the existing Phase 6 HITL test harness. Reuse Phase 6's helper.
6. Assert clean exit + no patch + report status.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/integration/test_migrate_shell_required_hitl.py`

```python
# tests/integration/test_migrate_shell_required_hitl.py
import json
from pathlib import Path

from click.testing import CliRunner

from codegenie.cli.migrate import migrate
from codegenie.graph.state_distroless import DistrolessLedger

FIXTURE = Path(__file__).parent.parent / "fixtures" / "repos" / "shell-required-distroless"

def test_migrate_shell_required_pauses_at_human(tmp_path, snapshot_runner) -> None:
    # arrange
    repo = snapshot_runner.copy_fixture(FIXTURE, tmp_path)

    # act — first invocation pauses at await_human
    runner = CliRunner()
    result = runner.invoke(migrate, ["run", str(repo), "--target", "distroless",
                                     "--cve", "CVE-2024-FAKE-NODE-RUNTIME"])

    # assert — paused, not failed
    assert result.exit_code == 12, f"expected paused_at_human (12), got {result.exit_code}: {result.output}"

    ledger = _read_latest_ledger(repo)
    assert ledger.last_outcome.signals.shell_invocation_trace.passed is False
    assert ledger.last_outcome.signals.shell_invocation_trace.retryable is False
    assert ledger.failing_signals == ["shell_invocation_trace"]
    # HumanRequest.reason carries the shell count and a path
    req = ledger.pending_human_request
    assert req is not None
    assert req.reason.startswith("shell_required:")

def test_migrate_shell_required_resumes_with_abort_decision_cleanly(tmp_path, snapshot_runner) -> None:
    # arrange — run + pause as above
    repo = snapshot_runner.copy_fixture(FIXTURE, tmp_path)
    runner = CliRunner()
    runner.invoke(migrate, ["run", str(repo), "--target", "distroless",
                            "--cve", "CVE-2024-FAKE-NODE-RUNTIME"])

    # act — submit abort decision
    decision = json.dumps({"action": "abort", "note": "service requires /bin/sh; not migratable"})
    result = runner.invoke(migrate, ["resume", str(repo), "--decision", decision])

    # assert — clean abort, no patch, report records abort
    assert result.exit_code == 13, f"expected aborted_by_human (13), got {result.exit_code}: {result.output}"
    ledger = _read_latest_ledger(repo)
    assert ledger.final_status == "aborted_by_human"
    assert not (repo / ".codegenie" / "migration" / ledger.run_id / "patch.diff").exists()
```

Red: most likely the fixture doesn't exist, or `runtime_shell_count` reports 0 because the probe doesn't see the `/admin/debug` route firing — surfaces an S3-02 contract clarification.

### Green — make it pass

- Materialize the fixture. Choose the shell-out shape that S3-02's probe is guaranteed to observe (init script that runs `sh -c 'date'` once, then runs the Node app — easier than synthesizing an HTTP request).
- Wire the test through the `CliRunner`; reuse Phase 6's HITL helper to inject the `HumanDecision`.
- If the abort path doesn't exit cleanly, debug at `escalate` / `await_human` (S5-03) — *do not* coerce the exit code.

### Refactor — clean up

- Add a third assertion that the `audit_chain` contains a `gate_failed:shell_invocation_trace` entry — the audit chain is what gives the failure forensic value.
- Confirm the run-id directory layout matches Gap 1's chain-no-collision contract (workflow_id starts with `wf:distroless:`).
- Document the fixture's purpose in its `README.md` — Risk #1 mitigation, not a "test we hope passes".

## Files to touch

| Path | Why |
|---|---|
| `tests/fixtures/repos/shell-required-distroless/server.js` | New — Node Express service with `/admin/debug` shell-out |
| `tests/fixtures/repos/shell-required-distroless/package.json` | New |
| `tests/fixtures/repos/shell-required-distroless/Dockerfile` | New — single-stage `node:20-bullseye-slim`; init script runs `sh -c 'date'` |
| `tests/fixtures/repos/shell-required-distroless/init.sh` | New — init script that triggers the shell observation |
| `tests/fixtures/repos/shell-required-distroless/.dockerignore` | New |
| `tests/fixtures/repos/shell-required-distroless/README.md` | New — Risk #1 fixture purpose |
| `tests/fixtures/advisories/cve-2024-fake-node-runtime.yaml` | New — synthetic advisory |
| `tests/integration/test_migrate_shell_required_hitl.py` | New — the HITL E2E |

## Out of scope

- **The `HumanRequest`/`HumanDecision` Pydantic models** — reused verbatim from Phase 6; this story does not add fields.
- **The strace probe's contract** — established in S3-02; this story exercises it.
- **Building the shell-required image and validating it against grype** — the test runs the full sandbox; this story does not add new sandbox infra.
- **A "shell required, but accept anyway" decision path** — not in scope per the design; HITL options are `abort` and `replan`. `replan` is the LLM-fallback path, covered by S6-06.
- **Retries on observed shell** — per S3-05, `runtime_shell_count > 0` with `confidence=high` is non-retryable. If you find the gate retries before HITL, surface a refactor to S3-05.

## Notes for the implementer

- The fixture's shell-out must happen **during the strace window** — typically the first 30 s after container start. An init script that runs `sh -c 'date'` once before exec'ing the Node app is the simplest reliable shape. *Avoid* relying on `child_process` from JS being observable — Node's runtime can lazy-load `sh` in ways the probe might miss; the init-script approach makes the trace deterministic.
- If S3-02's `HumanRequest.reason` format differs from what this story assumes (`"shell_required:<count>:<path>"`), match S3-02's contract exactly — do not invent. Test failures here are loud, not silent.
- The `runtime_shell_count == 0` semantic from `phase-arch-design.md §Component 8` is the *passing* condition. A non-zero count → `passed=False, retryable=False`. The test fixture is engineered to produce a *clear* nonzero count.
- The mocked `HumanDecision` injection convention is Phase 6's. If S5-03's `await_human` import-from-Phase-6 has drifted, reconcile **at S5-03**, not by hand-rolling a new injection in this test.
- Per `phase-arch-design.md §Implementation-level risks #1`, this fixture is the safety belt for false-negative shell detection. If the probe fails to flag the fixture, the entire phase ships an unsafe gate. The test should NOT be marked `xfail` under any condition.
- The CLI exit codes follow `phase-arch-design.md §Component 12` and S5-05: `12 = paused_at_human`, `13 = aborted_by_human`. Do not coerce these to `0` or `1`.
- Update story `Status:` to `Done` when complete.
