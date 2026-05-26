# Validation report — S5-01 (Stable SUT adapter)

**Date:** 2026-05-26
**Validator:** phase-story-validator (inline four-lens analysis — Coverage, Test-Quality, Consistency, Design-Patterns — applied directly after Stage 1's Context Brief. Mirrors the in-phase precedent set by the S1-01, S1-02, S2-01, S2-02, S3-01, S3-02, S4-01 validations: pre-validation file was a 13-line stub; the four lenses converged sharply; spawning four parallel critic agents would have burned tokens without changing the verdict.)
**Verdict:** **HARDENED**
**Story path:** [`docs/phases/06-sherpa-vuln-loop/stories/S5-01-stable-sut-adapter.md`](../S5-01-stable-sut-adapter.md)

## Why HARDENED (not STRONG, not RESCUE)

The story's *architectural intent* matches every authoritative source — it builds the concrete `LocalVulnRemediationSut` adapter `High-level-impl.md §"Step 5"` pins, behind the four-name ADR-0001 contract S1-01 already shipped, on top of the LangGraph subgraph S3-01 will ship and the checkpoint substrate S2-01/S2-02 already shipped. But the pre-validation 13-line stub left every load-bearing decision implicit:

1. **AC count effectively 0.** Three dash bullets (`-`, not `- [ ]`); no checkbox-shaped, no individually verifiable, no third-party-pass/failable.
2. **"Harness can call only the stable contract"** is unanchored. Through what enforcement? `__all__` discipline? An import-fence? An AST walk over `tests/integration/phase65_harness/`? Multiple plausible mechanisms; pre-validation picked none.
3. **"Adapter returns sanitized result fields"** is satisfiable by an adapter that returns hardcoded empty tuples for `evidence_references` and `failure_modes` — passes "sanitized" trivially because there's nothing to sanitize. No mechanism for routing graph-produced refs through `EvidenceRef` smart-constructor; no failure mode for the case where the graph emits an absolute path.
4. **"`SutDigest` is deterministic for the same graph/config/prompt inputs"** conflates two distinct seams: the *per-case* digest S1-01's `_compute_sut_digest_input(case)` already ships, vs the *per-SUT* `digest()` method on the Protocol (which must summarise SUT identity: config + topology + cassette + canary + embedding-model digest). An executor would build only one and miss the Phase-9 §G5 byte-equality substrate the Protocol's `digest()` is for.
5. **No module path.** Where does the concrete adapter live? `src/codegenie/workflows/`? `plugins/.../api.py`? Both? The boundary is load-bearing: if it goes in `codegenie.workflows.__all__`, S1-01 AC-12's allowlist sentinel changes and the contract boundary erodes. Pre-validation picked nothing.
6. **No execution-mode dispatch.** S1-01 AC-3 closed `ExecutionMode = Literal["dry_run", "apply", "replay"]` — an executor will silently invent dispatch logic, likely an `if/elif/else` chain that swallows a future fourth mode. The closed `match` + `assert_never` pattern (Phase-3/4/6 canon) is not named.
7. **No projection table for `VulnLedgerState → VulnRemediationResult`.** Three terminal variants → three result-shapes; four non-terminal variants → `assert_never`. Without explicit enumeration, an executor would land an `if state.kind == "completed": ... elif ...: ...` that silently fails when S1-02's seven-variant union gains an additional state.
8. **No untyped-exception trap.** `phase-arch-design.md §"Failure modes"` row 5 is explicit ("planner/gate exception | node outcome wrapper | typed failed state, not traceback escape"). Without an AC, a graph-node `RuntimeError` escapes `ainvoke` and the bench sees a raw traceback — exactly the "fail loud, but route into the typed envelope" discipline this row mandates.
9. **No checkpointer-injection seam preservation.** S3-01 explicitly shipped `build_subgraph` as *uncompiled* so the adapter could `.compile(checkpointer=...)`. Pre-validation did not say the adapter accepts a `CheckpointStore` factory by constructor injection — an executor would hard-code `SqliteCheckpointStore(...)` and the Phase-9 Postgres swap becomes a kernel-edit.
10. **No workflow_id allocation discipline.** Each `run_case` must mint a fresh `WorkflowId` (ULID) and create a per-run directory rooted at `.codegenie/remediation/<id>/`. Without the AC, an executor could reuse a shared chain across cases — replay verification would conflate.
11. **No cancellation discipline.** Phase-6.5 wraps `run_case` in `asyncio.wait_for(..., timeout=600.0)` (final-design step 1 verbatim). The adapter MUST cleanly handle `CancelledError`: cleanup → re-raise. Swallowing would hang the bench worker pool indefinitely.
12. **No `digest()` purity enforcement.** S1-01 AC-7 shipped a *placeholder* AST fence (no `digest()` implementation existed yet); this story is exactly where it must start *biting*. Without an explicit AC, the placeholder remains trivially passing forever.
13. **No sole-importer fence.** `final-design.md §"Relationship to Phase 6.5"` verbatim: "Phase 6.5 may NOT depend on: the concrete graph builder; node names; checkpoint backend internals; plugin-local file layout." The structural enforcement is an AST fence asserting *exactly one* module imports the private builder. Pre-validation did not name this.
14. **No contract-snapshot extension.** Every prior Phase-6 story (S1-01..S4-01) extends `test_phase6_sut_contract_snapshot.py` additively; pre-validation said nothing.
15. **No `mypy --strict` AC.** Standard closeout.
16. **No anti-refactor block.** Under deadline pressure an executor could ship a `SutRegistry` / `@register_sut_kind` decorator / `BaseSut` ABC / `ResultBuilder` fluent API — every one a premature abstraction (S1-01 Notes-for-implementer §"SUT-registry rule-of-three" deferred this to Phase 9 + Phase 10 — second + third concrete SUTs).
17. **No mutation-resistance reasoning.** The three pre-validation ACs are each satisfiable by trivial mutants:
    - "Harness can call only the stable contract" — mutant: a stub that returns a hardcoded `VulnRemediationResult` regardless of input.
    - "Adapter returns sanitized result fields" — mutant: an adapter that always returns `evidence_references=()`.
    - "`SutDigest` is deterministic" — mutant: an adapter whose `digest()` returns the literal `SutDigest("blake3:" + "0"*64)`. Stable, deterministic, useless.

All in-place fixable; none requires re-running `phase-story-writer`. The story's structure survives — three bullets grew to 14 numbered checkbox ACs across seven labeled sub-sections + a five-item anti-refactor block + Files-to-touch (19 entries) + a 14-step TDD plan + Out-of-scope + Notes-for-implementer. Verdict: **HARDENED**.

## Context Brief (Stage 1)

### Story snapshot

- **Goal (pre-validation):** "Implement the concrete adapter behind `VulnRemediationSut` while keeping the graph builder private." Vague — no module path, no execution-mode dispatch, no projection-table discipline, no exception-trap, no checkpointer-injection, no `digest()` purity, no sole-importer fence.
- **Goal (post-validation):** ship `src/codegenie/workflows/local_sut.py` carrying (i) `LocalVulnRemediationSut` (the concrete implementer of the ADR-0001 Protocol — sole legal importer of S3-01's private `build_subgraph`); (ii) `SutConfig` (frozen + extra="forbid"; carries plugin_id, cassette_id, canary_pin, embedding-model digest, artifact_root, checkpoint_store_factory — Phase-9 Postgres swap is one factory change); (iii) `_project_terminal_state_to_result` (pure, total, exhaustive `match` + `assert_never` over the three terminal `VulnLedgerState` variants); (iv) the single `try/except Exception` site wrapping `graph.ainvoke` (untyped exceptions become `FailedUnrecoverable(reason="subgraph_aborted")` with exception-class-suffixed failure_modes); (v) separate `asyncio.CancelledError` handler (cleanup → re-raise; never swallow); (vi) per-run workflow_id + 0o700 directory allocation; (vii) closed-`match` execution-mode dispatch over `dry_run`/`apply`/`replay`; (viii) pure `digest()` that bites the S1-01 AC-7 placeholder AST fence; (ix) sole-importer fence; (x) contract-snapshot extension. This story is the fifth concrete consumer of the *pure-projection-table + closed-`match` + `assert_never` substrate* in Phase-6 (S1-02 ledger + S2-02 hydration + S3-01 routing + S4-01 resume-verdict + this).
- **Status pre-validation:** `Ready` — never executed; never validated.
- **Status post-validation:** `HARDENED`.

### Authoritative sources

- **final-design.md** §"Decisions of record" item 2 verbatim (the four ADR-0001 names; "The concrete LangGraph builder is behind the adapter" — drives AC-1 module placement + AC-13 sole-importer fence); §"Main workflow" step 7 ("Return `VulnRemediationResult` through `VulnRemediationSut`" — the adapter IS this return path); §"Relationship to Phase 6.5" verbatim ("may NOT depend on: the concrete graph builder; node names; checkpoint backend internals; plugin-local file layout" — drives AC-1 + AC-13 + AC-14 byte-equal `__all__`).
- **phase-arch-design.md** §"Logical view" (the seam the adapter occupies); §"Process view" (the H→S→G→S→H roundtrip); §"Failure modes" row 3 ("SUT result leaks prompt/raw path | contract serialization test | CI failure" — AC-7 + AC-8) + row 5 ("planner/gate exception | node outcome wrapper | typed failed state, not traceback escape" — AC-9); §"Testing strategy" ("Contract tests: SUT adapter round-trips only sanitized result fields" — AC-7 + AC-8 + AC-12).
- **ADR-0001** §Decision ("concrete LangGraph builder remains private" — AC-13 structural enforcement); §Consequences (contract amendment process — AC-12 contract-snapshot extension + meta-test).
- **ADR-0003** (checkpointer-injection seam — AC-4 constructor factory).
- **High-level-impl.md §Step 5** verbatim ("Implement the concrete adapter behind `VulnRemediationSut`. Keep graph builder private. Add contract tests proving Phase 6.5 can invoke the SUT without graph imports.").
- **S1-01 hardened story** — the four ADR-0001 names + `_compute_sut_digest_input(case)` pure helper (AC-10 distinguishes per-SUT `digest()` from per-case helper) + AC-7's placeholder AST fence (this story makes it bite) + AC-12 allowlist sentinel (this story keeps it byte-equal).
- **S1-02 hardened story** — `VulnLedgerState`; `_TERMINAL_LEDGER_KINDS`; `FailedUnrecoverableReason`; `HumanReviewReason` — AC-7 projection table reads exactly these closed sets.
- **S2-01 hardened story** — `CheckpointStore` Protocol; AC-4 constructor-injection.
- **S2-02 hardened story** — `hydrate_or_fail` is the SOLE integrity site; adapter does NOT recompute chain (Anti-refactor).
- **S3-01 hardened story** — `build_subgraph(deps: SubgraphDeps) -> StateGraph[SubgraphState]` (uncompiled); AC-2's "uncompiled" decision is what preserves AC-4's checkpointer-injection seam.
- **S4-01 hardened story** — `AwaitingHumanReview` projection branch (AC-7) maps to `terminal_state="awaiting_human_review"`; the resume gate is *not* exercised in this story (S6-01 owns the integration scenario).
- **Phase-6.5 final-design.md** §"Main workflow" step 1 verbatim (`asyncio.wait_for(system_under_test.run_case(case), timeout=600.0)` — AC-11 cancellation discipline + AC-2 iscoroutinefunction enforcement).
- **Phase-9 S4-05** §G5 — `digest()` byte-equality across Local + Temporal SUTs — AC-10 pure-helper + Hypothesis substrate-prep property pays the rent today.
- **Phase-3 `FallbackTierPlanRecipeEngine`** (`plugins/.../subgraph/fallback_plan_engine.py`) — canonical Phase-6 bridge-adapter idiom (translate call-shape, await collaborator, pure projection table with `assert_never`).
- **`_attempts/_lessons.md`** — three cross-story lessons applied: (a) "two definitions of terminal coexist" (S1-02) → AC-7's projection rejects non-terminal variants with typed `TypeError`; (b) "store types do NOT enter `__all__`" (S2-01) → AC-1 keeps `LocalVulnRemediationSut` out of `codegenie.workflows.__all__`; (c) "sanitization-aware fold" (S4-01) → AC-8's caplog assertion + redacted SHA256.

### Hardest design tensions resolved

**Tension 1 — `LocalVulnRemediationSut` exposed via `codegenie.workflows.__all__` vs plugin-internal.** The harness needs *some* way to construct an instance; the question is whether `codegenie.workflows` is the import path or the plugin's `api.py` is. Re-exporting from `codegenie.workflows` invites Phase-6.5 to skip the Protocol and import the concrete class for "convenience" (then later add a hard dependency on `LocalVulnRemediationSut`-specific attributes — Phase-9's `TemporalVulnRemediationSut` then can't substitute drop-in). The Protocol-only export is what makes ADR-0001's four-name commitment load-bearing. **Resolution:** the adapter is plugin-internal; the factory `build_local_sut(config) -> LocalVulnRemediationSut` lives in `plugins/.../api.py`; `codegenie.workflows.__all__` stays byte-equal at 14 names. Anti-refactor #5 explicit.

**Tension 2 — Direct `CheckpointStore` injection vs `Callable[[WorkflowId], CheckpointStore]` factory.** A bare `CheckpointStore` instance can't carry per-workflow state (the SQLite path contains the workflow_id). A factory absorbs the per-call binding. **Resolution:** factory wins; AC-4. The Phase-9 Postgres adapter takes a connection-pool + workflow_id constructor — the factory pattern survives.

**Tension 3 — `if/elif/else` mode dispatch vs `match` + `assert_never`.** Phase-3/4/6 canon is `match` + `assert_never` for closed sum types. An `if/elif/else` chain compiles even when a fourth ExecutionMode value is silently added. **Resolution:** `match` + `assert_never`; AC-6 has an AST fence asserting the shape (no `else`, no `if/elif` chain). Mirrors S2-02 verdict-dispatch pattern.

**Tension 4 — Catch-all `except BaseException` vs `except Exception` + separate `except CancelledError`.** The Phase-6.5 harness's `asyncio.wait_for(..., timeout=600.0)` raises `CancelledError`; the bench worker pool needs the cancellation to propagate. `BaseException` catches `KeyboardInterrupt` / `SystemExit` / `CancelledError` — all three would be silently swallowed. **Resolution:** exactly one `except Exception` block (the typed-trap site) + a separate `except asyncio.CancelledError` for cleanup + re-raise. AC-9 AST fence enforces both counts.

**Tension 5 — `digest()` summarises per-SUT identity vs per-case identity.** S1-01's `_compute_sut_digest_input(case)` is the per-case helper that feeds `VulnRemediationResult.sut_digest`. The Protocol's `digest() -> SutDigest` (no parameters) is a *per-SUT* identity summary. Conflating them would either (i) make `digest()` per-case (signature change, ADR-0001 amendment) or (ii) make `_compute_sut_digest_input` per-SUT (orphan helper). **Resolution:** keep both seams distinct; AC-10 enumerates the per-SUT inputs explicitly (plugin manifest digest, graph topology hash, cassette pin, canary pin, embedding-model digest, `SutConfig`); Notes-for-implementer §"Why `digest()` is per-SUT, not per-case" explicit.

**Tension 6 — Sanitization breach at projection time: swallow vs route to `subgraph_aborted`.** If the graph emits a `Completed.report_path = "/etc/passwd"`, the `EvidenceRef` smart-constructor raises `ValidationError`. Options: (a) swallow and substitute `"<redacted>"`; (b) re-project to `FailedUnrecoverable(reason="subgraph_aborted")`. (a) silently *unbreaks* a sanitization bug — the failure_mode list never grows, the bench scorecards report no anomaly. (b) routes the breach into the typed envelope, surfacing it loudly. **Resolution:** (b); AC-8 explicit. Defense-in-depth: emit a structured log carrying SHA256 of the rejected ref (forensics) but NEVER the rejected substring itself (the log line could be ingested by an external system).

**Tension 7 — Sole-importer fence vs `__all__` discipline.** The `__all__` allowlist (AC-1) is necessary but not sufficient — a test file can `import plugins.vulnerability_remediation__node__npm.subgraph.builder` for "introspection" and silently leak the dependency. The AST fence (AC-13) walks every Python file in `src/codegenie/`, `tests/`, `plugins/` and asserts the import substring appears in exactly one file. **Resolution:** ship both. Anti-refactor #5 keeps `__all__` honest; AC-13 keeps integration tests honest.

## Four-lens findings (inline, no parallel subagents)

### Lens 1 — Coverage

| Finding | Severity | Resolution |
|---|---|---|
| AC-1 "Harness can call only the stable contract" unverifiable — no enforcement mechanism named | block | AC-13 sole-importer fence + AC-1 `__all__` byte-equal guard + AC-12 contract-snapshot extension. |
| AC-2 "Adapter returns sanitized result fields" satisfiable by always-empty mutants | block | AC-7 explicit projection table + AC-8 EvidenceRef + caplog assertion + Hypothesis sanitization properties. |
| AC-3 conflates per-case vs per-SUT digest | block | AC-10 enumerates the per-SUT digest inputs; Notes-for-implementer §"Why `digest()` is per-SUT, not per-case" disambiguates. |
| No execution-mode dispatch | block | AC-6 closed `match` + `assert_never` over the three ExecutionMode Literal values + AST fence asserting the shape. |
| No projection table (terminal `VulnLedgerState` → `VulnRemediationResult`) | block | AC-7 explicit table + parity matrices (HumanReviewReason → error-id; FailedUnrecoverableReason → error-id) + Hypothesis round-trip property. |
| No untyped-exception trap | block | AC-9 single `try/except Exception` site + AST fence + exception-class-suffixed failure_modes + meta-test. |
| No workflow_id allocation discipline | block | AC-5 fresh ULID per run + 0o700 dir + Hypothesis concurrent-uniqueness property. |
| No cancellation discipline | block | AC-11 `asyncio.wait_for`-driven test + orphan-file assertion + signal-AST fence + AST guard for separate `CancelledError` arm. |
| No `digest()` purity enforcement | block | AC-10 stability + sensitivity + AST purity walk + Phase-9 substrate-prep property — actively bites the S1-01 AC-7 placeholder. |
| No checkpointer-injection seam preservation | harden | AC-4 `Callable[[WorkflowId], CheckpointStore]` factory injection + Mock-spec call-count test. |
| No closeout (mypy + lint + import-linter + ADR amendment) | harden | AC-14 + ADR-0004 amendment line + import-linter widening. |
| No anti-refactor block | harden | Anti-refactor block — five explicit deferrals (SutRegistry, RunContext god-object, SutFactory ABC, ResultBuilder fluent API, no `__all__` extension). |

### Lens 2 — Test Quality

| Finding | Severity | Resolution |
|---|---|---|
| Original ACs satisfiable by trivial mutants (always-empty refs, hardcoded result, hardcoded digest) | block | Every AC carries an explicit "Mutation thinking" note naming the mutation class it catches. |
| No mutation-resistance test for the projection table's non-terminal-rejection arms | block | AC-7 four negative tests (one per non-terminal variant) asserting `TypeError` with a specific message. |
| No Hypothesis property for projection-table round-trip | harden | AC-7 final Hypothesis property: arbitrary terminal `VulnLedgerState` → `_project_terminal_state_to_result` → `model_dump_json` → `model_validate_json` → byte-equal. |
| No meta-test for the contract-snapshot classifier extension | harden | AC-12 three new synthetic-snapshot classifications (additive method add; rename; sync/async flip). |
| No meta-test for the AST fences (sole-importer, single-exception-site) | harden | AC-9 + AC-13 ship synthetic broken-fixture rejection meta-tests. |
| `mint_workflow_id` determinism unspecified | harden | AC-5 uses existing kernel `parse_workflow_id` (ULID generation is upstream-defined; the test asserts uniqueness across calls, not the exact ULID format). |
| No per-mode behavioural test (just AST fence) | harden | AC-6 ships per-mode behavioural assertions in addition to the AST fence. |
| Time-mocking discipline for AC-11 timeout test | nit | Notes-for-implementer pinning `pytest-asyncio` + `asyncio.wait_for(..., timeout=0.01)` as the timeout-test mechanism. |

### Lens 3 — Consistency

| Finding | Severity | Resolution |
|---|---|---|
| Pre-validation Goal contradicted final-design §"Relationship to Phase 6.5" — silent leak of concrete class | block | AC-1 keeps `LocalVulnRemediationSut` plugin-internal; harness imports the Protocol only; `codegenie.workflows.__all__` byte-equal-unchanged at 14 names. |
| Pre-validation didn't address S3-01's uncompiled-StateGraph seam | block | AC-4 + AC-3 explicit constructor-injected `Callable[[WorkflowId], CheckpointStore]` factory; the adapter is the sole `.compile(checkpointer=...)` site. |
| Pre-validation didn't address S2-02's SOLE integrity site | harden | References block + Anti-refactor #1 implicit (Anti-refactor block prohibits re-implementing chain verification; the `hydrate_or_fail` SOLE-site discipline is preserved). |
| Pre-validation didn't address S1-01 AC-7 placeholder fence biting now | block | AC-10 actively enforces AST purity over `digest()` — the placeholder AC-7 ships with this story. |
| Pre-validation didn't address ADR-0004 path-scope widening | harden | AC-14 explicit ADR-0004 amendment line + import-linter widening + structural sole-importer fence. |
| Pre-validation didn't address `codegenie.workflows.__all__` byte-equality | block | AC-1 explicit byte-equality regression-pin. |
| Pre-validation didn't address phase-arch-design.md §"Failure modes" row 5 | block | AC-9 single-site exception trap + exception-class-suffixed failure_modes. |
| Pre-validation didn't address Phase-6.5 timeout contract | block | AC-11 cancellation discipline + AC-2 iscoroutinefunction enforcement. |
| Pre-validation didn't address Phase-9 §G5 substrate prep | harden | AC-10 Hypothesis substrate-prep property pays Phase-9 rent today. |

### Lens 4 — Design Patterns

| Finding | Severity | Resolution |
|---|---|---|
| Risk of `SutRegistry` / `BaseSut` ABC / `@register_sut_kind` decorator under deadline pressure | block | Anti-refactor #1 explicit — rule-of-three for SUT registry is unmet; defer to Phase 9 + Phase 10. |
| Risk of `RunContext` god-object carrying every port reference | harden | Anti-refactor #2 — `_RunContext` carries only per-run derived values; no port references. |
| Risk of `SutFactory` ABC for one concrete factory | harden | Anti-refactor #3 — `from_plugin` is a classmethod; no ABC. |
| Risk of `ResultBuilder` fluent API hiding the exhaustive-`match` discipline | harden | Anti-refactor #4 — pure projection table reads like prose; no builder. |
| Risk of `LocalVulnRemediationSut` leaking into `codegenie.workflows.__all__` | block | Anti-refactor #5 + AC-1 byte-equality regression-pin. |
| `_project_terminal_state_to_result` must be pure (functional core); `run_case` is the imperative shell | harden | AC-7 AST purity fence; CLAUDE.md "Functional core / imperative shell" precedent. |
| Closed `match` + `assert_never` over `ExecutionMode` and `VulnLedgerState` terminal variants | harden | AC-6 + AC-7 explicit; AST fences. |
| Constructor-injected `CheckpointStore` factory (DIP) | harden | AC-4 — the Phase-9 Postgres swap is one factory change. |
| Pure `digest()` (functional core; substrate for Phase-9 §G5) | harden | AC-10 AST purity + Hypothesis substrate-prep property. |
| Single-exception-site discipline (Open/Closed at the boundary) | harden | AC-9 AST fence — exactly one `try/except Exception` + zero `except BaseException`. |
| Sole-importer fence (extension-by-addition for graph-builder consumers) | harden | AC-13 — exactly one importer. |

## Conflict resolution (priority: Consistency > Coverage > Test-Quality > Design-Patterns)

1. **`LocalVulnRemediationSut` exported from `codegenie.workflows.__all__` vs plugin-internal** (Coverage "harness needs a way to construct" vs Consistency "final-design §Phase-6.5 forbids concrete-class import"). **Resolution:** Consistency wins. The factory `build_local_sut(config)` lives in `plugins/.../api.py`; the harness imports the Protocol from `codegenie.workflows` and the factory from the plugin's `api.py`. Anti-refactor #5 explicit.

2. **Hard-coded `SqliteCheckpointStore` vs `Callable[[WorkflowId], CheckpointStore]` factory** (Design-Patterns DIP vs Coverage "simpler"). **Resolution:** Design-Patterns wins — the rule-of-three is *already met* (in-memory + SQLite shipped; Phase-9 Postgres pending). AC-4 explicit.

3. **`if/elif/else` mode dispatch vs closed `match` + `assert_never`** (Test-Quality "easier to test" vs Design-Patterns + Consistency "closed-sum-type discipline"). **Resolution:** Consistency + Design-Patterns win. AC-6 + AST fence.

4. **Swallow ValidationError on EvidenceRef vs route to `subgraph_aborted`** (Coverage "preserve the result for forensics" vs Consistency "failure-mode taxonomy"). **Resolution:** Consistency wins — silently swallowing a sanitization breach is the worst-case bench-scorecard failure mode. AC-8 explicit.

5. **`except BaseException` vs `except Exception` + separate `CancelledError`** (Coverage "catch everything" vs Consistency "must propagate cancellation"). **Resolution:** Consistency wins. AC-9 single-site discipline + AC-11 separate CancelledError arm.

No `NEEDS RESEARCH` flag remained after critic synthesis (LangGraph `AsyncSqliteSaver` API, BLAKE3 invocation, asyncio cancellation discipline, AST-walking fence pattern all have direct in-repo precedents).

## Stage 3 — Researcher

**Skipped.** No `NEEDS RESEARCH` flag from any critic remained unresolved after Stage-2 synthesis.

## Stage 4 — Edits applied

### Pre-validation story (13 lines)

```markdown
# S5-01 — Stable SUT adapter

**Status:** Ready
**Goal:** Implement the concrete adapter behind `VulnRemediationSut` while keeping the graph builder private.

## Acceptance criteria

- Harness can call only the stable contract.
- Adapter returns sanitized result fields.
- `SutDigest` is deterministic for the same graph/config/prompt inputs.

## TDD plan

Red: contract-only consumer test.
Green: implement adapter.
Refactor: move private builder imports behind the adapter.
```

### Post-validation story (post-edit)

14 numbered checkbox ACs across seven labeled sub-sections (Public surface + module shape; Constructor + factory + dependency injection; Workflow allocation + per-run artifact directory; Execution-mode dispatch; Pure projection table; Sanitization-enforced-by-construction; Untyped-exception trap; Pure `digest()`; Cancellation, timeout, and resource discipline; Contract snapshot + JSON round-trip + harness-side import fence; mypy/lint discipline). Five-item Anti-refactor block. 19-entry Files-to-touch. 14-step TDD plan (Red → Green → Refactor → Anti-refactor). Out-of-scope. Notes-for-implementer (8 paragraphs covering: plugin-internal placement; per-SUT vs per-case digest; projection AST fence; EvidenceRef wash; exception-class suffix forensics; CancelledError discipline; checkpoint-store factory rationale; ADR-0004 amendment rationale; Phase-9 §G5 substrate; per-run dir mode rationale).

### Edits applied

| # | Source | Change |
|---|---|---|
| 1 | COV-1 + CON-1 + Anti-refactor #5 | AC-1 — explicit module path; `__all__` byte-equality regression-pin; concrete class is plugin-internal. |
| 2 | COV-Protocol + TQ-iscoroutinefunction | AC-2 — five-test Protocol conformance (iscoroutinefunction + get_type_hints + isinstance + method allowlist + no extra public methods). |
| 3 | DP-DIP + COV-no-env | AC-3 — `SutConfig`-only configuration surface; AST fence over env reads. |
| 4 | DP-DIP + CON-S3-01 seam | AC-4 — `Callable[[WorkflowId], CheckpointStore]` factory injection; Mock-spec call-count test. |
| 5 | COV-workflow-id | AC-5 — fresh ULID per run + 0o700 dir + Hypothesis concurrent-uniqueness property. |
| 6 | COV-mode-dispatch + DP-closed-match | AC-6 — closed `match` + `assert_never` over ExecutionMode + AST fence asserting the shape. |
| 7 | COV-projection + TQ-round-trip + DP-purity | AC-7 — explicit three-variant projection table + parity matrices + four negative tests + AST purity fence + Hypothesis round-trip property. |
| 8 | COV-sanitization + TQ-caplog + DP-defense-in-depth | AC-8 — EvidenceRef wash + structured-log SHA256 redaction + three Hypothesis properties + caplog assertion that the rejected ref does NOT appear. |
| 9 | COV-exception + DP-OCP-boundary + TQ-meta-test | AC-9 — single `try/except Exception` site + AST fence + exception-class-suffixed failure_modes + meta-test rejecting synthetic two-`except` fixture + CancelledError re-raise + KeyboardInterrupt propagation. |
| 10 | COV-digest-purity + S1-01 AC-7 bite + Phase-9 §G5 | AC-10 — stability + sensitivity + AST purity walk + Phase-9 substrate-prep Hypothesis property + alphabetical-keys canonical JSON. |
| 11 | COV-cancellation + Phase-6.5 timeout | AC-11 — `asyncio.wait_for(..., timeout=0.01)` test + orphan-file assertion + signal-AST fence + AST guard for `raise` after cleanup. |
| 12 | COV-contract-snapshot + S1-01 AC-9 precedent | AC-12 — additive snapshot extension + three new synthetic-snapshot classifications. |
| 13 | CON-final-design-Phase-6.5 + DP-extension-by-addition | AC-13 — sole-importer fence walking `src/`, `tests/`, `plugins/`; synthetic-leak fixture rejection meta-test. |
| 14 | COV-closeout + CON-ADR-0004 | AC-14 — mypy/lint/import-linter + ADR-0004 amendment line + import-linter widening; structural fence is the actual policy enforcement. |
| 15 | DP-Rule-2 anti-refactor | Anti-refactor block — five explicit deferrals (SutRegistry, RunContext god-object, SutFactory ABC, ResultBuilder fluent API, no `__all__` extension). |
| 16 | All findings | Files-to-touch — 19 entries. |
| 17 | All findings | TDD plan — 14-step Red → 8-step Green → Refactor → Anti-refactor. |
| 18 | All findings | Out-of-scope (S6-01 e2e composition; Phase-6.5 harness-side fence; Phase-9 Temporal SUT; replay-determinism property; resume-from-paused integration; SutRegistry; LangGraph-version hardening). |
| 19 | All findings | Notes-for-implementer (8 paragraphs). |

## Verdict rationale

**HARDENED.** The pre-validation story's intent (a concrete SUT adapter that hides the graph from the harness) was correct; every load-bearing implementation decision was implicit. Every weakness was in-place fixable. The hardened story sits structurally identical to its S1-01..S4-01 family precedents — same density, same anti-refactor discipline, same Phase-9 substrate-prep horizon, same Files-to-touch granularity. The substrate-discipline carries Phase-6's contract boundary across into Phase-6.5 (timeout + cancellation contract), Phase-9 (`digest()` byte-equality), and Phase-10+ (any future task class's SUT adapter pattern).

## Recommended next step

`phase-story-executor` on `docs/phases/06-sherpa-vuln-loop/stories/S5-01-stable-sut-adapter.md` *after* S3-01 ships (the adapter imports from a builder that does not exist yet). The TDD plan's Step 1 (`import codegenie.workflows.local_sut` failing) is independent of S3-01 and can be greenlit immediately to validate the scaffold; Step 5 (the imperative shell) requires S3-01's `build_subgraph` and S4-01's HITL-projection branch.
