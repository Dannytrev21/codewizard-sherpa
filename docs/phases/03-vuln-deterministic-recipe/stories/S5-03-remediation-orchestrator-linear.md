# Story S5-03 — `RemediationOrchestrator` — `remediate()` linear six-call sync orchestrator (`transforms/coordinator.py`)

**Step:** Step 5 — Ship `NpmPackageUpgradeTransform`, `RemediationOrchestrator`, `PatchBranchWriter`, and the `codegenie remediate` CLI surface
**Status:** Ready
**Effort:** L
**Depends on:** S5-01 (`NpmPackageUpgradeTransform`), S5-02 (`load_context` + `RepoContextView`), S4-01 (`LockfilePolicyScanner`), S4-02/03/04 (`ValidationGate`), S4-05 (`TrustScorer` + escalation surface), S3-06 (`RecipeSelector` + `RecipeSelection`), S2-07 (`CveFeedReader`), S2-08 (retraction probe — not invoked here but the freshness contract).
**ADRs honored:** ADR-0001, ADR-0002, ADR-0005, ADR-0006, ADR-0007, ADR-0008, ADR-0013

## Context

The orchestrator is **the** integration point for every Phase-3 component and the single load-bearing claim for "single-repo, local, deterministic" (`roadmap.md §Phase 3`). It is six explicit function calls in sequence: `load_context → resolve_advisory → select_recipe → scan_lockfile → apply_transform → validate → write_branch`. No async, no retry inside, no clever generalization — Phase 5 wraps with three-retry gate machinery without changing the signature; Phase 6 wraps with LangGraph; Phase 9 wraps with Temporal Activities. The contract Phase 5 wraps is **this story's docstring**.

Per ADR-0006 the orchestrator MUST NOT retry. The only retry permitted in Phase 3 is the bounded transient-I/O retry inside `LockfileResolver` (S3-08). If you find yourself adding `for attempt in range(3): ...` in this file, you are doing Phase 5's job here and silently violating the layering. The docstring states the no-retry property explicitly so a future Phase-5 implementer can wrap without contradiction.

The orchestrator captures the engine-availability snapshot per Gap 6 **once at entry** into `RemediationAttempt.engine_availability` — every downstream consumer (selector, transform) reads from this snapshot rather than calling `RecipeEngine.available()` again. This closes the synthetic-flux race the property test in `tests/adv/test_engine_availability_snapshot.py` (S3-07) pins.

Failure preservation is the operator-debug contract: on any non-zero exit code, the worktree, partial branch, audit slice, and partial `raw/*` remain on disk under `.codegenie/remediation/<run-id>/`. The CLI safety net (S5-05) catches once at the top-level boundary and emits `meta.unexpected_exception`; the orchestrator itself never catches `Exception`.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #9 RemediationOrchestrator` — full internal design, exit-code mapping, failure-behavior contract, performance envelope.
  - `../phase-arch-design.md §"Control flow" — Happy path state diagram` — the seven exit edges (0, 4, 5, 6, 7, 8, 9; plus 10, 11 for the rare CVE-store paths).
  - `../phase-arch-design.md §"Process view — happy-path remediate run"` — the audit-event interleave sequence.
  - `../phase-arch-design.md §"Gap 6 — Engine availability check happens twice"` — snapshot captured once at entry.
  - `../phase-arch-design.md §"Data model" — RemediationAttempt + RemediationReport` — the typed shapes this function returns.
- **Phase ADRs:**
  - `../ADRs/0006-retry-deferred-to-phase-5-transient-io-exception.md` — **the** load-bearing ADR for this story; the docstring cites it verbatim.
  - `../ADRs/0001-transform-recipe-engine-two-abc-contract.md` — `Transform` contract this orchestrator consumes.
  - `../ADRs/0005-single-sandbox-profile-test-execution-overlay-signal-escalate.md` — `gate.signal_escalate` → exit 8.
  - `../ADRs/0007-lockfile-policy-scanner-graded-allow-policy-violations.md` — `--allow-policy-violations` flows through `config`.
  - `../ADRs/0013-confidence-strict-and-of-binary-signals-no-llm.md` — `TrustScore` is read from the gate, not recomputed.
- **Production ADRs:**
  - `../../../production/adrs/0011-recipe-first-rag-llm-fallback-planning.md` — Phase 4's wrap point.
  - `../../../production/adrs/0014-three-retry-default-per-gate.md` — Phase 5's wrap point; this story preserves the seam.
- **Source design:**
  - `../final-design.md §"Components" #10 RemediationOrchestrator` — six-call decomposition.
  - `../final-design.md §"Retry & escalation" #17` — retry deferred to Phase 5.
- **Existing code:**
  - `src/codegenie/transforms/context.py` (S5-02) — `load_context` is the first call.
  - `src/codegenie/transforms/cve/reader.py` (S2-07) — `CveFeedReader.get(cve_id)` is the second call.
  - `src/codegenie/recipes/selector.py` (S3-06) — `RecipeSelector.select(...) -> RecipeSelection` is the third call.
  - `src/codegenie/transforms/policy_scanner.py` (S4-01) — `LockfilePolicyScanner.scan(...) -> LockfileScanResult` is the fourth call.
  - `src/codegenie/transforms/npm_package_upgrade.py` (S5-01) — `NpmPackageUpgradeTransform` is the fifth call.
  - `src/codegenie/transforms/validation/gate.py` (S4-02/03/04/05) — `validate(transform_output, *, allow_test_network) -> GateOutcome` is the sixth call.
  - `src/codegenie/transforms/branch_writer.py` (S5-04, *parallel*) — `PatchBranchWriter.write(outcome) -> BranchHandoff` is the seventh call (the "six explicit" decomposition collapses the writer into the green path).
  - `src/codegenie/audit/writer.py` — shared `AuditWriter` instance flowed through every helper.

## Goal

Implement `src/codegenie/transforms/coordinator.py` exposing `remediate(repo_root: Path, cve_id: str, *, run_id: str, config: Config) -> RemediationReport` — a linear sync function composing the six explicit helper calls in order, capturing the engine-availability snapshot once at entry, returning a typed `RemediationReport` for every exit-code path (0/4/5/6/7/8/9), preserving worktree + partial branch + audit slice on failure, and carrying the no-retry-inside contract in a load-bearing docstring that Phase 5 will not contradict.

## Acceptance criteria

- [ ] `src/codegenie/transforms/coordinator.py` exports `remediate(repo_root: Path, cve_id: str, *, run_id: str, config: Config) -> RemediationReport`.
- [ ] The function is `def`, **not** `async def`. Calling it from an `async` context (Phase 6 LangGraph) must be possible via `asyncio.to_thread`; the function itself is synchronous.
- [ ] The function body is exactly seven function calls, in this order, with early-return on each non-green branch:
  1. `ctx = load_context(repo_root, auto_gather=config.auto_gather)` — Stale + auto_gather=False → propagates `StaleContextNotRefreshed` → CLI maps to exit 9.
  2. `engine_availability = _capture_engine_availability(config)` — Gap 6 snapshot; the orchestrator iterates the `RecipeEngineRegistry`, calls `engine.available()` once per registered engine, and stores results in a `Mapping[str, EngineAvailability]` projected onto `RemediationAttempt.engine_availability`.
  3. `advisory = resolve_advisory(cve_id, ctx, allow_stale=config.allow_stale_feeds)` — exits 10 if not in store, 11 if snapshot > 90 days without `--allow-stale-feeds`.
  4. `selection = select_recipe(ctx, advisory, skills=ctx.skills, engine_availability=engine_availability)` — `selection.reason != "matched"` → `_no_recipe_report(selection, run_id)` → exit 4.
  5. `policy = scan_lockfile(ctx, allow_violations=config.allow_policy_violations)` — `policy.violations` non-empty → `_policy_violation_report(policy, run_id)` → exit 7.
  6. `transform_output = apply_transform(ctx, advisory, selection.recipe, run_id, engine_availability)` — `transform_output.errors` → `_transform_fail_report(transform_output, run_id)` → exit 5.
  7. `gate_outcome = validate(transform_output, allow_test_network=config.allow_test_network)` — `not gate_outcome.green` and `gate_outcome.signal_escalate` → exit 8; `not gate_outcome.green` (no escalation) → exit 6.
  8. `return write_branch(transform_output, gate_outcome, run_id)` — green path, exit 0.
- [ ] **The orchestrator NEVER catches `Exception`.** Each helper either returns a typed report or raises a typed exception that the CLI's top-level safety net (S5-05) converts. The orchestrator's docstring states this verbatim.
- [ ] **No retry inside.** No `for`/`while` loops with retry semantics. The docstring states: *"Per ADR-0006, this orchestrator does not retry. The only Phase-3 retry is bounded transient-I/O retry inside LockfileResolver. Phase 5 wraps this function with three-retry gate machinery without changing this signature. Do not add retry logic here — Phase 5's wrap depends on the no-retry contract."*
- [ ] The engine-availability snapshot is **captured exactly once** at entry. The selector consumes it as a positional argument (or via a `RemediationContext` object the orchestrator builds and passes through). The transform reads it from `ApplyContext.engine_availability`. Neither component re-calls `RecipeEngine.available()` after the snapshot is built.
- [ ] Failure preservation: on every non-zero exit code, the directory `.codegenie/remediation/<run-id>/` exists with: the partial worktree (if step 5 ran), partial `raw/*` (whatever steps emitted), and the full audit slice. The CLI safety net is responsible for writing the final `remediation-report.yaml`; the orchestrator returns the `RemediationReport` shape regardless.
- [ ] The orchestrator constructs a single `AuditWriter` instance at entry and threads it through every helper call. Every Phase-3 audit event registered in S1-07 is emitted from the appropriate helper; the orchestrator itself emits two: `remediate.started` (entry, with `run_id`, `cve_id`, `repo_root`, `engine_availability`) and `remediate.completed` (exit, with `exit_code`).
- [ ] `RemediationReport.attempt.engine_availability` is populated from the snapshot.
- [ ] `tests/unit/transforms/test_coordinator.py` ships ≥ 6 tests — one per exit-code path:
  - exit 0: full happy path, green outcome, branch written.
  - exit 4: selector returns `RecipeSelection(reason="catalog_miss")`; transform never invoked; report's `attempt.transform_output is None`.
  - exit 5: transform returns `errors=["recipe_failed: ..."]`; gate never invoked.
  - exit 6: gate returns `green=False, signal_escalate=False`; branch never written.
  - exit 7: policy scanner returns violations not in `allow_violations`; transform never invoked.
  - exit 8: gate returns `green=False, signal_escalate=True`; branch never written; escalation JSON path in report.
  - exit 9: `load_context` raises `StaleContextNotRefreshed`; the orchestrator does NOT catch it — the test asserts the exception propagates (the CLI catches in S5-05).
- [ ] `tests/unit/transforms/test_coordinator_no_retry_contract.py` (≥ 2 tests) asserts the docstring contains the ADR-0006 verbatim sentence; asserts a static AST inspection of `remediate`'s body shows no `for` / `while` loop (regex over the parsed AST node types under the function — the canary for accidental retry).
- [ ] `tests/adv/test_engine_availability_snapshot.py` (lands in S3-07) is **re-asserted green** by this story's wiring: synthetic environmental flux between selector + transform must produce identical `available()` results because both read from the snapshot built here.
- [ ] The TDD plan's red test exists, is committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, `pytest` pass on touched files.

## Implementation outline

1. Write the failing tests under `tests/unit/transforms/test_coordinator.py` + `tests/unit/transforms/test_coordinator_no_retry_contract.py` (red).
2. Create `src/codegenie/transforms/coordinator.py` skeleton with the `remediate` signature, the load-bearing docstring (verbatim ADR-0006 sentence), and `raise NotImplementedError`.
3. Implement `_capture_engine_availability(config) -> Mapping[str, EngineAvailability]` — iterates `RecipeEngineRegistry.all()`, calls `engine.available()` once per engine, returns a frozen Mapping. Emits `engine.availability_snapshot_built` audit event with the snapshot's keys + values.
4. Implement the helper functions called by `remediate` — each is a small dispatcher that wraps the prior-story component:
   - `resolve_advisory(cve_id, ctx, *, allow_stale) -> CveEntry` — wraps `CveFeedReader.get` (S2-07); checks staleness via `CveFeedReader.staleness`.
   - `select_recipe(ctx, advisory, *, skills, engine_availability) -> RecipeSelection` — wraps `RecipeSelector.select` (S3-06); passes through the snapshot.
   - `scan_lockfile(ctx, *, allow_violations) -> LockfileScanResult` — wraps `LockfilePolicyScanner.scan` (S4-01).
   - `apply_transform(ctx, advisory, recipe, run_id, engine_availability) -> TransformOutput` — wraps `NpmPackageUpgradeTransform.run` (S5-01); builds `TransformInput` + `ApplyContext` carrying the snapshot.
   - `validate(transform_output, *, allow_test_network) -> GateOutcome` — wraps `validation.gate.validate` (S4-02/03/04/05).
   - `write_branch(transform_output, gate_outcome, run_id) -> RemediationReport` — wraps `PatchBranchWriter.write` (S5-04); builds the green-path report.
5. Implement the four failure-shape helpers (`_no_recipe_report`, `_policy_violation_report`, `_transform_fail_report`, `_gate_fail_report`) — each builds a `RemediationReport` with the appropriate `exit_code` and partial fields.
6. Compose the seven calls + early-returns in `remediate` body — flat sequence, no nesting beyond one `if` per branch.
7. Wire the entry/exit audit events (`remediate.started`, `remediate.completed`).
8. Write the AST-static canary test that walks `remediate`'s parsed AST and asserts no `For`/`While` nodes appear in the function body.
9. Run pytest, ruff, mypy.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/transforms/test_coordinator.py`.

```python
# Test signatures only — no implementation.

def test_happy_path_exit_0_branch_written(tmp_path, fixture_express, ncu_engine, cli_config): ...
def test_no_recipe_exit_4_selector_miss(tmp_path, fixture_unsupported_dialect, ...): ...
def test_transform_fail_exit_5_engine_non_zero(tmp_path, fixture_with_broken_recipe, ...): ...
def test_validation_fail_exit_6_install_fails(tmp_path, fixture_breaks_npm_ci, ...): ...
def test_policy_violation_exit_7_lockfile_redirect_blocked(tmp_path, fixture_policy_violation, ...): ...
def test_signal_escalate_exit_8_test_needs_network(tmp_path, fixture_test_needs_db, ...): ...
def test_stale_context_propagates_exit_9_orchestrator_does_not_catch(tmp_path, stale_fixture, no_auto_gather): ...
def test_engine_availability_snapshot_captured_once_at_entry(monkeypatch, fixture_express, ...): ...
def test_engine_availability_snapshot_threaded_into_selector_and_transform(...): ...
def test_failure_preservation_worktree_remains_on_exit_5(tmp_path, fixture_with_broken_recipe, ...): ...
def test_failure_preservation_audit_slice_remains_on_every_non_zero_exit(...): ...
def test_remediate_started_and_completed_audit_events_emitted(audit_capture, ...): ...
```

Test file path: `tests/unit/transforms/test_coordinator_no_retry_contract.py`.

```python
def test_docstring_cites_adr_0006_verbatim_no_retry_clause():
    from codegenie.transforms.coordinator import remediate
    assert "Per ADR-0006" in (remediate.__doc__ or "")
    assert "does not retry" in (remediate.__doc__ or "")

def test_remediate_body_has_no_for_or_while_loops():
    import ast, inspect
    from codegenie.transforms.coordinator import remediate
    src = inspect.getsource(remediate)
    tree = ast.parse(src)
    # walk the function body, assert no ast.For / ast.While nodes appear
    ...

def test_remediate_body_has_no_bare_except_exception():
    # AST walk for ast.ExceptHandler with type=None or type matching "Exception"
    ...
```

Run pytest; confirm failures. Commit as red marker.

### Green — make it pass

Implement `remediate` per the implementation outline. The body should read like the pseudocode in `phase-arch-design.md §"Component design" #9` — flat, eight steps (engine-availability snapshot insertion makes it eight; the spec calls "six explicit" because step 2 is scaffolding), each step has at most one `if` for the failure branch. Resist the urge to extract a generic "phase runner" that loops over steps — the explicit decomposition is the contract.

The engine-availability snapshot is the one new mechanism this story introduces beyond glue code: build it once after `load_context`, before `resolve_advisory`. The selector + transform consume it from the same frozen Mapping.

### Refactor — clean up

- Hoist `_EXIT_CODES: Final[Mapping[str, int]] = MappingProxyType({"success": 0, "no_recipe": 4, ...})` so the magic numbers appear once. Tests reference the named constants.
- Extract `_build_remediation_attempt(run_id, repo_root, cve_id, engine_availability) -> RemediationAttempt` — small builder; reduces nine constructor-call sites to one.
- Module docstring naming ADR-0006, Gap 6, and a one-paragraph summary of the six-call backbone + the "this is the Phase 5 wrap point" claim.
- Confirm the `RemediationReport.audit_path` field is set to the same path the writer (S5-04) records — they MUST agree, since downstream consumers (Phase 4 RAG retrieval) follow the path from the report.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/transforms/coordinator.py` | New — `remediate` + helper dispatchers + failure-shape builders |
| `src/codegenie/transforms/_exit_codes.py` | New — `_EXIT_CODES` constant + helpers; small, central |
| `src/codegenie/transforms/__init__.py` | Append re-export for `remediate` |
| `tests/unit/transforms/test_coordinator.py` | New — ≥ 6 exit-code tests + snapshot tests |
| `tests/unit/transforms/test_coordinator_no_retry_contract.py` | New — AST canary against retry/exception drift |
| `tests/unit/transforms/fixtures/coordinator/` | New — minimal fixture set covering each exit-code path |

## Out of scope

- **CLI exit-code mapping** — handled by S5-05. This story returns `RemediationReport.attempt.exit_code` as the typed integer; the CLI's `sys.exit()` call lives there.
- **`PatchBranchWriter` internals** — handled by S5-04. This story invokes `write_branch(...)` and trusts the writer's contract; the writer's git-flag enforcement, dirty-tree refusal, and existing-branch refusal are S5-04's job.
- **Phase-5 three-retry wrap** — explicitly out of scope and explicitly documented as the wrap point. The docstring's "Phase 5 wraps" clause is the load-bearing handoff.
- **Phase-6 LangGraph state ledger** — `RemediationAttempt` is the typed state seed; Phase 6 will wrap with `interrupt()` + SQLite checkpointer. This story produces the seed; the wrap is Phase 6.
- **Phase-9 Temporal Activity envelope** — `RemediationReport` is the typed Activity output; Phase 9 wraps without modifying this signature.
- **`auto_gather` recursion mechanism** — handled by S5-02. This orchestrator just lets `StaleContextNotRefreshed` propagate.
- **`signal_escalate` JSON on disk** — the operator-facing escalation JSON is written by S4-05; the orchestrator surfaces the path through `RemediationReport.attempt.gate_outcome.signals["escalation_json_path"]`. The CLI banner (S5-05) reads it.
- **`evidence_stale` retraction marking** — handled by S2-08 from inside `codegenie cve sync`, not from `remediate`.

## Notes for the implementer

- **The docstring is load-bearing.** It states the no-retry contract in a single sentence that Phase 5 will reference. If a future contributor (or AI agent) "improves" the docstring by paraphrasing, the canary test `test_docstring_cites_adr_0006_verbatim_no_retry_clause` fires. The verbatim string is the cheap canary; keep it.
- **The AST canary is the cheap version of "no retry inside."** A `for ... range(3)` inside `remediate` would silently violate ADR-0006 — and human review of a 60-line function body misses it 1 in 5 times. The AST walk in `test_remediate_body_has_no_for_or_while_loops` fires before review. Keep the test cheap (parse only `remediate`'s source, not the whole module) so the unit-test suite stays fast.
- **No `try: ... except Exception:` in this file.** Two `except` clauses are permitted: (a) typed exceptions from helpers that the orchestrator converts to a failure-shape `RemediationReport`, and (b) none — actually, even option (a) is wrong. Each helper returns the typed report directly; `remediate` calls + early-returns. No `try` blocks at all. The CLI safety net (S5-05) is the one place a bare-`except` is permitted in Phase 3 — and even there it logs + audits + re-raises.
- **Engine-availability snapshot is built BEFORE `resolve_advisory`** so that if the CVE isn't in the store (exit 10), the snapshot is still in the report (operator can see "we couldn't even start because the engine matrix was X"). This is an instrumentation choice — but it also means the snapshot is in every report regardless of exit path, which Phase 4 RAG can index uniformly.
- **The seven calls map to the seven stages in the production design's pipeline (Discovery → Assessment → Deep Scan → Planning → Execution → Validation → Handoff).** Phase 3 collapses Discovery + Assessment into `load_context + resolve_advisory`; the Deep Scan is implicit (the CVE store is already populated); Planning is `select_recipe`; Execution is `apply_transform`; Validation is `validate`; Handoff is `write_branch`. Keep the names; Phase 4+ extensions will recognize the seven-stage shape.
- **Per Rule 3 (Surgical Changes):** the helpers are thin dispatchers that build inputs from the prior step's outputs and call the prior-story component. Do NOT inline logic from S5-01 (transform), S5-02 (context), S4-01 (policy scanner), etc. — those stories own their components. If a helper grows past ~20 lines, you're recreating logic that belongs elsewhere.
- **`Config` is the single boundary object** carrying `auto_gather`, `allow_stale_feeds`, `allow_policy_violations`, `allow_test_network`, `engine` (cli `--engine` choice), `strict`. Define it as a frozen Pydantic model in this file (or in `transforms/config.py` if it grows). The CLI (S5-05) constructs it from flags; the orchestrator only reads.
- **Per Rule 12 (Fail loud):** every helper that emits an audit event MUST emit before returning. A silent emit-then-die path masks the "what step actually failed?" debug question. The integration test `test_failure_preservation_audit_slice_remains_on_every_non_zero_exit` asserts the last event in the audit slice corresponds to the helper that emitted the failure — not the `remediate.completed` event.
- **`asyncio.to_thread` compatibility:** the function is `def`, not `async def`. Phase 6's LangGraph state machine will call it via `await asyncio.to_thread(remediate, ...)`. This means nothing inside the function can block the GIL forever (an unbounded `subprocess.run` does; the `exec.run_in_sandbox` wrappers have wall-clock budgets — confirm the budgets are set in prior stories). Phase 6 cannot make a sync function async; if you find yourself adding `async def`, you're doing Phase 6's job.
