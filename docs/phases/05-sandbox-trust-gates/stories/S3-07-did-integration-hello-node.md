# Story S3-07 — DinD integration suite against `hello-node`

**Step:** Step 3 — Implement DinD backend + SandboxSpecBuilder + SandboxHealthProbe
**Status:** HARDENED
**Effort:** L
**Depends on:** S3-01 (`SandboxSpecBuilder.for_gate(gate, attempt, ctx) -> SandboxSpec` — DI ports `catalog` / `filter_fn` / `host_env_source`; no `for_gate_test_override`), S3-02 (`DockerInDockerClient.__init__(*, docker_url=None, docker_factory=docker.from_env)` — **no `allowlist=` parameter**), S3-03 (build + iptables network chokepoints; client structurally changed to create(`entrypoint=["sleep","infinity"]`)→start→apply_policy→exec_run(`spec.cmd`,demux=True)→revert→remove), S3-04 (copy-out + OOM + timeout populating `SandboxRun.{timed_out, killed_by_oom, copy_out_root}`), S3-05 (populated YAML catalogs + multi-phase collapse + digest-pinned policy)
**ADRs honored:** ADR-0001 (chokepoints still in place — integration must not bypass), ADR-0004 (DinD = `shared_kernel`), ADR-0012 (env-allowlist applied via `env_allowlist.filter` — there is no `EnvAllowlist` *class*), ADR-0013 (policy YAML digest verified), ADR-0014 (every `SandboxRun` / `SandboxSpec` access uses the frozen Pydantic surface — no dict shuffling)

## Validation notes (2026-05-24, phase-story-validator)

**Verdict:** HARDENED. The draft correctly identified the four-integration-test deliverable and traced cleanly to Goals 5 / 10 + ADR-0001 / ADR-0004, but had **five block-tier contract contradictions** that an executor following the draft literally would have hit on first import. Three are recurrences of bugs already caught by sibling validations (S3-01, S3-02, S3-03); one (the phantom hello-node fixture) is new and load-bearing for green.

1. **(consistency — block) `DockerInDockerClient(allowlist=allowlist)` is the constructor S3-02 HARDENED explicitly removed.** All four draft tests call `DockerInDockerClient(allowlist=allowlist)`; S3-02 `_validation/S3-02-did-client-sdk-core.md` finding #1 dropped the `allowlist` parameter entirely (env filtering happens upstream in `SandboxSpecBuilder.for_gate`, baked into `spec.env` and pinned into `sandbox_spec_hash`). The hardened surface is `__init__(self, *, docker_url: str | None = None, docker_factory: Callable[[], DockerClient] = docker.from_env)`. The draft would `TypeError` on instantiation. Resolution: AC-CLIENT-CTOR-1 pins the constructor signature; AC-CLIENT-CTOR-2 forbids any `allowlist=` kwarg anywhere in `tests/integration/sandbox/`. The TDD plan code blocks are rewritten.
2. **(consistency — block) `stage6_spec_builder.for_gate_test_override(...)` does not exist anywhere on `SandboxSpecBuilder`.** S3-01 HARDENED AC-API-2 pins `set(__all__) == {"SandboxSpecBuilder"}` and AC-FG-1 pins the **only** public method as `for_gate(self, gate: Gate, attempt: AttemptNumber, ctx: GateContext) -> SandboxSpec`. The draft's `for_gate_test_override(gate_id, attempt, worktree, cmd_override, memory_limit_mib?, time_budget_seconds?, network?, egress_allowlist?)` is a phantom method and the proposed overrides bypass the catalog→SandboxSpec translation S3-01/S3-05 own. Worse, the draft contradicts itself in Green: "Add `for_gate_test_override(...)` test helper on `SandboxSpecBuilder`" then "keep in `tests/sandbox/conftest.py`, not in the production class." Resolution: **construct `SandboxSpec` directly via Pydantic for these four integration tests** — the unit under test is `DockerInDockerClient.execute(spec)`, not `SandboxSpecBuilder`. Spec-builder coverage is owned by S3-01's unit + golden suite (AC-9 of this story already pulls that in). AC-NO-PHANTOM-1..AC-NO-PHANTOM-3 forbid the phantom helper.
3. **(consistency — block) `tests/fixtures/repos/hello-node/` does not exist in the repo today.** Story claims "Phase 3/4 carryover — verify presence (test should `pytest.skip` with clear message if missing)" and Out-of-scope says "Do not regenerate the fixture in this story." Reality (`ls tests/fixtures/repos/` shows only `express-cve-2024-21501` and `malicious-npmrc`): the fixture was never shipped. With the draft, all four tests skip — the suite is a no-op and Goal 5 + Goal 10 silently fail to land. The four tests in *this* story do NOT actually require `package.json` / `node_modules` (they exercise `npm --version`, OOM via `node -e`, `sleep`, and `curl` — none touch the project shape). Resolution: **AC-FIXTURE-1 has this story scaffold a minimal `tests/fixtures/repos/hello-node/` (single `package.json` with `{"name":"hello-node","version":"0.0.0","private":true}`, plus a `README.md` flagging it as the Phase-5 integration-only minimal placeholder)**; the rich `npm ci` / 120-unit-test variant is deferred to whichever Phase-3/4/5-S4-* story actually exercises `npm ci`. Fail-loud (Rule 12) over silent-skip.
4. **(consistency — harden) Base-image binary availability is unverified.** Draft AC-2 specs `python3 -c 'x=bytearray(10**9)'` for OOM, and Notes hedge with "Chainguard `cgr.dev/chainguard/node` typically has python3 — if not, use `node -e "Buffer.alloc(1e9)"`." This is exactly the silent-failure Rule 12 forbids: an OOM-detection regression would be misread as a "python3: not found" environment issue. Resolution: **switch to `node -e "Buffer.alloc(1e9)"`** unconditionally — Node's `Buffer.alloc` is the canonical OOM-inducer and the base image guarantees `node` (it's the Node base image). AC-OOM-CMD-1 pins this; AC-OOM-CMD-2 forbids `python3` from any integration cmd in this suite.
5. **(coverage + test-quality — block) Egress test's structural assertion can be passively satisfied without actually wiring the iptables chokepoint.** Draft asserts `"blocked" in stdout` from `(curl ...) || echo blocked` — but an implementation where `network_policy.apply()` was never called would still produce `blocked` in stdout on any runner where github.com is not reachable for unrelated reasons (corporate firewall, mid-test internet outage, host routing). And a curl that *hangs* on a packet-drop until pytest timeout would also "look like" a block. Resolution: AC-EGRESS-EVIDENCE-1..AC-EGRESS-EVIDENCE-4 — (a) use `curl --max-time 5 --connect-timeout 3` so a drop fails *fast* (not hangs), (b) assert curl exit code is `28` (operation timed out — the canonical packet-drop signature) by capturing the rc via `echo "rc=$?"`, (c) capture the run's structlog events and assert `EVENT_SANDBOX_DID_NETWORK_POLICY_APPLIED` was emitted for *both* runs with the same `AppliedPolicy.rules` (proves the chokepoint actually ran — closes ADR-0001 escape hatch), (d) cross-check `run_blocked.exit_code == 0` (the OR-chain succeeded), `run_ok.exit_code == 0`, and `run_ok.run_id != run_blocked.run_id`.
6. **(coverage — harden) `gate_isolation_class` Literal-narrowing not pinned.** Draft asserts `== "shared_kernel"` but `Literal["shared_kernel", "microvm"]` admits drift. Add AC-RUN-CONTRACT-1 that asserts `typing.get_type_hints(SandboxRun)['gate_isolation_class']` is exactly the two-member Literal (defends against ADR-0004 silent widening).
7. **(test-quality — harden) `timed_out` test over-asserts `exit_code == 137`.** SIGKILL via Docker yields 137, but the cleaner contract is `SandboxRun.timed_out=True` regardless of the underlying exit code (arch §Edge case 3). Resolution: AC-TIMEOUT-1 asserts `timed_out is True` AND `killed_by_oom is False`; AC-TIMEOUT-2 records (but does not gate on) the observed `exit_code` for the perf row. Drop the 137-literal assertion (it's a Docker-implementation detail that may change between Engine versions).
8. **(test-quality — harden) Happy-path version-regex matches too broadly.** Draft's `re.search(r"\d+\.\d+\.\d+", stdout)` would pass on any incidental semver-looking string in interleaved logs. Tighten to `re.fullmatch(r"\d+\.\d+\.\d+\n?", stdout)` on the trimmed first line of stdout. AC-HAPPY-1.
9. **(coverage — harden) Cleanup + concurrency.** Tests can leak Docker containers on failure; pytest-xdist parallel runs would race on `iptables` rules in `network_policy.py` (shared kernel state). Resolution: AC-CLEANUP-1 — module-scoped finalizer asserts no containers carry the suite's label (`label="phase05.integration.<test_id>"`); AC-CONCURRENCY-1 — `pytest.mark.serial` (or `-p no:xdist` for the integration dir) ensures one-test-at-a-time execution; the iptables rules race is fatal if violated.
10. **(coverage — harden) Skip-path verification.** Draft AC-7 says the suite skips cleanly when Docker is unreachable but no AC verifies the skip actually fires. Resolution: AC-SKIP-1 — a unit-level test (`tests/sandbox/test_integration_skip_predicate.py`) monkeypatches `docker.from_env` to raise `docker.errors.DockerException` and asserts `docker_available` fixture skips (not errors); paired with `pytestmark` resolution evidence in the report.
11. **(consistency — harden) `python -m codegenie.cli.sandbox health` is owned by S8-01.** Draft AC-CLI-SMOKE inlines a CLI invocation but `src/codegenie/cli/sandbox.py` doesn't exist yet (S8-01 territory). Resolution: AC-CLI-SMOKE-1 demotes this to a *manual* check recorded in `_attempts/S3-07.md` (not gated on green CI); the structured `SandboxHealthProbe.run()` call from S3-06 is the canonical test-level smoke instead. The Sandbox CLI smoke is properly an S8-01 acceptance criterion.
12. **(test-quality — harden) Perf row writer untested.** Draft AC-PERF says "wall-clock duration recorded in `.codegenie/perf/`" but no test verifies the file shape. A buggy writer (wrong keys, missing file, wrong scenario tag) ships green. Resolution: AC-PERF-1 asserts the JSONL file exists, parses, and the row has `{"scenario": "hello-node-npm-version", "duration_ms": int, "backend": "docker_in_docker"}` keys (closed set).
13. **(patterns — harden, Open/Closed) Parametrize the four integration tests over a scenario table.** The four tests have nearly identical setup → execute → assert shape. A scenario-table-driven parametrization (`@pytest.mark.parametrize("scenario", _SCENARIOS, ids=lambda s: s.id)`) makes adding a fifth scenario (`copy_out`, `image_pull`, `large_memory`, future task-class variants) a one-row diff (extension by addition; Rule 2 satisfied at four-now-fifth-soon threshold). The unique-shape outliers (`test_did_oom`'s OOM assertion, `test_did_egress_blocked`'s two-run comparison) stay as standalone tests; the happy-path + timeout fold cleanly. AC-PATTERN-1.
14. **(patterns — harden, dependency-injection uniformity) `docker_available` fixture should consume the `docker_factory` port S3-02 ships.** Rather than calling `docker.from_env().ping()` directly, the fixture takes `docker_factory=docker.from_env` (overridable for the skip-predicate test). Aligns with the production DI port; closes the seam Rule 8 calls out. AC-PATTERN-2.

The original goal (four real-daemon integration tests + spec-builder reuse + perf-row emission) is intact and unchanged. All changes harden ACs and rewrite the TDD-plan code blocks to the post-S3-02/S3-03 surface; no edits to scope or goal.

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

### A. Fixture preconditions (closes the phantom-dependency gap)

- [ ] **AC-FIXTURE-1** `tests/fixtures/repos/hello-node/` exists at the end of this story. Minimal shape sufficient for the four scenarios below: `package.json` containing `{"name":"hello-node","version":"0.0.0","private":true}` + a `README.md` whose first line is `Phase-5 integration-only placeholder (S3-07). Richer shape (npm ci, 120 unit tests) deferred to whichever Step 4 story exercises npm ci.` No `node_modules/` is shipped.
- [ ] **AC-FIXTURE-2** `tests/integration/sandbox/test_fixture_present.py` — a unit-level (no-docker) test asserts the fixture path exists and the `package.json` parses to the canonical body above. Runs in every CI lane, including the `no-docker` lane.

### B. Client / spec construction surface (closes the contract-drift gaps)

- [ ] **AC-CLIENT-CTOR-1** Every `DockerInDockerClient(...)` callsite in `tests/integration/sandbox/**` constructs the client via the S3-02 HARDENED signature — `DockerInDockerClient(docker_url=None, docker_factory=docker.from_env)` — or accepts the bare default-argument form. `grep -nE "DockerInDockerClient\\(.*allowlist" tests/integration/sandbox/` returns zero matches.
- [ ] **AC-CLIENT-CTOR-2** A unit-level guard test (`tests/sandbox/test_no_allowlist_kwarg_in_integration.py`, no-docker) asserts the grep above is empty — fail-loud regression for any future contributor who reintroduces the dropped kwarg.
- [ ] **AC-NO-PHANTOM-1** No `SandboxSpecBuilder` method other than `for_gate(gate, attempt, ctx)` is invoked in `tests/integration/sandbox/**`. `grep -nE "for_gate_test_override|for_gate_override|_override\\(" tests/integration/sandbox/` returns zero matches.
- [ ] **AC-NO-PHANTOM-2** Each of the four integration tests constructs its `SandboxSpec` directly via Pydantic (`SandboxSpec(base_image=..., copy_in=[...], env=..., cmd=[...], network=..., egress_allowlist=[...], enable_trace=False, time_budget_seconds=..., memory_limit_mib=..., pids_limit=..., copy_out=[...], label="phase05.integration.<test_id>", sandbox_spec_hash="<computed>")`). The `sandbox_spec_hash` is computed via `SandboxSpecBuilder._canonical_blake3` (the pure helper S3-01 exposes for reuse) over the same canonical-JSON shape — NOT via a private API on the builder instance.
- [ ] **AC-NO-PHANTOM-3** No edits to `src/codegenie/sandbox/spec_builder.py` or any production `sandbox/` / `gates/` module land in this story. Integration tests are pure consumers.

### C. Scenario tests (parametrized for extensibility)

- [ ] **AC-SCENARIO-TABLE-1** A module-level `_SCENARIOS: Final[tuple[Scenario, ...]]` table in `tests/integration/sandbox/_scenarios.py` carries one row per scenario with fields `(id, cmd, network, egress_allowlist, memory_limit_mib, time_budget_seconds, expected_predicate)`. Adding a new scenario (e.g., `copy_out`, `image_pull`) is a one-row edit — no test-body changes. The happy-path and timeout tests parametrize off this table; OOM and egress tests live standalone because their assertions are unique-shape.

- [ ] **AC-HAPPY-1** `tests/integration/sandbox/test_did_hello_node.py` — boots DinD, executes `cmd=["npm","--version"]` with `memory_limit_mib=512`, `time_budget_seconds=60`, `network="none"`, `egress_allowlist=[]`, `copy_in=[CopyInEntry(src=hello_node_repo, dst=PurePosixPath("/work"), mode="ro")]`. Asserts `run.exit_code == 0`, `run.backend == "docker_in_docker"`, `run.gate_isolation_class == "shared_kernel"`, `run.timed_out is False`, `run.killed_by_oom is False`. Reads `(run.logs_dir / "stdout.log").read_text().strip()` and asserts `re.fullmatch(r"\d+\.\d+\.\d+", stripped) is not None` (NOT `re.search` — version line is the ONLY stdout content).

- [ ] **AC-OOM-1** `tests/integration/sandbox/test_did_oom.py` — `cmd=["node","-e","Buffer.alloc(1e9)"]`, `memory_limit_mib=16`, `time_budget_seconds=30`. Asserts `run.killed_by_oom is True`, `run.timed_out is False`.
- [ ] **AC-OOM-CMD-1** Test cmd is **node-based** (`Buffer.alloc(1e9)`), NOT `python3 -c '...'`. Rationale: the Chainguard `cgr.dev/chainguard/node` base image guarantees `node`; `python3` is best-effort and a missing-binary failure would be misread as an OOM-detection regression (Rule 12 fail-loud).
- [ ] **AC-OOM-CMD-2** `grep -n "python3" tests/integration/sandbox/` returns zero matches (defends against accidental reintroduction).

- [ ] **AC-TIMEOUT-1** `tests/integration/sandbox/test_did_timeout.py` — `cmd=["sleep","30"]`, `time_budget_seconds=1`. Asserts `run.timed_out is True`, `run.killed_by_oom is False`. Does NOT assert any specific `exit_code` literal (Docker-Engine-version drift; the contract is the boolean flag).
- [ ] **AC-TIMEOUT-2** The observed `run.exit_code` is appended to the perf JSONL row (as `timeout_exit_code`) for trend observation but is not gated on.

- [ ] **AC-EGRESS-1** `tests/integration/sandbox/test_did_egress_blocked.py` runs two `SandboxSpec`s with identical `network="scoped"` + `egress_allowlist=["registry.npmjs.org"]`. Run-OK cmd: `["sh","-c","curl --max-time 5 --connect-timeout 3 -sfo /dev/null https://registry.npmjs.org/ && echo ok"]`; Run-Blocked cmd: `["sh","-c","curl --max-time 5 --connect-timeout 3 -sfo /dev/null https://github.com/; echo rc=$?"]`.
- [ ] **AC-EGRESS-EVIDENCE-1** `run_ok.exit_code == 0` and stdout `== "ok\n"`; `"rc=" in run_blocked.logs_dir/"stdout.log".read_text()` AND the captured rc value is `28` (curl `CURLE_OPERATION_TIMEDOUT` — the canonical packet-drop signature). Treat rc `7` (`CURLE_COULDNT_CONNECT`) as an acceptable variant for runners where DNS still resolves but routing is dropped — pin the accepted set as a module-level `_ACCEPTABLE_DROP_RCS: Final[frozenset[int]] = frozenset({28, 7})`.
- [ ] **AC-EGRESS-EVIDENCE-2** Both runs are scoped to the same `egress_allowlist`; the test captures structlog events from each `execute()` invocation (via the `pytest.fixture` `caplog_events` helper that reads `tests/conftest.py`'s structlog capture configuration — already canonical in this repo's Phase 1+ tests) and asserts `EVENT_SANDBOX_DID_NETWORK_POLICY_APPLIED` appears EXACTLY ONCE per run. Defends ADR-0001 chokepoint escape (an impl that skipped `network_policy.apply()` entirely would silently pass the stdout check on a runner where github.com is unreachable for unrelated reasons).
- [ ] **AC-EGRESS-EVIDENCE-3** `run_ok.run_id != run_blocked.run_id` (defends against a fake client that returns the same hardcoded `SandboxRun`).
- [ ] **AC-EGRESS-EVIDENCE-4** `--max-time 5 --connect-timeout 3` on every curl invocation: a packet-drop scenario must fail in ≤ 5 seconds, NOT hang until pytest's per-test timeout (≥ 60 s) — otherwise the test would still pass on a buggy revert that left an old DROP rule in place, just very slowly.

### D. Contract-level guard tests (no-docker, run in every lane)

- [ ] **AC-RUN-CONTRACT-1** `tests/sandbox/test_sandbox_run_isolation_class_literal.py` (no-docker) asserts `typing.get_args(typing.get_type_hints(SandboxRun)['gate_isolation_class'])` is exactly `("shared_kernel", "microvm")` — defends ADR-0004's two-value union from silent widening.
- [ ] **AC-RUN-CONTRACT-2** Same file asserts `typing.get_args(typing.get_type_hints(SandboxRun)['backend'])` is exactly `("docker_in_docker", "firecracker")`.

### E. Companion tests must remain green

- [ ] **AC-COMPANION-1** Every spec-builder golden + property test S3-01 ships (whatever the canonical filename pattern is — `tests/sandbox/test_spec_builder_golden*.py` and `tests/sandbox/test_spec_builder_property*.py`) runs green in this story's CI matrix. Listed here so the executor verifies the integration changes do not regress the unit-level spec contract.
- [ ] **AC-COMPANION-2** The four pre-existing fence tests stay green at end-of-story: `tests/schema/test_no_subprocess_outside_build_chokepoint.py`, `tests/schema/test_no_llm_imports_in_sandbox.py`, `tests/schema/test_env_allowlist_no_credentials.py`, `tests/schema/test_digests_yaml.py`.

### F. Skip / cleanup / concurrency hardening

- [ ] **AC-SKIP-1** `tests/sandbox/test_integration_skip_predicate.py` (no-docker) monkeypatches `docker.from_env` to raise `docker.errors.DockerException("daemon unreachable")`; instantiates the `docker_available` fixture; asserts the fixture calls `pytest.skip(...)` with a message matching `r"Docker daemon unavailable.*"` — NOT raises, NOT errors. Verifies the skip path is wired.
- [ ] **AC-CLEANUP-1** Every integration test carries a module-scoped finalizer that runs `docker.from_env().containers.list(all=True, filters={"label": f"phase05.integration.{test_id}"})` after the test, asserts the list is empty, and force-removes any leaked container with that label. Catches both leak regressions and finalizer ordering bugs.
- [ ] **AC-CONCURRENCY-1** `tests/integration/sandbox/conftest.py` declares `collect_ignore_glob` or a module-level `pytest_collection_modifyitems` hook that marks every test in the directory with `pytest.mark.serial`; the project's `pyproject.toml` `[tool.pytest.ini_options]` `addopts` honors `-p no:xdist` for the `integration/sandbox/` path (or the suite carries explicit `pytestmark = [pytest.mark.integration, pytest.mark.requires_docker, pytest.mark.serial]`). Rationale: `iptables` rules in `sandbox/did/network_policy.py` are global to the (Docker-Desktop or host) Linux kernel — parallel runs race and produce flaky drops.
- [ ] **AC-CONCURRENCY-2** The CI matrix `pytest` invocation for the integration lane includes `-p no:xdist` (or equivalent); the recipe is captured in the `Makefile` under a new `test-integration-sandbox` target.

### G. Per-test markers + invocation

- [ ] **AC-MARKERS-1** All four integration tests carry `pytestmark = [pytest.mark.integration, pytest.mark.requires_docker, pytest.mark.serial]`; missing-Docker invocations report SKIPPED (not FAILED). Markers registered in `pyproject.toml § [tool.pytest.ini_options] markers` if not already.

### H. Perf row contract

- [ ] **AC-PERF-1** After `test_did_hello_node`, a single JSONL line lands in `.codegenie/perf/<YYYY-MM-DD>.jsonl` with exactly the keys `{"scenario": "hello-node-npm-version", "duration_ms": int, "backend": "docker_in_docker", "isolation_class": "shared_kernel", "timeout_exit_code": int | None, "recorded_at": ISO-8601 str}`. Closed-set keys. `tests/sandbox/test_perf_row_writer.py` (no-docker, uses a fake clock + a fake `SandboxRun`) asserts the writer produces a line with this exact shape against a parametrized input grid.

### I. Operator smoke (manual; recorded, not CI-gated)

- [ ] **AC-CLI-SMOKE-1** A direct `SandboxHealthProbe.run(...)` invocation (from S3-06 HARDENED) prints `reachable=True` on a healthy Docker Desktop and structured reasons on a stopped daemon. Manual verification recorded in `_attempts/S3-07.md`. The full `codegenie sandbox health` CLI surface is owned by S8-01 — explicitly NOT exercised here.

### J. Patterns + DI uniformity (Open/Closed + Hexagonal-port consistency)

- [ ] **AC-PATTERN-1** `tests/integration/sandbox/_scenarios.py` is the SOLE table parametrizing new scenarios; adding a fifth scenario to the suite is a one-row diff there (zero changes to existing test files). AST-walked by `tests/sandbox/test_integration_scenario_extensibility.py` (no-docker) which asserts the scenario file has a module-level `_SCENARIOS: Final[tuple[Scenario, ...]]` and that `test_did_hello_node.py` + `test_did_timeout.py` reference it via import.
- [ ] **AC-PATTERN-2** `docker_available` fixture takes `docker_factory: Callable[[], DockerClient] = docker.from_env` as its single argument (overridable in `AC-SKIP-1` via `monkeypatch`/fixture-override) — mirrors S3-02 HARDENED's `DockerInDockerClient` DI port; one consistent seam across production and test.

### K. Green-gate

- [ ] **AC-GREEN-1** TDD plan's red test exists, is committed, and is green.
- [ ] **AC-GREEN-2** `ruff check`, `ruff format --check`, `mypy --strict src/`, `pytest -m "integration and requires_docker"` pass on macOS Docker Desktop and on Linux CI (the integration lane). `pytest` runs serially in this lane.

## Implementation outline

1. Scaffold the fixture (AC-FIXTURE-1):
   - Create `tests/fixtures/repos/hello-node/package.json` with body `{"name":"hello-node","version":"0.0.0","private":true}\n`.
   - Create `tests/fixtures/repos/hello-node/README.md` whose first line documents it as the Phase-5 integration-only placeholder.
2. Create `tests/integration/sandbox/_scenarios.py` (AC-SCENARIO-TABLE-1, AC-PATTERN-1):
   - Define a `Scenario` frozen dataclass + `_SCENARIOS: Final[tuple[Scenario, ...]]`.
   - One row each for `hello-node-npm-version` (happy) and `timeout-sleep-30`. OOM and egress live as standalone tests (their assertions are unique-shape).
3. Create `tests/integration/sandbox/conftest.py`:
   - Session-scoped fixture `docker_available(docker_factory=docker.from_env)` that calls `docker_factory().ping()`; failure → `pytest.skip("Docker daemon unavailable")` (AC-SKIP-1 verifies the predicate fires).
   - Fixture `hello_node_repo` returning `Path("tests/fixtures/repos/hello-node")`; asserts the path + `package.json` shape exist (does NOT skip — AC-FIXTURE-2 guarantees they exist).
   - Fixture `did_client` returning `DockerInDockerClient(docker_factory=docker.from_env)` — bare default-argument form, no `allowlist=` kwarg (AC-CLIENT-CTOR-1, AC-CLIENT-CTOR-2).
   - Module-scoped finalizer per AC-CLEANUP-1 that sweeps any container labeled `phase05.integration.*`.
   - `pytest_collection_modifyitems` hook to apply `pytest.mark.serial` to every test in this directory (AC-CONCURRENCY-1).
4. `test_did_hello_node.py` (parametrized off `_SCENARIOS` for the happy row):
   - Construct `SandboxSpec` directly via Pydantic (AC-NO-PHANTOM-2), computing `sandbox_spec_hash` via `SandboxSpecBuilder._canonical_blake3` (the pure helper).
   - Execute via `did_client.execute(spec)`; assert per AC-HAPPY-1 + AC-RUN-CONTRACT-1/2.
   - After the assertion, append the perf JSONL row (AC-PERF-1) via the writer module shipped alongside this story.
5. `test_did_oom.py`: same construction pattern; `cmd=["node","-e","Buffer.alloc(1e9)"]` (AC-OOM-CMD-1), `memory_limit_mib=16`. Assert per AC-OOM-1.
6. `test_did_timeout.py` (parametrized off `_SCENARIOS` for the timeout row): `cmd=["sleep","30"]`, `time_budget_seconds=1`. Assert per AC-TIMEOUT-1; record `run.exit_code` into the perf row (AC-TIMEOUT-2).
7. `test_did_egress_blocked.py` (standalone — two-run shape):
   - Two `SandboxSpec`s with identical `network="scoped"` + `egress_allowlist=["registry.npmjs.org"]`. Cmd-OK: `["sh","-c","curl --max-time 5 --connect-timeout 3 -sfo /dev/null https://registry.npmjs.org/ && echo ok"]`; Cmd-Blocked: `["sh","-c","curl --max-time 5 --connect-timeout 3 -sfo /dev/null https://github.com/; echo rc=$?"]`.
   - Capture structlog events from each `execute()` via the repo's canonical `caplog_events` fixture; assert per AC-EGRESS-EVIDENCE-1..-4 (single `EVENT_SANDBOX_DID_NETWORK_POLICY_APPLIED` event per run; rc ∈ `{28, 7}`; distinct `run_id`s).
8. Land contract-guard tests (no-docker) per AC-RUN-CONTRACT-1/2, AC-SKIP-1, AC-CLIENT-CTOR-2, AC-NO-PHANTOM-1 grep guards, AC-PERF-1 writer test.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/integration/sandbox/test_did_hello_node.py` (the smallest of the four — start here, then add the others).

```python
# tests/integration/sandbox/_scenarios.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Final, Literal

@dataclass(frozen=True)
class Scenario:
    id: str
    cmd: tuple[str, ...]
    network: Literal["none", "scoped"]
    egress_allowlist: tuple[str, ...]
    memory_limit_mib: int
    time_budget_seconds: int

_SCENARIOS: Final[tuple[Scenario, ...]] = (
    Scenario(
        id="hello-node-npm-version",
        cmd=("npm", "--version"),
        network="none",
        egress_allowlist=(),
        memory_limit_mib=512,
        time_budget_seconds=60,
    ),
    Scenario(
        id="timeout-sleep-30",
        cmd=("sleep", "30"),
        network="none",
        egress_allowlist=(),
        memory_limit_mib=128,
        time_budget_seconds=1,
    ),
)
```

```python
# tests/integration/sandbox/test_did_hello_node.py
"""The first real-daemon assertion that the entire stack composes.
Catches: SDK mis-config, missing chokepoints, env filter bypass, drift between
spec_builder's canonical hash and what actually runs."""

from __future__ import annotations
import re
from pathlib import PurePosixPath

import pytest

from codegenie.sandbox.contract import CopyInEntry, SandboxSpec
from codegenie.sandbox.spec_builder import _canonical_blake3  # pure helper from S3-01
from tests.integration.sandbox._scenarios import _SCENARIOS

pytestmark = [pytest.mark.integration, pytest.mark.requires_docker, pytest.mark.serial]

_HAPPY = next(s for s in _SCENARIOS if s.id == "hello-node-npm-version")


def _build_spec(*, hello_node_repo, scenario) -> SandboxSpec:
    """AC-NO-PHANTOM-2 — direct Pydantic construction; sandbox_spec_hash via the
    pure helper S3-01 exposes for reuse. No SandboxSpecBuilder method is called."""
    partial = {
        "base_image": "cgr.dev/chainguard/node@sha256:<pinned-from-tools/digests.yaml>",
        "copy_in": [CopyInEntry(src=hello_node_repo, dst=PurePosixPath("/work"), mode="ro")],
        "env": {"PATH": "/usr/local/bin:/usr/bin:/bin", "NODE_ENV": "test"},
        "cmd": list(scenario.cmd),
        "network": scenario.network,
        "egress_allowlist": list(scenario.egress_allowlist),
        "enable_trace": False,
        "time_budget_seconds": scenario.time_budget_seconds,
        "memory_limit_mib": scenario.memory_limit_mib,
        "pids_limit": 1024,
        "copy_out": [],
        "label": f"phase05.integration.{scenario.id}",
        "sandbox_spec_hash": "",
    }
    return SandboxSpec(**partial).model_copy(
        update={"sandbox_spec_hash": _canonical_blake3(partial)}
    )


def test_did_hello_node_npm_version(docker_available, did_client, hello_node_repo, caplog_events, perf_writer):
    spec = _build_spec(hello_node_repo=hello_node_repo, scenario=_HAPPY)
    run = did_client.execute(spec)

    assert run.exit_code == 0, f"npm --version failed: {(run.logs_dir / 'stderr.log').read_text()!r}"
    assert run.backend == "docker_in_docker"
    assert run.gate_isolation_class == "shared_kernel"
    assert run.timed_out is False
    assert run.killed_by_oom is False

    stripped = (run.logs_dir / "stdout.log").read_text().strip()
    # AC-HAPPY-1 — fullmatch on trimmed first line; defends against accidental log interleaving.
    assert re.fullmatch(r"\d+\.\d+\.\d+", stripped) is not None, f"unexpected stdout: {stripped!r}"

    perf_writer.append(
        scenario=_HAPPY.id, duration_ms=run.duration_ms,
        backend=run.backend, isolation_class=run.gate_isolation_class,
        timeout_exit_code=None,
    )
```

```python
# tests/integration/sandbox/test_did_oom.py
from __future__ import annotations
import pytest

pytestmark = [pytest.mark.integration, pytest.mark.requires_docker, pytest.mark.serial]


def test_oom_flag_set_on_memory_exhaustion(docker_available, did_client, hello_node_repo):
    """AC-OOM-1 / AC-OOM-CMD-1 — node-based OOM cmd (Buffer.alloc) avoids the python3-missing
    misread Rule 12 forbids."""
    from tests.integration.sandbox.test_did_hello_node import _build_spec
    from tests.integration.sandbox._scenarios import Scenario

    oom = Scenario(
        id="oom-node-buffer-alloc",
        cmd=("node", "-e", "Buffer.alloc(1e9)"),
        network="none",
        egress_allowlist=(),
        memory_limit_mib=16,
        time_budget_seconds=30,
    )
    spec = _build_spec(hello_node_repo=hello_node_repo, scenario=oom)
    run = did_client.execute(spec)

    assert run.killed_by_oom is True, "OOMKilled flag missed — Edge case #4 regression"
    assert run.timed_out is False
```

```python
# tests/integration/sandbox/test_did_timeout.py
from __future__ import annotations
import pytest

pytestmark = [pytest.mark.integration, pytest.mark.requires_docker, pytest.mark.serial]


def test_timeout_flag_set_on_budget_exceeded(docker_available, did_client, hello_node_repo, perf_writer):
    """AC-TIMEOUT-1 — boolean flag is the contract; exit_code is impl-defined and observed only."""
    from tests.integration.sandbox.test_did_hello_node import _build_spec
    from tests.integration.sandbox._scenarios import _SCENARIOS

    timeout_scenario = next(s for s in _SCENARIOS if s.id == "timeout-sleep-30")
    spec = _build_spec(hello_node_repo=hello_node_repo, scenario=timeout_scenario)
    run = did_client.execute(spec)

    assert run.timed_out is True
    assert run.killed_by_oom is False
    # AC-TIMEOUT-2 — record observed exit code into perf trend without gating.
    perf_writer.append(
        scenario=timeout_scenario.id, duration_ms=run.duration_ms,
        backend=run.backend, isolation_class=run.gate_isolation_class,
        timeout_exit_code=run.exit_code,
    )
```

```python
# tests/integration/sandbox/test_did_egress_blocked.py
"""AC-EGRESS-1..AC-EGRESS-EVIDENCE-4 — the iptables chokepoint (S3-03) actually drops
github.com while permitting npmjs.org, and we PROVE the chokepoint ran by inspecting
structlog events — defends against a regression where _compute_rules produces correct
argv but apply() is never invoked."""

from __future__ import annotations
import re
from pathlib import PurePosixPath
from typing import Final

import pytest

from codegenie.sandbox.contract import CopyInEntry, SandboxSpec
from codegenie.sandbox.spec_builder import _canonical_blake3

pytestmark = [pytest.mark.integration, pytest.mark.requires_docker, pytest.mark.serial]

_ACCEPTABLE_DROP_RCS: Final[frozenset[int]] = frozenset({28, 7})
_CURL = "curl --max-time 5 --connect-timeout 3"


def _scoped_spec(*, hello_node_repo, cmd: list[str], label: str) -> SandboxSpec:
    partial = {
        "base_image": "cgr.dev/chainguard/node@sha256:<pinned-from-tools/digests.yaml>",
        "copy_in": [CopyInEntry(src=hello_node_repo, dst=PurePosixPath("/work"), mode="ro")],
        "env": {"PATH": "/usr/local/bin:/usr/bin:/bin"},
        "cmd": cmd,
        "network": "scoped",
        "egress_allowlist": ["registry.npmjs.org"],
        "enable_trace": False,
        "time_budget_seconds": 30,
        "memory_limit_mib": 256,
        "pids_limit": 1024,
        "copy_out": [],
        "label": label,
        "sandbox_spec_hash": "",
    }
    return SandboxSpec(**partial).model_copy(
        update={"sandbox_spec_hash": _canonical_blake3(partial)}
    )


def test_scoped_allows_npmjs_blocks_github(docker_available, did_client, hello_node_repo, caplog_events):
    ok = _scoped_spec(
        hello_node_repo=hello_node_repo,
        cmd=["sh", "-c", f"{_CURL} -sfo /dev/null https://registry.npmjs.org/ && echo ok"],
        label="phase05.integration.egress-ok",
    )
    blocked = _scoped_spec(
        hello_node_repo=hello_node_repo,
        cmd=["sh", "-c", f"{_CURL} -sfo /dev/null https://github.com/; echo rc=$?"],
        label="phase05.integration.egress-blocked",
    )

    with caplog_events() as events_ok:
        run_ok = did_client.execute(ok)
    with caplog_events() as events_blocked:
        run_blocked = did_client.execute(blocked)

    # AC-EGRESS-EVIDENCE-3 — distinct runs, not a fake-client constant.
    assert run_ok.run_id != run_blocked.run_id

    # AC-EGRESS-EVIDENCE-1 (positive).
    assert run_ok.exit_code == 0
    assert (run_ok.logs_dir / "stdout.log").read_text() == "ok\n"

    # AC-EGRESS-EVIDENCE-1 (negative) — extract `rc=N` and require N ∈ acceptable drop rcs.
    blocked_stdout = (run_blocked.logs_dir / "stdout.log").read_text()
    m = re.search(r"^rc=(\d+)$", blocked_stdout, re.MULTILINE)
    assert m is not None, f"no rc line in stdout: {blocked_stdout!r}"
    assert int(m.group(1)) in _ACCEPTABLE_DROP_RCS, (
        f"unexpected curl rc {m.group(1)} — expected one of {sorted(_ACCEPTABLE_DROP_RCS)} "
        f"(28=timeout, 7=couldnt_connect). A different rc suggests the chokepoint did not "
        f"actually drop the packet — it may have returned an HTTP error instead."
    )

    # AC-EGRESS-EVIDENCE-2 — prove network_policy.apply() ran for BOTH runs.
    def _applied_count(events) -> int:
        return sum(1 for e in events if e.get("event") == "EVENT_SANDBOX_DID_NETWORK_POLICY_APPLIED")

    assert _applied_count(events_ok) == 1, "network_policy.apply() not invoked for run_ok"
    assert _applied_count(events_blocked) == 1, "network_policy.apply() not invoked for run_blocked"
```

### Green — make it pass

- Verify all S3-01..S3-05 contract surfaces are landed at the versions the Validation notes pin (`DockerInDockerClient` no `allowlist` kwarg, `SandboxSpecBuilder._canonical_blake3` pure helper exported, `SandboxRun.gate_isolation_class` literal pinned).
- Run all four tests against macOS Docker Desktop locally; surface any drift via the structured error names, do not patch over by reverting to phantom helpers.
- Verify CI matrix runs the suite serially on Linux with Docker available (AC-CONCURRENCY-1/-2).
- Land the seven no-docker guard tests (AC-FIXTURE-2, AC-CLIENT-CTOR-2, AC-NO-PHANTOM-1 grep guard, AC-RUN-CONTRACT-1/2, AC-SKIP-1, AC-PERF-1 writer, AC-PATTERN-1 scenario-extensibility) — these run in every CI lane, including the no-docker lane.

### Refactor — clean up

- Consolidate fixtures into `tests/integration/sandbox/conftest.py`.
- Add structured pytest IDs so failures point at the specific scenario.
- Verify the perf JSONL line writes once per session, not per test.
- Update `_attempts/S3-07.md` with manual `codegenie sandbox health` smoke results (daemon up vs daemon stopped).

## Files to touch

| Path | Why |
|---|---|
| `tests/fixtures/repos/hello-node/package.json` | New — minimal `{"name":"hello-node","version":"0.0.0","private":true}` (AC-FIXTURE-1). |
| `tests/fixtures/repos/hello-node/README.md` | New — flags it as the Phase-5 integration-only placeholder (AC-FIXTURE-1). |
| `tests/integration/sandbox/__init__.py` | New subpackage marker. |
| `tests/integration/sandbox/_scenarios.py` | New — `_SCENARIOS` table + `Scenario` dataclass (AC-SCENARIO-TABLE-1, AC-PATTERN-1). |
| `tests/integration/sandbox/conftest.py` | New — `docker_available`, `did_client`, `hello_node_repo`, `caplog_events`, `perf_writer`, leak-sweep finalizer, serial-collection hook (AC-CLIENT-CTOR-1, AC-CLEANUP-1, AC-CONCURRENCY-1, AC-PATTERN-2). |
| `tests/integration/sandbox/test_did_hello_node.py` | New — happy path on real daemon (AC-HAPPY-1). |
| `tests/integration/sandbox/test_did_oom.py` | New — OOM flag on real daemon (AC-OOM-1). |
| `tests/integration/sandbox/test_did_timeout.py` | New — boolean-flag timeout assertion (AC-TIMEOUT-1). |
| `tests/integration/sandbox/test_did_egress_blocked.py` | New — chokepoint behavior + structlog evidence (AC-EGRESS-1..AC-EGRESS-EVIDENCE-4). |
| `tests/integration/sandbox/test_fixture_present.py` | New — no-docker fixture-shape guard (AC-FIXTURE-2). |
| `tests/sandbox/test_sandbox_run_isolation_class_literal.py` | New — `get_args` guard on the two-value Literal (AC-RUN-CONTRACT-1/2). |
| `tests/sandbox/test_no_allowlist_kwarg_in_integration.py` | New — grep guard against `DockerInDockerClient(allowlist=...)` reintroduction (AC-CLIENT-CTOR-2, AC-NO-PHANTOM-1). |
| `tests/sandbox/test_integration_skip_predicate.py` | New — monkeypatched `docker.from_env` raises → fixture calls `pytest.skip(...)` (AC-SKIP-1). |
| `tests/sandbox/test_integration_scenario_extensibility.py` | New — AST walks `_scenarios.py` for the `_SCENARIOS: Final[tuple[Scenario, ...]]` pattern + imports from the parametrized test files (AC-PATTERN-1). |
| `tests/sandbox/test_perf_row_writer.py` | New — closed-set keys + JSONL shape under fake clock/run (AC-PERF-1). |
| `src/codegenie/perf/writer.py` (or similar; align with existing path) | New (or edit) — perf JSONL writer with the closed-set keys; the canonical home for Step 7's perf-row producers. |
| `Makefile` | Edit — add `test-integration-sandbox` target invoking `pytest -m "integration and requires_docker" -p no:xdist tests/integration/sandbox/` (AC-CONCURRENCY-2). |
| `pyproject.toml` | Edit — register `integration`, `requires_docker`, `serial` markers if missing (AC-MARKERS-1). |

## Out of scope

- Six signal collectors (build/install/tests/trace/policy/cve_delta) — Step 4 owns; this story only checks `SandboxRun` shape, not signals.
- `GateRunner` retry loop — Step 5.
- Firecracker — Step 6.
- Perf regression gates — Step 7 (this story only writes the perf row).
- `codegenie sandbox health` Click CLI — S8-01.

## Notes for the implementer

- **Skip cleanly, do not fail, when Docker is unavailable.** Contributors without Docker Desktop installed must still see green local runs; only the CI matrix that ships Docker actually enforces these tests. AC-SKIP-1 verifies the skip predicate.
- **Construct `SandboxSpec` directly via Pydantic — do NOT invent `SandboxSpecBuilder.for_gate_test_override`.** S3-01 HARDENED's public surface is `for_gate(gate, attempt, ctx)` only. The integration tests' unit under test is `DockerInDockerClient.execute(spec)`, not the spec builder — coverage of the builder is owned by S3-01's golden/property suites which run alongside (AC-COMPANION-1).
- **`DockerInDockerClient` constructor has NO `allowlist` parameter** — S3-02 HARDENED dropped it. Env filtering happens upstream in `SandboxSpecBuilder.for_gate` and is baked into `spec.env` + pinned into `sandbox_spec_hash`. If you find yourself wanting to pass `allowlist=`, stop and re-read S3-02 `_validation/`.
- **OOM cmd is `node -e "Buffer.alloc(1e9)"`, never `python3 -c ...`** — the Chainguard base image guarantees `node`; `python3` is best-effort and a missing-binary error would be misread as an OOM-detection regression (Rule 12 fail-loud). AC-OOM-CMD-2 grep guards against accidental reintroduction.
- **The egress test asserts EVENT_SANDBOX_DID_NETWORK_POLICY_APPLIED is emitted in BOTH runs.** Stdout-only assertions can be passively satisfied on a runner where github.com is unreachable for unrelated reasons (corporate firewall, mid-test outage) — the structlog evidence is the load-bearing assertion that the iptables chokepoint actually ran (closes ADR-0001 escape hatch). The fix for chokepoint bugs lives in S3-03; do not paper over here.
- **`--max-time 5 --connect-timeout 3` on every curl is non-negotiable.** A packet-drop must fail in ≤ 5 s, not hang until pytest's per-test budget. Hangs hide stale-revert bugs.
- **`hello-node` fixture is scaffolded by THIS story** (AC-FIXTURE-1) — minimal `package.json` only, no `node_modules`, no `npm ci`. The full 120-unit-test variant is owned by whichever Step-4 story actually exercises `npm ci` (the install/test signal collectors). Do NOT carry over a heavyweight fixture into this story.
- **Run the integration lane serially** (`-p no:xdist`). `iptables` rules in `network_policy.py` mutate global kernel state — parallel runs race and produce flaky drops. AC-CONCURRENCY-1/-2 capture this.
- **Don't disable a test to make the suite green.** If `test_did_oom` flakes on shared CI runners due to memory contention, mark with `pytest.mark.flaky(reruns=2)` and surface in `_attempts/S3-07.md`. Per CLAUDE.md Rule 12 (Fail loud).
- **macOS Docker Desktop quirk:** occasionally `container.kill(signal="SIGKILL")` returns success but `wait()` hangs. Use `wait(timeout=10)` on the second wait too and treat hang as a flake-class failure with a clear assertion message — escalate as a Risk #3 follow-up if it recurs.
- **Don't widen `SandboxRun.gate_isolation_class` silently.** AC-RUN-CONTRACT-1 pins the two-member Literal via `typing.get_args`. A new backend (e.g., gVisor in a future phase) must amend ADR-0004 and the Literal in lock-step — that's the extension-by-addition story.
- **`codegenie sandbox health` CLI is OUT of scope** (S8-01 owns the Click CLI). The structured `SandboxHealthProbe.run()` invocation from S3-06 is the test-level smoke — AC-CLI-SMOKE-1 records the manual check in `_attempts/S3-07.md` without gating green.
- After this story lands, Step 4 begins on a known-working `SandboxRun` producer. Any drift in `SandboxRun` shape introduced later breaks every collector — keep the fields locked (AC-RUN-CONTRACT-1/2 are the regression bell).
