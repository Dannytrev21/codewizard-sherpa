# Story S4-05 — Implement `replan_with_phase4` node + no-HITL-note-in-prompt guard

**Step:** Step 4 — Implement the ten nodes as thin wrappers over Phase 3/4/5 engines
**Status:** Ready
**Effort:** M
**Depends on:** S4-01
**ADRs honored:** ADR-0002 (`model_copy(update=...)`), ADR-0004 (retry re-enters Phase 4's `FallbackTier.run` with `prior_attempts`), ADR-0008 (HITL `note` field is operator-readable only, never LLM-readable)

## Context

`replan_with_phase4` is **the only node in Phase 6 that touches an LLM** — and only by transitive call into Phase 4's `FallbackTier.run(advisory, repo_ctx, recipe_selection, prior_attempts=...)`. It's reached on three paths: (1) recipe-miss → RAG-miss; (2) gate failure → `route_after_attempt = "retry_phase4"`; (3) HITL `continue` after exhaustion. In every case the contract is the same — pass `state.prior_attempts` through, set `last_engine="phase4_llm"`, return the updated state.

There is one *security* invariant this node must enforce: **`state.human_decision.note` must never reach Phase 4's prompt builder.** ADR-0008 documents the deferral of HITL operator-auth to Phase 11; the design's compensating posture is that the `note` field is plain text **for human reading only**, never an LLM input. The adversarial concern (`../phase-arch-design.md §Component 6`) is: a future careless edit decides to "give Phase 4 more context" by feeding the operator's note into the retry prompt; the result is an unauthenticated text channel from the local user into the LLM call, defeating fence-wrapping discipline established in Phase 4. The guard test `test_hitl_note_not_in_prompt.py` makes this load-bearing — any read of `state.human_decision.note` from inside `replan_with_phase4` raises at test time.

## References — where to look

- **Architecture:** `../phase-arch-design.md §Component 5` nodes table — `replan_with_phase4` row; `../phase-arch-design.md §Component 6 "HumanRequest / HumanDecision / await_human"` — the `note` field is "never flowed into any LLM prompt"; `../phase-arch-design.md §Scenario 2`
- **Phase ADRs:** `../ADRs/0004-retry-re-enters-phase4-fallback-tier.md` — *the* canonical justification for `prior_attempts` in this call; `../ADRs/0008-hitl-operator-auth-deferred-to-phase11.md` — explains *why* the note must not leak
- **Production ADRs:** ADR-P5-002 — additive `prior_attempts` kwarg on `FallbackTier.run`
- **Prior phases:** `../../04-vuln-llm-fallback-rag/final-design.md §2 FallbackTier` — `FallbackTier.run(advisory, repo_ctx, recipe_selection, prior_attempts=[]) -> FallbackTierResult` (verify the kwarg ordering before importing); `../../04-vuln-llm-fallback-rag/final-design.md` for fence-wrap defense around `prior_attempts`
- **Source design:** `../final-design.md §Conflict-resolution row 3`; `../final-design.md §Departures from all three inputs — "HumanDecision.note is **not** flowed into any LLM prompt"`

## Goal

Land `graph/nodes/replan_with_phase4.py` as a `@audited_node` wrapper that calls Phase 4's `FallbackTier.run(...)` with `prior_attempts=state.prior_attempts`, sets `last_engine="phase4_llm"`, and is **proven** by adversarial test never to read `state.human_decision.note`.

## Acceptance criteria

- [ ] `graph/nodes/replan_with_phase4.py` exports `replan_with_phase4(state: VulnLedger) -> VulnLedger`, decorated with `@audited_node`, calling `FallbackTier().run(advisory=state.advisory, repo_ctx=..., recipe_selection=state.recipe_selection, prior_attempts=state.prior_attempts)`.
- [ ] On return, sets `state.patch = PatchRef(...)` (translated from `FallbackTierResult.plan` per Phase 4's contract), `state.last_engine = "phase4_llm"`, `state.recipe_selection = <regenerated selection from Phase 4>`.
- [ ] **Adversarial guard test `tests/graph/test_nodes/test_hitl_note_not_in_prompt.py` exists and is green.** It instruments the node such that any attribute access of `human_decision.note` from inside `replan_with_phase4` raises a custom `HitlNoteLeaked` sentinel.
- [ ] Three additional TDD tests: (1) first-entry retry (`prior_attempts=[]`); (2) post-failure retry (`prior_attempts=[attempt1]`) verifies the *exact* list reaches Phase 4; (3) post-HITL-continue (`human_decision` non-None) still does *not* read `note`.
- [ ] Engine exceptions propagate.
- [ ] `mypy --strict`, `ruff`, `pytest tests/graph/test_nodes/test_replan_with_phase4.py tests/graph/test_nodes/test_hitl_note_not_in_prompt.py` green; fence-CI still green.

## Implementation outline

1. Confirm Phase 4's import path: `from codegenie.planner.fallback_tier import FallbackTier`; confirm `FallbackTierResult` shape (likely `plan, source, cost_tokens, confidence_signals, ...`).
2. Write the four red TDD tests first; the HITL guard test should be **the first** committed.
3. Implement the node body (~ 40 LOC): construct `repo_ctx` from `state.repo_path` (read Phase 4's `repo_ctx` factory if one exists; otherwise hand-build via the documented shape); call `FallbackTier().run(...)`; translate `result.plan` into `PatchRef`; emit one `GraphEvent(kind="exit", fields={"source": result.source, "cost_tokens": str(result.cost_tokens)})`.
4. **Do not** import `HumanDecision`; if you have to read `human_decision` to thread it through, read `.action` only — never `.note`. The guard test enforces this at runtime.
5. Confirm `last_engine="phase4_llm"` is set unconditionally — `replan_with_phase4` always identifies the LLM as the engine of record, even on the first non-retry entry from a recipe-miss path.
6. Run all four tests; confirm green.

## TDD plan — red / green / refactor

```python
# tests/graph/test_nodes/test_replan_with_phase4.py
from unittest.mock import MagicMock
from codegenie.graph.nodes.replan_with_phase4 import replan_with_phase4
from tests.graph.test_nodes.conftest import make_ledger, fake_attempt_summary


def test_first_entry_passes_empty_prior_attempts(mock_phase4):
    result = MagicMock(plan=MagicMock(diff_path="patch-1.diff", diff=b"d"),
                       source="llm_cold", cost_tokens=1200)
    mock_phase4["FallbackTier"].return_value.run.return_value = result

    out = replan_with_phase4(make_ledger(prior_attempts=[]))

    call = mock_phase4["FallbackTier"].return_value.run.call_args
    assert list(call.kwargs["prior_attempts"]) == []
    assert out.last_engine == "phase4_llm"
    assert out.patch is not None


def test_retry_threads_prior_attempts_into_phase4(mock_phase4):
    """LOAD-BEARING: Phase 5 exit-#19 distinct patch bytes require this wiring."""
    prior = [fake_attempt_summary(n=1), fake_attempt_summary(n=2)]
    result = MagicMock(plan=MagicMock(diff_path="patch-3.diff", diff=b"new"),
                       source="llm_fewshot", cost_tokens=2400)
    mock_phase4["FallbackTier"].return_value.run.return_value = result

    out = replan_with_phase4(make_ledger(prior_attempts=prior))

    call = mock_phase4["FallbackTier"].return_value.run.call_args
    assert list(call.kwargs["prior_attempts"]) == prior  # not [] — would break exit-#19
```

```python
# tests/graph/test_nodes/test_hitl_note_not_in_prompt.py
"""ADR-0008 invariant: HumanDecision.note must never reach Phase 4's prompt.

This is a SECURITY BOUNDARY. The note field is operator-readable plain text
(no auth in Phase 6 — single-host trust posture). Letting it into an LLM
prompt would create an unauthenticated text channel from any local user
into the agent's reasoning loop.
"""
import pytest
from unittest.mock import MagicMock
from codegenie.graph.nodes import replan_with_phase4 as rp_mod
from codegenie.graph.nodes.replan_with_phase4 import replan_with_phase4
from tests.graph.test_nodes.conftest import make_ledger


class HitlNoteLeaked(AssertionError):
    pass


class GuardedDecision:
    """A HumanDecision proxy whose `note` access raises — the canary."""
    def __init__(self, real):
        object.__setattr__(self, "_real", real)

    def __getattr__(self, name):
        if name == "note":
            raise HitlNoteLeaked(
                "replan_with_phase4 read HumanDecision.note — ADR-0008 violation"
            )
        return getattr(self._real, name)


def test_replan_does_not_read_human_decision_note(mock_phase4, monkeypatch):
    # Arrange — HITL continue branch, decision present, note has obvious content
    real_decision = MagicMock(action="continue", operator="alice", note="DO NOT READ ME")
    guarded = GuardedDecision(real_decision)
    ledger = make_ledger(human_decision=guarded, prior_attempts=[])
    result = MagicMock(plan=MagicMock(diff_path="p.diff", diff=b"d"),
                       source="llm_cold", cost_tokens=1)
    mock_phase4["FallbackTier"].return_value.run.return_value = result

    # Act + Assert — must NOT raise HitlNoteLeaked
    try:
        replan_with_phase4(ledger)
    except HitlNoteLeaked as e:
        pytest.fail(str(e))
```

**Red:** All four tests fail (module missing).
**Green:** Implement node; tests pass. The guard test is the load-bearing security canary.
**Refactor:** Confirm no `from codegenie.graph.hitl import HumanDecision` in the node module — there's literally no reason to import the type. Confirm `repo_ctx` construction is hoisted into a one-line helper that's *trivially* note-free.

## Files to touch

| Path | Action |
|---|---|
| `src/codegenie/graph/nodes/replan_with_phase4.py` | New |
| `tests/graph/test_nodes/test_replan_with_phase4.py` | New (TDD red) |
| `tests/graph/test_nodes/test_hitl_note_not_in_prompt.py` | New (security canary; commit first) |

## Out of scope

- Phase 4's prompt-builder internals — owned by `src/codegenie/planner/fallback_tier.py`.
- The fence-wrapping of `prior_attempts` summaries inside the Phase 4 prompt — also Phase 4's job (ADR-P5-002 spec).
- Cost-cap-breach handling — Phase 4's `LlmInvocationGuard` raises; this node propagates.
- Same-signature flake detection — done by `route_after_attempt` (S3-02), not here.
- Resetting `prior_attempts` on `HumanDecision.action="continue"` — Gap 4 of the arch design; this node does *not* mutate `prior_attempts` regardless of the HITL action.

## Notes for the implementer

- **The guard test (`test_hitl_note_not_in_prompt.py`) is the load-bearing security invariant for this story.** It must be in the first commit. If you write the node first and the guard later, you're paving over the threat model.
- The `GuardedDecision` proxy in the test is intentionally cumbersome — that's the point. If the production code never reads `.note`, the proxy is transparent; if it does, the proxy *loudly* fails. Don't refactor the proxy into something cleaner; clarity-on-failure is the design goal.
- `repo_ctx` construction: Phase 4 likely has a `build_repo_ctx(repo_path)` helper. If not, the node hand-builds the minimal `RepoCtx(repo_path=..., aliases=..., manifests=...)` — but read Phase 4's contract first; don't invent a shape.
- Per `../phase-arch-design.md §Component 5`, p50 = 3–8 s (LLM-bound). The fence-CI gate from S1-01 forbids `graph/` importing `anthropic` directly — the import boundary is Phase 4. Confirm this still holds after your edits.
- This node is the **only** place in Phase 6 where wall-clock variance dominates per-node overhead. The perf canary (S9-01) skips nodes that hit the network; this one is excluded from the 25%-regression gate.
- If Phase 4 raises `CostCapExceeded`, it propagates up; LangGraph captures state at the last checkpoint; CLI exits 1 (S6-02). Do not retry inside this node.
