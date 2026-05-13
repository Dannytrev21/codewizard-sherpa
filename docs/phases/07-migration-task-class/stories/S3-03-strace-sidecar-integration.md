# Story S3-03 — Strace sidecar PID-share + idempotence integration tests

**Step:** Step 3 — Land `BaseImageProbe`, `ShellInvocationTraceProbe`, and the four signal collectors
**Status:** Ready
**Effort:** M
**Depends on:** S3-02
**ADRs honored:** ADR-0013 (gate-time strace in Phase 5 chokepoint, sidecar PID-share, 30 s budget), ADR-P7-005 (Phase 2 `RuntimeTraceProbe` stub preserved), ADR-0008 (facts-not-judgments — idempotent evidence must be byte-stable)

## Context

S3-02 specified the sibling-sidecar pattern (`docker run --pid=container:<candidate>`) and the 30 s strace budget but mocked the subprocess at the unit level. This story is the **real-Docker** integration coverage: two tests that exercise the sidecar against an actual candidate container and assert (1) the candidate's PID 1 remains the candidate's own entrypoint — *not* strace — and (2) re-running the trace on the same candidate digest produces a **byte-identical** `ShellInvocationTrace` (idempotence; preserves the determinism commitment in `CLAUDE.md` and feeds the contract-surface snapshot's reproducibility promise).

This is the test that closes Gap 4 (ENTRYPOINT-wrapper anti-pattern would mutate PID 1) for real and the test that closes the idempotence claim in `phase-arch-design.md §Harness engineering ›Idempotence`. It runs under DinD on Linux CI and on macOS Docker Desktop locally.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design ›2. ShellInvocationTraceProbe` — internal-structure step 2: the candidate is launched with `docker run --rm --network=none --pids-limit=64 ...`; the sidecar PID-shares via `--pid=container:<candidate>`.
  - `../phase-arch-design.md §Gap 4` — the ENTRYPOINT-wrapper anti-pattern (PID 1 becomes strace; signal handling changes); sidecar pinned in `tools/digests.yaml#sandbox.strace_sidecar` (Alpine image).
  - `../phase-arch-design.md §Harness engineering ›Idempotence` — "`ShellInvocationTraceProbe` re-runs produce the same trace iff the candidate image digest is unchanged (asserted by `tests/integration/test_strace_idempotent.py`)."
  - `../phase-arch-design.md §Edge cases` — row 5 (budget exhaust path; idempotence must hold for the timeout case too).
  - `../phase-arch-design.md §Testing strategy ›Integration tests` — bullets `test_strace_sidecar_pid_share.py` and `test_strace_idempotent.py` are listed verbatim.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0013-shell-trace-runs-gate-time-in-phase5-chokepoint.md` — ADR-0013 — sibling sidecar, PID-share, 30 s budget, `--network=none` workload.
  - `../ADRs/0002-register-gate-probe-new-registry.md` — ADR-P7-001 — the probe is on the gate registry; integration tests dispatch via `all_gate_probes()`.
- **Existing code:**
  - `src/codegenie/probes/shell_invocation_trace.py` — the probe under test (S3-02).
  - `src/codegenie/tools/strace.py` — `run_in_sidecar(...)` real-subprocess wrapper (S2-04).
  - `src/codegenie/tools/buildkit.py` — `docker buildx build` for the fixture candidate image.
  - `tools/digests.yaml#sandbox.strace_sidecar` — pinned Alpine + strace image digest (S2-07).
  - `tests/fixtures/repos/express-distroless/` — landed later (S5-06); for this story use a minimal Dockerfile fixture inline.

## Goal

`tests/integration/test_strace_sidecar_pid_share.py` and `tests/integration/test_strace_idempotent.py` both pass on Linux DinD CI: the first asserts the candidate's PID 1 is the candidate's own entrypoint (`/proc/1/cmdline` inside the candidate does not start with `strace`); the second asserts re-tracing the same candidate digest produces a byte-identical `ShellInvocationTrace` (modulo non-deterministic fields explicitly normalized).

## Acceptance criteria

- [ ] `tests/integration/test_strace_sidecar_pid_share.py` builds a minimal candidate image (an Alpine `sleep 60` entrypoint suffices), launches it via the probe's `run()` path, and asserts that `docker exec <candidate> head -1 /proc/1/cmdline` returns the candidate's entrypoint binary path — **not** anything matching `strace` or `/usr/bin/strace`.
- [ ] The same test asserts the sidecar container *exists* during the run (via `docker ps --filter ancestor=<sandbox.strace_sidecar digest>`) and shares the PID namespace (its own `/proc/1/cmdline` is the *candidate*'s entrypoint when read from inside the sidecar — proving `--pid=container:<candidate>` is in effect).
- [ ] `tests/integration/test_strace_idempotent.py` invokes the probe twice against the same candidate digest with the same scenarios input and asserts `ShellInvocationTrace_run1.model_dump_json() == ShellInvocationTrace_run2.model_dump_json()` after normalizing two intentionally non-deterministic fields (`wall_clock_ms` to a fixed `0`, and any timestamp fields via field-exclusion). All other fields — `runtime_shell_count`, `traced_binaries`, `network_endpoints_touched`, `confidence`, `confidence_reasons`, `budget_ms`, `scenarios_run` — must match byte-for-byte.
- [ ] Both tests are marked `@pytest.mark.integration` and skip cleanly when `docker` is absent (`shutil.which("docker") is None`) so unit-only CI passes.
- [ ] The idempotence test runs with **three** re-traces (not two) and asserts pairwise byte-equality — catches the "second run accidentally cached, third run hits cold path" failure mode.
- [ ] Both tests clean up containers + images deterministically (use `try/finally` with `docker rm -f` and `docker rmi`).
- [ ] `mypy --strict` + `ruff check` clean on both test files.
- [ ] On budget-exhaust path (use a candidate that never reaches steady-state: `sh -c 'while true; do :; done'`) the idempotence test still passes — the timeout result is itself byte-stable (`confidence="medium"`, `runtime_shell_count=None`, identical `confidence_reasons`).

## Implementation outline

1. Author a minimal fixture Dockerfile in `tests/integration/_fixtures/strace_sidecar/Dockerfile` — Alpine base, `ENTRYPOINT ["/bin/sleep", "60"]`. Build it inside the test via `tools.buildkit.build` with `--load` and a content-addressed tag.
2. `test_strace_sidecar_pid_share.py`:
   - `pytest.skip` if `docker` absent or sidecar digest from `tools/digests.yaml#sandbox.strace_sidecar` cannot be pulled.
   - Build the candidate image.
   - Launch the candidate via `docker run -d --rm --network=none ... <candidate>`.
   - Invoke `ShellInvocationTraceProbe.run(view)` against it (the probe's run launches the sidecar).
   - Concurrently (during the 30 s window — use a `threading.Thread` or `asyncio.gather`), `docker exec <candidate_id> head -c 4096 /proc/1/cmdline` → assert *no* `strace` substring.
   - From inside the sidecar (`docker exec <sidecar_id> head -c 4096 /proc/1/cmdline`) → assert it matches the *candidate*'s entrypoint (PID-share proof).
   - Finally block cleans up.
3. `test_strace_idempotent.py`:
   - Build the candidate (same content → same digest).
   - Invoke `ShellInvocationTraceProbe.run(view)` three times against the same digest.
   - Normalize `wall_clock_ms` and exclude any naturally-noisy fields via `model_dump_json(exclude={"wall_clock_ms"})` — document which exclusions, and why, in the test file's docstring.
   - Assert pairwise equality: `dump1 == dump2 == dump3`.
   - Repeat with a budget-exhausting candidate (busy loop) and assert the `confidence="medium"` result is also byte-stable across re-runs.
4. Both tests log `GraphEvent`-style structured entries on entry/exit for `pytest -s` postmortem.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/integration/test_strace_sidecar_pid_share.py`

```python
# tests/integration/test_strace_sidecar_pid_share.py
import shutil
import subprocess
import threading

import pytest

pytestmark = pytest.mark.integration

from codegenie.probes.shell_invocation_trace import ShellInvocationTraceProbe
from codegenie.tools import buildkit, digests

@pytest.fixture
def candidate_image(tmp_path):
    if shutil.which("docker") is None:
        pytest.skip("docker not on PATH")
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text(
        'FROM alpine:3.20\nENTRYPOINT ["/bin/sleep","60"]\n'
    )
    tag = f"codegenie-strace-sidecar-test:{tmp_path.name}"
    digest = buildkit.build(context=tmp_path, tag=tag, platform="linux/amd64").image_digest
    yield digest, tag
    subprocess.run(["docker", "rmi", "-f", tag], check=False)

def test_candidate_pid1_is_not_strace(candidate_image):
    digest, tag = candidate_image
    # arrange: launch candidate in background
    cid = subprocess.check_output(
        ["docker", "run", "-d", "--rm", "--network=none", tag]
    ).decode().strip()
    try:
        # act: invoke the probe (which launches the sidecar against `cid`)
        observed = {}
        def _probe():
            view = _make_view(candidate_digest=digest, candidate_container_id=cid)
            observed["trace"] = ShellInvocationTraceProbe().run(view)
        t = threading.Thread(target=_probe, daemon=True)
        t.start()
        # while the sidecar is attached, read PID 1 in the candidate
        cmdline = subprocess.check_output(
            ["docker", "exec", cid, "head", "-c", "4096", "/proc/1/cmdline"]
        ).decode("utf-8", errors="replace")
        t.join(timeout=45)
        # assert: PID 1 is the candidate's entrypoint, NOT strace
        assert "strace" not in cmdline, (
            f"Candidate PID 1 must remain its own entrypoint (ADR-0013 / Gap 4); "
            f"observed cmdline: {cmdline!r}"
        )
        assert "/bin/sleep" in cmdline
    finally:
        subprocess.run(["docker", "rm", "-f", cid], check=False)
```

Idempotence file follows the same pattern:

```python
# tests/integration/test_strace_idempotent.py
def test_three_reruns_produce_byte_identical_trace(candidate_image): ...
def test_budget_exhaust_result_is_byte_stable(busy_loop_candidate_image): ...
```

Both fail initially because `ShellInvocationTraceProbe.run` either doesn't exist or doesn't drive a real sidecar yet. Commit red.

### Green — make it pass

Ensure `tools/strace.run_in_sidecar` accepts a `candidate_container_id` (passed through from the view) and constructs the `--pid=container:<id>` argument correctly. If S3-02's wrapper only accepts a digest, extend the wrapper additively in this story (the view carries both digest and container_id at gate time).

For idempotence: ensure `confidence_reasons` is sorted before serialization, `traced_binaries` and `network_endpoints_touched` are sorted, and `wall_clock_ms` is excluded from the equality comparison (documented in test docstring).

### Refactor — clean up

- Type hints + docstrings on test helpers.
- Lift `_make_view` into a shared fixture under `tests/integration/conftest.py` for use by S3-05 and S5-06.
- Mark both tests `@pytest.mark.integration` so the unit-only CI lane skips them.
- Verify cleanup: a failing test must not leak containers or images; `try/finally` everywhere.

## Files to touch

| Path | Why |
|---|---|
| `tests/integration/test_strace_sidecar_pid_share.py` | New — real-Docker test asserting PID 1 remains candidate's entrypoint. |
| `tests/integration/test_strace_idempotent.py` | New — three-rerun byte-identity test (success + budget-exhaust). |
| `tests/integration/_fixtures/strace_sidecar/Dockerfile` | New tiny fixture (Alpine sleep). |
| `tests/integration/conftest.py` | Extend with `candidate_image` + `_make_view` fixtures (additive). |
| `src/codegenie/probes/shell_invocation_trace.py` | Additive only if the view needs to carry `candidate_container_id` for the sidecar arg — extend the gate-time input contract without changing the probe's contract. |

## Out of scope

- **The probe itself** — S3-02; this story exercises it.
- **`tools/strace.py`** — S2-04; this story may extend the wrapper additively to accept the container-id, never to change behavior on existing callers.
- **`base_catalog.json` / target-image resolution** — S5-02.
- **End-to-end Node Express test** — S5-06 (`test_migrate_node_e2e.py`).
- **Perf canary on 30 s budget** — S7-04 (`test_strace_budget_distribution.py`).
- **macOS DinD edge cases (M-series Mac PID-namespace quirks)** — documented in `phase-arch-design.md §Risks specific to this step` for Step 3; this story is sufficient when green on Linux CI. macOS local quirks are a developer-experience follow-up.

## Notes for the implementer

- `docker exec <cid> head /proc/1/cmdline` returns NUL-separated argv. Decode with `errors="replace"` and treat the first NUL-separated token as the command. Don't over-parse — the assertion is *substring*, not equality.
- The PID-share test has a race: the candidate must be running when you exec, *and* the sidecar must be attached. A 1–2 s `time.sleep` after `docker run -d` is acceptable here (this is a test, not the prod hot path; the determinism rule does not forbid sleeps in test setup). If you can poll `docker inspect <cid>` for `.State.Running == true` instead, prefer that.
- Idempotence: `wall_clock_ms` will vary by tens of milliseconds. Exclude it from the dump comparison; document why in the test docstring (the field is *evidence*, but its value is environmentally noisy; only its *presence* + range is testable). Do **not** "normalize" by rounding — exclude.
- For the busy-loop / budget-exhaust idempotence variant: pin `gate.shell_trace.budget_s` to a small value (e.g., 3 s) via `monkeypatch.setenv` so the test wall-clock isn't 90 s. The byte-stability claim is independent of budget value.
- Both tests *must* skip cleanly when `docker` is absent — unit-only CI lanes (developer laptop without Docker, sandbox runners) need to pass. Use `pytest.skip(reason="docker absent")` early; do not `xfail`.
- `confidence_reasons` ordering: sort the list before populating the model (or set `frozenset` internally and emit sorted list). The byte-stability claim depends on it.
- Cleanup leaks are the most common flake source. Wrap every `docker run`/`docker build` in `try/finally` and call `docker rm -f` + `docker rmi -f` in the finally clause; do not rely on `--rm`.
