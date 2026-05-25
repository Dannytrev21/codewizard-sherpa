# Story S6-05 — KVM-gated CI smoke test + weekly cron

**Step:** Step 6 — FirecrackerClient backend + KVM-gated CI smoke test
**Status:** HARDENED 2026-05-25 (sub-claim "Open Q6 closure" is BLOCKED-PARTIAL — explicitly deferred to 6b ops; see Validation notes)
**Effort:** M
**Depends on:** S1-04 (`GateContext` contract), S1-05 (`EVENT_SANDBOX_*` registry seam in `sandbox/logging.py`), S2-01 (`RetryLedger` constructor + JSONL chain semantics), S3-05 (`gates/catalog/stage6_validate.yaml`), S5-02 (`GateRunner` + `StrictAndGate` constructor surface), S6-01 (`FirecrackerClient.from_pinned_digests` factory + `_valid_spec_kwargs` test helper + `SandboxRun` run.json layout), S6-02 (`apply_policy` + `NetNamespaceConfig.teardown()` + `nft` table-name convention + populated `test_firecracker_network_policy.py` placeholder), S6-03 (`load_pinned_digests` + `--check` PR-time fence + `find_project_root()`), S6-04 (`auto_detect` reason regex; `sandbox/logging.py` constants alphabetized into sorted `__all__`).
**ADRs honored:**
- `ADR-0004` (Firecracker is the Linux/CI second backend; KVM-gated smoke + weekly cron is the contracted evidence path).
- `ADR-0009` (host-side TAP + nftables network policy — exercised by the network-policy test).
- `ADR-0001` (two-chokepoint sandbox seam — smoke exercises a real gate via `GateRunner.run`, not raw `client.execute`).
- `production/adrs/0019` (sandbox stack — this story is the evidence-generation surface).
- `production/adrs/0043` (extension by addition — no silent edits; Open Q6 deferral is loud, not a stub-closure).

## Validation notes

(2026-05-25 — `phase-story-validator` automated run.) See `_validation/S6-05-kvm-smoke-and-weekly-cron.md` for the full audit. Verdict: **HARDENED**.

- **`from_pinned_digests` is the canonical factory.** Every callsite that previously used the (removed) `FirecrackerClient.from_digests_yaml()` is migrated to `FirecrackerClient.from_pinned_digests(load_pinned_digests(digests_yaml=find_project_root()/"tools/digests.yaml"), artifacts_root=find_project_root()/"tools/firecracker", api_socket_factory=..., process_handle_factory=..., vsock_exec_port=..., clock=...)` per S6-03 HARDENED AC-FACTORY-5.
- **`SandboxSpec` phantom-field discipline inherited from S6-01 HARDENED.** `logs_dir` and `copy_out_root` are NOT on `SandboxSpec` — they live on `SandboxRun`, generated inside the client. Tests use `_valid_spec_kwargs(...)` from `tests/sandbox/test_contract_models.py`.
- **`attempts.jsonl` read shape corrected.** `backend` and `gate_isolation_class` are on `SandboxRun` (persisted at `.codegenie/sandbox/runs/<sandbox_run_id>/run.json`), NOT on `Attempt.signals`. Tests join the two files via `_helpers.py::load_sandbox_run(...)`.
- **Open Q6 is NOT closed by this story.** Closure requires the on-call rotation owner + the org-standard PagerDuty incident-create action SHA — both operational deliverables outside the autonomous-implementer's scope. The story ships the code seam; **6b ops** fills the placeholders. Arch §Risks risk-2 + High-level-impl §Step 6 already prescribe this split — the validator amplifies (does not reframe) the mitigation.
- **Workflow paths-filter completeness.** Smoke now triggers when its OWN files change (test files + workflow file + network policy + `GateRunner` + the stage6 YAML).
- **Concurrency mutex.** `concurrency: { group: firecracker-smoke, cancel-in-progress: false }` — finite self-hosted runner; cron runs are NEVER cancelled by a late PR.
- **Mutation-thinking on the network-policy test.** Three positives + two negatives (registry succeeds; google succeeds via allowlist if extended? — no, just registry; github fails; 1.1.1.1 fails) + a fourth structured-event assertion (`run.signals.network_policy == "scoped"`).
- **Perf JSONL is typed.** `FirecrackerSmokePerfRow` (Pydantic frozen, `extra="forbid"`) — anaemic-dict failure modes for downstream consumer (S7-02) are eliminated.
- **PagerDuty step pinned by SHA + correct action class.** The placeholder `pagerduty-change-events-action@v1` is wrong (that's a deployment-annotation action). 6b ops names the org's incident-create action; the story enforces SHA-pinning + `if: failure() && github.event_name == 'schedule'` literal (no `||`).
- **Marker-discipline fence.** `tests/schema/test_kvm_gated_tests_carry_marker.py` AST-walks `tests/integration/sandbox/` and asserts every `test_firecracker_*.py` carries `pytestmark = pytest.mark.skip_if_no_kvm` at module scope.
- **Queue-watcher companion workflow.** `firecracker-queue-watcher.yml` runs on `ubuntu-latest` (no KVM dep) and pages on-call after 24h of stalled queue.

## Context

Phase 5 explicitly commits to "real Firecracker, not stub" with one KVM-gated CI smoke test plus a weekly cron — both gate-keeping evidence for ADR-0019 (sandbox stack resolution) and a tripwire that catches rootfs/kernel/digest drift before it bites an operator. With the client (S6-01), network policy (S6-02), and digest-pinned artifacts (S6-03) in place, this story lands the two KVM-only integration tests, wires a self-hosted KVM runner job in CI, and stands up the weekly cron with on-call paging on failure. **Open Q6 (KVM runner operational ownership)** is *prepared* here (the code seam, the doc-block, the typed perf JSONL) and **closed by 6b ops** (PagerDuty action + SHA + secret name + rotation owner).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design — FirecrackerClient` (line 495–502) — performance envelope (`npm ci && npm test` in ≤ 300 s on hello-node).
  - `../phase-arch-design.md §Physical view` (line 314–347) — "Linux CI self-hosted KVM runner" subgraph and the `firecracker bin → KVM → microVM` boot chain.
  - `../phase-arch-design.md §Testing strategy` (line 874–930) — `pytest.mark.skip_if_no_kvm` predicate; integration band ≈ 25%.
  - `../phase-arch-design.md §Goal 6` (line 21) — verbatim: real Firecracker, microVM class, KVM smoke + weekly cron.
  - `../phase-arch-design.md §Open Q6` (line 1061) — weekly cron infra ownership; flagged blocker if not delivered.
  - `../phase-arch-design.md §Data model` (line 760–795) — `Attempt` JSONL line shape; `backend` + `gate_isolation_class` live on `SandboxRun` (lines 110–111), not on `Attempt`.
  - `../final-design.md §Risks risk-2` — "Self-hosted KVM CI runner not provisioned" mitigation: split into 6a (code + local) and 6b (cron); 6b is required for §Goal 6.
  - `../High-level-impl.md §Step 6 — Risks specific to this step` (line 178) — codifies the 6a/6b split; this story is 6a + the *seams* for 6b.
- **Phase ADRs:**
  - `../ADRs/0004-dind-default-macos-with-gate-isolation-class.md §Consequences` — "`tests/integration/sandbox/test_firecracker_smoke.py` is `pytest.mark.skip_if_no_kvm`; weekly cron job exercises it on the self-hosted runner."
  - `../ADRs/0009-firecracker-network-policy-host-side-nftables.md §Consequences` — `test_firecracker_network_policy.py` is `skip_if_no_kvm`.
  - `../ADRs/0001-two-chokepoint-sandbox-seam.md` — `GateRunner` is the only consumer of `SandboxClient`; smoke exercises a real gate.
- **Sibling HARDENED reports (load-bearing — read in full before writing):**
  - `_validation/S6-01-firecracker-client-kvm-boot.md` — `SandboxSpec` phantom fields; `_valid_spec_kwargs`; `SandboxRun` run.json layout.
  - `_validation/S6-02-firecracker-nftables-policy-gap-4.md` — nftables table-name uniqueness; `apply_policy` contract; placeholder-test population discipline.
  - `_validation/S6-03-rootfs-digests-and-prepare.md` — `from_pinned_digests` is the canonical factory; `from_digests_yaml` was REMOVED.
  - `_validation/S6-04-auto-detect-macos-fallback.md` — reason-string namespace regex; event constants in `sandbox/logging.py`.
- **Production ADRs:**
  - `../../../production/adrs/0019-sandbox-stack.md` — this is the test that generates evidence for the eventual stack resolution.
  - `../../../production/adrs/0043-extension-by-addition-means-no-silent-edits.md` — Open Q6 deferral is *loud* (not a stub-closure).
- **Source design:**
  - `../final-design.md §Synthesis ledger row "Real Firecracker (not stub)"` — KVM smoke + weekly cron is the originating commitment.
- **Existing code (from prior stories):**
  - `src/codegenie/sandbox/firecracker/client.py` (S6-01) — the client under test.
  - `src/codegenie/sandbox/firecracker/network_policy.py` (S6-02) — `apply_policy` exercised by the network-policy smoke.
  - `src/codegenie/sandbox/firecracker/prepare.py` + `src/codegenie/sandbox/firecracker/digests.py` (S6-03) — `from_pinned_digests` + `load_pinned_digests` + `find_project_root()`.
  - `src/codegenie/sandbox/logging.py` (S1-05/S6-04) — event-constant registry (alphabetized into sorted `__all__`).
  - `tests/sandbox/test_contract_models.py` (S1-02) — `_valid_spec_kwargs(**overrides)` canonical fixture helper.
  - `tests/fixtures/repos/hello-node/` (Phase 3/4 carry-forward) — the fixture both tests run against.
  - `src/codegenie/gates/runner.py` (S5-02) — `GateRunner` for the real gate-run smoke.
  - `tests/integration/sandbox/test_firecracker_network_policy.py` (S6-02 placeholder — `pytest.mark.skip_if_no_kvm` only, no internal `pytest.skip`) — populated here.
- **External docs:**
  - GitHub Actions self-hosted runners: <https://docs.github.com/en/actions/hosting-your-own-runners/managing-self-hosted-runners/about-self-hosted-runners> — `runs-on: [self-hosted, kvm]` AND-conjunction semantics.
  - Workflow `schedule` syntax: <https://docs.github.com/en/actions/using-workflows/events-that-trigger-workflows#schedule> — UTC always.
  - `concurrency:` reference: <https://docs.github.com/en/actions/using-jobs/using-concurrency>.
  - Action-pinning hygiene: <https://docs.github.com/en/actions/security-guides/security-hardening-for-github-actions#using-third-party-actions> — pin to SHA, not tag.

## Goal

Land (a) the two KVM-gated integration tests (`test_firecracker_smoke.py`, `test_firecracker_network_policy.py`), (b) the self-hosted KVM runner workflow that runs them on every PR + manual dispatch + weekly cron, (c) the typed perf-JSONL writer that S7-02 will consume, (d) the queue-watcher companion workflow that pages on stalled-runner conditions, and (e) the doc-block + placeholder seams that 6b ops fills to close Open Q6. **Out of goal:** the operational deliverables of 6b (PagerDuty action SHA, secret name, rotation-owner doc) — explicitly deferred per arch §Risks risk-2.

## Acceptance criteria

### §A — Marker registration + fence

- [ ] **AC-MARK-1** — `pytest.mark.skip_if_no_kvm` is registered exactly once in `tests/conftest.py` via `config.addinivalue_line("markers", "skip_if_no_kvm: skip unless /dev/kvm is readable+writable")` AND a `pytest_collection_modifyitems(config, items)` hook that adds `pytest.mark.skip(reason="No /dev/kvm — KVM-gated test")` when the predicate `os.path.exists("/dev/kvm") and os.access("/dev/kvm", os.R_OK | os.W_OK)` is False.
- [ ] **AC-MARK-2** — Both smoke tests use `pytestmark = pytest.mark.skip_if_no_kvm` at **module scope** (not per-function decorators).
- [ ] **AC-MARK-3** — A regression unit test in `tests/unit/test_skip_if_no_kvm_predicate.py` exercises the predicate against a `tmp_path/"kvm"` file with `os.chmod(..., 0o000)` / `0o600` to validate both branches.
- [ ] **AC-FENCE-1** — `tests/schema/test_kvm_gated_tests_carry_marker.py` AST-walks `tests/integration/sandbox/test_firecracker_*.py` and asserts every such file declares `pytestmark` at module scope containing `skip_if_no_kvm`. Planted-positive removes the marker on a tmp-copy file and asserts the fence fires.

### §B — Test client + spec construction kernel (`tests/integration/sandbox/_helpers.py`)

- [ ] **AC-CONSTRUCT-1** — `_helpers.py::kvm_smoke_client_factory() -> FirecrackerClient` is the **only** construction site for the smoke; it returns `FirecrackerClient.from_pinned_digests(load_pinned_digests(digests_yaml=find_project_root()/"tools/digests.yaml"), artifacts_root=find_project_root()/"tools/firecracker", api_socket_factory=_default_api_socket_factory(), process_handle_factory=_default_process_handle_factory(), vsock_exec_port=_default_vsock_exec_port(), clock=_default_clock())` (DI defaults resolved per S6-01 HARDENED AC-DI-1..-4).
- [ ] **AC-CONSTRUCT-2** — `_helpers.py::kvm_smoke_spec(**overrides) -> SandboxSpec` wraps `_valid_spec_kwargs(...)` from `tests/sandbox/test_contract_models.py` so the canonical S1-02 required-fields set is always satisfied. Overrides flow through; phantom fields (`logs_dir`, `copy_out_root`) raise `TypeError` at the helper boundary (defensive — caught BEFORE pydantic).
- [ ] **AC-CONSTRUCT-3** — `_helpers.py::load_sandbox_run(run_dir: Path, attempt_line: dict) -> SandboxRun` reads `run_dir / "sandbox" / attempt_line["sandbox_run_id"] / "run.json"` and parses as `SandboxRun`. Raises `FileNotFoundError` with a structured message if the run is missing.
- [ ] **AC-SPEC-1** — Every `SandboxSpec` constructed in the smoke tests goes through `kvm_smoke_spec(...)`. Direct `SandboxSpec(...)` construction in `tests/integration/sandbox/test_firecracker_*.py` is fenced by a grep test (`tests/schema/test_kvm_smoke_uses_helpers.py`).
- [ ] **AC-SPEC-2** — `kvm_smoke_spec` enforces the contract: `network in {"none", "scoped"}`; `egress_allowlist` is a `tuple` (immutable); `env` is allowlist-filtered to `{"PATH", "NODE_ENV", "NPM_CONFIG_*", "HTTPS_PROXY"}` per arch §Physical view.
- [ ] **AC-SPEC-3** — `kvm_smoke_spec` rejects `logs_dir` / `copy_out_root` overrides loudly (phantom-field defense; mirrors S6-01 AC-API-2).

### §C — `tests/integration/sandbox/test_firecracker_smoke.py`

- [ ] **AC-SMOKE-1** — File header: `from __future__ import annotations`; module docstring cites ADR-0004 + ADR-0001 + Phase-arch §Goal 6 + this story ID.
- [ ] **AC-SMOKE-2** — `pytestmark = pytest.mark.skip_if_no_kvm` at module scope (AC-MARK-2).
- [ ] **AC-SMOKE-3** — Single test `test_firecracker_runs_hello_node_in_microvm_within_budget(tmp_path)`:
  - Builds `client = kvm_smoke_client_factory()` (AC-CONSTRUCT-1).
  - Builds `gate` via the S5-02 HARDENED `Gate`/`StrictAndGate` factory (TDD plan callout — verify-before-write).
  - Builds `ledger = RetryLedger(run_dir=tmp_path/"rem", gate_id="stage6_validate", prev_chain_head=None)` (verify against S2-01 HARDENED arity).
  - Builds `ctx = GateContext(worktree=Path("tests/fixtures/repos/hello-node").resolve(), run_id=tmp_path.name)` (verify against S1-04 HARDENED arity).
  - Times `runner.run(ctx)` via `time.monotonic()`.
- [ ] **AC-SMOKE-4** — Assertion order: (1) `outcome.passed` (failure message includes `outcome.summary`); (2) `elapsed <= 300` (failure message includes `f"smoke exceeded 300 s budget: {elapsed:.1f}s; last-30 p95 = {p95:.1f}s"`).
- [ ] **AC-SMOKE-5** — JSONL parsing: `attempts = (tmp_path / "rem" / "gates" / "stage6_validate" / "attempts.jsonl").read_text().splitlines()`; `last = json.loads(attempts[-1])`. Assert `last["outcome"]["passed"] is True`.
- [ ] **AC-SMOKE-6** — `npm ci` and `npm test` exit codes 0 are observable via `last["signals"]["build"]["passed"]` and `last["signals"]["tests"]["passed"]` (or equivalent S2-01 field shape).
- [ ] **AC-RUN-LOOKUP-1** — `run = load_sandbox_run(tmp_path, last)` (AC-CONSTRUCT-3).
- [ ] **AC-RUN-LOOKUP-2** — Assert `run.backend == "firecracker"` (compares against `Literal["docker_in_docker", "firecracker"]`).
- [ ] **AC-RUN-LOOKUP-3** — Assert `run.gate_isolation_class == "microvm"` (compares against `Literal["shared_kernel", "microvm"]`).
- [ ] **AC-FAIL-PATH-1** — The two assertions in AC-SMOKE-4 fire in order so a failed test surfaces the right cause to on-call (passed-check FIRST, budget SECOND).

### §D — `tests/integration/sandbox/test_firecracker_network_policy.py` (populating S6-02 placeholder)

- [ ] **AC-NET-1** — File header: `from __future__ import annotations`; module docstring cites ADR-0009 + ADR-0001 + this story ID; preserves the S6-02 docstring naming S6-05 as the populator.
- [ ] **AC-NET-2** — `pytestmark = pytest.mark.skip_if_no_kvm` at module scope (AC-MARK-2 / S6-02 AC-INTEG-1).
- [ ] **AC-NET-3** — Single test `test_scoped_allowlist_permits_npm_blocks_other_egress(tmp_path)`:
  - `spec_npm = kvm_smoke_spec(cmd=("sh","-c","npm ci --silent --cache /tmp/empty-cache"), copy_in=(("tests/fixtures/repos/hello-node","/work"),), network="scoped", egress_allowlist=("registry.npmjs.org",), time_budget_seconds=180, memory_limit_mib=1024)`.
  - `run = client.execute(spec_npm)`.
- [ ] **AC-NET-4** — Positive probe (must succeed): `run.exit_code == 0` for the `npm ci` invocation.
- [ ] **AC-NET-5** — Negative probe 1 (must fail): `client.execute(kvm_smoke_spec(cmd=("sh","-c","curl -sf https://github.com -o /dev/null"), ..., network="scoped", egress_allowlist=("registry.npmjs.org",))).exit_code != 0`.
- [ ] **AC-NET-6** — Negative probe 2 (must fail — IP-literal egress not in allowlist): `client.execute(kvm_smoke_spec(cmd=("sh","-c","curl -sf https://1.1.1.1 -o /dev/null"), ..., network="scoped", egress_allowlist=("registry.npmjs.org",))).exit_code != 0`.
- [ ] **AC-MUT-1** — Positive probe 2 (must succeed — explicit registry hit): `client.execute(kvm_smoke_spec(cmd=("sh","-c","curl -sf https://registry.npmjs.org/ -o /dev/null"), ..., network="scoped", egress_allowlist=("registry.npmjs.org",))).exit_code == 0`. Three positives + two negatives makes the ruleset's selectivity observable; no single mutation passes.
- [ ] **AC-MUT-2** — Structured-event assertion: `run.signals.network_policy == "scoped"` (per S6-02 AC-EVT-1 — the canonical event tag). If the field is named differently in S6-02 HARDENED, use that exact name.
- [ ] **AC-MUT-3** — `~/.npm` and `/tmp/cgsbx-*` are cleared by the pre-test workflow step (AC-PREP-3) — defends `npm ci` from succeeding via cache when policy is broken.
- [ ] **AC-NFT-1** — Post-test assertion: `subprocess.check_output(["nft","list","tables","inet"]).decode()` does NOT contain `f"cgsbx_{run.run_id[:12]}"` (our specific table; per S6-02 AC-TABLE-NAME-1).
- [ ] **AC-NFT-2** — Post-test cleanup in the autouse fixture (AC-PERF-EMIT-1): `NetNamespaceConfig.teardown()` is called on the policy from each `client.execute(...)` even on failure.
- [ ] **AC-NFT-3** — Concurrency guard: AC-CONC-1's `concurrency.group` ensures no two workflow runs race on this assertion.

### §E — Workflow file `.github/workflows/firecracker-smoke.yml`

- [ ] **AC-WF-1** — Top-of-workflow doc-block (lines 1–25) per AC-DOC-1 documents: runner label `[self-hosted, kvm]` AND-semantics; PagerDuty service routing (placeholder for 6b); rotation owner (placeholder for 6b); cron rationale ("Monday 07:00 UTC — UTC always; picked to land before US/EU work hours"); the 6a/6b split with a pointer to arch §Risks risk-2.
- [ ] **AC-WF-2** — `name: firecracker-smoke`.
- [ ] **AC-WF-3** — Triggers: `pull_request` (with `paths:` per AC-PATHS-1) + `workflow_dispatch` (with `inputs.acknowledge` per AC-DISPATCH-1) + `schedule: cron: "0 7 * * 1"` (with inline `# Monday 07:00 UTC...` comment per AC-CRON-1).
- [ ] **AC-WF-4** — Job: `smoke` on `runs-on: [self-hosted, kvm]`; `timeout-minutes: 20`.
- [ ] **AC-WF-5** — `env.KVM_TEST_FILES: "tests/integration/sandbox/test_firecracker_smoke.py tests/integration/sandbox/test_firecracker_network_policy.py"` (per D-2 — single source of truth).
- [ ] **AC-WF-6** — Steps in order: (1) `actions/checkout@v4` (SHA-pinned); (2) pre-flight cache hygiene (AC-PREP-3); (3) `codegenie sandbox prepare --backend firecracker --check` (AC-PREP-1); (4) `pytest $KVM_TEST_FILES --tb=short -ra`; (5) on-failure capture (AC-HEALTH-1); (6) on-failure upload (AC-HEALTH-2); (7) on-failure-and-cron PagerDuty page (AC-PD-1).
- [ ] **AC-WF-7** — No caching across runs (`actions/cache` not used) — intentional; the test exercises cold-start. Documented in AC-WF-1's doc-block.
- [ ] **AC-WF-8** — `actions/checkout@v4` is pinned to a SHA (per supply-chain hygiene; AC-PD-1 mirrors).
- [ ] **AC-WF-9** — `actions/upload-artifact@v4` is pinned to a SHA.
- [ ] **AC-WF-10** — All step `run:` blocks use `bash -euxo pipefail` (explicit error propagation; pipeline failures don't silently pass).
- [ ] **AC-CONC-1** — `concurrency: { group: firecracker-smoke, cancel-in-progress: false }` at the workflow level. Cron runs are NEVER cancelled.
- [ ] **AC-PATHS-1** — `pull_request.paths:` enumerates: `src/codegenie/sandbox/firecracker/**`, `src/codegenie/gates/runner.py`, `src/codegenie/gates/catalog/stage6_validate.yaml`, `tools/firecracker/**`, `tools/digests.yaml`, `tests/integration/sandbox/test_firecracker_*.py`, `tests/integration/sandbox/conftest.py`, `tests/integration/sandbox/_helpers.py`, `.github/workflows/firecracker-smoke.yml`, `.github/workflows/firecracker-queue-watcher.yml`.
- [ ] **AC-YAML-CONST-1** — Test file paths exist in exactly two places (`env.KVM_TEST_FILES` and `paths:`); the marker-fence test (AC-FENCE-1) cross-validates with `tests/schema/test_kvm_gated_tests_carry_marker.py`.
- [ ] **AC-CRON-1** — Inline comment `# Monday 07:00 UTC (UTC always — GitHub Actions cron is UTC; do not interpret as local).` immediately above the `cron:` line.
- [ ] **AC-RUNNER-1** — AC-WF-1 doc-block explicitly states "AND semantics: a runner must carry BOTH labels `self-hosted` and `kvm`".
- [ ] **AC-DISPATCH-1** — `workflow_dispatch.inputs.acknowledge` required boolean (`required: true; type: boolean; description: "I understand this consumes the KVM runner"`). Ad-hoc dispatch requires explicit acknowledgement.

### §F — PagerDuty step (seam for Open Q6 closure)

- [ ] **AC-PD-1** — On-call page step has literal `if: failure() && github.event_name == 'schedule'` — `&&` not `||`; no PR failure pages on-call.
- [ ] **AC-PD-2** — `uses:` line is a SHA-pinned reference (NOT `@v1`/`@v2`); the action name is a placeholder `pagerduty/<INCIDENT-CREATE-ACTION-NAME>@<SHA>` filled by 6b ops; the workflow file lints fail-loud if the placeholder is unfilled in production (CI lint via AC-PD-TEST-1).
- [ ] **AC-PD-3** — Integration-key secret reference: `${{ secrets.PAGERDUTY_KVM_RUNNER_SERVICE_KEY }}` (matches the org's `PAGERDUTY_*_SERVICE_KEY` convention).
- [ ] **AC-PD-4** — Payload fields: `summary: "codegenie firecracker weekly smoke failed"`; `severity:` literal documented by the chosen action (filled by 6b — `error` is the typical default); `links:` array pointing at `https://github.com/${{ github.repository }}/actions/runs/${{ github.run_id }}`.
- [ ] **AC-PD-5** — Comment block above the PagerDuty step references: "6b ops PR closes Open Q6 by filling the action SHA + secret name; until then, this step is a planned no-op on PR / dispatch and a placeholder-fire on `schedule`. See `docs/phases/05-sandbox-trust-gates/stories/_validation/S6-05-kvm-smoke-and-weekly-cron.md` §Open Q6 deferral."

### §G — Pre-flight + cache hygiene

- [ ] **AC-PREP-1** — Pre-flight step: `codegenie sandbox prepare --backend firecracker --check` (read-from-disk verify; ≤ 5 s per S6-03 HARDENED AC-CHECK-MODE-1..-4). Failure with `Prepare*Error` surfaces the digest mismatch + `install_hint` to the run log; workflow fails fast.
- [ ] **AC-PREP-2** — If S6-03 has not landed `--check`, the pre-flight degrades gracefully to `blake3sum tools/digests.yaml` (mirrors the digest-only verification path; flagged in workflow comments as "pending S6-03 GREEN"). On S6-03 GREEN, AC-PREP-2 collapses into AC-PREP-1.
- [ ] **AC-ISO-1** — Pre-test cache hygiene step: `rm -rf ~/.npm /tmp/npm-cache-* /tmp/cgsbx-* /tmp/empty-cache; mkdir -p /tmp/empty-cache` — eliminates the masked-by-cache failure mode (T-5).
- [ ] **AC-ISO-2** — The hello-node fixture is read-only from the test's POV; tests use `tmp_path` for any per-run state.
- [ ] **AC-ISO-3** — `npm ci` invocations inside the microVM always pass `--cache /tmp/empty-cache` (AC-NET-3).

### §H — Health capture on failure

- [ ] **AC-HEALTH-1** — `if: failure()` step: `codegenie sandbox health > sandbox-health-${{ github.run_id }}.json` (S8-01 owns the command; this story consumes its existing scaffolded form per S6-03 + S6-01 HARDENED).
- [ ] **AC-HEALTH-2** — `if: failure()` step: `actions/upload-artifact@v4` (SHA-pinned per AC-WF-9) uploads `sandbox-health-*.json` with `name: sandbox-health-${{ github.run_id }}`.
- [ ] **AC-HEALTH-3** — The artifact name `sandbox-health-<run-id>.json` is a downstream contract (S7-02 + Phase 13 cost-ledger consume it); the story doc-block records this.

### §I — Perf JSONL writer (typed)

- [ ] **AC-PERF-EMIT-1** — Autouse fixture in `tests/integration/sandbox/conftest.py` emits one `FirecrackerSmokePerfRow` line to `.codegenie/perf/firecracker_smoke.jsonl` per smoke test, on BOTH pass and fail (the failure case is the load-bearing evidence). Implemented via `pytest.fixture(autouse=True, scope="function")` with `yield` + `try/finally`. Per-test `try/finally` blocks inside test bodies are forbidden (the fixture is the single emit site).
- [ ] **AC-PERF-MODEL-1** — `tests/integration/sandbox/_perf_row.py::FirecrackerSmokePerfRow(BaseModel, frozen=True, extra="forbid")` with fields `run_id: str`, `backend: Literal["firecracker"]`, `wall_seconds: float`, `exit_code: int`, `run_ts: datetime`, `runner_name: str`, `runner_os: str`, `kernel_release: str`, `kvm_module_version: str | None`, `event_chain: tuple[str, ...]` (the event constants emitted during the test).
- [ ] **AC-PERF-MODEL-2** — `_perf_row.py::FirecrackerSmokePerfLog` is the reader S7-02 imports. Rejects rows missing fields with `ValidationError` (no silent under-counting).
- [ ] **AC-PERF-MODEL-3** — `_helpers.py::record_perf(...)` constructs `FirecrackerSmokePerfRow` and appends `model_dump_json() + "\n"` to the JSONL file (open in `"a"` mode).
- [ ] **AC-PROV-1** — `runner_name = socket.gethostname()`; `runner_os = platform.platform()`; `kernel_release = os.uname().release`; `kvm_module_version` from `(Path("/sys/module/kvm/version").read_text().strip() if Path("/sys/module/kvm/version").exists() else None)`.
- [ ] **AC-JSONL-1** — Property: two consecutive smoke tests append exactly two valid `FirecrackerSmokePerfRow` lines. Tested by a unit test under `tests/sandbox/test_perf_row_writer.py` against a `tmp_path` JSONL.

### §J — Perf trend test (segregated from the smoke workflow)

- [ ] **AC-PERF-1** — `tests/perf/test_firecracker_smoke_p95.py` exists; `pytestmark = [pytest.mark.skip_if_no_kvm, pytest.mark.slow]`.
- [ ] **AC-PERF-2** — Reads the LAST 30 lines of `.codegenie/perf/firecracker_smoke.jsonl` via `FirecrackerSmokePerfLog` (AC-PERF-MODEL-2).
- [ ] **AC-PERF-3** — Asserts `p95(wall_seconds) <= 300` AND `p50(wall_seconds) <= 240`. On fewer than 10 rows, the test is `pytest.skip` (insufficient data — not a failure).
- [ ] **AC-PERF-4** — The 300 s hard ceiling in AC-SMOKE-4 stays as a single-sample guard (investigate-on-fail); the p95 / p50 trend in AC-PERF-3 is the *recurring* discipline that S7-02 will tighten.

### §K — Logging events

- [ ] **AC-EVT-1** — `EVENT_SANDBOX_FIRECRACKER_SMOKE_STARTED = "sandbox.firecracker.smoke.started"` added to `src/codegenie/sandbox/logging.py` alphabetized into sorted `__all__`.
- [ ] **AC-EVT-2** — `EVENT_SANDBOX_FIRECRACKER_SMOKE_COMPLETED = "sandbox.firecracker.smoke.completed"` (same).
- [ ] **AC-EVT-3** — `EVENT_SANDBOX_FIRECRACKER_SMOKE_FAILED = "sandbox.firecracker.smoke.failed"` (same). Reasons on `FAILED` carry the structured `reason: Literal[...]` per S6-01 HARDENED inheritance.

### §L — Queue-watcher companion workflow

- [ ] **AC-QUEUE-1** — `.github/workflows/firecracker-queue-watcher.yml` exists; `on: schedule: cron: "0 */6 * * *"` (every 6h); runs on `ubuntu-latest` (NO KVM dep — must run even when the KVM runner is offline).
- [ ] **AC-QUEUE-2** — Step uses `gh api repos/${{ github.repository }}/actions/workflows/firecracker-smoke.yml/runs --jq '[.workflow_runs[]|select(.status=="queued" and ((now - (.created_at|fromdateiso8601)) > 86400))]'`. Non-empty result fires the same PagerDuty action (placeholder for 6b SHA) with `summary: "codegenie firecracker-smoke queue stalled > 24h"` and `reason: "sandbox.ci.firecracker_queue_stalled"`.
- [ ] **AC-QUEUE-3** — Watcher is documented in AC-WF-1's doc-block as the queue-stall escalation path; failure-mode is "the watcher itself fails to run" → 6b ops monitors the watcher's own success rate via a quarterly review (operational deliverable, not enforced here).

### §M — Workflow YAML fence + meta-tests

- [ ] **AC-PD-TEST-1** — `tests/ci/test_firecracker_smoke_workflow.py` parses `.github/workflows/firecracker-smoke.yml` via `yaml.safe_load` and asserts: (a) `concurrency.group == "firecracker-smoke"`; (b) `concurrency.cancel-in-progress == False`; (c) the page step's `if:` is exactly `"failure() && github.event_name == 'schedule'"`; (d) `runs-on == ["self-hosted", "kvm"]`; (e) the `cron:` value is `"0 7 * * 1"`; (f) every `uses:` line matches the regex `^[a-zA-Z0-9._/-]+@[0-9a-f]{40}$` OR carries an explicit `# placeholder-for-6b` comment (PagerDuty action only); (g) `paths:` enumerates the full AC-PATHS-1 set. Planted-positive mutates each field and asserts the fence fires.

### §N — Coverage + dependency floors

- [ ] **AC-COV-1** — Line coverage ≥ 95% on `tests/integration/sandbox/_helpers.py` and `tests/integration/sandbox/_perf_row.py`.
- [ ] **AC-COV-2** — Branch coverage ≥ 90% on the same.
- [ ] **AC-DEP-1** — No new Python dependencies (`subprocess`, `time`, `socket`, `platform`, `os`, `json`, `pytest`, `pydantic` — all already in closure). PagerDuty action is a GitHub Actions dependency only; no `pyproject.toml` impact.
- [ ] **AC-LINT-1** — `ruff check`, `ruff format --check`, `mypy --strict` on `tests/integration/sandbox/_helpers.py`, `tests/integration/sandbox/_perf_row.py`, `tests/integration/sandbox/conftest.py`, all test files, and the updated `src/codegenie/sandbox/logging.py` all pass.
- [ ] **AC-LOCAL-1** — Both smoke tests pass when run locally on a contributor's KVM-capable Linux box via `pytest tests/integration/sandbox/test_firecracker_smoke.py tests/integration/sandbox/test_firecracker_network_policy.py`; no CI-only assumptions in the test bodies (the workflow's pre-flight steps are in the WORKFLOW, not the tests).

## Implementation outline

1. **Kernel first — `tests/integration/sandbox/_helpers.py`** (AC-CONSTRUCT-1..-3 + AC-SPEC-1..-3 + AC-PERF-MODEL-3): `kvm_smoke_client_factory()`, `kvm_smoke_spec(**overrides)`, `load_sandbox_run(run_dir, attempt_line)`, `record_perf(...)`. Phantom-field defense raises `TypeError` BEFORE pydantic.
2. **`tests/integration/sandbox/_perf_row.py`** (AC-PERF-MODEL-1..-2): `FirecrackerSmokePerfRow` + `FirecrackerSmokePerfLog`.
3. **Marker registration in `tests/conftest.py`** (AC-MARK-1..-3) — predicate is `os.path.exists("/dev/kvm") and os.access("/dev/kvm", os.R_OK | os.W_OK)`.
4. **`tests/integration/sandbox/conftest.py` autouse fixture** (AC-PERF-EMIT-1 + AC-EVT-1..-3 emit boundaries) — fixture wraps test execution with the event chain and the JSONL emit.
5. **`tests/integration/sandbox/test_firecracker_smoke.py`** (§C ACs). Before writing, verify S1-04 (`GateContext`), S2-01 (`RetryLedger`), S5-02 (`StrictAndGate`) HARDENED arities. Test uses `kvm_smoke_client_factory()` and `load_sandbox_run(...)`; assertion order per AC-FAIL-PATH-1.
6. **`tests/integration/sandbox/test_firecracker_network_policy.py`** (§D ACs) — populate the S6-02 placeholder body; preserve module-scope marker; three positives + two negatives + structured-event assertion (AC-MUT-1..-3).
7. **Logging constants in `src/codegenie/sandbox/logging.py`** (AC-EVT-1..-3) — alphabetized into sorted `__all__` per S6-04 HARDENED convention.
8. **`.github/workflows/firecracker-smoke.yml`** (§E + §F + §G + §H ACs):
   ```yaml
   # === Documentation ===
   # firecracker-smoke — KVM-gated integration tests + weekly cron.
   # Runner: [self-hosted, kvm] (AND semantics: both labels required).
   # Cron: 0 7 * * 1 — Monday 07:00 UTC (UTC always; do not interpret as local).
   # PagerDuty: see Open Q6 closure in 6b ops PR. Placeholder lines marked `# placeholder-for-6b`.
   # See: docs/phases/05-sandbox-trust-gates/stories/S6-05-kvm-smoke-and-weekly-cron.md
   #      docs/phases/05-sandbox-trust-gates/stories/_validation/S6-05-kvm-smoke-and-weekly-cron.md
   # =====================
   name: firecracker-smoke
   concurrency:
     group: firecracker-smoke
     cancel-in-progress: false
   on:
     pull_request:
       paths:
         - "src/codegenie/sandbox/firecracker/**"
         - "src/codegenie/gates/runner.py"
         - "src/codegenie/gates/catalog/stage6_validate.yaml"
         - "tools/firecracker/**"
         - "tools/digests.yaml"
         - "tests/integration/sandbox/test_firecracker_*.py"
         - "tests/integration/sandbox/conftest.py"
         - "tests/integration/sandbox/_helpers.py"
         - ".github/workflows/firecracker-smoke.yml"
         - ".github/workflows/firecracker-queue-watcher.yml"
     workflow_dispatch:
       inputs:
         acknowledge:
           required: true
           type: boolean
           description: "I understand this consumes the KVM runner"
     schedule:
       # Monday 07:00 UTC (UTC always — GitHub Actions cron is UTC; do not interpret as local).
       - cron: "0 7 * * 1"
   env:
     KVM_TEST_FILES: "tests/integration/sandbox/test_firecracker_smoke.py tests/integration/sandbox/test_firecracker_network_policy.py"
   jobs:
     smoke:
       runs-on: [self-hosted, kvm]
       timeout-minutes: 20
       defaults:
         run:
           shell: bash -euxo pipefail {0}
       steps:
         - uses: actions/checkout@<SHA-PIN>           # SHA-pinned per AC-WF-8
         - name: pre-test cache hygiene
           run: |
             rm -rf ~/.npm /tmp/npm-cache-* /tmp/cgsbx-* /tmp/empty-cache
             mkdir -p /tmp/empty-cache
         - name: prepare firecracker artifacts (digest check)
           run: codegenie sandbox prepare --backend firecracker --check
         - name: run KVM-gated tests
           run: pytest $KVM_TEST_FILES --tb=short -ra
         - name: capture sandbox health on failure
           if: failure()
           run: codegenie sandbox health > sandbox-health-${{ github.run_id }}.json
         - name: upload health
           if: failure()
           uses: actions/upload-artifact@<SHA-PIN>     # SHA-pinned per AC-WF-9
           with:
             name: sandbox-health-${{ github.run_id }}
             path: sandbox-health-*.json
         # 6b ops PR closes Open Q6 by replacing this placeholder with the org-standard PagerDuty incident-create action
         # pinned to a SHA. Until then, this step is a planned no-op on PR / dispatch and a placeholder-fire on schedule.
         # See: docs/phases/05-sandbox-trust-gates/stories/_validation/S6-05-kvm-smoke-and-weekly-cron.md §Open Q6 deferral.
         - name: page on-call (weekly cron failure only)
           if: failure() && github.event_name == 'schedule'
           uses: pagerduty/<INCIDENT-CREATE-ACTION-NAME>@<SHA>    # placeholder-for-6b
           with:
             integration-key: ${{ secrets.PAGERDUTY_KVM_RUNNER_SERVICE_KEY }}
             summary: "codegenie firecracker weekly smoke failed"
             severity: error                                       # placeholder-for-6b: severity enum varies by action
             links: '[{"href":"https://github.com/${{ github.repository }}/actions/runs/${{ github.run_id }}","text":"workflow run"}]'
   ```
9. **`.github/workflows/firecracker-queue-watcher.yml`** (§L ACs) — `runs-on: ubuntu-latest`; queries GitHub API; fires PagerDuty on > 24h stall.
10. **Fence tests** (AC-FENCE-1 + AC-PD-TEST-1 + `tests/schema/test_kvm_smoke_uses_helpers.py` + `tests/sandbox/test_perf_row_writer.py`).
11. **Perf trend test `tests/perf/test_firecracker_smoke_p95.py`** (§J ACs) — segregated from the smoke workflow.

## TDD plan — red / green / refactor

### Red — write the failing tests first

Verify-before-write callouts (T-10, T-11, T-12): read the latest HARDENED reports for S1-04 (`GateContext` arity), S2-01 (`RetryLedger` arity), S5-02 (`StrictAndGate` factory shape). The signatures below assume canonical names; substitute whatever those HARDENED reports pinned.

```python
# tests/integration/sandbox/test_firecracker_smoke.py
from __future__ import annotations
"""KVM-gated smoke for FirecrackerClient — gate-keeping evidence for ADR-0019.

See: docs/phases/05-sandbox-trust-gates/ADRs/0004-dind-default-macos-with-gate-isolation-class.md
     docs/phases/05-sandbox-trust-gates/ADRs/0001-two-chokepoint-sandbox-seam.md
     docs/phases/05-sandbox-trust-gates/phase-arch-design.md §Goal 6
     docs/phases/05-sandbox-trust-gates/stories/S6-05-kvm-smoke-and-weekly-cron.md
"""

import json
import time
from pathlib import Path

import pytest

from codegenie.gates.runner import GateRunner
from codegenie.gates.retry_ledger import RetryLedger
from codegenie.gates.strict_and import StrictAndGate          # or canonical S5-02 factory
from codegenie.gates.contract import GateContext              # verify S1-04 HARDENED arity
from codegenie.sandbox.spec_builder import SandboxSpecBuilder # if S5-02 exposes from_catalog()

from ._helpers import kvm_smoke_client_factory, load_sandbox_run


pytestmark = pytest.mark.skip_if_no_kvm


def test_firecracker_runs_hello_node_in_microvm_within_budget(tmp_path: Path) -> None:
    client = kvm_smoke_client_factory()
    gate = StrictAndGate.from_catalog("stage6_validate")      # verify S5-02 HARDENED factory name
    ledger = RetryLedger(run_dir=tmp_path / "rem", gate_id="stage6_validate", prev_chain_head=None)
    runner = GateRunner(client=client, gate=gate, ledger=ledger,
                        spec_builder=SandboxSpecBuilder.from_catalog())
    ctx = GateContext(worktree=Path("tests/fixtures/repos/hello-node").resolve(),
                      run_id=tmp_path.name)

    start = time.monotonic()
    outcome = runner.run(ctx)
    elapsed = time.monotonic() - start

    # AC-FAIL-PATH-1: passed check FIRST so on-call sees the right cause.
    assert outcome.passed, f"hello-node gate did not pass: {outcome.summary}"
    assert elapsed <= 300, f"smoke exceeded 300 s budget: {elapsed:.1f}s"

    attempts_file = tmp_path / "rem" / "gates" / "stage6_validate" / "attempts.jsonl"
    last = json.loads(attempts_file.read_text().splitlines()[-1])
    assert last["outcome"]["passed"] is True

    # AC-RUN-LOOKUP-1..-3: backend + gate_isolation_class live on SandboxRun, not on Attempt.
    run = load_sandbox_run(tmp_path, last)
    assert run.backend == "firecracker", f"wrong backend: {run.backend}"
    assert run.gate_isolation_class == "microvm", f"wrong isolation class: {run.gate_isolation_class}"
```

```python
# tests/integration/sandbox/test_firecracker_network_policy.py
from __future__ import annotations
"""KVM-gated network-policy smoke — host-side TAP + nftables.

Populated by S6-05 (S6-02 shipped the placeholder).
See: docs/phases/05-sandbox-trust-gates/ADRs/0009-firecracker-network-policy-host-side-nftables.md
     docs/phases/05-sandbox-trust-gates/ADRs/0001-two-chokepoint-sandbox-seam.md
     docs/phases/05-sandbox-trust-gates/stories/S6-05-kvm-smoke-and-weekly-cron.md
"""

import subprocess
from pathlib import Path

import pytest

from ._helpers import kvm_smoke_client_factory, kvm_smoke_spec


pytestmark = pytest.mark.skip_if_no_kvm


def test_scoped_allowlist_permits_npm_blocks_other_egress(tmp_path: Path) -> None:
    client = kvm_smoke_client_factory()

    # Positive 1: npm ci (the workload) — allowlist must permit.
    spec_npm = kvm_smoke_spec(
        cmd=("sh", "-c", "npm ci --silent --cache /tmp/empty-cache"),
        copy_in=(("tests/fixtures/repos/hello-node", "/work"),),
        time_budget_seconds=180, memory_limit_mib=1024,
        network="scoped", egress_allowlist=("registry.npmjs.org",),
    )
    run_npm = client.execute(spec_npm)
    assert run_npm.exit_code == 0, "npm ci must succeed via allowlist"

    # Positive 2 (AC-MUT-1): explicit registry probe.
    spec_reg = kvm_smoke_spec(
        cmd=("sh", "-c", "curl -sf https://registry.npmjs.org/ -o /dev/null"),
        network="scoped", egress_allowlist=("registry.npmjs.org",),
        time_budget_seconds=30, memory_limit_mib=256,
    )
    assert client.execute(spec_reg).exit_code == 0, "registry must be reachable under scoped allowlist"

    # Negative 1: github.com blocked.
    spec_gh = kvm_smoke_spec(
        cmd=("sh", "-c", "curl -sf https://github.com -o /dev/null"),
        network="scoped", egress_allowlist=("registry.npmjs.org",),
        time_budget_seconds=30, memory_limit_mib=256,
    )
    assert client.execute(spec_gh).exit_code != 0, "github egress must be blocked"

    # Negative 2: IP-literal egress blocked.
    spec_ip = kvm_smoke_spec(
        cmd=("sh", "-c", "curl -sf https://1.1.1.1 -o /dev/null"),
        network="scoped", egress_allowlist=("registry.npmjs.org",),
        time_budget_seconds=30, memory_limit_mib=256,
    )
    assert client.execute(spec_ip).exit_code != 0, "ip-literal egress must be blocked"

    # AC-MUT-2: structured-event assertion (S6-02 AC-EVT-1 surface).
    assert run_npm.signals.network_policy == "scoped"

    # AC-NFT-1: no leak of OUR table (autouse fixture also tears down).
    tables = subprocess.check_output(["nft", "list", "tables", "inet"]).decode()
    assert f"cgsbx_{run_npm.run_id[:12]}" not in tables, "nftables table leaked"
```

### Green — make it pass

- Helpers under `_helpers.py` + `_perf_row.py` exist.
- Marker registered in `tests/conftest.py`.
- Autouse perf fixture in `tests/integration/sandbox/conftest.py` emits one `FirecrackerSmokePerfRow` per smoke test (pass AND fail).
- Workflow + queue-watcher workflows committed; SHA-pins applied for `actions/checkout` and `actions/upload-artifact` (PagerDuty SHA stays as a `# placeholder-for-6b` until 6b ops lands).
- Logging constants added to `sandbox/logging.py` (alphabetized into sorted `__all__`).

### Refactor — clean up

- Move any duplicated assertion message templates into `_helpers.py` constants.
- Confirm no test body carries a `try/finally` (the autouse fixture owns emit).
- Top-of-file docstrings in each new file cite the relevant ADR(s) + Phase-arch §Goal 6 + this story.

## Files to touch

| Path | Why |
|---|---|
| `tests/conftest.py` | Register `skip_if_no_kvm` marker + collection hook. |
| `tests/integration/sandbox/_helpers.py` | NEW — kernel for client factory, spec builder, run-summary lookup, perf record. |
| `tests/integration/sandbox/_perf_row.py` | NEW — typed `FirecrackerSmokePerfRow` + `FirecrackerSmokePerfLog`. |
| `tests/integration/sandbox/test_firecracker_smoke.py` | NEW — KVM-gated full gate run via `GateRunner`. |
| `tests/integration/sandbox/test_firecracker_network_policy.py` | EDIT — populate body of the S6-02 placeholder; preserve module-scope marker. |
| `tests/integration/sandbox/conftest.py` | EDIT — autouse perf-emit fixture from day 1 (NOT in Refactor). |
| `tests/unit/test_skip_if_no_kvm_predicate.py` | NEW — predicate regression for AC-MARK-3. |
| `tests/schema/test_kvm_gated_tests_carry_marker.py` | NEW — fence per AC-FENCE-1. |
| `tests/schema/test_kvm_smoke_uses_helpers.py` | NEW — fence: no direct `SandboxSpec(...)` in smoke tests. |
| `tests/sandbox/test_perf_row_writer.py` | NEW — AC-JSONL-1 property test. |
| `tests/ci/test_firecracker_smoke_workflow.py` | NEW — workflow YAML meta-fence per AC-PD-TEST-1. |
| `tests/perf/test_firecracker_smoke_p95.py` | NEW — perf trend (AC-PERF-1..-4); segregated from smoke workflow. |
| `.github/workflows/firecracker-smoke.yml` | NEW — main CI + cron workflow per §E+§F+§G+§H. |
| `.github/workflows/firecracker-queue-watcher.yml` | NEW — companion queue-stall watcher per §L. |
| `src/codegenie/sandbox/logging.py` | EDIT — add three `EVENT_SANDBOX_FIRECRACKER_SMOKE_*` constants alphabetized into sorted `__all__`. |
| `docs/phases/05-sandbox-trust-gates/README.md` | EDIT — mark Open Q6 as "deferred to 6b ops" (not closed); link to the validation report. |

## Out of scope

- **Open Q6 *operational* closure** — 6b ops PR fills the PagerDuty action SHA + the integration-key secret name + the rotation-owner doc. This story ships the code seams + the `# placeholder-for-6b` markers.
- **Operator CLI implementations (`codegenie sandbox health/inspect/gc`)** — S8-01 (this story only *invokes* `health` from the workflow).
- **Perf-budget regression gates (p50 / p95 / retry-2 budget) at PR-time** — S7-02 (this story records typed JSONL + ships AC-PERF-1..-4 trend test gated nightly).
- **Multi-arch KVM testing** — Phase 5 is x86_64 only.
- **E2E `codegenie remediate` smoke on Linux KVM** — S8-03 (this story exercises the gate primitives, not the orchestrator).
- **Cron-failure runbook content** — captured in the workflow comment header + the `_validation/` audit; a full ops runbook is a Phase 14 artifact.
- **The dispatch-input `acknowledge` UI / approval flow** — beyond the boolean gate.
- **Per-OS runner-image baking + multi-runner pool sizing** — operational deliverable.
- **Post-failure capture composite-action seam** (D-4) — deferred to Phase 7 when a second capture target enters scope (rule-of-three not yet reached).

## Notes for the implementer

- **Kernel-extract is not premature.** Two smoke tests in this story + (S7-02 perf) + (S8-03 e2e) + (Phase 7 distroless smoke) = four known consumers; rule-of-three crossed. `_helpers.py` ships day 1 (Design-Patterns critic D-1).
- **Workflow YAML constant pattern** (`env.KVM_TEST_FILES`): single source of truth for the test-file list; the `paths:` filter mirrors the same prefixes; the marker-fence test cross-validates. Future-proofs against test-file renames.
- **Cron is `0 7 * * 1` (Monday 07:00 UTC)** — picked to land before US/EU work hours so the on-call sees the page before the team starts. Do not change without an ADR amendment. GitHub Actions cron is UTC always — the inline comment defends against a maintainer reading it as local.
- **`runs-on: [self-hosted, kvm]` is AND-conjoined.** A runner with only `self-hosted` is not picked up. Documented in the workflow doc-block so on-call understands queue growth.
- **PagerDuty action choice is 6b's call.** The placeholder `pagerduty/<INCIDENT-CREATE-ACTION-NAME>@<SHA>` is intentional; the workflow lint (AC-PD-TEST-1) accepts the explicit `# placeholder-for-6b` annotation. Once 6b lands, remove the placeholder comment and pin the SHA. The action category matters — `change-events` actions annotate deployments; `incident-create` actions page on-call. Pick the latter.
- **`--check` invocation of `codegenie sandbox prepare --backend firecracker`** is the load-bearing pre-flight (S6-03 HARDENED `--check` is read-from-disk ≤ 5 s; ideal for PR-time). If S6-03 has not landed `--check` at story start, fall back to `blake3sum tools/digests.yaml` (AC-PREP-2) and collapse on S6-03 GREEN.
- **Hello-node fixture is shared with S3-07 and S5-05**; do not vendor a second copy.
- **`nft list tables` in the test file is a chokepoint exemption** — the production code path is owned by S6-02; in tests we accept the shell-out (mirrors the S3-03 / S6-02 test-file exemption). The chokepoint AST test (S5-04) already exempts `tests/`.
- **If the self-hosted KVM runner is not provisioned at story start**, escalate per `final-design.md §Risks risk-2` + `High-level-impl.md §Step 6 — Risks specific to this step` (line 178): the **6a deliverable** (this story without §L queue-watcher + with `# placeholder-for-6b` PagerDuty) lands ahead of 6b; the phase exit criterion is **not** met until 6b ops fills the placeholders and the cron has fired green at least once.
- **Open/Closed for post-failure capture (D-4 deferred):** when Phase 7 lands a second on-failure capture target (e.g., `codegenie sandbox baseimage-trace`), promote the inline-steps list into `.github/actions/post_failure_capture/action.yml` (a composite action). Rule-of-three reached at that point.
- **Concurrency mutex** (AC-CONC-1) is the registry-pattern equivalent for CI runners — a "registry of one" on the self-hosted runner. Documented in this story; future workflows that target the same runner should `concurrency.group:` the same label.
- **A passing weekly cron *is* the evidence ADR-0019 needs** — make sure the run captures cold-start latency, kernel feature requirements (`uname` output), KVM module version, and per-evaluation wall-clock in the typed JSONL (`FirecrackerSmokePerfRow`) so Phase 13/16 has data to consume.
- **6b ops PR closure surface** — see `_validation/S6-05-kvm-smoke-and-weekly-cron.md` §"Forward-compat anchor"; the README + workflow doc-block + Open Q6 line in `README.md` are the three touch points.
