"""Phase-4 fallback package — LLM-fallback + solved-example RAG.

S1-02 shipped the closed ``PlanProposal`` discriminated union (the LLM emits
exactly one of four named shapes; ``TypeAdapter(PlanProposal).json_schema()``
is passed as ``response_format`` so an injected LLM cannot structurally emit
a shell command or unfenced markdown) and its two smart-constructor newtypes
(``UnifiedDiff``, ``SandboxedRelativePath``).

S1-03 adds the Phase-4-local ``PlanOutcome`` sum type — a composition wrapper
that *wraps* Phase-3's ``RecipeOutcome`` (by BLAKE3 digest) rather than
widening it. Consumed only by event emission and the inline harvester; the
load-bearing fence at
``tests/property/test_plan_outcome_no_recipe_outcome_widening.py`` guarantees
Phase-3's ``RecipeOutcome`` variant set stays frozen so Phase 7's "diff
touches only the new plugin directory" exit criterion holds.

See:
- ``docs/phases/04-vuln-llm-fallback-rag/ADRs/0001-plan-proposal-closed-sum-type.md``
- ``docs/phases/04-vuln-llm-fallback-rag/ADRs/0004-plan-outcome-wraps-recipe-outcome.md``
"""

from __future__ import annotations

from codegenie.fallback.budget import BudgetSnapshot, BudgetToken
from codegenie.fallback.plan_outcome import (
    AppliedFromLlm,
    AppliedFromRecipe,
    PlanOutcome,
    RagOnlyApplicable,
    Refused,
)
from codegenie.fallback.plan_proposal import (
    PlanProposal,
    PlanProposalCallsiteRewrite,
    PlanProposalDepBump,
    PlanProposalOverride,
    PlanProposalRefuse,
    SandboxedRelativePath,
    UnifiedDiff,
)

__all__ = (
    "AppliedFromLlm",
    "AppliedFromRecipe",
    "BudgetSnapshot",
    "BudgetToken",
    "PlanOutcome",
    "PlanProposal",
    "PlanProposalCallsiteRewrite",
    "PlanProposalDepBump",
    "PlanProposalOverride",
    "PlanProposalRefuse",
    "RagOnlyApplicable",
    "Refused",
    "SandboxedRelativePath",
    "UnifiedDiff",
)
