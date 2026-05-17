# Story S5-06 — `adversarial_dockerfile` container-hardening test

**Step:** Step 5 — Ship Layer C (runtime + container) probes
**Status:** Ready (HARDENED)
**Effort:** S
**Depends on:** S5-02 (`RuntimeTraceProbe` ships with the `--network=none --cap-drop=ALL --security-opt=no-new-privileges` flags + `ProbeContext.image_digest_resolver` + per-scenario `scenarios.yaml` override mechanism)
**ADRs honored:** 02-ADR-0001 (the hardening flags are the audit trail for the `docker` allowlist entry — final-design.md §"Tradeoffs accepted" row 3), 02-ADR-0007 (no Plugin Loader — the adversarial Dockerfile is a fixture, not a plugin)

## Validation notes

Story hardened by phase-story-validator (`_validation/S5-06-adversarial-dockerfile.md`). This is the **4th adversarial test landed under `tests/adv/phase02/`** and the **2nd structural-proof adversarial for Layer C** (after S5-05's image-digest-drift). Verdict: **HARDENED**. Eighteen in-place edits applied (full details in `_validation/`); highlights:

1. **Network-touch test rewritten to assert `TraceScenarioCompleted`, NOT `TraceScenarioFailed`** (C1). S5-01's `TraceFailureReason` variant set is exactly `StraceUnavailable | DockerBuildFailed | ScenarioTimeout | ImageDigestUnresolved` — NO `exit_code` or `stderr_tail` carrier. The original AC asserted a variant shape that cannot exist. The proof of `--network=none` is now *the absence of network endpoints in the parsed trace*: `parsed_trace.network_endpoints_touched == frozenset()` on a `TraceScenarioCompleted` result, with `wall_clock_ms < 30_000` as the fast-fail bound.
2. **chown + setuid claims split out of the forkbomb fixture into dedicated fixtures** (K2). Two new fixtures (`dockerfile-cap-chown`, `dockerfile-setuid`); the forkbomb fixture's CMD is the pure forkbomb. Aligns the ACs with the story's own diagnostic-independence rationale in Notes-for-implementer.
3. **Fixture-level `.codegenie/scenarios.yaml` required per fixture** (C3). Without it, S5-02 falls back to `_DEFAULT_SCENARIOS` — five canonical scenarios with their canonical commands (which are NOT the adversarial invocation). Each fixture now declares a single scenario whose `command` IS the adversarial invocation, loaded by S5-02's `safe_yaml.load` chokepoint when `snapshot.root == fixture_dir`.
4. **`ProbeContext` construction + resolver binding pinned** (C2 + D5). Helpers `_helpers.py::_make_probe_context(image_digest)` and `_helpers.py::make_resolver(digest) -> Callable[[Path], str | None]` are the single source of construction; tests import them. Catches a future `ProbeContext` signature drift; eliminates `lambda root: digest` duplication across 5 tests.
5. **`_FIXTURE_TO_HARDENING_DIMENSION` mutation-resistance manifest** (T1 + T2). A `Final[Mapping[str, str]]` in `_helpers.py` maps each fixture name to the hardening flag/dimension it stresses. A committed parametrized test asserts every element of `RuntimeTraceProbe._HARDENING_FLAGS` is named by ≥ 1 fixture's dimension; a sibling test discovers `tests/fixtures/adversarial/dockerfile-*/` via glob and asserts each discovered fixture has both a manifest entry AND a `test_*` function. Replaces the developer-runnable mutation ritual (per S5-04 T2 / S5-05 T2 precedent: structural mutation-resistance is mandatory, not optional).
6. **Coordinator-continuation overlap proof** (T5 + T6). The original "noop probe slice in envelope" claim is weak: a coordinator that serializes (runs noop AFTER runtime_trace's full timeout) would pass it trivially. New AC: `noop.finish_wall_clock < runtime_trace.finish_wall_clock` (concurrency proof). New AC: the coordinator pinned envelope shape for the timed-out probe matches the per-fixture test's expected envelope.
7. **Build-success precondition + all-scenarios-timed-out count** (K3 + K4 + K6). Each test asserts the build helper returned a non-empty digest BEFORE invoking the probe (loud failure path distinct from containment); asserts `len([r for r in results if isinstance(r.reason, ScenarioTimeout)]) == n_configured_scenarios` (pin the count); asserts NOT the aggregate-timeout shape (mix of `Failed(ScenarioTimeout)` + `Skipped(ImageBuildUnavailable)`).
8. **Process-count signal scoped to runner's subprocess tree** (K7). `psutil.Process(os.getpid()).children(recursive=True)` is the canonical signal; slack tightened to ±2. A sanity test (`test_process_count_helper_smoke`) verifies the helper actually detects subprocesses (T4).
9. **Stdout backpressure assertion for infinite-loop** (T7). Layer C uses `run_allowlisted` directly (no `run_external_cli` cap). New AC asserts captured stdout < 16 MB; if S5-02 has no cap, the AC surfaces it as an S5-02 amendment candidate, not a workaround.
10. **`_NoOpLightProbe` registered via pytest fixture with teardown** (C5). Avoids registry pollution across test imports. If the registry lacks `unregister`, escalate to S1-08 (don't workaround with `del`).
11. **Rule-of-three extraction seam documented** (D1 + D2). The 5 per-fixture test functions are still readable (rule-of-three deferral mirrors S5-04 D2 / S5-05 D3). The kernel-extraction shape (`_FIXTURE_SPEC` dataclass + parametrized runner) is documented in Notes-for-implementer for the next maintainer who lands a 6th fixture (likely `--read-only` or microVM-equivalent).
12. **S8-03 CI wiring moved from AC to Notes** (K8 + C8). Not testable in this story; surfaced as an explicit S8-03 dependency.

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

Land `tests/adv/phase02/test_adversarial_dockerfile.py` (+ `_helpers.py`) and **five fixture Dockerfiles** under `tests/fixtures/adversarial/dockerfile-{forkbomb,infinite-loop,network-touch,cap-chown,setuid}/`. Each fixture exercises **one** distinct hardening dimension (diagnostic independence — when one regresses, exactly one fixture's test fails). The test proves:

- (a) `--cap-drop=ALL` + per-scenario 120 s timeout contain a forkbomb (`dockerfile-forkbomb`).
- (b) per-scenario 120 s timeout fires on a CPU pathology without fork (`dockerfile-infinite-loop`).
- (c) `--network=none` blocks runtime network access (`dockerfile-network-touch`) — proven structurally via `parsed_trace.network_endpoints_touched == frozenset()` on a `TraceScenarioCompleted` result, NOT via stderr-string-matching on a (non-existent) `TraceScenarioFailed.exit_code` carrier.
- (d) `--cap-drop=ALL` drops `CAP_CHOWN` (`dockerfile-cap-chown`) — proven via the scenario's captured stderr_tail in `parsed_trace`.
- (e) `--security-opt=no-new-privileges` blocks setuid escalation (`dockerfile-setuid`) — proven via the scenario's captured stderr_tail in `parsed_trace`.
- (f) no host-level process count growth occurs (asserted on the forkbomb test via `psutil.Process(os.getpid()).children(recursive=True)`, delta ≤ ±2).
- (g) the coordinator continues with subsequent probes after a probe times out (asserted on a 6th test wiring a `_NoOpLightProbe` alongside `RuntimeTraceProbe` and verifying `noop.finish_wall_clock < runtime_trace.finish_wall_clock` — concurrency proof, not serialization).

**Test function count: 6** (one per fixture + one coordinator-continuation integration test), plus 4 helper / manifest / sanity tests (`test_fixture_to_hardening_dimension_manifest_pins_all_flags`, `test_fixture_discovery_pins_all_test_functions`, `test_process_count_helper_smoke`, `test_build_fixture_image_helper_returns_digest`).

## Acceptance criteria

### Fixtures (5)

Each fixture is a directory under `tests/fixtures/adversarial/dockerfile-<name>/` containing exactly three files: `Dockerfile`, `README.md` (labeled "DELIBERATELY ADVERSARIAL — do not run outside the test harness; do not copy into production"), and `.codegenie/scenarios.yaml`. The `scenarios.yaml` declares **one** scenario whose `command` IS the adversarial invocation (so S5-02's `safe_yaml.load` reads it when `snapshot.root == fixture_dir` and the probe runs exactly one scenario per fixture — diagnostic clarity, predictable per-fixture wall-clock).

- [ ] **`dockerfile-forkbomb/`** — `FROM alpine:3.20`; CMD is the **pure** forkbomb (`["sh", "-c", ":(){ :|:& };:"]` — no chown, no setuid, no other actions). `.codegenie/scenarios.yaml`: `scenarios: [{name: "forkbomb", command: ["sh", "-c", ":(){ :|:& };:"]}]`. README labels it adversarial AND notes the literal forkbomb source so a future maintainer doesn't "fix" the obvious-looking syntax. **Hardening dimension exercised:** `--cap-drop=ALL` + per-scenario timeout.
- [ ] **`dockerfile-infinite-loop/`** — `FROM alpine:3.20`; CMD `["sh", "-c", "while true; do echo .; done"]`. `.codegenie/scenarios.yaml` declares one scenario with the same command. **Hardening dimension exercised:** per-scenario timeout (no fork; pure CPU pathology).
- [ ] **`dockerfile-network-touch/`** — `FROM alpine:3.20`; CMD `["sh", "-c", "wget -q http://example.com -O /dev/null"]` (deterministic argv; no shell glob; no PATH dependence on multiple wget variants). `.codegenie/scenarios.yaml` declares one scenario with the same command. **Hardening dimension exercised:** `--network=none`. The test does NOT depend on `example.com` being reachable — `--network=none` blocks the syscall at the kernel level before DNS resolution.
- [ ] **`dockerfile-cap-chown/`** — `FROM alpine:3.20`; CMD `["sh", "-c", "chown 0:0 /etc/passwd; exit 0"]`. `.codegenie/scenarios.yaml` declares one scenario with the same command. **Hardening dimension exercised:** `--cap-drop=ALL` drops `CAP_CHOWN`; chown fails with `operation not permitted` and the scenario exits with the trace capturing the failed chown syscall.
- [ ] **`dockerfile-setuid/`** — `FROM alpine:3.20`; the Dockerfile's `RUN` clauses bake a setuid binary into the image (`COPY su-copy /usr/local/bin/su-copy && chmod 4755 /usr/local/bin/su-copy`, where `su-copy` is a tiny C program or an `id`-equivalent shell script the fixture committed under `/usr/local/bin/su-copy`); CMD `["sh", "-c", "/usr/local/bin/su-copy; exit 0"]`. `.codegenie/scenarios.yaml` declares one scenario with the same command. **Hardening dimension exercised:** `--security-opt=no-new-privileges` blocks the setuid bit on exec.

### Helpers + manifest

- [ ] **`tests/adv/phase02/_helpers.py`** exposes:
  - `_FIXTURE_TO_HARDENING_DIMENSION: Final[Mapping[str, str]]` — the manifest. Keys are fixture directory names; values are the canonical hardening-flag/dimension strings. **Exactly** `{"dockerfile-forkbomb": "cap-drop+timeout", "dockerfile-infinite-loop": "timeout", "dockerfile-network-touch": "network-none", "dockerfile-cap-chown": "cap-drop", "dockerfile-setuid": "no-new-privileges"}`.
  - `build_fixture_image(name: str) -> str` — builds the fixture image and returns the docker image digest. Uses `run_allowlisted("docker", ["build", "-t", _image_tag(name), str(_fixture_path(name))])` for the build AND `run_allowlisted("docker", ["image", "inspect", _image_tag(name), "--format={{.Id}}"])` for the digest. Raises `pytest.fail(f"docker build failed for fixture {name}: <stderr_tail>")` with the build's stderr_tail on non-zero exit.
  - `make_resolver(digest: str) -> Callable[[Path], str | None]` — `return lambda _root: digest`. Centralizes the type-signature pin against `ProbeContext.image_digest_resolver`.
  - `_make_probe_context(image_digest: str) -> ProbeContext` — constructs a `ProbeContext(image_digest_resolver=make_resolver(image_digest), ...)` with all required fields explicit. Future `ProbeContext` signature drift surfaces immediately.
  - `_snapshot_process_count() -> int` — returns `len(psutil.Process(os.getpid()).children(recursive=True))`. NOT `psutil.process_iter()` (whole-system scope is too noisy on busy CI).
  - `noop_light_probe_fixture(probe_registry) -> Iterator[type[Probe]]` — pytest fixture that registers a class `_NoOpLightProbe(Probe)` decorated with `@register_probe(heaviness="light", name="noop_light")` whose `run()` returns a trivial slice in < 1 s, then unregisters at teardown. If the registry lacks `unregister`, escalate to S1-08 — do NOT workaround with `del registry._probes[...]`.

- [ ] **`test_fixture_to_hardening_dimension_manifest_pins_all_flags`** (`_helpers.py` import test) — parametrizes over `_FIXTURE_TO_HARDENING_DIMENSION.values()`; asserts each value is a non-empty string. Then imports `RuntimeTraceProbe._HARDENING_FLAGS` from S5-02 and asserts every flag substring (`network=none`, `cap-drop=ALL`, `no-new-privileges`) is named by ≥ 1 manifest value. **Mutation test:** deleting any flag from S5-02's `_HARDENING_FLAGS` flips this red because the manifest still names it; deleting a manifest entry flips it red because a flag is now unmapped.
- [ ] **`test_fixture_discovery_pins_all_test_functions`** — discovers `tests/fixtures/adversarial/dockerfile-*/` via `Path("tests/fixtures/adversarial").glob("dockerfile-*")`; for each discovered fixture, asserts (a) its name is a key in `_FIXTURE_TO_HARDENING_DIMENSION`; (b) the test module has a function named `test_<fixture_name_without_dockerfile_prefix>_*` (via `inspect.getmembers(module, inspect.isfunction)`). Catches "added a fixture but forgot the test" + "added a test but forgot the manifest entry".
- [ ] **`test_build_fixture_image_helper_returns_digest`** (Linux only, docker reachable) — calls `build_fixture_image("dockerfile-forkbomb")`; asserts the return is a non-empty string starting with `"sha256:"`; asserts a second call returns the same string (idempotency).
- [ ] **`test_process_count_helper_smoke`** — baseline = `_snapshot_process_count()`. Spawns `subprocess.Popen(["sleep", "1"])`; asserts `_snapshot_process_count() >= baseline + 1` while the subprocess is alive. After the subprocess exits, asserts `_snapshot_process_count() <= baseline + 1` (psutil's caching may keep a zombie briefly; ±1 tolerance). Confirms the helper actually detects subprocesses.

### Per-fixture tests (one per fixture)

All 5 per-fixture tests share preconditions (skip on non-Linux; skip on docker-unreachable; gate on `helpers.build_fixture_image(name)` returning a non-empty digest). All construct a `ProbeContext` via `_make_probe_context(digest)` and a `RepoSnapshot` rooted at the fixture directory, then `await RuntimeTraceProbe().run(snapshot, ctx)`.

- [ ] **`test_forkbomb_timeout`** — fixture `dockerfile-forkbomb`. Asserts:
  - All configured scenarios (1, per the fixture's `scenarios.yaml`) emit `TraceScenarioFailed(reason=ScenarioTimeout(seconds=120))`. Pin the count: `len([r for r in results if isinstance(r, TraceScenarioFailed) and isinstance(r.reason, ScenarioTimeout)]) == 1` (the single declared scenario, not the default-5).
  - Envelope `confidence == "low"` (per S5-02 derivation: 0/N completed → `"unavailable"` slice → `"low"` envelope per the `_envelope_confidence` lift).
  - Slice `trace_coverage_confidence == "unavailable"`.
  - **Not** the aggregate-timeout shape (the aggregate would produce a mix of `Failed(ScenarioTimeout)` + `Skipped(ImageBuildUnavailable)` — see S5-02 outline (e); the per-scenario shape is all `Failed(ScenarioTimeout)`). Pin this explicitly.
  - **Host process count delta:** baseline = `_snapshot_process_count()` before the test; final = after. Assert `abs(final - baseline) <= 2`. The 2-slack accommodates psutil's brief zombie-process retention; the forkbomb in a contained `--cap-drop=ALL` cgroup MUST NOT propagate beyond the container.
- [ ] **`test_infinite_loop_timeout`** — fixture `dockerfile-infinite-loop`. Asserts:
  - The configured scenario emits `TraceScenarioFailed(reason=ScenarioTimeout(seconds=120))`.
  - Test wall-clock `>= 120` AND `< 600` (the per-scenario timeout fired; aggregate did not). The earlier `<= 150` upper bound is replaced — wall-clock is a sanity check, not a precision measurement; CI slowness can legitimately push wall-clock past 150 s without indicating a failure.
  - **Stdout backpressure:** the captured stdout for the scenario is `< 16 * 1024 * 1024` bytes (16 MB sane cap). If S5-02 has no stdout cap on the `run_allowlisted("docker", …)` call (Layer C does NOT use `run_external_cli`'s 64 MB cap), this AC surfaces a real Phase 2 gap — the implementer escalates to an S5-02 amendment rather than working around it in the test.
- [ ] **`test_network_touch_blocked`** — fixture `dockerfile-network-touch`. Asserts:
  - The configured scenario emits `TraceScenarioCompleted` (NOT `TraceScenarioFailed` — `TraceFailureReason` has no `exit_code`/`stderr_tail` carrier; S5-02 produces `TraceScenarioCompleted` whenever the docker-run terminates and a trace was captured, regardless of CMD exit code).
  - `parsed_trace.network_endpoints_touched == frozenset()` — the proof of `--network=none`. Empty set means no `connect()` or `bind()` syscalls landed an endpoint.
  - `binaries_executed` contains `"wget"` (or `"/usr/bin/wget"`, etc.) — the binary RAN but the network call was blocked. Catches a regression where the fixture's CMD silently doesn't execute wget.
  - `wall_clock_ms < 30_000` — fast fail (the wget gets `bad address` from the kernel immediately; no 120 s timeout).
- [ ] **`test_cap_chown_blocked`** — fixture `dockerfile-cap-chown`. Asserts:
  - The configured scenario emits `TraceScenarioCompleted` (the chown command exited; trace captured).
  - `parsed_trace.files_read_at_runtime` or `parsed_trace.binaries_executed` contains `"chown"` (the binary RAN).
  - The probe's per-scenario captured stderr_tail (surfaced via the slice's `per_scenario_artifacts[name]` path on disk OR a slice field if S5-02 exposes one — see Notes-for-implementer) contains `"operation not permitted"` OR an equivalent `chown` failure marker (`"chown: /etc/passwd: Operation not permitted"`). The marker assertion is the proof of `CAP_CHOWN` being dropped.
- [ ] **`test_setuid_blocked`** — fixture `dockerfile-setuid`. Asserts:
  - The configured scenario emits `TraceScenarioCompleted`.
  - `parsed_trace.binaries_executed` contains `"/usr/local/bin/su-copy"` (the binary was invoked).
  - The captured stderr_tail contains a no-new-privileges failure marker (`"setuid"` reference OR `"permission denied"` from the runtime — the exact marker depends on Alpine's exec implementation; pin a regex `re.compile(r"(setuid|operation not permitted|permission denied)", re.I)` to catch the marker family without overspecifying).

### Coordinator-continuation test (1)

- [ ] **`test_coordinator_continues_after_runtime_trace_timeout`** — registers `_NoOpLightProbe` via the `noop_light_probe_fixture` (pytest fixture with teardown). Runs the coordinator with both `RuntimeTraceProbe` AND `_NoOpLightProbe` against the `dockerfile-forkbomb` fixture. Asserts:
  - The noop probe's slice IS in the gather's emitted envelope (its `run()` was reached).
  - **Concurrency proof (overlap):** the noop probe's `finish_wall_clock_ms < RuntimeTraceProbe`'s `finish_wall_clock_ms`. If the coordinator inadvertently serializes (runs noop AFTER runtime_trace's full timeout), this assertion flips red. A well-behaved coordinator dispatches both probes; the light noop completes in < 1 s while the heavy probe is still timing out.
  - **Envelope shape pinned:** the timed-out `runtime_trace` envelope matches the per-fixture test's expected shape (`confidence="low"`, 1 scenario = `TraceScenarioFailed(ScenarioTimeout(120))`). Catches a coordinator refactor that mutates probe envelopes under cancellation.

### Cross-cutting

- [ ] **Test runs only on Linux CI** — `pytest.mark.skipif(sys.platform != "linux", reason="Layer C container-hardening adversarial requires Linux")` on every test in the module. macOS path is permanent per S5-02 (the macOS probe deterministically emits `StraceUnavailable`; this adversarial asserts runtime containment, meaningful only when the container actually runs).
- [ ] **Docker daemon reachability** — `pytest.skip("docker daemon unreachable")` with a loud reason if `docker` is not on `$PATH` OR `docker info` exits non-zero. The CI job (`adv-phase02`) MUST have docker reachable; S8-03 fails loudly if docker is missing (not silently skipped).
- [ ] **Test wall-clock budget** — Each of 5 per-fixture tests has its own timeout: forkbomb/infinite-loop ~120-200 s (timeout-dominated); network-touch/cap-chown/setuid ~5-15 s (fast scenarios). Coordinator test ~120-200 s. Total ~10-15 min in the `adv-phase02` job. If pressure: mark the slow tests `@pytest.mark.slow` and gate behind a PR label — but the default is "they run on every PR".
- [ ] **`mypy --strict` clean** on the test module + `_helpers.py`. Test surfaces are plain pytest; type-checking is straightforward. `Mapping[str, str]` annotation on the manifest; `Callable[[Path], str | None]` on the resolver factory; explicit return type on every helper.
- [ ] **`psutil` added to `[dev]` extras only** (NOT `[gather]`). Document in Notes-for-implementer: `[gather]` runtime closure is unchanged by this story; Phase 0 `fence` job is unaffected (`psutil` is not in the LLM-import blocklist).
- [ ] **No raw `subprocess.run` / `subprocess.Popen` in the test module** — every shell-out goes through `run_allowlisted` via the helpers. EXCEPT `test_process_count_helper_smoke` which deliberately spawns `subprocess.Popen(["sleep", "1"])` to verify the helper itself; that one is documented as the lone allowed exception (a self-check, not a docker-orchestration path). The `forbidden-patterns` pre-commit must exempt only the `test_process_count_helper_smoke` line.

## Implementation outline

1. Create the five fixture directories (`tests/fixtures/adversarial/dockerfile-{forkbomb,infinite-loop,network-touch,cap-chown,setuid}/`); each contains `Dockerfile`, `README.md` (labeled "DELIBERATELY ADVERSARIAL"), and `.codegenie/scenarios.yaml` (single-scenario override; command IS the adversarial invocation). Per K2: each fixture exercises exactly one hardening dimension — diagnostic independence.
   - `dockerfile-setuid` additionally commits a small `su-copy` binary (a tiny C `main(){ return 0; }` compiled and committed, OR an `id`-equivalent shell script — pick one and document in the fixture's README; the Dockerfile `COPY`s it and `chmod 4755`s it).
2. Create `tests/adv/phase02/_helpers.py` exposing the manifest + helpers per the "Helpers + manifest" AC block:
   - `_FIXTURE_TO_HARDENING_DIMENSION: Final[Mapping[str, str]]` (the literal 5-entry mapping).
   - `build_fixture_image(name) -> str` — builds + inspects via `run_allowlisted`; `pytest.fail` with stderr_tail on build error.
   - `make_resolver(digest) -> Callable[[Path], str | None]` — one-line factory.
   - `_make_probe_context(image_digest) -> ProbeContext` — constructs with all required fields explicit.
   - `_snapshot_process_count() -> int` — `len(psutil.Process(os.getpid()).children(recursive=True))`.
   - `noop_light_probe_fixture` — pytest fixture; registers `_NoOpLightProbe` (a `@register_probe(heaviness="light", name="noop_light")` class with trivial-slice `run()`); teardown unregisters. If the registry lacks `unregister`, surface to user — DO NOT workaround.
3. Create `tests/adv/phase02/test_adversarial_dockerfile.py`. Module docstring documents (a) the mutation-resistance ritual now structurally encoded via `_FIXTURE_TO_HARDENING_DIMENSION`; (b) the rule-of-three deferral note (per D1 + Notes-for-implementer); (c) the macOS-skip + docker-unreachable-skip + Linux-CI-required preconditions. Top-of-module: `pytestmark = pytest.mark.skipif(sys.platform != "linux", ...)`. Import `psutil`; add to `pyproject.toml` `[project.optional-dependencies] dev` extras if not already present.
4. **Each per-fixture test** (`test_forkbomb_timeout`, `test_infinite_loop_timeout`, `test_network_touch_blocked`, `test_cap_chown_blocked`, `test_setuid_blocked`):
   - Skip-if-docker-unreachable (helper: `_require_docker_reachable()` calls `run_allowlisted("docker", ["info"])` and `pytest.skip` on non-zero exit).
   - `digest = build_fixture_image(fixture_name)` — gates the test on build success; loud failure path via `pytest.fail`.
   - `ctx = _make_probe_context(digest)`; `snapshot = RepoSnapshot(root=_fixture_path(fixture_name))` (construct via Phase 0's `RepoSnapshot` factory; pin in the test that snapshot.root IS the fixture dir so S5-02's `safe_yaml.load` reads the fixture's `.codegenie/scenarios.yaml`).
   - `baseline = _snapshot_process_count()` BEFORE the probe (forkbomb test only; others can skip the baseline if irrelevant).
   - `output = await RuntimeTraceProbe().run(snapshot, ctx)`.
   - `final = _snapshot_process_count()` AFTER (forkbomb only); assert `abs(final - baseline) <= 2`.
   - Assert per-test outcome shape (see Acceptance criteria above for the exact assertions per fixture).
5. **The coordinator-continuation test** (`test_coordinator_continues_after_runtime_trace_timeout`):
   - Uses the `noop_light_probe_fixture` (registers `_NoOpLightProbe` with teardown).
   - Constructs a `Coordinator` with both `RuntimeTraceProbe` and `_NoOpLightProbe` registered.
   - Runs the coordinator against the `dockerfile-forkbomb` fixture.
   - Asserts both slices in the envelope; asserts `noop_finish_ms < runtime_trace_finish_ms` (the overlap proof — see T5); asserts the runtime_trace envelope shape matches `test_forkbomb_timeout`'s expectation (see T6).
6. Each helper / manifest / sanity test (`test_fixture_to_hardening_dimension_manifest_pins_all_flags`, `test_fixture_discovery_pins_all_test_functions`, `test_build_fixture_image_helper_returns_digest`, `test_process_count_helper_smoke`) is a small dedicated function per the Acceptance criteria block.

## TDD plan — red / green / refactor

**Red:**

1. Land the five fixture directories (`Dockerfile` + `README.md` + `.codegenie/scenarios.yaml` each); the `dockerfile-setuid` fixture additionally commits the `su-copy` binary. Absence is the initial red state.
2. Land `tests/adv/phase02/_helpers.py` with the manifest + 6 helper functions per the AC block. Initial state: import fails (module missing).
3. Land `test_fixture_to_hardening_dimension_manifest_pins_all_flags` — assertion fails because the manifest doesn't exist yet; once landed, fails until S5-02's `_HARDENING_FLAGS` constant is importable; once both land, **the test passes** AND any future flag deletion in S5-02 flips it red (the structural mutation test).
4. Land `test_fixture_discovery_pins_all_test_functions` — fails until all 5 `test_*` functions exist; once landed, **passes** and a future "added a 6th fixture but forgot the test" regression flips it red.
5. Land `test_build_fixture_image_helper_returns_digest` and `test_process_count_helper_smoke` — exercise the helpers in isolation; fast (< 5 s).
6. Land each per-fixture test in turn:
   - `test_forkbomb_timeout` — first run on a correct S5-02 should be GREEN (this story's *purpose* is to prove S5-02's claims with a structural test that future regressions trip on). The red phase is "the test does not exist"; the green phase is "the test exists and passes against S5-02".
   - `test_infinite_loop_timeout`, `test_network_touch_blocked`, `test_cap_chown_blocked`, `test_setuid_blocked` — same logic.
7. Land `test_coordinator_continues_after_runtime_trace_timeout` — uses `noop_light_probe_fixture`; asserts overlap (`noop_finish < runtime_trace_finish`); asserts both slices in envelope; asserts runtime_trace envelope shape matches `test_forkbomb_timeout`'s pinned expectation.
8. **Structural mutation-resistance is now committed** (not developer-runnable). The `_FIXTURE_TO_HARDENING_DIMENSION` manifest + `test_fixture_to_hardening_dimension_manifest_pins_all_flags` together encode the relationship: every `_HARDENING_FLAGS` element MUST be named by ≥ 1 fixture's dimension; every fixture MUST have a corresponding test. Replaces the developer-runnable "delete `--network=none` and observe failure" ritual.

**Green:**

1. Land the five fixture Dockerfiles + READMEs + per-fixture `.codegenie/scenarios.yaml`.
2. Land `_helpers.py` with the manifest + 6 helpers.
3. Land `test_adversarial_dockerfile.py` with all 6 main tests + 4 helper/manifest/sanity tests.
4. Confirm all 10 pass on a Linux CI runner with Docker reachable.

**Refactor:**

1. Confirm `_snapshot_process_count`, `build_fixture_image`, `_make_probe_context`, `make_resolver` are in `_helpers.py` — greppable pure (or single-impure-call) functions.
2. Confirm the test module is ≤ 350 LOC (5 fixture tests + 1 coordinator test + 4 helper tests + module docstring). The 200 LOC bound in the original story underestimated the 5-fixture + 4-helper-test surface; 350 is the realistic target.
3. Confirm each fixture's `README.md` is labeled "DELIBERATELY ADVERSARIAL — do not run outside the test harness; do not copy into production".
4. Confirm `_helpers.py` exports the manifest as `Final[Mapping[str, str]]` and the 6 helpers with explicit return types; `mypy --strict` clean.
5. Confirm `_FIXTURE_TO_HARDENING_DIMENSION` is named **exactly** the literal 5-entry mapping (mutation-test from K7).
6. Per D1: do NOT extract a `_FIXTURE_SPEC` dataclass + parametrized runner yet — 5 per-fixture test functions are readable. Document the seam in Notes-for-implementer for the next maintainer (when the 6th fixture lands).

## Files to touch

- **New fixtures (5):**
  - `tests/fixtures/adversarial/dockerfile-forkbomb/{Dockerfile,README.md,.codegenie/scenarios.yaml}`
  - `tests/fixtures/adversarial/dockerfile-infinite-loop/{Dockerfile,README.md,.codegenie/scenarios.yaml}`
  - `tests/fixtures/adversarial/dockerfile-network-touch/{Dockerfile,README.md,.codegenie/scenarios.yaml}`
  - `tests/fixtures/adversarial/dockerfile-cap-chown/{Dockerfile,README.md,.codegenie/scenarios.yaml}`
  - `tests/fixtures/adversarial/dockerfile-setuid/{Dockerfile,README.md,.codegenie/scenarios.yaml,su-copy}` (the setuid binary committed as a tiny C source + compiled binary OR an `id`-equivalent script; pick one and document in the fixture's README)
- **New tests:** `tests/adv/phase02/test_adversarial_dockerfile.py`, `tests/adv/phase02/_helpers.py`.
- **Possibly extend:** `pyproject.toml` `[project.optional-dependencies] dev = […]` — add `psutil` if not already present.
- **Possibly extend (escalation candidate):** `scripts/check_forbidden_patterns.py` — exempt only `test_process_count_helper_smoke` from the `subprocess.run / subprocess.Popen` ban (the helper's self-check uses `Popen(["sleep", "1"])` deliberately). If the forbidden-patterns predicate is path-scoped, no edit needed; if it's flat, add a narrow exemption.

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

- **The forkbomb fixture is the load-bearing piece** — it's the structural proof that `--cap-drop=ALL` + the per-scenario timeout contains the worst-case malicious Dockerfile. If the forkbomb test ever flakes (e.g., the ±2 process-count slack is too tight on a busy CI runner), the resolution is **not** to weaken the assertion — investigate whether the cgroup container actually contained the forkbomb. A flaky containment test is a load-bearing-bug; fix the containment, not the test.
- **Structural mutation-resistance is now committed.** The `_FIXTURE_TO_HARDENING_DIMENSION` manifest + `test_fixture_to_hardening_dimension_manifest_pins_all_flags` together encode the relationship between S5-02's `_HARDENING_FLAGS` and the fixtures. Replaces the developer-runnable "delete `--network=none` and observe failure" ritual that was in the original story draft (which the S5-04 T2 / S5-05 T2 hardening reports explicitly said should be structural, not developer-runnable). Future regressions trip the manifest test, not a manual ritual.
- **`docker` daemon reachability.** Local dev frequently lacks Docker; the CI job has it. The `pytest.skip("docker daemon unreachable")` path is acceptable on local — but the CI job MUST NOT skip; surface that in S8-03's job spec (the CI job should fail loudly if Docker isn't available, not silently skip). The implementer's PR description must call out the test path `tests/adv/phase02/test_adversarial_dockerfile.py` as new content the `adv-phase02` job glob must pick up.
- **S8-03 dependency** (moved from AC list to here). The CI job `adv-phase02` (S8-03) is named in `High-level-impl.md §"Step 8"` line 984 as already including `test_adversarial_dockerfile.py`. The implementer's responsibility is the test file; S8-03's responsibility is the YAML wiring. Verify by reading phase-arch-design.md L955 + High-level-impl.md L984 — both name the test.
- **`psutil` is a `[dev]` dep, not `[gather]`.** It's a test-only utility; Phase 0 `fence` should be unaffected (`psutil` is not in the LLM-import blocklist). Adding to `[gather]` would bloat the runtime install for no production benefit. The validator confirmed `[gather]` extras are unchanged by this story (zero runtime delta).
- **The "coordinator continuation" claim** is what Phase 0 isolation buys us. Without that, a forkbomb-Dockerfile-victim probe would block all other probes; with it, the coordinator continues. The `_NoOpLightProbe` is the minimal proof; if Phase 0's isolation mechanism is not actually wired through the coordinator under cancellation, this test surfaces it and the resolution is a Phase 0 issue (not this story's).
- **Five fixtures, one dimension each — diagnostic independence.** Per K2 hardening, the chown + setuid claims were split out of the forkbomb fixture into dedicated fixtures. Each fixture exercises exactly one hardening dimension; when one regresses, exactly one fixture's test fails. The fixture-to-dimension mapping is encoded as a `Final[Mapping[str, str]]` manifest in `_helpers.py`:
  - `dockerfile-forkbomb` → `--cap-drop=ALL` + per-scenario timeout (resource containment).
  - `dockerfile-infinite-loop` → per-scenario timeout (CPU containment, no fork).
  - `dockerfile-network-touch` → `--network=none` (network containment).
  - `dockerfile-cap-chown` → `--cap-drop=ALL` blocks CAP_CHOWN (privilege containment).
  - `dockerfile-setuid` → `--security-opt=no-new-privileges` (privilege-escalation containment).
- **Why `TraceScenarioCompleted` (not `Failed`) for network-touch / cap-chown / setuid?** S5-01's `TraceFailureReason` variant set is exactly `StraceUnavailable | DockerBuildFailed | ScenarioTimeout | ImageDigestUnresolved` — no `exit_code` or `stderr_tail` carrier. S5-02 produces `TraceScenarioCompleted` whenever the docker-run terminates and a trace was captured, regardless of CMD exit code. The proof of `--network=none` is *the absence of network endpoints in the parsed trace*; the proof of `--cap-drop=ALL` (chown) and `--security-opt=no-new-privileges` (setuid) is the presence of the failure-marker substring in the captured stderr_tail. This is the structural mode: trace contents, not variant routing.
- **Per-fixture `scenarios.yaml` override (C3).** Each fixture's `.codegenie/scenarios.yaml` declares a single scenario whose `command` IS the adversarial invocation. Without this, S5-02 falls back to `_DEFAULT_SCENARIOS` (5 canonical scenarios with canonical commands like `["sh", "-c", "echo healthcheck"]`) — those would NOT trigger the forkbomb / network-touch / etc. inside the fixture's image. The fixture-level override is load-bearing.
- **No real network calls leak in the network-touch fixture** — `--network=none` is enforced before the container's CMD runs; the `wget` immediately gets `bad address` from the kernel. The test does NOT depend on `example.com` being reachable, and the assertion is on `parsed_trace.network_endpoints_touched == frozenset()`, not on stderr-string-matching.
- **Wall-clock pressure.** Two 120 s timeouts (forkbomb + infinite-loop) + one coordinator test (~120 s) + 3 fast tests (~15 s each) + build time = ~10-15 min in the `adv-phase02` job. If pressure: mark with `@pytest.mark.slow` and gate behind a PR label — but the default should be "runs on every PR" because the container-hardening flags are non-negotiable per High-level-impl.md §"Step 5". S8-03 owns the budget envelope; this story owns the test correctness.
- **The test does NOT depend on S5-05.** S5-05's freshness check and S5-06's containment test are independent — both depend on S5-02, neither on the other.
- **Rule-of-three deferral (D1).** The 5 per-fixture test functions are still readable; per CLAUDE.md "three similar lines is better than premature abstraction" + S5-04 D2 / S5-05 D3 deferral precedents, the kernel-extraction-into-`_FIXTURE_SPEC`-dataclass + parametrized-runner pattern is **deferred to the 6th-fixture addition**. The seam shape for the next maintainer: a dataclass with `name: str`, `hardening_dimension: str`, `expected_outcome: Literal["timeout", "trace-completed-blocked", "trace-completed-with-marker"]`, `assertion_fn: Callable[[ProbeOutput], None]` — plus a parametrized `test_adversarial_fixture[spec]`. Defer until the 6th fixture lands (likely Phase 5+ microVM-equivalent or `--read-only` addition).
- **Extension by addition: adding a new hardening flag.** If S5-02 later adds a 4th flag (e.g., `--read-only` for root filesystem), the additive procedure is: (1) add the new fixture under `tests/fixtures/adversarial/dockerfile-readonly/`; (2) add the entry to `_FIXTURE_TO_HARDENING_DIMENSION` in `_helpers.py`; (3) add the test function. `test_fixture_to_hardening_dimension_manifest_pins_all_flags` AND `test_fixture_discovery_pins_all_test_functions` enforce that all three additions happen together. No edits to existing fixtures.
- **Open question — runner-level cap escalation.** Some CI runners (privileged Docker-in-Docker) might *accidentally* allow `chown` because the outer runner has CAP_CHOWN. The test asserts the *inner* container fails, not the outer; the assertion target is the captured stderr_tail (`operation not permitted`), not the host's permissions. Document in the test module docstring; surface as an ADR-amend candidate if a future CI environment regresses this.
- **`build_fixture_image` digest reuse semantics.** The helper builds with `-t <tag>` (named tag) AND captures the digest via `docker image inspect`. The resolver returns this digest; S5-02's probe (during its `_execute_scenario`) will call `docker build` AGAIN with the same context — the build is incremental-cached by Docker daemon, so the second build is fast (< 1 s for an already-built image) and produces the same digest. This is wasted but functionally correct. If the implementer finds this wasteful in benchmark numbers, the optimization is **deferred to S5-02** (e.g., add a "skip-build if digest already exists locally" path) — NOT to S5-06.
