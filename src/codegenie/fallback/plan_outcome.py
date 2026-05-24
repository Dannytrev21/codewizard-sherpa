"""Phase 4 S1-03 — ``PlanOutcome`` wraps Phase-3 ``RecipeOutcome``.

ADR-0004 (composition over union-widening): rather than widening Phase-3's
``RecipeOutcome`` with new variants like ``MatchedFromRag`` /
``ReplannedByLlm`` — which would force ``case``-arm edits across Phase-3/4/5/6
files and break Phase-7's "diff touches only the new plugin directory" exit
criterion — Phase 4 introduces a *local* sum type that wraps the foreign
outcome by digest.

``FallbackTier.run`` continues returning the Phase-3 ``RecipeApplication``;
``PlanOutcome`` is consumed only by event emission and the inline harvester.
The coupling between ``AppliedFromRecipe`` / ``AppliedFromLlm`` and the
underlying ``RecipeOutcome.Applied`` is by **BLAKE3 digest**
(``recipe_outcome_digest: BlobDigest``) — never by embedding the foreign
instance, which would couple Phase 4 to Phase 3's serialization shape.

The load-bearing assurance is
``tests/property/test_plan_outcome_no_recipe_outcome_widening.py`` — an
AST walk asserting Phase-3's ``RecipeOutcome`` variant set is byte-identical
to the snapshot at ``tests/property/_recipe_outcome_phase3_snapshot.txt``.

Sources:
- ``docs/phases/04-vuln-llm-fallback-rag/ADRs/0004-plan-outcome-wraps-recipe-outcome.md``
- ``docs/phases/04-vuln-llm-fallback-rag/ADRs/0001-plan-proposal-closed-sum-type.md``
- ``docs/production/adrs/0033-domain-modeling-discipline.md``
"""

from __future__ import annotations

from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from codegenie.types.identifiers import BlobDigest, LeafResponseId, SolvedExampleId

_FROZEN_FORBID: Final[ConfigDict] = ConfigDict(frozen=True, extra="forbid")
"""Single-source the variant config: frozen instances + strict extra-key
rejection. Every ``PlanOutcome`` variant references this constant (F12) —
matches the ``fallback/`` convention established by ``plan_proposal.py``."""


class AppliedFromRecipe(BaseModel):
    """Emitted when ``FallbackTier`` dispatched the recipe-tier path and the
    Phase-3 engine produced ``RecipeOutcome.Applied``. ADR-0004."""

    model_config = _FROZEN_FORBID
    kind: Literal["recipe"] = "recipe"
    recipe_outcome_digest: BlobDigest


class AppliedFromLlm(BaseModel):
    """Emitted when ``FallbackTier`` escalated to the LLM tier and the LLM
    proposed a plan that the recipe engine subsequently applied. ADR-0004.

    ``few_shot_ref`` is ``None`` when the LLM answered cold (no RAG hit);
    the inline harvester gates on the high-confidence test (S6-03) rather
    than on the presence of a RAG anchor."""

    model_config = _FROZEN_FORBID
    kind: Literal["llm"] = "llm"
    recipe_outcome_digest: BlobDigest
    few_shot_ref: SolvedExampleId | None
    response_id: LeafResponseId


class RagOnlyApplicable(BaseModel):
    """Emitted when RAG retrieval surfaced a high-confidence solved example
    but the recipe path declined to apply — the few-shot match is logged for
    audit but no transform is produced. ADR-0004."""

    model_config = _FROZEN_FORBID
    kind: Literal["rag_only"] = "rag_only"
    few_shot_ref: SolvedExampleId


class Refused(BaseModel):
    """Emitted when the fallback tier refuses to act. ``reason`` is a closed
    four-member ``Literal``: provenance gating, budget guard, leaf refusal,
    leaf schema violation. Adding a fifth reason is an ADR amendment per
    ADR-0001 §Reversibility. ADR-0004."""

    model_config = _FROZEN_FORBID
    kind: Literal["refused"] = "refused"
    reason: Literal[
        "PROVENANCE_NOT_APP_LAYER",
        "BUDGET_EXCEEDED",
        "LEAF_REFUSED",
        "LEAF_SCHEMA_VIOLATION",
    ]


PlanOutcome = Annotated[
    AppliedFromRecipe | AppliedFromLlm | RagOnlyApplicable | Refused,
    Field(discriminator="kind"),
]
"""Phase-4-local sum type — composition wrapper around Phase-3 ``RecipeOutcome``.

Consumed only by event emission and the inline harvester; ``FallbackTier.run``
returns the Phase-3 ``RecipeApplication``. Every consumer ``match``-es with
``assert_never`` in the default arm — mypy ``--strict`` is the only place
exhaustiveness is enforced.

The discriminator idiom is the codebase-wide convention (``Field(discriminator=
"kind")`` — every umbrella in ``codegenie/transforms/outcomes.py``, plus the
HARDENED sibling ``plan_proposal.py``; Rule 11 mandates conformance). The
arch doc and ADR-0004 show ``Discriminator("kind")`` — that is a known
transcription error (S1-02 F2 / S1-03 F4)."""
