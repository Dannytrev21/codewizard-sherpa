# Story S5-02 — Distroless graph nodes — gather half

**Step:** Step 5 — `DistrolessLedger`, `build_distroless_loop()`, `cli/migrate.py`, and Node.js Express E2E
**Status:** Ready
**Effort:** M
**Depends on:** S5-01
**ADRs honored:** ADR-P7-001 (parallel ledger), ADR-P7-003 / ADR-P7-004 (`FallbackTier.run(task_type="distroless_migration")`), ADR-P7-007 (`Recipe.engine="dockerfile"` consumption in `select_recipe`)

## Context

The distroless loop has 11 nodes (one more than the vuln loop — `resolve_target_image`). This story ships the **gather half**: the five nodes that prepare the workflow for execution by pinning the advisory, resolving the target image, selecting a recipe, looking up RAG examples, and (on miss) replanning via Phase 4. The execute half (apply, validate, record, emit, await, escalate) is owned by S5-03; the factory wiring is S5-04. These five nodes are *pure functions on `DistrolessLedger`* — they consume Phase 2/3/4 services as types and return `state.model_copy(update={...})`.

Two non-trivial constraints are baked in: (a) `resolve_target_image` enforces the Chainguard image-name allowlist regex at the *node boundary* — closing edge case #3 (typosquat / poisoned YAML); (b) `replan_with_phase4` *must* pass `task_type="distroless_migration"` per ADR-P7-003, because the default branch (vuln path) would return a vuln-shaped patch that fails the gate consistently.

Every node body emits one `GraphEvent` on entry, one on exit, and one `"decision"` event when it routes; per the Phase 6 harness contract.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component 7 — build_distroless_loop()` (lines 682–711) — the 11-node list, especially nodes 1–5 (gather half).
  - `../phase-arch-design.md §Control flow — Happy path` (lines 1115–1131) — step 3 (`resolve_target_image` mmap + allowlist), step 6 (`select_recipe` reuses Phase 3 `RecipeMatcher` extended to match `engine="dockerfile"`).
  - `../phase-arch-design.md §Scenarios — Scenario 2 "Recipe miss → RAG miss → Phase 4 LLM fallback (task_type-routed)"` (lines 409–437) — exact `FallbackTier.run` invocation shape.
  - `../phase-arch-design.md §Edge cases #3` (typosquat regex), `#4` (multi-arch `--platform=linux/amd64`), `#10` (`parser_skipped_lines > 0` → recipe miss).
  - `../phase-arch-design.md §Component 9 — base_catalog.json hot view` (lines 748–781) — what `resolve_target_image` reads.
- **Phase ADRs:**
  - `../ADRs/0004-fallback-tier-task-type-kwarg.md` — ADR-P7-003 — `task_type="distroless_migration"` is mandatory at `replan_with_phase4`'s call site.
  - `../ADRs/0011-distroless-ledger-parallel-to-vuln-ledger.md` — ADR-P7-001 — image-name allowlist regex is the *one* place a typosquat is rejected (also reused by S6-09 adversarial tests).
- **Source design:**
  - `../final-design.md §Synthesis ledger row 10` — Phase 4 task-class routing via `task_type` kwarg.
- **Existing code:**
  - `src/codegenie/graph/nodes/select_recipe.py` (Phase 6) — Phase 3 `RecipeMatcher` invocation pattern; mirror but match by `engine="dockerfile"`.
  - `src/codegenie/graph/nodes/rag_lookup.py` (Phase 6) — Phase 4 `RagTier.lookup` invocation; collection routes via `task_type`.
  - `src/codegenie/graph/nodes/replan_with_phase4.py` (Phase 6) — vuln callsite; this story's distroless variant passes the new kwarg.
  - `src/codegenie/catalogs/distroless/` (S2-06) — `read_base_catalog()` reader for `resolve_target_image`.
  - `src/codegenie/planner/fallback_tier.py` (S1-04) — `FallbackTier.run(..., task_type=...)` signature, post-seam.

## Goal

Land five new node modules under `src/codegenie/graph/nodes/distroless/` (`ingest_target.py`, `resolve_target_image.py`, `select_recipe.py`, `rag_lookup.py`, `replan_with_phase4.py`) — each a pure function `state: DistrolessLedger -> DistrolessLedger` that emits `GraphEvent`s, honors the image-name allowlist regex, and passes `task_type="distroless_migration"` through to Phase 4.

## Acceptance criteria

- [ ] Five new files exist under `src/codegenie/graph/nodes/distroless/`: `ingest_target.py`, `resolve_target_image.py`, `select_recipe.py`, `rag_lookup.py`, `replan_with_phase4.py` — each exporting one node function with `(state: DistrolessLedger) -> DistrolessLedger` signature.
- [ ] `resolve_target_image` mmap-reads `.codegenie/cache/base_catalog.json` via `read_base_catalog()` (S2-06) and produces a `TargetImageRecommendation`; on miss, sets `target_image_recommendation=None` and lets the edge `route_after_resolve_target` route to `catalog_miss`.
- [ ] `resolve_target_image` enforces the regex `^cgr\.dev/chainguard/[a-z0-9-]+(@sha256:[a-f0-9]{64}|:[a-z0-9._-]+)$` against the resolved `to_image`; non-matching values raise `TargetImageRejected` (loud), not silently routed to miss. (Edge case #3.)
- [ ] `select_recipe` invokes Phase 3 `RecipeMatcher` with `engine="dockerfile"` constraint; matches `swap_base_image_single_stage.yaml` for single-stage Dockerfiles and `multi_stage_distroless_refactor.yaml` for multi-stage. `RecipeSelection.matched=False` with `reason="unsupported_dialect"` on miss (reused Phase 3 literal value — see arch §Decision points).
- [ ] `rag_lookup` invokes Phase 4 `RagTier.lookup` with collection `distroless_solved_examples_promoted` (per ADR-P7-003 routing); below `score=0.85` → `RagHit.miss=True`.
- [ ] `replan_with_phase4` invokes `FallbackTier.run(advisory, repo_ctx, recipe_selection, *, run_id=..., include_pending=False, auto_promote=False, prior_attempts=state.prior_attempts, task_type="distroless_migration")`. **The `task_type` kwarg is mandatory** — a static-analysis test or lint assertion confirms the literal `"distroless_migration"` appears in the source.
- [ ] Each node emits `GraphEvent(kind="enter", node=<name>)` on entry and `GraphEvent(kind="exit", ...)` on exit; routing decisions emit `kind="decision"`.
- [ ] Each node is a pure function: `state.model_copy(update={...})` not `state.field = ...`; no in-place mutation (the Phase 6 hook fires on regressions).
- [ ] Unit tests per node — `tests/graph/nodes/distroless/test_<node>.py` — covering happy path, miss path, and the regex-rejection path for `resolve_target_image`.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict src/codegenie/graph/nodes/distroless/`, and the per-node test files all pass.

## Implementation outline

1. Create the `src/codegenie/graph/nodes/distroless/` package with an empty `__init__.py`.
2. `ingest_target.py`: pins the `advisory_canonical_id` (from `--cve` flag, or `None`) and `dockerfile_path` (validated to exist) onto the state. Returns `state.model_copy(update={...})`.
3. `resolve_target_image.py`: calls `read_base_catalog(Path(".codegenie/cache/base_catalog.json"))`; matches `state.target_image_recommendation.from_image` against the catalog rows; on hit, applies the allowlist regex; raises `TargetImageRejected` on regex failure or returns the populated `TargetImageRecommendation`. On catalog miss, returns state with `target_image_recommendation=None`.
4. `select_recipe.py`: calls Phase 3 `RecipeMatcher(catalog_path, engine="dockerfile")` and selects per the `DockerfileInventory.is_multistage` signal.
5. `rag_lookup.py`: calls `RagTier.lookup(query, collection="distroless_solved_examples_promoted")`; below threshold → `RagHit(matched=False, score=...)`.
6. `replan_with_phase4.py`: passes `task_type="distroless_migration"` to `FallbackTier.run`; updates `state.patch`, `state.last_engine="phase4_llm"`, `state.prior_attempts`.
7. Per node, write the failing tests first — extra emphasis on the regex-rejection test for `resolve_target_image` and the literal-`task_type` assertion for `replan_with_phase4`.

## TDD plan — red / green / refactor

### Red — write the failing tests first

Test files: `tests/graph/nodes/distroless/test_ingest_target.py`, `test_resolve_target_image.py`, `test_select_recipe.py`, `test_rag_lookup.py`, `test_replan_with_phase4.py`.

```python
# tests/graph/nodes/distroless/test_resolve_target_image.py
def test_resolve_target_image_rejects_typosquat_loudly() -> None:
    """Edge case #3 — chamguard (typo) must raise, not silently route to miss."""
    catalog = {"rows": {"node:20-bullseye": {"to_image": "cgr.dev/chamguard/node:20-distroless", ...}}}
    with _patched_catalog(catalog):
        state = _make_state(from_image="node:20-bullseye")
        with pytest.raises(TargetImageRejected) as exc:
            resolve_target_image(state)
        assert "chamguard" in str(exc.value) or "allowlist" in str(exc.value)


def test_resolve_target_image_happy_path_populates_recommendation() -> None:
    state = _make_state(from_image="node:20-bullseye")
    new_state = resolve_target_image(state)
    assert new_state.target_image_recommendation is not None
    assert new_state.target_image_recommendation.to_image.startswith("cgr.dev/chainguard/")
    assert new_state.target_image_recommendation.pinned_digest.startswith("sha256:")


def test_resolve_target_image_catalog_miss_returns_none() -> None:
    state = _make_state(from_image="some-unknown-base:latest")
    new_state = resolve_target_image(state)
    assert new_state.target_image_recommendation is None
```

```python
# tests/graph/nodes/distroless/test_replan_with_phase4.py
def test_replan_with_phase4_passes_task_type_distroless_migration() -> None:
    """ADR-P7-003 — task_type must be the literal 'distroless_migration'."""
    state = _make_state(prior_attempts=[])
    fake_tier = _spy_fallback_tier()
    with _patched_fallback_tier(fake_tier):
        replan_with_phase4(state)
    assert fake_tier.last_call_kwargs["task_type"] == "distroless_migration"


def test_source_contains_literal_task_type_distroless_migration() -> None:
    """Static guard — ADR-P7-003 demands the literal appears in source."""
    src = (REPO_ROOT / "src/codegenie/graph/nodes/distroless/replan_with_phase4.py").read_text()
    assert '"distroless_migration"' in src
```

```python
# tests/graph/nodes/distroless/test_select_recipe.py
def test_select_recipe_matches_dockerfile_engine_for_single_stage() -> None:
    state = _make_state(dockerfile=_SINGLE_STAGE_DOCKERFILE)
    new_state = select_recipe(state)
    assert new_state.recipe_selection.matched
    assert new_state.recipe_selection.recipe_id == "swap_base_image_single_stage"


def test_select_recipe_miss_reason_unsupported_dialect() -> None:
    """Phase 3 RecipeSelection.reason 'unsupported_dialect' is reused (no new Literal value)."""
    state = _make_state(dockerfile=_UNKNOWN_DIALECT)
    new_state = select_recipe(state)
    assert not new_state.recipe_selection.matched
    assert new_state.recipe_selection.reason == "unsupported_dialect"
```

Run each; confirm all fail. Commit the red tests.

### Green — make it pass

Author each node as a short pure function. Use `state.model_copy(update=...)` exclusively. Emit `GraphEvent`s via the Phase 6 helper (assume `from codegenie.graph.events import emit_event` exists from Phase 6 S1-04).

### Refactor — clean up

- Add module docstrings linking each node to arch §Component 7's pseudo-code.
- Per cross-cutting concern: no `random` / no `time` imports — fence-CI under `graph/` enforces.
- Per arch §Edge cases #4, the multi-arch `--platform=linux/amd64` constraint applies to `imagetools inspect` calls *inside* `tools/buildkit.py` (S2-02); this story consumes the cached digest only, not the live lookup.
- Per arch §Edge cases #12, when `target_image_recommendation.catalog_row_age_h > 2160` (90 d), `confidence_band` should already be `"medium"` at catalog-render time (S2-06); `resolve_target_image` passes it through unchanged.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/graph/nodes/distroless/__init__.py` | NEW package init. |
| `src/codegenie/graph/nodes/distroless/ingest_target.py` | NEW node — pins advisory + dockerfile path. |
| `src/codegenie/graph/nodes/distroless/resolve_target_image.py` | NEW node — catalog lookup + regex enforcement (Edge case #3). |
| `src/codegenie/graph/nodes/distroless/select_recipe.py` | NEW node — Phase 3 RecipeMatcher with `engine="dockerfile"`. |
| `src/codegenie/graph/nodes/distroless/rag_lookup.py` | NEW node — distroless RAG collection lookup. |
| `src/codegenie/graph/nodes/distroless/replan_with_phase4.py` | NEW node — `FallbackTier.run(task_type="distroless_migration")`. |
| `tests/graph/nodes/distroless/test_*.py` | Per-node unit tests (5 files). |

## Out of scope

- **`apply_recipe`, `validate_in_sandbox`, `record_attempt`, `emit_artifact`, `await_human`, `escalate`** — handled by S5-03.
- **Factory + topology wiring** — handled by S5-04.
- **`route_after_resolve_target` edge predicate** — handled by S5-04 (factory owns edge wiring); this story produces the state shape the predicate reads.
- **CLI surface** — handled by S5-05.
- **End-to-end Express test** — handled by S5-06.
- **Phase 4 `FallbackTier.run` task_type kwarg implementation** — already landed in S1-04 (ADR-P7-003 seam); this story consumes it.

## Notes for the implementer

- **Per `phase-arch-design.md §Gap 6`, prompt-bleed across task types is the failure mode that motivates ADR-P7-003.** If you find yourself tempted to *not* pass `task_type`, you'll produce a vuln-shaped patch and the gate will fail consistently. Make the literal `"distroless_migration"` impossible to forget by writing the literal-in-source guard test first.
- **The image-name allowlist regex is the single security chokepoint** (Edge case #3). Per ADR-P7-001 it applies *both* to catalog hits and to anything the LLM produces in `replan_with_phase4`. This story enforces at the catalog boundary; S5-03's `apply_recipe` re-asserts on the patch's `to_image`.
- **`select_recipe.reason="unsupported_dialect"` is a semantic stretch** for image-dialect mismatch (arch §Tradeoffs row "RecipeSelection.reason not extended"). Per ADR-P7-001 / final-design.md §Conflict row 9, Phase 7 deliberately reuses the Phase 3 closed Literal value rather than extending it. Document the reuse in the node docstring.
- **Nodes never call sibling nodes** (Phase 6 SHERPA rule). `resolve_target_image` does not call `ingest_target`; the factory chains them. Fence-CI under `graph/nodes/distroless/` rejects `from codegenie.graph.nodes.distroless.<other> import ...`.
- **Per arch §Harness engineering, `replay_with_phase4` delegates to a probabilistic leaf** — Phase 4 owns the LLM call. The node itself is deterministic at the call-site level. No `random` import, no `time` import.
- **The `prior_attempts` list is the in-place-mutation trap.** Use `state.model_copy(update={"prior_attempts": [*state.prior_attempts, new]})` — never `state.prior_attempts.append(new)`. The S5-01 mutation hook fires on regressions.
- **`resolve_target_image` raising `TargetImageRejected` on regex failure (vs silently routing to miss)** is deliberate per CLAUDE.md Rule 12 ("Fail loud"). A typosquat is a *security* event, not a recoverable miss.
