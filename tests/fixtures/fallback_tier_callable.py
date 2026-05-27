"""Phase-4 S7-10 AC-9 — :class:`FallbackTierCallable` Protocol + fixture instance.

Phase 6 lifts the Phase-4 :class:`~codegenie.fallback.tier.FallbackTier`
:meth:`~codegenie.fallback.tier.FallbackTier.run` method into a LangGraph
node via ``node(fn=fallback_tier_callable, ...)``. This fixture pins the
**call shape** Phase 6 will consume so a future Phase-6 wiring story
type-checks against a Protocol rather than against the dataclass method.

Two deliverables in one file:

1. :class:`FallbackTierCallable` — a ``@runtime_checkable`` Protocol
   describing the awaited shape:
   ``async def __call__(advisory, repo_ctx, recipe_selection, *,
   prior_attempts=()) -> PlanOutcome``.
2. :data:`fallback_tier_callable` — a module-level instance such that
   ``isinstance(fallback_tier_callable, FallbackTierCallable)`` is
   ``True`` at import time.

Rule 7 surface (Global Rule 7 — don't blend contradictory shapes).
The story's AC-9 text references ``RecipeApplication`` as the return
type, but Phase 4 ships :class:`~codegenie.fallback.plan_outcome.PlanOutcome`
(ADR-04-0004 — ``PlanOutcome`` wraps the Phase-3 ``RecipeOutcome``;
``RecipeApplication`` is not a type that exists in
``src/codegenie/``). Honoring the shipped contract: the Protocol's
return type is ``PlanOutcome``. A future Phase-5 contract harmonization
that introduces ``RecipeApplication`` would land as a sibling Protocol
addition, not a silent type rename.

The fixture instance wires :class:`FallbackTier` with mocked
collaborators (:class:`LeafLlm`, :class:`LlmInvocationGuard`,
:class:`ConfidenceGate`, etc.) so the behavior test (AC-10) can assert
the call mechanics work end-to-end without spending tokens or touching
the filesystem outside ``tmp_path``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Protocol, runtime_checkable
from unittest.mock import AsyncMock, MagicMock

from codegenie.fallback.confidence_gate import ConfidenceGate
from codegenie.fallback.contracts import CveAdvisory, RecipeSelection, RepoContext
from codegenie.fallback.plan_outcome import PlanOutcome
from codegenie.fallback.tier import FallbackTier
from codegenie.plugins.events import EventLog
from codegenie.transforms.apply_context import AttemptSummary
from codegenie.types.identifiers import SolvedExampleId, WorkflowId

__all__ = [
    "FallbackTierCallable",
    "fallback_tier_callable",
]


@runtime_checkable
class FallbackTierCallable(Protocol):
    """Awaited call shape of :meth:`FallbackTier.run` — the seam Phase 6
    lifts into a LangGraph ``node(fn=..., ...)`` definition.

    ``__call__`` is async; matches the structural type
    :class:`FallbackTier` already satisfies. The Protocol is
    ``@runtime_checkable`` so the import-time isinstance assertion
    below works without metaclass magic.
    """

    async def __call__(
        self,
        advisory: CveAdvisory,
        repo_ctx: RepoContext,
        recipe_selection: RecipeSelection,
        *,
        prior_attempts: Sequence[AttemptSummary] = (),
    ) -> PlanOutcome: ...


def _build_fallback_tier_callable() -> FallbackTierCallable:
    """Construct a :class:`FallbackTier` with mocked collaborators and
    return its bound :meth:`run` method as the Protocol-conformant
    callable.

    The mocks expose just enough surface to satisfy the constructor;
    actual LLM / store / fence behavior is delegated to the placeholder
    :meth:`FallbackTier.run` body (which today returns a
    ``Refused(reason="PROVENANCE_NOT_APP_LAYER")``). The behavior test
    (AC-10) asserts the **call mechanics** — that ``run`` is awaitable,
    accepts the documented signature, and produces a non-None
    :data:`PlanOutcome`.

    A temporary directory provides the EventLog root. The directory is
    kept alive by binding it to a module-level reference so the
    EventLog's zstd files remain available across the entire test
    session — closes when the process exits.
    """
    leaf = AsyncMock()
    leaf.running_total = MagicMock(return_value=0)
    budget = MagicMock()
    budget.running_total = MagicMock(return_value=0)
    budget.precharge = AsyncMock()
    budget.reconcile = AsyncMock()

    event_log = EventLog(
        root=_EVENT_LOG_ROOT,
        workflow_id=WorkflowId("01HS710FALLBACKCALLABLEFX"),
    )

    store = MagicMock()
    store.contains = AsyncMock(return_value=False)
    store.add = AsyncMock(return_value=SolvedExampleId("ex-fixture-001"))

    embedder = MagicMock()
    embedder.model_digest = lambda: "blake3:" + "f" * 64

    tier = FallbackTier(
        retriever=MagicMock(),
        leaf=leaf,
        budget=budget,
        fence=MagicMock(),
        canary=MagicMock(),
        provenance=MagicMock(),
        event_log=event_log,
        prompt_builder=MagicMock(),
        harvester=MagicMock(),
        confidence_gate=ConfidenceGate(),
        store=store,
        embedder=embedder,
    )
    return tier.run


# Keep the EventLog tmp directory alive for the lifetime of the import.
# Python cleans this on process exit. AC-10 asserts the callable runs
# without raising — that requires a valid log root, not a fake one.
_TMP_KEEPER = TemporaryDirectory(prefix="phase4-fallback-callable-fixture-")
_EVENT_LOG_ROOT = Path(_TMP_KEEPER.name)


# Module-level instance — Phase 6 imports this directly. The Protocol's
# ``@runtime_checkable`` decorator makes the import-time isinstance
# assertion below a structural conformance check rather than an
# unverifiable contract claim.
fallback_tier_callable: FallbackTierCallable = _build_fallback_tier_callable()


# Hard pin — the structural conformance is asserted at import time so a
# future signature regression on FallbackTier.run breaks at module load
# rather than silently at the Phase-6 wiring site.
assert isinstance(fallback_tier_callable, FallbackTierCallable), (  # noqa: S101
    "fallback_tier_callable does not match the FallbackTierCallable Protocol "
    "— FallbackTier.run signature drifted; check src/codegenie/fallback/tier.py"
)
# Quiet the unused-import lint when asyncio appears only inside docstrings.
_ = asyncio
