# Story S4-06 — Implement `validate_in_sandbox` node + Phase 5 `run_one` public promotion (ADR-P6-001 land)

**Step:** Step 4 — Implement the ten nodes as thin wrappers over Phase 3/4/5 engines
**Status:** Ready
**Effort:** M
**Depends on:** S4-01
**ADRs honored:** ADR-0003 (per-gate retry counter — this node sets `current_gate_id`), ADR-0010 / ADR-P6-001 (promote `_run_one_attempt` to public `run_one` — the single surgical Phase 5 touch), ADR-0002 (`model_copy(update=...)`)

## Context

`validate_in_sandbox` is the **single highest-risk story in Step 4** because it is the only one that touches Phase 5 source. The Phase 6 design unrolls Phase 5's `for attempt in range(1, max_attempts + 1)` loop into a LangGraph cycle — which means Phase 5's per-attempt body must be callable from outside the loop. ADR-0010 / ADR-P6-001 commit to **the one and only Phase 5 source edit** in Phase 6: promote `GateRunner._run_one_attempt` (private) to `GateRunner.run_one` (public). `GateRunner.run` (the looped public API) is unchanged and still works for sync callers.

**Gap 2 of `../phase-arch-design.md` flags the risk:** Phase 5's `_run_one_attempt` may not actually be a clean single-attempt seam. The implementer must **read `src/codegenie/gates/runner.py` first** before writing any code. Three branches:

1. **Clean seam.** A private `_run_one_attempt(transition, ctx) -> GateOutcome` already exists. The change is a one-line public rename + an import in this node. Update the ADR's Decision section with "shipped as rename-only."
2. **Almost-clean seam.** The per-attempt body is factorable in 20–40 LOC of surgical refactor; do it; update Phase 5's contract-snapshot tests in lockstep; update the ADR with "shipped as small refactor."
3. **Not a clean seam at all** (loop body deeply interleaved with `RetryLedger.record` and `ctx.with_prior_attempt` mutations). **STOP. Surface a wider Phase 5 refactor as a follow-up story; do not inline Phase 5's per-attempt logic into this node** — the Phase 5 parity test (S7-02) will fail by construction.

Once the seam exists, the node body itself is short: build `GateContext`, call `run_one`, stamp `last_outcome` and `current_gate_id` onto the ledger, emit one event.

## References — where to look

- **Architecture:** `../phase-arch-design.md §Component 5` — `validate_in_sandbox` row; `../phase-arch-design.md §Gap analysis Gap 2`; `../phase-arch-design.md §Implementation-level risks #1`
- **Phase ADRs:** `../ADRs/0010-phase5-runner-run-one-public-promotion.md` — read in full before writing code; `../ADRs/0003-per-gate-retry-counter-scope.md` — explains why `current_gate_id` must be set HERE (not in `record_attempt`)
- **Prior phases:** `../../05-sandbox-trust-gates/final-design.md §6 GateRunner` — confirm whether `_run_one_attempt` is already factored; `../../05-sandbox-trust-gates/final-design.md §"GateContext, GateOutcome, AttemptSummary"` — input/output shapes
- **Source design:** `../final-design.md §Component 5 "validate_in_sandbox + record_attempt"`; `../final-design.md §Risk 1`

## Goal

(a) Promote Phase 5's `_run_one_attempt` to a public `GateRunner.run_one(transition, ctx) -> GateOutcome` (smallest possible change per ADR-P6-001). (b) Implement `graph/nodes/validate_in_sandbox.py` as a thin wrapper that calls `run_one` once per node invocation, stamps `last_outcome` + `current_gate_id`. (c) Land the contract-lint test that fails loudly if `run_one` ever reverts to private.

## Acceptance criteria

- [ ] **Pre-flight evidence note** at the top of the PR description: paste the relevant ~30 lines of `src/codegenie/gates/runner.py` showing the current seam, classify into branch 1/2/3 above, and state which path you took.
- [ ] `src/codegenie/gates/runner.py` has a public `GateRunner.run_one(transition: TransitionId, ctx: GateContext) -> GateOutcome` method. Either via a one-line rename of `_run_one_attempt` or a small refactor (≤ 50 LOC delta).
- [ ] If a refactor was needed, Phase 5's contract-snapshot test(s) in `tests/gates/test_runner_contract.py` (or equivalent) were updated in the *same* PR; full Phase 5 regression suite green.
- [ ] `tests/graph/test_runner_run_one_public.py` exists and asserts `codegenie.gates.runner.GateRunner.run_one` is importable and is *public* (not name-mangled, not starting with `_`).
- [ ] `graph/nodes/validate_in_sandbox.py` exports `validate_in_sandbox(state: VulnLedger) -> VulnLedger`, decorated with `@audited_node`, constructing `GateContext(worktree=state.repo_path, advisory=state.advisory, recipe_selection=state.recipe_selection, prior_attempts=state.prior_attempts)`, calling `GateRunner(...).run_one(transition=Phase5_STAGE6_VALIDATE, ctx=ctx)`, returning new state with `last_outcome` and `current_gate_id` set.
- [ ] TDD red tests: (1) wrapper call asserts `run_one` invoked exactly once per node call; (2) `current_gate_id` is stamped before `record_attempt` runs (so the next-node retry-count-reset semantics work); (3) engine exceptions propagate.
- [ ] If branch 3 (not-clean seam) — story is **closed as blocked**, with a follow-up story for the Phase 5 refactor; ADR-P6-001 amended to say so.
- [ ] `mypy --strict`, `ruff`, `pytest`, fence-CI all green.

## Implementation outline

1. **Read** `src/codegenie/gates/runner.py` end-to-end. Determine which branch (1/2/3) applies.
2. Write the red contract-lint test `tests/graph/test_runner_run_one_public.py` (will fail until Phase 5 is touched).
3. Apply the chosen branch:
   - Branch 1: rename `_run_one_attempt` → `run_one` (signature unchanged). Update any internal callsites inside `run()` to use the new public name.
   - Branch 2: extract the per-attempt body from `run()` into `run_one`. `run()` becomes `for attempt in ...: outcome = self.run_one(transition, ctx); self.ledger.record(...); ctx = ctx.with_prior_attempt(outcome); ...`.
   - Branch 3: STOP. Surface; do not write the node body. Update ADR-P6-001 Decision section to record the block.
4. Write the three red TDD tests for `validate_in_sandbox` in `tests/graph/test_nodes/test_validate_in_sandbox.py`.
5. Implement the node body (~ 40 LOC): determine `transition` (Phase 5 likely exports `TransitionId.STAGE6_VALIDATE` or similar — read the contract); build `GateContext`; call `GateRunner(sandbox=..., gate=..., ledger=...).run_one(transition, ctx)`; build new state via `model_copy(update={"last_outcome": outcome, "current_gate_id": transition.id, "last_node": "validate_in_sandbox", "events": [...]})`.
6. Confirm Phase 5 sync regression suite still green; confirm new tests green; commit.
7. Amend ADR-P6-001's "Decision" section with a one-paragraph note describing what actually shipped (rename-only vs small refactor).

## TDD plan — red / green / refactor

```python
# tests/graph/test_runner_run_one_public.py
"""ADR-P6-001 canary: Phase 5's run_one must stay public; a revert breaks this build."""
import inspect
import codegenie.gates.runner


def test_gate_runner_run_one_is_public_callable():
    cls = codegenie.gates.runner.GateRunner
    assert hasattr(cls, "run_one"), "ADR-P6-001 reverted: run_one missing"
    assert not "run_one".startswith("_"), "method must be public"
    sig = inspect.signature(cls.run_one)
    # Expected: self, transition, ctx -> GateOutcome
    assert "transition" in sig.parameters
    assert "ctx" in sig.parameters
```

```python
# tests/graph/test_nodes/test_validate_in_sandbox.py
from unittest.mock import MagicMock
import pytest
from codegenie.graph.nodes.validate_in_sandbox import validate_in_sandbox
from tests.graph.test_nodes.conftest import make_ledger


def test_validate_calls_run_one_once_per_invocation(mock_phase5):
    """The whole point of ADR-P6-001: ONE attempt per node call.
    If run_one is called > 1 times, the parity test (S7-02) will fail."""
    outcome = MagicMock(passed=False, retryable=True, failing_signals=["tests"])
    mock_phase5["GateRunner"].return_value.run_one.return_value = outcome

    out = validate_in_sandbox(make_ledger(patch=MagicMock()))

    assert mock_phase5["GateRunner"].return_value.run_one.call_count == 1
    assert out.last_outcome is outcome


def test_validate_stamps_current_gate_id_for_retry_counter(mock_phase5):
    """ADR-0003: record_attempt resets retry_count on current_gate_id change.
    If current_gate_id isn't stamped HERE, the retry counter never advances correctly."""
    outcome = MagicMock(passed=False, retryable=True, failing_signals=["build"])
    mock_phase5["GateRunner"].return_value.run_one.return_value = outcome

    out = validate_in_sandbox(make_ledger(current_gate_id=None, patch=MagicMock()))

    assert out.current_gate_id is not None
    assert out.current_gate_id != ""


def test_validate_propagates_sandbox_failure(mock_phase5):
    mock_phase5["GateRunner"].return_value.run_one.side_effect = RuntimeError("sandbox boot failed")
    with pytest.raises(RuntimeError, match="sandbox boot failed"):
        validate_in_sandbox(make_ledger(patch=MagicMock()))
```

**Red:**
1. `test_runner_run_one_public.py` fails until Phase 5 source is touched.
2. Node tests fail until module exists.

**Green:** Rename or refactor `_run_one_attempt`; implement node; tests pass.

**Refactor:** Confirm the Phase 5 contract-snapshot tests, if any (`tests/gates/test_runner_contract.py`), exercise both `run` (looped) and `run_one` (single) paths. If Phase 5 ships only the looped-API snapshot, add a `run_one` snapshot in the same PR.

## Files to touch

| Path | Action |
|---|---|
| `src/codegenie/gates/runner.py` | **Surgical** — rename `_run_one_attempt` → `run_one` (branch 1) or small refactor (branch 2). The only Phase 0–5 source touch in all of Phase 6. |
| `tests/gates/test_runner_contract.py` (or equivalent) | Update Phase 5 contract snapshot if refactor was needed |
| `src/codegenie/graph/nodes/validate_in_sandbox.py` | New |
| `tests/graph/test_runner_run_one_public.py` | New (CI canary against revert) |
| `tests/graph/test_nodes/test_validate_in_sandbox.py` | New (TDD red) |
| `docs/phases/06-sherpa-state-machine/ADRs/0010-phase5-runner-run-one-public-promotion.md` | Amend Decision section to describe what shipped (rename-only / small refactor / blocked) |

## Out of scope

- Recording the attempt in `RetryLedger` — that's `record_attempt` (S4-07). `run_one` returns `GateOutcome` only; it must NOT write to the ledger from inside, or the Phase 6 cycle will double-write. (See ADR-P6-001 Consequences.)
- Multi-attempt loops — Phase 6 unrolls the loop into the LangGraph cycle. If you find yourself thinking "what if I call `run_one` twice here," you're rebuilding the loop in the wrong place.
- Changing `GateContext` shape — additive Phase 5 evolution only; Phase 6 just constructs.
- Changing `transition` semantics — Phase 5 defines `TransitionId`; Phase 6 reads.

## Notes for the implementer

- **Read Phase 5 first.** No exceptions. The whole story collapses or proceeds based on what you find in `src/codegenie/gates/runner.py`. Spend the first 30 minutes reading, not coding.
- If you choose branch 2 (refactor): the parity test `tests/integration/test_retry_semantics_parity.py` (S7-02) is the *byte-identical* canary against drift. If it ever fails after this story, one of the two implementations is wrong. Run it locally before committing.
- The `current_gate_id` value comes from the `transition` — Phase 5's `TransitionId` (likely a string or an enum). Use a stable, content-addressed string; `record_attempt` reads it to decide whether to reset `retry_count`.
- Do **not** add a `run_one_async` variant. Phase 6 nodes are sync; LangGraph bridges to async at the checkpointer.
- The fence-CI gate from S1-01 forbids `graph/` importing `os | time | random | datetime` (in edges.py specifically; nodes are unrestricted). Confirm node body doesn't trip the broader linter.
- The wall-clock budget is 45–90 s per call (sandbox boot dominates) — this node is excluded from the per-node overhead canary (S9-01). The replay-after-kill test (S8-01) targets a SIGKILL specifically during this node's wall-clock window.
- If branch 3 (not-clean seam): **be loud about it**. CLAUDE.md Rule 12 — "Fail loud." Don't hand-wave around it. Add a `(Blocked-by: Phase-5-refactor-needed)` tag on the story, write a follow-up story sketch, and check in with the architect before doing anything else.
