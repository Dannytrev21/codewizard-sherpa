"""Phase-4 S6-02 metamorphic property — the retry-bypass branch output
depends **only** on ``prior_attempts[-1]``.

For any fixed ``last`` :class:`AttemptSummary` and any prefix permutation
of arbitrary other summaries, the emitted :class:`RagSkippedOnRetry`
payload (``last_attempt_number``, ``last_failing_signals``) is identical
across runs; only ``attempt_count`` varies with the prefix length.

Catches regressions where ``tier.py`` accidentally concatenates summaries,
hashes over the whole list, or selects ``[0]`` instead of ``[-1]``.

S6-01 GREEN-partial caveat: the placeholder ``FallbackTier.run`` does not
yet call ``PromptBuilder.build``, so the story's
``PromptAssembled.fenced_body_byte_length`` invariance check is deferred
until S6-01 GREEN-complete. The ``RagSkippedOnRetry`` payload invariance
captures the load-bearing semantics of the metamorphic property today.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from codegenie.fallback.confidence_gate import ConfidenceGate
from codegenie.fallback.contracts import (
    CveAdvisory,
    RecipeSelection,
    RepoContext,
)
from codegenie.fallback.tier import FallbackTier
from codegenie.plugins.events import EventLog, RagSkippedOnRetry
from codegenie.transforms.apply_context import AttemptSummary
from codegenie.types.identifiers import (
    AttemptNumber,
    CveId,
    PackageId,
    SignalKind,
    WorkflowId,
)


def _make_summary(*, attempt: int, signal: str, body: str) -> AttemptSummary:
    return AttemptSummary(
        attempt=AttemptNumber(attempt),
        failing_signals=(SignalKind(signal),),
        prior_failure_summary=body,
        evidence_paths=(),
        transform_id=None,
    )


def _build_tier(tmp_path: Path) -> FallbackTier:
    event_log = EventLog(
        root=tmp_path / "events",
        workflow_id=WorkflowId("01HS602PROPTESTXYZ000000"),
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


def _run_and_extract_skip(
    *,
    tmp_path: Path,
    prior_attempts: tuple[AttemptSummary, ...],
) -> RagSkippedOnRetry:
    tier = _build_tier(tmp_path)
    advisory = CveAdvisory(
        cve_id=CveId("CVE-2026-1234"),
        affected_package=PackageId("vulnpkg@1.0.0"),
        description="t",
    )
    repo_ctx = RepoContext(repo_root=".", readme="", transitive_dep_meta=())
    selection = RecipeSelection(recipe_name="r", build_system="npm")
    asyncio.run(tier.run(advisory, repo_ctx, selection, prior_attempts=prior_attempts))
    tier.event_log.flush()
    skips = [e for e in tier.event_log.replay() if isinstance(e, RagSkippedOnRetry)]
    assert len(skips) == 1
    return skips[0]


@given(
    prefix_a=st.lists(
        st.tuples(
            st.integers(min_value=1, max_value=50),
            st.text(
                alphabet="abcdefghijklmnopqrstuvwxyz._",
                min_size=1,
                max_size=20,
            ),
            st.text(
                alphabet="abcdefghij",
                min_size=0,
                max_size=80,
            ),
        ),
        min_size=0,
        max_size=4,
    ),
    prefix_b=st.lists(
        st.tuples(
            st.integers(min_value=1, max_value=50),
            st.text(
                alphabet="abcdefghijklmnopqrstuvwxyz._",
                min_size=1,
                max_size=20,
            ),
            st.text(
                alphabet="abcdefghij",
                min_size=0,
                max_size=80,
            ),
        ),
        min_size=0,
        max_size=4,
    ),
)
@settings(
    max_examples=25,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_prefix_permutation_does_not_change_last_payload(
    prefix_a: list[tuple[int, str, str]],
    prefix_b: list[tuple[int, str, str]],
    tmp_path_factory: object,
) -> None:
    """For two arbitrary prefixes of summaries terminated by the **same**
    last summary, the emitted ``RagSkippedOnRetry.last_attempt_number``
    and ``last_failing_signals`` are equal. Only ``attempt_count``
    differs (by construction — it's the length).
    """
    # Note: tmp_path_factory is per-function from pytest; we manufacture
    # one tmp dir per Hypothesis example to keep EventLog isolated.
    from pytest import TempPathFactory  # noqa: PLC0415 — local import for typing

    assert isinstance(tmp_path_factory, TempPathFactory)
    last = _make_summary(attempt=99, signal="sig.last", body="LAST")

    prior_a = tuple(_make_summary(attempt=a, signal=s, body=b) for a, s, b in prefix_a) + (last,)
    prior_b = tuple(_make_summary(attempt=a, signal=s, body=b) for a, s, b in prefix_b) + (last,)

    tmp_a = tmp_path_factory.mktemp("prop_a")
    tmp_b = tmp_path_factory.mktemp("prop_b")

    skip_a = _run_and_extract_skip(tmp_path=tmp_a, prior_attempts=prior_a)
    skip_b = _run_and_extract_skip(tmp_path=tmp_b, prior_attempts=prior_b)

    # The load-bearing invariant — last-attempt identity preserved.
    assert skip_a.last_attempt_number == skip_b.last_attempt_number == last.attempt
    assert skip_a.last_failing_signals == skip_b.last_failing_signals == last.failing_signals
    # Count varies with prefix length — sanity-check the orthogonal axis.
    assert skip_a.attempt_count == len(prefix_a) + 1
    assert skip_b.attempt_count == len(prefix_b) + 1
