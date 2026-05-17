# Validation report: S5-06 — `adversarial_dockerfile` container-hardening test

**Validated:** 2026-05-17
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1
**Story:** [`../S5-06-adversarial-dockerfile.md`](../S5-06-adversarial-dockerfile.md)

## Summary

S5-06 lands the load-bearing structural proof that `RuntimeTraceProbe`'s hardening triple (`--network=none --cap-drop=ALL --security-opt=no-new-privileges`) + per-scenario 120 s timeout + Phase 0 coordinator-isolation contain a worst-case hostile Dockerfile. The story's *intent* (a CI-gating adversarial under `tests/adv/phase02/` proving the four containment dimensions named in High-level-impl.md §"Step 5") is well-formed, traces cleanly to phase-arch-design.md §"Testing strategy", and honors the four ADRs it claims (02-ADR-0001 for `docker` allowlist; 02-ADR-0007 for in-tree-not-plugin).

The *contract surface* the original draft prescribed, however, contradicted the S5-01 variant set at two load-bearing points (the network-touch test asserted `TraceScenarioFailed(exit_code != 0, stderr_tail=…)`, but `TraceFailureReason` has no `exit_code`/`stderr_tail` carrier — the four variants are `StraceUnavailable | DockerBuildFailed | ScenarioTimeout | ImageDigestUnresolved`), under-specified the scenario-command wiring (the forkbomb fixture had no `scenarios.yaml` override, so the default 5 scenarios with their canonical commands would run instead of the forkbomb), and embedded the chown/setuid hardening proofs inside the forkbomb fixture in direct contradiction of the story's own diagnostic-independence rationale in Notes-for-implementer ("Four-of-five claims are independent; folding them into one fixture would couple the assertions and weaken the diagnostic when one regresses").

All three were fixable in-place against existing precedents (S5-01 variant set at `src/codegenie/probes/layer_c/scenario_result.py`; S5-02 `scenarios.yaml` override mechanism at AC line 67; S5-05 hardening of "diagnostic independence as separate test functions / separate fixtures"); none required architectural change. Six additional test-quality hardens (mutation-resistance suite per S5-04 T2 precedent; coordinator-overlap proof; aggregate-timeout-not-fired AC; stdout backpressure; psutil sanity; wall-clock-bound rationale) and three design-pattern hardens (Open/Closed seam documented for the rule-of-three trigger; registry teardown for `_NoOpLightProbe`; resolver-construction pattern pinned) were applied.

No `NEEDS RESEARCH` findings — every gap traced to an in-repo precedent (S5-01 variants, S5-02 contract surface, S5-05 hardening report, S5-04 mutation-resistance precedent, S5-03 AST-walk audit precedent).

Eighteen in-place edits applied; verdict **HARDENED**. Story is now structurally consistent with the existing S5-01/S5-02 contract surface and the five validation reports already landed for the S5-* family.

## Context Brief (Stage 1)

### Story snapshot
- **Goal:** Land `tests/adv/phase02/test_adversarial_dockerfile.py` + supporting fixture Dockerfiles under `tests/fixtures/adversarial/`. Prove (a) hardening triple contains a forkbomb / infinite-loop / network-touching adversarial Dockerfile; (b) per-scenario 120 s timeout fires; (c) no host-level process count growth occurs; (d) coordinator continues with subsequent probes after the timeout fires.
- **Non-goals:** image-digest-drift adversarial (S5-05); stale-scip (S4-02 + S7-02); secret-in-source (S6-07); hostile-skills-YAML (S7-04); concurrent-gather race (S7-04); macOS-equivalent container hardening; cross-runtime (`podman`); microVM-equivalent (Phase 5+).
- **Effort:** S
- **Depends on:** S5-02 (`RuntimeTraceProbe` ships with the hardening flags).

### Phase / arch constraints touched
- **02-ADR-0001** — `docker` in `ALLOWED_BINARIES`; hardening flags are the audit trail for the docker allowlist entry (final-design.md §"Tradeoffs accepted" row 3 — *"Mitigated by `tests/adv/phase02/test_adversarial_dockerfile.py` exercising the cap-drop path"*).
- **02-ADR-0007** — no Plugin Loader; the adversarial Dockerfile is a fixture under `tests/fixtures/`, not a plugin under `plugins/`.
- **phase-arch-design.md §"Testing strategy"** row "`test_adversarial_dockerfile.py`" (line 955) — names the test alongside the load-bearing corpus.
- **phase-arch-design.md §"Edge cases" row 5** (line 861-style adversarial-Dockerfile edge) — adjacent failure path.
- **High-level-impl.md §"Step 5"** — *"container-hardening flags (`--network=none --cap-drop=ALL --security-opt=no-new-privileges`) are non-negotiable; the `test_adversarial_dockerfile.py` is the proof"*. The CI job `adv-phase02` (S8-03) gates the test path.
- **CLAUDE.md** "Extension by addition" — new hardening flags add new fixtures additively; current Phase 2 set is closed at 3 (or 4 if read-only is later added).
- **CLAUDE.md** "Determinism over probabilism for structural changes" — the test must encode the hardening claim structurally (typed scenario outcomes + trace-content assertions), not via fragile substring scans of stderr.

### Sibling-family lineage
- **4th adversarial test landed under `tests/adv/phase02/`** (after S4-02 `test_stale_scip_fixture.py`, S5-05 `test_image_digest_drift.py`, S6-07 `test_secret_in_source.py` planned). Five more land in S7-04 (`hostile_skills_yaml`, `concurrent_gather_race`, `no_inmemory_secret_leak`, `phase3_handoff_smoke`). The phase exit criterion ("adversarial corpus ≥ 6 cases") is met by this set.
- **2nd structural-proof adversarial** for Layer C (after S5-05's image-digest-drift). S5-05 proves *cache invalidation correctness*; S5-06 proves *runtime containment correctness*.
- **1st adversarial that requires a real `docker build`** — S4-02 / S5-05 use mocked or pre-built images; S5-06 needs the real container runtime to prove the hardening flags work end-to-end.
- **Rule-of-three threshold:** **reached** but kernel-extraction (a `dockerfile-adversarial-fixture` manifest + parametrized runner) is **deferred** to the 4th fixture addition (mirrors S5-04 D2 / S5-05 D3 deferral pattern). Seam documented in Notes-for-implementer.

### Prior validation framings carried forward
- **S5-02 hardening:** envelope `confidence` is the frozen `Literal["high","medium","low"]`; `"unavailable"` is a slice-level signal, never an envelope value. The macOS path is permanent; `sys.platform != "linux"` is the canonical detector. `_HARDENING_FLAGS` is the module-level constant; tests import it.
- **S5-03 hardening:** AST-walk audits supersede source-grep purity tests (where a "did the test author do the right thing?" check is needed).
- **S5-04 hardening:** mutation-resistance suite is mandatory; `Final[...]` discipline on module constants; rule-of-three trigger documented for downstream story authors.
- **S5-05 hardening:** diagnostic independence demands separate test functions / separate fixtures; B2 integration tests assert against `schema_slice["index_health"]`; the contract-level signal (cache-key inequality) is preferred over implementation-level state (probe-method invocation count).

### Phase exit criteria the story contributes to
- **G6** (final-design §"Goals") — adversarial corpus ≥ 6 cases under `tests/adv/phase02/`. This story is the 4th (of ≥ 8 planned).
- **G6** (phase-arch-design §"CI gates") — `adv-phase02` is a load-bearing CI job; S8-03 wires the YAML.
- **High-level-impl.md §"Step 5" Risks** — "the container-hardening flags are non-negotiable; the `test_adversarial_dockerfile.py` is the proof".

### Open ambiguities discovered during Stage 1
- **Network-touch scenario outcome.** Story asserted `TraceScenarioFailed(exit_code != 0, stderr_tail=…)` — but `TraceFailureReason` has no `exit_code`/`stderr_tail` carrier (S5-01 variant set is `StraceUnavailable | DockerBuildFailed | ScenarioTimeout | ImageDigestUnresolved`). S5-02's Layer C does NOT route through `run_external_cli`'s `ProcessResult` shape; per S5-02 outline (f), a docker-run that completes (any exit code) yields `TraceScenarioCompleted` with the trace contents reflecting what happened. **Resolved at synthesis:** rewrite the network-touch assertion as `TraceScenarioCompleted` with `network_endpoints_touched == frozenset()` (proves `--network=none` blocked the wget syscalls early); wall-clock fast-fail (< 30 s) becomes a wall-clock-bound assertion on the same Completed outcome, not on a Failed outcome.
- **Forkbomb scenario-command wiring.** Story said "Invoke `RuntimeTraceProbe.run` against the forkbomb fixture" but didn't specify how `scenario.command` from `_DEFAULT_SCENARIOS` becomes the forkbomb invocation. The default 5 scenarios have their own canonical commands (`startup`, `smoke_test`, etc.); without a fixture-level `scenarios.yaml` override, those commands run inside the forkbomb image — they would not trigger the forkbomb. **Resolved at synthesis:** each fixture ships its own `.codegenie/scenarios.yaml` declaring a single scenario whose `command` is the adversarial invocation; the test fixture sets `snapshot.root = fixture_dir`, so S5-02's `safe_yaml.load` reads the fixture's scenarios.yaml.
- **chown/setuid claims folded into forkbomb fixture.** Notes-for-implementer says "folding them into one fixture would couple the assertions and weaken the diagnostic when one regresses" — but the ACs do exactly that. **Resolved at synthesis:** split into two new fixtures (`dockerfile-cap-chown` and `dockerfile-setuid`) with dedicated test functions; the forkbomb fixture's CMD becomes the pure forkbomb (no chown, no setuid). Total fixtures: 5; total test functions: 5 (1 per fixture) + 1 coordinator-continuation = 6.

## Findings by critic

### Coverage critic (K)

| ID | Severity | Finding | Proposed fix |
|---|---|---|---|
| K1 | harden | Goal says "three test functions" but TDD plan enumerates four (forkbomb, infinite-loop, network-touch, coordinator). After resolving K2 (chown/setuid split), the count becomes 6. The story-internal inconsistency hides the load-bearing coordinator-continuation function as a sub-bullet of the forkbomb AC. | Goal rewritten: enumerate exactly 6 test functions; AC list mirrors. The coordinator-continuation test is elevated to a peer-test (`test_coordinator_continues_after_runtime_trace_timeout`), not embedded inside the forkbomb test. |
| K2 | harden | The forkbomb fixture's CMD attempts (a) forkbomb, (b) `chown 0:0 /etc/passwd`, (c) setuid binary invocation — all in one scenario. This couples three hardening-dimension proofs; a regression in any one is diagnosed against the forkbomb fixture and the diagnostic narrows poorly. Story's own Notes contradict this folding. | Split into 3 fixtures: `dockerfile-forkbomb` (pure forkbomb), `dockerfile-cap-chown` (CMD = `chown 0:0 /etc/passwd; exit 0`), `dockerfile-setuid` (CMD = invokes a setuid binary baked into the image). Each gets its own test function asserting on the matching trace content. Total: 5 fixtures + 1 coordinator integration = 6 test functions. |
| K3 | harden | No AC for the `docker build` success precondition. If a fixture's `RUN apk add foo` fails at build time (e.g., network blip on the host pulling alpine), the test path collapses to `Skipped(ImageBuildUnavailable)` and would falsely "pass" the containment claim (the test asserts on `Failed(ScenarioTimeout)`, doesn't find it, fails for the wrong reason — opaque). | New AC: each test asserts `helpers.build_fixture_image(name)` returns a non-empty digest BEFORE invoking the probe; build failure raises `pytest.fail("docker build failed for fixture <name>: <stderr_tail>")` with the build's stderr_tail surfaced. Loud failure path, distinct from the containment assertion. |
| K4 | harden | No AC for "ALL configured scenarios time out" — the test asserts one `ScenarioTimeout` but doesn't pin the count. If S5-02 silently regresses to early-exit on the first failure, a single timeout would appear and the test would pass while 4 scenarios were skipped. | Each per-fixture test asserts `len([r for r in results if isinstance(r, TraceScenarioFailed) and isinstance(r.reason, ScenarioTimeout)]) == len(_configured_scenarios)`. Pin the count against the fixture's scenarios.yaml. |
| K5 | harden | Network-touch test asserts `stderr_tail` contains `bad address` or `Network is unreachable` — fragile (Alpine's wget vs busybox vs other base images produce different strings; locale-sensitive). | Reframe network-touch to assert on trace contents instead: `parsed_trace.network_endpoints_touched == frozenset()` AND `"wget"` (or whatever the CMD's binary is) `in binaries_executed`. This proves the binary RAN but the network call was blocked (the proof of `--network=none`), structurally rather than via stderr string-matching. |
| K6 | harden | No AC for the **aggregate** 600 s timeout NOT firing on the forkbomb test. Each forkbomb scenario takes 120 s; 5 × 120 s = 600 s = the aggregate budget exactly. If the aggregate fires, the per-scenario timeout proof is undermined (the timeouts came from the aggregate cancellation, not per-scenario). | New AC: assert all per-scenario results are `TraceScenarioFailed(reason=ScenarioTimeout(seconds=120))`, NOT one mix of `ScenarioTimeout` + 4 `Skipped(ImageBuildUnavailable)` (which is what S5-02's aggregate-timeout path produces — the closest variant for "didn't run" per S5-02 outline (e)). The distinction pins per-scenario semantics. |
| K7 | nit | `len(psutil.process_iter())` measures whole-system process count; flaky on busy CI for reasons unrelated to forkbomb (a parallel pytest plugin spawning subprocesses, a background daemon waking up). Story mentions `Process(os.getpid()).children(recursive=True)` as an option but doesn't pin it. | Pin `psutil.Process(os.getpid()).children(recursive=True)` as the canonical signal; `process_iter()` is named only as a fallback if `children(recursive=True)` returns 0 on platforms where the test runner spawns no children (defensive). Slack tightened from ±5 to ±2 because the signal is now scoped to the runner's own subprocess tree. |
| K8 | nit | "Test runs in `adv-phase02` CI job (S8-03)" is not testable in this story; it's a PR-description / S8-03-dependency note. | Moved from AC list to Notes-for-implementer; surfaced as an explicit S8-03 dependency for the implementer to flag in the PR description. |

### Test-Quality critic (T)

| ID | Severity | Finding | Proposed fix |
|---|---|---|---|
| T1 | harden | Mutation test ritual ("delete `--network=none`, observe failure") is documented but NOT committed — explicitly developer-runnable only. This is the exact pattern S5-04 T2 / S5-05 T2 hardened away from: mutation resistance MUST be structurally enforced. | Add a committed parametrized "fixture-to-hardening-flag mapping" test: a module-level dict `_FIXTURE_TO_HARDENING_DIMENSION: Final[Mapping[str, str]] = {"dockerfile-forkbomb": "cap-drop+timeout", "dockerfile-infinite-loop": "timeout", "dockerfile-network-touch": "network-none", "dockerfile-cap-chown": "cap-drop", "dockerfile-setuid": "no-new-privileges"}` lives in `_helpers.py`. A test parametrizes over the mapping and asserts each fixture's dimension is a non-empty string AND every element of `RuntimeTraceProbe._HARDENING_FLAGS` is named by at least one fixture's value. Catches the "added a flag but forgot the fixture" + "added a fixture but forgot the dimension" regressions. Mutation-resistance: deleting `--cap-drop=ALL` from S5-02's `_HARDENING_FLAGS` flips a new test red because no fixture would name the removed dimension. |
| T2 | harden | No fixture-discovery test. A future maintainer who adds `dockerfile-read-only/` but forgets the test function would silently land an unexercised fixture. | New AC: a parametrized test discovers `tests/fixtures/adversarial/dockerfile-*/` via `glob`; asserts every discovered fixture is named in `_FIXTURE_TO_HARDENING_DIMENSION` AND has a corresponding `test_*` function in the test module (introspect via `inspect.getmembers`). Catches the "added a fixture but forgot the test" regression. |
| T3 | harden | Wall-clock bound `120 ≤ wall_clock ≤ 150` is fragile (CI machine speed varies; docker startup can add 5-10 s easily). The 30 s slack is generous-but-not-generous-enough on slow runners. | Relax upper bound to `< 600` (aggregate budget); tighten lower bound to `>= 120` (the timeout fired). The narrow 30 s window is replaced by the structural distinction "per-scenario timeout fired AND aggregate didn't fire" (which K6 already pins). Document the rationale: wall-clock is a sanity-check, not a precision measurement. |
| T4 | harden | No sanity test that the `_snapshot_process_count` helper itself works. If `Process(os.getpid()).children(recursive=True)` returns 0 (no children of the runner), the delta-≤-2 assertion is vacuously true and the test would pass even if the cap-drop containment broke and the forkbomb DID escape. | New AC: `test_process_count_helper_smoke` — spawns a subprocess via `subprocess.Popen(["sleep", "1"])`, asserts `_snapshot_process_count()` increases by ≥ 1 while the subprocess is alive AND returns to baseline after the subprocess exits. Confirms the helper actually detects subprocess existence. |
| T5 | harden | The "coordinator continuation" claim is weak as written — it asserts the noop probe's slice IS in the envelope, but a coordinator that serializes probes (runs noop AFTER runtime_trace's full timeout) would pass this assertion trivially. The real claim is the noop COMPLETES while runtime_trace is still timing out (concurrency proof). | New AC: assert `noop_probe_finish_wall_clock < runtime_trace_finish_wall_clock`. If the coordinator's parallelism is sufficient, the noop probe finishes in < 1 s while runtime_trace takes the full timeout. Catches a regression where the coordinator inadvertently serializes after a probe begins timing out. |
| T6 | harden | No assertion on coordinator semantics for the cancelled runtime_trace probe in the coordinator-continuation test. After scenario timeout, does the coordinator mark the probe's envelope as `Failed`, `Skipped`, or `Completed-with-failures`? Without pinning, a coordinator refactor that changes the semantics silently passes. | New AC: in the coordinator test, assert the envelope shape for `runtime_trace` matches the per-fixture test's expected envelope (`confidence="low"`, all 5 scenarios = `TraceScenarioFailed(ScenarioTimeout)`). Pins the coordinator's pass-through of probe envelopes under cancellation. |
| T7 | harden | The infinite-loop CMD `while true; do echo .; done` produces unbounded stdout. S5-02's `run_external_cli` cap (64 MB per stream) does NOT apply to Layer C (uses `run_allowlisted` directly, per arch line 508). If there's no equivalent cap, the test runner could OOM. | New AC: `test_infinite_loop_stdout_capped` — asserts the captured stdout for the infinite-loop scenario is < 16 MB (sane cap for any container's lifetime). If S5-02 doesn't enforce a cap, this AC surfaces a real Phase 2 gap — implementer should escalate to S5-02 amendment rather than work around it in the test. |

### Consistency critic (C)

| ID | Severity | Finding | Proposed fix |
|---|---|---|---|
| C1 | block | **Network-touch test asserts a TraceScenarioFailed variant that cannot exist.** Story AC: `TraceScenarioFailed with exit_code != 0 and stderr_tail contains "Network is unreachable"`. But `TraceFailureReason` (S5-01) is exactly `StraceUnavailable \| DockerBuildFailed \| ScenarioTimeout \| ImageDigestUnresolved` — NO `exit_code` or `stderr_tail` carrier. Layer C does not route through `ScannerOutcome` (which DOES carry `exit_code`/`stderr_tail` — arch line 740); Layer C produces `ScenarioResult`. The test would crash on attribute access. | Reframe as `TraceScenarioCompleted` with `parsed_trace.network_endpoints_touched == frozenset()` AND `wall_clock_ms < 30_000`. The trace contents are the proof; the absence of network endpoints is `--network=none` working. Aligns with S5-02's documented "scenario completes if trace was captured" semantics. |
| C2 | block | **Test doesn't pin `ProbeContext` construction.** Story says "stubbed `image_digest_resolver`" but doesn't specify the contract. The test needs to construct a `ProbeContext(image_digest_resolver=lambda root: digest, …)` and pass it into `RuntimeTraceProbe.run(snapshot, ctx)`. Without pinning, a future ProbeContext refactor (adding a required field) silently breaks the test. | New AC: helper `_make_probe_context(image_digest: str) -> ProbeContext` lives in `_helpers.py`; test constructs the context exclusively via the helper. Helper imports `ProbeContext` from `src/codegenie/probes/base.py` and constructs it with all required fields explicit. Catches missing-required-field regressions immediately. |
| C3 | block | **Fixture scenario-command wiring is unspecified.** Without a `.codegenie/scenarios.yaml` under each fixture, S5-02 falls back to `_DEFAULT_SCENARIOS` — five canonical scenarios with their canonical commands (which are NOT the adversarial invocation). The forkbomb test would run the default `startup`, `smoke_test`, etc. commands inside the forkbomb image; none of those would trigger the forkbomb. | New AC: each fixture ships a `.codegenie/scenarios.yaml` declaring a single scenario (e.g., `scenarios: [{name: "adversarial", command: ["/bin/sh", "-c", ":(){ :\|:& };:"]}]` for forkbomb). The test asserts the fixture's scenarios.yaml is loaded (snapshot.root = fixture_dir; S5-02's `safe_yaml.load` reads it). Aligns the test's actual execution with the assertion. |
| C4 | harden | No pin on how the `image_digest_resolver` returns the just-built digest. The test must run `docker image inspect <tag> --format='{{.Id}}'` somewhere to know the digest. If this routes through raw `subprocess`, it bypasses the `run_allowlisted` chokepoint — Phase 0 `forbidden-patterns` would flag it. | New AC: `_helpers.py::build_fixture_image(name) -> str` returns the digest via `run_allowlisted("docker", ["image", "inspect", tag, "--format={{.Id}}"])`. The helper is the single source of digest resolution; tests bind `lambda root: digest` from the helper's return. No raw subprocess in the test surface. |
| C5 | harden | `_NoOpLightProbe` is defined inline with `@register_probe` — pollutes the module-level registry. If the test module is imported by another test (or runs after another test), the registry has a stale `_NoOpLightProbe` entry. | New AC: `_NoOpLightProbe` is registered via a pytest fixture (`@pytest.fixture` with `yield` + teardown that calls `probe_registry.unregister("noop_light")` or equivalent). Test imports the fixture; registry stays clean. If `unregister` doesn't exist on the registry, surface as an S1-08 dependency for the implementer to escalate (don't work around with `del`). |
| C6 | nit | `pytest.mark.skipif(sys.platform != "linux", …)` — consistent with S5-02's canonical detector. ✓ | No change required. |
| C7 | nit | `psutil` added to `[dev]` extras — consistent with the "test-only utility, not a runtime dep" rationale; `psutil` is NOT in the LLM-import blocklist (Phase 0 `fence` job). ✓ | No change required. Document explicitly in Notes-for-implementer that `[gather]` extras are unchanged (zero runtime delta). |
| C8 | nit | "Test runs in `adv-phase02` CI job (S8-03)" — correct per phase-arch-design.md line 984. ✓ But surfaced as an AC instead of an S8-03 dependency. | Move to Notes-for-implementer; add to Out-of-scope list (S8-03 owns CI wiring). |

### Design-Patterns critic (D)

| ID | Severity | Finding | Proposed fix |
|---|---|---|---|
| D1 | harden | **Open/Closed at the fixture boundary.** Three fixtures grow to five with the K2 split. The next addition (e.g., `dockerfile-read-only` for `--read-only`) would be the 6th fixture — past the rule-of-three threshold but the test module is still hand-coded (one `test_*` function per fixture). Per CLAUDE.md "Extension by addition" + S5-04 D2 / S5-05 D3 deferral pattern: extract at the 6th-or-later addition, not the 5th. | Document the seam in Notes-for-implementer: the extraction shape is a `_FIXTURE_SPEC` dataclass (`name: str`, `hardening_dimension: str`, `expected_outcome: Literal["timeout", "trace-completed-blocked"]`, `assertion_fn: Callable[[ProbeOutput], None]`) + a parametrized `test_adversarial_fixture[spec]`. Surface in Notes so the next maintainer knows where to extract when they land the 6th fixture (likely Phase 5+ microVM equivalent or `--read-only` addition). |
| D2 | harden | `_FIXTURE_TO_HARDENING_DIMENSION` (T1) IS the manifest pattern. Once it exists, the per-fixture test functions duplicate its information. The deferred extraction (D1) collapses the duplication. | Land the manifest now (T1 / T2 require it); defer the parametrized test-runner extraction. Per Rule 2: "three similar lines is better than premature abstraction" — five `test_*` functions are still readable; extract at the 6th. |
| D3 | nit | `_helpers.py` extraction is correct (pure helpers, greppable). | No change. Document in Notes that the helpers are the I/O boundary: `_snapshot_process_count` (impure — psutil call), `build_fixture_image` (impure — subprocess), `_make_probe_context` (pure — value construction). Pure/impure separation honored. |
| D4 | nit | `_NoOpLightProbe` uses `@register_probe(heaviness="light")` — Phase 1 ADR-0003 (heaviness sort) compatible. ✓ | No change; covered by C5 fixture-teardown. |
| D5 | harden | The resolver binding pattern (`lambda root: digest`) is repeated 5 times across 5 tests. Trivial duplication. | `_helpers.py::make_resolver(digest: str) -> Callable[[Path], str \| None]` — one-line factory. Tests import it. Eliminates duplication; centralizes the type-signature pin (catches a future `ProbeContext.image_digest_resolver` signature drift). |
| D6 | nit | The `register_probe` decorator coupling is acknowledged via the fixture-teardown pattern (C5). ✓ | No change beyond C5. |

## Researcher (Stage 3)

**Not invoked.** Zero `NEEDS RESEARCH` findings.

Rationale: every coverage / test-quality / consistency / design-pattern gap traced to an existing in-repo precedent — S5-01 variant set (`scenario_result.py`), S5-02 implementation outline (scenarios.yaml, ProbeContext, `_HARDENING_FLAGS`), S5-05 validation framings (diagnostic independence; B2-integration shape), S5-04 mutation-resistance precedent, S5-03 AST-walk audit precedent, Phase 0 `run_allowlisted` chokepoint, Phase 2 `_helpers.py` patterns. No external canonical pattern is required; the validator's job here is to align the story with existing precedents.

## Synthesis & edits applied

Synthesis order per validator priority (Consistency > Coverage > Test-Quality > Design-Patterns):

**Block-severity Consistency fixes first** (C1 + C2 + C3): the network-touch test was prescribing a variant that cannot exist (C1); the ProbeContext + resolver construction was unpinned (C2); the fixture scenario-command wiring was unspecified (C3). All three resolved by tightening AC text to match S5-01 / S5-02 contracts exactly.

**K2 (chown/setuid fixture split)** then resolved — it removes the AC-vs-Notes contradiction and creates the diagnostic independence the author already advocated for.

**T1 + T2 (mutation-resistance + fixture-discovery)** then landed via the `_FIXTURE_TO_HARDENING_DIMENSION` manifest in `_helpers.py`. This satisfies both findings with one structure (and earns D2's nod toward the eventual D1 kernel extraction).

**Remaining hardens** then landed: K3 (build-success precondition), K4 (all-scenarios timed out), K5 (trace-content over stderr-match), K6 (aggregate-timeout-not-fired), K7 (process-count signal scope), K8 + C8 (S8-03 dep → Notes), T3 (wall-clock bounds rationale), T4 (helper sanity), T5 + T6 (coordinator overlap + envelope pinning), T7 (stdout backpressure), C4 (digest-resolution chokepoint), C5 (registry teardown), D1 + D2 (rule-of-three extraction seam doc), D3 (pure/impure helper boundary doc), D5 (resolver factory helper).

**One conflict resolved with Consistency dominance:** D1 wants kernel extraction "for the rule-of-three threshold"; CLAUDE.md "three similar lines is better than premature abstraction" + S5-04 D2 / S5-05 D3 precedents say "defer until the 4th-of-the-pattern addition." Five test functions are still readable and the manifest already exists; defer the parametrized-runner extraction. The seam is documented for the next maintainer.

**Final test/fixture count after edits:** 5 fixtures (forkbomb, infinite-loop, network-touch, cap-chown, setuid) + 6 test functions (1 per fixture + 1 coordinator integration) + 4 helper-sanity / manifest tests = 10 test functions total. Story remains "S" effort because the helper extraction is small.

## Edits applied (18 in-place changes)

| # | Edit | Where | Critic finding |
|---|---|---|---|
| 1 | Validation notes block appended after header | Story header | (this report) |
| 2 | Goal rewritten: 5 fixtures + 6 test functions enumerated | Goal section | K1 + K2 |
| 3 | Forkbomb fixture AC: CMD is pure forkbomb (no chown, no setuid) | AC #1 | K2 |
| 4 | Infinite-loop and network-touch ACs preserved with C3 fixture-level scenarios.yaml addition | AC #2, AC #3 | C3 |
| 5 | `dockerfile-cap-chown` fixture AC added (CMD: `chown 0:0 /etc/passwd; exit 0`) | New AC | K2 |
| 6 | `dockerfile-setuid` fixture AC added (CMD: invokes setuid binary baked into image; setuid bit set via `chmod 4755 /bin/su-copy` in RUN) | New AC | K2 |
| 7 | Network-touch test AC rewritten: assert `TraceScenarioCompleted` + `parsed_trace.network_endpoints_touched == frozenset()` + `wall_clock_ms < 30_000` | AC for network-touch test | C1 + K5 |
| 8 | Forkbomb test AC: pin `all 5 scenarios are TraceScenarioFailed(ScenarioTimeout(120))` (count + variant) | AC for forkbomb test | K4 |
| 9 | Aggregate-timeout-not-fired AC: assert NOT one `Failed(ScenarioTimeout)` + 4 `Skipped(ImageBuildUnavailable)` | AC for forkbomb test | K6 |
| 10 | Docker-build-success precondition AC: helper raises `pytest.fail` with stderr_tail on build failure; ALL tests gate on success | New AC | K3 |
| 11 | `Process.children(recursive=True)` pinned as canonical signal; slack tightened to ±2 | "No host process escape" AC | K7 |
| 12 | `_FIXTURE_TO_HARDENING_DIMENSION` manifest test AC added (mutation-resistance + fixture-discovery in one structure) | New AC | T1 + T2 |
| 13 | Process-count helper sanity test AC: spawn `sleep 1` subprocess, assert delta ≥ 1 while alive, returns to baseline after | New AC | T4 |
| 14 | Coordinator-continuation test elevated to peer-test `test_coordinator_continues_after_runtime_trace_timeout`; assert `noop.finish < runtime_trace.finish` (overlap proof) AND envelope shape pinned | Rewritten coordinator AC | T5 + T6 |
| 15 | Stdout-backpressure AC: assert infinite-loop captured stdout < 16 MB; surface S5-02 gap if no cap exists | New AC | T7 |
| 16 | `ProbeContext` construction pinned via `_helpers.py::_make_probe_context(image_digest)`; resolver factory `_helpers.py::make_resolver(digest)` | Implementation outline | C2 + D5 |
| 17 | Fixture-level `.codegenie/scenarios.yaml` required for each fixture; declares single scenario whose command IS the adversarial invocation | Implementation outline + AC | C3 |
| 18 | `_NoOpLightProbe` registered via pytest fixture with teardown; if registry lacks `unregister`, escalate to S1-08 (don't workaround) | Implementation outline | C5 |
| — | Notes additions (not counted as edits): S8-03 dependency note; rule-of-three extraction seam (`_FIXTURE_SPEC` dataclass shape) for next maintainer; wall-clock bound rationale (`>= 120 AND < 600`); pure/impure helper boundary documented; `[gather]` extras unchanged |

## Verdict

**HARDENED.** Eighteen in-place edits applied. Story is now:

- Structurally consistent with the S5-01 variant set (no `exit_code` on `TraceFailureReason`)
- Structurally consistent with the S5-02 contract surface (`ProbeContext.image_digest_resolver`, fixture-level `scenarios.yaml`, sequential scenario execution)
- Diagnostically independent (5 fixtures × 1 dimension each, per Notes-for-implementer's own rationale)
- Mutation-resistant via committed `_FIXTURE_TO_HARDENING_DIMENSION` manifest
- Extension-by-addition-ready (`_FIXTURE_SPEC` dataclass + parametrized runner extraction is the documented next-maintainer seam at the 6th-fixture trigger)
- Honest about S5-02 dependencies (stdout cap; ProbeContext construction; `_NoOpLightProbe` registry teardown — each surfaces as escalation-candidate if S5-02 / S1-08 doesn't already accommodate)

The hardened story is ready for `phase-story-executor`. The implementer should not start until they have a Linux CI runner with Docker reachable; macOS dev hosts can land the fixtures and the no-op tests but cannot validate the containment claims locally.
