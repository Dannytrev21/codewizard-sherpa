# Story S3-03 — Hypothesis property tests: determinism + label-projection invariance

**Step:** Step 3 — Ship `@pure_edge` decorator + the four conditional-edge predicates + property tests
**Status:** Ready
**Effort:** M
**Depends on:** S3-02 (the four predicates + `_PURE_EDGES` registry), S1-02 (`VulnLedger` model)
**ADRs honored:** ADR-0012 (`@pure_edge` discipline — projection tests over AST machinery), ADR-0003 (per-gate retry counter semantics — strategy must generate retry-relevant states), ADR-0002 (`VulnLedger` model contract — strategies must produce extra="forbid"-valid instances)

## Context

S3-01 added the static AST gate; S3-02 added the predicate bodies + cartesian unit tests. This story adds the **behavior-level** purity guarantees that ADR-0012 calls out as load-bearing:

1. **Determinism (referential transparency).** For every generated `VulnLedger` `s`, `predicate(s) == predicate(s)` over repeated calls. This rules out a class of subtle bugs where a predicate accidentally consults `time.time()`, an env var, or a process-global cache.
2. **Label-projection invariance.** For every predicate `p` and every generated `s`, permuting fields the predicate does **not** consume — e.g., `AttemptSummary.created_at`, `events[*].at`, `last_node`, `chain_head` — leaves `p(s)` unchanged. This closes `critique.md security-attack-4` ("synthetic state property tests do not exercise production timestamp-bearing states") by directly generating timestamp permutations into the strategy.

Both gates run via `hypothesis` over 10,000 examples per predicate per CI run. The strategies for `VulnLedger` (and its nested types `AttemptSummary`, `LastOutcome`, `RagHit`, `RecipeSelection`, `HumanDecision`) are **hand-written** in `tests/graph/strategies.py`. Auto-derivation via `hypothesis-pydantic` was considered and rejected (`High-level-impl.md §Step 3 Risks`): generated values for non-leaf Pydantic types drift silently with minor Pydantic version bumps, and the strategy needs to control retry-shape distributions to actually exercise `route_after_attempt`'s branches at non-trivial densities.

The projection-invariance check is implemented per-predicate by a `NON_CONSUMED_FIELDS` map declaring which fields each predicate *ignores*. Tests then mutate those fields and re-evaluate.

## References — where to look

- **Architecture:** `../phase-arch-design.md §Component 4 "@pure_edge predicates"` line 720 — declares `test_edge_label_depends_only_on_projection.py` as the closure of `critique.md security-attack-4`. `§Testing strategy` lines ~1170–1180 — Hypothesis-based property tests in Layer 1. `§Data model` lines ~932–945 — the `Reads:` annotations on each field tell you which predicate consumes what (prose only, but informative).
- **Phase ADRs:** `../ADRs/0012-pure-edge-discipline-tests-over-acl-machinery.md` — explicitly cites these tests as the *behavior-verifying* substitute for AST machinery; `../ADRs/0002-vuln-ledger-frozen-false-with-runtime-mutation-hook.md` — strategies must produce instances `Pydantic.model_validate` accepts.
- **Production ADRs:** None directly.
- **Source design:** `../final-design.md §Component 4` (line 221), `§Goal 19 "Tests verify intent, not syntax"` — the rationale tier.
- **High-level plan:** `../High-level-impl.md §Step 3` lines 88–89 (done criteria for both property tests), line 98 (strategy drift risk note).
- **Existing code:** `src/codegenie/graph/edges.py` (S3-01 + S3-02 — `_PURE_EDGES` registry, the four predicates, `_same_signature` helper); `src/codegenie/graph/state.py` (S1-02 — `VulnLedger` and nested types).

## Goal

Land Hypothesis strategies for `VulnLedger` and two property-test files that assert (a) every predicate is deterministic across repeat calls and (b) every predicate's label is invariant under permutation of its non-consumed fields, at 10,000 examples each per CI run.

## Acceptance criteria

- [ ] `tests/graph/strategies.py` defines `vuln_ledger_strategy()`, `attempt_summary_strategy()`, `last_outcome_strategy()`, `rag_hit_strategy()`, `recipe_selection_strategy()`, `human_decision_strategy()`, and a `vuln_ledger_with_retry_shape_strategy(*, force_passed=..., force_retry_count_at_max=...)` variant that biases generation toward retry-relevant branches.
- [ ] `tests/graph/test_edges_determinism.py` iterates `_PURE_EDGES`, runs 10,000 examples per predicate, and asserts `predicate(s) == predicate(s)` on every generated `s`. Settings: `@settings(max_examples=10_000, deadline=None, derandomize=False)`.
- [ ] `tests/graph/test_edge_label_depends_only_on_projection.py` defines a `NON_CONSUMED_FIELDS: dict[str, set[str]]` map listing per-predicate fields the predicate does **not** consume (including nested `AttemptSummary.created_at`, `events[*].at`, `last_node`, `chain_head`). For each predicate it generates one `s`, computes `label = predicate(s)`, then generates a permuted `s'` differing only in non-consumed fields, and asserts `predicate(s') == label`. At least 10,000 examples per predicate.
- [ ] The projection test exercises **timestamp permutation** explicitly — at least one strategy permutes `AttemptSummary.created_at` and `events[*].at` to arbitrary `datetime` values (closes `critique.md security-attack-4`).
- [ ] Strategy golden fixture: `tests/graph/test_strategies_golden.py` pins one representative `VulnLedger` instance generated with `random.seed(0)` (via Hypothesis `derandomize=True` + a fixed `derandomize_seed`) and asserts its JSON shape against `tests/graph/golden/vuln_ledger_strategy_sample.json` — Pydantic-minor-bump canary per `High-level-impl.md §Step 3 Risks`.
- [ ] CI runtime budget: both property test files together complete in < 60s on a developer laptop (10k examples × 4 predicates × ~tens of μs per call).
- [ ] The TDD plan's red test exists, was committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest` all pass on the touched files.

## Implementation outline

1. Create `tests/graph/strategies.py`:
   - `from hypothesis import strategies as st`
   - Build leaf strategies first: `signal_strategy = st.text(min_size=1, max_size=64)`, `summary_strategy = st.text(max_size=512)`, `score_strategy = st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)`, `datetime_strategy = st.datetimes(min_value=..., max_value=...).map(lambda d: d.replace(tzinfo=timezone.utc))`.
   - Compose into `attempt_summary_strategy()`, `last_outcome_strategy()`, etc., using `st.builds(AttemptSummary, ...)` so Pydantic `model_validate` runs at draw time.
   - `vuln_ledger_strategy()` composes the nested types.
   - `vuln_ledger_with_retry_shape_strategy(*, force_passed=None, force_retry_count_at_max=False)` is a thin wrapper that overrides `last_outcome.passed` and `retry_count == max_attempts` to bias toward `route_after_attempt`'s less-frequent branches.
2. Create `tests/graph/test_edges_determinism.py`:
   - One `@pytest.mark.parametrize("predicate", _PURE_EDGES)` test.
   - Body uses `@given(state=vuln_ledger_strategy())` + `@settings(max_examples=10_000, deadline=None)`.
   - `@pytest.mark.hypothesis_slow` or similar marker so CI can subset locally vs full.
   - Skip `route_after_attempt` / `route_after_human` for ledgers where their topology precondition (`assert ... is not None`) doesn't hold — use `assume(state.last_outcome is not None)` / `assume(state.human_decision is not None)`.
3. Create `tests/graph/test_edge_label_depends_only_on_projection.py`:
   - `NON_CONSUMED_FIELDS = {"route_after_select_recipe": {"rag_hit", "last_outcome", "retry_count", ..., "events", "chain_head", "last_node"}, "route_after_rag": {...}, ...}`. Build this map by hand from `phase-arch-design.md §Data model`'s `Reads:` annotations.
   - For each predicate, use `@given(state=vuln_ledger_strategy(), perturbations=...)`. The `perturbations` strategy generates new values for the non-consumed fields. The test deepcopies `state`, overwrites the non-consumed fields with the perturbation values, and asserts the label is invariant.
   - Add a dedicated test `test_timestamp_permutation_invariance` that explicitly fuzzes `AttemptSummary.created_at` and any `at`-fields on event-like structures — written out by hand to make the security-attack-4 closure obvious to reviewers.
4. Create `tests/graph/test_strategies_golden.py`:
   - `@given(state=vuln_ledger_strategy()) @settings(derandomize=True, max_examples=1)` draws one canonical example.
   - Serialize via `state.model_dump_json(indent=2, by_alias=True)` and compare against `tests/graph/golden/vuln_ledger_strategy_sample.json`. Update via `--update-golden` pytest flag (or pytest-snapshot conventions; pick one and document in `tests/graph/README.md`).

## TDD plan — red / green / refactor

### Red

Test file: `tests/graph/test_edges_determinism.py`

```python
"""Story S3-03 — referential transparency of every @pure_edge predicate.

Pins ADR-0012 (behavior-level purity check; complements the AST decorator).
"""
from __future__ import annotations

from collections.abc import Callable

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from codegenie.graph.edges import _PURE_EDGES
from codegenie.graph.state import VulnLedger
from tests.graph.strategies import vuln_ledger_strategy


@pytest.mark.parametrize("predicate", _PURE_EDGES, ids=lambda f: f.__name__)
@given(state=vuln_ledger_strategy())
@settings(
    max_examples=10_000,
    deadline=None,
    derandomize=False,
    suppress_health_check=[HealthCheck.too_slow],
)
def test_predicate_is_deterministic(
    predicate: Callable[[VulnLedger], str],
    state: VulnLedger,
) -> None:
    """f(s) == f(s) for every generated VulnLedger. Catches any sneaky
    consultation of time/random/env-var that the AST decorator misses."""
    # honor topology preconditions on assertions inside predicates
    if predicate.__name__ == "route_after_attempt":
        assume(state.last_outcome is not None)
    if predicate.__name__ == "route_after_human":
        assume(state.human_decision is not None)

    first = predicate(state)
    second = predicate(state)
    assert first == second, f"{predicate.__name__} non-deterministic: {first!r} != {second!r}"
```

Test file: `tests/graph/test_edge_label_depends_only_on_projection.py`

```python
"""Story S3-03 — label-projection invariance.

Closes critique security-attack-4: production states carry timestamps and
audit-chain heads; the routing label must not depend on them.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from codegenie.graph.edges import (
    route_after_attempt,
    route_after_human,
    route_after_rag,
    route_after_select_recipe,
)
from codegenie.graph.state import VulnLedger
from tests.graph.strategies import (
    attempt_summary_strategy,
    datetime_strategy,
    vuln_ledger_strategy,
)


# Fields each predicate does NOT consume. Built by hand from
# phase-arch-design §Data model "Reads:" annotations.
NON_CONSUMED_FIELDS: dict[str, set[str]] = {
    "route_after_select_recipe": {
        "rag_hit", "last_outcome", "retry_count", "max_attempts",
        "prior_attempts", "human_decision", "events", "chain_head",
        "last_node", "patch", "last_engine",
    },
    "route_after_rag": {
        "recipe_selection", "last_outcome", "retry_count", "max_attempts",
        "prior_attempts", "human_decision", "events", "chain_head",
        "last_node", "patch", "last_engine",
    },
    "route_after_attempt": {
        "recipe_selection", "rag_hit", "human_decision", "events",
        "chain_head", "last_node", "patch", "last_engine",
        # NOTE: AttemptSummary.created_at is non-consumed (per _same_signature);
        # see test_timestamp_permutation_invariance for explicit coverage.
    },
    "route_after_human": {
        "recipe_selection", "rag_hit", "last_outcome", "retry_count",
        "max_attempts", "prior_attempts", "events", "chain_head",
        "last_node", "patch", "last_engine",
    },
}


@pytest.mark.parametrize("predicate", [
    route_after_select_recipe,
    route_after_rag,
    route_after_attempt,
    route_after_human,
], ids=lambda f: f.__name__)
@given(
    base=vuln_ledger_strategy(),
    perturb=vuln_ledger_strategy(),
)
@settings(max_examples=10_000, deadline=None)
def test_label_invariant_under_non_consumed_field_permutation(
    predicate,
    base: VulnLedger,
    perturb: VulnLedger,
) -> None:
    if predicate.__name__ == "route_after_attempt":
        assume(base.last_outcome is not None)
    if predicate.__name__ == "route_after_human":
        assume(base.human_decision is not None)

    non_consumed = NON_CONSUMED_FIELDS[predicate.__name__]
    # Build a new ledger that copies `base`'s consumed fields and `perturb`'s
    # non-consumed fields.
    overrides = {f: getattr(perturb, f) for f in non_consumed}
    permuted = base.model_copy(update=overrides)

    # topology precondition may have changed after permutation; re-assume
    if predicate.__name__ == "route_after_attempt":
        assume(permuted.last_outcome is not None)
    if predicate.__name__ == "route_after_human":
        assume(permuted.human_decision is not None)

    assert predicate(base) == predicate(permuted), (
        f"{predicate.__name__} label depends on a non-consumed field; "
        f"base={base!r} permuted={permuted!r}"
    )


@given(
    base=vuln_ledger_strategy(),
    new_created_at=datetime_strategy,
    new_chain_head=st.binary(min_size=32, max_size=32),
)
@settings(max_examples=10_000, deadline=None)
def test_timestamp_permutation_invariance(
    base: VulnLedger,
    new_created_at: datetime,
    new_chain_head: bytes,
) -> None:
    """Closes critique security-attack-4: production states carry timestamps;
    no predicate label may depend on them."""
    assume(len(base.prior_attempts) >= 1)
    assume(base.last_outcome is not None)
    assume(base.human_decision is not None)

    permuted_prior = [
        a.model_copy(update={"created_at": new_created_at})
        for a in base.prior_attempts
    ]
    permuted = base.model_copy(update={
        "prior_attempts": permuted_prior,
        "chain_head": new_chain_head,
    })

    for predicate in (route_after_select_recipe, route_after_rag,
                      route_after_attempt, route_after_human):
        assert predicate(base) == predicate(permuted), (
            f"{predicate.__name__} label varies under timestamp/chain_head permutation"
        )
```

### Green

Smallest shape that passes:

1. Implement `tests/graph/strategies.py` per the implementation outline — `st.builds(...)` for every nested Pydantic type, top-level `vuln_ledger_strategy()` composes them. Predicate bodies from S3-02 are already pure, so once the strategies produce valid ledgers, both tests pass on first run.
2. Build the `NON_CONSUMED_FIELDS` map carefully — the only reading required is `phase-arch-design.md §Data model` (lines ~920–950). Get this map *right* the first time; a missed entry causes false-positive failures, and a spurious entry causes silent under-coverage (the test still passes but doesn't actually verify the invariant for that field). Cross-check against the predicate bodies in S3-02.

### Refactor

- Add `derandomize=False` so Hypothesis explores aggressively in CI; locally, `HYPOTHESIS_PROFILE=ci` (configured in `tests/conftest.py`) caps `max_examples` at 200 for fast feedback.
- Document each strategy with a docstring explaining the chosen value distribution (especially the retry-shape biases).
- Add a `@pytest.mark.slow` marker so the merge-queue runs 10k but developer pre-commit runs the cheap 200-example profile.
- Move the `NON_CONSUMED_FIELDS` map into a dataclass or pinned-frozenset and add a unit test that asserts every key in `_PURE_EDGES.__name__` has an entry — fail-loud when a predicate is added without updating the map.

## Files to touch

| Path | Why |
|---|---|
| `tests/graph/strategies.py` | New module: Hypothesis strategies for `VulnLedger` and nested types. |
| `tests/graph/test_edges_determinism.py` | New: 10k-example determinism property test per predicate. |
| `tests/graph/test_edge_label_depends_only_on_projection.py` | New: 10k-example projection-invariance test per predicate + explicit timestamp permutation test. |
| `tests/graph/test_strategies_golden.py` | New: pin one canonical-shape generated example to catch Pydantic-version drift. |
| `tests/graph/golden/vuln_ledger_strategy_sample.json` | New: golden fixture from the strategy. |
| `tests/conftest.py` | Add `hypothesis` profiles (`dev` 200 examples, `ci` 10_000 examples). |

## Out of scope

- Strategies for any non-`VulnLedger` Pydantic model in the codebase (Phase 5's `RetryLedger`, Phase 3's `Advisory`, etc.) — those have their own test files.
- Property tests on nodes — node tests are S4-01 onward (mock-based, not property-based).
- The "label depends only on a state projection" *AST* check — explicitly rejected by ADR-0012; this story is the behavior-level substitute.
- Updating `phase-arch-design.md §Data model`'s `Reads:` annotations — they are prose-only documentation per ADR-0012 and not load-bearing.
- A `hypothesis-pydantic` auto-derivation pass — rejected per `High-level-impl.md §Step 3 Risks` ("strategies for nested Pydantic models drift").

## Notes for the implementer

1. **The `NON_CONSUMED_FIELDS` map is the load-bearing artifact.** Get it right by reading every predicate body in `edges.py` (from S3-02) and asking "which `state.X` accesses appear in this function?" Anything not accessed goes in the non-consumed set. Cross-check against `phase-arch-design.md §Data model`'s prose `Reads:` annotations — but the source of truth is the code, not the prose.
2. **Hand-written strategies, not auto-derived.** `hypothesis-pydantic` looks tempting but breaks silently on minor Pydantic version changes. The strategy golden fixture (`test_strategies_golden.py`) is the canary — if a Pydantic bump changes a default, the golden diff fails loudly.
3. **`assume(...)` discards examples that violate topology preconditions.** `route_after_attempt` and `route_after_human` have `assert state.X is not None` preconditions; without `assume`, the property test would fire `AssertionError` on every example where the precondition doesn't hold. Hypothesis's `HealthCheck.filter_too_much` may complain if `assume` rejects more than ~33% — bias the strategy to satisfy the precondition (e.g., `vuln_ledger_strategy()` defaults `last_outcome` to non-None 80% of the time).
4. **CI runtime budget is 60s for both files.** 10k examples × 4 predicates ≈ 40k predicate calls, each in the microsecond range. The strategy is the bottleneck (Pydantic validation per draw). If runtime exceeds 60s, *first* profile to identify the bottleneck — don't blindly lower `max_examples` without surfacing the tradeoff in a follow-up story.
5. **Do not rely on `hypothesis.strategies.from_type(VulnLedger)`.** It works for trivial Pydantic models but fails or produces uselessly degenerate examples for nested `Optional[...]` + `Literal[...]` shapes. Hand-written is the only reliable path.
6. **The projection-invariance test handles `route_after_attempt` carefully.** Per ADR-0003 the predicate consumes `prior_attempts[-2:]` for the same-signature check, but `AttemptSummary.created_at` is non-consumed (the helper compares `failing_signals` and `prior_failure_summary` only). The timestamp-permutation test explicitly exercises this — *do not* add `prior_attempts` to `route_after_attempt`'s non-consumed set; permute the *fields inside* the `AttemptSummary` items instead.
