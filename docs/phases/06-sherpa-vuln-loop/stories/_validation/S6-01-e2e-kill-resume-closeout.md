# Validation report — S6-01 (E2E kill/resume closeout)

**Date:** 2026-05-26
**Validator:** phase-story-validator (inline four-lens analysis — Coverage, Test-Quality, Consistency, Design-Patterns — applied directly after Stage 1's Context Brief. Mirrors the precedent set by every prior Phase-6 validation (S1-01..S5-01): the pre-validation file was a 16-line stub with three dash bullets; the four lenses converged sharply; spawning four parallel critic agents would have burned tokens without changing the verdict.)
**Verdict:** **HARDENED**
**Story path:** [`docs/phases/06-sherpa-vuln-loop/stories/S6-01-e2e-kill-resume-closeout.md`](../S6-01-e2e-kill-resume-closeout.md)

## Why HARDENED (not STRONG, not RESCUE)

The story's *architectural intent* matches every authoritative source — it is the Phase-6 closeout composing every prior story's surfaces into runtime verification of `final-design.md §"Exit criteria mapping"` + `phase-arch-design.md §"Scenarios"` 1..4 + the cross-cutting `tests/e2e/scenarios.yaml` + the workflow-scope replay-determinism property `docs/roadmap.md §"Phase 6"` names verbatim. But the pre-validation 16-line stub left every load-bearing decision implicit:

1. **AC count effectively 0.** Three dash bullets (`-`, not `- [ ]`); no checkbox-shaped, no individually verifiable, no third-party-pass/failable.
2. **"Integrations pass"** is unanchored. Through what fixtures? What assertions? What test-module paths? Multiple plausible mechanisms; pre-validation picked none.
3. **"Phase 6.5 contract test imports `VulnRemediationSut`, not graph internals"** conflates two seams: (a) the placeholder fence at `tests/fence/test_phase6_no_graph_imports_from_phase65.py` (already exists, `pytest.skip`s when Phase 6.5 has not landed); (b) a NEW Phase-6.5-shaped consumer simulation that enforces the closure *during the Phase-6/Phase-6.5 gap*. An executor would pick (a), and the closure would silently remain unenforced until Phase 6.5 ships.
4. **"Roadmap and docs links resolve to the Phase 6 package"** is satisfiable by `tests/unit/test_phase6_docs.py` (which already exists and tests this); the AC is already-passing — useless as a closeout assertion. The mutation-resistant form is "every internal cross-link under `docs/phases/06-sherpa-vuln-loop/` resolves" — a walk over the package, not the existing top-level assertion.
5. **No mention of `phase-arch-design.md §"Scenarios"` row 4 (tampered checkpoint).** Of the four canonical scenarios, only three are named (clean + retry + kill/resume + HITL); the tampered-checkpoint scenario — the one that proves `final-design.md §"Decisions of record"` item 3 ("Resume verifies the prior chain head before replay") — is silently omitted.
6. **No mention of `tests/e2e/scenarios.yaml`.** `High-level-impl.md §"Step 6"` lists it explicitly; `docs/roadmap.md §"Phase 6"` lists it explicitly. An executor would ship the four integration tests and forget the cross-cutting addition.
7. **No mention of `tests/property/test_workflow_replay_determinism.py`.** `High-level-impl.md §"Step 6"` lists it explicitly; `docs/roadmap.md §"Phase 6"` lists it explicitly with `(repo_snapshot, cassette_id, embedding_model_digest)` triple + N≥50 + byte-identical-modulo-timestamps. An executor would ship integration tests and skip the property entirely.
8. **No fixture cohort named.** Roadmap names three: `node_typescript_helm` + `node_yarn_berry_pnp` + `node_pnpm_native`. Pre-validation picked none — an executor would parametrize against one fixture (whichever was convenient) and the package-manager-dispatch closeout would silently coast.
9. **No mutation-resistance reasoning.** Every pre-validation AC is satisfiable by trivial mutants:
   - "Clean-completion integrations pass" — mutant: a stub that returns a hardcoded `VulnRemediationResult(terminal_state="completed", ...)` would pass without ever invoking the graph.
   - "Kill/resume works" — mutant: a stub that runs two independent invocations producing the same `Completed` output, never actually resuming from a checkpoint.
   - "Phase 6.5 contract test imports `VulnRemediationSut`" — mutant: a test importing only `VulnRemediationSut` (without driving anything) trivially passes the import-only assertion.
10. **No `stories/README.md` "Definition of done" closeout.** The five bullets there are the actual closeout discipline; pre-validation didn't name them.
11. **No `_lessons.md` closeout.** The cross-story lessons captured by every prior Phase-6 attempt log would lose the S6-01 entry; future phase authors would lose load-bearing context.
12. **No anti-refactor block.** Under closeout pressure an executor could ship a `BaseE2ETestCase`, a `@register_scenario` decorator, a `_e2e_helpers.py` module, or a new public name in `codegenie.workflows.__all__` — every one a premature abstraction.
13. **No contract-snapshot closeout cross-check.** S5-01 extends the snapshot additively; S6-01's job is to close-pin the S5-01-post state. Without a SHA256 cross-check anchor, an executor could regenerate the snapshot to "absorb" a non-existent change and slip a contract amendment through.
14. **No ADR-amendment-discipline assertion.** S6-01 ships zero new public types and should not amend any ADR. Without an explicit "no ADR amendments" assertion, an executor could slip an amendment through under closeout pressure.
15. **No mention of the metamorphic kill-and-resume === never-killed property.** Phase-9's Temporal substrate-swap conformance inherits this invariant; without the AC, Phase-9's later assertion would have no Phase-6 substrate to compare against.
16. **No mention of the `apply()` call-count == 0 sub-assertion** for the tampered-checkpoint scenario. Without it, the only mutation-resistant defense against an adapter that "helpfully" recovers from a tampered chain would be missing.
17. **No mention of the `hydrate_or_fail` SOLE-site cross-check.** S2-02 shipped `hydrate_or_fail` as the SOLE integrity site; S6-01 must close-pin that the adapter delegates (never re-implements) integrity decisions.

All in-place fixable; none requires re-running `phase-story-writer`. The story's structure survives — three bullets grew to 13 numbered checkbox ACs across seven labeled sub-sections + a six-item anti-refactor block + Files-to-touch (16 entries) + a 10-step TDD plan + Out-of-scope + Notes-for-implementer (8 paragraphs). Verdict: **HARDENED**.

## Context Brief (Stage 1)

### Story snapshot

- **Goal (pre-validation):** "Prove the Phase 6 exit criteria end to end and publish the downstream handoff." Vague — no scenario list, no fixture cohort, no test-architecture additions, no contract-snapshot closeout, no docs-link discipline, no anti-refactor.
- **Goal (post-validation):** ship the Phase-6 closeout package — five integration fixtures (`tests/integration/workflows/test_phase6_{clean_completion,retry_recovery,kill_resume,hitl_interrupt_resume,tampered_checkpoint}.py`) + one workflow-scope determinism property (`tests/property/test_workflow_replay_determinism.py`) + one Phase-6.5-consumer isolation simulation (`tests/integration/test_phase6_consumer_isolation.py` + `tests/golden/phase6/synthetic_consumer.py`) + one `tests/e2e/scenarios.yaml` (three rows, one per cohort fixture) + the docs/contract closeout sweep + the `stories/README.md` Definition-of-done flip + the `_lessons.md` closeout entry. Every assertion is a runtime test or a fence walk; every fence walk follows existing AST-precedent. The story ships zero new production modules and zero ADR amendments.
- **Status pre-validation:** `Ready` — never executed; never validated.
- **Status post-validation:** `HARDENED`.

### Authoritative sources

- **final-design.md** §"Exit criteria mapping" all four rows (each row maps to one AC); §"Decisions of record" item 3 (semantic checkpoints + chain-head verification — drives AC-3 + AC-5); §"Relationship to Phase 6.5" verbatim (drives AC-7 four-bullet AST walk); §"Non-goals" item 1 (drives Anti-refactor #1).
- **phase-arch-design.md** §"Scenarios" #1..#4 verbatim (drives AC-1..AC-5); §"Failure modes" rows 1 + 4 + 5 (drives AC-5 + AC-4 + AC-2 sub-assertions); §"Testing strategy" (drives AC-1..AC-5 module placement); §"Cross-cutting test-architecture additions" verbatim (drives AC-6 + AC-8).
- **High-level-impl.md** §"Step 6" all six bullets (each bullet is one AC).
- **stories/README.md** §"Definition of done" five bullets (drives AC-11).
- **docs/roadmap.md** §"Phase 6" — fixture cohort + N≥50 + `(repo_snapshot, cassette_id, embedding_model_digest)` triple verbatim (drives AC-1..AC-4 cohort + AC-6 property).
- **ADR-0001** §Consequences ("Phase 6.5 imports the contract only" — drives AC-7); **ADR-0003** (chain-head verification before replay — drives AC-3 + AC-5).
- **S5-01 (HARDENED)** — `build_local_sut(config)` factory + `LocalVulnRemediationSut` + the sole-importer fence (drives AC-1..AC-5 SUT construction + AC-9 contract-snapshot cross-check + Anti-refactor #3 inheritance).
- **S4-01 (HARDENED)** — `HitlInterrupt`, `ResumeInput`, `resume_or_reject` (drives AC-4).
- **S2-02 (HARDENED)** — `hydrate_or_fail` is the SOLE integrity site (drives AC-5 sub-assertion).
- **S2-01 (HARDENED)** — `CheckpointStore` Protocol + SQLite/in-memory adapters (drives AC-3 + AC-5 chain-walk).
- **Phase-4 S6-07 (HARDENED)** — the `FallbackTier`-scope determinism property; AC-6 extends to workflow-scope.
- **Phase-3 `tests/fixtures/adversarial/*/.codegenie/scenarios.yaml`** — the schema AC-8 extends.
- **`tests/unit/test_phase6_docs.py`** (existing) — the test AC-10/AC-11/AC-12/AC-13 extend additively.
- **`tests/fence/test_phase6_no_graph_imports_from_phase65.py`** (existing — placeholder) — the complementary fence AC-7 ships alongside.
- **`_attempts/_lessons.md`** — three cross-story lessons applied: (a) `_lessons.md` is append-only and load-bearing for future story authors → AC-12 captures S6-01's lessons; (b) "store types do NOT enter `__all__`" (S2-01) → Anti-refactor #3 inherits; (c) "sanitization is a write-time defense; chain head is computed over the live event" (S2-01, S2-02) → AC-5 mutates SQLite directly to bypass sanitization.

### Hardest design tensions resolved

**Tension 1 — "Phase 6.5 contract test imports the protocol" interpreted as the existing placeholder fence vs. a complementary consumer-isolation test.** The placeholder fence at `tests/fence/test_phase6_no_graph_imports_from_phase65.py` skips when Phase 6.5 has not landed (today). An executor reading the pre-validation AC would point to the placeholder, mark it "covered", and move on — but the closure remains *structurally unenforced* during the Phase-6/Phase-6.5 gap. **Resolution:** AC-7 ships a *complementary* test (`tests/integration/test_phase6_consumer_isolation.py` + a synthetic-consumer source file under `tests/golden/phase6/synthetic_consumer.py`) that enforces the closure from *this side* without waiting for Phase 6.5. The placeholder un-skips when Phase 6.5's harness directory lands; the new test enforces today.

**Tension 2 — `tests/e2e/scenarios.yaml` as YAML + loader vs. parametrized integration test rows.** Adding three more parametrized rows to AC-1's clean-completion test would cover the runtime assertion; the YAML file would not be created. But the YAML file IS the cross-cutting test-architecture surface — Phase 7 will add `phase: 7` rows additively; without an established schema at S6-01, Phase 7's executor would re-invent it. **Resolution:** AC-8 creates the YAML + a separate loader test; the YAML is the data-not-prompts registry future closeouts extend. The parametrization in AC-1..AC-5 stays — AC-8 is *cross-cutting infrastructure*, not duplicate coverage.

**Tension 3 — Workflow-scope determinism property with N=50 vs. N=1 in default test runs.** N=50 concurrent `asyncio.gather` runs take ~10-20 minutes per fixture in CI — far above the per-test budget. But N=1 trivially passes (a single run is byte-equal to itself). **Resolution:** AC-6 uses `N = int(os.environ.get("PHASE6_DETERMINISM_EXAMPLES", "1"))` for default test runs (cheap; catches gross regressions) + `@pytest.mark.bench` for N=50 (expensive; runs in the nightly bench job Phase-6.5 owns). The Hypothesis `@settings(max_examples=...)` config respects the env var. The `bench` marker is already CI-excluded by default (`pyproject.toml` `addopts` excludes `-m bench`).

**Tension 4 — Metamorphic kill-and-resume === never-killed at the byte level vs. just "same terminal state".** "Same terminal state" passes for an adapter that "helpfully" restarts from genesis on resume (it would still reach `Completed`); the chain would be wrong but the result would look identical. **Resolution:** AC-3 asserts byte-equality of the *result payload* (modulo `_BYTE_EQUAL_MODULO` allowlist) AND a chain-walk sub-assertion that the chain head on the second call originates from the *latest verified checkpoint*, NOT from genesis. The two sub-assertions catch orthogonal mutations: byte-equality catches a non-deterministic adapter; the chain-walk catches a genesis-restarting adapter.

**Tension 5 — Tampered checkpoint via `CheckpointStore` Protocol vs. direct SQLite mutation.** Mutating via the Protocol would write a sanitized tampered row — the chain head would correctly track the sanitized bytes; `hydrate_or_fail` would NOT fire. Direct SQLite mutation skips sanitization and produces a row whose stored `next_head` does not match the recomputed-from-bytes fold — the `ChainMismatch` arm of `ReplayVerdict`. **Resolution:** AC-5 mutates SQLite directly via `sqlite3.connect(...).execute(...)`; the comment in the test explicitly notes the choice. The mutation surface in production is the same — a malicious actor writes to the file directly.

**Tension 6 — Closeout discipline: no new public types, no ADR amendments, no `__all__` extensions.** S6-01 is the closeout — every prior Phase-6 story extends the surface; this one closes it. An executor under deadline pressure could slip an `e2e_helpers.py` module, a `BaseE2ETestCase`, a `@register_scenario` decorator, or a new public name. **Resolution:** Anti-refactor block (6 items) + AC-13 explicit `make check` + meta-assertion that no ADR carries an `Amended` line referencing S6-01.

## Four-lens findings (inline, no parallel subagents)

### Lens 1 — Coverage

| Finding | Severity | Resolution |
|---|---|---|
| Pre-validation ACs have effective AC count 0 (dash bullets, no checkboxes, no individual verifiability) | block | 13 numbered checkbox ACs across seven labeled sub-sections. |
| Tampered-checkpoint scenario (phase-arch-design §Scenarios #4) silently omitted | block | AC-5 explicit + the `apply()` call-count == 0 + `hydrate_or_fail` SOLE-site sub-assertions. |
| `tests/e2e/scenarios.yaml` (cross-cutting test-arch addition) silently omitted | block | AC-8 explicit (three rows; `extra="forbid"` schema; loader test). |
| Workflow-scope replay-determinism property silently omitted | block | AC-6 explicit (Hypothesis `@settings` with env-var-driven N; concurrent `asyncio.gather`; `_BYTE_EQUAL_MODULO` allowlist). |
| Fixture cohort not named | block | AC-1..AC-5 explicit `@pytest.mark.parametrize("fixture_name", ["node_typescript_helm", "node_yarn_berry_pnp", "node_pnpm_native"])`. |
| Phase-6.5 contract isolation enforcement absent during Phase-6/Phase-6.5 gap | block | AC-7 complementary `test_phase6_consumer_isolation.py` + synthetic consumer file + AST walk. |
| `Definition of done` bullets remain prose; no closeout flip | harden | AC-11 explicit (flip to `- [x]` with inline test references; unit assertion `== 5`). |
| `_lessons.md` closeout entry absent | harden | AC-12 explicit (3–5 cross-story lessons; unit assertion the section exists). |
| Contract-snapshot byte-equality across S5-01→S6-01 not cross-checked | block | AC-9 explicit (SHA256 anchor file written by S5-01, read by S6-01). |
| `make check` / `mypy --strict` / `make lint-imports` closeout discipline absent | harden | AC-13 explicit. |
| No ADR-amendment-discipline meta-assertion | harden | AC-13 sub-assertion walks `docs/phases/06-sherpa-vuln-loop/ADRs/*.md` asserting no `Amended` line references S6-01. |
| No internal cross-link walk over Phase-6 docs | harden | AC-10 sub-test `test_phase6_internal_cross_links_resolve`. |

### Lens 2 — Test Quality

| Finding | Severity | Resolution |
|---|---|---|
| Original ACs satisfiable by trivial mutants (hardcoded `Completed` result; two independent runs claiming "resume"; import-only test) | block | Every AC carries an explicit "Mutation thinking" note naming the mutation class it catches. |
| No metamorphic test for kill-and-resume === never-killed | block | AC-3 metamorphic byte-equality + chain-walk sub-assertion. |
| No Hypothesis property for workflow-scope determinism | block | AC-6 explicit (concurrent `asyncio.gather`; pairwise byte-identical modulo allowlist). |
| No mutation-resistance for the planner-replan chain in retry scenario | block | AC-2 explicit five-transition chain walk (`PatchApplied → GateFailedRetryable → NeedsPlan → PlanReady → PatchApplied → Completed`). |
| No `apply()` call-count == 0 sub-assertion for tampered-checkpoint | block | AC-5 explicit (test-double `TransformPort`; call-count assertion). |
| No `hydrate_or_fail` call-count == 1 sub-assertion | block | AC-5 explicit (`Mock(wraps=hydrate_or_fail)`; call-count assertion). |
| No stale-resume-token rejection for HITL (phase-arch-design §Failure modes row 4) | block | AC-4 explicit `ResumeRejected(reason="stale_token")` assertion. |
| No chain-origin sub-assertion for HITL resume | block | AC-4 explicit (chain walk shows approved-resume originates from latest verified checkpoint, NOT genesis). |
| No mutation-resistance for docs cross-links | harden | AC-10 sub-test walks every Markdown file under `docs/phases/06-sherpa-vuln-loop/` asserting every relative link resolves. |
| Determinism property's N=50 vs. cheap-default not pinned | nit | AC-6 explicit env-var-driven N + `@pytest.mark.bench` for N=50. |
| `_BYTE_EQUAL_MODULO` duplication risk between AC-3 + AC-6 | nit | Refactor step pins: define once in AC-3's module; re-use via module-import in AC-6. |

### Lens 3 — Consistency

| Finding | Severity | Resolution |
|---|---|---|
| Pre-validation Goal contradicted final-design §"Exit criteria mapping" — three rows of four covered | block | AC-1..AC-5 map to all four exit-criteria rows + the additional tampered-checkpoint scenario. |
| Pre-validation didn't address `final-design.md §"Relationship to Phase 6.5"` four-bullet "may NOT depend on" closure | block | AC-7 explicit four-bullet AST walk over the synthetic consumer. |
| Pre-validation didn't address `phase-arch-design.md §"Cross-cutting test-architecture additions"` | block | AC-6 + AC-8 explicit. |
| Pre-validation didn't address `stories/README.md §"Definition of done"` | harden | AC-11 explicit flip + unit assertion. |
| Pre-validation didn't address `_lessons.md` closeout discipline | harden | AC-12 explicit. |
| Pre-validation didn't address S2-02's `hydrate_or_fail` SOLE-site discipline | block | AC-5 explicit `hydrate_or_fail`-was-called sub-assertion + ADR-0003 reference. |
| Pre-validation didn't address S5-01's sole-importer fence (already shipped) | harden | References explicit; the integration tests import via the plugin's `build_local_sut` factory, not the builder directly — the existing fence stays at exactly one importer. |
| Pre-validation didn't address Phase-6.5's `await asyncio.wait_for(sut.run_case(case), timeout=600.0)` contract | harden | AC-1..AC-5 explicit "the test envelope mirrors the Phase-6.5 shape exactly" so the close-out code path === the production code path. |
| Pre-validation didn't address Phase-9 substrate-swap inheritance (metamorphic kill-and-resume invariant) | harden | AC-3 explicit + Notes-for-implementer paragraph on Phase-9 inheritance. |
| Pre-validation didn't address roadmap's "fixture cohort" naming | block | AC-1..AC-5 explicit cohort parametrization. |
| Pre-validation didn't address `final-design.md §"Non-goals"` item 1 (no second task class) | harden | Anti-refactor #1 explicit (no generalized cross-task-class harness). |

### Lens 4 — Design Patterns

| Finding | Severity | Resolution |
|---|---|---|
| Risk of `BaseE2ETestCase` / `PhaseClosureHarness` / `WorkflowFixtureBuilder` ABC under closeout pressure | block | Anti-refactor #1 explicit — the five integration tests share *fixtures*, not a *base class*; canonical pytest dependency-injection. |
| Risk of `@register_scenario` decorator-based scenarios registry | block | Anti-refactor #2 explicit — the YAML file IS the registry; CLAUDE.md "Organizational uniqueness as data, not prompts". |
| Risk of new public name in `codegenie.workflows.__all__` ("convenience" `LocalVulnRemediationSut` re-export) | block | Anti-refactor #3 explicit — closeout ships zero new public types; AC-9 contract-snapshot cross-check catches. |
| Risk of new module under `src/codegenie/workflows/_e2e_helpers.py` | harden | Anti-refactor #4 explicit — all new code is under `tests/`. |
| Risk of `LangGraph` / `aiosqlite` / Hypothesis version-pinning churn | harden | Anti-refactor #5 explicit — closeout is not the place for stability pin work. |
| Risk of coverage ratchet bump slipping in under "closeout" | nit | Anti-refactor #6 explicit — deferred to a focused coverage story. |
| Conftest fixtures composed via dependency injection, not god-object | harden | Files-to-touch explicit (`tests/integration/workflows/conftest.py`); Refactor step pins the discipline. |
| Functional core / imperative shell for determinism property | harden | AC-6 — the byte-equality assertion is pure; the harness is the imperative shell. |
| Open/Closed at the YAML schema (Phase 7+ rows extend additively) | harden | AC-8 — the schema is `extra="forbid"`; new fields require explicit schema amendment. |

## Conflict resolution (priority: Consistency > Coverage > Test-Quality > Design-Patterns)

1. **"Phase 6.5 contract test imports VulnRemediationSut" interpreted as the existing placeholder fence vs. a complementary consumer-isolation test** (Coverage "the placeholder already exists, mark as covered" vs. Consistency "closure must be enforced during the Phase-6/Phase-6.5 gap"). **Resolution:** Consistency wins. AC-7 ships the complementary test today; the placeholder un-skips when Phase 6.5 lands.

2. **`tests/e2e/scenarios.yaml` as YAML+loader vs. parametrized rows** (Coverage "parametrized rows cover the same runtime assertion" vs. Consistency "the YAML is the cross-cutting test-architecture surface High-level-impl.md + roadmap name verbatim"). **Resolution:** Consistency + Design-Patterns win. AC-8 explicit YAML + loader. The parametrization in AC-1..AC-5 stays — AC-8 is cross-cutting infrastructure.

3. **Workflow-scope determinism N=50 vs. cheap-default** (Coverage "N=50 to match roadmap" vs. Test-Quality "N=50 takes 10-20 minutes; default test runs would time out"). **Resolution:** Test-Quality wins on the default; Consistency wins on the bench. AC-6 env-var-driven N + `@pytest.mark.bench` for the full N=50.

4. **Closeout discipline: silent abstraction additions vs. anti-refactor block** (Coverage "an abstract base class would make the tests DRYer" vs. Design-Patterns + Rule 2 "three similar lines is better than premature abstraction"). **Resolution:** Design-Patterns + Rule 2 win. Anti-refactor #1 explicit; closeout is not the place to introduce abstractions across one task class.

5. **`_BYTE_EQUAL_MODULO` duplication between AC-3 + AC-6** (Test-Quality "DRY across two consumers" vs. Rule 2 "rule-of-three not yet met"). **Resolution:** Test-Quality wins narrowly — the invariant is load-bearing for both ACs and an explicit module-import is cheaper than the cognitive cost of two sources of truth. Refactor step pins the discipline; the module-import is *not* an abstraction (no class, no factory, no decorator) — just a constant.

No `NEEDS RESEARCH` flag remained after critic synthesis. LangGraph integration, `asyncio.gather` concurrency, pytest-asyncio mechanics, Hypothesis `@settings` config, AST-walking fence patterns, and SQLite direct-mutation all have direct in-repo precedents.

## Stage 3 — Researcher

**Skipped.** No `NEEDS RESEARCH` flag from any critic remained unresolved after Stage-2 synthesis.

## Stage 4 — Edits applied

### Pre-validation story (16 lines)

```markdown
# S6-01 — E2E kill/resume closeout

**Status:** Ready
**Goal:** Prove the Phase 6 exit criteria end to end and publish the downstream handoff.

## Acceptance criteria

- Clean-completion, retry-recovery, kill/resume, and HITL-resume integrations pass.
- Phase 6.5 contract test imports `VulnRemediationSut`, not graph internals.
- Roadmap and docs links resolve to the Phase 6 package.

## TDD plan

Red: failing integration fixtures and docs assertions.
Green: finish workflow wiring.
Refactor: close duplicated fixture setup.
```

### Post-validation story (post-edit)

13 numbered checkbox ACs across seven labeled sub-sections (Scenario 1..5 + Cross-cutting test-architecture additions + Closeout sweep + Closeout discipline). Six-item Anti-refactor block. 16-entry Files-to-touch. 10-step TDD plan (Red → Green → Refactor → Anti-refactor). Out-of-scope. Notes-for-implementer (8 paragraphs covering: fixture cohort rationale; metamorphic kill-and-resume === never-killed Phase-9 inheritance; direct SQLite tamper rationale; concurrent `asyncio.gather` over sequential; AST-walking the synthetic consumer file; contract-snapshot SHA256 cross-check rationale; `extra="forbid"` YAML schema; Definition-of-done checkbox flip; no new `__all__` name rationale).

### Edits applied

| # | Source | Change |
|---|---|---|
| 1 | COV-clean-completion + TQ-mutation + CON-fixture-cohort | AC-1 — three parametrized fixtures + chain-content assertion + `subgraph` import-meta-assertion. |
| 2 | COV-retry-recovery + TQ-chain-walk + CON-failure-modes-row-5 | AC-2 — five-transition chain walk + test-double `GateRunner` via plugin adapter slot. |
| 3 | COV-kill-resume + TQ-metamorphic + DP-functional-core | AC-3 — metamorphic kill-and-resume === never-killed + chain-origin sub-assertion + `_BYTE_EQUAL_MODULO` allowlist. |
| 4 | COV-hitl + TQ-stale-resume + CON-failure-modes-row-4 | AC-4 — stale + valid resume + chain-origin sub-assertion. |
| 5 | COV-tampered-checkpoint + TQ-apply-call-count + CON-ADR-0003 | AC-5 — direct SQLite mutation + `apply()` call-count == 0 + `hydrate_or_fail` SOLE-site cross-check. |
| 6 | COV-determinism + TQ-Hypothesis + CON-roadmap | AC-6 — workflow-scope Hypothesis property + env-var N + `@pytest.mark.bench` for N=50. |
| 7 | COV-consumer-isolation + CON-final-design-Phase-6.5 + DP-extension-by-addition | AC-7 — synthetic-consumer source + AST walk + four-bullet closure. |
| 8 | COV-scenarios-yaml + CON-cross-cutting + DP-open-closed | AC-8 — YAML file (3 rows) + `extra="forbid"` + loader test. |
| 9 | COV-contract-snapshot + DP-cross-story-discipline | AC-9 — SHA256 cross-check across S5-01 → S6-01. |
| 10 | COV-docs + TQ-cross-link-walk | AC-10 — roadmap row + mkdocs nav + internal cross-link walk. |
| 11 | COV-definition-of-done + CON-stories-README | AC-11 — flip to `- [x]` + unit assertion. |
| 12 | COV-lessons + CON-cross-story-discipline | AC-12 — `_lessons.md` closeout entry + unit assertion. |
| 13 | COV-closeout + CON-no-amendments + DP-rule-2 | AC-13 — `make check` + meta-assertion no ADR amendments. |
| 14 | DP-Rule-2 anti-refactor | Anti-refactor block — six explicit deferrals (BaseE2ETestCase, @register_scenario, public-name extensions, _e2e_helpers module, dep-version churn, coverage ratchet). |
| 15 | All findings | Files-to-touch — 16 entries. |
| 16 | All findings | TDD plan — 10-step Red → 8-step Green → Refactor → Anti-refactor. |
| 17 | All findings | Out-of-scope (Phase-7 closeout; Phase-6.5 harness; Phase-9 Temporal; LangGraph version matrix; coverage ratchet; cross-task-class harness). |
| 18 | All findings | Notes-for-implementer (8 paragraphs). |

## Verdict rationale

**HARDENED.** The pre-validation story's intent (a Phase-6 closeout that proves the exit criteria end-to-end) was correct; every load-bearing implementation decision was implicit. Every weakness was in-place fixable. The hardened story sits structurally identical to its S1-01..S5-01 family precedents — same density, same anti-refactor discipline, same cross-story-substrate horizon (Phase-9 metamorphic inheritance), same Files-to-touch granularity. The closeout discipline (no new public types, no ADR amendments, no `__all__` extensions) is what distinguishes a closeout from an extension story; the Anti-refactor block makes the discipline structurally enforceable.

## Recommended next step

`phase-story-executor` on `docs/phases/06-sherpa-vuln-loop/stories/S6-01-e2e-kill-resume-closeout.md` *after* S5-01 ships (S6-01 reads `tests/golden/phase6-contract/.s5_01_post_sha256` which S5-01's executor writes; AC-9 will fail loud per Rule 12 if the anchor file is missing). All five integration tests + the determinism property + the consumer-isolation test + the YAML file + the docs assertions can be ship independently from each other; the dependency between them is *fixtures* (under `tests/integration/workflows/conftest.py`), not behaviour.
