# Story S5-01 — `ReplanHook` Protocol + integration contract test

**Step:** Step 5 — GateRunner three-retry loop + Phase 4 replan_hook integration
**Status:** Ready
**Effort:** S
**Depends on:** S4-05
**ADRs honored:** ADR-0002, ADR-0006

## Context

`GateRunner` invokes Phase 4's `FallbackTier.run` on every retryable failure to obtain a new `RecipeApplication`. The architecture (§Component design) called this a "closure over `FallbackTier.run`" without a typed contract — Gap 2 in the gap analysis. Without a Protocol and a contract test, Phase 4 can change its signature and Phase 5 silently breaks. This story plants the typed seam (`ReplanHook` in `gates/contract.py`) and the integration assertion that the orchestrator's concrete hook actually accepts a `GateContext` with `prior_attempts` and returns a non-empty `RecipeApplication.diff`, with the fence-wrapped `prior_failure_summary` visible in the captured prompt.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Gap analysis Gap 2` — formalize `ReplanHook` Protocol; contract test rationale.
  - `../phase-arch-design.md §Component design — GateRunner` — `replan_hook: ReplanHook | None` signature; closure over `FallbackTier.run`.
  - `../phase-arch-design.md §Process view §Scenario 2` — sequence diagram showing the retry call into Phase 4 with `prior_attempts=[AttemptSummary(...)]`.
  - `../phase-arch-design.md §Code contracts and APIs` — `AttemptSummary` shape (`attempt_id`, `sandbox_run_id`, `failing_signals`, `prior_failure_summary`, `evidence_paths`).
- **Phase ADRs:**
  - `../ADRs/0002-additive-prior-attempts-kwarg.md` — `prior_attempts: list[AttemptSummary] = []` kwarg shape and prompt-injection rationale.
  - `../ADRs/0006-protocol-vs-abc-convention.md` — Protocol (not ABC) for cross-phase callables; structural typing matches "closure" framing.
- **Production ADRs:**
  - `../../../production/adrs/0011-recipe-first-rag-llm-fallback-planning.md` — `FallbackTier.run` is the load-bearing target the hook wraps.
- **Source design:**
  - `../final-design.md §Synthesis ledger — Retry feedback transport row` — winner score 12.
- **Existing code:**
  - `src/codegenie/gates/contract.py` (from S1-04) — extend with `ReplanHook`; `AttemptSummary`, `GateContext` already live here.
  - Phase 4 `FallbackTier` (existing) — the hook closes over its `run(advisory, repo_ctx, recipe_selection, prior_attempts=...)` signature.
  - `codegenie.llm.fence` (Phase 4) — `FenceWrapper` + canary matcher reused; do not re-implement.

## Goal

Add the typed `ReplanHook` Protocol to `gates/contract.py` and a VCR-cassette integration contract test asserting the orchestrator's concrete hook implementation accepts a `GateContext` carrying `prior_attempts` and returns a usable `RecipeApplication` with the fence-wrapped summary visible in the Phase 4 prompt.

## Acceptance criteria

- [ ] `gates/contract.py` exports a `runtime_checkable` `Protocol` named `ReplanHook` with one `__call__(self, ctx: GateContext) -> RecipeApplication` method; `mypy --strict` accepts both a function and a class-with-`__call__` as conforming.
- [ ] A concrete `_OrchestratorReplanHook` (or equivalent closure factory) lives under `src/codegenie/orchestrator/replan_hook.py` and wraps `FallbackTier.run(advisory=ctx.advisory, repo_ctx=..., recipe_selection=..., prior_attempts=ctx.prior_attempts)`; it must not import anything from `sandbox/` (cross-package boundary).
- [ ] `tests/integration/contracts/test_replan_hook_contract.py` — builds the concrete hook from a fixture `GateContext` with `prior_attempts=[AttemptSummary(...)]`, invokes it under a recorded VCR cassette, and asserts: (a) the returned `RecipeApplication.diff` is non-empty `bytes`; (b) the captured Phase 4 prompt contains the fence-wrapped `prior_failure_summary` (regex match against the canary-bounded block); (c) the canary-pattern matcher in `codegenie.llm.fence` is invoked at least once during the call (verified via `unittest.mock.patch` call-count on the matcher symbol).
- [ ] The VCR cassette is committed under `tests/integration/contracts/cassettes/replan_hook_contract.yaml`; `ANTHROPIC_API_KEY` is scrubbed and the cassette replays offline (`pytest --no-network`).
- [ ] An empty `prior_attempts=[]` invocation also passes through the hook and produces a non-empty diff (regression guard for the kwarg's default-empty behavior per ADR-0002).
- [ ] A `Protocol` conformance test: `assert isinstance(_OrchestratorReplanHook(...), ReplanHook)` (runtime check) and a `mypy` smoke file under `tests/typing/test_replan_hook_typing.py` that passes a non-conforming callable (wrong return type) and is annotated `# type: ignore[arg-type]` to confirm the type checker rejects it.
- [ ] TDD plan's red test exists, is committed, and is green.
- [ ] `ruff check`, `mypy --strict src/codegenie/gates src/codegenie/orchestrator`, `pytest tests/integration/contracts/test_replan_hook_contract.py` pass.

## Implementation outline

1. In `src/codegenie/gates/contract.py`, add:
   ```python
   @runtime_checkable
   class ReplanHook(Protocol):
       def __call__(self, ctx: GateContext) -> RecipeApplication: ...
   ```
   Import `RecipeApplication` from its Phase 4 owner (`codegenie.plan.fallback`) — guard the import with `if TYPE_CHECKING:` to avoid runtime cycles.
2. Create `src/codegenie/orchestrator/replan_hook.py` with a factory `make_orchestrator_replan_hook(fallback_tier, repo_ctx, recipe_selection) -> ReplanHook` returning a closure. The closure pulls `advisory` and `prior_attempts` off `ctx`; everything else is captured.
3. Re-export `ReplanHook` from `src/codegenie/gates/__init__.py`.
4. Add `tests/integration/contracts/conftest.py` with a `gate_context_with_one_prior_attempt` fixture producing a deterministic `GateContext` (frozen UTC timestamps).
5. Configure VCR (`pytest-recording` or `vcrpy`): record once with a live Phase 4 call; scrub `Authorization` and `x-api-key` headers in `before_record_request`.
6. Write the contract test (red), implement the factory (green), refactor.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/integration/contracts/test_replan_hook_contract.py`

```python
# tests/integration/contracts/test_replan_hook_contract.py
from __future__ import annotations

import re
from unittest.mock import patch

import pytest

from codegenie.gates.contract import (
    AttemptSummary,
    GateContext,
    ReplanHook,
)
from codegenie.orchestrator.replan_hook import make_orchestrator_replan_hook


@pytest.mark.vcr("cassettes/replan_hook_contract.yaml")
def test_orchestrator_hook_conforms_and_passes_summary_into_phase4_prompt(
    fallback_tier_stub,
    repo_ctx_stub,
    recipe_selection_stub,
    gate_context_with_one_prior_attempt: GateContext,
) -> None:
    hook = make_orchestrator_replan_hook(
        fallback_tier=fallback_tier_stub,
        repo_ctx=repo_ctx_stub,
        recipe_selection=recipe_selection_stub,
    )

    assert isinstance(hook, ReplanHook), "concrete hook must conform structurally"

    with patch(
        "codegenie.llm.fence.canary_matcher.match",
        wraps=__import__("codegenie.llm.fence.canary_matcher", fromlist=["match"]).match,
    ) as canary_mock:
        recipe_app = hook(gate_context_with_one_prior_attempt)

    # (a) non-empty diff returned
    assert isinstance(recipe_app.diff, bytes) and len(recipe_app.diff) > 0

    # (b) prompt captured by VCR contains the fenced prior_failure_summary
    summary = gate_context_with_one_prior_attempt.prior_attempts[0].prior_failure_summary
    captured_prompt = fallback_tier_stub.last_prompt_text()
    fence_pattern = re.compile(
        r"<BEGIN_PRIOR_ATTEMPT_[A-F0-9]{16}>.*?"
        + re.escape(summary)
        + r".*?<END_PRIOR_ATTEMPT_[A-F0-9]{16}>",
        re.DOTALL,
    )
    assert fence_pattern.search(captured_prompt), "prior_failure_summary must appear fence-wrapped"

    # (c) canary matcher invoked at least once
    assert canary_mock.call_count >= 1, "FenceWrapper canary pattern matcher must run"


@pytest.mark.vcr("cassettes/replan_hook_contract_empty.yaml")
def test_hook_works_with_empty_prior_attempts(
    fallback_tier_stub,
    repo_ctx_stub,
    recipe_selection_stub,
    gate_context_no_priors: GateContext,
) -> None:
    hook = make_orchestrator_replan_hook(
        fallback_tier=fallback_tier_stub,
        repo_ctx=repo_ctx_stub,
        recipe_selection=recipe_selection_stub,
    )
    recipe_app = hook(gate_context_no_priors)
    assert len(recipe_app.diff) > 0, "empty prior_attempts still produces a patch (ADR-0002 default-empty)"
```

### Green — make it pass

Smallest implementation: add `ReplanHook` Protocol; add `make_orchestrator_replan_hook` returning `lambda ctx: fallback_tier.run(advisory=ctx.advisory, repo_ctx=repo_ctx, recipe_selection=recipe_selection, prior_attempts=ctx.prior_attempts)`. Record VCR cassette once against the live Phase 4 with `--record-mode=once`.

### Refactor — clean up

- Replace the lambda with a named function inside the factory so the traceback is readable.
- Add a docstring citing ADR-0002 and Gap 2.
- Ensure no `sandbox/` imports leak in `orchestrator/replan_hook.py`.
- Add `from __future__ import annotations` to defer `RecipeApplication` import to type-checking time.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/gates/contract.py` | Add `ReplanHook` `Protocol`. |
| `src/codegenie/gates/__init__.py` | Re-export `ReplanHook`. |
| `src/codegenie/orchestrator/replan_hook.py` | Concrete factory. |
| `tests/integration/contracts/test_replan_hook_contract.py` | The two contract tests. |
| `tests/integration/contracts/conftest.py` | Fixtures: `gate_context_with_one_prior_attempt`, `gate_context_no_priors`, stubs. |
| `tests/integration/contracts/cassettes/replan_hook_contract.yaml` | Recorded once, committed. |
| `tests/integration/contracts/cassettes/replan_hook_contract_empty.yaml` | Recorded once, committed. |
| `tests/typing/test_replan_hook_typing.py` | mypy smoke for `# type: ignore[arg-type]` rejection. |
| `pyproject.toml` | Add `pytest-recording` (or `vcrpy`) to dev deps if not already present. |

## Out of scope

- `GateRunner.run` loop implementation — S5-02.
- Adding the `prior_attempts` kwarg to `FallbackTier.run` and `FenceWrapper.compose_prior_attempts` helper — S5-03.
- Stage 6 chokepoint AST test — S5-04.
- End-to-end retry-recovers integration — S5-05.

## Notes for the implementer

- `@runtime_checkable` lets the test do `isinstance(hook, ReplanHook)`; without it, the `Protocol` is type-only and the assert fails at import.
- Do **not** put `ReplanHook` under `sandbox/`. It belongs in `gates/contract.py` because the consumer is `GateRunner`. The fence test (S1-07's `test_no_subprocess_outside_build_chokepoint.py` + S5-04's `test_stage6_chokepoint.py`) will complain if `sandbox/` reaches into Phase 4.
- VCR cassette: ensure `decode_compressed_response: true` so the prompt is greppable as plain text.
- The canary pattern matcher symbol path is `codegenie.llm.fence.canary_matcher.match` per Phase 4; verify the import path before mocking — if Phase 4 uses a different module name, this story surfaces the mismatch and the test is the right place to fail.
- Resist adding retry semantics to the hook itself; retry is `GateRunner`'s job (S5-02).
- Keep the factory's parameter list closed under what the orchestrator owns — `fallback_tier`, `repo_ctx`, `recipe_selection`. Pulling `advisory` from `ctx` (not the factory) is what makes the closure usable across attempts.
