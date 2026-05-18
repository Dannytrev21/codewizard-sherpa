# Story S7-01 — `FallbackTierPlanRecipeEngine` plugin adapter

**Step:** Step 7 — Ship plugin wiring: FallbackTierPlanRecipeEngine + harvest + E2E exit criteria
**Status:** Ready
**Effort:** M
**Depends on:** S6-01 (`FallbackTier.run`), S1-03 (`PlanOutcome`), S1-02 (`PlanProposal`); Phase-3 plugin `RecipeEngine` Protocol stable
**ADRs honored:** ADR-0002 (FallbackTier pipeline), ADR-0004 (PlanOutcome wraps RecipeOutcome — never widens), ADR-0003 (path-scoped fence), production-ADR-0031 (extension by addition into plugin)

## Context

Step 7 is the moment Phase 4's substrate becomes addressable from the existing Phase-3 orchestrator. `FallbackTier.run(...)` lives in `src/codegenie/fallback/tier.py` but the orchestrator does not know about it — it dispatches `transforms()['plan']` against a `RecipeEngine` shape (Phase-3 Protocol). The job of this story is to ship the **Adapter** that conforms `FallbackTier` to that Protocol, returning Phase-3's `RecipeOutcome` so the orchestrator sees zero new behavior at the type level.

Two non-negotiables: (1) the adapter lives *inside the plugin directory* (`plugins/vulnerability-remediation--node--npm/subgraph/`), not in `src/codegenie/` — per ADR-0031 and the Phase-7 precondition that "the diff touches only the new plugin directory"; (2) it emits Phase-4-local `PlanOutcome` to the event log **alongside** the projected `RecipeOutcome`, so the inline harvester (S6-03) has the rich four-variant shape and Phase 3 keeps its three-variant shape (ADR-0004). Widening `RecipeOutcome` would retroactively force Phase 7's distroless plugin to add `case` arms — the failure mode this adapter exists to prevent.

The adapter is the registered value of `plugin.transforms()['plan']`; whether the plugin already has a placeholder `plan` engine from Phase 3 (a refuse-only stub) is a question the implementer reads from the existing plugin source first (Global Rule 8). If it does, this story *replaces* it surgically; if it does not, this story adds the slot.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component 14 — FallbackTierPlanRecipeEngine` — purpose ("zero edits to `src/codegenie/plugins/protocols.py`"), public interface (`apply(repo, plan, capability) -> RecipeOutcome`), internal structure (constructs `FallbackTier` from plugin-resolved adapters; awaits `FallbackTier.run(...)`; projects `RecipeApplication → RecipeOutcome.{Applied,NotApplicable,Failed}`).
  - `../phase-arch-design.md §Logical view` — the `FallbackTierPlanRecipeEngine --> FallbackTier` edge in the component diagram.
  - `../phase-arch-design.md §Process view` — Scenario 2 sequence diagram: `Eng as FallbackTierPlanRecipeEngine`, `Eng-->>Orch: RecipeOutcome.Applied(transform)`.
  - `../phase-arch-design.md §Design patterns applied` row "FallbackTierPlanRecipeEngine returning Phase 3's `RecipeOutcome` shape" — Adapter pattern (not `RecipeEngine` extension).
- **Phase ADRs:**
  - `../ADRs/0002-fallback-tier-pipeline-no-langgraph.md` — `FallbackTier.run` is a `def`, not a LangGraph node; the adapter just awaits it.
  - `../ADRs/0004-plan-outcome-wraps-recipe-outcome.md` — `PlanOutcome` is consumed by event-emission/harvester only; never widens Phase-3 `RecipeOutcome`; `FallbackTier.run` returns Phase-3's `RecipeApplication`.
  - `../ADRs/0003-path-scoped-fence-amendment.md` — adapter must not import `anthropic`/`chromadb`/`fastembed`/`onnxruntime` (those imports live behind the substrate Protocols this adapter composes); the adapter is plugin-side, not under `src/codegenie/fallback/`.
- **Production ADRs:**
  - `../../../production/adrs/0031-plugin-architecture.md` — plugin scope; extension by addition; `transforms()['plan']` is the seam.
- **Source design:**
  - `../final-design.md §Component 14` and §"Three load-bearing structural lines" item 3 — why the adapter exists and why it must not widen `RecipeOutcome`.
- **High-level impl:**
  - `../High-level-impl.md §Step 7` — `Features delivered` first bullet; `Done criteria` bullets on `RecipeOutcome` projection and kernel-frozen invariant.
- **Existing code:**
  - `src/codegenie/plugins/protocols.py` (Phase 3) — `RecipeEngine` Protocol. **Read this; do not edit.**
  - `src/codegenie/fallback/tier.py` (S6-01) — `FallbackTier.run` signature and return shape.
  - `src/codegenie/fallback/plan_outcome.py` (S1-03) — `PlanOutcome` union to emit.
  - `plugins/vulnerability-remediation--node--npm/` — current scaffold; check `transforms()` for any existing `plan` slot.
  - `src/codegenie/plugins/events.py` (Phase 3) — `EventLog` shape for `PlanOutcome` emission.

## Goal

Land `plugins/vulnerability-remediation--node--npm/subgraph/fallback_plan_engine.py` exposing `FallbackTierPlanRecipeEngine` that implements Phase-3 `RecipeEngine` over `FallbackTier.run`, projects `RecipeApplication → RecipeOutcome.{Applied,NotApplicable,Failed}`, emits `PlanOutcome` alongside, and is wired into `plugin.transforms()['plan']` — with zero edits to `src/codegenie/plugins/protocols.py`, `RemediationOrchestrator`, or any Phase-0/1/2/3 kernel file.

## Acceptance criteria

- [ ] `plugins/vulnerability-remediation--node--npm/subgraph/fallback_plan_engine.py` exists, defines `class FallbackTierPlanRecipeEngine`, and conforms structurally to the Phase-3 `RecipeEngine` Protocol (mypy `--strict` accepts assignment without `cast`).
- [ ] `FallbackTierPlanRecipeEngine.__init__` accepts the substrate dependencies as constructor args (`retriever: SolvedExampleRetriever`, `leaf: LeafLlm`, `budget: LlmInvocationGuard`, `fence: FenceWrapper`, `canary: CanaryGuard`, `provenance: ProvenanceGate`, `event_log: EventLog`, `prompt_builder: PromptBuilder`, `harvester: SolvedExampleWriter`, `confidence_gate: ConfidenceGate`) — no globals, no module-level state; constructor is pure.
- [ ] `async def apply(self, repo, plan, capability) -> RecipeOutcome` awaits `FallbackTier.run(advisory, repo_ctx, recipe_selection)` and projects the returned `RecipeApplication` to a Phase-3 `RecipeOutcome` variant:
  - `RecipeApplication(transform=t)` → `RecipeOutcome.Applied(transform=t)`
  - `RecipeApplication.Refused(reason=PROVENANCE_NOT_APP_LAYER | LEAF_REFUSED)` → `RecipeOutcome.NotApplicable(reason=...)`
  - `RecipeApplication.Refused(reason=BUDGET_EXCEEDED | LEAF_SCHEMA_VIOLATION)` → `RecipeOutcome.Failed(reason=...)`
  - `LeafProtocolViolation | BudgetExceeded | EgressViolation` raised inside `run` → caught and surfaced as `RecipeOutcome.Failed(reason=<typed>)`.
- [ ] After projection, `FallbackTierPlanRecipeEngine.apply` emits exactly one `PlanOutcome` event to `event_log` carrying the four-variant Phase-4 shape (`AppliedFromRecipe | AppliedFromLlm | RagOnlyApplicable | Refused`); the `RecipeOutcome` is emitted by the orchestrator path as before (the adapter does not double-emit Phase-3 events).
- [ ] **Zero edits** to `src/codegenie/plugins/protocols.py` (asserted by S1-07's `test_kernel_frozen.py`); the adapter conforms structurally — no `RecipeEngine` ABC method added; no new variant appended to `RecipeOutcome`.
- [ ] `plugin.transforms()` returns `FallbackTierPlanRecipeEngine` instance for the `'plan'` key; unit test asserts `isinstance(plugin.transforms()['plan'], FallbackTierPlanRecipeEngine)`.
- [ ] `match plan_outcome` on the emitted `PlanOutcome` is exhaustive (mypy `assert_never` arm); a deliberate-failure fixture (a fifth `PlanOutcome` variant added in a sub-fixture) fails mypy `--strict`.
- [ ] AST-walking test asserts `fallback_plan_engine.py` does not `import anthropic`, `import chromadb`, `import fastembed`, or `import onnxruntime` — the adapter composes substrate Protocols, not the SDK directly (ADR-0003 path-scoped fence).
- [ ] The adapter raises `NotImplementedError` if `plan.recipe_selection.task_class != "vulnerability-remediation"` (defense in depth; plugin scope is single-task per ADR-0031).
- [ ] `make check` clean: `ruff format`, `ruff check`, `mypy --strict`, `pytest -q` all green.
- [ ] TDD red test exists, committed, green.

## Implementation outline

1. Read `src/codegenie/plugins/protocols.py` first (Global Rule 8) — note the exact `RecipeEngine.apply` signature including `repo`, `plan`, `capability` parameter names and return type. Also read the Phase-3 plugin's existing `transforms()` to see whether `'plan'` is already a key.
2. Create `plugins/vulnerability-remediation--node--npm/subgraph/fallback_plan_engine.py`. Import `FallbackTier`, `PlanOutcome`, `RecipeOutcome` (from Phase-3 kernel — read-only), and the substrate Protocols. **No `import anthropic`.**
3. Define `class FallbackTierPlanRecipeEngine` with `__init__` taking the dependency tuple (see acceptance criteria). Construct `self._tier = FallbackTier(retriever=..., leaf=..., ...)`.
4. Implement `async def apply(self, repo, plan, capability) -> RecipeOutcome`:
   - Build `(advisory, repo_ctx, recipe_selection)` from `plan` and `repo` per the existing Phase-3 plan shape.
   - Wrap `await self._tier.run(...)` in `try / except (LeafProtocolViolation, BudgetExceeded, EgressViolation) as e:` — convert to `RecipeOutcome.Failed(reason=type(e).__name__)`.
   - Project the returned `RecipeApplication` to `RecipeOutcome` via a `match` statement with `assert_never` arm.
   - Build `PlanOutcome` (Phase-4-local) from the same `RecipeApplication` + Phase-4 metadata (`few_shot_ref` from retriever event, `response_id` from leaf event, etc.); emit one `PlanOutcomeEmitted(plan_outcome)` event.
   - Return the projected `RecipeOutcome`.
5. Update the plugin's `transforms()` to return `FallbackTierPlanRecipeEngine` for the `'plan'` slot. Wire dependencies via the existing plugin TCCM (`TaskClassClassifierManifest`) construction path; surface a conflict per Global Rule 7 if the plugin uses a different DI shape.
6. Add a per-variant unit test (`tests/unit/plugin/test_fallback_plan_engine.py`) exhaustively covering the four `RecipeApplication` shapes plus each typed-error projection. Mock `FallbackTier` so the adapter's projection logic is isolated.

## TDD plan — red / green / refactor

### Red — write the failing test first

```python
# tests/unit/plugin/test_fallback_plan_engine.py
from __future__ import annotations
from unittest.mock import AsyncMock, MagicMock
import pytest
from codegenie.plugins.protocols import RecipeEngine, RecipeOutcome
from codegenie.fallback.plan_outcome import PlanOutcome, AppliedFromLlm, Refused
from codegenie.fallback.errors import LeafProtocolViolation, BudgetExceeded, EgressViolation
from plugins.vulnerability_remediation_node_npm.subgraph.fallback_plan_engine import (
    FallbackTierPlanRecipeEngine,
)


def _engine(tier: AsyncMock, event_log: MagicMock) -> FallbackTierPlanRecipeEngine:
    return FallbackTierPlanRecipeEngine(
        retriever=MagicMock(), leaf=MagicMock(), budget=MagicMock(),
        fence=MagicMock(), canary=MagicMock(), provenance=MagicMock(),
        event_log=event_log, prompt_builder=MagicMock(),
        harvester=MagicMock(), confidence_gate=MagicMock(),
    )._with_tier(tier)  # test seam — production uses constructor-built tier


def test_conforms_structurally_to_recipe_engine(stub_tier, event_log):
    engine = _engine(stub_tier, event_log)
    # mypy --strict will reject this assignment if the Protocol doesn't fit:
    re: RecipeEngine = engine
    assert re is engine


async def test_projects_applied_from_llm_to_recipe_outcome_applied(
    stub_tier, event_log, applied_from_llm_recipe_application, repo, plan, cap,
):
    stub_tier.run = AsyncMock(return_value=applied_from_llm_recipe_application)
    out = await _engine(stub_tier, event_log).apply(repo, plan, cap)
    assert isinstance(out, RecipeOutcome.Applied)
    # And one PlanOutcome event of the right variant fired:
    [evt] = [e for e in event_log.events if e.kind == "PlanOutcomeEmitted"]
    assert isinstance(evt.plan_outcome, AppliedFromLlm)


async def test_projects_provenance_refused_to_not_applicable(
    stub_tier, event_log, refused_provenance_recipe_application, repo, plan, cap,
):
    stub_tier.run = AsyncMock(return_value=refused_provenance_recipe_application)
    out = await _engine(stub_tier, event_log).apply(repo, plan, cap)
    assert isinstance(out, RecipeOutcome.NotApplicable)
    assert "PROVENANCE_NOT_APP_LAYER" in out.reason


@pytest.mark.parametrize(
    "exc_cls", [LeafProtocolViolation, BudgetExceeded, EgressViolation],
)
async def test_typed_errors_become_failed(
    exc_cls, stub_tier, event_log, repo, plan, cap,
):
    stub_tier.run = AsyncMock(side_effect=exc_cls("boom"))
    out = await _engine(stub_tier, event_log).apply(repo, plan, cap)
    assert isinstance(out, RecipeOutcome.Failed)
    assert exc_cls.__name__ in out.reason


def test_adapter_does_not_import_sdk():
    import ast, inspect
    from plugins.vulnerability_remediation_node_npm.subgraph import fallback_plan_engine
    src = inspect.getsource(fallback_plan_engine)
    tree = ast.parse(src)
    bad = {"anthropic", "chromadb", "fastembed", "onnxruntime"}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [a.name.split(".")[0] for a in (node.names or [])] + (
                [node.module.split(".")[0]] if isinstance(node, ast.ImportFrom) and node.module else []
            )
            assert not (bad & set(names)), f"forbidden import in adapter: {names}"
```

Run with `pytest tests/unit/plugin/test_fallback_plan_engine.py -v` — all five tests must fail before any implementation lands.

### Green — make it pass

Implement `FallbackTierPlanRecipeEngine` per the Implementation outline. Wire the projection `match` over the `RecipeApplication` variants. Wire `try/except` for typed errors. Emit one `PlanOutcomeEmitted` event per call.

### Refactor — clean up

- Extract the `RecipeApplication → RecipeOutcome` projection into a private free function `_project_to_recipe_outcome(app: RecipeApplication) -> RecipeOutcome` to keep `apply` short. Document the closed mapping table at the top of the module.
- Verify the `match` arms are exhaustive via mypy `--strict` + the `assert_never` arm. Run `make typecheck` and ensure a deliberately-incomplete `match` (try removing one arm) fails the type check.
- Confirm `test_kernel_frozen.py` (from S1-07) is still green after the adapter lands.

## Files to touch

| Path | Why |
|---|---|
| `plugins/vulnerability-remediation--node--npm/subgraph/fallback_plan_engine.py` | New `FallbackTierPlanRecipeEngine` adapter (the load-bearing artifact). |
| `plugins/vulnerability-remediation--node--npm/__init__.py` or plugin entry-point module | Wire `transforms()['plan'] = FallbackTierPlanRecipeEngine` via existing TCCM hook. |
| `tests/unit/plugin/test_fallback_plan_engine.py` | TDD red tests + per-variant projection coverage. |
| `tests/unit/plugin/conftest.py` | Shared fixtures (`stub_tier`, `event_log`, `repo`, `plan`, `cap`, `applied_from_llm_recipe_application`, `refused_provenance_recipe_application`). |

## Out of scope

- Plugin-side `rag_query_builder` (S7-02).
- `vuln_provenance` adapter generalisation (S7-03).
- `plugin.yaml` thresholds and skill templates (S7-04).
- Fixtures (S7-05) and E2E tests (S7-06, S7-07).
- Adversarial corpus (S7-09).
- Final kernel-frozen verification (S7-08) — this story's adapter must not trip the guard, but the guard re-run is its own story.

## Notes for the implementer

- The adapter is the seam where the **Adapter pattern** (toolkit name) is the right call, not GoF inheritance — Phase-3 `RecipeEngine` is a Protocol; structural conformance is the contract.
- The `_with_tier` test seam in the red test above is intentional — production code constructs `FallbackTier` from the constructor args; tests inject a stub `tier` to keep the adapter under isolation. Hide it under a `_TestOnly` marker or use a `MutableMapping`-style override; surface the pattern explicitly so reviewers know it's a deliberate seam.
- The `PlanOutcomeEmitted` event name is canonical for this phase; if Phase 3's `EventLog` requires registering new event kinds in a frozen registry, this story does that addition surgically (no edits to the registry's *interface*).
- Resist threading `BudgetToken` through the adapter — it flows `FallbackTier → LeafLlm.invoke` only (ADR-0010, S2-05 import-linter contract). The adapter constructs the tier with `budget` and forgets about it.
- The "zero edits to `src/codegenie/plugins/protocols.py`" invariant is what makes this story load-bearing for Phase 7. If the implementer is tempted to edit the Protocol to "make the adapter simpler," stop and re-read ADR-0004 + S1-07; surface the conflict per Global Rule 7 before changing anything.
- The deliberate-failure fixture for `assert_never` exhaustiveness (acceptance bullet 7) is one of the highest-leverage tests in the phase — without it, a future implementer adds a fifth `PlanOutcome` variant and the `match` silently degrades to a runtime `UnreachableError`. Pair it with `mypy --strict` in CI.
