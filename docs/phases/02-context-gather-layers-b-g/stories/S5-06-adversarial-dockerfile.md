# Story S5-06 — `adversarial_dockerfile` container-hardening test

**Step:** Step 5 — Ship Layer C (runtime + container) probes
**Status:** Ready
**Effort:** S
**Depends on:** S5-02 (`RuntimeTraceProbe` ships with the `--network=none --cap-drop=ALL --security-opt=no-new-privileges` flags)
**ADRs honored:** 02-ADR-0001 (the hardening flags are the audit trail for the `docker` allowlist entry — final-design.md §"Tradeoffs accepted" row 3), 02-ADR-0007 (no Plugin Loader — the adversarial Dockerfile is a fixture, not a plugin)

## Context

S5-02's `RuntimeTraceProbe` runs the analyzed-repo's container under `--network=none --cap-drop=ALL --security-opt=no-new-privileges` and a per-scenario 120 s timeout. These flags are **non-negotiable** (High-level-impl.md §"Step 5" — "Risks specific to this step"). The structural proof is this story: a hand-crafted hostile Dockerfile (forkbomb / infinite-loop / wide-open file descriptor leak) does **not** escape the cap-drop, does **not** access the network, does **not** persist privileges, and **does** trigger the per-scenario 120 s timeout — and the coordinator continues with other probes after the timeout fires.

The adversarial Dockerfile lives under `tests/fixtures/adversarial/dockerfile-forkbomb/Dockerfile` (and similar siblings). The test under `tests/adv/phase02/test_adversarial_dockerfile.py` builds + runs it under the same hardening flags `RuntimeTraceProbe` constructs, asserts the timeout-failure path, asserts no host process escapes the cap-drop (no `kill -9 <host pid>` happens; no fork-bomb propagates beyond the container; the test process count is stable before and after), and asserts the coordinator continues — other probes (a tiny synthetic light probe) complete after the timeout.

This test is **CI-gating** in the `adv-phase02` job (S8-03).

## References

- [phase-arch-design.md §"Component design" #6 (`RuntimeTraceProbe`)](../phase-arch-design.md) — hardening flags `--network=none --cap-drop=ALL --security-opt=no-new-privileges`.
- [phase-arch-design.md §"Edge cases" row 5 (`docker build` fails on adversarial Dockerfile)](../phase-arch-design.md) — adjacent failure path.
- [phase-arch-design.md §"Testing strategy" — adversarial table](../phase-arch-design.md) — `test_adversarial_dockerfile.py` named alongside the load-bearing corpus.
- [02-ADR-0001 §Tradeoffs](../ADRs/0001-add-docker-and-security-cli-tools-to-allowed-binaries.md) — "Mitigated by `tests/adv/phase02/test_adversarial_dockerfile.py` exercising the cap-drop path".
- [High-level-impl.md §"Step 5"](../High-level-impl.md) — "container-hardening flags (`--network=none --cap-drop=ALL --security-opt=no-new-privileges`) are non-negotiable; the `test_adversarial_dockerfile.py` is the proof".
- [final-design.md §"Adversarial corpus"](../final-design.md) — adversarial corpus ≥ 6 cases.

## Goal

Land `tests/adv/phase02/test_adversarial_dockerfile.py` and the supporting fixture Dockerfile(s) under `tests/fixtures/adversarial/`. The test proves (a) the hardening triple contains a forkbomb / infinite-loop / network-touching adversarial Dockerfile; (b) the per-scenario 120 s timeout fires; (c) no host-level process count growth occurs; (d) the coordinator continues with subsequent probes after the timeout fires.

## Acceptance criteria

- [ ] `tests/fixtures/adversarial/dockerfile-forkbomb/Dockerfile` exists — a minimal `FROM alpine:3.20` image with a CMD that runs a forkbomb (`:(){ :|:& };:` or equivalent shell-form forkbomb). Document the literal source in a `README.md` co-located with the fixture so a future maintainer doesn't accidentally "fix" the obvious-looking syntax.
- [ ] `tests/fixtures/adversarial/dockerfile-infinite-loop/Dockerfile` exists — a `FROM alpine:3.20` image with CMD `["sh", "-c", "while true; do echo .; done"]` — proves the timeout fires even on a non-fork-bomb pathology.
- [ ] `tests/fixtures/adversarial/dockerfile-network-touch/Dockerfile` exists — a `FROM alpine:3.20` image with CMD that attempts `wget http://example.com` or `nc -z example.com 80`; under `--network=none`, the network call fails fast; the scenario should fail with exit-non-zero **before** the 120 s timeout (proves `--network=none` works, distinct from the timeout proof).
- [ ] `tests/adv/phase02/test_adversarial_dockerfile.py` exists with three test functions (one per fixture):
  - **`test_forkbomb_times_out_and_coordinator_continues`** — invokes `RuntimeTraceProbe.run` against the forkbomb fixture with a stubbed `image_digest_resolver`. Assert: each scenario emits `TraceScenarioFailed(reason=ScenarioTimeout(seconds=120))`; the probe envelope completes; **the host process count before and after the test is stable to within ±5** (read via `psutil.Process(os.getpid()).children(recursive=True)` count, or `/proc/<pid>/task` count on Linux). The ±5 slack accommodates the test runner's own incidental subprocesses; the forkbomb in a contained `--cap-drop=ALL` cgroup should not propagate.
  - **`test_infinite_loop_times_out`** — invokes against the infinite-loop fixture; assert per-scenario `TraceScenarioFailed(reason=ScenarioTimeout(seconds=120))`; assert the test wall-clock between probe-start and probe-finish is between 120 s and 150 s (the per-scenario timeout fires; aggregate doesn't).
  - **`test_network_touch_blocked_by_network_none`** — invokes against the network-touch fixture; assert the scenario emits `TraceScenarioFailed` with `exit_code != 0` and `stderr_tail` contains a network-unreachable marker (e.g., `bad address` or `Network is unreachable`); critically, the failure occurs **before** the 120 s timeout (asserts `wall_clock_ms < 30_000` for the failed scenario — `--network=none` causes immediate DNS failure).
- [ ] **Coordinator continuation proof.** In `test_forkbomb_times_out_and_coordinator_continues`, run the probe within a `Coordinator` instance configured with a second synthetic probe (a light no-op probe registered just for the test); assert the synthetic probe's slice IS in the gather's emitted envelope (i.e., its `run()` was reached) even though `RuntimeTraceProbe` timed out on every scenario. This proves Phase 0 isolation holds.
- [ ] **No host process escape.** Before and after `test_forkbomb_…`, snapshot host process count via `psutil` (`len(psutil.process_iter())`); the delta is ≤ 5 (test-runner slack). On `psutil` unavailable (no `psutil` in `[gather]` extras), the test fall-back is `len(os.listdir("/proc"))` on Linux or `subprocess.check_output(["ps","-A"]).count(b"\n")` (which itself is process-counting). Pick `psutil` and add it to `[dev]` extras (not `[gather]`).
- [ ] **`--cap-drop=ALL` proof.** The forkbomb fixture's CMD attempts `chown 0:0 /etc/passwd` before the forkbomb; under `--cap-drop=ALL` this fails (CAP_CHOWN dropped); the scenario's `stderr_tail` contains the `chown: operation not permitted` marker. Assert this marker in the test (independent of the forkbomb timing).
- [ ] **`--security-opt=no-new-privileges` proof.** The forkbomb fixture includes a setuid binary attempt (e.g., a copy of `/bin/su` chmod 4755 in the image build); the runtime attempt to invoke the setuid binary fails because no-new-privileges blocks the setuid bit. Assert the marker in the test.
- [ ] **Test runs in `adv-phase02` CI job (S8-03)** — the PR description for this story notes the test path must be picked up by the job's glob; S8-03 is responsible for the YAML wiring.
- [ ] **Test runs only on Linux CI** (per S5-02's macOS path: on darwin, the probe deterministically emits `StraceUnavailable` and never runs `docker run`; the adversarial test asserts containment, which is meaningful only when the container actually runs). Skip-with-loud-reason on non-Linux via `pytest.mark.skipif(sys.platform != "linux", reason="Layer C container-hardening adversarial requires Linux")`.
- [ ] **Test wall-clock budget.** Each adversarial test function may consume up to ~180 s wall-clock (forkbomb / infinite-loop timeouts dominate); the three together fit ≤ 10 min in the `adv-phase02` job. If wall-clock pressure proves an issue, mark them as `@pytest.mark.slow` and split into a separate CI lane — but the default behavior is "they run on every PR's `adv-phase02` job".
- [ ] **Real `docker build` runs in this test** — unlike S5-05's adversarial (which mocks), this one needs the real container runtime to prove the hardening flags actually work. The test is gated on `docker` being on `$PATH` and the Docker daemon being reachable; if not (e.g., local dev without Docker), `pytest.skip("docker daemon unreachable")` with a loud reason.
- [ ] `mypy --strict` clean on the test file (the test is plain pytest; type-checking is mostly trivial).
- [ ] The fixture Dockerfiles are **clearly labeled** in their co-located `README.md` as "DELIBERATELY ADVERSARIAL — do not run outside the test harness; do not copy into production"; the labels prevent accidental use.

## Implementation outline

1. Create `tests/fixtures/adversarial/dockerfile-forkbomb/{Dockerfile,README.md,setup.sh}` — `Dockerfile` is the minimal forkbomb+chown+setuid image; `setup.sh` is a small helper to build the image when running outside the test harness (clearly labeled "do not run").
2. Create `tests/fixtures/adversarial/dockerfile-infinite-loop/Dockerfile` and `tests/fixtures/adversarial/dockerfile-network-touch/Dockerfile`.
3. Create `tests/adv/phase02/test_adversarial_dockerfile.py` with the three test functions; pytest fixtures for the snapshot-process-count helpers; `psutil` import (add to `[dev]` extras in `pyproject.toml`).
4. Each test function:
   - Skip on non-Linux.
   - Skip if `docker` not on `$PATH` or daemon unreachable.
   - Snapshot host process count.
   - Build the fixture image via `run_allowlisted("docker", ["build", "-t", "codegenie-test-<name>", <fixture-path>])`.
   - Invoke `RuntimeTraceProbe.run` against a `RepoSnapshot` rooted at the fixture directory; bind `image_digest_resolver` to return the just-built digest.
   - Capture the probe's `ProbeOutput`.
   - Assert outcome shape per the test's specific claim.
   - Snapshot host process count again; assert delta ≤ 5.
5. The "coordinator continuation" test uses a small `_NoOpLightProbe` defined inline in the test file (a class decorated with `@register_probe(heaviness="light")` that returns a trivial slice); the test runs the coordinator with both probes and asserts both slices land in the envelope.

## TDD plan — red / green / refactor

**Red:**

1. Land all three fixture Dockerfiles with explicit "DELIBERATELY ADVERSARIAL" READMEs (the fixtures themselves are the test inputs; their absence is the initial red state).
2. Write `test_forkbomb_times_out_and_coordinator_continues` — assertion fails because the test file doesn't exist yet; once written, it fails because `RuntimeTraceProbe.run` (without S5-02 timeout enforcement) might not actually time out, OR because S5-02 *does* enforce the timeout and the assertions pass on initial run if S5-02 is correctly implemented. **Initial run on a correct S5-02 should be green** — this story's purpose is to *prove* S5-02's hardening claims with a structural test that future regressions trip on. The red phase is "the test does not exist"; the green phase is "the test exists and passes against S5-02".
3. Write `test_infinite_loop_times_out` and `test_network_touch_blocked_by_network_none` — same logic.
4. Write `test_coordinator_continues_after_runtime_trace_timeout` — uses `_NoOpLightProbe`; asserts both slices in envelope.
5. **Mutation test — verify the test would catch a regression.** Temporarily edit S5-02's `RuntimeTraceProbe` to omit `--network=none` from the argv; rerun `test_network_touch_blocked_by_network_none`; assert it now **fails** (the network-touch fixture succeeds where it should fail). Restore S5-02; assert it passes. Document the mutation-test ritual in the test module's docstring so future maintainers know the test's failure mode is structural, not noise.

**Green:**

1. Land the three fixture Dockerfiles.
2. Land the test file with the four test functions.
3. Confirm all four pass on a Linux host with Docker reachable.

**Refactor:**

1. Extract `_snapshot_process_count()` and `_build_fixture_image(name)` into helpers in `tests/adv/phase02/_helpers.py` — pure helpers, not pytest fixtures, so they're greppable.
2. Confirm the test file is ≤ 200 LOC; the four test functions should be small.
3. Confirm each fixture's `README.md` clearly labels the fixture as adversarial.

## Files to touch

- **New fixtures:** `tests/fixtures/adversarial/dockerfile-forkbomb/{Dockerfile,README.md}`, `tests/fixtures/adversarial/dockerfile-infinite-loop/{Dockerfile,README.md}`, `tests/fixtures/adversarial/dockerfile-network-touch/{Dockerfile,README.md}`.
- **New tests:** `tests/adv/phase02/test_adversarial_dockerfile.py`, `tests/adv/phase02/_helpers.py` (process-count + image-build helpers).
- **Possibly extend:** `pyproject.toml` `[project.optional-dependencies] dev = […]` — add `psutil` if not already present.
- **PR description note:** the new adversarial test path (`tests/adv/phase02/test_adversarial_dockerfile.py`) must be picked up by S8-03's `adv-phase02` CI job spec.

## Out of scope

- The `image_digest_drift` adversarial — **S5-05**.
- The `stale-scip` adversarial — **S4-02 (stub) + S7-02 (full)**.
- Secret-in-source adversarial — **S6-07**.
- Hostile-skills-YAML adversarial — **S7-04**.
- Concurrent-gather race — **S7-04**.
- macOS-equivalent container hardening — explicitly out of scope (macOS path emits `StraceUnavailable` per S5-02; this adversarial is Linux-only).
- Cross-validating with `podman` instead of `docker` — `docker` is in `ALLOWED_BINARIES` (02-ADR-0001); `podman` is not; cross-runtime validation is a Phase-3+ follow-up.
- microVM-equivalent test (Phase 5+ ADR-0012) — when `docker` is swapped for a microVM, the adversarial test is re-targeted against the new runtime; that's a Phase-5+ amendment to this story.

## Notes for the implementer

- **The forkbomb fixture is the load-bearing piece** — it's the structural proof that `--cap-drop=ALL` + the per-scenario timeout contains the worst-case malicious Dockerfile. If the forkbomb test ever flakes (e.g., the ±5 process-count slack is too tight on a busy CI runner), the resolution is **not** to weaken the assertion — investigate whether the cgroup container actually contained the forkbomb. A flaky containment test is a load-bearing-bug; fix the containment, not the test.
- **The mutation test discipline** (delete `--network=none`, observe the network-touch test fail) is documented but **not committed in the deleted state** — it's a developer-runnable check. Document the ritual in the module docstring so future maintainers can manually verify the test's discriminating power. This is the same discipline S3-01's mutation test on the `AKIA` pattern uses.
- **`docker` daemon reachability.** Local dev frequently lacks Docker; the CI job has it. The `pytest.skip("docker daemon unreachable")` path is acceptable on local — but the CI job must NOT skip; surface that in S8-03's job spec (the CI job should fail loudly if Docker isn't available, not silently skip).
- **`psutil` is a `[dev]` dep, not `[gather]`.** It's a test-only utility; Phase 0 `fence` should be unaffected (`psutil` is not in the LLM-import blocklist). Document the choice — adding to `[gather]` would bloat the runtime install for no production benefit.
- **The "coordinator continuation" claim** is what Phase 0 isolation buys us. Without that, a forkbomb-Dockerfile-victim probe would block all other probes; with it, the coordinator continues. The `_NoOpLightProbe` is the minimal proof; if Phase 0's isolation mechanism is not actually wired through the coordinator under cancellation, this test surfaces it and the resolution is a Phase 0 issue (not this story's).
- **Why three fixtures instead of one?** Each fixture exercises a distinct hardening dimension:
  - forkbomb → `--cap-drop=ALL` + per-scenario timeout (resource containment).
  - infinite-loop → per-scenario timeout (CPU containment, no fork).
  - network-touch → `--network=none` (network containment).
  - `chown 0:0 /etc/passwd` → `--cap-drop=ALL` blocks CAP_CHOWN (privilege containment).
  - setuid invocation → `--security-opt=no-new-privileges` (privilege-escalation containment).
  Four-of-five claims are independent; folding them into one fixture would couple the assertions and weaken the diagnostic when one regresses.
- **No real network calls leak in the network-touch fixture** — `--network=none` is enforced before the container's CMD runs; the `wget` immediately gets `bad address` from the kernel. The test must NOT depend on `example.com` being reachable.
- **Wall-clock pressure.** Three 120 s timeouts back-to-back is ~6 min; plus build time, ~7-8 min. If `adv-phase02`'s total budget (S8-03 says ≤ 6 min for `portfolio`; `adv-phase02` is its own job with looser budget) is tight, mark with `@pytest.mark.slow` and gate behind a label on the PR — but the default should be "runs on every PR" because the container-hardening flags are non-negotiable per High-level-impl.md §"Step 5".
- **The test does NOT depend on S5-05.** S5-05's freshness check and S5-06's containment test are independent — both depend on S5-02, neither on the other.
- **The `chown` + setuid claims** stress two of the three hardening flags (`--cap-drop=ALL`, `--security-opt=no-new-privileges`). The third (`--network=none`) gets its own fixture. If a fourth flag is later added (e.g., `--read-only` for root filesystem), this story's adversarial corpus extends by a fourth fixture — additive, no edits to existing fixtures.
- **Open question — runner-level cap escalation.** Some CI runners (privileged Docker-in-Docker) might *accidentally* allow `chown` because the outer runner has CAP_CHOWN. The test asserts the *inner* container fails, not the outer; the assertion target is the container's stderr (`operation not permitted`), not the host's permissions. Document in the test module docstring; surface as an ADR-amend candidate if a future CI environment regresses this.
