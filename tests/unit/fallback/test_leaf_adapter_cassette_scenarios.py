"""Phase-4 S3-02 AC-23 — adapter cassette scenarios (markers only).

Two scenarios are reserved for S3-06's live-cassette refresh workflow:

- ``leaf_adapter_llm_from_scratch`` — expects a
  :class:`PlanProposalCallsiteRewrite` on
  ``fixtures/vuln-major-bump/express-cve-2026-1234``.
- ``leaf_adapter_rag_hit_few_shot`` — expects the cassette-recorded
  :class:`PlanProposal` on ``fixtures/vuln-rag-hit/express-rerun``.

Both tests are marked :data:`uses_anthropic_cassette` and skipped while the
``ANTHROPIC_CASSETTES_LIVE`` environment switch is unset. S3-04 / S3-05 /
S3-06 will land the sanitizer hooks, scanner, lock, and refresh workflow
that flip the switch on. Until then **no live cassette bytes** are recorded
by S3-02 (ADR-0014).
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.uses_anthropic_cassette


@pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_CASSETTES_LIVE"),
    reason="S3-04/S3-05/S3-06 will enable live cassette playback; deferred per ADR-0014",
)
def test_leaf_adapter_llm_from_scratch_cassette_marker() -> None:
    """Reserved scenario — see module docstring."""
    pytest.skip("cassette discipline lands in S3-04 / S3-05 / S3-06")


@pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_CASSETTES_LIVE"),
    reason="S3-04/S3-05/S3-06 will enable live cassette playback; deferred per ADR-0014",
)
def test_leaf_adapter_rag_hit_few_shot_cassette_marker() -> None:
    """Reserved scenario — see module docstring."""
    pytest.skip("cassette discipline lands in S3-04 / S3-05 / S3-06")
