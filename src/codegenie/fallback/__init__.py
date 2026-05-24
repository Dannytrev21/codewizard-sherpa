"""Phase-4 fallback package — LLM-fallback + solved-example RAG.

The package surface is intentionally narrow at S1-02: the closed
``PlanProposal`` discriminated union and its two smart-constructor newtypes
(``UnifiedDiff``, ``SandboxedRelativePath``). Every later Phase-4 module
(prompt builder, leaf-LLM port, fallback tier) consumes this typed shape;
the Anthropic SDK is passed ``TypeAdapter(PlanProposal).json_schema()`` as
``response_format`` so an injected LLM cannot structurally emit a shell
command or unfenced markdown.

See ``docs/phases/04-vuln-llm-fallback-rag/ADRs/0001-plan-proposal-closed-sum-type.md``.
"""

from __future__ import annotations

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
    "PlanProposal",
    "PlanProposalCallsiteRewrite",
    "PlanProposalDepBump",
    "PlanProposalOverride",
    "PlanProposalRefuse",
    "SandboxedRelativePath",
    "UnifiedDiff",
)
