"""Phase-4 S6-03 AC-8 — auto-harvest idempotence via deterministic-id pre-check.

When :meth:`FallbackTier.on_validated` is invoked twice with the
identical ``(outcome, context)`` pair, the second call MUST detect the
duplicate via ``await self.store.contains(sid)`` and emit
``HarvestSkipped(reason="already_harvested")`` *before* minting a
write-capability or calling :func:`ingest_solved_example`.

The deterministic :data:`SolvedExampleId` is the load-bearing
identifier: ``_solved_example_id_for(outcome, embedding_model)`` is a
BLAKE3 hash over the five identity fields (S4-06 AC-3), so identical
inputs produce identical ids and the membership check is exact.

This test pins the **caller-side idempotence detection** — no
``SolvedExampleHarvestedDeduped`` event variant is invented; the closed
:class:`HarvestSkipped.reason` set (``low_confidence`` |
``trust_failed`` | ``outcome_not_harvestable`` | ``already_harvested``)
remains stable.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from codegenie.fallback.confidence_gate import ConfidenceGate
from codegenie.fallback.plan_outcome import AppliedFromLlm
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
    SolvedExampleId,
    TaskClassId,
    WorkflowId,
)


def _trust_high_pass() -> TrustOutcome:
    return TrustOutcome(passed=True, confidence="high", signals=(), failing=())


def _ctx() -> PostValidationContext:
    plan = PlanProposalDepBump(
        manifest_path="package.json",
        package=PackageId("vulnpkg@1.0.0"),
        target_version=SemverVersion("1.0.1"),
        rationale="patch vuln",
    )
    return PostValidationContext(
        workflow_id=WorkflowId("wf-on-validated-idempotent-001"),
        chain_head=ChainHead("c" * 64),
        advisory_digest=BlobDigest("1" * 64),
        cve_id=CveId("CVE-2026-7777"),
        task_class=TaskClassId("vuln_remediation"),
        language=Language("typescript"),
        build_system="npm",
        transform_digest=BlobDigest("2" * 64),
        trust_outcome_digest=BlobDigest("3" * 64),
        query_text="fix the cve",
        plan_proposal=plan,
    )


def _outcome() -> AppliedFromLlm:
    return AppliedFromLlm(
        recipe_outcome_digest=BlobDigest("4" * 64),
        few_shot_ref=None,
        response_id=LeafResponseId("01HRESP" + "0" * 14),
    )


def _make_tier(tmp_path: Path) -> tuple[FallbackTier, MagicMock, MagicMock]:
    """Construct a FallbackTier with a programmable store + AsyncMock
    ``contains``/``add`` so the test can flip the seen-set between calls.

    Returns ``(tier, store, store.contains_spy)``.
    """
    event_log = EventLog(
        root=tmp_path,
        workflow_id=WorkflowId("01HS603IDEMPOTENTTESTWX00"),
    )
    embedder = MagicMock()
    embedder.model_digest = lambda: BlobDigest("blake3:" + "9" * 64)
    embedder.embed = lambda _text: tuple(0.1 for _ in range(384))

    seen: set[SolvedExampleId] = set()

    async def _contains(sid: SolvedExampleId) -> bool:
        return sid in seen

    async def _add(example, capability):  # type: ignore[no-untyped-def]
        seen.add(example.id)
        return example.id

    store = MagicMock()
    store.contains = AsyncMock(side_effect=_contains)
    store.add = AsyncMock(side_effect=_add)

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
    return tier, store, store.contains


def _emitted(tier: FallbackTier) -> list[object]:
    tier.event_log.flush()  # type: ignore[attr-defined]
    return list(tier.event_log.replay())  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_second_call_with_identical_inputs_emits_already_harvested(
    tmp_path: Path,
) -> None:
    """Two ``on_validated`` calls with identical ``(outcome, context)``:
    the first emits ``SolvedExampleHarvested``; the second emits
    ``HarvestSkipped(reason="already_harvested")``.
    """
    tier, store, _contains = _make_tier(tmp_path)
    outcome = _outcome()
    context = _ctx()
    trust = _trust_high_pass()

    # First call — harvests.
    await tier.on_validated(outcome, trust, context=context)
    # Second call — identical inputs — detects duplicate.
    await tier.on_validated(outcome, trust, context=context)

    events = _emitted(tier)
    harvested = [e for e in events if isinstance(e, SolvedExampleHarvested)]
    skipped = [e for e in events if isinstance(e, HarvestSkipped)]

    assert len(harvested) == 1, f"first call must emit SolvedExampleHarvested; got {len(harvested)}"
    assert len(skipped) == 1, (
        f"second call must emit exactly one HarvestSkipped; got {len(skipped)}"
    )
    assert skipped[0].reason == "already_harvested"


@pytest.mark.asyncio
async def test_store_add_called_exactly_once_across_duplicate_calls(
    tmp_path: Path,
) -> None:
    """``store.add`` is invoked exactly **once** across two identical
    ``on_validated`` calls — the idempotence pre-check spares the
    embed + write cost on the second invocation.
    """
    tier, store, _contains = _make_tier(tmp_path)
    outcome = _outcome()
    context = _ctx()
    trust = _trust_high_pass()

    await tier.on_validated(outcome, trust, context=context)
    await tier.on_validated(outcome, trust, context=context)

    assert store.add.await_count == 1, (
        f"store.add must be awaited exactly once; got {store.add.await_count}"
    )


@pytest.mark.asyncio
async def test_contains_check_runs_before_mint(tmp_path: Path) -> None:
    """``store.contains`` is consulted on EVERY call (including the first).
    A second call where ``contains`` returns True short-circuits BEFORE
    capability mint — proved by ``store.add`` not being called.
    """
    tier, store, contains_spy = _make_tier(tmp_path)
    outcome = _outcome()
    context = _ctx()
    trust = _trust_high_pass()

    await tier.on_validated(outcome, trust, context=context)
    await tier.on_validated(outcome, trust, context=context)

    # contains() awaited on both calls — sanity check.
    assert contains_spy.await_count == 2
    # add() awaited only on first.
    assert store.add.await_count == 1


@pytest.mark.asyncio
async def test_already_harvested_carries_correct_outcome_kind(
    tmp_path: Path,
) -> None:
    """The duplicate-detection ``HarvestSkipped`` carries the same
    ``plan_outcome_kind`` discriminator as the eligible-outcome path
    (``"llm"`` for :class:`AppliedFromLlm`).
    """
    tier, _store, _contains = _make_tier(tmp_path)
    outcome = _outcome()
    context = _ctx()
    trust = _trust_high_pass()

    await tier.on_validated(outcome, trust, context=context)
    await tier.on_validated(outcome, trust, context=context)

    skipped = [e for e in _emitted(tier) if isinstance(e, HarvestSkipped)]
    assert skipped[0].plan_outcome_kind == "llm"
