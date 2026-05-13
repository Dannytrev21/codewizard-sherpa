# Story S3-02 — Implement the four conditional-edge predicates + branch-coverage parametrization

**Step:** Step 3 — Ship `@pure_edge` decorator + the four conditional-edge predicates + property tests
**Status:** Ready
**Effort:** M
**Depends on:** S3-01 (`@pure_edge` decorator), S1-02 (`VulnLedger` model with `AttemptSummary`, `RagHit`, `last_outcome`, `recipe_selection`, `human_decision` fields)
**ADRs honored:** ADR-0012 (`@pure_edge` discipline), ADR-0003 (per-gate retry counter + same-signature flake short-circuit), ADR-0014 (Phase 5 three-retry-per-gate, preserved through `state.max_attempts`)

## Context

With the decorator landed, this story implements the four routing predicates that wire the LangGraph topology. They are the *only* routing decisions in Phase 6 — all branching the state machine ever does flows through these four functions. Per ADR-0012 each predicate is small (≤ 20 LOC), pure, takes `VulnLedger`, returns a string literal that LangGraph maps to a destination node.

The four predicates and their codomains:

| Predicate | Reads | Returns |
|---|---|---|
| `route_after_select_recipe` | `state.recipe_selection.matched` | `"matched"` \| `"miss"` |
| `route_after_rag` | `state.rag_hit.score` vs threshold | `"hit"` \| `"miss"` |
| `route_after_attempt` | `state.last_outcome.passed/retryable`, `state.retry_count`, `state.max_attempts`, `state.prior_attempts[-2:]` | `"passed"` \| `"retry_phase4"` \| `"retry_exhausted"` \| `"non_retryable"` |
| `route_after_human` | `state.human_decision.action` | `"continue"` \| `"override"` \| `"abort"` |

The load-bearing one is `route_after_attempt` — it encodes the entire retry policy in one function (ADR-0003) and is the single integration point between Phase 5's per-gate counter (ADR-0014) and Phase 6's HITL trigger. The same-signature flake short-circuit (`_same_signature(prior_attempts[-1], prior_attempts[-2])`) prevents a deterministic failure from burning the retry budget. The implementation per `phase-arch-design.md §Component 4` lines ~720–742 is canonical and must be copied verbatim, then unit-tested over the full cartesian.

The `rag_score_threshold` (0.85 per `tools/policy/graph-thresholds.yaml`) is read **at module load time** from the policy YAML, not inlined as a magic number. The YAML itself is shipped in S5-03; for now the predicate reads from a small `Settings` loader that defaults to 0.85 if the file is absent (development ergonomics) but logs a warning. S5-03 will add the digest-pin.

## References — where to look

- **Architecture:** `../phase-arch-design.md §Component 4 "@pure_edge predicates"` lines 701–746 — canonical source for the four predicate bodies, especially `route_after_attempt` and `_same_signature`. `§Process view → Scenario 1 / 2 / 3` shows each predicate firing in context. `§Edge cases` row 9 (same-signature flake) and row 13 (HITL-continue-after-flake gap).
- **Phase ADRs:** `../ADRs/0003-per-gate-retry-counter-scope.md` — defines `retry_count` semantics and same-signature short-circuit; this story is the implementation. `../ADRs/0012-pure-edge-discipline-tests-over-acl-machinery.md` — the discipline contract this story honors. `../ADRs/0005-static-schema-version-literal-pin.md` — predicates do not branch on schema version.
- **Production ADRs:** None directly — these predicates are Phase 6's contribution.
- **Source design:** `../final-design.md §Component 4` line 221 and `§Synthesis ledger row 13`.
- **High-level plan:** `../High-level-impl.md §Step 3` lines 76–98 (done criteria).
- **Existing code:** `src/codegenie/graph/edges.py` (decorator from S3-01); `src/codegenie/graph/state.py` (`VulnLedger`, `AttemptSummary`, `RagHit`, `RecipeSelection`, `LastOutcome`, `HumanDecision` fields from S1-02 / S1-03); `tools/policy/graph-thresholds.yaml` (will be shipped in S5-03 — until then, read with a sane default and log a warning).

## Goal

Land the four `@pure_edge` predicates and the `_same_signature` helper in `src/codegenie/graph/edges.py`, with full cartesian parametrization for `route_after_attempt` and one parametrized test per other predicate.

## Acceptance criteria

- [ ] `route_after_select_recipe(state) -> Literal["matched", "miss"]` returns `"matched"` iff `state.recipe_selection is not None and state.recipe_selection.matched`, else `"miss"`.
- [ ] `route_after_rag(state) -> Literal["hit", "miss"]` returns `"hit"` iff `state.rag_hit is not None and state.rag_hit.score >= rag_score_threshold` (threshold read from `tools/policy/graph-thresholds.yaml`, default 0.85), else `"miss"`.
- [ ] `route_after_attempt(state) -> Literal["passed", "retry_phase4", "retry_exhausted", "non_retryable"]` is implemented byte-equivalent to `phase-arch-design.md §Component 4` lines ~722–737 and is parametrized over the full cartesian `(passed ∈ {T,F}) × (retryable ∈ {T,F}) × (retry_count ∈ {0,1,2,3,4}) × (same_sig ∈ {T,F})` with 100% branch coverage measured by `coverage.py --branch`.
- [ ] `_same_signature(a, b)` returns `True` iff `sorted(a.failing_signals) == sorted(b.failing_signals) and a.prior_failure_summary == b.prior_failure_summary`; tested with one positive and two negative cases (signal-set differs; summary differs).
- [ ] `route_after_human(state) -> Literal["continue", "override", "abort"]` returns `state.human_decision.action`, with `assert state.human_decision is not None` (topology-guaranteed precondition documented inline).
- [ ] `test_route_after_attempt_same_signature_flake` exists and pins that two consecutive `AttemptSummary` rows with identical `sorted(failing_signals)` and identical `prior_failure_summary` route to `"non_retryable"` even when `retry_count=0 < max_attempts=3`.
- [ ] All four predicates appear in `_PURE_EDGES` after import (verified by an import-side-effect test).
- [ ] The TDD plan's red test exists, was committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest` all pass on the touched files.

## Implementation outline

1. In `src/codegenie/graph/edges.py` (already has `pure_edge` from S3-01), add the four predicates with `@pure_edge` applied. Type each return as `Literal[...]` matching the table above.
2. Add `_same_signature(a: AttemptSummary, b: AttemptSummary) -> bool` as a private helper (no decorator — it is not a routing predicate).
3. Add a thin `_load_rag_threshold() -> float` that reads `tools/policy/graph-thresholds.yaml` via PyYAML, returning `data["rag_score_threshold"]` if present, else `0.85` with a `logging.warning("graph-thresholds.yaml not found; using 0.85 default")`. Cache the result at module scope (read once). Note: digest-pin lands in S5-03.
4. For each predicate, copy the canonical body verbatim from `phase-arch-design.md §Component 4`. Do not "improve" or simplify — match the source-of-truth byte-for-byte so the property tests in S3-03 are checking the documented contract.
5. `route_after_attempt` uses `assert state.last_outcome is not None` because the topology guarantees `record_attempt` precedes it. Document the `python -O` constraint with a comment pointing to `tests/graph/test_pep_no_O_optimizations.py` (from S1-05).
6. `route_after_human` uses `assert state.human_decision is not None` for the same reason — `await_human` only routes after the operator's decision lands via `aupdate_state`.

## TDD plan — red / green / refactor

### Red

Test file: `tests/graph/test_edges.py`

```python
"""Story S3-02 — four conditional-edge predicates.

Branch-coverage gate for ADR-0003 (per-gate retry + same-signature flake) and
the four-predicate routing contract from phase-arch-design §Component 4.
"""
from __future__ import annotations

import itertools

import pytest

from codegenie.graph.edges import (
    _PURE_EDGES,
    _same_signature,
    route_after_attempt,
    route_after_human,
    route_after_rag,
    route_after_select_recipe,
)
from codegenie.graph.state import (
    AttemptSummary,
    HumanDecision,
    LastOutcome,
    RagHit,
    RecipeSelection,
    VulnLedger,
)


# --- fixtures ----------------------------------------------------------------

def _attempt(
    *,
    signals: list[str] | None = None,
    summary: str = "boom",
) -> AttemptSummary:
    return AttemptSummary(
        failing_signals=signals or ["sig-A"],
        prior_failure_summary=summary,
        # other required fields per S1-02 schema — fill from the fixture in
        # tests/graph/conftest.py (created in S1-02 follow-up)
        ...
    )


def _ledger(
    *,
    last_outcome: LastOutcome | None = None,
    retry_count: int = 0,
    max_attempts: int = 3,
    prior_attempts: list[AttemptSummary] | None = None,
    recipe_selection: RecipeSelection | None = None,
    rag_hit: RagHit | None = None,
    human_decision: HumanDecision | None = None,
) -> VulnLedger:
    return VulnLedger(
        last_outcome=last_outcome,
        retry_count=retry_count,
        max_attempts=max_attempts,
        prior_attempts=prior_attempts or [],
        recipe_selection=recipe_selection,
        rag_hit=rag_hit,
        human_decision=human_decision,
        # other required-by-extra-forbid fields from S1-02 fixture
        ...
    )


# --- route_after_select_recipe ----------------------------------------------

class TestRouteAfterSelectRecipe:
    def test_matched_when_recipe_matched_true(self) -> None:
        s = _ledger(recipe_selection=RecipeSelection(matched=True, ...))
        assert route_after_select_recipe(s) == "matched"

    def test_miss_when_recipe_matched_false(self) -> None:
        s = _ledger(recipe_selection=RecipeSelection(matched=False, ...))
        assert route_after_select_recipe(s) == "miss"

    def test_miss_when_recipe_selection_none(self) -> None:
        s = _ledger(recipe_selection=None)
        assert route_after_select_recipe(s) == "miss"


# --- route_after_rag --------------------------------------------------------

class TestRouteAfterRag:
    @pytest.mark.parametrize("score,expected", [
        (0.84, "miss"),
        (0.85, "hit"),
        (0.86, "hit"),
        (1.0, "hit"),
        (0.0, "miss"),
    ])
    def test_threshold_boundary(self, score: float, expected: str) -> None:
        s = _ledger(rag_hit=RagHit(score=score, ...))
        assert route_after_rag(s) == expected

    def test_miss_when_rag_hit_none(self) -> None:
        assert route_after_rag(_ledger(rag_hit=None)) == "miss"


# --- _same_signature --------------------------------------------------------

class TestSameSignature:
    def test_true_when_signals_and_summary_match(self) -> None:
        a = _attempt(signals=["a", "b"], summary="x")
        b = _attempt(signals=["b", "a"], summary="x")  # set-equivalent
        assert _same_signature(a, b) is True

    def test_false_when_signals_differ(self) -> None:
        a = _attempt(signals=["a"], summary="x")
        b = _attempt(signals=["a", "b"], summary="x")
        assert _same_signature(a, b) is False

    def test_false_when_summary_differs(self) -> None:
        a = _attempt(signals=["a"], summary="x")
        b = _attempt(signals=["a"], summary="y")
        assert _same_signature(a, b) is False


# --- route_after_attempt — FULL CARTESIAN ------------------------------------

@pytest.mark.parametrize("passed,retryable,retry_count,same_sig", list(itertools.product(
    [True, False],          # passed
    [True, False],          # retryable
    [0, 1, 2, 3, 4],        # retry_count (max_attempts=3 in fixture)
    [True, False],          # same_signature on prior_attempts[-2:]
)))
def test_route_after_attempt_full_cartesian(
    passed: bool,
    retryable: bool,
    retry_count: int,
    same_sig: bool,
) -> None:
    """Branch coverage gate for ADR-0003. Every combination has exactly one
    label per the canonical predicate body in phase-arch-design §Component 4."""
    prior = [
        _attempt(signals=["s1"], summary="boom"),
        _attempt(signals=["s1"] if same_sig else ["s2"],
                 summary="boom" if same_sig else "different"),
    ]
    s = _ledger(
        last_outcome=LastOutcome(passed=passed, retryable=retryable, ...),
        retry_count=retry_count,
        max_attempts=3,
        prior_attempts=prior,
    )

    result = route_after_attempt(s)

    # Expected label (mirror of canonical predicate):
    if passed:
        expected = "passed"
    elif not retryable:
        expected = "non_retryable"
    elif same_sig:
        expected = "non_retryable"
    elif retry_count >= 3:
        expected = "retry_exhausted"
    else:
        expected = "retry_phase4"

    assert result == expected


def test_route_after_attempt_same_signature_flake() -> None:
    """ADR-0003: two consecutive identical failure signatures route to
    non_retryable even when retry_count=0 < max_attempts=3."""
    sig = ["yarn-audit-CVE-2024-X"]
    prior = [
        _attempt(signals=sig, summary="yarn audit failed"),
        _attempt(signals=sig, summary="yarn audit failed"),
    ]
    s = _ledger(
        last_outcome=LastOutcome(passed=False, retryable=True, ...),
        retry_count=0,
        max_attempts=3,
        prior_attempts=prior,
    )
    assert route_after_attempt(s) == "non_retryable"


# --- route_after_human ------------------------------------------------------

class TestRouteAfterHuman:
    @pytest.mark.parametrize("action", ["continue", "override", "abort"])
    def test_passthrough(self, action: str) -> None:
        s = _ledger(human_decision=HumanDecision(action=action, ...))
        assert route_after_human(s) == action


# --- registration -----------------------------------------------------------

def test_all_four_predicates_registered() -> None:
    names = {f.__name__ for f in _PURE_EDGES}
    assert {
        "route_after_select_recipe",
        "route_after_rag",
        "route_after_attempt",
        "route_after_human",
    }.issubset(names)
```

### Green

Smallest shape that passes:

```python
# src/codegenie/graph/edges.py (excerpt; pure_edge from S3-01 already exists above)

from typing import Literal
from codegenie.graph.state import AttemptSummary, VulnLedger
# threshold loader omitted; see _load_rag_threshold()

_RAG_SCORE_THRESHOLD: float = _load_rag_threshold()


@pure_edge
def route_after_select_recipe(state: VulnLedger) -> Literal["matched", "miss"]:
    if state.recipe_selection is not None and state.recipe_selection.matched:
        return "matched"
    return "miss"


@pure_edge
def route_after_rag(state: VulnLedger) -> Literal["hit", "miss"]:
    if state.rag_hit is not None and state.rag_hit.score >= _RAG_SCORE_THRESHOLD:
        return "hit"
    return "miss"


def _same_signature(a: AttemptSummary, b: AttemptSummary) -> bool:
    return (sorted(a.failing_signals) == sorted(b.failing_signals)
            and a.prior_failure_summary == b.prior_failure_summary)


@pure_edge
def route_after_attempt(
    state: VulnLedger,
) -> Literal["passed", "retry_phase4", "retry_exhausted", "non_retryable"]:
    assert state.last_outcome is not None  # topology precondition; do not run -O
    if state.last_outcome.passed:
        return "passed"
    if not state.last_outcome.retryable:
        return "non_retryable"
    if (len(state.prior_attempts) >= 2
            and _same_signature(state.prior_attempts[-1], state.prior_attempts[-2])):
        return "non_retryable"
    if state.retry_count >= state.max_attempts:
        return "retry_exhausted"
    return "retry_phase4"


@pure_edge
def route_after_human(state: VulnLedger) -> Literal["continue", "override", "abort"]:
    assert state.human_decision is not None  # topology precondition
    return state.human_decision.action
```

### Refactor

- Replace `...` placeholders in the test fixtures with the actual `VulnLedger` / `AttemptSummary` / `LastOutcome` / `RagHit` / `RecipeSelection` / `HumanDecision` defaults — these come from the shared fixture file `tests/graph/conftest.py` (extend if necessary; do not inline kw-args repeatedly).
- Add docstrings to each predicate citing ADR-0003 (for `route_after_attempt`) and ADR-0012 (for the discipline).
- Add a module-scope `__all__` listing only the four predicates (helps S3-03 import discoverability).
- Run `coverage run --branch -m pytest tests/graph/test_edges.py && coverage report --include='src/codegenie/graph/edges.py' --show-missing` and confirm 100% branch coverage on the file.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/graph/edges.py` | Add the four predicates, `_same_signature`, and `_load_rag_threshold`. |
| `tests/graph/test_edges.py` | Red test, full cartesian, same-sig flake. |
| `tests/graph/conftest.py` | (Extend if needed) shared `VulnLedger` / `AttemptSummary` factories. |
| `tools/policy/graph-thresholds.yaml` | **Out of scope** — created in S5-03. For this story, the loader tolerates absence. |

## Out of scope

- Hypothesis property tests for determinism + label-projection invariance — S3-03.
- Digest-pinning of `graph-thresholds.yaml` — S5-03.
- Wiring the predicates into the `StateGraph` topology via `add_conditional_edges` — S5-01.
- HITL same-sig-flake "continue silently routes to non_retryable" gap — documented in `phase-arch-design.md §Edge cases row 13`; the test for it lives in S7-04. Do **not** add the workaround here.
- Modifying `route_after_attempt`'s body away from the canonical source — even a "clearer" refactor risks breaking the byte-identity assumption that S3-03's property test relies on.

## Notes for the implementer

1. **Match the canonical source byte-for-byte.** The decision tree in `route_after_attempt` (passed → non_retryable → same_signature short-circuit → retry_exhausted → retry_phase4) is ordered for ADR-0003 reasons. Reordering the branches *will* produce a different label for some cartesian combination even though the boolean logic looks equivalent. Do not "improve" the order.
2. The cartesian has 80 cases (`2×2×5×2`). pytest's `parametrize` runs them in well under a second; no need to subset.
3. `_same_signature` uses `sorted(failing_signals)` so a future Phase 5 contract that returns signals in different orderings does not break the detector. Don't change to `set(...)` — order-sensitivity is fine; `sorted` is canonical and stable.
4. The `assert state.last_outcome is not None` in `route_after_attempt` is **load-bearing for `python -O` compliance**. S1-05 ships `test_pep_no_O_optimizations.py`. Do not "fix" the assertion to a raise — `phase-arch-design.md §Component 4` line 746 explicitly chose `assert` here because it is a programmer-error precondition, not a runtime condition.
5. `_load_rag_threshold()` reads the YAML at import time. When `tools/policy/graph-thresholds.yaml` ships in S5-03, the digest-pin gate runs there, not here. Do not add a `BLAKE3` check to this story.
6. The `Literal[...]` return types are checked by `mypy --strict`; if you change a return-string value (e.g. `"non-retryable"` with a hyphen), mypy will catch the typo at PR time, but the LangGraph edge-mapping in S5-01 will silently route to the wrong node at runtime. Names are part of the contract — change only via an ADR amendment.
