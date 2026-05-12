# Story S5-01 — `RagLlmEngine` skeleton + `applies()` fallback-only + DI wiring

**Step:** Step 5 — Compose `RagLlmEngine` + three-tier `apply()`
**Status:** Ready
**Effort:** M
**Depends on:** S3-06 (`LeafLlmAgent` shipped — both implementations + `LeafAgentNode` wrap), S4-04 (`SolvedExampleStore` with digest filter), S4-05 (`QueryKeyCache`), S1-08 (`Recipe.engine` Literal extension + registry seam)
**ADRs honored:** ADR-P4-001, ADR-P4-003, ADR-P4-004, ADR-P4-014, ADR-P4-015, Phase-3 ADR-0001 (`RecipeEngine` ABC contract — unchanged)

## Context
Phase 3 froze a `RecipeEngine` ABC with three sibling engines registered via decorator (`@register_recipe_engine`). Phase 4's LLM fallback ships as the third such engine — `RagLlmEngine` — composing seven collaborators (`store`, `cache`, `embed`, `leaf`, `loader`, `validator`, `guard`) plus two threshold parameters (`tau_hit=0.86`, `tau_few=0.72`). This story lands the class skeleton, the constructor's seven-collaborator dependency injection, the engine-registry registration in `src/codegenie/recipes/engines/__init__.py`, and — critically — the `applies()` rule that returns `True` **only** when `RecipeSelection.diagnostics.previous_engines` carries a Phase-3 fallback `reason ∈ {catalog_miss, range_break, peer_dep_conflict, no_engine, unsupported_dialect}`. Never on a cold start. This single discipline closes critic §B.1 (the synth would otherwise let `rag_llm` be picked first on greenfield runs and silently spend money). `apply()` is a stub (`raise NotImplementedError`) — the five-helper body lands in S5-02.

## References — where to look
- **Architecture:** `../phase-arch-design.md §Component design / 1. RagLlmEngine` — public interface, the seven-collaborator constructor, the `applies()` rule with the five fallback reasons, the "never True from a cold start" invariant; `§Logical view — components and relations` — `RagLlmEngine` as third sibling under `RecipeEngine`; `§Process view — runtime` step 2 (`SEL → ENG.applies → True (only on fallback reason)`).
- **Phase ADRs:**
  - `../ADRs/0001-recipe-engine-literal-extends-with-rag-llm.md` — ADR-P4-001 — `Recipe.engine` Literal admits `"rag_llm"`; `RecipeSelector.engines = [Ncu, OpenRewriteStub, RagLlm]`; `applies()` returns True only on Phase-3 fallback reasons.
  - `../ADRs/0003-plan-envelope-kind-and-target-files-allowlist.md` — ADR-P4-003 — `Plan` envelope shape the engine returns. (Body lands in S5-02 but `apply()`'s return type references it.)
  - `../ADRs/0004-leaf-llm-agent-protocol-os-tiered.md` — ADR-P4-004 — `LeafLlmAgent` is the injected Protocol, not a concrete class; `available()` cascades into engine readiness.
  - `../ADRs/0014-langgraph-leaf-agent-node-minimal-wrap.md` — ADR-P4-014 — `LeafAgentNode` is the swap point; `RagLlmEngine` constructor receives the `LeafLlmAgent` directly, not the node (the node is internal to the leaf-side wrap).
  - `../ADRs/0015-solved-example-schema-task-class-generic.md` — ADR-P4-015 — `SolvedExampleStore` reads filter by `task_class="vuln"` for Phase 4; the engine threads this default.
- **Production ADRs:**
  - `../../../production/adrs/0011-recipe-first-rag-llm-fallback-planning.md` — the recipe-first/RAG-then-LLM decision chain Phase 4 realises.
  - `../../../production/adrs/0028-task-class-introduction-order.md` — Phase 7/15 extend the same `applies()` rule; this story's discipline ("only on fallback reason") is the precedent.
- **Source design:** `../final-design.md §Component 1 — RagLlmEngine` — five-helper shape and the `applies()` rule verbatim. `§Synthesis ledger row "Engine ABC vs sibling vs router"` — the third-engine pick.
- **High-level impl:** `../High-level-impl.md §Step 5` — the constructor's seven args + `tau_hit=0.86, tau_few=0.72` defaults.
- **Existing code:** `src/codegenie/recipes/engines/__init__.py` (Phase 3 — engine registry; this story adds one line registering `RagLlmEngine`); `src/codegenie/recipes/contract.py` (Phase 3 — `RecipeEngine` ABC; do not edit); `src/codegenie/recipes/selector.py` (Phase 3 — iterates registered engines; engines added by decorator surface automatically).

## Goal
Ship the `RagLlmEngine` class skeleton, register it in the engine registry, and enforce that `applies()` returns `True` only when a prior Phase-3 engine emitted one of the five fallback reasons — never from a cold-start selection.

## Acceptance criteria
- [ ] `src/codegenie/recipes/engines/rag_llm.py` defines `class RagLlmEngine(RecipeEngine)` decorated with `@register_recipe_engine` from the Phase 3 registry.
- [ ] Constructor signature is exactly: `__init__(self, store: SolvedExampleStore, cache: QueryKeyCache, embed: EmbeddingProvider, leaf: LeafLlmAgent, loader: PromptLoader, validator: OutputValidator, guard: LlmInvocationGuard, *, tau_hit: float = 0.86, tau_few: float = 0.72) -> None`. The two thresholds are keyword-only; the seven collaborators are positional-or-keyword and stored as attributes verbatim (no wrapping, no copying).
- [ ] `available(self) -> bool` returns `self.leaf.available() and self.store.opens_cleanly()` — composing the collaborators' own readiness checks (`§Component 1 internal-design`); does **not** call `Anthropic` or open chromadb.
- [ ] `applies(self, advisory: Advisory, repo_ctx: RepoContextView) -> bool` returns `True` **iff** `RecipeSelection.diagnostics.previous_engines` (threaded into `applies` via `repo_ctx`'s selector-state field) contains at least one `EngineAttempt` whose `reason` is in the closed set `{"catalog_miss","range_break","peer_dep_conflict","no_engine","unsupported_dialect"}`. Returns `False` on a cold start (empty `previous_engines`), on a run that produced a non-fallback reason, and on a run where the only prior engine succeeded.
- [ ] `apply(self, recipe: Recipe, repo: Path, ctx: ApplyContext) -> RecipeApplication` exists as a method stub raising `NotImplementedError("S5-02 lands the three-tier body")`. The signature matches the Phase 3 `RecipeEngine` ABC verbatim (mypy strict catches any drift).
- [ ] `src/codegenie/recipes/engines/__init__.py` imports `rag_llm` so its decorator fires at module load; the registry now exposes three engines (`ncu`, `openrewrite`, `rag_llm`) — a sibling Phase 3 test (`tests/unit/recipes/test_engine_registry_lists_three.py` lands here) asserts the count and the ordered names.
- [ ] `tests/unit/recipes/engines/test_rag_llm_applies_only_on_fallback_reason.py`:
  - `test_cold_start_returns_false` — `RecipeSelection.diagnostics.previous_engines = []` → `applies() is False`.
  - `test_each_fallback_reason_returns_true` — parametrised over all five reasons; each independently makes `applies() is True`.
  - `test_non_fallback_reason_returns_false` — e.g. `previous_engines=[EngineAttempt(engine="ncu", reason="ncu_succeeded", ...)]` → `applies() is False` (a successful prior run is not a fallback).
  - `test_unknown_reason_string_returns_false` — `reason="some_future_reason"` (string not in the closed set) → `applies() is False`; the engine refuses to fall back on reasons it doesn't understand.
- [ ] `tests/unit/recipes/engines/test_rag_llm_constructor_di.py` builds the engine with seven `Mock(spec=...)` collaborators and asserts each is stored on the named attribute (`engine.store is mock_store`, etc.); asserts `tau_hit == 0.86` and `tau_few == 0.72` defaults; asserts ctor accepts keyword overrides for the thresholds.
- [ ] `tests/unit/recipes/engines/test_rag_llm_available_composes_collaborators.py` — when `leaf.available() is False`, engine's `available()` is `False`; when `store.opens_cleanly() is False`, engine's `available()` is `False`; both `True` → engine `True`.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict src/codegenie/recipes/engines/rag_llm.py`, and `pytest tests/unit/recipes/engines/` all pass.

## Implementation outline
1. Read `src/codegenie/recipes/contract.py` (Phase 3 `RecipeEngine` ABC) and `src/codegenie/recipes/engines/__init__.py` (registry mechanics). Copy the existing `NcuEngine` / `OpenRewriteStubEngine` registration shape verbatim — do not invent.
2. Create `src/codegenie/recipes/engines/rag_llm.py`. Imports:
   - `from codegenie.recipes.contract import RecipeEngine, RecipeApplication, ApplyContext, Recipe`
   - `from codegenie.recipes.engines import register_recipe_engine` (Phase 1's seam)
   - `from codegenie.rag.store import SolvedExampleStore` and `from codegenie.rag.query_key_cache import QueryKeyCache`
   - `from codegenie.rag.contract import EmbeddingProvider`
   - `from codegenie.llm.contract import LeafLlmAgent`
   - `from codegenie.llm.prompt_loader import PromptLoader`
   - `from codegenie.llm.output_validator import OutputValidator`
   - `from codegenie.llm.guard import LlmInvocationGuard`
   - `from codegenie.advisory.models import Advisory` and the `RepoContextView` type from Phase 2
   - Do **not** import `anthropic`, `chromadb`, `sentence_transformers`, or `langgraph` here — fence-CI from Step 1 fails the PR if any leak. The seven Protocols / ABCs are the only allowed surface.
3. Declare `@register_recipe_engine` decorating `class RagLlmEngine(RecipeEngine)`. Store the seven collaborators as `self.store`, `self.cache`, `self.embed`, `self.leaf`, `self.loader`, `self.validator`, `self.guard`. Store thresholds as `self.tau_hit`, `self.tau_few`. Add a class-level `name: ClassVar[Literal["rag_llm"]] = "rag_llm"` so the registry can look it up.
4. Implement `available()` as the two-line composition. No I/O beyond what the injected collaborators do.
5. Implement `applies()`. Pull `previous_engines` off the `RepoContextView` (or whatever Phase-3 selector-state field carries it — match the existing `NcuEngine.applies` access pattern). Define the closed set `_FALLBACK_REASONS: Final[frozenset[str]] = frozenset({"catalog_miss","range_break","peer_dep_conflict","no_engine","unsupported_dialect"})` as a module-level constant. Return `any(att.reason in _FALLBACK_REASONS for att in previous_engines)`.
6. Stub `apply()` raising `NotImplementedError` with a TODO referencing S5-02.
7. Edit `src/codegenie/recipes/engines/__init__.py` to add `from . import rag_llm  # noqa: F401` after the existing `ncu` / `openrewrite` imports — order matters for the registry insertion order asserted in `test_engine_registry_lists_three.py`.
8. Write the four test files. Use `pytest.mark.parametrize` for the five reasons. Mock collaborators with `unittest.mock.Mock(spec=...)` so signature drift surfaces.
9. Run ruff / ruff format / mypy strict / pytest.

## TDD plan — red / green / refactor

### Red
`tests/unit/recipes/engines/test_rag_llm_applies_only_on_fallback_reason.py`
```python
import pytest
from unittest.mock import Mock
from codegenie.recipes.engines.rag_llm import RagLlmEngine
from codegenie.recipes.contract import EngineAttempt

FALLBACK_REASONS = ["catalog_miss","range_break","peer_dep_conflict","no_engine","unsupported_dialect"]

def _engine() -> RagLlmEngine:
    return RagLlmEngine(
        store=Mock(), cache=Mock(), embed=Mock(), leaf=Mock(),
        loader=Mock(), validator=Mock(), guard=Mock(),
    )

def test_cold_start_returns_false():
    eng = _engine()
    advisory, repo_ctx = Mock(), Mock(previous_engines=[])
    assert eng.applies(advisory, repo_ctx) is False

@pytest.mark.parametrize("reason", FALLBACK_REASONS)
def test_each_fallback_reason_returns_true(reason: str) -> None:
    eng = _engine()
    repo_ctx = Mock(previous_engines=[EngineAttempt(engine="ncu", reason=reason, duration_ms=10)])
    assert eng.applies(Mock(), repo_ctx) is True

def test_non_fallback_reason_returns_false():
    eng = _engine()
    repo_ctx = Mock(previous_engines=[EngineAttempt(engine="ncu", reason="ncu_succeeded", duration_ms=10)])
    assert eng.applies(Mock(), repo_ctx) is False

def test_unknown_reason_string_returns_false():
    eng = _engine()
    repo_ctx = Mock(previous_engines=[EngineAttempt(engine="ncu", reason="some_future_reason", duration_ms=10)])
    assert eng.applies(Mock(), repo_ctx) is False
```

`tests/unit/recipes/engines/test_rag_llm_constructor_di.py`
```python
def test_seven_collaborators_stored_verbatim_and_thresholds_defaulted():
    store, cache, embed, leaf, loader, validator, guard = (Mock() for _ in range(7))
    eng = RagLlmEngine(store, cache, embed, leaf, loader, validator, guard)
    assert eng.store is store and eng.cache is cache and eng.embed is embed
    assert eng.leaf is leaf and eng.loader is loader and eng.validator is validator and eng.guard is guard
    assert eng.tau_hit == 0.86 and eng.tau_few == 0.72

def test_thresholds_overridable_by_keyword():
    eng = RagLlmEngine(Mock(), Mock(), Mock(), Mock(), Mock(), Mock(), Mock(), tau_hit=0.9, tau_few=0.7)
    assert eng.tau_hit == 0.9 and eng.tau_few == 0.7
```

`tests/unit/recipes/engines/test_rag_llm_available_composes_collaborators.py`
```python
@pytest.mark.parametrize("leaf_ok,store_ok,expected", [(True,True,True),(False,True,False),(True,False,False),(False,False,False)])
def test_available_is_logical_and_of_leaf_and_store(leaf_ok, store_ok, expected):
    leaf, store = Mock(), Mock()
    leaf.available.return_value = leaf_ok
    store.opens_cleanly.return_value = store_ok
    eng = RagLlmEngine(store, Mock(), Mock(), leaf, Mock(), Mock(), Mock())
    assert eng.available() is expected
```

`tests/unit/recipes/test_engine_registry_lists_three.py`
```python
def test_registry_has_three_engines_in_load_order():
    from codegenie.recipes.engines import _REGISTRY  # or whatever Phase 3 named it
    names = [e.name for e in _REGISTRY]
    assert names == ["ncu","openrewrite","rag_llm"]
```

### Green
Minimal class body: ctor stores attrs, `available` is two lines, `applies` is a `frozenset` `any(...)`, `apply` raises `NotImplementedError`. One import line added to `engines/__init__.py`.

### Refactor
- Pull `_FALLBACK_REASONS` to module-level `Final[frozenset[str]]`. Add a docstring tying it to ADR-P4-001 and the closed-set discipline.
- Add class docstring naming the seven collaborators and citing ADR-P4-001/-003/-004/-014/-015.
- Type-pin `name: ClassVar[Literal["rag_llm"]] = "rag_llm"`.
- Mypy-strict pass: ensure `previous_engines` access has a precise type (not `Any`); if the Phase 3 type is `list[EngineAttempt]`, import it.
- Log `engine.applies.decided(result=..., reason=...)` at debug level only — this is a high-frequency selector path and noise is the cost.

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/recipes/engines/rag_llm.py` | NEW — the class skeleton, `applies()`, `available()`, `apply()` stub. |
| `src/codegenie/recipes/engines/__init__.py` | One-line import so the `@register_recipe_engine` decorator fires at module load. |
| `tests/unit/recipes/engines/test_rag_llm_applies_only_on_fallback_reason.py` | NEW — the four `applies()` cases. |
| `tests/unit/recipes/engines/test_rag_llm_constructor_di.py` | NEW — seven collaborators stored verbatim + threshold defaults/overrides. |
| `tests/unit/recipes/engines/test_rag_llm_available_composes_collaborators.py` | NEW — `available()` is the AND of `leaf.available()` and `store.opens_cleanly()`. |
| `tests/unit/recipes/test_engine_registry_lists_three.py` | NEW — registry contains three engines in load order. |

## Out of scope
- **The five `apply()` helpers** (`_compute_query_key`, `_retrieve`, `_plan_from_rag`, `_invoke_llm`, `_materialize`) — handled by S5-02.
- **`tier_evidence` field on `RecipeApplication`** — handled by S5-02.
- **Cassette-driven integration tests** — handled by S5-03.
- **Orchestrator writeback-stub promotion** — handled by S6-03 (Step 1 already planted the stub branch).
- **Gap-1 `rag_exact`-only-on-`recipe_invocation` discipline** — handled by S5-02.

## Notes for the implementer
- Resist the urge to put even one line of three-tier logic into `apply()`. The whole point of this story is a reviewable skeleton — the body lands in S5-02 with its own TDD pass.
- The `applies()` rule is the most-tested behaviour in this story for a reason: critic §B.1 specifically attacked the "rag_llm picked first on cold start" failure mode. Treat any test that fails to exercise an `previous_engines=[]` case as incomplete.
- Mock the collaborators with `Mock(spec=...)` where the real type is importable. Bare `Mock()` is acceptable for the ctor test (the spec value isn't load-bearing there) but `Mock(spec=LeafLlmAgent)` in the `available()` test makes signature drift surface.
- Do **not** import `anthropic` / `chromadb` / `sentence_transformers` / `langgraph` in `rag_llm.py`. The fence-CI test from Step 1 (`tests/fence/test_fence_phase4.py`) will fail the PR if any leak — that is the load-bearing import-graph invariant for the whole phase.
- The `_FALLBACK_REASONS` frozen-set is exhaustive *as of Phase 4*. Phase 7 (Chainguard) will extend it via a registry pattern — but **do not** invent that registry now. Hard-code the set; ADR-P4-001 says the Literal grows by one value per task class and the precedent is "extend the set in this file when the next task class lands."
- The selector-state plumbing (how `previous_engines` reaches `applies()`) is already done by Phase 3. If the field name on `RepoContextView` differs from `previous_engines`, match the Phase 3 spelling exactly — don't rename.
