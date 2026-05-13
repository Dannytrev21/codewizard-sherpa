# Story S1-04 — Add `task_type` kwarg to `FallbackTier.run`

**Step:** Step 1 — Establish the six additive seams, ADRs, and the contract-surface snapshot canary
**Status:** Ready
**Effort:** S
**Depends on:** —
**ADRs honored:** ADR-P7-003 (this phase ADR-0004), ADR-P7-008 (this phase ADR-0001), production ADR-0011

## Context

Phase 4's `FallbackTier.run` ships with a vuln-shaped signature and no notion of task class; Phase 7's `replan_with_phase4` node will need to route the distroless workflow to the distroless prompt and the distroless solved-examples collection. This story lands the *additive* kwarg seam: `task_type: str | None = None` is appended as a keyword-only argument; when `None`, behavior is byte-identical to the pre-edit implementation. A dedicated integration test pins the byte-identity claim — without it, "behavior-preserving" is convention, not fact.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component 13 ADR-P7-003` (lines ~860–880) — exact signature change; the `None`-default contract.
  - `../phase-arch-design.md §Gap 6` — the prompt-bleed anti-case (vuln advisory + `task_type="distroless_migration"`); the symmetric test (`test_phase4_task_type_mismatch_safety.py`) lives in S6-08, not here.
  - `../phase-arch-design.md §Testing strategy ›Integration tests` — `test_phase4_default_task_type_behavior_unchanged.py` is the test this story owns.
- **Phase ADRs:**
  - `../ADRs/0004-fallback-tier-task-type-kwarg.md` — ADR-P7-003 — the decision; `None`-default behavior-preservation rationale; rejection of the parallel `MigrationFallbackTier` alternative.
  - `../ADRs/0001-six-named-additive-seams-and-adr-0028-amendment.md` — ADR-P7-008 — kwarg-with-`None`-default is one of the six allowed additive shapes.
- **Production ADRs:**
  - `../../../production/adrs/0011-recipe-first-rag-llm-fallback-planning.md` — recipe → RAG → LLM-fallback; the kwarg gates routing inside the LLM-fallback stage only.
- **Existing code (read before writing):**
  - `src/codegenie/planner/fallback_tier.py` — read `FallbackTier.run`'s current signature *exactly* (every positional, every keyword-only arg, every default). The new kwarg must land *after* `prior_attempts` (the most recent existing kwarg per the arch doc).
  - `src/codegenie/graph/nodes/replan_with_phase4.py` (or wherever Phase 6's `replan_with_phase4` lives) — confirm vuln callers never pass `task_type`; they will keep passing nothing and the `None` default carries them.
  - Phase 4's existing integration tests under `tests/integration/` that hit `FallbackTier.run` — these are the byte-identity anchor.

## Goal

`FallbackTier.run` gains a keyword-only `task_type: str | None = None` kwarg, and `tests/integration/test_phase4_default_task_type_behavior_unchanged.py` proves that omitting the kwarg produces byte-identical `FallbackTierResult` to the pre-edit code path on at least one representative vuln fixture.

## Acceptance criteria

- [ ] `FallbackTier.run` in `src/codegenie/planner/fallback_tier.py` declares `task_type: str | None = None` as a **keyword-only** argument, positioned after `prior_attempts` and before any return-type annotation.
- [ ] When `task_type is None`, no branch inside `FallbackTier.run` is entered that differs from the pre-edit code path (i.e., the function falls through to the existing vuln prompt-template loader and the existing vuln RAG collection). When `task_type` is a non-`None` `str`, the function selects the prompt template at `src/codegenie/planner/prompts/migration_{task_type}.v1.yaml` and the RAG collection `{task_type}_solved_examples_promoted` — but the prompt YAML and collection are NOT shipped in this story; the lookup may raise `PromptTemplateNotFound` (or equivalent) for non-`None` values until S6-06 lands the actual template. **The branch exists; its non-`None` body is "lookup-and-fail-loud."**
- [ ] `tests/integration/test_phase4_default_task_type_behavior_unchanged.py` is committed and green: runs the existing Phase 4 vuln fixture(s) through `FallbackTier.run` *twice* — once with the explicit pre-edit call shape and once with the new shape (no `task_type` kwarg, so it defaults to `None`) — and asserts the two `FallbackTierResult` instances are byte-identical (`model_dump_json` equal, sorted-key canonical-JSON equal).
- [ ] `tests/unit/planner/test_fallback_tier_signature.py` is committed and green: uses `inspect.signature(FallbackTier.run)` to assert (a) `task_type` is keyword-only, (b) default is `None`, (c) annotation is `str | None` (or `Optional[str]` — match the codebase's existing style).
- [ ] At least one existing Phase 4 vuln integration test (`tests/integration/test_phase4_*.py` or similar) still passes verbatim with the new code (no test edits needed).
- [ ] `ruff check`, `ruff format --check`, and `mypy --strict` pass on `src/codegenie/planner/fallback_tier.py` and both new test files.

## Implementation outline

1. Read `src/codegenie/planner/fallback_tier.py` and capture the current `FallbackTier.run` signature as a comment in the integration test for documentation.
2. Identify a representative Phase 4 vuln fixture (or build one minimally — re-use whatever the existing Phase 4 integration suite uses; do not invent a new fixture for this story).
3. Write the failing tests in `tests/integration/test_phase4_default_task_type_behavior_unchanged.py` and `tests/unit/planner/test_fallback_tier_signature.py` (TDD red).
4. Edit `FallbackTier.run`: append `*, task_type: str | None = None` to the signature (keyword-only, after `prior_attempts`). Add a single early-return-or-branch guard: `if task_type is None: # pre-Phase-7 path` falls through; `else: # Phase 7+ task-class routing path` selects template + collection by `task_type`.
5. Run both new tests + the broader Phase 4 integration suite; iterate until green.
6. Refactor: function docstring update naming ADR-P7-003; ensure the non-`None` branch's prompt-template-and-collection lookup raises a typed exception (`PromptTemplateNotFound` or `TaskTypeUnsupported`) loudly — *not* a silent fallback to the vuln path.

## TDD plan — red / green / refactor

### Red — write the failing tests first

Test files:
- `tests/integration/test_phase4_default_task_type_behavior_unchanged.py`
- `tests/unit/planner/test_fallback_tier_signature.py`

```python
# tests/unit/planner/test_fallback_tier_signature.py
import inspect
from codegenie.planner.fallback_tier import FallbackTier


def test_fallback_tier_run_has_task_type_kwarg_keyword_only_default_none():
    sig = inspect.signature(FallbackTier.run)
    assert "task_type" in sig.parameters
    p = sig.parameters["task_type"]
    assert p.kind == inspect.Parameter.KEYWORD_ONLY
    assert p.default is None
    # annotation may be `str | None` or `Optional[str]` — accept both
    assert "str" in str(p.annotation) and "None" in str(p.annotation)
```

```python
# tests/integration/test_phase4_default_task_type_behavior_unchanged.py
import json
import pytest

from codegenie.planner.fallback_tier import FallbackTier
# import the existing vuln fixture builder Phase 4's tests use — read tests/integration/test_phase4_*.py first
from tests.fixtures.phase4 import build_vuln_fallback_inputs  # adjust import to match repo


@pytest.mark.integration
def test_fallback_tier_default_task_type_is_byte_identical_to_pre_edit_behavior():
    advisory, repo_ctx, recipe_selection, kwargs = build_vuln_fallback_inputs()
    tier = FallbackTier()
    # Pre-Phase-7 call shape (no task_type kwarg)
    result_a = tier.run(advisory, repo_ctx, recipe_selection, **kwargs)
    # Post-Phase-7 call shape, explicit task_type=None — must be byte-identical
    result_b = tier.run(advisory, repo_ctx, recipe_selection, **kwargs, task_type=None)

    payload_a = result_a.model_dump_json()
    payload_b = result_b.model_dump_json()
    assert json.loads(payload_a) == json.loads(payload_b), (
        "FallbackTier.run with task_type=None must be byte-identical to the pre-edit call shape — "
        "ADR-P7-003 behavior-preservation invariant."
    )
```

Expected red failure mode: `TypeError: run() got an unexpected keyword argument 'task_type'` on the second call in the integration test, plus `AssertionError: "task_type" in sig.parameters` (signature test).

### Green — make it pass

Edit `src/codegenie/planner/fallback_tier.py`:

```python
def run(
    self,
    advisory: AdvisoryRef,
    repo_ctx: RepoContext,
    recipe_selection: RecipeSelection,
    *,
    run_id: str,
    include_pending: bool,
    auto_promote: bool,
    prior_attempts: list[AttemptSummary] = [],
    task_type: str | None = None,            # NEW — ADR-P7-003
) -> FallbackTierResult:
    if task_type is None:
        # Pre-Phase-7 behavior path — byte-identical to master.
        ...
    else:
        # Phase 7+ task-class routing — selects prompt + RAG collection by task_type.
        # Loud failure if the prompt template / collection don't exist yet (S6-06 lands them).
        ...
```

Do not refactor the existing body. The new branch is the only diff inside the function; everything else stays exactly as it was. Use whatever the codebase's existing default-list pattern is — if the existing `prior_attempts: list[...] = []` mutable default is intentional (pylint-suppressed elsewhere), preserve it; do not "fix" the mutable default in this story (out of scope).

### Refactor — clean up

- Add a one-line docstring update at the top of `FallbackTier.run` citing ADR-P7-003.
- Ensure the `else` branch raises typed errors (e.g., `PromptTemplateNotFound(task_type)`); do not return a partial result silently.
- Re-run the entire Phase 4 integration suite (`pytest tests/integration/ -k phase4`) and confirm zero regressions.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/planner/fallback_tier.py` | Append keyword-only `task_type: str | None = None` to `FallbackTier.run` (ADR-P7-003). |
| `tests/unit/planner/test_fallback_tier_signature.py` | New test — anchors the signature shape via `inspect.signature`. |
| `tests/integration/test_phase4_default_task_type_behavior_unchanged.py` | New test — byte-identity anchor for the `None`-default path. |

## Out of scope

- **`prompts/migration_distroless.v1.yaml`** — S6-06 lands the actual prompt template; this story's non-`None` branch may raise `PromptTemplateNotFound` until then.
- **`distroless_solved_examples_promoted` RAG collection** — S6-07.
- **Task-type mismatch safety test (`test_phase4_task_type_mismatch_safety.py`)** — S6-08 (the test requires a real distroless prompt to verify the failure mode is loud).
- **Phase 8 `xfail` test (`test_supervisor_logs_task_type.py`)** — S6-08 defines the `xfail`; this story does not.
- **`replan_with_phase4` node passing `task_type="distroless_migration"`** — S5-02 (the distroless graph node that uses this kwarg at the callsite).
- **Contract-surface snapshot regen capturing the new signature** — S1-07.

## Notes for the implementer

- The byte-identity assertion is the single most important test in this story. *Run it before and after your edit.* If it's red on `master` (because the kwarg doesn't exist), green after the edit, then byte-identity holds. If `result_a` and `result_b` ever differ for any reason — sorted-key drift, default-list mutation, timestamp inclusion — the test will fail loudly and the seam claim collapses. Use canonical-JSON comparison (`json.loads(payload).items()` sorted), not raw string `==`, to avoid spurious failures from dict-ordering differences across Python minor versions.
- The keyword-only placement (after `*,` or after `prior_attempts` if there's no explicit `*`) is load-bearing. Positional placement would break every existing callsite — that's a behavior-changing edit, not a behavior-preserving extension, and would fire the contract-surface snapshot canary (S1-07) for the wrong reason. Read `phase-arch-design.md §Component 13 ADR-P7-003` for the exact signature shape.
- Do **not** silently fall back to the vuln prompt when `task_type` is non-`None` and the template doesn't exist. Loud failure is what Gap 6 / S6-08 will later exercise. The `else` branch raising `PromptTemplateNotFound` is the right shape; "if template missing, use vuln" is wrong.
- The integration test depends on whatever vuln fixture Phase 4 already uses — *do not invent a new fixture*. Read `tests/integration/test_phase4_*.py` (or wherever Phase 4 integration tests live) and reuse the same `build_*` helper / fixture path. If no such helper exists, build one minimally inside `tests/fixtures/phase4/__init__.py` and reuse it.
- The `inspect.signature` check is sensitive to annotation style — `str | None` vs `Optional[str]` print differently. The assertion uses substring matching to be robust to either style; if the codebase has a preferred style, match it but keep the test's assertion permissive.
- Per CLAUDE.md "Match the codebase's conventions" — if `FallbackTier.run` uses `Optional[str]` instead of `str | None`, match that. Do not switch styles mid-file.
- Mutable default arguments (`prior_attempts: list[AttemptSummary] = []`) are a known Python smell; they exist in the current signature per the arch doc. Do not refactor them in this story — that's a behavior-touching edit outside ADR-P7-003's scope.
