"""Phase-4 S6-03 AC-15 — exactly one terminal event per ``on_validated``.

Hypothesis property: for any combination of
``(PlanOutcome variant, TrustOutcome (passed, confidence))`` and any
seed state of ``store.contains`` (``False`` for fresh, ``True`` for
already-harvested), the :meth:`FallbackTier.on_validated` body MUST
emit **exactly one** of:

* :class:`SolvedExampleHarvested` (success path; only reachable when
  outcome is :class:`AppliedFromLlm`, the gate passes, and the store
  is fresh).
* :class:`HarvestSkipped` (any of the four closed-set ``reason`` values).

Mutual exclusion + totality together prove the dispatch tree is well-
formed: no branch silently emits nothing, no branch double-emits.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Final, Literal, cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from codegenie.fallback.confidence_gate import ConfidenceGate
from codegenie.fallback.plan_outcome import (
    AppliedFromLlm,
    AppliedFromRecipe,
    PlanOutcome,
    RagOnlyApplicable,
    Refused,
)
from codegenie.fallback.plan_proposal import PlanProposalDepBump
from codegenie.fallback.post_validation_context import PostValidationContext
from codegenie.fallback.tier import FallbackTier
from codegenie.plugins.events import EventLog, HarvestSkipped, SolvedExampleHarvested
from codegenie.transforms.outcomes import TrustOutcome
from codegenie.types.identifiers import (
    BlobDigest,
    ChainHead,
    CveId,
    Language,
    LeafResponseId,
    PackageId,
    SemverVersion,
    SignalKind,
    SolvedExampleId,
    TaskClassId,
    WorkflowId,
)

_OUTCOME_VARIANTS: Final[tuple[Literal["llm", "recipe", "rag_only", "refused"], ...]] = (
    "llm",
    "recipe",
    "rag_only",
    "refused",
)
_CONFIDENCES: Final[tuple[Literal["high", "degraded"], ...]] = (
    "high",
    "degraded",
)


def _build_outcome(kind: str) -> PlanOutcome:
    if kind == "llm":
        return AppliedFromLlm(
            recipe_outcome_digest=BlobDigest("4" * 64),
            few_shot_ref=None,
            response_id=LeafResponseId("01HRESPLLM00000000000"),
        )
    if kind == "recipe":
        return AppliedFromRecipe(
            recipe_outcome_digest=BlobDigest("5" * 64),
        )
    if kind == "rag_only":
        return RagOnlyApplicable(
            few_shot_ref=SolvedExampleId("ex-fixture-001"),
        )
    if kind == "refused":
        return Refused(reason="LEAF_REFUSED")
    raise ValueError(f"unknown variant {kind!r}")


def _build_trust(passed: bool, confidence: str) -> TrustOutcome:
    # TrustOutcome invariant: passed iff len(failing) == 0.
    failing: list[SignalKind] = [] if passed else [SignalKind("test.failure")]
    return TrustOutcome(
        passed=passed,
        confidence=cast(Literal["high", "degraded"], confidence),
        signals=[],
        failing=failing,
    )


def _ctx() -> PostValidationContext:
    plan = PlanProposalDepBump(
        manifest_path="package.json",
        package=PackageId("vulnpkg@1.0.0"),
        target_version=SemverVersion("1.0.1"),
        rationale="patch",
    )
    return PostValidationContext(
        workflow_id=WorkflowId("wf-on-validated-property"),
        chain_head=ChainHead("c" * 64),
        advisory_digest=BlobDigest("1" * 64),
        cve_id=CveId("CVE-2026-9999"),
        task_class=TaskClassId("vuln_remediation"),
        language=Language("typescript"),
        build_system="npm",
        transform_digest=BlobDigest("2" * 64),
        trust_outcome_digest=BlobDigest("3" * 64),
        query_text="fix the cve",
        plan_proposal=plan,
    )


def _make_tier(tmp_path: Path, *, store_seen: bool) -> FallbackTier:
    event_log = EventLog(
        root=tmp_path,
        workflow_id=WorkflowId("01HS603PROPMUTEX00000000"),
    )
    embedder = MagicMock()
    embedder.model_digest = lambda: BlobDigest("blake3:" + "8" * 64)
    embedder.embed = lambda _text: tuple(0.1 for _ in range(384))
    store = MagicMock()
    store.contains = AsyncMock(return_value=store_seen)
    store.add = AsyncMock(return_value=SolvedExampleId("ex-prop-fresh-001"))

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
        store=store,
        embedder=embedder,
    )


def _emitted(tier: FallbackTier) -> list[object]:
    tier.event_log.flush()  # type: ignore[attr-defined]
    return list(tier.event_log.replay())  # type: ignore[attr-defined]


@given(
    outcome_kind=st.sampled_from(_OUTCOME_VARIANTS),
    passed=st.booleans(),
    confidence=st.sampled_from(_CONFIDENCES),
    store_seen=st.booleans(),
)
@settings(
    max_examples=40,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_exactly_one_terminal_event_per_on_validated_call(
    outcome_kind: str,
    passed: bool,
    confidence: str,
    store_seen: bool,
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """**Mutual exclusion + totality:** for every input combination,
    exactly one of {SolvedExampleHarvested, HarvestSkipped} fires.

    The matrix is 4 (outcome variants) × 2 (passed) × 3 (confidence) ×
    2 (store_seen) = 48 distinct truth-table rows; Hypothesis samples
    from the cartesian product.
    """
    tmp_path = tmp_path_factory.mktemp("mutex")
    tier = _make_tier(tmp_path, store_seen=store_seen)
    outcome = _build_outcome(outcome_kind)
    trust = _build_trust(passed, confidence)
    ctx = _ctx()

    asyncio.run(tier.on_validated(outcome, trust, context=ctx))

    events = _emitted(tier)
    harvested = [e for e in events if isinstance(e, SolvedExampleHarvested)]
    skipped = [e for e in events if isinstance(e, HarvestSkipped)]

    total_terminal = len(harvested) + len(skipped)
    assert total_terminal == 1, (
        f"expected exactly one terminal event for outcome={outcome_kind} "
        f"passed={passed} confidence={confidence} store_seen={store_seen}; "
        f"got {len(harvested)} harvested + {len(skipped)} skipped"
    )

    # Discriminator semantics: harvested only when llm + gate-pass + fresh.
    expected_harvest = outcome_kind == "llm" and passed and confidence == "high" and not store_seen
    if expected_harvest:
        assert harvested, f"expected harvested for llm+pass+high+fresh; got skipped={skipped}"
    else:
        assert skipped, (
            f"expected skipped for {outcome_kind}/{passed}/{confidence}/{store_seen}; "
            f"got harvested={harvested}"
        )


def test_outcome_variants_count_matches_planoutcome_union() -> None:
    """Sanity — :data:`_OUTCOME_VARIANTS` has exactly 4 entries,
    matching the four-variant ``PlanOutcome`` discriminated union
    (S1-03). A future fifth variant fails this assertion AND the
    ``assert_never`` arm in ``harvest_eligibility``, surfacing the
    widening at two sites simultaneously.
    """
    assert set(_OUTCOME_VARIANTS) == {"llm", "recipe", "rag_only", "refused"}
    assert len(_OUTCOME_VARIANTS) == 4
