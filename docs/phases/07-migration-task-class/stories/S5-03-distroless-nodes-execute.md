# Story S5-03 — Distroless graph nodes — execute half

**Step:** Step 5 — `DistrolessLedger`, `build_distroless_loop()`, `cli/migrate.py`, and Node.js Express E2E
**Status:** Ready
**Effort:** M
**Depends on:** S5-02
**ADRs honored:** ADR-P7-001 (parallel ledger), ADR-P7-005 (no shared dispatcher; Phase 6 HITL contracts imported verbatim), Phase 6 ADR-0007 (await_human runs at gate decision; reused verbatim)

## Context

This story ships the **execute half** of the distroless loop: `apply_recipe`, `validate_in_sandbox`, `record_attempt`, `emit_artifact`. The two remaining nodes (`await_human`, `escalate`) are **imported verbatim from Phase 6** — they operate on the `DistrolessLedger`'s `human_request`/`human_decision` fields identically to how they operate on `VulnLedger`'s, because the HITL contract (`docs/contracts/hitl-v0.6.0.json`) is unchanged. This is the load-bearing reuse claim of `phase-arch-design.md §Component 7` and `final-design.md §Acknowledged debt Phase 8 inherits`.

`apply_recipe` invokes Phase 3's recipe engine path — specifically `DockerfileRecipeEngine` for `engine="dockerfile"` recipes (S4-01) — and the new `DockerfileBaseImageSwapTransform` (S4-03). `validate_in_sandbox` is a single-attempt wrapper around Phase 5's `GateRunner.run_one(transition=stage6_validate_distroless, ctx)` (the multi-attempt loop is unrolled into the LangGraph cycle per Phase 6 §Component-5). `record_attempt` is Phase 5's `RetryLedger.record` invocation. `emit_artifact` writes `migration-report.yaml` + the patch + raw artifacts to `.codegenie/migration/<run-id>/`.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component 7 — build_distroless_loop()` (lines 682–711) — node list, especially nodes 6 (apply_recipe), 7 (validate_in_sandbox), 8 (record_attempt), 9 (await_human verbatim from Phase 6), 10 (emit_artifact), 11 (escalate verbatim from Phase 6).
  - `../phase-arch-design.md §Control flow — Happy path` steps 7–13 — sequence and side effects.
  - `../phase-arch-design.md §Process view` (lines 207–245) — fsync/checkpoint discipline.
  - `../phase-arch-design.md §Component 11 — Regression-suite wall-clock canary` — `emit_artifact` writes `migration-report.yaml`, the canonical persistence shape.
  - `../phase-arch-design.md §Edge cases #5` (strace budget exhaust → `confidence=medium` → retry), `#7` (`RegistryAuthFailed` from buildkit), `#15` (`python -O` strips `@pure_edge` assertions — `await_human` boundary).
- **Phase ADRs:**
  - `../ADRs/0011-distroless-ledger-parallel-to-vuln-ledger.md` — ADR-P7-001 — fields the execute nodes read/write.
  - `../ADRs/0012-parallel-cli-verbs-no-shared-dispatcher.md` — ADR-P7-005 — `await_human` and `escalate` reuse from Phase 6 verbatim.
- **Source design:**
  - `../final-design.md §Component-7` — list of nodes; `await_human` and `escalate` explicitly named as imported, not reimplemented.
- **Existing code:**
  - `src/codegenie/graph/nodes/await_human.py` (Phase 6 S6-x) — the verbatim-imported node.
  - `src/codegenie/graph/nodes/escalate.py` (Phase 6) — the verbatim-imported node.
  - `src/codegenie/graph/nodes/apply_recipe.py` (Phase 6) — invocation pattern; this story's distroless variant dispatches on `recipe.engine == "dockerfile"`.
  - `src/codegenie/graph/nodes/validate_in_sandbox.py` (Phase 6) — `GateRunner.run_one` pattern.
  - `src/codegenie/graph/nodes/record_attempt.py` (Phase 6) — `RetryLedger.record` pattern.
  - `src/codegenie/transforms/dockerfile_base_image_swap.py` (S4-03) — the transform `apply_recipe` invokes.
  - `src/codegenie/recipes/engines/dockerfile_engine.py` (S4-01) — the engine the transform uses.
  - `src/codegenie/gates/retry_ledger.py` (Phase 5) — `RetryLedger.record(Attempt(...))` invocation.

## Goal

Land four new node modules — `apply_recipe.py`, `validate_in_sandbox.py`, `record_attempt.py`, `emit_artifact.py` — under `src/codegenie/graph/nodes/distroless/`, each a pure function on `DistrolessLedger`; and re-export `await_human` and `escalate` from Phase 6 **verbatim** (no new node bodies, no shadowing).

## Acceptance criteria

- [ ] Four new files: `apply_recipe.py`, `validate_in_sandbox.py`, `record_attempt.py`, `emit_artifact.py` under `src/codegenie/graph/nodes/distroless/` — each exporting a single `(state: DistrolessLedger) -> DistrolessLedger` function.
- [ ] `apply_recipe` invokes `DockerfileBaseImageSwapTransform.apply(state.recipe_selection.recipe, repo_ctx, worktree)` when `state.recipe_selection.recipe.engine == "dockerfile"`; routes to the Phase 3 default engine otherwise. Sets `state.patch=PatchRef(...)`, `state.last_engine="dockerfile_recipe"` on success.
- [ ] `validate_in_sandbox` invokes `GateRunner.run_one(transition=stage6_validate_distroless, ctx=GateContext(worktree, advisory, recipe_selection, prior_attempts))` and writes `state.last_outcome=GateOutcome(...)`, `state.current_gate_id="stage6_validate_distroless"`. **Single attempt** — no internal retry; multi-attempt is the LangGraph cycle's job per Phase 6 §Component-5.
- [ ] `record_attempt` invokes `RetryLedger.record(Attempt(...))`; updates `state.prior_attempts` via `model_copy(update={"prior_attempts": [*state.prior_attempts, summary]})` (no in-place append); extends `state.chain_head`; resets `retry_count` when `current_gate_id` changed.
- [ ] `emit_artifact` writes:
  - `.codegenie/migration/<run-id>/migration-report.yaml` (canonical YAML via `MigrationReport.model_dump`)
  - `.codegenie/migration/<run-id>/diff/<recipe-id>.patch` (the recipe-applied patch)
  - `.codegenie/migration/<run-id>/raw/{build.log,dive.json,scenarios/*.trace.log}` (from `state.last_outcome` artifact refs)
  - and creates git branch `codegenie/distroless/<short-sha>` (delegating to `DockerfileBaseImageSwapTransform`).
- [ ] `src/codegenie/graph/nodes/distroless/__init__.py` re-exports `await_human` and `escalate` directly from `codegenie.graph.nodes.await_human` and `codegenie.graph.nodes.escalate` — **verbatim imports**, no wrapper, no shadowing.
- [ ] A test asserts `codegenie.graph.nodes.distroless.await_human is codegenie.graph.nodes.await_human.await_human` — identity check, not equality. (Per ADR-P7-005 / final-design §Component-7 "imported verbatim".)
- [ ] Every node body is a pure function: `state.model_copy(update={...})`; the Phase 6 mutation hook fires on regressions.
- [ ] Per-node unit tests cover happy path, failure path, and the engine-routing case for `apply_recipe`.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict src/codegenie/graph/nodes/distroless/`, and the per-node test files all pass.

## Implementation outline

1. `apply_recipe.py`: branch on `recipe.engine`; if `"dockerfile"`, call `DockerfileBaseImageSwapTransform.apply(...)`; on Phase 3 default, delegate to the Phase 6 dispatch. Catch `RoundTripFailure`, `DockerfileRejected`, `WorktreeContaminated` — these raise loudly (no silent miss). Cite arch §Component 5 (transform) for the contract.
2. `validate_in_sandbox.py`: construct `GateContext` from state; call `GateRunner.run_one(stage6_validate_distroless, ctx)`; write `state.last_outcome` + `current_gate_id`. **No retry loop.** Cite Phase 6 §Component-5.
3. `record_attempt.py`: build `Attempt(...)` per Phase 5 contract; call `RetryLedger.record`; update `state.prior_attempts` immutably; extend `state.chain_head` via Phase 5's `head_extend(...)`.
4. `emit_artifact.py`: build `MigrationReport(...)` from state; write four artifact paths under `.codegenie/migration/<run-id>/`; create git branch via the transform's helper; emit `GraphEvent(kind="exit", ...)`. The `<run-id>` is read from state (set by `cli/migrate.py` in S5-05).
5. `__init__.py`: `from codegenie.graph.nodes.await_human import await_human` and `from codegenie.graph.nodes.escalate import escalate`, re-exported via `__all__`. No body.
6. Tests written failing first, in order: identity check for verbatim imports → engine-routing for `apply_recipe` → single-attempt for `validate_in_sandbox` → `prior_attempts` immutability for `record_attempt` → file-system shape for `emit_artifact`.

## TDD plan — red / green / refactor

### Red — write the failing tests first

Test files under `tests/graph/nodes/distroless/`.

```python
# test_imports_verbatim.py
def test_await_human_is_phase6_object() -> None:
    """ADR-P7-005 — await_human is imported verbatim, not re-implemented."""
    from codegenie.graph.nodes.distroless import await_human as distroless_ah
    from codegenie.graph.nodes.await_human import await_human as phase6_ah
    assert distroless_ah is phase6_ah


def test_escalate_is_phase6_object() -> None:
    from codegenie.graph.nodes.distroless import escalate as distroless_es
    from codegenie.graph.nodes.escalate import escalate as phase6_es
    assert distroless_es is phase6_es
```

```python
# test_apply_recipe.py
def test_apply_recipe_routes_dockerfile_engine_to_transform() -> None:
    state = _make_state(recipe_engine="dockerfile")
    spy = _spy_dockerfile_transform()
    with _patched_transform(spy):
        new_state = apply_recipe(state)
    assert spy.call_count == 1
    assert new_state.last_engine == "dockerfile_recipe"
    assert new_state.patch is not None


def test_apply_recipe_raises_on_round_trip_failure() -> None:
    """Per arch §Edge cases #2 — RoundTripFailure raises loud, not silent miss."""
    state = _make_state(dockerfile_that_breaks_round_trip=True)
    with pytest.raises(RoundTripFailure):
        apply_recipe(state)
```

```python
# test_validate_in_sandbox.py
def test_validate_in_sandbox_single_attempt_no_internal_retry() -> None:
    """Phase 6 §Component-5 — retry loop is the LangGraph cycle's job."""
    spy = _spy_gate_runner()
    state = _make_state(retry_count=2)
    with _patched_gate_runner(spy):
        validate_in_sandbox(state)
    assert spy.run_one_call_count == 1  # exactly one, regardless of retry_count


def test_validate_in_sandbox_writes_last_outcome_and_gate_id() -> None:
    state = _make_state()
    new_state = validate_in_sandbox(state)
    assert new_state.current_gate_id == "stage6_validate_distroless"
    assert new_state.last_outcome is not None
```

```python
# test_record_attempt.py
def test_record_attempt_appends_immutably_no_in_place_mutation() -> None:
    state = _make_state(prior_attempts=[_existing_attempt()])
    pre_id = id(state.prior_attempts)
    new_state = record_attempt(state)
    assert id(new_state.prior_attempts) != pre_id  # new list object
    assert len(new_state.prior_attempts) == 2


def test_record_attempt_resets_retry_count_on_gate_id_change() -> None:
    state = _make_state(current_gate_id="stage5_something_else", retry_count=2)
    new_state = record_attempt(state)
    assert new_state.retry_count == 0  # reset, because gate changed
```

```python
# test_emit_artifact.py
def test_emit_artifact_writes_migration_report_yaml(tmp_path: Path) -> None:
    state = _make_state(run_id="abc123", repo_path=tmp_path)
    emit_artifact(state)
    report_path = tmp_path / ".codegenie/migration/abc123/migration-report.yaml"
    assert report_path.exists()
    report = yaml.safe_load(report_path.read_text())
    assert report["schema_version"] == "v0.7.0"


def test_emit_artifact_writes_patch_and_raw_artifacts(tmp_path: Path) -> None:
    state = _make_state(run_id="abc123", repo_path=tmp_path, patch=_make_patch_ref(),
                         last_outcome=_make_outcome_with_artifacts())
    emit_artifact(state)
    assert (tmp_path / ".codegenie/migration/abc123/diff").exists()
    assert (tmp_path / ".codegenie/migration/abc123/raw/build.log").exists()
```

Run each; confirm all fail. Commit.

### Green — make it pass

Author the four node bodies as short pure functions; write `__init__.py` with the two verbatim re-exports.

### Refactor — clean up

- Add module docstrings citing arch §Component 7 step numbers and Phase 5/6 contract sources.
- Per cross-cutting: no `random`, no `time` imports.
- Per arch §Edge cases #15 (`python -O`): `await_human` is the boundary that fires `interrupt_before`; the verbatim import is the right tool — do not wrap in custom logic.
- Per arch §Edge cases #7: `apply_recipe` does *not* catch `RegistryAuthFailed` (that's `validate_in_sandbox`'s domain, where `tools/buildkit.py` parses stderr).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/graph/nodes/distroless/apply_recipe.py` | NEW node — dispatches `engine="dockerfile"` to transform. |
| `src/codegenie/graph/nodes/distroless/validate_in_sandbox.py` | NEW node — `GateRunner.run_one` single-attempt wrapper. |
| `src/codegenie/graph/nodes/distroless/record_attempt.py` | NEW node — `RetryLedger.record` + immutable list append. |
| `src/codegenie/graph/nodes/distroless/emit_artifact.py` | NEW node — writes report + patch + raw artifacts; creates branch. |
| `src/codegenie/graph/nodes/distroless/__init__.py` | UPDATE — re-export `await_human` and `escalate` verbatim from Phase 6. |
| `tests/graph/nodes/distroless/test_*.py` | Per-node unit tests + the verbatim-imports identity test. |

## Out of scope

- **`ingest_target`, `resolve_target_image`, `select_recipe`, `rag_lookup`, `replan_with_phase4`** — handled by S5-02.
- **Factory + topology + edges** — handled by S5-04.
- **HITL `await_human` / `escalate` *bodies*** — owned by Phase 6 (re-exported, never modified).
- **Phase 5 `stage6_validate_distroless` transition definition** — owned by Phase 5 / S3-02 wiring; this story consumes the transition name.
- **`MigrationReport` model** — defined in S5-01; this story consumes it.
- **`DockerfileBaseImageSwapTransform`** — defined in S4-03; this story consumes it.
- **CLI orchestration** — S5-05.

## Notes for the implementer

- **`await_human` and `escalate` are imported verbatim** (final-design.md §Acknowledged debt; ADR-P7-005). Do *not* wrap with `functools.wraps`; do *not* shadow with a re-named function. The identity check (`distroless.await_human is await_human.await_human`) is load-bearing — Phase 8 will trust that these are the same object.
- **`validate_in_sandbox` is single-attempt** (Phase 6 §Component-5). If you add retry logic here, you've duplicated the LangGraph cycle and the gate's three-retry counter (Phase 5) will fire twice. The LangGraph edge `route_after_attempt` (Phase 6, reused) routes back to `replan_with_phase4` on retry.
- **`record_attempt` immutability** — `state.prior_attempts.append(...)` triggers the Phase 6 in-place mutation hook (S5-01 honors). Always use `state.model_copy(update={"prior_attempts": [*state.prior_attempts, summary]})`.
- **`emit_artifact` writes to `.codegenie/migration/<run-id>/`** — note this directory is *different* from Phase 6's `.codegenie/remediation/<run-id>/`, per `phase-arch-design.md §Gap 1`. Cross-task chain-no-collision is structurally guaranteed by the directory split (S5-07 verifies).
- **The `<run-id>` field is not on `DistrolessLedger` directly** in arch §Component 6 — it's derived from `workflow_id` or set on the ledger by `cli/migrate.py` (S5-05). If the field is missing on the model, surface it now via Open Implementation Questions: either add `run_id: str` to `DistrolessLedger` (back-edit S5-01 *before* it lands) or pass it through `state.workflow_id` semantics. Pre-write the rationale either way.
- **`apply_recipe` raises on `RoundTripFailure` / `DockerfileRejected` / `WorktreeContaminated`** — these are *recipe miss equivalents* per arch §Edge cases #1/#2. The edge `route_after_attempt` then routes to `rag_lookup`. Per CLAUDE.md Rule 12, do not coerce these to silent failure.
- **Per arch §Harness engineering, the per-node `GraphEvent` emit is mandatory.** Reuse the Phase 6 `emit_event(state, kind, node, payload)` helper. Audit events flow to `.codegenie/migration/<run-id>/audit/`.
- **Per cross-cutting concern, mypy --strict must be clean.** The `RetryLedger.record(Attempt(...))` call requires that `Attempt` is built from typed fields, not `dict[str, Any]`.
