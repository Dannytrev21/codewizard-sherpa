"""S6-02 — :meth:`FallbackTier.run` retry-bypass branch (ADR-04-0011).

When ``prior_attempts`` is non-empty (truthiness, not literal ``!= []``),
RAG retrieval is **skipped entirely** and the prompt body would carry the
fence-wrapped ``prior_failure_summary`` of the most recent attempt in
place of the RAG few-shot.

S6-01 GREEN-partial caveat: the current :meth:`FallbackTier.run`
placeholder always returns :class:`Refused` and does not yet call
``retriever.query`` / ``prompt_builder.build`` / ``leaf.invoke`` (full
9-step dispatch deferred to S6-01 GREEN-complete). The retry-bypass
emission and event-payload identity ACs are testable today against the
placeholder; the full retry-path 10-event-tape AC is deferred to S6-01
GREEN-complete and tracked in ``_attempts/S6-02.md``. This is the same
GREEN-partial pattern S6-08 followed (terminal-anchor over the
placeholder run).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from codegenie.fallback.confidence_gate import ConfidenceGate
from codegenie.fallback.contracts import (
    CveAdvisory,
    RecipeSelection,
    RepoContext,
)
from codegenie.fallback.tier import FallbackTier
from codegenie.plugins.events import (
    EventLog,
    PlanOutcomeEmitted,
    RagSkippedOnRetry,
)
from codegenie.transforms.apply_context import AttemptSummary
from codegenie.types.identifiers import (
    AttemptNumber,
    CveId,
    PackageId,
    SignalKind,
    WorkflowId,
)


def _advisory() -> CveAdvisory:
    return CveAdvisory(
        cve_id=CveId("CVE-2026-1234"),
        affected_package=PackageId("vulnpkg@1.0.0"),
        description="test",
    )


def _selection() -> RecipeSelection:
    return RecipeSelection(recipe_name="npm_dep_bump", build_system="npm")


def _repo_ctx() -> RepoContext:
    return RepoContext(repo_root=".", readme="", transitive_dep_meta=())


def _make_tier(tmp_path: Path) -> FallbackTier:
    event_log = EventLog(
        root=tmp_path / "events",
        workflow_id=WorkflowId("01HS602RETRYTESTWXX0Z000"),
    )
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
        anchor_output_dir=tmp_path / "anchors",
    )


def _make_summary(*, attempt: int, signal: str, body: str) -> AttemptSummary:
    return AttemptSummary(
        attempt=AttemptNumber(attempt),
        failing_signals=(SignalKind(signal),),
        prior_failure_summary=body,
        evidence_paths=(),
        transform_id=None,
    )


def _emitted(tier: FallbackTier) -> list[object]:
    tier.event_log.flush()  # type: ignore[attr-defined]
    return list(tier.event_log.replay())  # type: ignore[attr-defined]


# --- AC: branch semantics + bool(prior_attempts) truthiness ----------------


@pytest.mark.asyncio
@pytest.mark.parametrize("n", [1, 2, 3])
async def test_retry_emits_rag_skipped_with_last_attempt_payload(n: int, tmp_path: Path) -> None:
    """For N ∈ {1, 2, 3}, the emitted :class:`RagSkippedOnRetry` carries
    the **last** attempt's ``attempt`` and ``failing_signals`` plus the
    full ``attempt_count``. Catches the ``[0]``-instead-of-``[-1]``
    regression (invisible at N=1) AND the hard-coded ``attempt_count=1``
    mutation (invisible at N=1).
    """
    prior = tuple(
        _make_summary(attempt=i + 1, signal=f"sig.kind.{i}", body=f"failure-{i}") for i in range(n)
    )
    last = prior[-1]

    tier = _make_tier(tmp_path)
    await tier.run(_advisory(), _repo_ctx(), _selection(), prior_attempts=prior)

    skip_events = [e for e in _emitted(tier) if isinstance(e, RagSkippedOnRetry)]
    assert len(skip_events) == 1, "exactly one RagSkippedOnRetry per attempt"
    skip = skip_events[0]
    assert skip.attempt_count == n
    assert skip.last_attempt_number == last.attempt
    assert skip.last_failing_signals == last.failing_signals


@pytest.mark.asyncio
async def test_retry_with_list_shape_emits_rag_skipped(tmp_path: Path) -> None:
    """``Sequence[AttemptSummary]`` is read-covariant: ``list`` is a valid
    truthy shape (``bool([summary]) is True``). The branch must trigger
    for both ``tuple`` and ``list`` shapes equally."""
    summary = _make_summary(attempt=7, signal="sig.list", body="list-shape")
    tier = _make_tier(tmp_path)
    await tier.run(_advisory(), _repo_ctx(), _selection(), prior_attempts=[summary])

    skip_events = [e for e in _emitted(tier) if isinstance(e, RagSkippedOnRetry)]
    assert len(skip_events) == 1
    assert skip_events[0].last_attempt_number == AttemptNumber(7)


@pytest.mark.asyncio
@pytest.mark.parametrize("empty", [(), []])
async def test_empty_prior_attempts_does_not_emit_rag_skipped(
    empty: object, tmp_path: Path
) -> None:
    """``bool(()) is False`` AND ``bool([]) is False`` — both encode the
    initial-plan path. A literal ``prior_attempts != []`` predicate
    would misclassify ``()`` as truthy; pin the truthiness predicate
    explicitly via this parametrized check.
    """
    tier = _make_tier(tmp_path)
    await tier.run(
        _advisory(),
        _repo_ctx(),
        _selection(),
        prior_attempts=empty,  # type: ignore[arg-type]
    )

    skip_events = [e for e in _emitted(tier) if isinstance(e, RagSkippedOnRetry)]
    assert skip_events == [], "initial-plan path must not emit RagSkippedOnRetry"


# --- AC: emission ordering — RagSkippedOnRetry precedes terminal events ----


@pytest.mark.asyncio
async def test_rag_skipped_precedes_plan_outcome_and_anchor(
    tmp_path: Path,
) -> None:
    """:class:`RagSkippedOnRetry` lands in event-tape *before*
    :class:`PlanOutcomeEmitted` (step 3 of the 9-step dispatch is the
    retrieval step; ``PlanOutcomeEmitted`` is the terminal step 9 wrapper).
    AttemptAnchorRecorded remains the final event (S6-08 invariant)."""
    summary = _make_summary(attempt=2, signal="sig.kind.x", body="failure")
    tier = _make_tier(tmp_path)
    await tier.run(_advisory(), _repo_ctx(), _selection(), prior_attempts=(summary,))

    kinds = [type(e).__name__ for e in _emitted(tier)]
    assert "RagSkippedOnRetry" in kinds
    assert "PlanOutcomeEmitted" in kinds
    assert "AttemptAnchorRecorded" in kinds
    assert kinds.index("RagSkippedOnRetry") < kinds.index("PlanOutcomeEmitted")
    assert kinds.index("PlanOutcomeEmitted") < kinds.index("AttemptAnchorRecorded")
    # S6-08 terminal-anchor invariant — AttemptAnchorRecorded is last.
    assert kinds[-1] == "AttemptAnchorRecorded"


# --- AC: PlanOutcome variant on retry-bypass (today: still Refused while  --
# --- S6-01 placeholder; will become AppliedFromLlm on happy-retry once    --
# --- S6-01 GREEN-complete lands the leaf call) ----------------------------


@pytest.mark.asyncio
async def test_retry_bypass_still_emits_plan_outcome_terminal(
    tmp_path: Path,
) -> None:
    """Defense for the S6-01 GREEN-partial caveat: the retry-bypass branch
    must still produce a terminal :class:`PlanOutcomeEmitted` — the
    placeholder's :class:`Refused` outcome is fine for today; the
    happy-retry ``AppliedFromLlm`` variant lands once S6-01 GREEN-complete
    wires the leaf call.
    """
    summary = _make_summary(attempt=1, signal="sig.kind.0", body="single")
    tier = _make_tier(tmp_path)
    await tier.run(_advisory(), _repo_ctx(), _selection(), prior_attempts=(summary,))

    plan_events = [e for e in _emitted(tier) if isinstance(e, PlanOutcomeEmitted)]
    assert len(plan_events) == 1
    assert plan_events[0].outcome_kind in {"recipe", "llm", "rag_only", "refused"}


# --- AC: payload integrity across distinguishable prior_attempts ----------


@pytest.mark.asyncio
async def test_distinguishable_prior_attempts_pin_last_attempt_payload(
    tmp_path: Path,
) -> None:
    """Prior attempts with **distinct** signals + bodies — the emitted
    event's ``last_failing_signals`` must equal prior[-1].failing_signals
    (not prior[0], not the concatenation, not a hash of all).
    """
    prior = (
        _make_summary(attempt=1, signal="sig.alpha", body="alpha"),
        _make_summary(attempt=2, signal="sig.beta", body="beta"),
        _make_summary(attempt=3, signal="sig.gamma", body="gamma"),
    )
    tier = _make_tier(tmp_path)
    await tier.run(_advisory(), _repo_ctx(), _selection(), prior_attempts=prior)

    [skip] = [e for e in _emitted(tier) if isinstance(e, RagSkippedOnRetry)]
    assert skip.last_failing_signals == (SignalKind("sig.gamma"),)
    assert skip.last_attempt_number == AttemptNumber(3)
    assert skip.attempt_count == 3
