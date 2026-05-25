"""Phase 6 S2-01 AC-2 — store types do NOT enter ``codegenie.workflows.__all__``.

The Phase-6.5 bench harness consumes exactly the 14 names committed by
S1-01 + S1-02 (final-design.md §"Relationship to Phase 6.5" — `may not
depend on: checkpoint backend internals`). This story adds three new
symbols (``CheckpointStore``, ``SqliteCheckpointStore``,
``InMemoryCheckpointStore``) but **none** of them belong in
``__all__``. A future executor that adds ``CheckpointStore`` for "API
convenience" fails this test loud.
"""

from __future__ import annotations

from typing import Final

import codegenie.workflows as workflows_pkg

_EXPECTED_FOURTEEN: Final[frozenset[str]] = frozenset(
    {
        "AwaitingHumanReview",
        "Completed",
        "FailedUnrecoverable",
        "GateFailedRetryable",
        "LedgerStateKind",
        "NeedsPlan",
        "PatchApplied",
        "PlanReady",
        "SutDigest",
        "TransitionEvent",
        "TransitionId",
        "VulnLedgerState",
        "VulnRemediationCase",
        "VulnRemediationResult",
        "VulnRemediationSut",
    }
)


def test_ac2_all_is_byte_equal_to_fourteen_name_set() -> None:
    """``__all__`` is unchanged after S2-01 lands — store types stay package-private."""
    actual = set(workflows_pkg.__all__)
    assert actual == _EXPECTED_FOURTEEN, (
        "codegenie.workflows.__all__ drifted from the S1-01+S1-02 fourteen-name "
        "allowlist after S2-01. Store types (CheckpointStore, "
        "SqliteCheckpointStore, InMemoryCheckpointStore) are deliberately "
        "package-private — final-design.md §'Relationship to Phase 6.5' "
        "forbids the harness from depending on checkpoint backend internals."
    )


def test_ac2_store_types_are_not_publicly_exported() -> None:
    """None of the three store types appear in ``__all__``."""
    forbidden = {"CheckpointStore", "SqliteCheckpointStore", "InMemoryCheckpointStore"}
    intersection = forbidden & set(workflows_pkg.__all__)
    assert intersection == set(), (
        f"Store types in __all__: {intersection}. Phase-6.5 must NOT depend "
        "on checkpoint backend internals — see final-design.md §'Relationship "
        "to Phase 6.5'."
    )
