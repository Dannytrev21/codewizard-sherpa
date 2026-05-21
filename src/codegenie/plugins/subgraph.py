"""S6-03 — ``SubgraphNode`` Protocol + ``SubgraphState`` (Gap-1 fix).

``phase-arch-design.md §Gap analysis Gap 1`` flagged that the 5-node
remediation subgraph (``ingest_cve → match_recipe → apply_recipe →
stage6_validate → write_branch``) left the per-node transition contract
implicit. This module makes it explicit:

* :class:`SubgraphNode` — a ``@runtime_checkable`` single-method Protocol;
  every node S6-04 builds implements ``async def run(state) -> NodeTransition``.
* :class:`SubgraphState` — the typed, frozen payload :class:`Advance` carries
  between nodes (required ``workflow_id`` / ``cve`` plus six node-populated
  accumulator fields).

The three transitions — :class:`Advance`, :class:`ShortCircuit`,
:class:`Escalate` — are **re-exported** from the canonical declaration site
:mod:`codegenie.transforms.outcomes` (ADR-0010 Amendment 2026-05-18: a single
declaration site per discriminated union). They are NOT redefined here, so
``codegenie.plugins.subgraph.Advance is codegenie.transforms.outcomes.Advance``.

PEP 544 limitation (AC-7 / AC-8): a ``@runtime_checkable`` Protocol checks
attribute *existence* only. ``isinstance(node, SubgraphNode)`` returns
``True`` even for a class whose ``run`` is synchronous, or a class where
``run`` is a non-callable attribute. The coroutine-ness and call signature
of ``run`` are enforced at type-check time by ``mypy --strict`` (see
``tests/unit/plugins/test_subgraph_mypy_negative.py``), not at runtime — do
not add an ``inspect.iscoroutinefunction`` runtime check; Protocols are
structural by design.

ADRs: ADR-0010 (tagged-union sum types; single declaration site), ADR-0010
Amendment 2026-05-19 (this story widens ``Advance.state`` to
:class:`SubgraphState` and ``EscalationReason`` to seven members at the
canonical site), Phase 5 ADR-0006 (Protocol over ABC when there is no
shared default behavior — the Protocol body is ``...``).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict

from codegenie.plugins.bundle import Bundle
from codegenie.plugins.resolver import PluginResolution
from codegenie.transforms.outcomes import (
    Advance,
    Escalate,
    NodeTransition,
    RecipeOutcome,
    ShortCircuit,
    TrustOutcome,
)
from codegenie.transforms.transform import Transform
from codegenie.types.identifiers import BranchName, CveId, WorkflowId

__all__ = [
    "Advance",
    "Escalate",
    "NodeTransition",
    "ShortCircuit",
    "SubgraphNode",
    "SubgraphState",
]


class SubgraphState(BaseModel):
    """Typed payload threaded through the 5-node remediation subgraph.

    ``workflow_id`` and ``cve`` are required at construction. The six
    accumulator fields default to ``None`` and are populated as the subgraph
    advances — each by the node named below:

    * ``resolution`` — ``IngestCveNode`` (the plugin resolution)
    * ``bundle`` — the post-resolution bundle build
    * ``recipe_outcome`` — ``MatchRecipeNode``
    * ``transform`` — ``ApplyRecipeNode``
    * ``trust_outcome`` — ``Stage6ValidateNode``
    * ``branch`` — ``WriteBranchNode``

    Nodes never mutate the state in place; they advance it with
    ``model_copy(update={...})`` (ADR-0010 frozen-state discipline).

    ``arbitrary_types_allowed=True`` is required because ``transform`` is
    typed against :class:`~codegenie.transforms.transform.Transform`, an
    ``abc.ABC`` rather than a Pydantic model — Pydantic validates it with an
    ``isinstance`` check. This mirrors the ``ConcreteResolution`` precedent
    in :mod:`codegenie.plugins.resolver`, which carries an ``Adapter``
    Protocol field under the same config.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    workflow_id: WorkflowId
    cve: CveId
    resolution: PluginResolution | None = None
    bundle: Bundle | None = None
    recipe_outcome: RecipeOutcome | None = None
    transform: Transform | None = None
    trust_outcome: TrustOutcome | None = None
    branch: BranchName | None = None


@runtime_checkable
class SubgraphNode(Protocol):
    """Per-node contract for the remediation subgraph.

    Each node consumes the accumulated :class:`SubgraphState` and returns
    exactly one :data:`NodeTransition`: ``Advance`` (run the next node),
    ``ShortCircuit`` (stop the outer loop and emit the outcome), or
    ``Escalate`` (promote the workflow to human review). The orchestrator's
    outer loop is a single ``match`` over the three transitions; Phase 6's
    LangGraph migration lifts each ``match`` arm to one edge type.
    """

    async def run(self, state: SubgraphState) -> NodeTransition: ...


# ``Advance.state`` is annotated with :class:`SubgraphState` at the canonical
# declaration site (``codegenie.transforms.outcomes``), where the name is a
# ``TYPE_CHECKING``-only forward reference (importing it at runtime would close
# an ``outcomes ↔ subgraph`` cycle). ``model_rebuild`` re-evaluates that
# forward reference now that ``SubgraphState`` is in scope.
Advance.model_rebuild()
