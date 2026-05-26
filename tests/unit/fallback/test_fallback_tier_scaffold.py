"""Phase-4 S6-01 GREEN-partial — :class:`FallbackTier` scaffold contract.

Pins the structural shape every downstream story (S6-02/S6-03/S6-07/
S6-08, S7-01..S7-10) reads against. The full 9-step dispatch +
4-refuse-paths + 10-event happy-path tape land in the S6-01 completion
session (documented in `_attempts/S6-01.md`).
"""

from __future__ import annotations

import inspect
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from codegenie.fallback.plan_outcome import Refused
from codegenie.fallback.plan_proposal import (
    PlanProposalCallsiteRewrite,
    PlanProposalDepBump,
    PlanProposalOverride,
    PlanProposalRefuse,
)
from codegenie.fallback.tier import FallbackTier, transform_from_plan
from codegenie.plugins.events import EventLog, PlanOutcomeEmitted
from codegenie.types.identifiers import (
    CveId,
    PackageId,
    SemverVersion,
    WorkflowId,
)


def _make_tier(tmp_path: Path) -> FallbackTier:
    """Build a FallbackTier with mock collaborators for shape testing."""
    from codegenie.fallback.confidence_gate import ConfidenceGate

    event_log = EventLog(root=tmp_path, workflow_id=WorkflowId("01HS601SCAFFOLDTESTWX0001"))
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


# --- Structural-shape tests ------------------------------------------------


def test_fallback_tier_is_frozen_dataclass(tmp_path: Path) -> None:
    """FallbackTier is a frozen dataclass — mutation post-construction raises."""
    import dataclasses

    tier = _make_tier(tmp_path)
    assert dataclasses.is_dataclass(FallbackTier)
    assert FallbackTier.__dataclass_params__.frozen is True  # type: ignore[attr-defined]
    with pytest.raises(Exception):  # noqa: B017
        tier.event_log = MagicMock()  # type: ignore[misc]


def test_fallback_tier_constructor_shape_matches_arch_component_1(
    tmp_path: Path,
) -> None:
    """Constructor signature: 7 positional substrate collaborators +
    3 keyword-only Phase-4 newcomers. ADR-0002 §Reversibility commits
    to this shape — Phase-6 LangGraph migration wraps each as a node
    1-to-1."""
    sig = inspect.signature(FallbackTier)
    params = sig.parameters
    expected_positional = (
        "retriever",
        "leaf",
        "budget",
        "fence",
        "canary",
        "provenance",
        "event_log",
    )
    expected_kw_only = ("prompt_builder", "harvester", "confidence_gate")
    for name in expected_positional:
        assert name in params, f"missing positional collaborator {name!r}"
    for name in expected_kw_only:
        assert name in params, f"missing kw-only collaborator {name!r}"
        assert params[name].kind is inspect.Parameter.KEYWORD_ONLY


def test_run_signature_has_immutable_empty_tuple_default(tmp_path: Path) -> None:
    """`prior_attempts` defaults to `()` (immutable empty tuple) — no
    mutable-default footgun. `Sequence` is read-covariant."""
    sig = inspect.signature(FallbackTier.run)
    p = sig.parameters["prior_attempts"]
    assert p.default == (), f"prior_attempts default must be the empty tuple, got {p.default!r}"
    assert p.kind is inspect.Parameter.KEYWORD_ONLY


def test_on_validated_signature_is_async_kw_context(tmp_path: Path) -> None:
    """S6-03 AC-1 — `on_validated(outcome, trust, *, context)` async signature."""
    sig = inspect.signature(FallbackTier.on_validated)
    params = list(sig.parameters)
    assert params == ["self", "outcome", "trust", "context"]
    assert sig.parameters["context"].kind is inspect.Parameter.KEYWORD_ONLY
    assert inspect.iscoroutinefunction(FallbackTier.on_validated)


def test_run_returns_a_typed_plan_outcome(tmp_path: Path) -> None:
    """`run` returns a :data:`PlanOutcome` variant — never `Optional`,
    never `dict`. GREEN-partial scaffold returns the
    `PROVENANCE_NOT_APP_LAYER` placeholder until the full dispatch lands.
    """
    import asyncio

    from codegenie.fallback.contracts import (
        CveAdvisory,
        RecipeSelection,
        RepoContext,
    )

    tier = _make_tier(tmp_path)
    advisory = CveAdvisory(
        cve_id=CveId("CVE-2026-TEST0001"),
        affected_package=PackageId("test@1.0.0"),
        description="placeholder",
    )
    repo_ctx = RepoContext(repo_root="/tmp/repo")
    recipe = RecipeSelection(recipe_name="npm_dep_bump", build_system="npm")

    async def _run() -> object:
        return await tier.run(advisory, repo_ctx, recipe)

    outcome = asyncio.run(_run())
    assert isinstance(outcome, Refused)
    assert outcome.reason == "PROVENANCE_NOT_APP_LAYER"


def test_run_emits_plan_outcome_emitted_event(tmp_path: Path) -> None:
    """Every `run` invocation emits a terminal :class:`PlanOutcomeEmitted`
    carrying the typed :data:`PlanOutcome` discriminated-union payload."""
    import asyncio

    from codegenie.fallback.contracts import (
        CveAdvisory,
        RecipeSelection,
        RepoContext,
    )

    tier = _make_tier(tmp_path)
    advisory = CveAdvisory(
        cve_id=CveId("CVE-2026-TEST0002"),
        affected_package=PackageId("test@1.0.0"),
        description="placeholder",
    )
    repo_ctx = RepoContext(repo_root="/tmp/repo")
    recipe = RecipeSelection(recipe_name="npm_dep_bump", build_system="npm")

    async def _run() -> None:
        await tier.run(advisory, repo_ctx, recipe)

    asyncio.run(_run())
    tier.event_log.flush()  # type: ignore[attr-defined]
    events = list(tier.event_log.replay())  # type: ignore[attr-defined]
    plan_outcome_events = [e for e in events if isinstance(e, PlanOutcomeEmitted)]
    assert len(plan_outcome_events) == 1
    assert plan_outcome_events[0].outcome_kind == "refused"


# --- transform_from_plan exhaustiveness ------------------------------------


def test_transform_from_plan_handles_dep_bump() -> None:
    plan = PlanProposalDepBump(
        manifest_path="package.json",
        package=PackageId("a@1.0.0"),
        target_version=SemverVersion("1.0.1"),
        rationale="patch",
    )
    assert transform_from_plan(plan).plan_kind == "dep_bump"


def test_transform_from_plan_handles_override() -> None:
    plan = PlanProposalOverride(
        manifest_path="package.json",
        package=PackageId("a@1.0.0"),
        forced_version=SemverVersion("1.0.1"),
        rationale="override",
    )
    assert transform_from_plan(plan).plan_kind == "override"


def test_transform_from_plan_handles_callsite_rewrite() -> None:
    plan = PlanProposalCallsiteRewrite(
        manifest_path="package.json",
        files=["src/x.ts"],
        diff="--- a/src/x.ts\n+++ b/src/x.ts\n@@ -1,1 +1,1 @@\n-old\n+new\n",
        rationale="rewrite",
    )
    assert transform_from_plan(plan).plan_kind == "callsite_rewrite"


def test_transform_from_plan_handles_refuse() -> None:
    plan = PlanProposalRefuse(
        reason="out_of_scope",
        rationale="no safe patch found",
    )
    assert transform_from_plan(plan).plan_kind == "refuse"
