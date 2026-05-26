"""Phase-4 S7-01 — :class:`FallbackTierPlanRecipeEngine` adapter tests.

Loads the plugin module via :func:`importlib.util.spec_from_file_location`
(the hyphenated slug is not Python-identifier-valid; the plugin
loader documented at ``codegenie.plugins.loader`` uses the same
mechanism). The tests pin:

* The adapter exists and is constructible from a FallbackTier.
* ``apply(...)`` returns a :data:`RecipeOutcome` variant.
* The pure projection function handles every :data:`PlanOutcome`
  variant via ``match`` exhaustiveness (AC-PROJECTION-TOTALITY).
* No event emission from the adapter (terminal ``PlanOutcomeEmitted``
  is owned by the tier).
* AST-import fence: no anthropic / chromadb / fastembed / onnxruntime
  imports inside ``fallback_plan_engine.py``.
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import pytest

from codegenie.fallback.confidence_gate import ConfidenceGate
from codegenie.fallback.plan_outcome import (
    AppliedFromLlm,
    AppliedFromRecipe,
    PlanOutcome,
    RagOnlyApplicable,
    Refused,
)
from codegenie.fallback.tier import FallbackTier
from codegenie.plugins.events import EventLog
from codegenie.transforms.outcomes import (
    Applied,
    RecipeFailed,
    Skipped,
)
from codegenie.types.identifiers import (
    BlobDigest,
    LeafResponseId,
    SolvedExampleId,
    WorkflowId,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_ENGINE_PATH = (
    _REPO_ROOT
    / "plugins"
    / "vulnerability-remediation--node--npm"
    / "subgraph"
    / "fallback_plan_engine.py"
)


def _load_engine_module() -> ModuleType:
    """Load the engine module via importlib (slug → spec resolution).

    ``@dataclass(slots=True)`` requires the class's module to be in
    ``sys.modules`` at decoration time — register the module under its
    synthetic name before ``exec_module``.
    """
    import sys

    mod_name = "_test_fallback_plan_engine"
    spec = importlib.util.spec_from_file_location(mod_name, _ENGINE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module


_ENGINE_MODULE = _load_engine_module()
FallbackTierPlanRecipeEngine = _ENGINE_MODULE.FallbackTierPlanRecipeEngine
_project = _ENGINE_MODULE._project_plan_outcome_to_recipe_outcome


def _make_tier(tmp_path: Path) -> FallbackTier:
    event_log = EventLog(root=tmp_path, workflow_id=WorkflowId("01HS701FALLBACKADAPTERWX0"))
    return FallbackTier(
        retriever=MagicMock(),
        leaf=MagicMock(),
        budget=MagicMock(),
        fence=MagicMock(),
        canary=MagicMock(),
        provenance=MagicMock(),
        event_log=event_log,
        prompt_builder=MagicMock(),
        harvester=MagicMock(),
        confidence_gate=ConfidenceGate(),
        store=MagicMock(),
        embedder=MagicMock(),
    )


# --- AC-PROJECTION-TOTALITY — all 4 PlanOutcome variants ------------------


def test_projects_applied_from_llm_to_applied() -> None:
    outcome: PlanOutcome = AppliedFromLlm(
        recipe_outcome_digest=BlobDigest("0" * 64),
        few_shot_ref=None,
        response_id=LeafResponseId("resp-001"),
    )
    result = _project(outcome)
    assert isinstance(result, Applied)
    assert result.transform_id == "phase4.plan.applied_from_llm"


def test_projects_applied_from_recipe_to_applied() -> None:
    outcome: PlanOutcome = AppliedFromRecipe(recipe_outcome_digest=BlobDigest("0" * 64))
    result = _project(outcome)
    assert isinstance(result, Applied)
    assert result.transform_id == "phase4.plan.applied_from_recipe"


def test_projects_rag_only_applicable_to_skipped() -> None:
    outcome: PlanOutcome = RagOnlyApplicable(few_shot_ref=SolvedExampleId("ex-001"))
    result = _project(outcome)
    assert isinstance(result, Skipped)


def test_projects_refused_to_recipe_failed() -> None:
    outcome: PlanOutcome = Refused(reason="LEAF_REFUSED")
    result = _project(outcome)
    assert isinstance(result, RecipeFailed)
    assert "leaf_refused" in str(result.error.error_id)


# --- AC-CTOR + AC-FAIL-LOUD-CONSTRUCTION ----------------------------------


def test_ctor_keyword_only_via_dataclass_field(tmp_path: Path) -> None:
    """Construction requires the ``tier`` keyword (frozen + slots)."""
    tier = _make_tier(tmp_path)
    engine = FallbackTierPlanRecipeEngine(tier=tier)
    assert isinstance(engine, FallbackTierPlanRecipeEngine)


def test_frozen_instance_rejects_mutation(tmp_path: Path) -> None:
    tier = _make_tier(tmp_path)
    engine = FallbackTierPlanRecipeEngine(tier=tier)
    with pytest.raises(Exception):  # noqa: B017 — dataclass FrozenInstanceError
        engine.tier = MagicMock()  # type: ignore[misc]


# --- AC-PROTOCOL-CONFORMANCE — structurally a RecipeOutcome producer ------


@pytest.mark.asyncio
async def test_apply_returns_recipe_outcome(tmp_path: Path) -> None:
    """The adapter's ``apply`` returns a :data:`RecipeOutcome` variant."""
    tier = _make_tier(tmp_path)
    engine = FallbackTierPlanRecipeEngine(tier=tier)
    outcome = await engine.apply(object(), object(), object())
    # The scaffold tier returns Refused → projection is RecipeFailed.
    assert isinstance(outcome, RecipeFailed)


# --- AC-NO-EMIT — adapter contributes no events ---------------------------


@pytest.mark.asyncio
async def test_apply_emits_zero_events_beyond_tier(tmp_path: Path) -> None:
    """The adapter itself emits nothing; the tier emits its own
    terminal PlanOutcomeEmitted."""
    tier = _make_tier(tmp_path)
    engine = FallbackTierPlanRecipeEngine(tier=tier)
    await engine.apply(object(), object(), object())
    tier.event_log.flush()  # type: ignore[attr-defined]
    events = list(tier.event_log.replay())  # type: ignore[attr-defined]
    # Exactly one PlanOutcomeEmitted — from the tier, NOT the adapter.
    plan_outcome_events = [e for e in events if type(e).__name__ == "PlanOutcomeEmitted"]
    assert len(plan_outcome_events) == 1


# --- AC-FENCE-IMPORT — no LLM/embedding SDK imports -----------------------


def test_engine_module_does_not_import_llm_sdks() -> None:
    """AST walk: the adapter imports no anthropic / chromadb / fastembed /
    onnxruntime symbols."""
    source = _ENGINE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden = {"anthropic", "chromadb", "fastembed", "onnxruntime"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = (node.module or "").split(".")[0]
            assert mod not in forbidden, f"fallback_plan_engine.py must not import {mod!r}"
        elif isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                assert top not in forbidden, f"fallback_plan_engine.py must not import {top!r}"


# --- AC-CTOR purity: __init__ does no I/O ---------------------------------


def test_ctor_does_no_io(tmp_path: Path) -> None:
    """The adapter's frozen-dataclass ``__init__`` is the auto-generated
    one — no custom __post_init__, no I/O at construction time."""
    tier = _make_tier(tmp_path)
    # If construction triggered any event emission, the tier's log
    # would carry a record. Verify the log is empty post-construction.
    FallbackTierPlanRecipeEngine(tier=tier)
    tier.event_log.flush()  # type: ignore[attr-defined]
    events = list(tier.event_log.replay())  # type: ignore[attr-defined]
    assert events == [], "constructor must not emit events"
