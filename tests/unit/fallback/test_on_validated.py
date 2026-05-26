"""Phase-4 S6-03 — :meth:`FallbackTier.on_validated` body tests.

Covers the load-bearing ACs:

* AC-7 — dispatch order: eligibility → gate → mint → ingest → emit.
* AC-12 — mint + ingest NOT called when any precondition fails.
* AC-13 — ``HarvestSkipped`` discriminator membership + closed-set
  ``reason`` enforcement.
* AC-14 — ``SolvedExampleHarvested.solved_example_id`` matches the
  returned id from ``ingest_solved_example``.

Deferred (S6-03 completion follow-ups documented in S6-01 attempt
log): AC-8 idempotence (needs `SolvedExampleStore.contains()` on the
Protocol), AC-15 Hypothesis exactly-one-terminal-event property.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

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
from codegenie.plugins.events import (
    EventLog,
    HarvestSkipped,
    SolvedExampleHarvested,
)
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


def _trust(*, passed: bool, confidence: str) -> TrustOutcome:
    failing: tuple[SignalKind, ...] = () if passed else (SignalKind("test.failure"),)
    return TrustOutcome(
        passed=passed,
        confidence=confidence,  # type: ignore[arg-type]
        signals=(),
        failing=failing,
    )


def _ctx() -> PostValidationContext:
    plan = PlanProposalDepBump(
        manifest_path="package.json",
        package=PackageId("a@1.0.0"),
        target_version=SemverVersion("1.0.1"),
        rationale="patch",
    )
    return PostValidationContext(
        workflow_id=WorkflowId("wf-on-validated-001"),
        chain_head=ChainHead("a" * 64),
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


def _make_tier(
    tmp_path: Path,
    *,
    ingest_return_id: str = "01HSE-ingest-return",
    embedder_digest: str = "blake3:" + "9" * 64,
) -> tuple[FallbackTier, MagicMock]:
    """Build a FallbackTier whose store + embedder are mocks suitable
    for asserting call shape. Returns (tier, ingest_spy)."""
    event_log = EventLog(
        root=tmp_path,
        workflow_id=WorkflowId("01HS603ONVALIDATEDTESTWX0"),
    )
    embedder = MagicMock()
    embedder.model_digest = lambda: BlobDigest(embedder_digest)
    embedder.embed = lambda _text: tuple(0.1 for _ in range(384))
    store = MagicMock()
    # AC-8 idempotence pre-check — default to "not contained" so existing
    # happy-path tests exercise the new harvest flow rather than the
    # already_harvested branch.
    store.contains = AsyncMock(return_value=False)
    ingest_spy: MagicMock = MagicMock()
    store.add = AsyncMock(return_value=SolvedExampleId(ingest_return_id))

    def _track_add(example, capability):  # type: ignore[no-untyped-def]
        ingest_spy(example=example, capability=capability)
        return SolvedExampleId(ingest_return_id)

    store.add = AsyncMock(side_effect=_track_add)
    tier = FallbackTier(
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
    return tier, ingest_spy


def _emitted(tier: FallbackTier) -> list[object]:
    tier.event_log.flush()  # type: ignore[attr-defined]
    return list(tier.event_log.replay())  # type: ignore[attr-defined]


# --- Happy path -----------------------------------------------------------


@pytest.mark.asyncio
async def test_happy_path_emits_solved_example_harvested(tmp_path: Path) -> None:
    """AC-7 + AC-14 — gate passes + eligible outcome → ingest called +
    SolvedExampleHarvested emitted with the returned id."""
    tier, ingest_spy = _make_tier(tmp_path, ingest_return_id="01HSE-pinned-id")
    outcome: PlanOutcome = AppliedFromLlm(
        recipe_outcome_digest=BlobDigest("0" * 64),
        few_shot_ref=None,
        response_id=LeafResponseId("resp-001"),
    )
    trust = _trust(passed=True, confidence="high")

    await tier.on_validated(outcome, trust, context=_ctx())

    ingest_spy.assert_called_once()
    events = _emitted(tier)
    harvest_events = [e for e in events if isinstance(e, SolvedExampleHarvested)]
    skip_events = [e for e in events if isinstance(e, HarvestSkipped)]
    assert len(harvest_events) == 1
    assert harvest_events[0].solved_example_id == "01HSE-pinned-id"
    assert skip_events == []


# --- AC-12 — gate rejection paths emit HarvestSkipped, no ingest ----------


@pytest.mark.parametrize(
    ("passed", "confidence", "expected_reason"),
    [
        (True, "degraded", "low_confidence"),
        (False, "high", "trust_failed"),
        (False, "degraded", "trust_failed"),
    ],
)
@pytest.mark.asyncio
async def test_confidence_gate_rejection_skips_ingest(
    tmp_path: Path, passed: bool, confidence: str, expected_reason: str
) -> None:
    """AC-3 + AC-7 step 2 — gate-reject paths emit HarvestSkipped with
    the right reason; mint + ingest NOT called."""
    tier, ingest_spy = _make_tier(tmp_path)
    outcome: PlanOutcome = AppliedFromLlm(
        recipe_outcome_digest=BlobDigest("0" * 64),
        few_shot_ref=None,
        response_id=LeafResponseId("resp-002"),
    )
    trust = _trust(passed=passed, confidence=confidence)

    await tier.on_validated(outcome, trust, context=_ctx())

    ingest_spy.assert_not_called()
    events = _emitted(tier)
    skip_events = [e for e in events if isinstance(e, HarvestSkipped)]
    harvest_events = [e for e in events if isinstance(e, SolvedExampleHarvested)]
    assert len(skip_events) == 1
    assert skip_events[0].reason == expected_reason
    assert skip_events[0].plan_outcome_kind == "llm"
    assert harvest_events == []


# --- Eligibility-rejection paths (non-AppliedFromLlm outcomes) ------------


@pytest.mark.parametrize(
    "outcome_kind",
    [
        ("recipe", AppliedFromRecipe(recipe_outcome_digest=BlobDigest("0" * 64))),
        ("rag_only", RagOnlyApplicable(few_shot_ref=SolvedExampleId("ex-001"))),
        ("refused", Refused(reason="LEAF_REFUSED")),
    ],
    ids=lambda x: x[0] if isinstance(x, tuple) else str(x),
)
@pytest.mark.asyncio
async def test_outcome_not_harvestable_skips_ingest(
    tmp_path: Path, outcome_kind: tuple[str, PlanOutcome]
) -> None:
    """AC-7 step 1 — non-AppliedFromLlm outcomes emit HarvestSkipped
    with reason='outcome_not_harvestable'; mint + ingest NOT called."""
    expected_kind, outcome = outcome_kind
    tier, ingest_spy = _make_tier(tmp_path)
    trust = _trust(passed=True, confidence="high")

    await tier.on_validated(outcome, trust, context=_ctx())

    ingest_spy.assert_not_called()
    events = _emitted(tier)
    skip_events = [e for e in events if isinstance(e, HarvestSkipped)]
    assert len(skip_events) == 1
    assert skip_events[0].reason == "outcome_not_harvestable"
    assert skip_events[0].plan_outcome_kind == expected_kind


# --- AC-13 — HarvestSkipped event shape pinning ---------------------------


def test_harvest_skipped_rejects_unknown_reason() -> None:
    """The closed-set ``reason`` Literal rejects an out-of-set value."""
    from datetime import UTC, datetime

    from codegenie.types.identifiers import EventId

    with pytest.raises(Exception):  # noqa: B017 — pydantic ValidationError
        HarvestSkipped(
            event_id=EventId("ev-1"),
            workflow_id=WorkflowId("wf-1"),
            timestamp=datetime.now(UTC),
            reason="not_in_the_closed_set",  # type: ignore[arg-type]
            plan_outcome_kind="llm",
        )


def test_harvest_skipped_rejects_unknown_plan_outcome_kind() -> None:
    """Closed-set ``plan_outcome_kind`` Literal — rejects junk."""
    from datetime import UTC, datetime

    from codegenie.types.identifiers import EventId

    with pytest.raises(Exception):  # noqa: B017
        HarvestSkipped(
            event_id=EventId("ev-1"),
            workflow_id=WorkflowId("wf-1"),
            timestamp=datetime.now(UTC),
            reason="low_confidence",
            plan_outcome_kind="not_a_real_kind",  # type: ignore[arg-type]
        )
