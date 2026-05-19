# Story S12-03 — `Both` coordination e2e + `Both` property tests

**Step:** Step 12 — End-to-end test suite + property tests + adversarial tests + regression-gate enforcement
**Status:** Ready
**Effort:** L
**Depends on:** S12-01 (fixture portfolio)
**ADRs honored:** ADR-0001 (no `MultiPluginCoordinator` in Phase 7 — this e2e is the load-bearing proof that the contract holds: `Both` produces evidence, NOT coordination), ADR-0004 (`Provenance` discriminated union — the e2e asserts on the `Both(...)` variant typed via the seven-variant union), ADR-0006 (explicit `_ADAPTER_DISPATCH_ORDER` — `Both` arises from the `match (app, base)` composition only when both layers resolve non-`Unknown`), ADR-0008 (no `vuln.provenance` cache — `Both` is recomputed deterministically), ADR-0017 (**this is the ADR S12-03 exists to prove**: exit code 8 + `coordination-summary.yaml` + `RequiresMultiPluginCoordination` event; the e2e is the ADR's empirical reality-check).

## Context

This is THE headline test for the load-bearing roadmap-coherence claim of Phase 7:

> "When a CVE is present in BOTH the app layer (npm transitive) AND the base-image layer (apk pkg), `assemble_provenance` returns `Both`; the orchestrator emits exactly one `RequiresMultiPluginCoordination` event into the spanning log; writes `coordination-summary.yaml`; exits with code 8; and **does NOT open a PR**."

This is the proof that "extension by addition" works:

- Phase 3's vulnerability-remediation plugin and Phase 7's distroless-migration plugin both match `(task=vulnerability-remediation, language=node, build=npm)`.
- Either picking one and silently dropping the other, OR shipping a `MultiPluginCoordinator` that runs both as child workflows — both options were explicitly rejected (ADR-0001).
- Instead: produce **evidence**. Write the typed event into the spanning log. Phase 8's Planner (months from now) reads the event and emits coordinated child workflows. Phase 7 stops at the event boundary.

`S12-03` ships THREE artifacts:

1. **`tests/e2e/test_both_provenance_emits_coordination_event_e2e.py`** (`@pytest.mark.phase07_e2e`) — the headline e2e against `tests/fixtures/portfolio/node-vulnerable-alpine/`.
2. **`tests/property/vuln_provenance/test_both_invariant.py`** — Hypothesis property test: for any non-`Unknown` `(AppKind, BaseKind)` pair, `assemble_provenance` returns `Both(app_record, base_record)` with NO nested `Both` (locks the discriminated-union shape from ADR-0004).
3. **`tests/property/vuln_provenance/test_both_always_emits_coordination.py`** — Hypothesis property test: for every workflow where `assemble_provenance` returns `Both`, the spanning event log has exactly ONE `RequiresMultiPluginCoordination` event AND the CLI exit code is 8 AND `coordination-summary.yaml` is written.

Together these three artifacts pin ADR-0017's contract at three levels: e2e (the system actually behaves this way), property (the invariant holds across all generated inputs), and golden-file (the `coordination-summary.yaml` shape is locked across changes).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Scenarios §Scenario C — Both variant: emit RequiresMultiPluginCoordination` (lines 455–486) — the exact sequence this e2e implements.
  - `../phase-arch-design.md §Testing strategy §End-to-end tests` (line 1278) — the e2e + the no-PR invariant.
  - `../phase-arch-design.md §Testing strategy §Property tests (Hypothesis)` (lines 1280–1286) — the two property tests verbatim.
  - `../phase-arch-design.md §Component design §13 — RequiresMultiPluginCoordination event + coordination-summary.yaml writer` (lines 905–949) — the typed event + YAML shape.
- **Phase ADRs:**
  - `../ADRs/0017-both-provenance-exits-code-8-with-coordination-summary.md` — **the load-bearing ADR this story proves**. Read it in full; every AC traces to a line in this ADR.
  - `../ADRs/0001-no-multi-plugin-coordinator-in-phase-7.md` — explains WHY Phase 7 doesn't ship a coordinator; the e2e proves the rejection holds.
- **Existing code:**
  - S11-01 — `RequiresMultiPluginCoordination` typed event (`src/codegenie/primitives/vuln_provenance/events.py`).
  - S11-02 — `emit_coordination(...)` writer + `coordination-summary.yaml` schema + `_index.tsv`.
  - S11-04 — `EXIT_PENDING_COORDINATION = 8` constant + CLI wiring.
  - `tests/golden/coordination-summary/both-app-direct-plus-base-image.yaml` — the golden file from S11-02; the e2e asserts byte-equality against this (modulo time-varying fields).

## Goal

Land three test artifacts that together pin ADR-0017's contract:

1. The headline e2e exercising the full vulnerable-Node.js-with-`Both`-layers → coordination-summary + exit-8 path on a `--privileged` Linux runner.
2. A Hypothesis property test pinning the `Both` discriminated-union shape (no recursion, typed records).
3. A Hypothesis property test pinning the "every `Both` workflow emits exactly one coordination event AND exits 8 AND writes summary" invariant.

## Acceptance criteria

### Part A — e2e test (`tests/e2e/test_both_provenance_emits_coordination_event_e2e.py`)

**Fixture + CLI invocation (AC-1, AC-2)**
- [ ] **AC-1** The e2e invokes `codegenie remediate <fixture-path> --cve <pinned-cve-id>` via `SubprocessJail` against `tests/fixtures/portfolio/node-vulnerable-alpine/` (the `Both` fixture from S12-01 AC-1). The CVE ID is pinned in the fixture's README AND in the e2e file as `_PINNED_CVE` constant; verified by a guard test that the two match.
- [ ] **AC-2** The subprocess exits with code **8** (the `EXIT_PENDING_COORDINATION` value from S11-04). Verified by `assert result.returncode == 8, result.stderr` — failure message includes stderr so future debugging sees the exit-code mismatch reason immediately (Rule 12).

**`Both` variant + event emission (AC-3, AC-4, AC-5)**
- [ ] **AC-3** Exactly ONE `RequiresMultiPluginCoordination` event lands in `<tmp_path>/.codegenie/events/spanning/*.jsonl.zst`. Verified by zstandard-decompressing the spanning log, parsing as JSONL, filtering on `kind == "requires_multi_plugin_coordination"`, asserting `len(filtered) == 1`.
- [ ] **AC-4** The emitted event's `app_record` field deserializes to a non-`Unknown` `AppKind` variant (either `AppDirect` or `AppTransitive`) AND `base_record` deserializes to a non-`Unknown` `BaseKind` variant (`BaseImage(...)`). Verified by Pydantic round-trip: `RequiresMultiPluginCoordination.model_validate(event_dict)` succeeds without falling back to `Unknown`.
- [ ] **AC-5** The event's `schema_version` is exactly `"phase-7-0"` (per S11-01 + Gap 2 forward-compat hook). Verified by direct field equality — any drift (e.g., `"phase-7-1"`) fails this AC.

**`coordination-summary.yaml` write + golden (AC-6, AC-7, AC-8)**
- [ ] **AC-6** `<tmp_path>/.codegenie/coordination/<workflow_id>.yaml` exists; the path's `<workflow_id>` segment is a valid `WorkflowId` newtype value (round-trippable). The YAML validates against the `CoordinationSummary` Pydantic schema from S11-02 (`extra="forbid"`).
- [ ] **AC-7** The YAML byte-equals the golden file `tests/golden/coordination-summary/both-app-direct-plus-base-image.yaml` (from S11-02), after redacting time-varying fields (`workflow_id`, `emitted_at`). Mismatch prints a unified diff with a copy-paste-ready `--update-goldens` hint.
- [ ] **AC-8** `<tmp_path>/.codegenie/coordination/_index.tsv` has exactly ONE line appended for this workflow (the append-on-write index from S11-02 / Gap 5). The line's columns match `<workflow_id>\t<cve_id>\t<emitted_at>\t<summary_path>` (or whatever the S11-02-pinned schema is — read S11-02's golden before pinning here).

**No-PR + exit-code-8 invariants (AC-9, AC-10)**
- [ ] **AC-9** **No PR is opened.** `gh` is NOT invoked. Verified by `assert "gh" not in [call.binary for call in jail.recorded_calls]`. This is the load-bearing Phase-7-stops-here invariant from ADR-0017 + `High-level-impl.md §Step 12`.
- [ ] **AC-10** No `Both` row is written to any `remediation-report.yaml` (the migration plugin's `subgraph/api.py::emit_coordination` returns `Applicability.PendingCoordination` BEFORE the remediation-report writer fires — verified by `assert not (tmp_path / ".codegenie/remediation").exists() or not any((tmp_path / ".codegenie/remediation").iterdir())`). Phase 7 emits the coordination evidence and stops; no remediation report is produced for `Both` workflows.

**Marker + skip guard (AC-11)**
- [ ] **AC-11** Same `@pytest.mark.phase07_e2e` decoration + same Linux-`--privileged`-only skip guard as S12-02 AC-12 + AC-13. Skip reason: `"phase07_e2e (Both coordination) requires Linux --privileged runner"`. Override via `CODEGENIE_FORCE_PHASE07_E2E=1`.

### Part B — `test_both_invariant.py` (Hypothesis property)

**Property: `Both` is shaped correctly (AC-12, AC-13)**
- [ ] **AC-12** `tests/property/vuln_provenance/test_both_invariant.py::test_both_record_pair_produces_both_variant_no_recursion` — Hypothesis strategy `non_unknown_app_kinds()` × `non_unknown_base_kinds()` (each draws from the closed sum-type variants per S1-02 / S1-03). Property: for every drawn pair `(app, base)`, `assemble_provenance` with adapters stubbed to return `(app, base)` returns `Both(app_record=app, base_record=base)`. Verified by `isinstance(result, Both)` AND `result.app_record == app` AND `result.base_record == base`.
- [ ] **AC-13** **No nested `Both`.** The property test ALSO asserts `not isinstance(result.app_record, Both)` AND `not isinstance(result.base_record, Both)`. If a typo or schema-drift ever lets `Both(Both(...), ...)` materialize, Pydantic's `extra="forbid"` + the nested discriminated union from S1-03 should `raise ValidationError` — the test asserts that `pydantic.ValidationError` (NOT a silent acceptance) is raised when constructing `Both(app_record=Both(...), base_record=...)` directly. Two assertions: one positive (well-formed `Both` is accepted), one negative (recursive `Both` is rejected at type construction).

**Hypothesis discipline (AC-14)**
- [ ] **AC-14** Pinned Hypothesis seed via `@settings(database=None, deadline=None, derandomize=True)` OR an explicit `@seed(<int>)` decorator. Print the seed in test failures so re-runs are reproducible (Rule 12). 200+ examples per run (Hypothesis default is 100; `Both` shape is load-bearing enough to deserve 2×).

### Part C — `test_both_always_emits_coordination.py` (Hypothesis property)

**Property: every `Both` workflow emits exactly one event + exit 8 + summary written (AC-15, AC-16, AC-17)**
- [ ] **AC-15** `tests/property/vuln_provenance/test_both_always_emits_coordination.py::test_both_workflow_emits_one_event_writes_summary_exits_8` — Hypothesis strategy `both_provenance_workflows()` generates synthetic workflows (`workflow_id`, `cve_id`, `app_record`, `base_record`) where `assemble_provenance` returns `Both(...)`. Adapters are stubbed; the property test invokes the orchestrator subgraph directly (not the full CLI — this is a property test, not an e2e). Property: after the subgraph runs, the spanning log has exactly ONE `RequiresMultiPluginCoordination` event for the workflow's ID; the orchestrator's `Applicability` is `PendingCoordination`; `coordination-summary.yaml` exists for the workflow.
- [ ] **AC-16** Exit-code-8 mapping is verified at the orchestrator level: `assert orchestrator.exit_code_for(PendingCoordination) == 8`. The CLI's `EXIT_PENDING_COORDINATION = 8` constant from S11-04 is the single source of truth (do not hardcode `8` in this test; import the constant).
- [ ] **AC-17** **Idempotence under retry.** If the same workflow is re-emitted (same `workflow_id`), exactly ONE event remains in the spanning log (the writer is append-only with `WorkflowId` uniqueness — if a second event lands with the same ID, the test fails AND a follow-up issue is filed; per S11-02 Tradeoff). This pins the load-bearing append-only invariant from `High-level-impl.md §What's next §New CI gates` line 445.

**Property test gates (AC-18, AC-19)**
- [ ] **AC-18** `pytest tests/property/vuln_provenance/test_both_invariant.py tests/property/vuln_provenance/test_both_always_emits_coordination.py` green on every PR (these property tests do NOT require `--privileged` Linux — they run in the regular `make check` pyramid).
- [ ] **AC-19** Both property tests respect `make check`'s coverage gate (no `--no-cov` workaround); they contribute to the ≥ 90% line coverage on `src/codegenie/primitives/vuln_provenance/` from `phase-arch-design.md §Testing strategy §Test pyramid` line 1261.

### Gates inherited from Definition of Done
- [ ] **AC-20** Byte-edit allowlist fence S5-01 green: new files only under `tests/e2e/`, `tests/property/vuln_provenance/`. No `src/codegenie/` byte-edit.
- [ ] **AC-21** `mypy --strict tests/e2e/test_both_provenance_emits_coordination_event_e2e.py tests/property/vuln_provenance/test_both_*.py` clean.
- [ ] **AC-22** `make check` green (excluding `phase07_e2e`); CI matrix-split job green for `phase07_e2e`.

## Implementation outline

1. **Read S11-01 / S11-02 / S11-04 first.** The event schema, the YAML writer, and the exit-code constant are the seams this story tests; without internalizing their shape, the assertions drift.
2. **Author the e2e** (Part A): `setup` (copy `node-vulnerable-alpine/` to `tmp_path`), `act` (invoke `codegenie remediate` via `SubprocessJail`), `assert` (AC-1..AC-11). Use the same redaction helper as S12-02 for time-varying fields.
3. **Author `test_both_invariant.py`** (Part B): two Hypothesis strategies (`non_unknown_app_kinds`, `non_unknown_base_kinds`); the property under test is the typed shape from S1-03. The negative `pydantic.ValidationError` assertion is a separate, non-Hypothesis unit test (Hypothesis is for the positive sweep; the negative is single-case).
4. **Author `test_both_always_emits_coordination.py`** (Part C): one Hypothesis strategy (`both_provenance_workflows`); the property under test is the typed contract from ADR-0017. Adapter stubs are constructed via `unittest.mock` or a tiny in-test `class StubAdapter`. The orchestrator subgraph is invoked directly (NOT via CLI).
5. Run all three artifacts; capture the actual `coordination-summary.yaml` from the e2e run; verify byte-equality with S11-02's golden.
6. Mutation guards (see TDD plan below).

## TDD plan (red-green-refactor)

### Red
1. Write all three test files with stubbed `# TODO` bodies plus the assertion shape but no implementation. Run: all three fail (e2e fails on missing fixture / non-zero exit code OR skipped on macOS; property tests fail on import errors or stub-only bodies).
2. Specifically, write the e2e's AC-2 assertion `assert result.returncode == 8` first; without S11-04's wiring this would have returned 0 or 1. (Step 11 must be merged before this story runs green; the dependency DAG enforces it.)

### Green
1. The e2e: copy fixture, invoke CLI, walk the assertions. The `Both` fixture from S12-01 + the S10/S11 chain (recipes + gates + event emission + exit-code wiring) must all be green for the e2e to pass.
2. `test_both_invariant.py`: implement the two Hypothesis strategies (drawing from `AppKind` / `BaseKind` sum-type variants), implement the property body. Run Hypothesis with the pinned seed; 200+ examples pass.
3. `test_both_always_emits_coordination.py`: implement the `both_provenance_workflows` strategy, invoke the subgraph, assert event-count + exit-code mapping + summary-write.

### Refactor
1. Extract the time-varying-fields redaction helper into the conftest if S12-02 hasn't already done so.
2. **Mutation guard #1 (positive correctness):** temporarily change S2-04's `match (app, base)` composition to always return `app` (silently dropping `base`). Re-run the e2e + property tests; AC-3 (event count) and AC-15 (every-`Both`-emits) must fail. Revert.
3. **Mutation guard #2 (no-PR invariant):** temporarily add a `subprocess.run(["gh", "pr", "create", ...])` line into the orchestrator's `PendingCoordination` arm. AC-9 must fail. Revert.
4. **Mutation guard #3 (nested-`Both` rejection):** temporarily relax S1-03's nested discriminated union (e.g., change `app_record: AppKind` to `app_record: AppKind | Both`). The negative ValidationError assertion in AC-13 must fail. Revert.
5. **Mutation guard #4 (idempotence under retry):** temporarily make the spanning-log writer append even on duplicate `workflow_id`. AC-17 must fail. Revert.

## Files to touch

**New files:**
- `tests/e2e/test_both_provenance_emits_coordination_event_e2e.py`.
- `tests/property/vuln_provenance/test_both_invariant.py`.
- `tests/property/vuln_provenance/test_both_always_emits_coordination.py`.

**Read-but-not-modified files** (these are tested but not edited; if any need edits, surface as a follow-up rather than blending into this story per Rule 7 + ADR-0009):
- `tests/golden/coordination-summary/both-app-direct-plus-base-image.yaml` (S11-02's golden).
- `src/codegenie/primitives/vuln_provenance/events.py` (S11-01).
- `src/codegenie/cli/exit_codes.py` (S11-04).
- `plugins/distroless-migration--node--npm/subgraph/api.py` (S11-02).

## Out of scope

- The single-plugin happy path e2e — S12-02.
- The other property tests already shipped in S2-05 (dispatch order, idempotence) and S4-04 (SBOM tampering).
- Adversarial tests — S12-04.
- Perf benchmarks — S12-05.
- CI workflow YAML — S12-05.
- Phase 8's Planner reading the event — out of Phase 7's scope per ADR-0001.

## Notes for the implementer

- **The e2e is the contract evidence; the property tests are the contract reinforcement.** If you only ship the e2e, a single-fixture happy path proves the contract for one CVE; the property tests prove the contract for the entire `(AppKind × BaseKind)` cross-product. Both are needed.
- **AC-13 (no nested `Both`) is the load-bearing type-discipline check.** If a future refactor accidentally makes `app_record: AppKind | Both`, the universe of `Provenance` becomes infinite-depth recursive and Phase 8's Planner cannot pattern-match exhaustively. The negative ValidationError assertion is the canary.
- **AC-9 (no PR) is the load-bearing scope-discipline check.** Phase 7 explicitly stops at the event boundary (ADR-0001 + ADR-0017). Any code path that opens a PR for a `Both` workflow IS the architectural failure this whole phase is designed to prevent. The `gh` not-invoked assertion is the structural firewall.
- **Hypothesis strategies must draw from the closed sum-type variants, NOT free-form `str`.** Per Rule 9 (tests verify intent), a strategy that generates random strings for `AppKind.distro` would never test the real type discipline. Use `hypothesis.strategies.sampled_from(get_args(AppKind))` or equivalent.
- **Pin the Hypothesis seed.** Flaky property tests destroy trust in the gate. `@settings(derandomize=True)` is the safest; `@seed(<int>)` is fine if explicit; **never** unpinned.
- **Rule 11 — codebase conventions.** Phase 1/2 property tests live under `tests/property/`; new Phase 7 property tests go under `tests/property/vuln_provenance/`. Mirror the existing subfolder convention; do not invent `tests/property/phase07/`.
- **Surface conflicts (Rule 7).** If S11-02's golden file uses a different field order or naming than this story assumes, **defer to S11-02** (the more recent / load-bearing story) and update this story's expectations rather than the golden file.
- **Idempotence under retry (AC-17) interacts with Gap 5 in arch.** The `_index.tsv` append-on-write semantics need to match: appending twice for the same `WorkflowId` is the failure mode. Read S11-02's notes carefully; if S11-02 chose to allow duplicate rows with a downstream dedup, AC-17 needs to phrase the invariant differently (e.g., "exactly one row when read through the dedup projection"). Surface this in `_validation/S12-03.md` if it bites.
