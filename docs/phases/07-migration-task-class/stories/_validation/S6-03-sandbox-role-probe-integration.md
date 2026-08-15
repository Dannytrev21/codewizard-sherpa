# Validation report — S6-03 Integration test: `spawn(role=Role.PROBE)` boots microVM + Phase 5 regression suite green

**Date:** 2026-08-15
**Validator:** phase-story-validator (four-critic inline pipeline + synthesizer)
**Verdict:** **HARDENED** — the story's core surface (microVM topology proof + default-arg runtime byte-identity + typed failure modes + regression-suite green + CI matrix discipline) was sound, and the split into A/B/C/D/E/F was the right decomposition. Seven fixable weaknesses landed:
1. **Category error on `confidence` / `reason`** — AC-D asserted an `SandboxRun.exit_status.reason` surface that does not exist on Phase 5's shipped model (per `05/final-design.md §Failure modes`); ADR-0002's `confidence`/`reason` mentions describe `ShellInvocationTraceProbe`'s `ProbeOutput`, not `SandboxClient`'s `SandboxRun`. Rewritten against `SandboxRunFailed` (exception) + `SandboxRun.timed_out`/`killed_by_oom` (Phase 5's actual typed failure surface).
2. **Same-backend guard missing** on `test_probe_topology_identical_to_gate` — a stealth fixture-selection bug (Firecracker vs DinD on the same runner) would fail the field-equality check for the wrong reason.
3. **Normalization helper reuse** was framed as "optional" — must be a Rule-3 obligation (S6-02 owns the helper + `Final[tuple[str, ...]]` allow-list; S6-03 imports).
4. **Marker-name assumption** — story hard-coded `@pytest.mark.phase07_integration` without discovering Phase 5's actual convention (Rule 11).
5. **"Everything skipped" defense is CI-workflow-level, not pytest-level** — a pytest test cannot see other matrix entries; must be a post-matrix aggregator step.
6. **Baseline JSON discipline** — CODEOWNERS-gate mechanics were assumed, not spelled out; needs shape-validity companion + skip-`reason=` allow-list.
7. **Existential vs universal quantification** on audit-tag assertions — `at least one event has role==PROBE` is defeated by stealth per-callsite inconsistency; universal-quantification is required.

Also: several `SandboxRun` field-name assumptions (`exit_status.success`, `cpu_quota`, `memory_limit_mib`, `pids_limit`, `duration_ms`) are contingent on Phase 5's shipped model — the invariants are correct, the field names must be reconciled. Added a new AC-G — runtime concurrency safety — as the real-backend complement of S6-02's stub-level concurrency test.

Story is executable once (a) Phase 5's `sandbox/` module + pre-existing tests land, (b) S6-02 ships the normalization helper at a shared location, (c) the CI-workflow-level "everything skipped" aggregator step is scoped with Phase 5's CI owner.

**Story:** [`../S6-03-sandbox-role-probe-integration.md`](../S6-03-sandbox-role-probe-integration.md)

---

## Stage 1 — Context brief

**Read:**
- Story (all sections).
- `docs/phases/07-migration-task-class/ADRs/0003-sandbox-role-additive-enum-on-spawn.md` — primary. §Decision (one new parameter), §Consequences row 4 (every existing callsite unchanged), row 6 (integration test asserts identical topology + audit-log tag), row 8 (future roles `RECIPE`/`AUDIT` land additively).
- `docs/phases/07-migration-task-class/ADRs/0002-shell-invocation-trace-probe-runs-in-microvm.md` — consumer. §Consequences row 5 (**probe-level** typed warnings: `shell_invocation_trace.sandbox_boot_failed`, `shell_invocation_trace.build_failed` — these describe `ProbeOutput.confidence` / probe warning IDs, NOT `SandboxRun` fields). §Consequences row 4 (`Probe.run(repo, ctx)` receives `ctx.sandbox_client` — this is the seam S7-02 uses, not S6-03).
- `docs/phases/05-sandbox-trust-gates/final-design.md` §Components §1 (canonical method name `execute(spec) -> SandboxRun`), §Components §2 (`SandboxRun` fields: `run_id`, `exit_code`, `logs_dir`, `microvm_seconds`, `gate_isolation_class`, `trace_path: Path | None`, `timed_out: bool`, `killed_by_oom: bool`), §Components §3/§4 (DinD → `shared_kernel`, Firecracker → `microvm`), §Failure modes (`SandboxRunFailed` exception, `SandboxRun.timed_out`, `SandboxRun.killed_by_oom` — **no `exit_status.reason` field**).
- Sibling validated stories: `_validation/S6-01-sandbox-role-enum.md`, `_validation/S6-02-sandbox-spawn-role-parameter.md` — the family patterns: Preconditions section, `Final[tuple[str, ...]]` allow-lists for load-bearing sets, identity-not-equality on enum members, planted-violation matrices, CODEOWNERS-gated baselines.
- `docs/operations/cassettes.md` §CODEOWNERS gate — the discipline `phase5_skip_counts.json` should mirror.
- Repo state: `find src -type d -name sandbox` → `src/codegenie/transforms/sandbox` only; `src/codegenie/sandbox/` does not exist on `main`. `find tests -name '*sandbox*'` → several tests under `tests/unit/plugins/`, `tests/unit/transforms/`, `tests/integration/transforms/` — but **no `tests/unit/sandbox/` and no `tests/integration/test_sandbox_*.py`**. Phase 5's test suite has not shipped.

**Load-bearing findings from the context read:**
1. **`src/codegenie/sandbox/` does not exist on `main` as of 2026-08-15.** Mirrors S6-01 §1, S6-02 §1. Story is only executable once Phase 5's sandbox module lands — and this story additionally needs Phase 5's *test suite* to exist (or at least a marker + fixture convention to inherit).
2. **Category error on `confidence`/`reason`.** ADR-0002 §Consequences row 5 is talking about `ShellInvocationTraceProbe`'s `ProbeOutput` (`ProbeOutput.confidence: Literal["high", "medium", "low"]` and probe warning IDs). Phase 5's `SandboxRun` has NO `exit_status.reason` field; its typed failure surface is `SandboxRunFailed` (exception), `SandboxRun.timed_out: bool`, `SandboxRun.killed_by_oom: bool`. AC-D's original assertions were pointing at a nonexistent surface — must be rewritten against Phase 5's actual model.
3. **Method name reconciliation** (`spawn` vs `execute`) inherits from S6-02 §2. Phase 5's canonical name is `execute(...)`; Phase 7 ADRs speak `spawn(...)`. All AC test-name examples that say `test_..._spawn_...` may need renaming; the invariant is naming consistency with S6-02.
4. **Marker-name assumption** — story guesses `@pytest.mark.phase07_integration` without evidence it exists. Phase 5's actual convention must be discovered (Rule 11); if none exists, coordinate a marker-add in Phase 5's test-infrastructure PR, do not invent Phase-7-only.
5. **Normalization helper reuse** — story says "optional, only if AC-B's normalization logic is reused." But S6-02's `_normalize_run_for_byte_identity` and its `Final[tuple[str, ...]]` allow-list are load-bearing; S6-03 as the runtime complement MUST import and use, not re-declare. A stealth divergence would silently mask default-path drift.
6. **Same-backend guard** — `test_probe_topology_identical_to_gate` asserts identical `gate_isolation_class` between GATE and PROBE runs. Phase 5's design assigns `shared_kernel` on DinD, `microvm` on Firecracker. If the two calls select different backends (via different fixtures on the same runner), the assertion fails for the wrong reason. Preflight `assert gate_run.backend == probe_run.backend` needed.
7. **"Everything skipped is a green build"** defense in AC-E bullet 3 was framed as a pytest test ("a CI matrix test confirms full coverage cannot be silently skipped on every runner"). A pytest test cannot see other matrix entries — this is a post-matrix aggregator step in `.github/workflows/*.yml`. Wrong ownership boundary in the original story.
8. **Existential-quantification thin tests** — `at least one audit_events entry has role == "probe"` is defeated by a stealth per-callsite inconsistency where only one site emits the tag. Universal-quantification is required to pin the invariant.
9. **`SandboxRun` field-name assumptions** — story uses `exit_status.success`, `duration_ms`, `cpu_quota`, `memory_limit_mib`, `pids_limit`. Some of these do not appear in Phase 5's `final-design.md`; some (like `microvm_seconds`) have different names. The invariants are correct ("resource budgets identical between roles"), the field names are contingent — must reconcile against the shipped `SandboxRun` model.
10. **Baseline JSON discipline** — story specifies `tests/_baselines/phase5_skip_counts.json` but the CODEOWNERS-gate mechanics were assumed, not spelled out. `docs/operations/cassettes.md` is the precedent; reuse the exact discipline (two-CODEOWNERS approval, shape-validity companion test, PR-description convention).

## Stage 2 — Four critics (inline)

Critics run inline (not spawned as subagents) — the story's AC surface, while broader than S6-01/S6-02, still concentrates on a handful of well-enumerable invariants (topology equivalence, byte-identity on default path, regression counts, typed failure modes, CI matrix aggregation). Marginal signal from four independent subagent reads doesn't justify the token cost. Family patterns from S6-01/S6-02 already cover the majority of the discipline this story needs.

### Coverage critic

- **coverage-1 (BLOCK)** — **AC-D category error.** `SandboxRun.exit_status.reason` doesn't exist on Phase 5's shipped model. Story confuses `ProbeOutput.confidence` (S7-02's surface) with `SandboxRun` (S6-02/S6-03's surface). Must rewrite against `SandboxRunFailed` / `SandboxRun.timed_out` / `SandboxRun.killed_by_oom` (Phase 5's actual §Failure modes).
- **coverage-2 (harden)** — AC-A/AC-B/AC-D existential quantification (`at least one audit_events entry`) is defeated by stealth per-callsite inconsistency. Convert to universal quantification.
- **coverage-3 (harden)** — AC-A `test_probe_topology_identical_to_gate` lacks same-backend preflight guard. A cross-backend comparison fails the equality check for the wrong reason.
- **coverage-4 (harden)** — AC-B five-spec matrix duplicates S6-02 unit-level coverage at runtime cost. Reduce to two hand-picked specs (one `command` variation, one `env` variation); the exhaustive matrix is unit-level.
- **coverage-5 (harden)** — AC-B does not enforce that S6-02's normalization helper is imported (not re-declared). A stealth local re-declaration diverges silently.
- **coverage-6 (harden)** — AC-C bullet 1 assumes `tests/unit/sandbox/ tests/integration/test_sandbox_*.py` paths exist; Phase 5's actual layout must be discovered. Invariant is "every pre-existing Phase-5 test still passes", not literal paths.
- **coverage-7 (harden)** — AC-C bullet 3 "zero golden-file deletions" via mere `git diff --name-status` misses delete+re-add. Hash-and-compare needed.
- **coverage-8 (harden)** — AC-D `test_probe_capture_trace_false_succeeds` was correct but its universal audit-tag check was existential ("audit log still carries `role == "probe"`"). Tighten.
- **coverage-9 (harden)** — Missing: on failed `Role.PROBE` boot, the audit-event stream must still carry `role is Role.PROBE` (forensic attribution). Currently no AC pins this.
- **coverage-10 (harden)** — AC-E bullet 3 ("everything skipped" defense) is misplaced. Not a pytest test; must be a CI workflow aggregation step.
- **coverage-11 (harden)** — Missing: runtime concurrency check. S6-02 has stub-level; S6-03 is the real-backend complement. Cheap invariant guard against hidden shared state.
- **coverage-12 (harden)** — Baseline JSON bootstrap case (`skip_count: 0`) is not spelled out. If Phase 5's test suite is empty, baseline is legal-empty.

### Test-quality critic

- **test-1 (harden)** — `e.role == "probe"` sketches treat enum as string. `SandboxRole(str, Enum)` mixin makes `==` succeed against underlying string; stealth `str`-bleed passes. Use `e.role is SandboxRole.PROBE` (matches S6-02's test-1 finding).
- **test-2 (harden)** — Baseline JSON needs shape-validity companion (`test_baseline_shape_valid`) — a hand-edit that corrupts the JSON currently silently passes since fence just diffs counts.
- **test-3 (harden)** — Skip-reason strings should be module-scope `Final[str]` constants (matches AC-C bullet 3), asserted at the fence-comparison layer. A hand-edit that changes wording fails both the local test and the baseline allow-list — no "swap one skip for another with a stealth different reason" bypass.
- **test-4 (harden)** — Topology-equivalent-fields set should be a `Final[tuple[str, ...]]` at module scope (matches S6-02's normalized-fields discipline). A stealth widening fails a companion `test_topology_equivalent_fields_enumerated`.
- **test-5 (harden)** — Concurrent-runs invariants: distinct `run_id`s, distinct non-`None`-vs-`None` `trace_path`s, distinct trace files if both non-`None` (guards against global capture file). Explicit invariants beyond just "role tags don't cross-contaminate".
- **test-6 (harden)** — Red-mode diagnostic table is present in TDD plan but missing failure-owner attribution (executor might silently fix Phase-5-shaped work inside a Phase-7 story). Enumerate each red mode → owner story.

### Consistency critic

- **consistency-1 (BLOCK)** — Category error on `confidence`/`reason` (coverage-1). ADR-0002 vs Phase-5 `final-design.md §Failure modes` are the ADR-vs-shipped-model conflict; story blended both. Rule 7 (surface conflicts, don't average them) — resolved by aligning AC-D with Phase-5's shipped surface.
- **consistency-2 (harden)** — Preconditions section missing (mirrors S6-01/S6-02). At minimum: module existence, method name, test path discovery, helper reuse, category correction, same-backend guard, field-name reconciliation, event class name, baseline discipline, CI-workflow ownership.
- **consistency-3 (harden)** — Marker name (`@pytest.mark.phase07_integration`) assumed rather than discovered. Rule 11.
- **consistency-4 (harden)** — `_sandbox_normalization.py` described as "optional" — but S6-02 already owns the helper; S6-03 must reuse. Rule 3 + DRY.
- **consistency-5 (harden)** — `SandboxRun` field-name assumptions (`exit_status.success`, `cpu_quota`, `memory_limit_mib`, `pids_limit`, `duration_ms`, `started_at`) don't all appear in Phase-5 `final-design.md`. Contingent-on-shipped-model note needed.
- **consistency-6 (harden)** — AC-E bullet 3 is CI-workflow-level, not pytest-level (coverage-10). Ownership boundary needs explicit statement so the executor doesn't ship a pytest test that trivially always passes.
- **consistency-7 (harden)** — `_baselines/phase5_skip_counts.json` mentioned but the CODEOWNERS-gate discipline is a repeat of `docs/operations/cassettes.md`; reference the precedent explicitly.

### Design-patterns critic

- **design-1 (nit)** — Test-only story with independent invariant families (topology / regression / failure) is the right decomposition for a load-bearing integration proof. Story respects.
- **design-2 (harden)** — Concurrency: default is that shared-mutable-state is invisible until CI runs against a real backend on a machine with real IO. Cheap single-test guard via `asyncio.gather` on the real client. See coverage-11.
- **design-3 (harden)** — Extension-by-addition for future roles (`Role.RECIPE`, `Role.AUDIT` per ADR-0003 §Consequences row 8): the topology-identical assertion is a natural `parametrize` over a module-scope tuple. Rule 2 says don't ship the abstraction today (one non-gate role); but the invariant + tuple *name* should be picked so the future extension is one row, not a refactor. Note-for-implementer, not AC.
- **design-4 (nit)** — Additive-parameter + additive-fixture + additive-baseline shape (S6-01 → S6-02 → S6-03 → future S6-04 for `Role.RECIPE`) is a clean Open/Closed progression across a story family. No abstraction needed today; the discipline lives in the story-family shape.
- **design-5 (nit)** — Failure-mode assertions on Phase 5's typed surface (`SandboxRunFailed` exception, `timed_out`/`killed_by_oom` fields) reuse the existing sum-type-shape discipline; no new abstraction. Sound.
- **design-6 (harden)** — Red-mode ownership attribution (test-6). This is a design-pattern concern in the sense that "which upstream story owns which red mode" is a coordination-shape decision — if the story doesn't spell it out, the executor is tempted to silently fix Phase-5-shaped work here, violating Rule-3 surgical-changes and burning cross-story bisect ability.

## Stage 3 — Researcher

**Not fired.** No critic finding tagged `NEEDS RESEARCH`. Every finding pointed at:
- ADR-vs-shipped-model text (resolvable by reading Phase-5 `final-design.md §Failure modes` alongside ADR-0002 §Consequences).
- Standard pytest / asyncio / stdlib patterns (`Final`, `is`-identity, `@pytest.mark.parametrize` scope).
- Codebase precedents already present (`docs/operations/cassettes.md` for CODEOWNERS-gated baselines; S6-01/S6-02 validation reports for family patterns).

## Stage 4 — Synthesizer + Editor

**Priority:** Consistency > Coverage > Test-Quality > Design-Patterns.

**Conflict resolution:**
- **coverage-1 + consistency-1 (both BLOCK on category error)** — resolved by rewriting AC-D against Phase-5's actual typed failure surface (`SandboxRunFailed` exception + `SandboxRun.timed_out` / `killed_by_oom` fields) and adding Preconditions §5 spelling out why. ADR-0002's `confidence`/`reason` mentions are re-read as probe-level (S7-02's territory), not sandbox-level. Consistency wins over the ADR-literal reading.
- **coverage-3 (same-backend guard) vs coverage-4 (AC-B two-spec vs five-spec)** — no conflict; both resolved orthogonally. Same-backend guard is a preflight `assert`; AC-B reduces to two runtime specs (unit-level five-spec matrix is S6-02's territory).
- **coverage-6 (test-path discovery) vs consistency-3 (marker discovery)** — no conflict; both resolved by Preconditions §3 (paths + markers together must be discovered from Phase-5's actual layout).
- **coverage-10 + consistency-6 (CI-workflow-level "everything skipped" defense)** — resolved by Preconditions §10 spelling out the ownership boundary and AC-E bullet 3 pointing at the workflow aggregator (not a pytest test). Executor may split the workflow-edit into a follow-up story if scope demands, but MUST NOT close S6-03 without either the aggregator landing or the follow-up story being `Ready`.
- **design-3 (extension-by-addition for future roles) vs Rule 2 (Simplicity First)** — Rule 2 wins (as documented in the skill's Priority rule: Consistency > Coverage > Test-Quality > Design-Patterns). The design-pattern opportunity is recorded as a Notes-for-implementer paragraph, not an AC — the *name* and *location* of the `_TOPOLOGY_EQUIVALENT_ROLES` tuple are cheap to pick today; the `parametrize` scaffold is Rule-2-forbidden until the second consumer arrives.

**Edits applied** (see story's `## Validation notes` block for the concise summary):
- Front-matter: `Status` bumped from `Ready` → `HARDENED`; `Depends on` extended with S6-02's normalization-helper reuse + Phase-5 pre-existing-tests requirement; `ADRs honored` extended with the Preconditions §5 pointer to the category-correction resolution and the Phase-5 `final-design.md §Failure modes` pointer as source of truth.
- New `## Preconditions` section (ten items): (1) sandbox/ module existence, (2) method-name reconciliation inheriting S6-02 §2, (3) Phase-5 test path + marker convention discovery, (4) normalization-helper reuse from S6-02, (5) **category correction on `confidence`/`reason`**, (6) same-backend guard, (7) `SandboxRun` field-name contingency, (8) audit-event class-name contingency, (9) baseline JSON CODEOWNERS-gate + skip-reason allow-list discipline, (10) "everything skipped" defense as CI-workflow-level.
- New `## Validation notes` block summarizing edits and verdict.
- AC-A: added same-backend preflight guard (`gate_run.backend == probe_run.backend`); enumerated resource-budget fields as `_TOPOLOGY_EQUIVALENT_FIELDS: Final[tuple[str, ...]]` at module scope (contingent on Preconditions §7); rewrote `exit_status.success is True` → `exit_code == 0` (Phase-5's actual surface); universal-quantification role-tag check (`every event ... satisfies e.role is SandboxRole.PROBE`, not existential); identity-not-equality on enum members.
- AC-B: made normalization-helper import a hard requirement (Preconditions §4); reduced to two specs (one `command` variation, one `env` variation); added `test_normalization_helper_is_shared` companion; universal-quantification on GATE role tags.
- AC-C: added `test_baseline_shape_valid` for JSON structure; made skip-reason strings `Final[str]` constants (`_SKIP_REASON_NO_PRIVILEGE`); tightened golden-file deletion check to hash-and-compare (not just `git diff --name-status`); added empty-baseline bootstrap case.
- AC-D **rewritten** against Phase-5's actual typed failure surface: `SandboxRunFailed` (exception) + `SandboxRun.timed_out is True` (field) instead of the nonexistent `exit_status.reason`; added `test_probe_failure_still_tags_role` for forensic-attribution invariant.
- AC-E: pinned marker-discovery discipline to Preconditions §3; reframed "everything skipped" as CI-workflow-level per Preconditions §10; explicit skip-reason `Final[str]` at module scope.
- AC-F: added `pytest tests/fence/` full-fence-sweep AC (new `tests/_baselines/` artifact is a Phase-1-style structural defense addition); `mypy --strict` scope extended to the new fence test file.
- New AC-G — Runtime concurrency safety: real-backend complement of S6-02's stub-level concurrency test. Two concurrent `asyncio.gather` runs (one `Role.GATE`, one `Role.PROBE + capture_trace=True`) on one client; invariants: distinct `run_id`s, `trace_path` non-`None` only on PROBE, distinct trace files, universal-quantification role-tag correctness.
- TDD plan: enumerated red-mode-to-upstream-owner attribution table (guards against silently fixing Phase-5-shaped work here); expanded refactor gate to verify normalization-helper import (not re-declaration), module-scope constants (not function-local); added red modes for AC-D rewrite (`SandboxRunFailed` and `timed_out` field must exist — otherwise Phase-5 shipping bug, not story bug).
- Notes for the implementer: added five paragraphs (three-invariant-family framing; baseline JSON CODEOWNERS-gated artifact; category correction; marker-name discovery; same-backend guard); removed the duplicated / stale versions of the pre-existing paragraphs (normalization helper; runner-capability skipping; gate_isolation_class; fallback; reading order; no-placeholder; S7-02 coordination); preserved the pre-existing paragraphs that still applied (edited to align with new AC numbering); added extension-by-addition-for-future-roles nudge as Rule-2-compliant (Notes-only, not AC).

**Not edited** (respect for original scope, Rule 3):
- Story's Goal (four bullets), Context narrative, References section — the writer's framing is sound; the validator only tightens verification, not intent.
- Files-to-touch list — the enumerated file paths are the right shape (two integration test files, one fence test file, one baseline JSON, one optional helper location) and complete.
- Out-of-scope section — sharply scoped (S6-03 owns integration proof; S7-02 owns probe-level integration; S10-04/S10-05 own gate-specific assertions; Phase-5 backend additions are Phase-5's territory).
- Implementation outline's ordered steps — already reads existing conventions before writing; the discipline is correct even if some field names + method name need reconciling per Preconditions.

## Strong dimensions (record for future stories to imitate)

- **Runtime complement to a unit-level surface.** S6-03 as the runtime companion to S6-02's stub-level tests is the right integration-story shape: unit tests characterize the shape exhaustively (five-spec matrix), integration tests prove the runtime path against one or two hand-picked specs on a real backend. The story's split between S6-02 (unit) and S6-03 (integration) is a good precedent for future backend-heavy amendments.
- **Independent invariant families for a load-bearing integration proof.** Three families (new behavior works / old behavior unchanged / failure modes honestly typed) each with their own AC block make the "what does green mean?" question crisp. Any regression in any family is a different class of defect with a different escalation path (Rule 12 — Fail loud).
- **Two defenses for the "everything skipped is a green build" failure mode.** A pytest-level baseline-count fence + a CI-workflow-level aggregator; either one alone can be evaded. Encoding both is the right belt-and-suspenders discipline for gated integration suites.
- **Red-mode-to-upstream-owner attribution table.** The TDD plan's enumeration of "which upstream story owns each red mode" prevents the executor from silently fixing Phase-5-shaped work inside a Phase-7 story — preserves cross-story bisect ability and honors Rule 3 (Surgical Changes).
- **Reuse-not-re-declare discipline for shared test helpers.** The `_normalize_run_for_byte_identity` reuse obligation (Preconditions §4 + `test_normalization_helper_is_shared` companion) prevents silent divergence between unit-level and integration-level normalization sets — a subtle bug class that would silently mask default-path drift.
- **Category correction — probe-level vs sandbox-level surfaces.** ADR text is intent; shipped code is truth. Preconditions §5 spells out how to distinguish `ProbeOutput.confidence` (probe-level) from `SandboxRun.timed_out`/`killed_by_oom` (sandbox-level) — a discipline that will pay dividends every time a probe story references sandbox internals or a sandbox story references probe internals.
- **CODEOWNERS-gated baseline JSON reused from cassette precedent.** Rather than inventing a new baseline discipline, reuse `docs/operations/cassettes.md`'s exact playbook (two-approver, shape-validity companion, PR-description convention). Future baseline-family fences compose without a taxonomy explosion.

## Provenance / signatures

- Validator: phase-story-validator skill, four-critic inline pipeline (Coverage, Test-Quality, Consistency, Design-Patterns) + synthesizer.
- Runtime evidence: none required — story is not executed, only hardened.
- Edits: applied via Edit tool against `docs/phases/07-migration-task-class/stories/S6-03-sandbox-role-probe-integration.md`.
- Cross-story references surfaced (not amended): Phase-5 `final-design.md §Components §1/§2/§Failure modes` is the canonical surface for AC-A/AC-B/AC-D assertions; S6-02's normalization helper location is a hard dependency for AC-B; the CI workflow aggregator (AC-E bullet 3) is a coordination point with Phase-5's CI owner.
