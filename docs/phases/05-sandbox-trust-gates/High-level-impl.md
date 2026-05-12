# Phase 05 — Sandbox + Trust-Aware gates: High-level implementation plan

**Status:** Implementation plan
**Date:** 2026-05-12
**Architecture reference:** [phase-arch-design.md](phase-arch-design.md)
**ADRs:** [ADRs/](ADRs/)
**Source design:** [final-design.md](final-design.md)
**Roadmap reference:** [docs/roadmap.md](../../roadmap.md) §"Phase 5"

## Executive summary

Phase 5 lands two new top-level packages (`src/codegenie/sandbox/` and `src/codegenie/gates/`) that wrap every Phase 3 Stage 6 (Validate) call in an ephemeral sandboxed gate execution with a deterministic three-retry loop. We sequence the work contracts-first: ship the `SandboxClient` Protocol, `SandboxSpec/SandboxRun`, `ObjectiveSignals`, and the BLAKE3-chained `RetryLedger` before any backend; then the DinD backend (macOS-default) and signal collectors; then the `GateRunner` loop with `replan_hook` into Phase 4; then Firecracker as the second backend with KVM-gated CI; finish with adversarial hardening, performance regression gates, and the operator CLI. Every step adds CI gates (fence checks, static introspection, schema chokepoints) so violations of the load-bearing invariants from ADR-0008/0012/0014 fail at PR time, not at runtime.

## Order of operations

**Contracts first → foundations → vertical slice → second backend → adversarial/perf → CLI.** Rationale: the data contracts (`SandboxSpec`, `SandboxRun`, `ObjectiveSignals`, `AttemptSummary`, `RetryLedger` JSONL shape) are what every other module depends on and what Phase 6 will lift unchanged — they must be byte-stable before any implementation work can be reviewed. CI fence rules and the `extra="forbid"` introspection test land alongside the contracts so later steps cannot silently violate ADR-0008. The DinD vertical slice (Steps 3–4) is the smallest end-to-end path that demonstrates "no transform leaves the sandbox unverified" against `hello-node`; Firecracker (Step 6) is additive and KVM-gated so it never blocks the macOS dev loop. Adversarial and performance tests come after the loop is closed because they verify properties of an already-working system. The CLI lands last because it is observable surface over previously-built primitives.

## Step 1 — Scaffold packages, contracts, and CI fences

**Goal:** The two new packages exist with all data contracts, registries, and structural CI gates in place — no backend logic yet, but every invariant that protects later steps is enforced.

**Features delivered:**
- `src/codegenie/sandbox/` and `src/codegenie/gates/` packages with `__init__.py`, `errors.py`, `registry.py`.
- `sandbox/contract.py`: `SandboxClient` Protocol, `SandboxSpec`, `SandboxRun`, `SandboxHealth`, `CopyInEntry` (all `extra="forbid", frozen=True`).
- `sandbox/signals/models.py`: `ObjectiveSignals` + six sub-models + `SignalProvenance`.
- `gates/contract.py`: `Gate` ABC, `GateContext`, `GateOutcome`, `RetryPolicy`, `AttemptSummary`, `TransitionId` enum, `ReplanHook` Protocol.
- `gates/catalog/_schema.json` + empty `stage6_validate.yaml` stub validated against it.
- Decorator registries: `@register_sandbox_backend`, `@register_signal_kind`.
- `sandbox/env_allowlist.py` with static deny substrings.
- CI gates: `tests/schema/test_no_llm_imports_in_sandbox.py`, `tests/schema/test_no_subprocess_outside_build_chokepoint.py`, `tests/schema/test_objective_signals_static.py`, `tests/schema/test_env_allowlist_no_credentials.py`, `tests/schema/test_stage6_chokepoint.py`, `tests/schema/test_digests_yaml.py`.

**Done criteria:**
- [ ] `pytest tests/schema/` green (six fence/introspection tests pass with empty backends).
- [ ] `pytest tests/sandbox/test_contracts.py tests/gates/test_contracts.py` green — every model rejects unknown fields, is frozen, round-trips canonical JSON.
- [ ] `mypy --strict src/codegenie/sandbox src/codegenie/gates` clean.
- [ ] `tools/digests.yaml` has placeholder entries for `sandbox.firecracker`, `sandbox.vmlinux`, `sandbox.rootfs`, `sandbox.policy_yaml` (failing values OK; presence enforced).
- [ ] Static introspection test asserts no field reachable from `ObjectiveSignals` contains `confidence`, `llm`, `self_reported`, or `model_says`.
- [ ] Branch coverage on `sandbox/contract.py` and `gates/contract.py` ≥ 95%.

**Depends on:** Phase 0–4 packages already on disk (probe ABC, `TrustScorer`, `FallbackTier`, audit chain head file).

**Effort:** M — mechanical but volume is high; six fence tests plus six sub-models plus four Protocol/ABC contracts.

## Step 2 — Implement `RetryLedger` and audit-chain extension

**Goal:** A working append-only, BLAKE3-chained ledger that extends Phase 4's chain head and refuses to start on tamper.

**Features delivered:**
- `gates/retry_ledger.py`: `RetryLedger` with `record`, `record_pre_execute` (per Gap 1), `head`, `attempts` replay verification.
- File layout `.codegenie/remediation/<run-id>/gates/<gate_id>/attempts.jsonl` + sibling `manifest.yaml`.
- `Attempt` internal Pydantic model with `prev_hash` / `chain_hash` fields.
- Chain-head startup check reading `.codegenie/remediation/<run-id>/chain_head.bin` from Phase 4.
- `AuditChainCorrupted` error raised on init mismatch or replay mismatch.

**Done criteria:**
- [ ] `tests/gates/test_retry_ledger.py` ≥ 95% line / 90% branch.
- [ ] Property test (hypothesis): N records with identical `prev_chain_head` produce identical `head()` regardless of write timing; out-of-order `attempt_id` is rejected.
- [ ] `tests/adversarial/test_audit_chain_tamper.py` — manually editing `attempts.jsonl` causes `attempts()` to raise `AuditChainCorrupted`.
- [ ] `tests/adversarial/test_phase4_chain_head_mismatch.py` — corrupted `chain_head.bin` causes `__init__` to raise.
- [ ] `record_pre_execute` writes a `"pre_execute"` JSONL line before the matching `"attempt"` line; ordering verified by golden file.
- [ ] Each `record` fsyncs (timing test asserts ≤ 50 ms p95 on a tmpfs, real fsync on physical disk).

**Depends on:** Step 1 contracts. Phase 4 chain-head file format (read from existing Phase 4 code).

**Effort:** S — small surface, but the chain math and pre-execute marker (Gap 1) demand care.

**Risks specific to this step:** Misreading Phase 4's chain-head byte format. Mitigation: build `tests/golden/phase4_chain_head.bin` from Phase 4's own producer and compare.

## Step 3 — Implement `DockerInDockerClient` backend + `SandboxSpecBuilder` + `SandboxHealthProbe`

**Goal:** A real Docker-in-Docker backend that executes a `SandboxSpec` against `hello-node` and returns a `SandboxRun`; spec construction is YAML-driven and byte-stable.

**Features delivered:**
- `sandbox/did/client.py`: `DockerInDockerClient` implementing `SandboxClient`.
- `sandbox/did/build.py`: subprocess chokepoint for `docker buildx build`.
- `sandbox/did/run.py`, `sandbox/did/copy_out.py`: SDK-based create/cp/start/exec/inspect/remove.
- `sandbox/did/network_policy.py`: iptables chokepoint for `network=scoped` allowlist.
- `sandbox/spec_builder.py`: `SandboxSpecBuilder.for_gate(gate, attempt, ctx)` with per-attempt overrides, env-allowlist filter, `sandbox_spec_hash` (BLAKE3 of canonical JSON with sorted env keys).
- `gates/catalog/stage6_validate.yaml` + `stage6_validate_loose.yaml` populated.
- `sandbox/health/probe.py`: `SandboxHealthProbe` registered as Phase 1 probe.
- `tools/policy/sandbox-policy.yaml` (digest-pinned, codegenie-owned).
- `tests/fixtures/repos/hello-node/` (carry-forward from Phase 3/4; verify presence).

**Done criteria:**
- [ ] `tests/integration/sandbox/test_did_hello_node.py` boots DinD, executes a no-op `npm --version` SandboxSpec, verifies `SandboxRun.exit_code == 0`, `gate_isolation_class == "shared_kernel"`, `backend == "docker_in_docker"`.
- [ ] `tests/integration/sandbox/test_did_oom.py` triggers OOM via `memory_limit_mib=16`; `SandboxRun.killed_by_oom == True`.
- [ ] `tests/integration/sandbox/test_did_timeout.py` triggers SIGKILL via `time_budget_seconds=1`; `SandboxRun.timed_out == True`.
- [ ] `tests/integration/sandbox/test_did_egress_blocked.py` with `network=scoped` to `registry.npmjs.org` confirms `curl github.com` fails inside the sandbox.
- [ ] `tests/sandbox/test_spec_builder.py` golden-file checks `tests/golden/sandbox_spec_stage6_validate_attempt1.json` byte-equal.
- [ ] Property test: `sandbox_spec_hash` invariant under env-dict reordering.
- [ ] `codegenie sandbox health` (stub CLI sufficient here) reports `reachable=True` on a healthy Docker Desktop and structured reasons on daemon-down.
- [ ] `tests/schema/test_no_subprocess_outside_build_chokepoint.py` still green (chokepoint discipline preserved).

**Depends on:** Step 1 (contracts, registry, allowlist), Step 2 (ledger — health probe writes nothing but spec_builder hash is verified).

**Effort:** L — Docker SDK quirks (copy-out edge cases, OOM detection via `inspect`, strace-in-VM), golden files, network policy via iptables.

**Risks specific to this step:** Docker Desktop on macOS has known quirks with `network=none` and bind-mount permissions; strace inside the container needs `SYS_PTRACE` cap which Docker Desktop sometimes refuses. Mitigation: surface `strace SYS_PTRACE missing` as a `SandboxHealth.warnings` entry and let trace coverage degrade to soft per §Goal 11 — do not block macOS dev loop on it.

## Step 4 — Implement six signal collectors + `StrictAndGate` adapter

**Goal:** A `SandboxRun` is translated to a fully populated `ObjectiveSignals`, and `StrictAndGate.evaluate` delegates to Phase 3's `TrustScorer` to produce a `GateOutcome` equivalent to strict-AND on populated signals.

**Features delivered:**
- `sandbox/signals/build.py`, `install.py`, `tests.py`, `trace.py`, `policy.py`, `cve_delta.py` — each ≤ 60 LOC, pure functions, decorated with `@register_signal_kind`.
- Pre-patch test inventory capture (input to `collect_test_signal` — wired through `GateContext`).
- Trace baseline plumbing for `collect_trace_signal` (informational `coverage_ok` soft signal).
- `tools/policy/sandbox-policy.yaml` digest check at collector entry.
- `gates/strict_and.py`: `StrictAndGate` ~40 LOC adapter materializing `list[TrustSignal]` and calling Phase 3 `TrustScorer.score`.
- New signal kinds (`trace`, `policy`, `cve_delta`) registered against Phase 3's extension point.

**Done criteria:**
- [ ] `tests/sandbox/test_signals_*.py` — each collector ≥ 95% line; pure-function property test (same fixture → same sub-model) green.
- [ ] `tests/gates/test_strict_and.py` — for every combination of {passed, failed} × 6 signals, `StrictAndGate.evaluate(os, ctx).passed == all(s.passed for s in populated_signals)`.
- [ ] **Property: equivalence with Phase 3.** Hypothesis-driven test asserts `StrictAndGate.evaluate(os, ctx).passed == Phase3TrustScorer.score(materialized_signals).passed` for any populated combination; if Phase 3 changes, this test fails.
- [ ] `collect_policy_signal` ignores any `.codegenie/policy.yaml` inside the worktree and uses digest-pinned `tools/policy/sandbox-policy.yaml` exclusively (`tests/adversarial/test_in_repo_policy_ignored.py`).
- [ ] `collect_test_signal` reports `delta_test_count = -1` when a test file is removed by the patch (against `tests/fixtures/repos/test-removes-test/`).
- [ ] `collect_trace_signal` returns `passed=False` when a new shell invocation is observed; non-retryable per YAML.
- [ ] `GateMissingRequiredSignal` raised if any `required_signals` element is `None`.

**Depends on:** Step 3 (real `SandboxRun` artifacts to parse), Step 1 (registry).

**Effort:** M — six small collectors, but the test fixtures (`postinstall-exfil`, `test-removes-test`, trace baseline) carry real weight.

## Step 5 — Implement `GateRunner` three-retry loop + Phase 4 `replan_hook` integration

**Goal:** The full retry-1-fail / retry-2-recover loop runs end-to-end against real Phase 4 `FallbackTier.run` with structured `AttemptSummary` fence-wrapped into the prompt; Stage 6 chokepoint is enforced.

**Features delivered:**
- `gates/runner.py`: `GateRunner` with `for attempt in 1..max_attempts` loop, pre-execute marker write, replan-hook invocation on retryable failure, `failed_unrecoverable` detection (same `failing_signals` 3×), `escalate` on non-retryable.
- Additive `prior_attempts: list[AttemptSummary] = []` kwarg added to `FallbackTier.run` (Phase 4 amendment per ADR-P5-002).
- `ReplanHook` Protocol concrete implementation in the orchestrator.
- Phase 4 prompt builder consumes `prior_failure_summary` via `FenceWrapper` (reused from Phase 4) with canary-pattern check.
- Phase 3 Stage 6 chokepoint: `RemediationOrchestrator` calls `GateRunner.run` exactly once; no other module under `src/codegenie/` calls `validation.*` directly.
- `ApplyContext` extended with `prior_attempts` (Phase 3 edit per arch §Development view).

**Done criteria:**
- [ ] `tests/integration/gates/test_stage6_retry_recovers.py` — against `tests/fixtures/repos/breaking-change-cve/`, attempt 1 fails (test failure), attempt 2 passes after real Phase 4 re-plan with VCR cassette; `attempts.jsonl` has two entries with distinct `sandbox_run_id` and `patch_blake3`.
- [ ] `tests/gates/test_runner_branches.py` — every loop branch (passed / not-retryable / failed_unrecoverable / replan-and-continue) covered; ≥ 90% branch on `runner.py`.
- [ ] `tests/schema/test_stage6_chokepoint.py` — AST walk asserts only `gates/runner.py` and `RemediationOrchestrator` reach `validation.*`.
- [ ] `tests/integration/contracts/test_replan_hook_contract.py` (Gap 2) — orchestrator's concrete hook accepts `GateContext` with `prior_attempts`, invokes `FallbackTier.run`, returns a non-empty `RecipeApplication.diff`; VCR cassette captures the fenced `prior_failure_summary` in the prompt; canary pattern matcher invoked.
- [ ] `tests/gates/test_pre_execute_marker.py` (Gap 1) — `record_pre_execute` writes before `execute`; resume after marker-only state behaves per `SandboxResumeBehavior` default (re-execute).
- [ ] `tests/integration/gates/test_failed_unrecoverable.py` — three identical `failing_signals` lists → `GateOutcome.state == "failed_unrecoverable"`, CLI exit code 12 distinct from `escalate` (11).
- [ ] Zero LLM imports under `sandbox/**` and `gates/**` (fence test still green).

**Depends on:** Steps 2, 3, 4. Phase 4 `FallbackTier.run` accepts the additive kwarg.

**Effort:** L — the integration test requires fixtures, VCR cassettes, and a real Phase 4 path; the Stage 6 chokepoint may surface unexpected callers in the existing codebase.

**Risks specific to this step:** Phase 4's existing prompt builder may not yet expose a clean injection point for `prior_failure_summary`. Mitigation: ADR-P5-002 captures the contract; if injection requires deeper Phase 4 surgery, surface it in the ADR and add a `FenceWrapper.compose_prior_attempts` helper in `codegenie.llm.fence` rather than spreading edits.

## Step 6 — Implement `FirecrackerClient` backend + KVM-gated CI smoke test

**Goal:** A real Firecracker-backed `SandboxClient` runs hello-node `npm ci && npm test` on a self-hosted KVM CI runner; macOS falls back to DinD automatically with no functional regression.

**Features delivered:**
- `sandbox/firecracker/client.py`: `FirecrackerClient` implementing `SandboxClient`.
- `sandbox/firecracker/network_policy.py` (Gap 4): host-side TAP + nftables apply for `network=scoped` egress allowlist.
- `sandbox/firecracker/rootfs.md`: documented procedure for baking pinned `vmlinux` + `rootfs.ext4`.
- `tools/firecracker/<rootfs_digest>/vmlinux` + `rootfs.ext4` committed (or LFS-pointed) with digests in `tools/digests.yaml`.
- `sandbox/registry.auto_detect()`: KVM-present → Firecracker, else DinD; INFO log on fallback.
- `codegenie sandbox prepare --backend firecracker` subcommand (idempotent on identical digests).
- Single CI smoke test on a self-hosted KVM runner + weekly cron job.

**Done criteria:**
- [ ] `tests/integration/sandbox/test_firecracker_smoke.py` (KVM-only, `pytest.mark.skip_if_no_kvm`) — boots a microVM, runs `npm ci && npm test` against hello-node, completes within 300 s, `gate_isolation_class == "microvm"`, `backend == "firecracker"`.
- [ ] `tests/integration/sandbox/test_firecracker_network_policy.py` (KVM-only) — `network=scoped` to `registry.npmjs.org` permits `npm ci`, blocks `curl github.com`.
- [ ] `FirecrackerKvmMissing`, `FirecrackerBinaryMissing`, `FirecrackerRootfsMissing` raised with structured reasons; `health()` surfaces each.
- [ ] On macOS, `auto_detect()` returns DinD and logs the fallback at INFO level (`tests/sandbox/test_auto_detect.py`).
- [ ] Weekly cron in CI invokes the smoke test; failure pages the on-call owner of the KVM runner.
- [ ] `tools/digests.yaml` enforces actual binary + rootfs digests; `tests/schema/test_digests_yaml.py` upgraded from presence-only to digest-validation.
- [ ] `codegenie sandbox prepare --backend firecracker` produces byte-identical rootfs on a clean machine given the same inputs (sanity-checked, not exhaustive).

**Depends on:** Step 3 (Protocol + spec builder), Step 5 (so the smoke test exercises a real gate). One operational dependency: a provisioned self-hosted KVM runner (deferred to Phase 0 ops per Open Q6 — flagged as a blocker if not delivered).

**Effort:** L — Firecracker rootfs baking, KVM runner provisioning, nftables host policy, and CI infrastructure are each non-trivial.

**Risks specific to this step:** Self-hosted KVM runner may not be available when this step starts. Mitigation: split into 6a (FirecrackerClient + local KVM dev test on contributor laptops with KVM) and 6b (CI smoke + weekly cron) so the absence of a CI runner does not block the code merge — but the phase exit criterion requires 6b complete.

## Step 7 — Adversarial test suite + performance regression gates

**Goal:** All adversarial paths from arch §Edge cases are covered by explicit tests, and the latency budgets from §Goal 10 are enforced as CI gates.

**Features delivered:**
- `tests/adversarial/test_patch_disables_test.py`, `test_postinstall_exfil.py`, `test_prompt_injection_in_error_log.py`, `test_in_repo_policy_ignored.py` (already from Step 4), `test_audit_chain_tamper.py`, `test_phase4_chain_head_mismatch.py` (from Step 2 — verified in suite).
- `tests/adversarial/test_test_added_informational.py` — delta > 0 logged, not failed.
- Fixtures: `tests/fixtures/repos/always-fails/`, `tests/fixtures/repos/postinstall-exfil/`, `tests/fixtures/repos/test-removes-test/`.
- `tests/perf/test_gate_latency.py` — build p50 ≤ 90 s / p95 ≤ 180 s; test p50 ≤ 60 s / p95 ≤ 120 s; trace p50 ≤ 15 s / p95 ≤ 45 s on hello-node. Records to `.codegenie/perf/` for trend.
- `tests/perf/test_retry_2_budget.py` — retry-2 wall-clock ≤ 1.6× retry-1 wall-clock against retry-recovers fixture.
- `tests/sandbox/test_cost_emitter.py` (Gap 5) — `CostEmitter` writes one `SandboxCostEntry` per attempt to `.codegenie/cost/sandbox.jsonl`; byte-stable schema.
- `src/codegenie/sandbox/cost.py`: `CostEmitter` + `SandboxCostEntry` Pydantic model.
- Adversarial concurrency: `tests/integration/sandbox/test_concurrent_remediate.py` — second concurrent `codegenie remediate` on same repo exits with `RepoAlreadyInProgress` via `fcntl.flock` on `.codegenie/remediation/.lock`.

**Done criteria:**
- [ ] All adversarial tests pass; mutation-style negative checks (e.g., temporarily set `passed=True` on a TestSignal with `delta_test_count=-1` — gate must still fail because TrustScorer reads `passed`).
- [ ] Performance tests pass on the reference runner (Docker Desktop on M-series Mac, 8-core CI Linux); flake rate ≤ 1% over 50 runs.
- [ ] `tests/perf/test_retry_2_budget.py` asserts the 1.6× ratio with no cache and full re-run of all six gates.
- [ ] `CostEmitter` emits one row per attempt — Phase 13 contract sample asserted via golden file.
- [ ] Total Phase 5 coverage: ≥ 90% line / 80% branch across `sandbox/` + `gates/`; 95% / 90% on `gates/runner.py` and `sandbox/contract.py`.
- [ ] Prompt-injection adversarial fires Phase 4's `FenceWrapper` canary matcher; log replaced with `<redacted>`; audit event `prompt_injection.detected` recorded.

**Depends on:** Steps 2–6 complete (signals, runner, both backends).

**Effort:** M — high-volume but each test is small once fixtures are in place.

**Risks specific to this step:** Perf tests flaky on shared CI runners. Mitigation: run perf tests on a dedicated CI runner or `[perf]` PR label + weekly cron only; do not gate every PR on them.

## Step 8 — Operator CLI surface + end-to-end smoke

**Goal:** Operators have the inspection and housekeeping commands they need, and the full `codegenie remediate` invocation against a CVE fixture demonstrates the phase exit criteria.

**Features delivered:**
- `cli/sandbox.py` Click subcommands: `health`, `inspect <gate-run-id>`, `gc [--older-than 7d]`, `prepare [--backend firecracker]`.
- `codegenie remediate` flags: `--sandbox-backend {did,firecracker,auto}` (default `auto`), `--max-attempts-override <int>` (requires `--operator-ack`, audit-emits `gate.attempts_override`), `--allow-test-network` (widens `egress_allowlist`, leaves `trace.new_endpoints` informational).
- `tests/e2e/test_remediate_with_sandbox.py` — runs `codegenie remediate --cve <fixture-cve>` against `tests/fixtures/repos/breaking-change-cve/` end-to-end (Phase 3 stages + Phase 4 LLM via VCR + Phase 5 gates); asserts: gate passes on attempt 2, `attempts.jsonl` has 2 chained entries, exit code 0, `.codegenie/cost/sandbox.jsonl` has 2 rows, evidence bundle paths exist.
- ADRs written and committed under `docs/phases/05-sandbox-trust-gates/ADRs/`: ADR-P5-001 (Stage 6 chokepoint), -002 (FallbackTier `prior_attempts` amendment), -003 (Phase 3 signal-kind widening), -004 (`extra="forbid"` + static introspection), -005 (Phase 4 chain-head check at startup), -006 (Protocol vs ABC convention), -007 (pre-execute marker — Gap 1), -008 (LLM Judge persona deferred — Gap 3), -009 (Firecracker nftables host policy — Gap 4), -010 (`SandboxCostEntry` schema — Gap 5).

**Done criteria:**
- [ ] `codegenie sandbox health` prints structured reasons (smoke against a real Docker Desktop).
- [ ] `codegenie sandbox inspect <gate-run-id>` pretty-prints `attempts.jsonl` and verifies the BLAKE3 chain.
- [ ] `codegenie sandbox gc --older-than 7d` removes old `.codegenie/sandbox/runs/<id>/` dirs; idempotent on second call.
- [ ] `codegenie sandbox prepare --backend firecracker` is idempotent on identical digests.
- [ ] `--max-attempts-override 5` without `--operator-ack` fails with Click exit 2.
- [ ] `tests/cli/test_sandbox_cli.py` ≥ 90% line on `cli/sandbox.py`.
- [ ] E2E test passes on macOS DinD (auto-detect) AND on Linux KVM CI (Firecracker).
- [ ] All ten ADRs present under `ADRs/`, Nygard-format, status `Accepted`.
- [ ] Roadmap §"Phase 5" exit criteria checklist all marked done in `README.md`.

**Depends on:** Steps 1–7.

**Effort:** M — CLI wiring is mechanical; the E2E test and ADR write-ups are the real work.

## Exit-criteria mapping

Roadmap §"Phase 5" exit criteria:
> No transform leaves the sandbox unverified. The three-retry loop is demonstrated end-to-end with at least one case that fails on retry-1 and recovers on retry-2.

Phase-arch §Goals (the verifiable expansion of the roadmap exit criteria):

| Exit criterion (verbatim or close) | Step(s) |
|---|---|
| §Goal 1 — No transform leaves sandbox unverified; Stage 6 chokepoint | Step 5 (chokepoint test), Step 1 (`test_stage6_chokepoint.py`) |
| §Goal 2 — 3-retry loop, retry-1 fail → retry-2 recover, real Phase 4 | Step 5, Step 8 (E2E) |
| §Goal 3 — Public surface: one `SandboxClient` Protocol, one `Gate` ABC, one `RetryLedger` Pydantic family | Step 1, Step 2 |
| §Goal 4 — Two new top-level packages with fence-CI rules | Step 1 |
| §Goal 5 — macOS DinD via Docker Desktop, `gate_isolation_class: shared_kernel` | Step 3 |
| §Goal 6 — Real Firecracker (not stub), `microvm` class, KVM smoke + weekly cron | Step 6 |
| §Goal 7 — No credentials in sandbox; env allowlist | Step 1 (CI test), Step 3 (filter applied) |
| §Goal 8 — `ObjectiveSignals` `extra="forbid", frozen=True` + introspection CI test | Step 1 |
| §Goal 9 — Six signal collectors via decorator; open registry | Step 4 |
| §Goal 10 — Latency budgets on `hello-node` | Step 7 |
| §Goal 11 — Retry-2 wall-clock ≤ 1.6× retry-1 | Step 7 |
| §Goal 12 — Coverage ≥ 90/80; 95/90 on runner + contract | Steps 1–7 cumulatively; Step 8 final check |
| §Goal 13 — Zero tokens at package boundary | Step 1 (fence test), all steps |
| §Goal 14 — Audit chain extends Phase 4 head; refuses on mismatch | Step 2 |
| §Goal 15 — Operator CLI `health`/`inspect`/`gc`/`prepare` + flags | Step 8 |
| Adversarial cases (test removal, postinstall exfil, prompt injection, in-repo policy, chain tamper) | Step 7 (+ Step 2, Step 4 contributors) |
| Cost ledger emission (Gap 5) | Step 7 |
| Pre-execute marker (Gap 1) | Step 2, Step 5 |
| Replan-hook contract test (Gap 2) | Step 5 |
| Firecracker network policy (Gap 4) | Step 6 |
| ADR-P5-001 through -010 written | Step 8 |

## Implementation-level risks

1. **Phase 4 prompt-builder injection point is shallower than expected.** What goes sideways: Step 5's `replan_hook` integration test can't get `prior_failure_summary` into the actual prompt without editing Phase 4 prompt internals beyond the agreed kwarg. Signal: the contract test in Step 5 needs to peek at LLM raw bytes via VCR cassette and a regex; if the regex doesn't match, integration is broken. What to do: stop, write ADR-P5-002 amendment with the exact prompt-builder change required, and add `FenceWrapper.compose_prior_attempts` in `codegenie.llm.fence` rather than scattering edits across Phase 4.

2. **Self-hosted KVM CI runner not provisioned by the time Step 6 starts.** What goes sideways: Step 6 ships locally on a developer KVM laptop but the weekly cron smoke test cannot run; phase exit criterion §Goal 6 unmet. Signal: ops backlog ticket for the KVM runner sits unscheduled. What to do: split Step 6 into 6a (code + local KVM dev test) and 6b (CI cron); merge 6a as soon as ready; escalate 6b as a phase blocker if the runner is not delivered within one sprint of Step 6a landing.

3. **strace `SYS_PTRACE` denial on Docker Desktop for macOS contributors.** What goes sideways: trace gate consistently emits `coverage_ok=False` on macOS, contributors view it as broken, pressure mounts to either fail-fast (breaking the macOS dev loop) or remove the trace gate (weakening security). Signal: contributor PRs disable the trace gate or downgrade it. What to do: hold the line per §Goal 11 / arch tradeoffs table — `coverage_ok` is **soft** by design on macOS; `SandboxHealth.warnings` surfaces the cap; CI on Linux still enforces hard. Document this clearly in `README.md` and `codegenie sandbox health` output.

4. **`SandboxSpec.sandbox_spec_hash` becomes unstable across Python versions or `pyyaml` upgrades.** What goes sideways: golden-file `tests/golden/sandbox_spec_*.json` tests break on Python 3.12 → 3.13 upgrade or yaml roundtrip changes. Signal: CI golden diff in unrelated bump PRs. What to do: canonicalize to BLAKE3 over JSON with sorted keys produced by `json.dumps(..., sort_keys=True, separators=(",", ":"))` and pin a single canonicalizer; never go through YAML for the hash input. Add a portability test asserting hash stability across Python minor versions in CI matrix.

5. **`pytest-docker` fixture flakiness inflates retry-perf test variance.** What goes sideways: `test_retry_2_budget.py` flakes because cold image pulls take 30 s sometimes and 5 s other times, blowing the 1.6× ratio. Signal: CI flake rate on perf marker ≥ 5%. What to do: warm the base-image pull in a session-scoped fixture before the perf test starts the timer; budget tests measure post-pull only; document the "no warm pool" production reality as Phase 9 territory (§Non-goal 3).

6. **Phase 3 `TrustScorer` signal-kind extension point doesn't actually exist or is closed.** What goes sideways: Step 4's `StrictAndGate` adapter can't materialize new kinds (`trace`, `policy`, `cve_delta`) without editing Phase 3 internals. Signal: ADR-P5-003 cannot be written without describing a Phase 3 edit. What to do: confirm Phase 3 has an open registry (e.g., `@register_trust_signal_kind`) before Step 4 starts. If not, add it as a Step 4a (Phase 3 amendment) before Step 4 — keeps "extension by addition" honest.

## What's next — handoff to Phase 6

- **New artifacts on disk Phase 6 reads on resume:** `.codegenie/remediation/<run-id>/gates/<gate_id>/attempts.jsonl` (BLAKE3-chained, with `pre_execute` markers per Gap 1); per-attempt `sandbox/<sandbox_run_id>/{stdout.log,stderr.log,trace.jsonl,policy.json,sbom.json}`; extended `chain_head.bin`; `.codegenie/cost/sandbox.jsonl` (Phase 13 also reads).
- **New contracts stable for Phase 6 to lift unchanged:** `SandboxClient` Protocol, `Gate` ABC + YAML catalog, `GateContext`, `GateOutcome` (`state ∈ {passed, failed_retryable, failed_unrecoverable, escalate}` maps to LangGraph `Command(goto=...) / interrupt()`), `AttemptSummary` (Phase 6 state ledger appends), `ReplanHook` Protocol.
- **New CI gates in place:** fence on LLM imports under `sandbox/` and `gates/`; subprocess chokepoint; Stage 6 chokepoint; `ObjectiveSignals` static introspection (ADR-0008 enforced); env-allowlist credential check; digests-yaml presence + values.
- **Implicit assumptions Phase 6 can now make:** the retry loop's data shapes are the contract, not its control flow — Phase 6 re-wraps as a LangGraph subgraph without touching `RetryLedger`/`AttemptSummary`/`GateOutcome`; `Gate.evaluate` is a pure function safe to call on resume; `SandboxClient.execute` is NOT idempotent (use the pre-execute marker per Gap 1); the orchestrator process is the sole credential holder (sandbox env never sees `ANTHROPIC_API_KEY`); `extra="forbid"` plus static introspection make accidental ADR-0008 violations impossible at PR time.
- **Open questions surfaced for Phase 6 / 11 / 13:** `SandboxResumeBehavior` enum policy (Phase 6 chooses); `evidence_paths` retention (Phase 11); cost-cap interaction on retries (Phase 13); LLM Judge persona ownership (ADR-P5-008 deferral — roadmap amendment).
