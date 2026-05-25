# Validation report — Story S7-01 — Adversarial fixtures + adversarial tests

**Story:** [`../S7-01-adversarial-fixtures-and-tests.md`](../S7-01-adversarial-fixtures-and-tests.md)
**Validated:** 2026-05-25
**Validator:** `phase-story-validator` (single-agent inline mode)
**Validator agent run:** automated (`story-validation-corrector` scheduled task)
**Verdict:** **HARDENED**

## Summary

S7-01 is the **adversarial-suite consolidation** for Phase 5 Step 7 — the last code-bearing story in the phase before the perf gates (S7-02) and the operator CLI (S8). It owns three NEW fixture trees (`always-fails/`, `postinstall-exfil/`, and the additive extension of S4-02's `test-removes-test/`), four NEW adversarial tests (`test_patch_disables_test`, `test_postinstall_exfil`, `test_prompt_injection_in_error_log`, `test_test_added_informational`), a fifth distinct adversarial path (`test_always_fails_returns_failed_unrecoverable` — covers the sliding-window `failed_unrecoverable` distinct from the delta<0-driven path), and the collection-verification of three already-in-tree adversarial files owned by prior HARDENED stories (S2-01/S2-02 → `test_audit_chain_tamper.py`; S2-03 → `test_phase4_chain_head_compat.py`; S4-03 → `test_in_repo_policy_ignored.py`).

The draft was directionally correct — the right edge-case scope, the right `EVENT_SANDBOX_EGRESS_BLOCKED`/`prompt_injection.detected` intuition, the right fixture-portfolio shapes from `phase-arch-design.md §Fixture portfolio` — but carried **30 findings across all four critic lenses, 15 of them block-tier** that would have either failed at first import, proven nothing about the load-bearing properties they appeared to verify (the mutation-flip-passed AC was structurally inverted from what the gate actually does), or clobbered S4-02's GREEN fixture artifacts. The most consequential were:

1. **(consistency — block) `GateRunner.from_default_catalog(repo=repo)` doesn't exist.** Per [S5-02 HARDENED AC-CTOR-1](S5-02-gate-runner-retry-loop.md), the canonical constructor is **keyword-only** `GateRunner(*, client, gate, ledger, spec_builder, max_attempts=3, replan_hook=None)`. Draft TDD code calls a phantom factory → executor's first attempt is an `AttributeError`. Fix: AC-CTOR-1 + shared `gate_runner_factory` fixture mirroring [S6-05 HARDENED `_kvm_smoke_client_factory`](S6-05-kvm-smoke-and-weekly-cron.md) precedent.

2. **(consistency — block) `GateRunner.run` is `async def`; draft uses sync `def test_*`.** Per [S5-02 HARDENED AC-ASYNC-1](S5-02-gate-runner-retry-loop.md): `inspect.iscoroutinefunction(GateRunner.run) is True`. Sync invocation binds a coroutine; assertions vacuously succeed. Fix: AC-ASYNC-1 — every adversarial test using `GateRunner.run` is `async def`.

3. **(consistency — block) `runner.run(gate_id=...)` has wrong arity.** Per [S5-02 HARDENED](S5-02-gate-runner-retry-loop.md): the only signature is `async def run(self, ctx: GateContext) -> GateOutcome`. Draft passes `gate_id` as kwarg → `TypeError`. Fix: AC-RUN-CTX-1 wires a real `GateContext(workflow_id, run_id, prior_attempts, transform_output)` per [S1-04 HARDENED](S1-04-gates-contract-abc-models.md); `gate_id` is the `Gate.id` attribute owned by the gate instance.

4. **(consistency — block) `GateOutcome.gate_state` doesn't exist.** Per [S1-04 HARDENED §F](S1-04-gates-contract-abc-models.md): `GateOutcome` has `passed`, `state`, `retryable`, `attempt`, `signals`, `failing_signals`, `summary`. Draft asserts `result.gate_state == "failed_unrecoverable"` → `AttributeError`. Fix: AC-STATE-1 corrects to `outcome.state == "failed_unrecoverable" AND outcome.passed is False AND outcome.retryable is False` per S1-04 HARDENED cross-field invariant AC-CF-3.

5. **(test-quality / coverage — block) `mutation_flip_passed` AC is structurally inverted from how `StrictAndGate` works.** Draft claims: *"flipping `TestSignal.passed = True` while keeping `delta_test_count = -1` still results in `StrictAndGate.evaluate(...).passed is False` because the scorer reads the signal-level boolean computed from the same field."* That is the **opposite** of how the strict-AND scorer behaves. Per [S4-05 HARDENED](S4-05-strict-and-gate-equivalence.md) + production [ADR-0008](../../../../production/adrs/0008-objective-signal-trust-score.md): `StrictAndGate` evaluates `all(signal.passed for signal in populated_signals)` — it reads `signal.passed` directly. Flipping `passed=True` would let the gate PASS. The protection lives in the **collector** (per ADR-0015: `TestSignal.passed = False when delta_test_count < 0`), not in the gate. Following the draft AC, an implementation could legitimately set `passed=True` regardless of `delta_test_count` and the AC would still claim "the scorer protects us" — false. This is the worst kind of test: it makes the executor feel safe while the real defense is unverified. Fix: AC-MUT-COLLECTOR-1 / AC-MUT-WITNESS-1 / AC-MUT-WITNESS-2 retarget to the COLLECTOR — a mutant `collect_test_signal` that ignores `pre_patch_inventory_path` is the failure mode to catch.

6. **(consistency — block) `tests/adversarial/test_audit_chain_tamper.py` is OWNED by S2-01 + S2-02 and already in tree, parametrized across 7 fields × 2 row types.** Per [S2-01 HARDENED AC-AT-1..-2](S2-01-retry-ledger-blake3-chain.md) + [S2-02 HARDENED AC-AT-3..-6](S2-02-pre-execute-marker-gap-1.md): the file ships parametrized tampers `{attempt_id, prev_hash, sandbox_run_id, outcome.summary, sandbox_spec_hash, started_at, type}` on both `attempt` AND `pre_execute` rows. S7-01 re-writing it would either clobber (regressing the parametrized coverage) or duplicate (creating two conflicting truths). Fix: AC-COLLECT-TAMPER-1 reduces to "the file exists, is collected, all parametrized cases pass under the consolidated suite"; the autouse import-check in `tests/adversarial/conftest.py` catches accidental rename.

7. **(consistency — block) Filename `test_phase4_chain_head_mismatch.py` is WRONG.** Per [S2-03 HARDENED AC-H-1 + Files-to-touch](S2-03-phase4-chain-head-compat.md): the file shipped GREEN is `test_phase4_chain_head_compat.py` (suffix `_compat`, NOT `_mismatch`). Story's Context + Out-of-scope references are stale. Fix: AC-COLLECT-PHASE4-1 corrects the filename; Out-of-scope row updated.

8. **(consistency — block) `tests/adversarial/test_in_repo_policy_ignored.py` is OWNED by S4-03 and already in tree, parametrized over six attack paths + symlink + digest-mismatch.** Per [S4-03 HARDENED](S4-03-trace-policy-cve-collectors.md): `AC-POLICY-ADV-PARAMETRIZE-1` covers all attack vectors plus a `builtins.open`/`pathlib.Path.open`/`read_text`/`read_bytes` monkeypatch spy. Draft AC-6 ("is referenced from the suite and re-run in this story's pytest collection to confirm it still passes") is a non-assertion — pytest discovery does this automatically. Fix: AC-COLLECT-POLICY-1 makes the collection guarantee STRUCTURAL via the conftest autouse import-check at module-import time (not at runtime — catches the rename/move regression class).

9. **(consistency / coverage — block) Three `tests/fixtures/repos/*` directories already have S4-02-owned artifacts; draft would clobber them.** Per [S4-02 HARDENED Files-to-touch](../S4-02-test-signal-with-inventory-delta.md): `tests/fixtures/repos/test-removes-test/pre_inventory.json` (42-test baseline) AND `tests/fixtures/repos/test-removes-test/sandbox_run/logs/stdout.log` already exist. S4-02 also owns `tests/fixtures/repos/test-adds-regression/` (delta>0 informational path). Draft Implementation §1 says "Copy `tests/fixtures/repos/hello-node/` three times into `always-fails/`, `postinstall-exfil/`, `test-removes-test/`" — clobbering S4-02's GREEN artifacts. The numbers also disagree (draft: "5-test baseline"; S4-02: 42-test). Fix: AC-FIX-COEXIST-1..-3 — `test-removes-test/` EXTENDED (not recreated; pre_inventory.json + stdout.log BYTE-IDENTICAL); `test_test_added_informational` REUSES `test-adds-regression/`; baseline numbers ALIGN with S4-02's 42-test fixture.

10. **(consistency — block) `tests/fixtures/repos/always-fails/` has NO test consumer.** Draft lands the fixture but no AC exercises it. Fix: AC-FIX-ALWAYS-1 + AC-ALWAYS-FAILS-1..-4 — add `test_always_fails_returns_failed_unrecoverable.py` that targets the `always-fails/` fixture via build+test+trace-fail path; distinct from `test_patch_disables_test`'s delta-driven path (covered by sliding-window detector per S5-02 HARDENED AC-SLIDE-1).

11. **(consistency — block) `details: dict[str, str | int | bool]` constrains `new_endpoints` to NOT be a list.** Per [S1-03 HARDENED](S1-03-objective-signals-models.md) + ADR-0014 + [S4-02 HARDENED catalog discipline](../S4-02-test-signal-with-inventory-delta.md): `_SignalBase.details` is typed `dict[str, str | int | bool]` — no `list`. Draft AC-5 implies a list. Fix: AC-EXFIL-DETAILS-1 (comma-joined sorted string, matching S4-02 `failing_tests` convention) + AC-EXFIL-DETAILS-2 (`new_endpoints_count: int`) + AC-CAT-MEMBER-1 (catalog-membership verified at test-import time).

12. **(consistency — block) `sandbox.egress.blocked` must be a `Final[str]` constant, not a string literal.** Per [S1-01 HARDENED + S4-03 HARDENED + S6-04 HARDENED](S6-04-auto-detect-macos-fallback.md): every observable event is a constant in `sandbox/logging.py`, alphabetized in sorted `__all__`. Fix: AC-EXFIL-EVT-1 imports `EVENT_SANDBOX_EGRESS_BLOCKED` (S4-03 owns; Notes carryforward if absent) AND uses the [S5-02 HARDENED AC-OBS-1](S5-02-gate-runner-retry-loop.md) `structlog.testing.capture_logs()` precedent via the new `EventSpy` Decorator.

13. **(consistency — block) `AuditChainCorrupted` is raised at `RetryLedger.__init__`, not inside `GateRunner.run`.** Per [S2-01 HARDENED AC-RR-1..-4](S2-01-retry-ledger-blake3-chain.md) + S5-02 HARDENED AC-CTOR-1: the caller constructs `RetryLedger(...)` and passes it as a kwarg to `GateRunner(...)`. Corrupt ledger → `AuditChainCorrupted` at ledger construction → GateRunner never instantiated → no sandbox call. Draft's "restarts GateRunner against the same run-id, asserts AuditChainCorrupted is raised before any sandbox call" was directionally right but mis-located the construction site. (Folded into S2-01/S2-02 ownership per #6 above; framing corrected in Notes-for-implementer #7.)

14. **(consistency — block) `tests/adversarial/__init__.py` for pytest collection is wrong.** Pytest's `conftest.py` + `testpaths` discovery already collects `tests/adversarial/`. Adding `__init__.py` makes the directory a Python package, changes `rootdir` semantics, breaks `tmp_path` collision avoidance, and is a documented pytest anti-pattern. Other phase test directories (`tests/sandbox/`, `tests/gates/`, `tests/schema/`) confirm: none have `__init__.py`. Fix: AC-COLLECT-CONF-1 + AC-COLLECT-NO-INIT-1 + AC-COLLECT-PYPROJECT-1 — `conftest.py` (not `__init__.py`) is the collection seam; `testpaths` add (one-line YAML edit) if absent.

15. **(design / consistency — block) `tests/fixtures/load.py` mixes test code with fixture data.** Per [S6-05 HARDENED `tests/integration/sandbox/_helpers.py` precedent](S6-05-kvm-smoke-and-weekly-cron.md): test helpers live at `tests/_helpers/`. Co-locating code inside `tests/fixtures/` (the data tree) risks accidental pytest collection if a conftest is dropped under `tests/fixtures/` later. Fix: AC-LOAD-LOC-1 — `tests/_helpers/fixtures.py`; AC-LOAD-IMPORT-1 — renamed `apply_fixture_patch` (verb-form precedent from S6-03 `load_pinned_digests`); AC-LOAD-PURITY-1 — module-purity AST scan mirrors S2-01 / S4-01.

The remaining 15 findings were harden- or nit-tier and would not block executor success but each tightens an AC, a test, or a forward-compat seam:

16. **(coverage — harden) No AC IDs.** Every sibling HARDENED story uses `AC-XX-N` IDs. Rewritten ACs carry IDs grouped A–I.

17. **(test-quality — harden) TDD plan covers only 1/6 test files.** AC-TDD-RED-1..-7 require one Red test per file, each committed before the matching Green.

18. **(test-quality — harden) Prompt-injection test boundary — exercise the Hexagonal port, not synthesize a SandboxRun.** Per [S5-03 HARDENED](S5-03-phase4-prior-attempts-kwarg-fence.md): `FenceWrapper.compose_prior_attempts(*, prior_attempts: list[AttemptSummary]) -> str` is the port. AC-INJ-PORT-1 / AC-INJ-REDACT-1 / AC-INJ-EVENT-1 / AC-INJ-NEGATIVE-1 + AC-INJ-LOOP-1 retarget the test to a pure unit test against the port; no GateRunner, no SandboxClient.

19. **(test-quality — harden) `fake_sandbox_run` factory needs newtype constructors.** Per CLAUDE.md "Newtype identifiers" + [S5-02 HARDENED AC-NT-1](S5-02-gate-runner-retry-loop.md). AC-FAKE-NT-1.

20. **(coverage — harden) Catalog-membership ACs for new `details` keys.** Per ADR-0014 + S4-02 HARDENED `_TEST_DETAIL_KEYS` discipline. AC-CAT-MEMBER-1 at test-import time.

21. **(consistency — harden) `Status` line `Ready (HARDENED 2026-05-25)` form** — mirrors every sibling HARDENED story.

22. **(coverage — harden) `Out of scope` row corrections** for the two filename + ownership corrections (#6, #7, #8).

23. **(design — harden) Decorator/Spy pattern for the audit-event capture across tests.** Per [S5-05 HARDENED AC-SPY-1 (`ReplanHookSpy`)](S5-05-retry-recovers-integration.md): three concrete consumers (`test_postinstall_exfil`, `test_prompt_injection_in_error_log`, `test_always_fails_returns_failed_unrecoverable`) clear the rule-of-three. AC-EVT-SPY-1 / AC-EVT-SPY-2 — `tests/_helpers/events.py::EventSpy`.

24. **(coverage — harden) `mutation_flip_passed` retargeted to the collector as a teaching witness.** Per CLAUDE.md Rule 9. AC-MUT-WITNESS-1 / -2 + a paired docstring explaining why the field, not the boolean, is load-bearing.

25. **(consistency — harden) `_fixture_patch.diff` byte-stability fence.** AC-PATCH-STABLE-1 — `tests/schema/test_fixture_patches_byte_stable.py` re-runs `git apply --check` + `git diff --stat` against committed goldens.

26. **(coverage — harden) `_fixture_patch.diff` path collides with `.codegenie/`.** `.codegenie/` is the on-disk output namespace per CLAUDE.md. AC-PATCH-LOC-1 — patches live at `tests/fixtures/repos/<name>/.fixture_patch/_patch.diff` (NOT inside `.codegenie/`); AC-PATCH-GITIGNORE-1 — `.fixture_patch/` committed; fixture's own `.codegenie/` `.gitignore`d.

27. **(test-quality — harden) `apply_fixture_patch` isolates side-effects.** Per CLAUDE.md "Functional core / imperative shell": imperative shell uses `shutil.copytree` + `subprocess.run(["git", "apply", ...])`; paired pure `_resolve_patch_path` is `Path`-only. AC-PURE-1, AC-PURE-2.

28. **(consistency — harden) `Effort: L` kept** — volume verified.

29. **(coverage — harden) Pytest `addopts --cov-fail-under=85`** — narrow runs need `--no-cov`. AC-COV-1, AC-PG-1.

30. **(coverage — nit) Effort annotation** — phase README convention, no change.

**No `RESCUE`-tier findings.** The goal traces cleanly to phase exit criteria (the seven Edge-case rows + the §Adversarial tests bullets); every gap was patchable by fixing API references against the seven HARDENED sibling reports, correcting the mutation-witness target (collector, not gate), pinning fixture coexistence with S4-02, and locating helpers at `tests/_helpers/`.

**No Stage-3 research needed.** Every gap was answerable from the seven HARDENED sibling reports (S1-04, S2-01, S2-02, S2-03, S4-02, S4-03, S5-02, S5-05 — and S5-03 for the FenceWrapper port), the seven Phase-5 ADRs (0001/0007/0011/0012/0013/0014/0015), production ADR-0008 (objective-signal trust-score — the strict-AND surface), [phase-arch-design.md §Edge cases / Adversarial tests / Fixture portfolio / Data model], CLAUDE.md commitments (Extension by addition, Newtype identifiers, Functional core / imperative shell, Rule 9, Rule 11, Rule 12), and codebase precedents in `src/codegenie/sandbox/signals/` (catalog discipline) + `src/codegenie/hashing.py` (BLAKE3 chokepoint) + `src/codegenie/audit.py` (chained anchors). No external arXiv / library-docs lookup needed.

## Context Brief (Stage 1)

### Story snapshot

- **Goal (verbatim, hardened):** Ship three adversarial fixture repos (extending the two already-in-tree fixture trees `test-removes-test/` + `test-adds-regression/` additively; creating `always-fails/` + `postinstall-exfil/` from `hello-node/` baseline), one shared fixture-loader helper at `tests/_helpers/fixtures.py`, one shared `EventSpy` helper at `tests/_helpers/events.py`, one adversarial `conftest.py`, and four (or five) NEW adversarial pytest files such that every Edge-case row 5/6/7/16/17 listed in §Adversarial tests has an executable, deterministic test that fails the gate as the architecture specifies, AND the suite verifies the three already-in-tree adversarial files collect and pass under the consolidated run.
- **Non-goals (Out-of-scope, hardened):** Re-implementing the three already-in-tree adversarial files; any change to `FenceWrapper`; perf tests (S7-02); `CostEmitter` (S7-03); concurrent-remediate `flock` (S7-04); adding new event constants (S4-03 / S5-03 own); adding `_TRACE_DETAIL_KEYS` entries (S4-03 owns); mutation testing of `StrictAndGate.evaluate` itself (wrong target — covered by AC-PD-COLLECTOR-MUT-1 and AC-MUT-WITNESS-1 at the collector boundary).

### Phase 5 exit criteria touched

- **Step 7 done-criteria (High-level-impl.md §Step 7):** "All adversarial tests pass; mutation-style negative checks (e.g., temporarily set `passed=True` on a TestSignal with `delta_test_count=-1` — gate must still fail because TrustScorer reads `passed`)" — this Step 7 line itself contains the bug Validation note #5 corrects. The story now retargets the mutation witness to the COLLECTOR; the Step 7 line's "gate must still fail because TrustScorer reads `passed`" is **factually wrong** and a Notes-for-implementer carryforward flags an amendment for `High-level-impl.md §Step 7`.
- **§Adversarial tests (arch lines 921–928):** six bullets. Two NEW tests this story owns (`test_patch_disables_test`, `test_postinstall_exfil`, `test_prompt_injection_in_error_log`, `test_test_added_informational`); plus the optional `test_always_fails_returns_failed_unrecoverable` if AC-ALWAYS-FAILS-1 is accepted in scope. Three OWNED-BY-PRIOR-STORIES (S2-01/S2-02, S2-03, S4-03) — collected, not written.
- **§Edge cases:** rows 5 (postinstall-exfil), 6 (test-removed), 7 (test-added informational), 10 (in-repo policy — owned), 11 (audit-chain tamper — owned), 12 (phase-4 chain-head mismatch — owned), 16 (prompt-injection), 17 (same-failing-3× → failed_unrecoverable).
- **§Fixture portfolio (arch lines 897–905):** `always-fails`, `postinstall-exfil`, `test-removes-test` (extended), `test-adds-regression` (reused).

### Load-bearing commitments touched

- **ADR-0001 (two-chokepoint sandbox seam):** adversarial tests route through the `GateRunner` chokepoint, never raw `client.execute`.
- **ADR-0007 (pre-execute marker):** every test that reaches `GateRunner.run` inherits the marker discipline by construction; AC-PD-LEDGER-1 asserts the interleaved `PreExecuteMarker` + `Attempt` row pattern.
- **ADR-0011 (no verdict cache):** `failed_unrecoverable` computed fresh per attempt — sliding-window detector per [S5-02 HARDENED AC-SLIDE-1](S5-02-gate-runner-retry-loop.md).
- **ADR-0012 (static env allowlist):** structural defense; `test_postinstall_exfil` verifies the runtime trace catches what escapes the allowlist envelope.
- **ADR-0013 (digest-pinned policy YAML):** `test_in_repo_policy_ignored.py` closes (owned by S4-03; this story collects).
- **ADR-0014 (extra=forbid + static-introspection):** `details` value type is `str | int | bool` (no list); banned-substring fence intact; per-collector `Final[frozenset[str]]` catalogs extended only by the owning collector's story.
- **ADR-0015 (asymmetric delta-policy):** load-bearing; AC-PD-COLLECTOR-MUT-1 + AC-MUT-WITNESS-1 verify the COLLECTOR is the load-bearing decision.
- **production [ADR-0008](../../../../production/adrs/0008-objective-signal-trust-score.md) (objective-signal trust-score):** `StrictAndGate.evaluate` reads `signal.passed` directly — the gate is the strict-AND multiplexer; the collector is the load-bearing decision.
- **CLAUDE.md "Extension by addition":** new files; three already-in-tree files unchanged; conftest autouse guard catches accidental edits.
- **CLAUDE.md "Newtype identifiers":** `RunId(...)`, `AttemptNumber(...)`, `SignalKind(...)` constructor form everywhere.
- **CLAUDE.md "Functional core / imperative shell":** `apply_fixture_patch` is imperative shell; `_resolve_patch_path` is pure; module-purity AST scan enforces.
- **CLAUDE.md "Fail loud":** `EventSpy.assert_emitted` raises `AssertionError` with clear message; never silent substring tolerance.
- **CLAUDE.md "Tests verify intent, not just behavior" (Rule 9):** mutation witness retargeted to the COLLECTOR — the field, not the boolean, is load-bearing.
- **CLAUDE.md "Match the existing convention" (Rule 11):** `tests/_helpers/` precedent from S6-05; AC-XX-N IDs from every sibling HARDENED story.

### Sibling-family lineage (Design-Patterns)

- **This story is the 7th consumer in Phase 5** of the Decorator-Spy + module-purity + `Final`-catalog + DI-via-keyword-only-constructor + `structlog.testing.capture_logs` stack. Each prior consumer (S2-01 / S2-02 / S4-01 / S4-02 / S4-03 / S5-02 / S5-05) shipped explicit consumers; this story consolidates the adversarial suite around them.
- **First consumer of `EventSpy`** (rule-of-three across `test_postinstall_exfil`, `test_prompt_injection_in_error_log`, `test_always_fails_returns_failed_unrecoverable` clears the threshold — extract the kernel at `tests/_helpers/events.py`).
- **First consumer of `apply_fixture_patch`** (rule-of-three across `test_patch_disables_test`, `test_postinstall_exfil`, `test_always_fails_returns_failed_unrecoverable` — extract at `tests/_helpers/fixtures.py`).
- **First consumer of `mutation_flip_collector_passed`** — extracted in `tests/adversarial/conftest.py` (only one direct consumer today: `test_patch_disables_test_collector_passes_under_mutant_collector`; documented as a teaching witness; do not extract further until rule-of-three is cleared).
- **First story that lands an `__init__.py`-FREE adversarial test directory** — establishes the convention reference for future phase adversarial directories.
- **Codebase precedent for fixture loading:** `apply_fixture_patch` mirrors the `shutil.copytree` + `subprocess.run(["git", "apply", ...])` pattern used by Phase 3 `tests/integration/transforms/*.py` integration tests (the precedent for tmp-dir-isolated fixture mutation).
- **Codebase precedent for event-spy:** `EventSpy` mirrors the Decorator shape from [S5-05 HARDENED `ReplanHookSpy`](S5-05-retry-recovers-integration.md) — wrap, observe, delegate. The hexagonal-port discipline is preserved.

### Prior validation history (if any)

- None for S7-01. This is the first validation pass.

## Four-critic findings (synthesized; Consistency > Coverage > Test-Quality > Design-Patterns priority)

### Coverage critic

| # | Severity | Finding | Resolution |
|---|---|---|---|
| C-1 | block | No AC IDs anywhere (vs. every sibling HARDENED story) | Rewritten ACs with `AC-XX-N` IDs grouped A–I |
| C-2 | block | `GateRunner.from_default_catalog(repo=repo)` is invented; HARDENED ctor is keyword-only | AC-CTOR-1 + `gate_runner_factory` shared fixture |
| C-3 | block | `runner.run(gate_id=...)` wrong arity; only `async def run(self, ctx: GateContext)` exists | AC-RUN-CTX-1 — real `GateContext(...)` |
| C-4 | block | `GateOutcome.gate_state` field doesn't exist; correct field is `state` | AC-STATE-1 |
| C-5 | block | `mutation_flip_passed` AC inverts how `StrictAndGate` works — gate would PASS the mutant | AC-MUT-COLLECTOR-1 / AC-MUT-WITNESS-1 / AC-MUT-WITNESS-2 retarget to COLLECTOR |
| C-6 | block | `test_audit_chain_tamper.py` owned by S2-01/S2-02 (parametrized 7 fields × 2 row types) | AC-COLLECT-TAMPER-1 — collect-only; no rewrite |
| C-7 | block | `test_in_repo_policy_ignored.py` collection is a non-assertion (pytest discovery automatic) | AC-COLLECT-POLICY-1 + AC-COLLECT-CONF-1 — autouse import-check |
| C-8 | block | Filename `test_phase4_chain_head_mismatch.py` wrong; should be `_compat.py` | AC-COLLECT-PHASE4-1 + Out-of-scope row + References block updated |
| C-9 | block | `tests/adversarial/__init__.py` is wrong (changes rootdir; pytest anti-pattern) | AC-COLLECT-NO-INIT-1 + AC-COLLECT-PYPROJECT-1 + AC-COLLECT-CONF-1 |
| C-10 | block | `test_test_added_informational` invents new fixture instead of reusing S4-02's `test-adds-regression/` | AC-FIX-COEXIST-3 + AC-INFO-FIXTURE-1 |
| C-11 | block | `tests/fixtures/repos/always-fails/` lands but no AC consumes it | AC-FIX-ALWAYS-1 + AC-ALWAYS-FAILS-1..-4 — new test file |
| C-12 | block | `sandbox.egress.blocked` referenced as string literal, not `Final[str]` constant | AC-EXFIL-EVT-1 — `EVENT_SANDBOX_EGRESS_BLOCKED` import |
| C-13 | block | `mutation_flip_passed` claim ("scorer reads boolean computed from same field") is false | Same fix as C-5 — retarget to COLLECTOR |
| C-14 | block | `AuditChainCorrupted` mis-located in `GateRunner.run`; raised at `RetryLedger.__init__` | Folded into C-6 ownership; framing corrected in Notes-for-implementer #7 |
| C-15 | harden | Dependency closure under-enumerated (S5-05 only); real closure is S2-01/S2-02/S2-03/S4-02/S4-03/S5-02/S5-03/S5-04/S5-05 | `Depends on:` line rewritten |
| C-16 | harden | `ADRs honored` line missing ADR-0001, ADR-0011, ADR-0012 | `ADRs honored:` line rewritten with seven ADRs |
| C-17 | harden | Catalog-membership ACs for new `details` keys (`new_endpoints`, `new_endpoints_count`) | AC-CAT-MEMBER-1 |
| C-18 | harden | `Validation notes` block convention missing | Added at top of story |
| C-19 | harden | `Status:` `Ready (HARDENED 2026-05-25)` form | Status updated |

### Test-quality critic

| # | Severity | Finding | Resolution |
|---|---|---|---|
| T-1 | block | TDD code uses `GateRunner.from_default_catalog(repo=repo)` — `ImportError`/`AttributeError` | Same fix as C-2 — AC-CTOR-1 |
| T-2 | block | TDD code uses `runner.run(gate_id="stage6_validate")` — `TypeError` | Same fix as C-3 — AC-RUN-CTX-1 |
| T-3 | block | TDD code asserts `result.gate_state` — `AttributeError` | Same fix as C-4 — AC-STATE-1 |
| T-4 | block | TDD code uses sync `def test_…` against `async def run` | AC-ASYNC-1 — `async def test_…` |
| T-5 | block | `test_sig.model_copy(update={"passed": True})` then asserts `delta_test_count == -1` — tautology | Same fix as C-5 — retarget to COLLECTOR |
| T-6 | block | `sandbox.egress.blocked` event has no structured-log capture pattern | AC-EXFIL-EVT-1 — `EventSpy.assert_emitted` |
| T-7 | block | Prompt-injection test over-couples (synthetic `SandboxRun` + Phase 4 internal walk) | AC-INJ-PORT-1..-4 — Hexagonal port boundary |
| T-8 | block | Audit-chain tamper TDD duplicates S2-02 AC-AT-3..-6 | Folded into C-6 — collect-only |
| T-9 | block | `test_test_added_informational` doesn't specify how patch produces delta=+1 | AC-INFO-COLLECTOR-1 — direct `collect_test_signal` invocation against S4-02 fixture |
| T-10 | block | No mutation witness for the COLLECTOR itself (the actual load-bearing decision) | AC-PD-COLLECTOR-MUT-1 + AC-MUT-WITNESS-1 |
| T-11 | harden | TDD plan covers only 1/6 (now 7) test files | AC-TDD-RED-1..-7 |
| T-12 | harden | `fake_sandbox_run` factory needs newtype constructors | AC-FAKE-NT-1 |
| T-13 | harden | `EventSpy` Decorator pattern not extracted (rule-of-three cleared) | AC-EVT-SPY-1 + AC-EVT-SPY-2 |
| T-14 | nit | `Effort: L` correct | No change |

### Consistency critic

| # | Severity | Finding | Resolution |
|---|---|---|---|
| K-1 | block | `GateRunner.from_default_catalog`/`run(gate_id=...)`/`gate_state` violate S5-02 + S1-04 HARDENED | Same fixes as C-2/C-3/C-4 |
| K-2 | block | Mutation-flip claim contradicts S4-05 HARDENED + ADR-0008 | Same fix as C-5 |
| K-3 | block | `test_audit_chain_tamper.py` re-write violates S2-01/S2-02 HARDENED ownership | AC-COLLECT-TAMPER-1 |
| K-4 | block | Filename `test_phase4_chain_head_mismatch.py` violates S2-03 HARDENED filename | AC-COLLECT-PHASE4-1 + filename corrections |
| K-5 | block | `test-removes-test/` fixture clobber violates S4-02 HARDENED byte-equality | AC-FIX-COEXIST-1 + AC-FIX-COEXIST-2 |
| K-6 | block | New fixture path for delta>0 violates S4-02 ownership of `test-adds-regression/` | AC-FIX-COEXIST-3 |
| K-7 | block | `details["new_endpoints"]` as list violates ADR-0014 / S1-03 HARDENED typing | AC-EXFIL-DETAILS-1 + AC-EXFIL-DETAILS-2 |
| K-8 | block | Event literal violates S1-01/S6-04/S4-03 HARDENED `Final[str]` pattern | AC-EXFIL-EVT-1 |
| K-9 | block | `tests/fixtures/load.py` location violates S6-05 HARDENED `tests/_helpers/` precedent | AC-LOAD-LOC-1 + AC-LOAD-PURITY-1 |
| K-10 | block | `tests/adversarial/__init__.py` violates pytest convention + phase pattern | AC-COLLECT-NO-INIT-1 |
| K-11 | harden | `Status` line lacks HARDENED suffix | Status updated |
| K-12 | harden | `Depends on:` lacks closure | Line rewritten with full closure |
| K-13 | harden | `ADRs honored:` lacks closure | Line rewritten with seven ADRs |
| K-14 | harden | `Validation notes` block missing | Added |
| K-15 | nit | High-level-impl.md §Step 7 itself contains the mutation-witness bug | Notes-for-implementer carryforward for upstream amendment |

### Design-patterns critic

| # | Severity | Finding | Resolution |
|---|---|---|---|
| D-1 | block | `mutation_flip_passed` AC is teaching scaffolding for the wrong property | AC-MUT-WITNESS-1 / -2 retarget to the COLLECTOR; docstring documents why field, not boolean, is load-bearing |
| D-2 | block | `tests/fixtures/load.py` co-locates code with data | AC-LOAD-LOC-1 — `tests/_helpers/fixtures.py` |
| D-3 | harden | `EventSpy` Decorator pattern not extracted; rule-of-three cleared by three consumers | AC-EVT-SPY-1 + AC-EVT-SPY-2 |
| D-4 | harden | Hexagonal-port boundary for FenceWrapper not exercised; test reaches into Phase 4 internals | AC-INJ-PORT-1 — port boundary only |
| D-5 | harden | Functional-core / imperative-shell split for `apply_fixture_patch` unenforced | AC-PURE-1 + AC-PURE-2 + AC-LOAD-PURITY-1 |
| D-6 | harden | `fake_sandbox_run` factory missing newtype discipline | AC-FAKE-NT-1 |
| D-7 | harden | No registry / catalog for fixture+test mapping — but YAGNI (only 5 tests); explicit better than premature abstraction | Surface as Note; do not mandate |
| D-8 | nit | `tests/adversarial/test_runner_ctor_keyword_only.py` AST fence | AC-CTOR-1 — covers it as one-AC-per-fence per S5-02 precedent |

## Conflict resolution (Consistency > Coverage > Test-Quality > Design-Patterns)

- **C-5 vs T-5 vs D-1** all converge on the same fix (retarget mutation witness to COLLECTOR) — no conflict, just three lenses on the same defect.
- **C-9 vs K-10** converge on no `__init__.py` — same fix.
- **C-11 vs scope:** AC-FIX-ALWAYS-1 adds a fifth NEW test (`test_always_fails_returns_failed_unrecoverable.py`) — Coverage demands it (the fixture without a test is structural waste); Consistency confirms (sliding-window `failed_unrecoverable` is a distinct path from delta<0-driven, named separately in arch §Edge case 17). Scope grows by one file but stays inside the story's stated goal ("six adversarial tests" → "four NEW + one optional NEW + three collected").
- **D-7 (registry for fixture+test mapping)** vs Rule 2 ("three similar lines is better than premature abstraction"): YAGNI wins. Six explicit tests are fine; surface as Note for the next phase if test count crosses 10.

## Stage 3 — researcher

**Not invoked.** No findings tagged `NEEDS RESEARCH`. Every gap was answerable from in-repo materials.

## Stage 4 — synthesizer outputs

- **Verdict:** **HARDENED.**
- **Story edits:** `Status` line; `Depends on:` line; `ADRs honored:` line; `Validation notes` block (added under header); `## Acceptance criteria` rewritten with AC-XX-N IDs grouped A–I (37 ACs total — up from 11); `## Implementation outline` (15 ordered steps; up from 9); `## TDD plan — red / green / refactor` (7 Red ACs across the seven new files; Green sequenced; Refactor narrowed); `## Files to touch` (table re-keyed; "Explicitly NOT touched" addendum); `## Out of scope` (3 corrections — filenames + ownership); `## Notes for the implementer` (17 paragraphs, all anchored to a HARDENED sibling or an ADR or a CLAUDE.md commitment).
- **No new files written outside `_validation/`.** No code edits to `src/codegenie/`. No test files written. The autouse `conftest.py` guard, the helpers, and the new adversarial tests are the executor's work.

## Followups for downstream stories / phases

- **High-level-impl.md §Step 7** carries the same mutation-witness inversion the draft AC inherited. Amend the line *"mutation-style negative checks (e.g., temporarily set `passed=True` on a TestSignal with `delta_test_count=-1` — gate must still fail because TrustScorer reads `passed`)"* to read: *"mutation-style negative checks at the COLLECTOR boundary (a `collect_test_signal` mutant that ignores `pre_patch_inventory_path` and always returns `passed=True` reaches the gate as `passed=True` and bypasses the strict-AND; the regression is the collector, not the gate)."* This is a Step-7 description amendment, not a Phase 5 ADR change.
- **S4-03 GREEN check (precondition for AC-CAT-MEMBER-1):** verify `_TRACE_DETAIL_KEYS` includes `{new_endpoints, new_endpoints_count}` AND `sandbox/logging.py` exports `EVENT_SANDBOX_EGRESS_BLOCKED`. If absent at S7-01 executor-run time, the executor files a Notes-for-implementer carryforward to S4-03 GREEN before unblocking S7-01.
- **S5-03 GREEN check (precondition for AC-INJ-EVENT-1):** verify `EVENT_PROMPT_INJECTION_DETECTED` is exported from `codegenie.llm.fence`. Same handling as above.
- **Phase 6 (next phase):** the consolidated adversarial suite this story lands becomes the regression baseline for the LangGraph state-machine integration; Phase 6 should add the suite to its CI gate.
