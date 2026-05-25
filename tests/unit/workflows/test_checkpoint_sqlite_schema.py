"""Phase 6 S2-01 AC-5 — SQLite schema golden + WAL/sync/busy-timeout pragmas.

The schema string in :data:`_CHECKPOINT_SCHEMA_SQL` is the single
canonical declaration; the golden at
``tests/golden/phase6-checkpoint/sqlite_schema.sql`` is the byte-equal
sidecar a reviewer can grep without importing Python. AC-5 fails loud
on drift between them.

The pragma checks confirm:

* ``journal_mode=WAL`` — readers do not block writers.
* ``synchronous=FULL`` (numeric value ``2``) — a power loss between
  commit and fsync cannot leave a torn write visible.
* ``busy_timeout>=5000`` — stale locks surface as retries, not
  immediate exceptions.
"""

from __future__ import annotations

from pathlib import Path

from codegenie.types.identifiers import WorkflowId
from codegenie.workflows.sqlite_checkpoints import (
    _CHECKPOINT_SCHEMA_SQL,
    SqliteCheckpointStore,
)

_GOLDEN_PATH = (
    Path(__file__).resolve().parents[3]
    / "tests"
    / "golden"
    / "phase6-checkpoint"
    / "sqlite_schema.sql"
)


def test_ac5_schema_byte_equal_to_golden() -> None:
    """The schema string is byte-equal to the sidecar golden."""
    assert _GOLDEN_PATH.exists(), (
        f"Phase-6 checkpoint schema golden missing at {_GOLDEN_PATH}. "
        "Land it alongside _CHECKPOINT_SCHEMA_SQL."
    )
    expected = _GOLDEN_PATH.read_text()
    assert _CHECKPOINT_SCHEMA_SQL == expected, (
        "SQLite schema drift between codegenie.workflows.sqlite_checkpoints "
        "and tests/golden/phase6-checkpoint/sqlite_schema.sql. If additive "
        "(new column with default, new index), update both files. If "
        "breaking (column rename, index removal), amend ADR-0003."
    )


def test_ac5_wal_synchronous_busy_timeout_pragmas(tmp_path: Path) -> None:
    """A constructed store reports journal_mode=WAL + synchronous=FULL."""
    store = SqliteCheckpointStore(tmp_path)
    try:
        wf = WorkflowId("01HZZZZZZZZZZZZZZZZZZZZZZZ")
        conn = store._connection_for(wf)  # noqa: SLF001 — intentional probe
        (journal_mode,) = conn.execute("PRAGMA journal_mode").fetchone()
        (synchronous,) = conn.execute("PRAGMA synchronous").fetchone()
        (busy_timeout,) = conn.execute("PRAGMA busy_timeout").fetchone()
        assert journal_mode.lower() == "wal", (
            "Phase-6 SQLite store must use WAL journaling. PRAGMA returned: " + journal_mode
        )
        assert synchronous == 2, (
            "Phase-6 SQLite store must use synchronous=FULL (numeric 2). "
            f"PRAGMA returned: {synchronous}."
        )
        assert busy_timeout >= 5000, (
            "Phase-6 SQLite store must set busy_timeout >= 5000ms. "
            f"PRAGMA returned: {busy_timeout}."
        )
    finally:
        store.close()
