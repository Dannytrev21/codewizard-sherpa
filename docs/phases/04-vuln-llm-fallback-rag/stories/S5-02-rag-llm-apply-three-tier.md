# Story S5-02 — `apply()` three-tier helpers + `tier_evidence` + Gap 1 `rag_exact`-only-on-`recipe_invocation`

**Step:** Step 5 — Compose `RagLlmEngine` + three-tier `apply()`
**Status:** Ready
**Effort:** L
**Depends on:** S5-01 (`RagLlmEngine` skeleton + DI + `applies()`), S2-01 (`OutputValidator` chain + `Plan` envelope)
**ADRs honored:** ADR-P4-001, ADR-P4-003 (Gap 1 — `Plan.kind` is a tier-routing signal), ADR-P4-008 (objective-signal trust), ADR-P4-010 (`LlmInvocationGuard` preflight), ADR-P4-011 (`LlmPromptContext` exfil boundary), ADR-P4-014 (`LeafAgentNode` swap point)

## Context
S5-01 landed a class skeleton whose `apply()` raises `NotImplementedError`. This story replaces the stub with the load-bearing three-tier choreography: tier-1 `QueryKeyCache` exact-replay → tier-2 `SolvedExampleStore` RAG retrieval → tier-3 `LeafLlmAgent` cold-or-few-shot call. The body is **five tiny helpers** (`_compute_query_key`, `_retrieve`, `_plan_from_rag`, `_invoke_llm`, `_materialize`), each ≤ 30 LOC and cyclomatic ≤ 5, enforced by ruff `C901`. Three things this story locks in beyond the helpers: (1) the **Gap 1 fix** — `rag_exact` short-circuits the LLM only when `top1.cosine ≥ τ_hit` **AND** the retrieved `SolvedExample.plan.kind == "recipe_invocation"`; retrieved `manual_patch` examples with cosine ≥ τ_hit demote to tier-3 with the example carried as few-shot, because diff bytes are repo-specific (ADR-P4-003 / arch §Gap 1); (2) the **eager-embed overlap** perf optimisation — embedding compute is enqueued before the tier-1 result-check returns so it overlaps subsequent wall-clock; (3) the new **`RecipeApplication.tier_evidence`** field — a structured dict carrying `tier_used`, `top1_cosine` (when tier-2 ran), `cache_hit_key` (when tier-1 hit), `few_shots_used`, `cost_usd`, `tokens` — that powers the `remediation-report.yaml#phase4.tier_evidence` operator surface and the Step 6 writeback-gate's strict cross-field consistency check.

## References — where to look
- **Architecture:**
  - `../phase-arch-design.md §Component design / 1. RagLlmEngine` — the five-helper shape (≤ 30 LOC, cyclomatic ≤ 5 enforced by ruff `C901`); the `plan_source ∈ {"query_cache","rag_exact","rag_fewshot_llm","llm_cold"}` enum.
  - `../phase-arch-design.md §Process view — runtime` — the sequence diagram (`ENG → QKC.get → EMB.embed → RAG.query → GRD.check_budget → LLM.invoke`); the "embedding compute is eagerly enqueued on the LLM-cold path to overlap with validation wall-clock" note.
  - `../phase-arch-design.md §Gap analysis — Gap 1` — the verbatim spec for the Gap-1 fix: path (b) — `rag_exact` may only return `Plan.kind="recipe_invocation"` plans; `manual_patch` retrieved at cosine ≥ τ_hit demotes to tier-3.
  - `../phase-arch-design.md §Data model` — `Plan`, `RetrievedExample`, `CachedPlan`, `QueryKey` shapes.
  - `../phase-arch-design.md §Component 3 — OutputValidator` — the `Plan` envelope (`kind: Literal["recipe_invocation","manual_patch"]`) is the validator's output; the engine consumes the typed `Plan`, never raw text.
  - `../phase-arch-design.md §Control flow` (the eleven-step numbered list — search for "tier_evidence") — the materialisation step and the `remediation-report.yaml#phase4` section it feeds.
- **Phase ADRs:**
  - `../ADRs/0001-recipe-engine-literal-extends-with-rag-llm.md` — ADR-P4-001 — `engine_used="rag_llm"` is the discriminator the orchestrator writeback branch reads; this story is where it gets written.
  - `../ADRs/0003-plan-envelope-kind-and-target-files-allowlist.md` — ADR-P4-003 — `Plan.kind` is *also* a tier-routing signal (Gap 1); only `recipe_invocation` is repo-portable. `target_files` allowlist is enforced by `OutputValidator`, not re-checked here.
  - `../ADRs/0010-llm-invocation-guard-running-total-with-override.md` — ADR-P4-010 — `_invoke_llm` calls `guard.precheck(request, running_total_usd=ctx.remaining_budget_usd)` preflight; any breach raises `CostCeilingBreached` before the network call.
  - `../ADRs/0011-llm-prompt-context-exfiltration-boundary.md` — ADR-P4-011 — the few-shots block carries `RetrievedExampleStub` (id + advisory summary + patch), never the full `SolvedExample` body; the prompt builder is the only place that lifts retrieved-example data into a request.
  - `../ADRs/0014-langgraph-leaf-agent-node-minimal-wrap.md` — ADR-P4-014 — `_invoke_llm` calls `self.leaf.invoke(req)`; the `LeafAgentNode` wrap is internal to the leaf.
- **Production ADRs:**
  - `../../../production/adrs/0011-recipe-first-rag-llm-fallback-planning.md` — the three-tier decision chain; this story is its Phase-4 instantiation.
  - `../../../production/adrs/0024-cost-observability-end-to-end.md` — `cost_usd` and token counts land in `tier_evidence` in the shape Phase 13's roll-up consumes verbatim.
- **Source design:** `../final-design.md §Component 1 — RagLlmEngine` — the five-helper shape is copy-pasted from here. `§Synthesis ledger row "rag_exact materialization (Gap 1)"` — the path (b) decision.
- **High-level impl:** `../High-level-impl.md §Step 5` — done-criteria list this story's tests instantiate.
- **Existing code:**
  - `src/codegenie/recipes/engines/rag_llm.py` (S5-01) — the class to extend.
  - `src/codegenie/recipes/contract.py` (Phase 3) — `RecipeApplication` lives here; this story adds the `tier_evidence` field.
  - `src/codegenie/llm/contract.py` (S1-01) — `LlmRequest`, `LlmResponse`, `Plan`.
  - `src/codegenie/llm/output_validator.py` (S2-01) — `OutputValidator.validate` runs inside `LeafLlmAgent.invoke`, not here.
  - `src/codegenie/rag/query_key_cache.py` (S4-05) — `cache.get(qk) -> CachedPlan | None` and `cache.put(qk, plan, example_id)`.
  - `src/codegenie/rag/store.py` (S4-04) — `store.read().query(vec, top_k, filters) -> list[RetrievedExample]` with always-on `embedding_model_digest` filter.

## Goal
Implement `RagLlmEngine.apply()` as five LOC-and-complexity-bounded helpers that realise the three-tier chain, record `plan_source` and `tier_evidence` for every path, and route only `recipe_invocation`-shaped retrieved plans through the `rag_exact` LLM-skip path (Gap 1).

## Acceptance criteria
- [ ] `RecipeApplication` (in `src/codegenie/recipes/contract.py`) gains a `tier_evidence: TierEvidence` field where `TierEvidence` is a new `BaseModel(extra="forbid", frozen=True)` with fields `tier_used: Literal["tier1_cache","tier2_rag","tier3_llm"]`, `plan_source: Literal["query_cache","rag_exact","rag_fewshot_llm","llm_cold"]`, `top1_cosine: float | None`, `cache_hit_key: str | None`, `few_shots_used: int`, `cost_usd: Decimal`, `tokens: TokenCounts`. The Phase 3 contract-snapshot test regenerates and the PR carries the `phase-3-contract-bumped` label.
- [ ] `RagLlmEngine.apply(recipe, repo, ctx) -> RecipeApplication` is implemented as exactly five helpers, defined in the order they execute:
  1. `_compute_query_key(advisory, repo_ctx, recipe_selection) -> QueryKey` — pure; builds the seven-field `QueryKey` tuple and returns it.
  2. `_retrieve(qk: QueryKey, query_text: str) -> _RetrieveResult` — checks `cache.get(qk)`; on miss, schedules the embedding compute eagerly (`asyncio.create_task` or a thread-pool submit — implementation choice, but the embedding call **must start before the tier-1 result return path completes**), then queries `store.read().query(vec, top_k=5, filters={"task_class","ecosystem","language","embedding_model_digest"})`. Returns a discriminated-union dataclass `_RetrieveResult` carrying one of `{Tier1Hit(cached: CachedPlan), Tier2Hit(top: list[RetrievedExample])}`.
  3. `_plan_from_rag(retrieved: _RetrieveResult) -> _PlanDecision` — pure tier-routing. **Gap 1 fix**: `rag_exact` short-circuit fires iff `top[0].cosine ≥ tau_hit` AND `top[0].body.plan.kind == "recipe_invocation"`. A retrieved `manual_patch` example with cosine ≥ τ_hit is **demoted** to `_PlanDecision.few_shot(examples=top[:3])`. `τ_few ≤ top[0].cosine < τ_hit` → `_PlanDecision.few_shot(examples=top[:3])`. Below `τ_few` → `_PlanDecision.cold()`. Returns one of `{Exact(plan, example_id), FewShot(examples), Cold()}`.
  4. `_invoke_llm(req: LlmRequest, *, remaining_budget_usd: Decimal) -> LlmResponse` — calls `self.guard.precheck(req, running_total_usd=remaining_budget_usd)` *before* `self.leaf.invoke(req)`. `OutputValidator` runs **inside** `LeafLlmAgent.invoke` (do not call it here). Raises `CostCeilingBreached` / `LlmOutputRejected` / `LlmTransportError` upward.
  5. `_materialize(decision_or_cached, *, recipe, repo, ctx) -> RecipeApplication` — assembles the `RecipeApplication(engine_used="rag_llm", diff=..., plan_source=..., tier_evidence=...)`. Runs `git apply --check` on the resulting diff (Phase 3 invariant); failure sets `exit_code=6 ("transform.apply_failed")` and leaves `tier_evidence.plan_source` unchanged so diagnostics survive.
- [ ] Each helper is ≤ 30 LOC (counted from `def` line to the function's last statement, blanks and docstrings included) and has cyclomatic complexity ≤ 5. Enforced by ruff `C901` configured in `pyproject.toml` for `src/codegenie/recipes/engines/rag_llm.py`.
- [ ] `tests/unit/recipes/engines/test_planner_tier_decisions.py` parametrises all four `plan_source` values, each exercised in isolation:
  - `query_cache` — `cache.get(qk)` returns a `CachedPlan` → `tier_evidence.tier_used == "tier1_cache"`, `plan_source == "query_cache"`, `cache_hit_key` populated, `top1_cosine is None`, `cost_usd == 0`, no embed/store/leaf calls beyond what tier-1 needs (assert via `Mock.assert_not_called()` on `embed`, `store`, `leaf`).
  - `rag_exact` — `cache.get` returns None; `store.query` returns `RetrievedExample(cosine=0.90, body=SolvedExample(plan=Plan(kind="recipe_invocation", ...)))` → `plan_source == "rag_exact"`, `leaf.invoke.assert_not_called()`, `top1_cosine == 0.90`.
  - `rag_fewshot_llm` — `store.query` returns `RetrievedExample(cosine=0.79, ...)` → `plan_source == "rag_fewshot_llm"`, `leaf.invoke` called once with `request.few_shots_block is not None`, `few_shots_used == 3` (top-3).
  - `llm_cold` — `store.query` returns empty (or all below τ_few) → `plan_source == "llm_cold"`, `leaf.invoke` called once with `request.few_shots_block is None`, `few_shots_used == 0`.
- [ ] `tests/unit/recipes/engines/test_rag_exact_only_fires_on_recipe_invocation_plan.py` (Gap 1 fix) — two parametrised cases:
  - `top1.cosine = 0.90` and `body.plan.kind == "manual_patch"` → `plan_source == "rag_fewshot_llm"` (demoted), `leaf.invoke.assert_called_once()` (NOT skipped), and the request's `few_shots_block` carries the demoted example as a few-shot.
  - `top1.cosine = 0.90` and `body.plan.kind == "recipe_invocation"` → `plan_source == "rag_exact"`, `leaf.invoke.assert_not_called()`.
- [ ] `tests/unit/recipes/engines/test_apply_helpers_under_30_loc.py` — programmatic AST scan over `src/codegenie/recipes/engines/rag_llm.py` asserts each of the five helpers' `FunctionDef` node has `(end_lineno - lineno + 1) <= 30`; a separate `ruff check --select C901 --max-complexity 5 src/codegenie/recipes/engines/rag_llm.py` is asserted to exit 0.
- [ ] `tests/unit/recipes/engines/test_eager_embed_overlaps_wall_clock.py` — async-ordering test: instruments `embed.embed` and `cache.get` with awaitables whose order of first-await is recorded; asserts `embed.embed` was *scheduled* (first call site reached) before `_retrieve` returns from the tier-1 miss path. Implementation may use `asyncio.gather` or a thread-pool — the test pins the observable property, not the mechanism.
- [ ] `tests/unit/recipes/engines/test_invoke_llm_calls_guard_preflight.py` — `guard.precheck` is called once with `(request, running_total_usd=ctx.remaining_budget_usd)` **before** `leaf.invoke`; when `guard.precheck` raises `CostCeilingBreached`, `leaf.invoke.assert_not_called()`.
- [ ] `tests/unit/recipes/engines/test_tier_evidence_shape.py` — for each `plan_source`, the produced `RecipeApplication.tier_evidence` round-trips through `TierEvidence.model_dump_json()` / `TierEvidence.model_validate_json()` (Pydantic `extra="forbid"` catches drift) and matches a golden YAML fixture under `tests/golden/tier_evidence/<plan_source>.yaml`.
- [ ] `tests/unit/recipes/engines/test_apply_failed_keeps_tier_evidence.py` — `git apply --check` failure on a returned diff → `RecipeApplication.exit_code == 6` AND `tier_evidence.plan_source` still reflects the tier that produced the bad diff (diagnostics survive). Engine **never retries**; **never** writes a negative example.
- [ ] All Step 5 code passes `mypy --strict src/codegenie/recipes/engines/rag_llm.py` and `ruff check src/codegenie/recipes/engines/rag_llm.py`.

## Implementation outline
1. Add `TierEvidence` and `TokenCounts` Pydantic models to `src/codegenie/recipes/contract.py` (or a new `src/codegenie/recipes/tier_evidence.py` re-exported from `contract`). Wire `RecipeApplication.tier_evidence: TierEvidence | None = None` — `None` is reserved for the two non-LLM Phase-3 engines, never for `rag_llm`. Update the Phase 3 contract snapshot and label the PR `phase-3-contract-bumped`.
2. In `src/codegenie/recipes/engines/rag_llm.py`, add the five helper methods. Mark each `_` private. Add a single public `apply(recipe, repo, ctx) -> RecipeApplication` that orchestrates: `qk = self._compute_query_key(...)`; `retrieved = self._retrieve(qk, query_text)`; `decision = self._plan_from_rag(retrieved)`; if `decision` is `Exact` → straight to `_materialize`; else build `LlmRequest` (via `self.loader.render_request(...)` from S2-02 + retrieved as few-shots if `FewShot`) and `response = self._invoke_llm(req, remaining_budget_usd=ctx.remaining_budget_usd)`; then `_materialize`.
3. `_retrieve`: implement the eager-embed overlap. Simplest correct shape is `asyncio.run(self._retrieve_async(...))` with a top-level `asyncio.gather(self.embed.embed(query_text), self.cache.get(qk))`; on cache-hit, cancel the embed task (`embed_task.cancel()`); on cache-miss, await the embed and pass into `store.query`. If async machinery proves fragile under tests, fall back to a `concurrent.futures.ThreadPoolExecutor(max_workers=2).submit(embed.embed, ...)` pattern — same observable ordering, simpler tests. Document the chosen shape in a class docstring referencing `phase-arch-design.md §Process view`.
4. `_plan_from_rag`: implement the Gap 1 fix as a single nested `if`. Pseudocode:
   ```python
   if isinstance(retrieved, Tier1Hit):
       return Exact(plan=retrieved.cached.plan, example_id=retrieved.cached.example_id)  # plan_source filled by _materialize
   top = retrieved.top
   if not top:
       return Cold()
   top1 = top[0]
   if top1.cosine >= self.tau_hit and top1.body.plan.kind == "recipe_invocation":
       return Exact(plan=top1.body.plan, example_id=top1.body.id)
   if top1.cosine >= self.tau_few:
       return FewShot(examples=top[:3])
   return Cold()
   ```
   The `manual_patch` + cosine ≥ τ_hit case falls through to the `tau_few` branch — which is exactly the demotion the gap requires.
5. `_invoke_llm`: two lines — `self.guard.precheck(req, running_total_usd=remaining_budget_usd)`; `return self.leaf.invoke(req)`. Do not catch exceptions; let them propagate. `OutputValidator` runs inside `LeafLlmAgent.invoke` per ADR-P4-004 — do **not** call it here.
6. `_materialize`: assemble the `Plan → diff` materialisation. For `Exact` from tier-2, the retrieved `recipe_invocation`-shaped plan is applied via the existing Phase 3 recipe-invocation materialiser (`recipe_id` + parameters → diff); for `FewShot` / `Cold`, the LLM response's `Plan` is materialised (a `manual_patch` plan's `diff` is the diff; a `recipe_invocation` plan is materialised through the same Phase 3 path). Run `git apply --check`; on failure return `RecipeApplication(exit_code=6, tier_evidence=...)` — do **not** retry, do **not** call the LLM again, do **not** write a negative example.
7. Configure ruff `C901` (`tool.ruff.lint.mccabe.max-complexity = 5`) scoped to `src/codegenie/recipes/engines/rag_llm.py` via a per-file override; the global ceiling stays at 10. Add a `noqa` ban for this file so any helper that violates is a CI red.
8. Write tests in the order: shape (`tier_evidence_shape`), branches (`planner_tier_decisions` + `rag_exact_only_fires_on_recipe_invocation_plan`), invariants (`apply_helpers_under_30_loc`, `invoke_llm_calls_guard_preflight`), perf-ordering (`eager_embed_overlaps_wall_clock`), failure (`apply_failed_keeps_tier_evidence`).
9. Run ruff, ruff format, mypy strict, pytest. Regenerate the Phase 3 contract snapshot and commit it on the same PR.

## TDD plan — red / green / refactor

### Red
`tests/unit/recipes/engines/test_rag_exact_only_fires_on_recipe_invocation_plan.py`
```python
import pytest
from unittest.mock import Mock
from codegenie.recipes.engines.rag_llm import RagLlmEngine
from codegenie.llm.contract import Plan, RecipeInvocation, ManualPatch
from codegenie.rag.models import SolvedExample, RetrievedExample

def _eng(leaf_mock, store_mock, cache_mock=None):
    return RagLlmEngine(
        store=store_mock, cache=cache_mock or Mock(get=Mock(return_value=None)),
        embed=Mock(), leaf=leaf_mock, loader=_passthrough_loader(),
        validator=Mock(), guard=Mock(),
    )

@pytest.mark.parametrize(
    "kind,expected_source,expect_llm_called",
    [
        ("recipe_invocation", "rag_exact", False),
        ("manual_patch",      "rag_fewshot_llm", True),
    ],
)
def test_rag_exact_short_circuit_only_for_recipe_invocation(kind, expected_source, expect_llm_called):
    # Top hit is well over tau_hit (0.86), so cosine alone would say "exact"
    plan = Plan(kind=kind, intent="x", canary_echo="c", rationale="r",
                **({"recipe_invocation": RecipeInvocation(...)} if kind == "recipe_invocation"
                   else {"manual_patch": ManualPatch(diff="--- a\n+++ b\n", target_files=["package.json"])}))
    example = SolvedExample(plan=plan, ...)
    store = Mock(); store.read().query.return_value = [RetrievedExample(cosine=0.90, body=example, ...)]
    leaf = Mock(); leaf.invoke.return_value = _ok_llm_response()
    eng = _eng(leaf_mock=leaf, store_mock=store)
    app = eng.apply(_recipe(), _repo(), _ctx())
    assert app.tier_evidence.plan_source == expected_source
    assert leaf.invoke.called is expect_llm_called
```

`tests/unit/recipes/engines/test_planner_tier_decisions.py`
```python
@pytest.mark.parametrize(
    "scenario,expected_source",
    [
        ("tier1_hit",          "query_cache"),
        ("tier2_exact_recipe", "rag_exact"),
        ("tier2_fewshot",      "rag_fewshot_llm"),
        ("tier3_cold",         "llm_cold"),
    ],
)
def test_each_plan_source_exercised_in_isolation(scenario, expected_source):
    eng = _engine_for(scenario)  # fixture wires the four mocks to the scenario
    app = eng.apply(_recipe(), _repo(), _ctx())
    assert app.tier_evidence.plan_source == expected_source
    # Cross-scenario invariants: no_llm_call_on_tier1 + no_store_call_on_tier1 etc.
    if scenario == "tier1_hit":
        eng.embed.embed.assert_not_called(); eng.store.read().query.assert_not_called(); eng.leaf.invoke.assert_not_called()
    if scenario in ("tier2_fewshot","tier3_cold"):
        eng.leaf.invoke.assert_called_once()
    if scenario == "tier2_exact_recipe":
        eng.leaf.invoke.assert_not_called()
```

`tests/unit/recipes/engines/test_apply_helpers_under_30_loc.py`
```python
import ast, subprocess, sys

HELPERS = {"_compute_query_key","_retrieve","_plan_from_rag","_invoke_llm","_materialize"}

def test_each_helper_is_under_thirty_lines():
    src = open("src/codegenie/recipes/engines/rag_llm.py").read()
    tree = ast.parse(src)
    cls = next(n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == "RagLlmEngine")
    seen = {fn.name: (fn.end_lineno - fn.lineno + 1) for fn in cls.body if isinstance(fn, ast.FunctionDef) and fn.name in HELPERS}
    assert set(seen) == HELPERS, f"missing helpers: {HELPERS - set(seen)}"
    for name, loc in seen.items():
        assert loc <= 30, f"{name} is {loc} lines (>30)"

def test_ruff_c901_enforces_max_complexity_five():
    r = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--select", "C901",
         "--config", "tool.ruff.lint.mccabe.max-complexity=5",
         "src/codegenie/recipes/engines/rag_llm.py"],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stdout + r.stderr
```

`tests/unit/recipes/engines/test_eager_embed_overlaps_wall_clock.py`
```python
import asyncio

async def test_embed_scheduled_before_cache_get_completes():
    events: list[str] = []
    async def slow_cache_get(qk):
        events.append("cache_start"); await asyncio.sleep(0.05); events.append("cache_done"); return None
    async def fast_embed(text):
        events.append("embed_start"); await asyncio.sleep(0.01); events.append("embed_done"); return [0.0]*384
    cache = Mock(); cache.get = slow_cache_get
    embed = Mock(); embed.embed = fast_embed
    eng = _engine_for_async(cache=cache, embed=embed)
    await eng._retrieve(_qk(), "query text")
    # Property: embed_start observed before cache_done. (Order of cache_start vs embed_start may vary.)
    assert events.index("embed_start") < events.index("cache_done")
```

### Green
Five helpers, the `_plan_from_rag` if-chain implementing Gap 1 verbatim, `_invoke_llm` two-liner, `_retrieve` using `asyncio.gather` for the overlap. Cancel the embed task on tier-1 hit. `_materialize` calls the existing Phase 3 recipe-invocation materialiser for `recipe_invocation`-shaped plans and `git apply --check`s the result.

### Refactor
- Pull `TierEvidence`, `TokenCounts`, and the `_PlanDecision` discriminated union out into a named module (`src/codegenie/recipes/engines/_rag_llm_models.py`) so the engine file stays under the LOC ceiling.
- Add docstrings on each helper citing the arch section and ADR it realises (e.g. `_plan_from_rag` cites `phase-arch-design.md §Gap 1` + ADR-P4-003).
- Log structured events on each tier transition: `engine.rag_llm.tier1_hit`, `engine.rag_llm.tier2_exact`, `engine.rag_llm.tier2_fewshot`, `engine.rag_llm.llm_cold`. These power the operator-facing report and Step 7's perf canaries.
- Edge cases: `top` has length 1 (no `top[:3]` over-slice); embedding compute raises (cancel cache, propagate as `EmbeddingProviderError`); `store.query` returns no rows (treat as `Cold`); `cache.get` returns a `CachedPlan` whose `catalog_blake3` mismatches current — treat as a miss (Phase 4 implicit-TTL; document inline).
- Mypy-strict pass: ensure the discriminated unions use `Literal` discriminators or `match-case` so mypy narrows.
- Confirm `LlmPromptContext` (ADR-P4-011) is the only schema feeding `loader.render_request`; the helper does not lift any other field from `repo_ctx` into the prompt.

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/recipes/engines/rag_llm.py` | The five helpers + `apply()` orchestration land here, on top of S5-01's skeleton. |
| `src/codegenie/recipes/engines/_rag_llm_models.py` | NEW — `_PlanDecision` union, `_RetrieveResult` union (kept private to the engine). |
| `src/codegenie/recipes/contract.py` | Add `TierEvidence`, `TokenCounts`, `RecipeApplication.tier_evidence` field; Phase 3 contract snapshot regenerates. |
| `pyproject.toml` | Per-file ruff override: `tool.ruff.lint.mccabe.max-complexity = 5` for `src/codegenie/recipes/engines/rag_llm.py`. |
| `tests/unit/recipes/engines/test_planner_tier_decisions.py` | NEW — all four `plan_source` cases in isolation. |
| `tests/unit/recipes/engines/test_rag_exact_only_fires_on_recipe_invocation_plan.py` | NEW — the Gap 1 fix. |
| `tests/unit/recipes/engines/test_apply_helpers_under_30_loc.py` | NEW — AST scan + ruff `C901` enforcement. |
| `tests/unit/recipes/engines/test_eager_embed_overlaps_wall_clock.py` | NEW — async-ordering test for the perf overlap. |
| `tests/unit/recipes/engines/test_invoke_llm_calls_guard_preflight.py` | NEW — preflight discipline (ADR-P4-010). |
| `tests/unit/recipes/engines/test_tier_evidence_shape.py` | NEW — round-trip + golden YAML. |
| `tests/unit/recipes/engines/test_apply_failed_keeps_tier_evidence.py` | NEW — `git apply --check` failure preserves diagnostics. |
| `tests/golden/tier_evidence/{query_cache,rag_exact,rag_fewshot_llm,llm_cold}.yaml` | NEW — golden fixtures. |
| `tests/contracts/test_recipe_engine_literal.py` | Regenerate snapshot (Phase 3 contract bump). |

## Out of scope
- **Cassette-driven end-to-end integration tests** — handled by S5-03 (`test_e2e_llm_cold.py`, `test_e2e_rag_then_llm_fewshot.py`, `test_egress_proxy_blocks_x_api_key_in_request.py`).
- **Orchestrator writeback-branch promotion** — handled by S6-03 (the Step-1 stub stays a stub until then).
- **`writeback_solved_example` body** — handled by S6-01 / S6-02; this story only writes `tier_evidence` for the gate to consume later.
- **`OutputValidator` chain** — handled by S2-01; runs inside `LeafLlmAgent.invoke`, never called directly here.
- **Prompt template rendering** — handled by S2-02 (`PromptLoader`); this story consumes `loader.render_request(...)` as an opaque function.

## Notes for the implementer
- Gap 1 is the single most-tested behaviour in this story. The reviewer will look for the `kind == "recipe_invocation"` check in `_plan_from_rag` and the test that proves a `manual_patch` retrieval at cosine 0.90 still calls the LLM. Treat any code path that exits via `rag_exact` without checking `Plan.kind` as a CI red.
- `_invoke_llm` is two lines. Resist the urge to wrap retries, fall-back models, or "if validator rejects, try again with stricter system prompt." ADR-P4-007 forbids application-level retry; ADR-P4-008 (objective signals only) forbids any "the LLM said it would be careful, let's give it another shot" pattern.
- The five-helper LOC ceiling is enforced by both an AST scan **and** ruff `C901`. If a helper drifts past 30 LOC, extract a private module-level pure function — do **not** raise the ceiling. The ceiling exists because critic §B noted that engines that exceed ~150 total LOC start hiding decisions.
- `tier_evidence.tier_used` and `tier_evidence.plan_source` are intentionally *both* recorded — the orchestrator's writeback gate (S6-02) cross-checks them for engine-spoof attempts (`engine_used="ncu"` + `tier_evidence` shaped like a `rag_llm` run → refused). Do not coalesce the two fields into one.
- The eager-embed overlap is a **performance optimisation, not a correctness invariant**. If the async ordering proves fragile under CI (Windows? GIL contention?), fall back to a `ThreadPoolExecutor.submit` pattern without changing the public contract. The arch design explicitly permits this fallback.
- `git apply --check` is run **inside** `_materialize`. Do not move it to the orchestrator; Phase 3 already runs it once after the engine returns, but the engine's own check catches obvious-bad diffs early and lets `tier_evidence` survive a failed materialisation.
- The Phase 3 contract snapshot bump is the most visible CI signal of this PR. The `phase-3-contract-bumped` label is required by ADR-P4-001's PR discipline — do not merge without it.
- Do **not** lift fields out of `repo_ctx` into the LLM request beyond what `LlmPromptContext` (ADR-P4-011) names. `tests/integration/test_llm_prompt_context_does_not_leak_secrets.py` from Step 7 will catch any drift, but the conscientious form is to confine all prompt building to `PromptLoader.render_request`.
