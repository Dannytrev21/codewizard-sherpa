# Story S8-03 — E2E `tests/e2e/test_remediate_with_sandbox.py` against `breaking-change-cve`

**Step:** Step 8 — Operator CLI surface + end-to-end smoke
**Status:** Ready
**Effort:** L
**Depends on:** S6-05, S8-02
**ADRs honored:** ADR-0002, ADR-0005, ADR-0007, ADR-0010

## Context

This is the **headline exit-criterion test** for Phase 5. Roadmap §"Phase 5" requires: *"No transform leaves the sandbox unverified. The three-retry loop is demonstrated end-to-end with at least one case that fails on retry-1 and recovers on retry-2."* S5-05 already lands the integration test at the `GateRunner` level; this story lands the **full process** test: `codegenie remediate --cve <fixture-cve>` invoked as a subprocess (or via `CliRunner` for speed) against `tests/fixtures/repos/breaking-change-cve/`, exercising every Phase 5 surface (DinD or Firecracker auto-detect, `RetryLedger` BLAKE3 chain extension, replan hook into Phase 4, cost-emitter, audit events) in one shot.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Test strategy — E2E (~5%)` — exact file path `tests/e2e/test_remediate_with_sandbox.py`; budgets 60–300 s.
  - `../phase-arch-design.md §Process view` — sequence diagram covering remediate → orchestrator → Phase 4 → GateRunner → SandboxClient → ledger; the assertions in this story trace those edges.
  - `../phase-arch-design.md §Component design — RetryLedger` — file layout `.codegenie/remediation/<run-id>/gates/<gate_id>/{attempts.jsonl,manifest.yaml}` + per-attempt `sandbox/<sandbox_run_id>/{stdout.log,stderr.log,trace.jsonl,policy.json,sbom.json}`.
  - `../phase-arch-design.md §Fixtures and data` — `tests/fixtures/repos/breaking-change-cve/` is the exit-criterion fixture; `tests/fixtures/vcr/cassette-attempt-1.yaml` and `cassette-attempt-2.yaml` carry the LLM responses.
- **Phase ADRs:**
  - `../ADRs/0002-additive-prior-attempts-kwarg.md` — attempt 2's prompt receives the attempt-1 `AttemptSummary` via the additive kwarg; covered by VCR cassette divergence between attempts.
  - `../ADRs/0005-phase4-chain-head-compatibility.md` — Phase 4's `chain_head.bin` is consumed at startup; the test verifies the post-run head matches the on-disk file.
  - `../ADRs/0007-pre-execute-marker-for-resume-safety.md` — every attempt writes a `pre_execute` marker before the `attempt` row; the test inspects both rows.
  - `../ADRs/0010-cost-sandbox-run-ledger-schema.md` — two cost rows (one per attempt) in `.codegenie/cost/sandbox.jsonl`; this story asserts shape and count.
- **Production ADRs:**
  - `../../../production/adrs/0014-three-retry-default-per-gate.md` — three retries baseline; this test runs with the default (no override).
- **Source design:**
  - `../final-design.md §Synthesis ledger row "Three-retry loop with replan hook"` — the exit-criterion expectation.
- **Existing code:**
  - `tests/fixtures/repos/breaking-change-cve/` (carry-forward from Phase 3/4 + S5-05).
  - `tests/fixtures/vcr/cassette-attempt-1.yaml`, `tests/fixtures/vcr/cassette-attempt-2.yaml` (from S5-05).
  - `src/codegenie/cli/remediate.py` after S8-02.
  - `tests/integration/gates/test_stage6_retry_recovers.py` (S5-05) — same fixture, lower scope.

## Goal

Land `tests/e2e/test_remediate_with_sandbox.py` that invokes `codegenie remediate --cve <fixture-cve>` against the `breaking-change-cve` fixture end-to-end, asserts gate passes on attempt 2, verifies two chained `attempts.jsonl` entries with distinct `sandbox_run_id` and `patch_blake3`, two `.codegenie/cost/sandbox.jsonl` rows, exit code 0, and every evidence-bundle path exists on disk.

## Acceptance criteria

- [ ] `tests/e2e/test_remediate_with_sandbox.py` exists, is marked `pytest.mark.e2e`, and runs in 60–300 s wall-clock on the reference runners (macOS Docker Desktop + Linux KVM CI).
- [ ] The test invokes `codegenie remediate --cve <fixture-cve> --repo <fixture-path>` via `click.testing.CliRunner` (or `subprocess.run` if process-level isolation is required for sandbox launch) and asserts **exit code 0**.
- [ ] VCR cassettes at `tests/fixtures/vcr/cassette-attempt-1.yaml` and `tests/fixtures/vcr/cassette-attempt-2.yaml` are wired via the same fixture S5-05 uses; the cassettes cover both LLM calls including the attempt-2 prompt containing the fenced `prior_failure_summary`.
- [ ] After the run, `.codegenie/remediation/<run-id>/gates/stage6_validate/attempts.jsonl` exists and contains **exactly two `attempt` rows** (interleaved with two `pre_execute` markers per ADR-0007); attempt 1 has `outcome.state == "failed_retryable"`, attempt 2 has `outcome.state == "passed"`.
- [ ] The two `attempt` rows have **distinct `sandbox_run_id`** values (different UUID7s) and **distinct `patch_blake3`** values (the LLM produced a different patch on retry).
- [ ] The BLAKE3 chain is valid: `RetryLedger(...).attempts()` over the same path raises no exception; `head()` matches the last row's `chain_hash` hex.
- [ ] `.codegenie/remediation/<run-id>/chain_head.bin` exists post-run and its bytes equal `ledger.head()` — Phase 4's chain head was extended through Phase 5 and re-written, per ADR-0005.
- [ ] `.codegenie/cost/sandbox.jsonl` exists and contains **exactly two `SandboxCostEntry` rows**, one per attempt; each row validates against `SandboxCostEntry.model_validate_json(line)`; `attempt_id` values are `{1, 2}` and `sandbox_run_id` matches the corresponding `attempts.jsonl` rows.
- [ ] Per-attempt evidence directories `.codegenie/remediation/<run-id>/gates/stage6_validate/sandbox/<sandbox_run_id>/` exist for both attempts and each contains all of: `stdout.log`, `stderr.log`, `trace.jsonl` (or a structured "trace unavailable" placeholder on macOS per arch §Risks #3), `sbom.json`. `policy.json` is present (digest-pinned per ADR-0013).
- [ ] No file under `.codegenie/remediation/<run-id>/` contains `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, or any string matching the env-allowlist deny substrings — verified by a grep-assertion over every artifact (closes the credential-leak class).
- [ ] On macOS the test passes with auto-detected DinD backend; on Linux-KVM CI it passes with auto-detected Firecracker backend; both paths share the same assertions (parametrize `auto_detect` via `monkeypatch` if needed for branch coverage, OR run twice in CI matrix).
- [ ] The test logs the final `attempts.jsonl` and `sandbox.jsonl` row counts as a structlog event `e2e.remediate_with_sandbox.summary` for CI postmortem.
- [ ] TDD plan's red test exists, is committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict tests/e2e`, `pytest -m e2e tests/e2e/test_remediate_with_sandbox.py` all pass.

## Implementation outline

1. Create `tests/e2e/__init__.py` if absent; register `e2e` marker in `pyproject.toml`/`pytest.ini`.
2. Create `tests/e2e/conftest.py` with two fixtures:
   - `e2e_repo` — copies `tests/fixtures/repos/breaking-change-cve/` to a tmp dir so the test never mutates the source fixture.
   - `vcr_cassettes` — wires both cassettes via the existing VCR config helper (re-use S5-05's setup).
3. Write `tests/e2e/test_remediate_with_sandbox.py::test_retry2_recovers_end_to_end(e2e_repo, vcr_cassettes, monkeypatch)`:
   - Set `CODEGENIE_HOME=tmp/.codegenie` via `monkeypatch.setenv` so the run is isolated.
   - Invoke `CliRunner().invoke(cli, ["remediate", "--cve", "CVE-2026-XXXX", "--repo", str(e2e_repo)])`.
   - Assert `result.exit_code == 0`.
   - Resolve `run_dir = next((e2e_repo / ".codegenie" / "remediation").iterdir())`.
   - Open `attempts.jsonl` and partition lines into `pre_execute` vs `attempt` by `kind` field; assert counts (2 + 2).
   - Build a `RetryLedger(run_dir, "stage6_validate", prev_chain_head=None)` and call `.attempts()` — assert no raise, list length 2, `[a.outcome.state for a in attempts] == ["failed_retryable", "passed"]`.
   - Diff `sandbox_run_id` and `patch_blake3` between the two attempts.
   - Open `.codegenie/cost/sandbox.jsonl`, parse each line via `SandboxCostEntry.model_validate_json`, assert 2 rows.
   - For each attempt, walk `gates/stage6_validate/sandbox/<sandbox_run_id>/` and assert presence of `stdout.log`, `stderr.log`, `trace.jsonl` (or trace-unavailable placeholder), `sbom.json`, `policy.json`.
   - Grep over every file under `run_dir` for deny-substring matches (`*KEY*`, `*TOKEN*`, `*SECRET*`, `*PASSWORD*`) → assert empty.
   - Compare `(run_dir.parent / "chain_head.bin").read_bytes()` against `RetryLedger(...).head()` — equal.
4. Add a second test `test_e2e_macos_auto_detect_uses_did` that `monkeypatch.setattr("codegenie.sandbox.registry._kvm_available", lambda: False)` and asserts the run still reaches `exit_code == 0` and `SandboxRun.backend == "docker_in_docker"` in both attempts (read from the `attempts.jsonl` `outcome.signals.build.details.backend` or wherever the backend is recorded).
5. Update `pyproject.toml`:
   - Register marker: `markers = ["e2e: end-to-end smoke (slow)"]`.
   - Optionally add `addopts = "--strict-markers"`.

## TDD plan — red / green / refactor

### Red

Test file path: `tests/e2e/test_remediate_with_sandbox.py`

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from codegenie.cli import cli
from codegenie.gates.retry_ledger import RetryLedger
from codegenie.sandbox.cost import SandboxCostEntry


_DENY_SUBSTRINGS = ("KEY", "TOKEN", "SECRET", "PASSWORD")


@pytest.mark.e2e
def test_retry2_recovers_end_to_end(e2e_repo: Path, vcr_cassettes, monkeypatch) -> None:
    result = CliRunner().invoke(
        cli, ["remediate", "--cve", "CVE-2026-FIXTURE", "--repo", str(e2e_repo)]
    )

    assert result.exit_code == 0, result.output

    run_dir = next((e2e_repo / ".codegenie" / "remediation").iterdir())
    jsonl = run_dir / "gates" / "stage6_validate" / "attempts.jsonl"
    assert jsonl.exists()

    lines = [json.loads(ln) for ln in jsonl.read_text().splitlines()]
    pre = [ln for ln in lines if ln.get("kind") == "pre_execute"]
    att = [ln for ln in lines if ln.get("kind") == "attempt"]
    assert len(pre) == 2 and len(att) == 2, "two pre_execute markers and two attempt rows"

    assert att[0]["outcome"]["state"] == "failed_retryable"
    assert att[1]["outcome"]["state"] == "passed"
    assert att[0]["sandbox_run_id"] != att[1]["sandbox_run_id"], "distinct sandbox runs"
    assert att[0]["patch_blake3"] != att[1]["patch_blake3"], "LLM produced a new patch"

    # chain verification round-trip
    ledger = RetryLedger(run_dir=run_dir, gate_id="stage6_validate", prev_chain_head=None)
    attempts = ledger.attempts()
    assert [a.attempt_id for a in attempts] == [1, 2]

    # chain head extended
    head_bin = run_dir / "chain_head.bin"
    assert head_bin.exists()
    assert head_bin.read_bytes() == ledger.head()

    # cost rows
    cost_lines = (run_dir.parent.parent / "cost" / "sandbox.jsonl").read_text().splitlines()
    assert len(cost_lines) == 2
    parsed = [SandboxCostEntry.model_validate_json(ln) for ln in cost_lines]
    assert sorted(p.attempt_id for p in parsed) == [1, 2]

    # evidence bundle paths
    for a in att:
        ev = run_dir / "gates" / "stage6_validate" / "sandbox" / a["sandbox_run_id"]
        assert (ev / "stdout.log").exists()
        assert (ev / "stderr.log").exists()
        assert (ev / "sbom.json").exists()
        assert (ev / "policy.json").exists()
        # trace.jsonl may be a placeholder on macOS — accept either content or marker file
        assert (ev / "trace.jsonl").exists() or (ev / "trace.unavailable").exists()

    # no credentials anywhere in the run dir
    for p in run_dir.rglob("*"):
        if p.is_file():
            data = p.read_bytes()
            for needle in _DENY_SUBSTRINGS:
                assert needle.encode() not in data, f"deny-substring {needle} leaked into {p}"
```

### Green

The test should already pass if S5-05, S6-05, S7-03, S8-01, and S8-02 landed correctly — this story's "green" is mostly wiring fixtures (`e2e_repo`, `vcr_cassettes`) and resolving the on-disk paths the CLI actually produces. If anything is missing, surface the gap in `_attempts/S8-03.md` and fix in the responsible upstream module — do NOT paper over by relaxing the assertion.

### Refactor

- Extract the path-resolution logic (`run_dir`, `cost.jsonl`) into `tests/e2e/_paths.py` so S8-04's coverage check can reuse it.
- Move `_DENY_SUBSTRINGS` to share with `tests/schema/test_env_allowlist_no_credentials.py` if the constants don't already live in one place — surface the duplication as a story-spawn candidate, do not fork.
- Add structured `structlog.get_logger().info("e2e.remediate_with_sandbox.summary", ...)` at test-end for CI log forensics.
- Parametrize across `(backend="auto", backend="did", backend="firecracker")` if and only if both CI runners are present in the matrix — otherwise gate `firecracker` parametrization on `skip_if_no_kvm`.

## Files to touch

| Path | Why |
|---|---|
| `tests/e2e/__init__.py` | Make `tests.e2e` a package. |
| `tests/e2e/conftest.py` | `e2e_repo`, `vcr_cassettes` fixtures. |
| `tests/e2e/test_remediate_with_sandbox.py` | The headline test. |
| `tests/e2e/_paths.py` | Path helpers (refactor target). |
| `pyproject.toml` (or `pytest.ini`) | Register `e2e` marker; add `addopts = "--strict-markers"` if not already set. |

## Out of scope

- ADR audit + final coverage report — S8-04.
- Performance regression / wall-clock budgets — S7-02 already covers; this E2E is **correctness**, not a perf test.
- Negative-case E2E (CVE that escalates) — desirable but not exit-criterion-mandated; if appetite remains, file as a follow-on story.
- Cross-OS testing beyond macOS DinD and Linux Firecracker — Windows is out of scope for Phase 5.
- Removing the VCR cassette dependency by hitting a real LLM — never; that violates the determinism principle.

## Notes for the implementer

- The fixture CVE id (`CVE-2026-FIXTURE` in the test stub) must match what the fixture's metadata declares. If `breaking-change-cve/` has a different ID, use that — do not edit the fixture.
- VCR cassettes were recorded against a specific request hash. If `S5-03`'s `FenceWrapper.compose_prior_attempts` changed the prompt shape, the cassettes need to be re-recorded — surface that as a blocker, not a flake.
- The two `attempt` rows MUST have distinct `patch_blake3`. If they're equal, either (a) Phase 4's replan didn't actually re-call the LLM, or (b) the LLM returned the same patch — the test fails loudly, which is correct.
- `chain_head.bin` is *re-written* by Phase 5 to extend the chain (per ADR-0005). The test asserts the *post-run* equality with `ledger.head()`. Do not confuse this with the *startup* check (which is `RetryLedger.__init__`'s job and tested in S2-03).
- The deny-substring grep is intentionally over *every* artifact under `run_dir`, including logs. If a contributor's CVE description happens to contain "TOKEN" as a substring, the test will fail; that's a fixture-content problem, not a test bug — pick a CVE without such substrings.
- On macOS, `trace.jsonl` may be absent because of the SYS_PTRACE limitation (arch §Risks #3). Accept either the file or a `trace.unavailable` marker file written by the trace collector; do not skip the assertion entirely.
- Wall-clock 60–300 s is a *budget*, not a target. If the test ever exceeds 300 s on the reference runner, treat as a blocker for S8-04 closure.
- If `e2e_repo` is a `git` worktree, ensure `git status` is clean post-run or the next attempt may operate on a dirty tree; the fixture should be a *copy*, not a worktree.
