"""Hypothesis property test for ``codegenie.indices.IndexFreshness``.

AC-11 of story 02 S1-01. Required deliverable per 02-ADR-0006 §Consequences:
"any ``IndexFreshness`` round-trips identity-equal."
"""

from __future__ import annotations

from datetime import UTC, datetime

from hypothesis import given
from hypothesis import strategies as st
from pydantic import TypeAdapter

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

_aware_datetimes = st.datetimes(
    min_value=datetime(2020, 1, 1),
    max_value=datetime(2030, 1, 1),
    timezones=st.just(UTC),
)

_commits_behind = st.builds(
    CommitsBehind,
    n=st.integers(min_value=0, max_value=10_000),
    last_indexed=st.text(alphabet="0123456789abcdef", min_size=7, max_size=40),
)
_digest_mismatch = st.builds(
    DigestMismatch,
    expected=st.text(min_size=1, max_size=80),
    actual=st.text(min_size=1, max_size=80),
)
_coverage_gap = st.builds(
    CoverageGap,
    files_indexed=st.integers(min_value=0, max_value=1_000_000),
    files_in_repo=st.integers(min_value=0, max_value=1_000_000),
)
_indexer_error = st.builds(IndexerError, message=st.text(min_size=1, max_size=120))

_stale_reasons: st.SearchStrategy[StaleReason] = st.one_of(
    _commits_behind,
    _digest_mismatch,
    _coverage_gap,
    _indexer_error,
)
_freshness: st.SearchStrategy[IndexFreshness] = st.one_of(
    st.builds(Fresh, indexed_at=_aware_datetimes),
    st.builds(Stale, reason=_stale_reasons),
)

_adapter: TypeAdapter[IndexFreshness] = TypeAdapter(IndexFreshness)


@given(value=_freshness)
def test_index_freshness_roundtrips_identity(value: IndexFreshness) -> None:
    decoded = _adapter.validate_json(_adapter.dump_json(value))
    # Top-level: identity-equal and concrete type preserved.
    assert decoded == value
    assert type(decoded) is type(value)
    # Nested reason for Stale: concrete type preserved (guards against
    # silent loss of Field(discriminator="kind") on StaleReason).
    if isinstance(value, Stale):
        assert isinstance(decoded, Stale)
        assert type(decoded.reason) is type(value.reason)
