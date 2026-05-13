# Story S4-03 — Implement `apply_recipe` node

**Step:** Step 4 — Implement the ten nodes as thin wrappers over Phase 3/4/5 engines
**Status:** Ready
**Effort:** S
**Depends on:** S4-01
**ADRs honored:** ADR-0002 (`frozen=False` + `model_copy(update=...)`), ADR-0004 (retry re-enters Phase 4 with `prior_attempts`), ADR-0012 (per-node tests over field-ACL machinery)

## Context

`apply_recipe` is the convergence point for *every* engine-of-record path: recipe-matched, RAG-hit, or Phase 4 LLM fallback all flow through here. Its job is to take whatever `patch` / `recipe_selection` is currently on the ledger, call Phase 3's `RecipeEngine.apply(ApplyContext(patch=state.patch, prior_attempts=state.prior_attempts))`, and stamp the resulting `PatchRef` (path + blake3 digest) plus `last_engine` discriminator back onto the ledger. The `prior_attempts` kwarg is **load-bearing** — ADR-P5-002 made it additive across Phase 3, 4, and 5 specifically so that retry passes produce *distinct* patch bytes (Phase 5 exit-criterion #19). If `apply_recipe` drops `prior_attempts` on the floor, the parity test (S7-02) and the distinct-patch-bytes test (S7-03) will both fail by construction.

The node is deterministic (given a fixed patch + prior_attempts → same engine output) and synchronous; its single failure mode worth catching is "Phase 3 raises" — which is propagated, not swallowed. Tests use the conftest mock to verify that `prior_attempts` is *wired through* into the `ApplyContext` constructor, because losing that kwarg is the highest-impact silent-bug shape for this node.

## References — where to look

- **Architecture:** `../phase-arch-design.md §Component 5` nodes table — `apply_recipe` row; `../phase-arch-design.md §Control flow Step 10`
- **Phase ADRs:** `../ADRs/0004-retry-re-enters-phase4-fallback-tier.md` — explains why `prior_attempts` must flow; `../ADRs/0002-vuln-ledger-frozen-false-with-runtime-mutation-hook.md`
- **Production ADRs:** ADR-P5-002 (additive `prior_attempts` kwarg across Phase 3/4/5 — verify the kwarg name and position before importing)
- **Prior phases:** `../../03-vuln-deterministic-recipe/final-design.md §2 "RecipeEngine ABC"` — `RecipeEngine.apply(recipe, repo, ctx: ApplyContext)`; `../../05-sandbox-trust-gates/final-design.md §6 GateRunner` for the `prior_attempts` shape (`list[AttemptSummary]`)
- **Source design:** `../final-design.md §Conflict-resolution row 3 "Retry path"` — re-enter Phase 4 with `prior_attempts`; `apply_recipe` is downstream of that

## Goal

Land `graph/nodes/apply_recipe.py` as a thin `@audited_node` wrapper that calls Phase 3's `RecipeEngine.apply(...)` with `ApplyContext(prior_attempts=state.prior_attempts, ...)` and stamps `PatchRef` + `last_engine` onto the ledger.

## Acceptance criteria

- [ ] `graph/nodes/apply_recipe.py` exports `apply_recipe(state: VulnLedger) -> VulnLedger`, decorated with `@audited_node`, that constructs `ApplyContext(patch=state.patch, prior_attempts=state.prior_attempts, ...)` and calls `RecipeEngine().apply(state.recipe_selection.recipe, state.repo_path, ctx)`.
- [ ] Returned `RecipeApplication` is translated into a `PatchRef(path=..., blake3=...)` set on the new ledger; `last_engine` is set to `"recipe"` when `state.recipe_selection.recipe is not None` and `state.rag_hit is None`, `"rag"` when `state.rag_hit is not None`, `"phase4_llm"` when entering after `replan_with_phase4` (read `state.last_engine` — if `replan_with_phase4` already set it, preserve).
- [ ] The TDD red test `test_apply_recipe_threads_prior_attempts` asserts the engine was called with `ctx.prior_attempts == state.prior_attempts` (the load-bearing wiring check) and is committed before any production code.
- [ ] Emits one `GraphEvent(kind="exit", fields={"patch_blake3": <hex>, "patch_size_bytes": <int>})`.
- [ ] `mypy --strict`, `ruff`, and `pytest tests/graph/test_nodes/test_apply_recipe.py` all green.

## Implementation outline

1. Locate Phase 3's actual `ApplyContext` signature in `src/codegenie/recipes/` — confirm `prior_attempts: list[AttemptSummary] = []` is a real kwarg (it should be per ADR-P5-002). If not, surface as a blocker — do not paper over.
2. Write the red tests below in `tests/graph/test_nodes/test_apply_recipe.py`.
3. Implement the node (~ 30 LOC): import `RecipeEngine`, `ApplyContext` from Phase 3; construct `ApplyContext(patch=state.patch, prior_attempts=state.prior_attempts, repo_path=state.repo_path)`; call `engine.apply(...)`; build `PatchRef(path=application.diff_path, blake3=blake3(application.diff).hexdigest())`.
4. Determine `last_engine` value from incoming state (see AC #2 above for the precedence).
5. Emit event with `patch_blake3` + `patch_size_bytes` (perf-traceable in Phase 13's cost ledger).
6. Confirm tests green; confirm no in-place mutations (S4-01's hook would catch).

## TDD plan — red / green / refactor

```python
# tests/graph/test_nodes/test_apply_recipe.py
from unittest.mock import MagicMock
import pytest
from codegenie.graph.nodes.apply_recipe import apply_recipe
from tests.graph.test_nodes.conftest import make_ledger, fake_attempt_summary


def test_apply_recipe_threads_prior_attempts(mock_phase3):
    """LOAD-BEARING: prior_attempts must reach ApplyContext or Phase 5 exit-#19 breaks."""
    # Arrange — three prior failures on the ledger
    prior = [fake_attempt_summary(n=i) for i in (1, 2, 3)]
    application = MagicMock(diff=b"--- a/x\n+++ b/x\n", diff_path="patch-attempt-4.diff",
                            engine_used="recipe")
    mock_phase3["RecipeEngine"].return_value.apply.return_value = application
    ledger = make_ledger(prior_attempts=prior, recipe_selection=MagicMock(recipe=MagicMock()))

    # Act
    out = apply_recipe(ledger)

    # Assert — INTENT: the *exact* prior_attempts list must reach ApplyContext;
    # otherwise the retry produces patch bytes indistinguishable from attempt 1
    # (Phase 5 exit-#19 violation).
    call = mock_phase3["RecipeEngine"].return_value.apply.call_args
    ctx = call.kwargs.get("ctx") or call.args[-1]
    assert list(ctx.prior_attempts) == prior  # NOT empty, NOT a copy with missing items

    # PatchRef stamped from application
    assert out.patch is not None
    assert out.patch.blake3  # non-empty hex
    assert out.last_engine == "recipe"


def test_apply_recipe_preserves_phase4_engine_discriminator(mock_phase3):
    """When the upstream was replan_with_phase4, last_engine must NOT be overwritten to 'recipe'."""
    application = MagicMock(diff=b"d", diff_path="p.diff", engine_used="phase4_llm")
    mock_phase3["RecipeEngine"].return_value.apply.return_value = application
    ledger = make_ledger(last_engine="phase4_llm",
                         recipe_selection=MagicMock(recipe=None),
                         rag_hit=None)

    out = apply_recipe(ledger)
    assert out.last_engine == "phase4_llm"


def test_apply_recipe_propagates_engine_failure(mock_phase3):
    mock_phase3["RecipeEngine"].return_value.apply.side_effect = RuntimeError("engine blew up")
    with pytest.raises(RuntimeError, match="engine blew up"):
        apply_recipe(make_ledger(recipe_selection=MagicMock(recipe=MagicMock())))
```

**Red:** `apply_recipe` doesn't exist; all three tests fail.
**Green:** Implement the node; tests pass. The `prior_attempts` test is the canary against the silent-drop bug.
**Refactor:** Confirm `last_engine` precedence is a *single* helper function (e.g., `_pick_engine(state) -> Literal["recipe","rag","phase4_llm"]`) so the rule lives in one place, not scattered.

## Files to touch

| Path | Action |
|---|---|
| `src/codegenie/graph/nodes/apply_recipe.py` | New |
| `tests/graph/test_nodes/test_apply_recipe.py` | New (TDD red) |
| `tests/graph/test_nodes/conftest.py` | Extend — add `fake_attempt_summary(n)` builder if not already present |

## Out of scope

- The actual Phase 4 prompt enrichment with `prior_attempts` — that's Phase 4's `FallbackTier.run` internals, exercised by `replan_with_phase4` (S4-05) and parity-tested in S7-03.
- Applying the patch to the worktree — Phase 3's `RecipeEngine.apply` owns the worktree mutation; `apply_recipe` only translates the result into `PatchRef`.
- Patch caching by `blake3` — the design note in `../phase-arch-design.md §Idempotence` mentions "if the file exists with same blake3, it's reused" — that's Phase 3's responsibility, not ours.
- `last_engine` *changes* via this node — once Phase 4 stamped `"phase4_llm"`, `apply_recipe` preserves it. Don't repaint.

## Notes for the implementer

- **The `prior_attempts` wiring is the single most important line in this node.** If you forget the kwarg, every other Phase 6 test still passes (`prior_attempts` is just an empty list on the first attempt), but S7-03 fails after the first retry and there's no green CI signal until then. Make the unit test loud.
- `PatchRef` shape is from `graph/state.py` (S1-02): `(path: Path, blake3: str)`. The hex digest is the bytes-level identity Phase 5's parity test reads.
- Don't compute the blake3 digest here twice — if Phase 3's `RecipeApplication` already carries one, trust it. If not, compute once via `blake3(application.diff).hexdigest()`.
- Per `../phase-arch-design.md §Component 5`, p50 ≤ 200 ms — this includes Phase 3's actual apply work (npm/ncu wrapping); Phase 6's overhead is < 5 ms. Don't add caching.
- The fence-CI gate from S1-01 forbids importing sibling nodes; importing from `codegenie.recipes.*` is fine — that's the Phase 3 boundary.
