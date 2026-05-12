# Story S7-02 — Adversarial corpus: ≥ 30 fixtures gating merge

**Step:** Step 7 — Harden — ≥ 30 adversarial fixtures, determinism canary, perf canaries, Phase-2 regression hard-gate, Phase-4 handoff verification, CI gates
**Status:** Ready
**Effort:** L
**Depends on:** S7-01 (fixture portfolio + mirror substrate), S6-01 (OpenRewriteEngineStub — its isolation tests live in this corpus), S5-05 (full CLI vertical — many tests invoke `codegenie remediate` end-to-end), S4-01 (LockfilePolicyScanner — five typed violations are exercised here), S4-03 (test_validator — escalation isolation tests), S3-01 (`tools/npm.py` wrapper — `NpmScriptsEnabled` adversarial), S3-04 (`recipes/digests.yaml` — drift adversarial), S2-06 (cve snapshot store — tampering adversarial)
**ADRs honored:** ADR-0005 (single sandbox profile + `test_execution=True` overlay + `gate.signal_escalate` — isolation tests pin every dimension), ADR-0007 (LockfilePolicyScanner graded escape valve — five typed violations + `--allow-policy-violations` exercised here), ADR-0008 (CVE feed integrity — content-hash mismatch + signature tampering), ADR-0009 (CveRetractionProbe — retraction-detection adversarial), ADR-0010 (audit chain extension — chain-integrity + chain-break observability), ADR-0011 (canonicalization + `recipes/digests.yaml` — drift adversarials), ADR-0012 (fixture mirror integrity — corpus runs offline against pinned mirror), ADR-0013 (no LLM + strict-AND confidence — fence + strict-AND adversarials), ADR-0014 (`ALLOWED_BINARIES` is the only exec surface)

## Context

The adversarial corpus is the **single highest-leverage Phase-3 CI gate**. Every other test (golden, bench, integration, determinism canary) trusts that the corpus already trips on hostile input; if the corpus is incomplete or fictional, the gate is fictional. This story lands **≥ 30 adversarial fixtures** under `tests/adv/` covering every load-bearing Phase 3 invariant. The count is **synth-relaxed from S's ≥ 40** because ten of S's fixtures targeted a second sandbox profile that this design (single profile + `test_execution=True` overlay per ADR-0005) does not have.

The corpus is **CI-gating**: any new fixture that fails on `main` blocks the merge. The combined p95 wall-clock cap is **< 90 s** for the default `tests/adv -m "not slow_adv"` run; tests that need long subprocess work go behind `[slow_adv]` markers and run nightly only. Every test docstring opens with `"""ADR-NNNN | Invariant: <one-sentence>"""` so the gating ADR is grep-able from `pytest --collect-only -q` (the same discipline Phase 2's S8-01 established).

The corpus categories (≥ 30 fixtures distributed across them):

1. **npm-install postinstall blocked** (S3-01 wrapper) — `--ignore-scripts` invariant; the `postinstall-rce-attempt` fixture from S7-01 is consumed here.
2. **Lockfile policy violations — all five typed** (S4-01) — `RegistryRedirect`, `MissingIntegrity`, `LifecycleScriptDeclared`, `PublishConfigOverride`, `ResolutionsRedirect`. Each gets a blocked-without-flag test and an allowed-with-flag test.
3. **Test-execution isolation** (S4-03 + ADR-0005 overlay) — filesystem, network (network-none default + signature-scan escalation), wall, pid, memory, fork-bomb.
4. **OpenRewriteEngineStub isolation** (S6-01) — no Maven Central reach-through; no file written outside worktree; java-missing handling.
5. **Git-hooks-disabled + signing-key-absent** (S5-04 branch writer) — pre-commit / pre-push hooks do not fire; commits are unsigned when no signing key configured (no error).
6. **Branch refusals** (S5-04) — dirty tree refusal; existing branch refusal.
7. **Audit chain integrity + chain-break observability** (ADR-0010) — tampered chain head triggers `audit.chain_break.detected` event but the run continues (carried forward from Phase 2 invariant).
8. **No-credentials-in-sandbox** — `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `CHAINGUARD_TOKEN`, `MY_INTERNAL_SECRET` in parent env never appear in subprocess env (carried forward from Phase 2 S8-01; re-asserted at the Phase-3 wrapper layer).
9. **Fence-job tests** — `anthropic`, `langgraph`, `chromadb`, `qdrant`, `sentence-transformers`, `voyageai`, `openai` import-forbidden under `transforms/` + `recipes/` (ADR-0013).
10. **CVE snapshot tampering + hash mismatch** (S2-06 + ADR-0008) — corrupt snapshot on disk; loud read failure.
11. **Recipe digest drift** (S3-04 + ADR-0011) — recipe content edited without digest update; `RecipeRegistry` refuses load.
12. **`tools/digests.yaml` drift breaks install** (Phase 2 ADR-0004 + ADR-0014) — `npm` or `ncu` digest mismatch at install; CI red.
13. **Engine-availability snapshot consistency under flux** (S3-07 + Gap 6) — selector and transform see the same `available()` result even when the environment changes mid-run.
14. **Cache-replay back-reference validation** (S3-08 + ADR-0010) — `cache.replay` audit event correctly references the original chain head.
15. **Subprocess discipline** — no `subprocess.run`/`Popen` under `transforms/` or `recipes/` outside `src/codegenie/exec.py` and `src/codegenie/tools/` (AST scan).

This corpus is the last story in Phase 3 that adds raw test surface; S7-03 onward only consume the corpus.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Testing strategy" §"Adversarial tests (`tests/adv/`) — target ≥ 30 fixtures"` — the canonical list this story implements.
  - `../phase-arch-design.md §"Failure modes & recovery"` — informs the negative-case shape (probe/validator falls back rather than crashing the gather/run).
  - `../phase-arch-design.md §"Gap analysis"` — Gap 6 (engine availability snapshot — has a dedicated adversarial), Gap 1 (audit chain extension — has a chain-break adversarial), Gap 2 (recipe digest drift — has an adversarial).
- **Phase ADRs (each trips at least one fixture):**
  - `../ADRs/0005-single-sandbox-profile-test-execution-overlay-signal-escalate.md` — overlay isolation; signal-escalate honest-failure invariant.
  - `../ADRs/0007-lockfile-policy-scanner-graded-allow-policy-violations.md` — five typed violations; `--allow-policy-violations` grammar.
  - `../ADRs/0008-cve-feed-integrity-content-hash-best-effort-signature-graded-staleness.md` — snapshot hash mismatch.
  - `../ADRs/0009-cve-retraction-probe-evidence-stale-marker.md` — retraction adversarial.
  - `../ADRs/0010-audit-chain-extension-cache-replay-event.md` — chain integrity + `cache.replay` back-reference.
  - `../ADRs/0011-lockfile-canonicalization-and-npm-digest-pin-for-deterministic-diffs.md` — recipe digest drift; tools digest drift.
  - `../ADRs/0012-test-fixture-bundle-plus-resolution-plus-pinned-mirror.md` — mirror integrity; corpus runs against pinned mirror.
  - `../ADRs/0013-confidence-strict-and-of-binary-signals-no-llm.md` — fence-job tests; strict-AND tests.
  - `../ADRs/0014-allowed-binaries-additions-npm-ncu-java.md` — non-allowlisted binary refuses to exec.
- **Production ADRs:** `../../../production/adrs/` — no direct dependency; Phase 3 adversarials are phase-local.
- **Source design:**
  - `../final-design.md §"Test plan" §"Adversarial tests"` — the canonical category list.
  - `../final-design.md §"Risks (top 5)"` — Risk #2 (determinism flake), Risk #4 (audit-chain corruption), each motivates a corpus fixture.
  - `../High-level-impl.md §"Step 7"` — the row that pins this story's outputs.
- **Existing code:**
  - Every Phase 3 source file is the surface this corpus exercises; the highest-density targets are `src/codegenie/transforms/coordinator.py` (orchestrator), `src/codegenie/transforms/validation/test_validator.py` (S4-03 isolation), `src/codegenie/tools/npm.py` (S3-01 wrapper), `src/codegenie/recipes/registry.py` (S3-04 digest manifest), `src/codegenie/transforms/cve/store.py` (S2-06 snapshot).
- **Style reference:** `../../02-context-gather-layers-b-g/stories/S8-01-adversarial-corpus-completion.md` — the direct template; ADR-cite docstring discipline + fall-back-not-abort contract + per-fixture acceptance row.

## Goal

Land ≥ 30 adversarial fixtures + their tests under `tests/adv/` (and supporting fixtures under `tests/fixtures/`) so every load-bearing Phase 3 invariant trips a CI-gated red-fail when violated, and the combined p95 wall-clock stays under 90 s.

## Acceptance criteria

- [ ] Phase 3 ships at least **30 net-new adversarial fixtures** counted by enumerating `tests/adv/test_*.py` files added in this story (script `scripts/count_phase3_adversarial.py` introduced here; CI job `adversarial_corpus` in S7-07 asserts the floor of 30).
- [ ] The combined Phase 3 adversarial suite (`pytest tests/adv -m "not slow_adv"`) completes in **< 90 s p95** on the CI runner; the bench is recorded in the PR body.
- [ ] Each adversarial test docstring opens with `"""ADR-NNNN | Invariant: <one-sentence>"""` so `pytest --collect-only -q | grep ADR-` yields one line per test.
- [ ] At least one fixture per ADR (0005, 0007, 0008, 0009, 0010, 0011, 0012, 0013, 0014) exists. Cross-check at PR time via the docstring grep.
- [ ] The five lockfile policy violation types each get **both** a blocked-without-flag test (exit 7) and an allowed-with-flag test (exit 0 when `--allow-policy-violations=<type>` is set). That's 10 tests.
- [ ] The following named tests exist and are green:
  - [ ] `test_npm_wrapper_rejects_scripts_enabled.py` — wrapper raises `NpmScriptsEnabled` when caller omits `--ignore-scripts` (S3-01 invariant).
  - [ ] `test_postinstall_rce_blocked_by_wrapper.py` — `postinstall-rce-attempt` bundle from S7-01 attempts to run hostile `preinstall` script; the wrapper-level `--ignore-scripts` blocks it *before* subprocess starts; assert no file appears under `/tmp/pwned`.
  - [ ] `test_test_profile_refuses_scoped_network_without_flag.py` — caller passes `network="scoped"` to `run_in_sandbox` without `--allow-test-network` propagated through; raises `TestNetworkOptInRequired`.
  - [ ] `test_test_execution_filesystem_isolation.py` — test command writes to `/etc/foo`; wrapper rejects; exit non-zero.
  - [ ] `test_test_execution_network_default_none.py` — test command attempts DNS lookup; with default `network=none`, lookup fails with `ENOTFOUND`; signature scan triggers `signal_escalate`; exit 8.
  - [ ] `test_test_execution_wall_clock_bounded.py` — test that sleeps 600 s with overlay budget 300 s; wrapper terminates at budget; exit non-zero with `wall_exceeded` signal.
  - [ ] `test_test_execution_pid_bounded.py` — test forks 100 processes with pid budget 32; wrapper terminates; signal recorded.
  - [ ] `test_test_execution_memory_bounded.py` — test allocates 4 GB with memory budget 1.5 GB; wrapper terminates.
  - [ ] `test_test_execution_fork_bomb_bounded.py` — `:(){ :|:& };:` payload; pid budget caps; wrapper terminates without taking down the runner.
  - [ ] `test_openrewrite_stub_isolation.py` — `OpenRewriteEngineStub` invoked with `network=none`; assert no Maven Central reach-through (no DNS, no socket); assert no file written outside worktree (S6-01 invariant).
  - [ ] `test_git_hooks_disabled_during_branch_write.py` — repo has a hostile `.git/hooks/pre-commit` that writes a flag file; `PatchBranchWriter` invokes git with `--no-verify` or hooks disabled; flag file does not appear.
  - [ ] `test_signing_key_absent_no_error.py` — repo has `commit.gpgsign=true` but no signing key; `PatchBranchWriter` writes the branch without failing (signing is best-effort, never required in Phase 3).
  - [ ] `test_branch_refuses_dirty_tree.py` — worktree has uncommitted changes; orchestrator refuses; `branch.refused_dirty_tree` audit event emitted.
  - [ ] `test_branch_refuses_existing_branch.py` — target branch `codegenie/vuln-fix/<cve-id>-<sha>` already exists; orchestrator refuses; `branch.refused_exists` emitted.
  - [ ] `test_audit_chain_integrity_holds_across_phase3_events.py` — every Phase-3 event-type appends correctly; chain verification succeeds at run end.
  - [ ] `test_audit_chain_break_observability.py` — tampered chain head from a prior run; remediate detects, emits `audit.chain_break.detected` exactly once, **run continues** (exit 0 on the happy path; chain-break is observability, never abort).
  - [ ] `test_no_credentials_in_subprocess_env.py` — set credentials in parent env; assert no `transforms/` subprocess invocation includes them.
  - [ ] `test_phase3_fence_no_llm_imports.py` — AST scan of `src/codegenie/transforms/` and `src/codegenie/recipes/`; forbidden imports absent.
  - [ ] `test_phase3_no_subprocess_direct.py` — AST scan; no `subprocess.run`/`Popen` outside `src/codegenie/exec.py` and `src/codegenie/tools/`.
  - [ ] `test_cve_snapshot_hash_mismatch_rejected.py` — corrupt a snapshot's content; `CveFeedReader` raises `CveSnapshotIntegrityError`; exit 11.
  - [ ] `test_cve_snapshot_signature_tampering_advisory_only.py` — corrupt signature only (content intact); reader logs warning, marks `provenance.signature_verified=False`, **does not refuse** (best-effort signature per ADR-0008).
  - [ ] `test_cve_retraction_marks_evidence_stale.py` — synthetic retraction; `CveRetractionProbe` appends `evidence_stale.marked` to prior run's audit chain.
  - [ ] `test_recipes_digests_yaml_drift_breaks_load.py` — recipe content edited without `recipes/digests.yaml` update; `RecipeRegistry` raises `RecipeNotInDigestManifest`.
  - [ ] `test_tools_digests_yaml_drift_breaks_install.py` — `npm` binary on `$PATH` has a different SHA-256 than `tools/digests.yaml`; install step fails loud.
  - [ ] `test_engine_availability_snapshot_consistency.py` — between selector and transform, `RemediationAttempt.engine_availability` does not change; even when the test deletes `java` from `$PATH` mid-run, the captured snapshot is what the transform reads (Gap 6).
  - [ ] `test_cache_replay_back_references_original_chain_head.py` — second run hits the lockfile cache; `cache.replay` event references the *original* chain head, not the current one.
  - [ ] `test_allowed_binaries_blocks_unknown.py` — caller asks `run_in_sandbox` to invoke `wget`; raises `BinaryNotAllowed`.
  - [ ] `test_trust_score_strict_and_no_partial_credit.py` — three of four binary signals are `True`, one is `False`; `TrustScorer.score()` returns `binary=False` (no partial credit).
  - [ ] `test_signal_escalate_honest_failure_no_silent_widening.py` — test fails with `ENOTFOUND`; the architecture **does not** silently widen sandbox to `scoped`; exit 8; operator must re-run with `--allow-test-network` (ADR-0005 invariant).
- [ ] `scripts/count_phase3_adversarial.py` is a < 60-LOC pure-stdlib script that walks `tests/adv/` (excluding Phase 0/1/2 inherited tests) and prints `Phase 3 adversarial fixtures: N`; CI job in S7-07 asserts N ≥ 30.
- [ ] Every supporting fixture under `tests/fixtures/adv/` is ≤ 1 MB on disk (large in-memory payloads constructed at test time via factories, not committed as blobs).
- [ ] No new top-level dep introduced (`pyproject.toml` unchanged); stdlib + Phase 1/2/3 deps only.
- [ ] Slow tests (> 5 s wall) carry `pytest.mark.slow_adv` and are excluded from the default `pytest tests/adv -m "not slow_adv"` run.

## Implementation outline

1. **Inventory pass.** List the ≥ 30 tests this story owns from the acceptance-criteria checklist + the architecture's enumeration. Build a worksheet `(test_name, ADR, owning_subsystem, owning_fixture)`. Cross-reference with `tests/adv/` from Phase 2; do not duplicate tests that were already shipped against Phase 0/1/2 invariants. Phase 3 only re-asserts the **subset** that is at risk under the new components.
2. **For each test:**
   - Add the test file under `tests/adv/test_<scenario>.py` with the ADR-cite docstring.
   - Add supporting fixtures under `tests/fixtures/adv/<scenario>/` (single file where possible; multi-file only when the scenario demands it).
   - Assert the **fall-back / refuse-loudly** behavior, not just the raise. The contract is *the run exits with the documented code AND emits the structured event*; a test that asserts only one of the two passes for the wrong reason.
3. **The `test_audit_chain_break_observability.py`** is the highest-leverage chain-integrity test. Stage: (a) run `codegenie remediate` once on the `express` fixture to produce a baseline run record; (b) programmatically rewrite the previous run's `chain_head` field to a wrong BLAKE3; (c) run remediate a second time; (d) capture structlog; (e) assert `audit.chain_break.detected` fires exactly once; (f) assert exit code is 0 (chain break is observability, not abort); (g) assert the second run's `previous_hash` records the *broken* hash for forensics.
4. **The `test_no_credentials_in_subprocess_env.py`** uses `monkeypatch.setenv` to set credentials in `os.environ`, runs a remediate against the `express` fixture, and inspects audit records (every `recipe.engine.invoked` / `npm.install.run` / `tests.executed` event records sanitized env keys). The assertion is the negative: each credential key is **not in** any subprocess env.
5. **The `test_phase3_fence_no_llm_imports.py` + `test_phase3_no_subprocess_direct.py`** are AST scans. They walk `src/codegenie/transforms/` + `src/codegenie/recipes/` via `ast.parse`, collect import nodes, and assert the forbidden set is empty. The fence test is the runtime version of S1-09's static fence; both must hold.
6. **The `test_engine_availability_snapshot_consistency.py`** uses a custom `RecipeEngine` stub registered for this test only, whose `available()` returns `True` on first call and `False` on subsequent calls. Run remediate; assert the orchestrator captured `True` at entry (in `RemediationAttempt.engine_availability`) and the transform reads the snapshot rather than re-calling `available()`. This is Gap 6's verification.
7. **The five-violation × allowed/blocked matrix** (10 tests) is the most repetitive surface. Factor a parametrized base test `test_lockfile_policy_violation_<type>_{blocked,allowed}.py` that takes `(violation_type, flag_value, expected_exit)` and asserts. Each violation type gets its own fixture under `tests/fixtures/adv/lockfile_<violation_type>/`.
8. **`scripts/count_phase3_adversarial.py`**: one function, walks `tests/adv/`, filters by `test_*.py` newly added by this story (compare against a baseline list of Phase 0/1/2 inherited tests embedded in the script), prints `Phase 3 adversarial fixtures: N`. CI asserts `N >= 30`.
9. **Wall-clock budget pass.** After all tests are green, `pytest tests/adv --durations=20 -m "not slow_adv"`. Any test > 5 s gets `pytest.mark.slow_adv` (excluded from default CI; nightly only) or a perf fix. Common slow culprits: real subprocess invocations of `npm install` against the mirror — for the adversarial path, prefer stubbing at the `tools.npm.run` seam rather than running real `npm`.

## TDD plan — red / green / refactor

### Red — write the failing test first

Start with `test_audit_chain_break_observability.py` (most cross-cutting; exercises orchestrator + audit writer + structlog + lifecycle).

Path: `tests/adv/test_audit_chain_break_observability.py`

```python
"""ADR-0010 | Invariant: tampered chain_head logs `audit.chain_break.detected` once and never aborts the run."""

def test_audit_chain_break_logs_but_continues(tmp_path, bundle_fixture, npm_mirror_url, structlog_capture, run_remediate) -> None: ...
def test_audit_chain_break_records_broken_hash_for_forensics(tmp_path, bundle_fixture, npm_mirror_url, run_remediate) -> None: ...
```

Path: `tests/adv/test_postinstall_rce_blocked_by_wrapper.py`

```python
"""S3-01 + ADR-0014 | Invariant: --ignore-scripts wrapper-level invariant blocks postinstall RCE before subprocess starts."""

def test_postinstall_payload_never_executes(tmp_path, bundle_fixture, npm_mirror_url, run_remediate) -> None: ...
def test_wrapper_rejects_scripts_enabled_at_call_site() -> None: ...
```

Path: `tests/adv/test_signal_escalate_honest_failure_no_silent_widening.py`

```python
"""ADR-0005 | Invariant: a test failing with ENOTFOUND exits 8 and does NOT silently widen sandbox to `scoped`."""

def test_enotfound_exits_8_with_escalation_json_on_disk(tmp_path, bundle_fixture, npm_mirror_url, run_remediate) -> None: ...
def test_no_silent_sandbox_widening_in_audit_log(tmp_path, bundle_fixture, npm_mirror_url, run_remediate) -> None: ...
```

Path: `tests/adv/test_engine_availability_snapshot_consistency.py`

```python
"""Gap 6 | Invariant: engine.available() is captured once at orchestrator entry; transform reads the snapshot, not the live result."""

def test_selector_and_transform_see_same_availability(monkeypatch, bundle_fixture, npm_mirror_url, register_test_engine, run_remediate) -> None: ...
def test_snapshot_persists_across_environmental_flux(monkeypatch, bundle_fixture, npm_mirror_url, register_test_engine, run_remediate) -> None: ...
```

Path: `tests/adv/test_lockfile_policy_violation_parametrized.py`

```python
"""ADR-0007 | Invariant: each typed lockfile-policy violation blocks without flag (exit 7) and unblocks with --allow-policy-violations=<type> (exit 0)."""

@pytest.mark.parametrize("violation_type", ["RegistryRedirect", "MissingIntegrity", "LifecycleScriptDeclared", "PublishConfigOverride", "ResolutionsRedirect"])
def test_blocked_without_flag(violation_type: str, tmp_path, bundle_fixture, npm_mirror_url, run_remediate) -> None: ...

@pytest.mark.parametrize("violation_type", ["RegistryRedirect", "MissingIntegrity", "LifecycleScriptDeclared", "PublishConfigOverride", "ResolutionsRedirect"])
def test_allowed_with_flag(violation_type: str, tmp_path, bundle_fixture, npm_mirror_url, run_remediate) -> None: ...
```

Each test red-fails initially because the supporting fixture doesn't exist or the test infrastructure (`run_remediate`, `register_test_engine`, `structlog_capture`) hasn't been added to `conftest.py`. Green when the fixture + the production code (already landed in earlier stories) connect correctly.

### Green — make each one pass

The production code is already shipped by earlier stories; this story's "green" is about (a) constructing the right hostile fixture and (b) asserting against the right structlog event / exit code / on-disk artifact. The most common first failure is the assertion shape — e.g., the wrapper raises `NpmScriptsEnabled` but the test expected `ScriptsBlocked`. Read the production exception names from S3-01 / S4-01 / S2-06 before writing the assertion.

For the fence + no-subprocess AST scans, green is reached when no forbidden import is detected. If a forbidden import surfaces (e.g., someone snuck `import requests` into `transforms/cve/syncer.py`), the fix is to remove the import, not relax the test.

For the test-execution isolation suite (filesystem, network, wall, pid, memory, fork-bomb), green requires the S4-03 + ADR-0005 overlay machinery to actually enforce the budgets. If a budget isn't enforced (e.g., the wall-clock timeout doesn't fire), the fix is in the wrapper (S3-01) or `run_in_sandbox` (S1-06), not in the test. Surface as a Step-3/4 follow-up in the PR body.

### Refactor — clean up

After green:

- **Wall-clock pass.** `pytest tests/adv --durations=20 -m "not slow_adv"` — anything > 5 s gets `slow_adv` or a perf fix.
- **De-duplicate fixtures.** If two adversarials reuse the `express` baseline + a small mutation, share the bundle; do not commit a near-duplicate.
- **Confirm ADR-cite docstrings** for every new test (`pytest --collect-only -q | grep ADR-` yields ≥ 30 lines).
- **Run `scripts/count_phase3_adversarial.py`** locally; assert ≥ 30 before opening the PR.
- **Verify no test invokes the real internet.** `unshare -rn pytest tests/adv` on Linux (or document the test list in the PR body) confirms offline-only.
- **Confirm the `[slow_adv]` marker is registered** in `pyproject.toml` (S7-07 wires the marker into the test config).

## Files to touch

| Path | Why |
|---|---|
| `tests/adv/test_npm_wrapper_rejects_scripts_enabled.py` | S3-01 wrapper invariant. |
| `tests/adv/test_postinstall_rce_blocked_by_wrapper.py` | End-to-end; `postinstall-rce-attempt` bundle from S7-01. |
| `tests/adv/test_test_profile_refuses_scoped_network_without_flag.py` | ADR-0005 overlay opt-in invariant. |
| `tests/adv/test_test_execution_filesystem_isolation.py` | Overlay filesystem dimension. |
| `tests/adv/test_test_execution_network_default_none.py` | Overlay network-none default + signal-escalate trigger. |
| `tests/adv/test_test_execution_wall_clock_bounded.py` | Overlay wall budget. |
| `tests/adv/test_test_execution_pid_bounded.py` | Overlay pid budget. |
| `tests/adv/test_test_execution_memory_bounded.py` | Overlay memory budget. |
| `tests/adv/test_test_execution_fork_bomb_bounded.py` | Overlay pid budget + structural defense. |
| `tests/adv/test_openrewrite_stub_isolation.py` | S6-01 isolation. |
| `tests/adv/test_git_hooks_disabled_during_branch_write.py` | S5-04 hooks-disabled invariant. |
| `tests/adv/test_signing_key_absent_no_error.py` | S5-04 best-effort signing. |
| `tests/adv/test_branch_refuses_dirty_tree.py` | S5-04 refusal. |
| `tests/adv/test_branch_refuses_existing_branch.py` | S5-04 refusal. |
| `tests/adv/test_audit_chain_integrity_holds_across_phase3_events.py` | ADR-0010 happy-path chain integrity. |
| `tests/adv/test_audit_chain_break_observability.py` | ADR-0010 chain-break observability. |
| `tests/adv/test_no_credentials_in_subprocess_env.py` | No-secrets invariant (re-asserted at Phase 3). |
| `tests/adv/test_phase3_fence_no_llm_imports.py` | ADR-0013 fence (runtime AST scan). |
| `tests/adv/test_phase3_no_subprocess_direct.py` | Subprocess discipline AST scan. |
| `tests/adv/test_cve_snapshot_hash_mismatch_rejected.py` | ADR-0008 content-hash gate. |
| `tests/adv/test_cve_snapshot_signature_tampering_advisory_only.py` | ADR-0008 best-effort signature. |
| `tests/adv/test_cve_retraction_marks_evidence_stale.py` | ADR-0009. |
| `tests/adv/test_recipes_digests_yaml_drift_breaks_load.py` | ADR-0011 recipe digest. |
| `tests/adv/test_tools_digests_yaml_drift_breaks_install.py` | Phase 2 ADR-0004 + ADR-0014. |
| `tests/adv/test_engine_availability_snapshot_consistency.py` | Gap 6. |
| `tests/adv/test_cache_replay_back_references_original_chain_head.py` | ADR-0010 cache replay back-ref. |
| `tests/adv/test_allowed_binaries_blocks_unknown.py` | ADR-0014. |
| `tests/adv/test_trust_score_strict_and_no_partial_credit.py` | ADR-0013 strict-AND. |
| `tests/adv/test_signal_escalate_honest_failure_no_silent_widening.py` | ADR-0005 honest-failure invariant. |
| `tests/adv/test_lockfile_policy_violation_parametrized.py` | ADR-0007 five-type × {blocked, allowed}. |
| `tests/fixtures/adv/<scenario>/` (multiple) | Supporting hostile fixtures. |
| `tests/adv/conftest.py` (extend) | `run_remediate`, `register_test_engine`, `structlog_capture` fixtures. |
| `scripts/count_phase3_adversarial.py` | CI helper; < 60 LOC stdlib. |

## Out of scope

- **The fixture portfolio itself.** S7-01 ships `tests/fixtures/repos_bundles/` + the mirror; this story consumes them.
- **The determinism canary test.** S7-03 lands `test_byte_identical_diff_5x.py`.
- **The perf canaries.** S7-04.
- **The Phase-2 regression hard-gate.** S7-05.
- **The Phase-4 handoff contract test.** S7-06.
- **CI workflow wiring.** S7-07 wires the `adversarial_corpus` job; this story lands the tests + the count script.
- **New production code.** If a test red-fails because the production code doesn't enforce the invariant, surface as a Step-3/4/5/6 follow-up. This story does not extend production code; it only encodes the contract.
- **Phase 0/1/2 inherited adversarials.** Those run as part of S7-05 (the Phase-2 regression hard-gate); this story's count and budget cover Phase 3 net-new only.

## Notes for the implementer

- **Phase 2's S8-01 is the direct template.** Read it once before starting; the structural pattern (ADR-cite docstring, fall-back-not-abort contract, per-fixture acceptance row, `slow_adv` marker discipline, count-script CI gate) is identical. Phase 3's differences are scope (different invariants, different exit codes, different ADRs) — not shape.
- **"Refuse loudly, do not crash" is the universal contract.** A test that asserts only the exit code passes if the run crashes with an unhandled exception (pytest sees a non-zero exit and concludes "test passed"); the assertion **must** also verify the structured audit event was emitted. Both layers hold or the test is fictional.
- **Verify each test's red by mutating production locally.** If you ship a test that silently passes for the wrong reason (e.g., the orchestrator aborts and the test catches the exception as success), the CI gate is fictional. Mutate the production code locally (comment out the wrapper check, e.g.) and watch the test red-fail; revert.
- **`slow_adv` is a knife, not a refuge.** Mark a test slow only if it cannot be made fast without losing coverage. The nightly job runs them; do not let `slow_adv` become a dumping ground for tests that just take a few seconds — those get a perf fix.
- **`test_audit_chain_break_observability.py` is the highest-leverage chain-integrity test.** The event must fire exactly once per tampered run. If `verify_previous_chain_head()` is called multiple times in the lifecycle, the test will count multiple events and red-fail confusingly. Pin the call site to "exactly once at orchestrator startup, before the first transform helper runs."
- **`test_signal_escalate_honest_failure_no_silent_widening.py` is the load-bearing isolation invariant.** ADR-0005's `gate.signal_escalate` is explicitly *not* an auto-widening. A future PR that adds "if test failed with ENOTFOUND, retry with `network=scoped`" silently bypasses operator opt-in; this test is the gate against that drift. Make the assertion broad: scan the audit log for any `run_in_sandbox` invocation with `network != "none"` post-failure; if any exist, the test red-fails.
- **The AST-scan tests (fence + no-subprocess) must walk `__init__.py` files too.** A forbidden re-export buried in an `__init__.py` is the classic sneak-in path. The scan is recursive across every `.py` under `src/codegenie/transforms/` + `src/codegenie/recipes/`.
- **The five-violation parametrized matrix is the most repetitive surface; resist the urge to over-factor.** Parametrize at one level (the violation type); keep the assertion shape inline. Over-factoring (e.g., a fixture factory that takes a "violation type" enum and returns the right hostile lockfile) is harder to debug than five small explicit fixtures.
- **The mirror integrity test from S7-01 is the prerequisite.** If the mirror is broken, every adversarial that runs `npm install --package-lock-only` red-fails for the wrong reason. Confirm `tests/integration/test_fixture_mirror_pin_integrity.py` is green on `main` before merging this story.
- **Track the corpus count in the PR body.** "Phase 3 adversarial fixtures: 32" + the breakdown by ADR + the wall-clock p95 makes the merge a 30-second review. The count script is the source of truth; CI asserts the floor.
