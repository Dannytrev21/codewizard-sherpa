# Story S6-03 — Integration test: `spawn(role=Role.PROBE)` boots microVM + Phase 5 regression suite green

**Step:** Step 6 — Phase 5 `SandboxRole` additive enum + `SandboxClient.spawn(role=...)` amendment
**Status:** Ready
**Effort:** S
**Depends on:** S6-02 (`role` parameter on `spawn(...)` must exist), transitively S6-01 (enum) and S5-01 (allowlist)
**ADRs honored:** Phase 7 ADR-0003 (primary), Phase 7 ADR-0002 (the consumer that this test pins for), Phase 7 ADR-0001 (no parallel `probe-control` process), Phase 5 ADR-0001 (two-chokepoint sandbox seam)

## Context

S6-01 + S6-02 ship the API surface — the `SandboxRole` enum and the `role` parameter on `SandboxClient.spawn(...)`. This story ships the **integration proof** that ADR-0002 §Decision binds: under `Role.PROBE` the microVM boots with **identical topology** to `Role.GATE` *plus* eBPF host-side trace capture *plus* a short container boot, and the default-arg path remains byte-identical to pre-amendment.

The reason this is a separate story is that the integration test exercises real backend dispatch (Firecracker on KVM-equipped Linux runners, DinD on macOS dev, Lima where Phase 5's stack adopts it). Unit tests with stub `SandboxClient`s already covered the API surface in S6-02; this story is the *behavioral* proof. Without it, "identical-plus-trace-capture" remains an unverified architectural claim — and ADR-0002 §Tradeoffs row 4 explicitly warns "Fence is structural; doesn't catch dynamic code that bypasses the AST check." This integration test is the runtime check that bypass attempts produce observable evidence.

The Phase 5 regression-suite green-light is the **second** load-bearing assertion in this story. ADR-0003 §Consequences row 4 says "Every existing `SandboxClient.spawn(...)` call site in Phase 5 keeps working unchanged (default `Role.GATE`)." This story is where that claim becomes a CI gate, not just a design promise. S5-01's byte-edit allowlist catches *structural* drift; this story catches *behavioral* drift — a stealth change to the dispatcher that breaks gate semantics for `Role.GATE` callers would slip past the fence but fail this story's regression assertion.

This is a `@pytest.mark.phase07_integration` (or equivalent — match Phase 5's existing integration-test marker convention) test; on `--privileged` Linux CI runners Firecracker is exercised, on macOS / non-privileged runners DinD is exercised, and `gate_isolation_class` propagates correctly through both paths.

## References — where to look

- **Architecture:**
  - [`../phase-arch-design.md §Component design §9 (ShellInvocationTraceProbe)`](../phase-arch-design.md) — the call shape this test pins for: `spawn(role=Role.PROBE, workspace=..., command=["docker","buildx","build","--target=builder","."], capture_trace=True)`.
  - [`../phase-arch-design.md §Harness engineering — sandbox amendment`](../phase-arch-design.md) — the integration-test discipline section; describes the fixture portfolio.
  - [`../phase-arch-design.md §Tradeoffs (consolidated)`](../phase-arch-design.md) — row "default-arg path byte-identical".
- **Phase ADRs:**
  - [`../ADRs/0003-sandbox-role-additive-enum-on-spawn.md`](../ADRs/0003-sandbox-role-additive-enum-on-spawn.md) — §Consequences row 4 (every existing callsite unchanged), row 6 (integration test asserts identical topology + audit-log tag).
  - [`../ADRs/0002-shell-invocation-trace-probe-runs-in-microvm.md`](../ADRs/0002-shell-invocation-trace-probe-runs-in-microvm.md) — §Consequences row 5 (failure modes are typed: `confidence: "low"` with `reason: "build_failed"` etc.).
  - [`../ADRs/0001-no-multi-plugin-coordinator-in-phase-7.md`](../ADRs/0001-no-multi-plugin-coordinator-in-phase-7.md) — context: no parallel `probe-control` apparatus.
- **Source design:**
  - [`../final-design.md §Risks #1`](../final-design.md) — the fallback if Phase 5 rejects (the test must distinguish "Role.PROBE means probe-tagged GATE topology" from the fallback path).
- **Phase 5 context:**
  - [`../../05-sandbox-trust-gates/final-design.md §Components §1 SandboxClient`](../../05-sandbox-trust-gates/final-design.md) + [`§Goals #3 / #4`](../../05-sandbox-trust-gates/final-design.md) — KVM-Firecracker vs DinD fallback discipline; this story respects both.
  - [`../../05-sandbox-trust-gates/ADRs/0001-two-chokepoint-sandbox-seam.md`](../../05-sandbox-trust-gates/ADRs/0001-two-chokepoint-sandbox-seam.md) — the seam.
  - Phase 5's existing `tests/integration/test_sandbox_*.py` suite — the regression target.
- **High-level impl:**
  - [`../High-level-impl.md §Step 6`](../High-level-impl.md) — Done criteria bullet 3 + bullet 4.

## Goal

Ship `tests/integration/test_sandbox_client_role_probe.py` and a companion `tests/integration/test_sandbox_role_gate_regression.py` (or equivalent — name per Phase 5's integration test conventions) such that:

1. **`spawn(role=Role.PROBE, capture_trace=True)` boots a microVM with identical topology to `spawn(role=Role.GATE)`** — same backend, same `gate_isolation_class`, same resource budgets — *plus* eBPF host-side trace capture is enabled in the returned `SandboxRun.trace_path` (or backend-equivalent capture artifact) and the audit log carries `role: "probe"`.
2. **The default-arg path** (`client.spawn(spec)` without explicit `role`) produces a `SandboxRun` byte-equal under normalization to `client.spawn(spec, role=Role.GATE)`. This is the runtime check that S6-02's unit test only proves at the stub level.
3. **Phase 5's existing test suite is green with zero new test skips, zero `xfail` markers added, and zero golden file deletions.** The full `pytest tests/unit/sandbox/ tests/integration/test_sandbox_*.py` run exits 0 on the post-S6-03 branch.
4. **Failure modes are typed.** A deliberate broken `Role.PROBE` boot (e.g., a malformed spec) produces a `SandboxRun` with the typed `confidence: "low"` annotation and `reason: "build_failed"` (or backend-specific reason) per ADR-0002 §Consequences row 5 — no uncaught exception, no `None` return.

## Acceptance criteria

### A. `Role.PROBE` topology proof

- [ ] `tests/integration/test_sandbox_client_role_probe.py::test_probe_role_boots_microvm_with_capture` — runs `client.spawn(probe_spec, role=Role.PROBE, capture_trace=True)` against the Phase 5 backend the CI runner supports (Firecracker on `--privileged` Linux, DinD on macOS or non-privileged Linux); asserts `SandboxRun.exit_status.success` is `True` and `SandboxRun.trace_path` (or backend-equivalent) is a non-empty file.
- [ ] `tests/integration/test_sandbox_client_role_probe.py::test_probe_topology_identical_to_gate` — runs the *same* `spec` (modulo the `capture_trace` flag) under both `Role.GATE` and `Role.PROBE`; asserts the two `SandboxRun`s share the same `backend`, same `gate_isolation_class`, same `cpu_quota`, same `memory_limit_mib`, same `pids_limit`. The only differences permitted are: (i) `trace_path` is non-`None` only under `Role.PROBE+capture_trace=True`; (ii) `audit_events[*].role` is `"probe"` vs `"gate"`; (iii) timing fields (`duration_ms`, `started_at`).
- [ ] `tests/integration/test_sandbox_client_role_probe.py::test_probe_audit_event_role_tag` — asserts at least one `audit_events` entry has `role == "probe"`, and no entries have `role == "gate"`, on a `Role.PROBE` run.

### B. Default-arg path byte-identity (runtime)

- [ ] `tests/integration/test_sandbox_role_gate_regression.py::test_default_arg_byte_equal_to_role_gate` — calls `client.spawn(gate_spec)` and `client.spawn(gate_spec, role=Role.GATE)` against a real backend; normalizes time-dependent fields; asserts the resulting `SandboxRun`s are equal under the normalization. This is the runtime complement to S6-02's stub-level test.
- [ ] `tests/integration/test_sandbox_role_gate_regression.py::test_default_arg_audit_event_role_is_gate` — asserts every audit event on the default-arg path carries `role == "gate"` (additive field per S6-02; the runtime confirms it propagates).

### C. Phase 5 regression suite green

- [ ] On the post-S6-03 branch, **`pytest tests/unit/sandbox/ tests/integration/test_sandbox_*.py` exits 0.** Capture the full run output in `_attempts/S6-03.md` for auditability.
- [ ] **Zero new `pytest.skip`, `xfail`, or `skipif` markers** in Phase 5's test suite. A regression detector script (`tests/unit/test_phase5_regression_no_skips.py`) compares the count of `@pytest.mark.skip` / `@pytest.mark.xfail` / `pytest.skip(...)` call sites in `tests/unit/sandbox/` + `tests/integration/test_sandbox_*.py` against the Phase 6.5-baseline count; any net-positive diff fails CI.
- [ ] **Zero golden-file deletions** under `tests/golden/sandbox/`. Additive updates per S6-02 are permitted (the `role` field); deletions are not.
- [ ] `make check` exits 0.

### D. Typed failure-mode coverage

- [ ] `tests/integration/test_sandbox_client_role_probe.py::test_probe_boot_failure_returns_typed_outcome` — induces a microVM boot failure (e.g., malformed `workspace` path or a backend-specific deliberate failure) on `Role.PROBE`; asserts the returned `SandboxRun.exit_status` carries a typed failure `reason` (one of the ADR-0002 §Consequences row 5 reasons: `"sandbox_boot_failed"` or `"build_failed"`) and `confidence: "low"`. No uncaught exception propagates to the test.
- [ ] `tests/integration/test_sandbox_client_role_probe.py::test_probe_capture_trace_false_succeeds` — runtime confirmation of S6-02's orthogonality claim: `client.spawn(probe_spec, role=Role.PROBE, capture_trace=False)` boots successfully; `trace_path` is `None`; audit log still carries `role == "probe"`.

### E. CI matrix discipline

- [ ] The integration test file declares `@pytest.mark.phase07_integration` (or whatever marker Phase 5 uses for `--privileged`-runner-gated tests; reconcile against Phase 5's existing convention — Rule 11).
- [ ] On runners that lack the privileged capability (no KVM, no `--privileged`), the test gracefully `skip(reason="Firecracker requires --privileged or KVM; DinD path tested elsewhere")` rather than failing — Phase 5's existing fixture-skip mechanism is the precedent (Phase 5 §Goals #3).
- [ ] On both `--privileged` Linux and standard macOS runners, at least one path of the integration suite executes; a CI matrix test confirms full coverage cannot be silently skipped on every runner simultaneously (the "everything skipped" failure mode is a CI bug, not a green build).

### F. Fence + regression-detector composition

- [ ] S5-01's byte-edit allowlist fence remains green (this story adds no new byte-edits to Phase 0–6.5 files — it ships only new test files).
- [ ] `mypy --strict tests/integration/test_sandbox_client_role_probe.py tests/integration/test_sandbox_role_gate_regression.py` clean.
- [ ] `ruff check tests/integration/` + `ruff format --check tests/integration/` clean for the new files.

## Implementation outline

1. **Read Phase 5's integration test conventions** under `tests/integration/test_sandbox_*.py`: marker names, fixture names (`gate_spec`, `firecracker_client`, `did_client`, etc.), how runner-capability detection works. Rule 11 — Match existing conventions. The new test files inherit those conventions.
2. **Reconcile the method name** (`spawn` vs `execute` — see S6-02 Notes). Whichever the codebase uses, the integration tests call that method directly. Do not introduce a wrapper or alias.
3. **Write `tests/integration/test_sandbox_client_role_probe.py`** with the AC-A and AC-D test functions. Each function uses Phase 5's existing `gate_spec` / equivalent fixture for the GATE baseline; constructs a parallel `probe_spec` (typically the same spec with `capture_trace` semantics layered on).
4. **Write `tests/integration/test_sandbox_role_gate_regression.py`** with the AC-B test functions. These call `spawn(...)` against a real backend (matrix-selected per runner capability) and compare the default-arg run against the explicit-`Role.GATE` run under a normalization function defined once and reused across both Phase 7 and any future regression suite (extract to `tests/integration/_sandbox_normalization.py` or similar; mind Rule 3 — Surgical Changes — only create the helper if necessary).
5. **Write `tests/unit/test_phase5_regression_no_skips.py`** (AC-C bullet 2) — a small grep/AST scan that counts skip / xfail markers in Phase 5's test directories and asserts the count is `≤` the baseline. Baseline can be a checked-in JSON file (`tests/_baselines/phase5_skip_counts.json`) refreshed only via a CODEOWNERS-gated edit.
6. **Run the full integration suite locally** on whatever backend the dev machine supports; capture output in `_attempts/S6-03.md` for the validator.
7. **Run `make check`** — confirm Phase 5 + Phase 7 green.

## TDD plan (red → green → refactor)

Note: this story is a **test-only** story (the production code lands in S6-02). The "red" here is that the integration tests fail to *find* the behavior they assert — either because S6-02's `role` parameter isn't wired correctly (in which case S6-02 is incomplete and this story blocks) or because Phase 5's backend dispatcher hasn't been wired to honor `capture_trace` end-to-end (in which case S6-02 needs amending). This story's red is a diagnostic for the API-shipping stories.

### Red

Write the test file `tests/integration/test_sandbox_client_role_probe.py` end-to-end against the AC list. Run it on a `--privileged` Linux dev box (or under the CI matrix in draft-PR mode). Expected red modes:

1. `test_probe_role_boots_microvm_with_capture` — fails if `capture_trace=True` does not actually enable eBPF capture (e.g., S6-02 wired the parameter but not the dispatch).
2. `test_probe_topology_identical_to_gate` — fails if the backend silently changes resource budgets under `Role.PROBE` (e.g., raises `cpu_quota` to accommodate `buildx`). Surface and decide: either the topology *is* identical (fix the dispatcher) or ADR-0003's "identical topology" claim needs revision (escalate as an ADR amendment — this is RESCUE-tier per the validation grammar).

### Green

The path to green is either (a) S6-02 is correct and the tests pass against the real backend — happy case — or (b) the tests reveal an S6-02 gap that must be fixed before this story can close. Fix-S6-02 work is **not** in scope for this story; if AC-A fails, S6-03 is BLOCKED and S6-02 is reopened.

### Refactor

Verify the normalization helper (if extracted) is reused, not duplicated; verify `mypy --strict` + `ruff` clean on the new test files; verify no new fixture shadowing or marker collisions with Phase 5's existing test infrastructure.

## Files to touch

- `tests/integration/test_sandbox_client_role_probe.py` — new file, ACs A + D + parts of E.
- `tests/integration/test_sandbox_role_gate_regression.py` — new file, AC B.
- `tests/integration/_sandbox_normalization.py` (or similar) — optional, only if AC-B's normalization logic is reused.
- `tests/unit/test_phase5_regression_no_skips.py` — new file, AC C bullet 2.
- `tests/_baselines/phase5_skip_counts.json` — new baseline file, CODEOWNERS-gated for future refreshes.

This story **does not touch** `src/codegenie/` — the byte-edit allowlist counter stays at the level S6-02 left it.

## Out of scope

- Fixing any S6-02 gap revealed by AC-A's failure — if `Role.PROBE` doesn't actually enable trace capture end-to-end, that's a defect in S6-02 and reopens that story; S6-03 stays BLOCKED until S6-02 is fixed.
- `ShellInvocationTraceProbe`'s probe-level integration test (calling `ctx.sandbox_client.spawn(role=Role.PROBE)` from inside the probe's `run()`) — owned by **S7-02** and **S7-05**.
- `DistrolessBuildGate` / `ShellInvocationDeltaGate` real-microVM integration (they use `Role.GATE` — the default — which AC-B already covers, but their gate-specific assertions belong to **S10-04** and **S10-05**).
- Phase 5 backend additions (e.g., real Lima integration on macOS) — Phase 5's roadmap, not Phase 7's.
- Performance / latency budgets for `Role.PROBE` boots (cold p99, warm p99) — those are bench-tier concerns in **S12-05**, not integration-correctness concerns here.

## Notes for the implementer

- **The two load-bearing assertions are independent.** AC-A proves `Role.PROBE` does what ADR-0002 says it does. AC-B + AC-C prove `Role.GATE` (and the default-arg path) is unchanged. A green build requires **both**. A failure on AC-A is a "Phase 7 added new behavior that doesn't actually work" defect; a failure on AC-B or AC-C is a "Phase 7 broke Phase 5" defect — far worse. Treat regressions on AC-B / AC-C with elevated severity (Rule 12 — Fail loud).
- **Runner-capability skipping is a footgun.** AC-E bullet 3 names the "everything skipped is a green build" failure mode. The `test_phase5_regression_no_skips.py` baseline check is the structural defense, but also verify by hand: at least one integration-suite path actually executes on at least one CI matrix entry, every time. If the CI runner pool changes (e.g., the `--privileged` Linux runner pool is reduced), this story may need to re-skip-strategy — flag in the attempt log.
- **The normalization helper** (if extracted) must drop `started_at`, `ended_at`, `duration_ms`, and any host-randomized fields (PIDs, ports). It must **not** drop `trace_path` (`None` for `Role.GATE`, non-`None` for `Role.PROBE+capture_trace=True` — that's a load-bearing diff). It must **not** drop `audit_events[*].role` — also load-bearing.
- **`gate_isolation_class` is the Phase 5 contract surface that propagates to Phase 11.** Phase 5 §Goals #4 says the merge gate refuses to auto-promote `shared_kernel` verdicts. This story must verify that `Role.PROBE` produces the same `gate_isolation_class` value as `Role.GATE` on the same backend — drift here would silently change Phase 11's merge-promotion eligibility.
- **The fallback ADR-0003 §Reversibility names** (if Phase 5 rejects the amendment, route `Role.PROBE` through `Role.GATE` semantically) is **not exercised by these tests**. If the fallback is invoked, AC-A's `test_probe_audit_event_role_tag` becomes the *only* observable distinction, and AC-A's topology-identical test must be re-examined for what "identical" means under the fallback. Surface in `_attempts/S6-03.md` if the fallback path is in play.
- **Reading order before writing tests:**
  1. [`../ADRs/0002-shell-invocation-trace-probe-runs-in-microvm.md §Consequences`](../ADRs/0002-shell-invocation-trace-probe-runs-in-microvm.md) — failure modes (`sandbox_boot_failed`, `build_failed`).
  2. [`../ADRs/0003-sandbox-role-additive-enum-on-spawn.md §Consequences`](../ADRs/0003-sandbox-role-additive-enum-on-spawn.md) — additive audit-log field, every existing callsite unchanged.
  3. Phase 5's `tests/integration/test_sandbox_*.py` — fixture names, marker conventions, runner-capability detection.
  4. `src/codegenie/sandbox/client.py` post-S6-02 — actual method shape.
- **No `pytest.skip("not implemented")` placeholders.** Either the test passes or it fails for a named reason. ADR-0002 §Tradeoffs row 4 warns against structural-only fences; this story is the runtime complement and "placeholder green" defeats its purpose (Rule 12).
- **Coordinate with S7-02 timing.** S7-02 (`ShellInvocationTraceProbe`) is the *only* production caller of `spawn(role=Role.PROBE)` in Phase 7. If this story's tests pin a behavior S7-02 then has to work around, that's a coordination defect — fix here, not in the probe. The arch design and ADR-0002 §Decision are the canonical contract; both stories implement against it, not against each other.
