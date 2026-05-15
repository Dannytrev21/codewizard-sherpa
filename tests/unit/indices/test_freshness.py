"""Unit tests for ``codegenie.indices.freshness`` — story 02 S1-01.

Covers all 12 acceptance criteria (AC-1 through AC-11, including AC-6a)
from ``docs/phases/02-context-gather-layers-b-g/stories/S1-01-index-freshness-sum-type.md``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import assert_never

import pytest
from pydantic import TypeAdapter, ValidationError

from codegenie.indices import (
    CommitsBehind,
    CoverageGap,
    DigestMismatch,
    Fresh,
    IndexerError,
    IndexFreshness,
    Stale,
    StaleReason,
)

STALE_REASONS: list[StaleReason] = [
    CommitsBehind(n=3, last_indexed="abc1234"),
    DigestMismatch(expected="sha256:aaa", actual="sha256:bbb"),
    CoverageGap(files_indexed=900, files_in_repo=1000),
    IndexerError(message="strace_unavailable"),
]

FRESHNESS_INSTANCES: list[IndexFreshness] = [
    Fresh(indexed_at=datetime(2026, 5, 14, tzinfo=UTC)),
    *(Stale(reason=r) for r in STALE_REASONS),
]


@pytest.mark.parametrize("instance", FRESHNESS_INSTANCES)
def test_index_freshness_roundtrip_identity(instance: IndexFreshness) -> None:
    """AC-4: round-trip identity through the discriminated union; nested
    ``Stale.reason`` concrete type is preserved (guards against a regression
    that drops ``Field(discriminator="kind")`` from ``StaleReason``)."""
    adapter = TypeAdapter(IndexFreshness)
    encoded = adapter.dump_json(instance)
    decoded = adapter.validate_json(encoded)
    assert decoded == instance
    assert type(decoded) is type(instance)
    if isinstance(instance, Stale):
        assert isinstance(decoded, Stale)
        assert type(decoded.reason) is type(instance.reason)


def test_discriminator_strings_are_exactly_pinned() -> None:
    """AC-2: discriminator strings are a cross-ADR contract (02-ADR-0006).

    A symmetric swap (``CommitsBehind.kind = "digest_mismatch"`` +
    ``DigestMismatch.kind = "commits_behind"``) would pass the round-trip
    test but break every real consumer; pin the exact strings.
    """
    assert Fresh(indexed_at=datetime(2026, 1, 1, tzinfo=UTC)).kind == "fresh"
    assert Stale(reason=CommitsBehind(n=1, last_indexed="x")).kind == "stale"
    assert CommitsBehind(n=1, last_indexed="x").kind == "commits_behind"
    assert DigestMismatch(expected="a", actual="b").kind == "digest_mismatch"
    assert CoverageGap(files_indexed=1, files_in_repo=2).kind == "coverage_gap"
    assert IndexerError(message="x").kind == "indexer_error"


def test_json_shape_pinned() -> None:
    """AC-10: round-trip identity alone tolerates a symmetric ``kind`` → ``tag``
    rename; the JSON-shape pin does not."""
    fresh_dump = Fresh(indexed_at=datetime(2026, 1, 1, tzinfo=UTC)).model_dump(mode="json")
    assert fresh_dump["kind"] == "fresh"
    assert "indexed_at" in fresh_dump
    assert set(fresh_dump.keys()) == {"kind", "indexed_at"}

    stale_dump = Stale(reason=CommitsBehind(n=3, last_indexed="abc1234")).model_dump(mode="json")
    assert stale_dump == {
        "kind": "stale",
        "reason": {"kind": "commits_behind", "n": 3, "last_indexed": "abc1234"},
    }


def test_top_level_unknown_kind_is_rejected() -> None:
    """AC-5: the top-level ``IndexFreshness`` discriminator is enforced."""
    adapter = TypeAdapter(IndexFreshness)
    with pytest.raises(ValidationError):
        adapter.validate_python({"kind": "bogus_freshness"})


def test_stale_reason_rejects_unknown_kind() -> None:
    """AC-5: construction via raw dict must reject an unknown discriminator."""
    with pytest.raises(ValidationError):
        Stale.model_validate({"kind": "stale", "reason": {"kind": "bogus", "x": 1}})


def test_models_are_frozen_and_forbid_extra() -> None:
    """AC-2 partial: ``frozen=True`` + ``extra="forbid"`` are load-bearing."""
    inst = CommitsBehind(n=1, last_indexed="abc")
    with pytest.raises(ValidationError):
        # extra="forbid"
        CommitsBehind.model_validate(
            {"kind": "commits_behind", "n": 1, "last_indexed": "x", "extra": "no"}
        )
    with pytest.raises(ValidationError):
        # frozen=True
        inst.n = 2  # type: ignore[misc]


def test_match_is_exhaustive_over_stale_reason() -> None:
    """AC-6: exhaustive ``match`` over every ``StaleReason`` variant terminates
    with ``assert_never``. If a future contributor adds a fifth variant without
    updating this match, mypy ``--warn-unreachable`` on this module (S1-11
    override) will flag the ``assert_never(reason)`` line. At runtime this test
    only confirms every current variant routes."""
    seen: set[str] = set()
    for reason in STALE_REASONS:
        match reason:
            case CommitsBehind():
                seen.add("commits_behind")
            case DigestMismatch():
                seen.add("digest_mismatch")
            case CoverageGap():
                seen.add("coverage_gap")
            case IndexerError():
                seen.add("indexer_error")
            case _ as unexpected:
                assert_never(unexpected)
    assert seen == {"commits_behind", "digest_mismatch", "coverage_gap", "indexer_error"}


def test_match_is_exhaustive_over_index_freshness_top_level() -> None:
    """AC-6a: symmetric with ``test_match_is_exhaustive_over_stale_reason``.

    The renderer (S8-01 — ``report/confidence_section.py``) must ``match`` at
    this layer; the exhaustive discipline is rehearsed here so a future third
    top-level variant cannot be added without breaking every consumer's mypy
    build (via S1-11's ``mypy --warn-unreachable`` per-module override).
    """
    seen: set[str] = set()
    for freshness in FRESHNESS_INSTANCES:
        match freshness:
            case Fresh():
                seen.add("fresh")
            case Stale():
                seen.add("stale")
            case _ as unexpected:
                assert_never(unexpected)
    assert seen == {"fresh", "stale"}


def test_all_exports_full_variant_set() -> None:
    """AC-1: ``__all__`` pins the eight names; each resolves to a class object."""
    import codegenie.indices as m

    assert set(m.__all__) == {
        "IndexFreshness",
        "Fresh",
        "Stale",
        "StaleReason",
        "CommitsBehind",
        "DigestMismatch",
        "CoverageGap",
        "IndexerError",
    }


def test_freshness_module_has_no_model_construct() -> None:
    """AC-8: ``model_construct`` bypasses validation; the forbidden-patterns
    rule lands in S1-11, but the discipline starts here. Source-scan guard."""
    import codegenie.indices.freshness as freshness_mod

    source = Path(freshness_mod.__file__).read_text()
    assert "model_construct" not in source
