# Story S3-07 — DinD integration suite against `hello-node`

**Step:** Step 3 — Implement DinD backend + SandboxSpecBuilder + SandboxHealthProbe
**Status:** Ready
**Effort:** L
**Depends on:** S3-03 (build + network chokepoints), S3-04 (copy-out + OOM + timeout), S3-05 (populated YAML catalogs + digest-pinned policy)
**ADRs honored:** ADR-0001 (chokepoints still in place — integration must not bypass), ADR-0004 (DinD = `shared_kernel`), ADR-0012 (env-allowlist applied), ADR-0013 (policy YAML digest verified)

## Context

This story is the first end-to-end exercise of the DinD backend against a real Docker daemon. It validates that S3-01 through S3-05 compose correctly: `SandboxSpecBuilder` produces a byte-stable spec, `DockerInDockerClient` executes it, copy-out/OOM/timeout work for real (not mocked), and the iptables `network=scoped` allowlist behaves as designed against live `registry.npmjs.org`. Phase exit-criterion §Goal 5 ("macOS DinD via Docker Desktop, `gate_isolation_class: shared_kernel`") and §Goal 10 (latency on `hello-node`) both depend on this story passing.

Four integration tests + a golden-file spec test + a hash property test. Marked with `pytest.mark.integration` and `pytest.mark.requires_docker`; skipped if `docker.from_env().ping()` fails so contributors without Docker Desktop installed still see green local runs.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design — DockerInDockerClient` — performance envelope (`p50 ≤ 90 s, p95 ≤ 180 s`).
  - `../phase-arch-design.md §Testing strategy — Integration` — `tests/integration/sandbox/test_*.py`; `pytest-docker` for rootless DinD.
  - `../phase-arch-design.md §Goal 5 / 10` — exit-criteria this story closes.
  - `../phase-arch-design.md §Scenario 1` — happy path sequence diagram.
  - `../phase-arch-design.md §Edge cases #3, #4, #5` — timeout / OOM / egress block.
  - `../phase-arch-design.md §Implementation-level risks #3` — macOS strace warning surfaced, not blocking.
- **Phase ADRs:**
  - `../ADRs/0001-two-chokepoint-sandbox-seam.md` — integration test must not bypass the chokepoint discipline; fence test stays green throughout.
  - `../ADRs/0004-dind-default-macos-with-gate-isolation-class.md` — integration asserts `gate_isolation_class == "shared_kernel"`.
- **Source design:**
  - `../final-design.md §Synthesis ledger — Sandbox stack` rows that justify DinD on macOS.
- **Existing code:**
  - `tests/fixtures/repos/hello-node/` — Phase 3/4 carryover; verify presence (test should `pytest.skip` with clear message if missing).
  - `src/codegenie/sandbox/spec_builder.py` (S3-01), `did/client.py` (S3-02 + S3-03 edits + S3-04 edits), `gates/catalog/stage6_validate.yaml` (S3-05).
- **External docs:**
  - https://docs.docker.com/desktop/ — Docker Desktop requirement on macOS.
  - https://pytest-docker.readthedocs.io/ — `pytest-docker` plugin if used for fixture orchestration.

## Goal

Land four `pytest.mark.integration` tests against a real Docker daemon plus a spec-builder golden-file test and a `sandbox_spec_hash` env-reorder property test, all green on macOS Docker Desktop and Linux CI.

## Acceptance criteria

- [ ] `tests/integration/sandbox/test_did_hello_node.py` — boots DinD, executes a no-op `npm --version` `SandboxSpec` built from `stage6_validate.yaml` against `hello-node`, asserts `SandboxRun.exit_code == 0`, `gate_isolation_class == "shared_kernel"`, `backend == "docker_in_docker"`, `logs_dir / "stdout.log"` contains the version string.
- [ ] `tests/integration/sandbox/test_did_oom.py` — `memory_limit_mib=16` + `cmd=["sh","-c","python3 -c 'x=b\"a\"*10**9'"]` (or equivalent OOM-inducer); asserts `SandboxRun.killed_by_oom is True`, `timed_out is False`.
- [ ] `tests/integration/sandbox/test_did_timeout.py` — `time_budget_seconds=1` + `cmd=["sleep","30"]`; asserts `SandboxRun.timed_out is True`, `killed_by_oom is False`, `exit_code == 137`.
- [ ] `tests/integration/sandbox/test_did_egress_blocked.py` — `network=scoped` with `egress_allowlist=["registry.npmjs.org"]`; asserts `curl https://github.com` fails inside the sandbox (exit non-zero) while `curl https://registry.npmjs.org` succeeds.
- [ ] `tests/sandbox/test_spec_builder.py::test_for_gate_attempt1_matches_golden` (already added in S3-01) **runs and passes** in this story's CI matrix — listed here because it's the unit-level companion that locks the spec shape.
- [ ] `tests/sandbox/test_spec_hash_property.py` (S3-01) green on this story's run too.
- [ ] All four integration tests carry `pytest.mark.integration` and `pytest.mark.requires_docker`; skip cleanly with a clear message when `docker.from_env().ping()` raises.
- [ ] `tests/schema/test_no_subprocess_outside_build_chokepoint.py`, `test_no_llm_imports_in_sandbox.py`, `test_env_allowlist_no_credentials.py`, `test_digests_yaml.py` all green at end of this story.
- [ ] CLI smoke: `codegenie sandbox health` (stub-CLI is sufficient — S8-01 ships the full one; this story may inline a `python -m codegenie.cli.sandbox health` invocation) prints `reachable=True` on a healthy Docker Desktop and structured reasons on a stopped daemon (manual verification, recorded in `_attempts/S3-07.md`).
- [ ] hello-node `npm --version` wall-clock duration recorded in `.codegenie/perf/` (Step 7's perf gate consumes it later; this story just emits the row).
- [ ] TDD plan's red test exists, is committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `pytest -m "integration and requires_docker"` pass on macOS Docker Desktop and Linux CI.

## Implementation outline

1. Create `tests/integration/sandbox/conftest.py`:
   - Session-scoped fixture `docker_available` that calls `docker.from_env().ping()`; failure → `pytest.skip("Docker daemon unavailable")`.
   - Fixture `hello_node_repo` returning `Path("tests/fixtures/repos/hello-node")`; skip if missing.
   - Fixture `stage6_spec_builder` wiring `GateCatalogLoader` + `EnvAllowlist` + `SandboxSpecBuilder`.
2. `test_did_hello_node.py`:
   - Build `SandboxSpec` via `spec_builder.for_gate(stage6_validate, attempt=1, ctx=ctx_for(hello_node_repo))`, override `cmd=["npm","--version"]` (or use a tiny `attempt_overrides` block via a test-only catalog).
   - Execute via `DockerInDockerClient()`; assert run fields.
3. `test_did_oom.py`: similar, override `memory_limit_mib=16`, supply OOM-inducing cmd.
4. `test_did_timeout.py`: override `time_budget_seconds=1`, supply `sleep 30`.
5. `test_did_egress_blocked.py`:
   - First sub-test: `cmd=["sh","-c","curl -sfo /dev/null https://registry.npmjs.org/ && echo ok"]` → exit 0.
   - Second sub-test: `cmd=["sh","-c","curl -sfo /dev/null https://github.com/ && echo ok || echo blocked"]` → stdout `blocked`.
   - Both runs share the same `egress_allowlist=["registry.npmjs.org"]`.
6. Record perf row: after `test_did_hello_node`, append a JSONL line to `.codegenie/perf/<date>.jsonl` with `{scenario, duration_ms, backend}`.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/integration/sandbox/test_did_hello_node.py` (the smallest of the four — start here, then add the others).

```python
# tests/integration/sandbox/test_did_hello_node.py
import pytest
from codegenie.sandbox.did.client import DockerInDockerClient

pytestmark = [pytest.mark.integration, pytest.mark.requires_docker]

def test_did_hello_node_npm_version(docker_available, stage6_spec_builder, hello_node_repo, allowlist):
    """The first real-daemon assertion that the entire stack composes.
    Catches: SDK mis-config, missing chokepoints, env filter bypass, golden drift between
    spec_builder and what actually runs."""
    spec = stage6_spec_builder.for_gate_test_override(
        gate_id="stage6_validate",
        attempt=1,
        worktree=hello_node_repo,
        cmd_override=["npm", "--version"],
    )
    run = DockerInDockerClient(allowlist=allowlist).execute(spec)

    assert run.exit_code == 0, f"npm --version failed: {run.logs_dir / 'stderr.log'!r}"
    assert run.backend == "docker_in_docker"
    assert run.gate_isolation_class == "shared_kernel"
    assert run.timed_out is False
    assert run.killed_by_oom is False
    # The stdout MUST contain a version string. Hardcoding the version is brittle; pattern instead.
    stdout = (run.logs_dir / "stdout.log").read_text()
    import re
    assert re.search(r"\d+\.\d+\.\d+", stdout), f"no version in stdout: {stdout!r}"
```

```python
# tests/integration/sandbox/test_did_oom.py
import pytest
from codegenie.sandbox.did.client import DockerInDockerClient

pytestmark = [pytest.mark.integration, pytest.mark.requires_docker]

def test_oom_flag_set_on_memory_exhaustion(docker_available, stage6_spec_builder, hello_node_repo, allowlist):
    spec = stage6_spec_builder.for_gate_test_override(
        gate_id="stage6_validate", attempt=1, worktree=hello_node_repo,
        cmd_override=["sh", "-c", "python3 -c 'x=bytearray(10**9)'"],
        memory_limit_mib=16,
    )
    run = DockerInDockerClient(allowlist=allowlist).execute(spec)
    assert run.killed_by_oom is True, "OOMKilled flag missed — Edge case #4 regression"
    assert run.timed_out is False
```

```python
# tests/integration/sandbox/test_did_timeout.py
import pytest
from codegenie.sandbox.did.client import DockerInDockerClient

pytestmark = [pytest.mark.integration, pytest.mark.requires_docker]

def test_timeout_triggers_sigkill_and_137(docker_available, stage6_spec_builder, hello_node_repo, allowlist):
    spec = stage6_spec_builder.for_gate_test_override(
        gate_id="stage6_validate", attempt=1, worktree=hello_node_repo,
        cmd_override=["sleep", "30"], time_budget_seconds=1,
    )
    run = DockerInDockerClient(allowlist=allowlist).execute(spec)
    assert run.timed_out is True
    assert run.exit_code == 137
    assert run.killed_by_oom is False
```

```python
# tests/integration/sandbox/test_did_egress_blocked.py
import pytest
from codegenie.sandbox.did.client import DockerInDockerClient

pytestmark = [pytest.mark.integration, pytest.mark.requires_docker]

def test_scoped_allows_npmjs_blocks_github(docker_available, stage6_spec_builder, hello_node_repo, allowlist):
    """The iptables chokepoint (S3-03) actually drops github.com while permitting npmjs.org.
    Catches a regression where _compute_rules produces correct argv but apply() runs them
    in the wrong namespace."""
    ok = stage6_spec_builder.for_gate_test_override(
        gate_id="stage6_validate", attempt=1, worktree=hello_node_repo,
        cmd_override=["sh", "-c", "curl -sfo /dev/null https://registry.npmjs.org/ && echo ok"],
        network="scoped", egress_allowlist=["registry.npmjs.org"],
    )
    blocked = stage6_spec_builder.for_gate_test_override(
        gate_id="stage6_validate", attempt=1, worktree=hello_node_repo,
        cmd_override=["sh", "-c", "(curl -sfo /dev/null https://github.com/ && echo ok) || echo blocked"],
        network="scoped", egress_allowlist=["registry.npmjs.org"],
    )
    client = DockerInDockerClient(allowlist=allowlist)
    run_ok = client.execute(ok)
    run_blocked = client.execute(blocked)
    assert run_ok.exit_code == 0
    assert "ok" in (run_ok.logs_dir / "stdout.log").read_text()
    assert "blocked" in (run_blocked.logs_dir / "stdout.log").read_text()
```

### Green — make it pass

- Add `for_gate_test_override(...)` test helper on `SandboxSpecBuilder` that takes the same base catalog but applies inline overrides — keep in `tests/sandbox/conftest.py`, not in the production class.
- Run all four tests against macOS Docker Desktop locally; fix any drift surfaced in S3-02/03/04 by surgical edits to those stories' files.
- Verify CI matrix runs the suite on Linux with Docker available.

### Refactor — clean up

- Consolidate fixtures into `tests/integration/sandbox/conftest.py`.
- Add structured pytest IDs so failures point at the specific scenario.
- Verify the perf JSONL line writes once per session, not per test.
- Update `_attempts/S3-07.md` with manual `codegenie sandbox health` smoke results (daemon up vs daemon stopped).

## Files to touch

| Path | Why |
|---|---|
| `tests/integration/sandbox/__init__.py` | New subpackage marker. |
| `tests/integration/sandbox/conftest.py` | New — `docker_available`, `hello_node_repo`, `stage6_spec_builder` fixtures. |
| `tests/integration/sandbox/test_did_hello_node.py` | New — happy path on real daemon. |
| `tests/integration/sandbox/test_did_oom.py` | New — OOM flag on real daemon. |
| `tests/integration/sandbox/test_did_timeout.py` | New — SIGKILL path on real daemon. |
| `tests/integration/sandbox/test_did_egress_blocked.py` | New — iptables behavior verified. |
| `tests/sandbox/conftest.py` | Edit — add `for_gate_test_override` test helper. |
| `pyproject.toml` or `pytest.ini` | Edit — register `integration`, `requires_docker` markers if not already registered. |

## Out of scope

- Six signal collectors (build/install/tests/trace/policy/cve_delta) — Step 4 owns; this story only checks `SandboxRun` shape, not signals.
- `GateRunner` retry loop — Step 5.
- Firecracker — Step 6.
- Perf regression gates — Step 7 (this story only writes the perf row).
- `codegenie sandbox health` Click CLI — S8-01.

## Notes for the implementer

- **Skip cleanly, do not fail, when Docker is unavailable.** Contributors without Docker Desktop installed must still see green local runs; only the CI matrix that ships Docker actually enforces these tests.
- The egress block test is the only one that requires the iptables chokepoint to be *correctly* wired into Docker's network namespace. If `_compute_rules` is correct but `apply()` runs in the wrong namespace, `curl github.com` will succeed and the test fails. The fix is in S3-03; do not paper over here.
- macOS Docker Desktop has a known quirk: occasionally `container.kill(signal="SIGKILL")` returns success but `wait()` hangs. Use `wait(timeout=10)` on the second wait too and treat hang as a flake-class failure with a clear assertion message — escalate as a Risk #3 follow-up if it recurs.
- **Don't disable a test to make the suite green.** If `test_did_oom` flakes on shared CI runners due to memory contention, mark with `pytest.mark.flaky(reruns=2)` and surface in `_attempts/S3-07.md`. Per CLAUDE.md Rule 12 (Fail loud).
- The OOM test cmd `python3 -c 'x=bytearray(10**9)'` requires Python in the base image — the Chainguard `cgr.dev/chainguard/node` image typically has it; if not, use a Node equivalent: `node -e "Buffer.alloc(1e9)"`.
- The `hello-node` fixture is Phase 3/4 carryover — if absent, the four tests must skip with a clear message pointing at `docs/phases/03-*/stories/` for restoration. Do not regenerate the fixture in this story.
- After this story lands, Step 4 begins on a known-working `SandboxRun` producer. Any drift in `SandboxRun` shape introduced later breaks every collector — keep the fields locked.
