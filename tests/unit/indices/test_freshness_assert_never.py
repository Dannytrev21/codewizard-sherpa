"""S7-05 AC-5 — exhaustive ``match`` over ``IndexFreshness`` + ``StaleReason``.

A separate non-property test that pattern-matches on every variant in the
closed sum type. The final ``case _`` triggers :func:`typing.assert_never`,
which mypy resolves to ``Never``. Repo-wide ``warn_unreachable = true``
(see ``pyproject.toml [tool.mypy] warn_unreachable``) fires a build error
if any case is missing — that is the load-bearing structural defense.

Mirrors the discipline of the S5-01 sum-type kernel: this file is the
"trip-wire" that a future contributor extending ``StaleReason`` cannot
silently bypass.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import assert_never

from codegenie.indices import (
    CommitsBehind,
    CoverageGap,
    DigestMismatch,
    Fresh,
    IndexerError,
    IndexFreshness,
    Stale,
)


def _stringify(x: IndexFreshness) -> str:
    """Exhaustive pattern-match over every ``IndexFreshness`` + ``StaleReason``.

    Removing or commenting out any ``case`` arm makes mypy
    ``--warn-unreachable`` flag the ``assert_never`` branch as reachable
    with a non-``Never`` operand — a hard build break.
    """
    match x:
        case Fresh():
            return "fresh"
        case Stale(reason=CommitsBehind(n=n)):
            return f"stale_commits_behind_{n}"
        case Stale(reason=DigestMismatch()):
            return "stale_digest_mismatch"
        case Stale(reason=CoverageGap()):
            return "stale_coverage_gap"
        case Stale(reason=IndexerError()):
            return "stale_indexer_error"
        case _:  # pragma: no cover — mypy enforces exhaustiveness
            assert_never(x)


def test_exhaustive_match_assert_never() -> None:
    """Constructs one instance of every variant and verifies dispatch.

    The runtime path proves the ``case`` arms behave as expected; mypy
    ``--warn-unreachable`` proves no variant was missed at typecheck time.
    """
    assert _stringify(Fresh(indexed_at=datetime(2026, 1, 1, tzinfo=UTC))) == "fresh"
    assert _stringify(Stale(reason=CommitsBehind(n=1, last_indexed="abc1234"))).startswith(
        "stale_commits_behind_"
    )
    assert (
        _stringify(Stale(reason=DigestMismatch(expected="x" * 64, actual="y" * 64)))
        == "stale_digest_mismatch"
    )
    assert (
        _stringify(Stale(reason=CoverageGap(files_indexed=0, files_in_repo=0)))
        == "stale_coverage_gap"
    )
    assert _stringify(Stale(reason=IndexerError(message="boom"))) == "stale_indexer_error"
