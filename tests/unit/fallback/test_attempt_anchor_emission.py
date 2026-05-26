"""S6-08 — :meth:`FallbackTier.run` emits ``AttemptAnchorRecorded`` as the
terminal event of the per-attempt tape and writes JSONL inline on refusal.

AC-EMIT-1 / AC-EMIT-2 / AC-ORDER-1 / AC-WRITER-2 / AC-WRITER-3 / AC-IDENTITY-1
/ AC-RAG-1.

S6-01 GREEN-partial caveat: the current :meth:`FallbackTier.run` placeholder
emits a single :class:`PlanOutcomeEmitted` followed by the new
:class:`AttemptAnchorRecorded`, so the "index 10 of 11" tape assertion
(AC-ORDER-1 strict form) is **deferred** until S6-01 GREEN-complete. Today's
assertion: anchor is the *last* event AND immediately follows
``PlanOutcomeEmitted``. Surfaced in ``_attempts/S6-08.md``.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pydantic import TypeAdapter

from codegenie.fallback.attempt_anchor import AttemptAnchor
from codegenie.fallback.confidence_gate import ConfidenceGate
from codegenie.fallback.contracts import (
    CveAdvisory,
    RecipeSelection,
    RepoContext,
)
from codegenie.fallback.tier import FallbackTier
from codegenie.plugins.events import (
    AttemptAnchorRecorded,
    EventLog,
    PlanOutcomeEmitted,
)
from codegenie.transforms.apply_context import AttemptSummary
from codegenie.transforms.outcomes import TrustOutcome
from codegenie.types.identifiers import (
    AttemptId,
    AttemptNumber,
    CveId,
    PackageId,
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
        workflow_id=WorkflowId("01HS608EMISSIONTESTWX0000"),
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


def _emitted(tier: FallbackTier) -> list[object]:
    tier.event_log.flush()  # type: ignore[attr-defined]
    return list(tier.event_log.replay())  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_run_emits_attempt_anchor_after_plan_outcome(tmp_path: Path) -> None:
    """AC-EMIT-1 + AC-ORDER-1 — exactly one ``AttemptAnchorRecorded`` per
    run, emitted *after* ``PlanOutcomeEmitted`` and as the terminal event."""
    tier = _make_tier(tmp_path)
    await tier.run(_advisory(), _repo_ctx(), _selection())
    events = _emitted(tier)
    anchor_events = [e for e in events if isinstance(e, AttemptAnchorRecorded)]
    plan_events = [e for e in events if isinstance(e, PlanOutcomeEmitted)]
    assert len(anchor_events) == 1
    assert len(plan_events) == 1
    assert events.index(plan_events[0]) < events.index(anchor_events[0])
    assert events[-1] is anchor_events[0]


@pytest.mark.asyncio
async def test_refusal_anchor_has_none_llm_fields(tmp_path: Path) -> None:
    """AC-EMIT-2 — refusal-path anchors have ``trust_outcome_*`` + the five
    LLM-derived fields all ``None`` (early-refusal short-circuits before any
    LLM call)."""
    tier = _make_tier(tmp_path)
    await tier.run(_advisory(), _repo_ctx(), _selection())
    events = _emitted(tier)
    anchor_event = next(e for e in events if isinstance(e, AttemptAnchorRecorded))
    anchor = TypeAdapter(AttemptAnchor).validate_python(anchor_event.anchor)
    assert anchor.validator_outcome == "Refused"
    assert anchor.refusal_reason == "PROVENANCE_NOT_APP_LAYER"
    assert anchor.trust_outcome_passed is None
    assert anchor.trust_outcome_confidence is None
    assert anchor.prompt_digest_blake3 is None
    assert anchor.response_digest_blake3 is None
    assert anchor.tokens_in is None
    assert anchor.cost_usd is None


@pytest.mark.asyncio
async def test_refusal_anchor_jsonl_persisted(tmp_path: Path) -> None:
    """AC-WRITER-2 — refusal-path anchors are written to JSONL inline
    before ``run`` returns. Round-trip the file back through TypeAdapter
    and assert the rebuilt anchor matches the emitted event payload."""
    tier = _make_tier(tmp_path)
    await tier.run(_advisory(), _repo_ctx(), _selection())
    events = _emitted(tier)
    anchor_event = next(e for e in events if isinstance(e, AttemptAnchorRecorded))
    anchor = TypeAdapter(AttemptAnchor).validate_python(anchor_event.anchor)
    date_dir = next((tmp_path / "anchors").iterdir())
    file_path = date_dir / f"{anchor.workflow_id}.jsonl"
    assert file_path.exists()
    lines = file_path.read_bytes().splitlines()
    assert len(lines) == 1
    rebuilt = TypeAdapter(AttemptAnchor).validate_json(lines[0])
    assert rebuilt.attempt_id == anchor.attempt_id
    assert rebuilt.cve_id == anchor.cve_id


@pytest.mark.asyncio
async def test_anchor_identity_workflow_and_attempt_index(tmp_path: Path) -> None:
    """AC-IDENTITY-1 — ``workflow_id`` mirrors the EventLog's workflow_id;
    ``attempt_index`` equals ``len(prior_attempts)``; ``attempt_id`` is
    freshly-minted per call and never re-used."""
    tier = _make_tier(tmp_path)
    await tier.run(_advisory(), _repo_ctx(), _selection(), prior_attempts=())
    summaries = (
        AttemptSummary(
            attempt=AttemptNumber(1),
            failing_signals=(),
            prior_failure_summary="recipe match failed",
            evidence_paths=(),
            transform_id=None,
        ),
    )
    await tier.run(_advisory(), _repo_ctx(), _selection(), prior_attempts=summaries)
    events = _emitted(tier)
    anchor_events = [e for e in events if isinstance(e, AttemptAnchorRecorded)]
    assert len(anchor_events) == 2
    anchors = [TypeAdapter(AttemptAnchor).validate_python(e.anchor) for e in anchor_events]
    assert anchors[0].workflow_id == WorkflowId("01HS608EMISSIONTESTWX0000")
    assert anchors[0].attempt_index == 0
    assert anchors[1].attempt_index == 1
    assert anchors[0].attempt_id != anchors[1].attempt_id


@pytest.mark.asyncio
async def test_jsonl_file_appends_across_runs(tmp_path: Path) -> None:
    """AC-WRITER-4 — two back-to-back runs in the same workflow + UTC date
    produce a two-line file; line 1 is the first anchor, line 2 the second."""
    tier = _make_tier(tmp_path)
    await tier.run(_advisory(), _repo_ctx(), _selection())
    await tier.run(_advisory(), _repo_ctx(), _selection())
    date_dir = next((tmp_path / "anchors").iterdir())
    file_path = next(date_dir.iterdir())
    lines = file_path.read_bytes().splitlines()
    assert len(lines) == 2
    parsed = [TypeAdapter(AttemptAnchor).validate_json(line) for line in lines]
    assert parsed[0].attempt_id != parsed[1].attempt_id


# ---- AC-PHASE5-1 surrogate ------------------------------------------------


@pytest.mark.asyncio
async def test_finalize_success_anchor_attaches_trust_and_writes(tmp_path: Path) -> None:
    """AC-WRITER-3 surrogate — once a pending anchor is parked (the eventual
    S6-01 GREEN-complete happy path or the Phase-5 ``GateRunner`` success
    block), :meth:`finalize_success_anchor` recovers it, attaches trust, and
    writes JSONL. Today this is the only call site for success-path anchors
    because Phase 5's ``GateRunner`` does not yet exist (AC-PHASE5-2)."""
    tier = _make_tier(tmp_path)
    attempt_id = AttemptId("d" * 32)
    pending = AttemptAnchor(
        attempt_id=attempt_id,
        workflow_id=tier.event_log.workflow_id,
        cve_id=CveId("CVE-2026-9999"),
        timestamp_utc=tier._build_refusal_anchor(  # reuse the helper's _now_utc
            attempt_id=AttemptId("e" * 32),
            cve_id=CveId("CVE-2026-0000"),
            reason="PROVENANCE_NOT_APP_LAYER",
            attempt_index=0,
        ).timestamp_utc,
        attempt_index=0,
        plan_proposal_kind="dep_bump",
        validator_outcome="AppliedFromLlm",
    )
    tier._pending_anchors[attempt_id] = pending
    trust = TrustOutcome(
        passed=True,
        confidence="high",
        signals=(),
        failing=(),
    )
    tier.finalize_success_anchor(attempt_id, trust)
    assert attempt_id not in tier._pending_anchors  # popped
    date_dir = next((tmp_path / "anchors").iterdir())
    file_path = next(date_dir.iterdir())
    rebuilt = TypeAdapter(AttemptAnchor).validate_json(file_path.read_bytes().splitlines()[0])
    assert rebuilt.trust_outcome_passed is True
    assert rebuilt.trust_outcome_confidence == "high"


def test_finalize_success_anchor_is_noop_when_no_pending(tmp_path: Path) -> None:
    """Defensive: ``finalize_success_anchor`` for an attempt that never
    parked is a no-op (refusal-path anchors are written inline and never
    reach this hook)."""
    tier = _make_tier(tmp_path)
    trust = TrustOutcome(passed=True, confidence="high", signals=(), failing=())
    # Should not raise; should not write a file.
    tier.finalize_success_anchor(AttemptId("f" * 32), trust)
    assert not (tmp_path / "anchors").exists() or not any((tmp_path / "anchors").iterdir())
