"""Phase 6 S2-01 — production SQLite WAL ``CheckpointStore`` adapter.

Per-workflow SQLite file at ``root / <workflow_id> / checkpoints.sqlite``
+ ``root / <workflow_id> / checkpoints.lock`` (the
:func:`fcntl.flock`-protected lock file beside the SQLite). The
per-workflow layout matches the
``.codegenie/remediation/<run-id>/`` shape phase-arch-design.md
§"Deployment view" pins; concurrent workflows do not block each other.

Discipline:

* ``journal_mode=WAL`` so readers do not block writers.
* ``synchronous=FULL`` so a power-loss between commit and fsync cannot
  leave a torn write visible. (AC-11's tamper test simulates the
  data-side failure mode; the configuration-side guarantee lives here.)
* ``busy_timeout=5000`` so a stale lock does not surface as an
  immediate ``database is locked`` exception.

Clock injection: ``clock: Callable[[], datetime] | None`` (defaults to
``datetime.now(UTC)``). The clock is the SOLE clock site in the store;
the chain-head computation in ``_chain.py`` stays pure (AC-13 + the
S1-02 AST purity fence).

Anti-refactor (story §"Anti-refactor #1, #3, #6"): no
``BaseCheckpointStore`` ABC, no ``CheckpointTransaction`` context
manager, no ``Clock`` Protocol with ``now() -> datetime`` — the body is
six lines of imperative-shell SQL composed with free helpers from
:mod:`codegenie.workflows.checkpoints`.
"""

from __future__ import annotations

import fcntl
import os
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from codegenie.output.sanitizer import sanitize_for_persistence
from codegenie.types.identifiers import ChainHead, WorkflowId
from codegenie.workflows._chain import _compute_chain_head
from codegenie.workflows.checkpoints import (
    _GENESIS_CHAIN_HEAD,
    _MAX_EVENT_BYTES,
    _PAYLOAD_TOO_LARGE_DIRECTIVE,
    _assert_boundary,
    _canonical_event_bytes,
)
from codegenie.workflows.errors import CheckpointPayloadTooLargeError
from codegenie.workflows.vuln_ledger import TransitionEvent

__all__ = [
    "SqliteCheckpointStore",
    "_CHECKPOINT_SCHEMA_SQL",
]


# Single-source-of-truth schema string. Byte-equal to the golden at
# ``tests/golden/phase6-checkpoint/sqlite_schema.sql`` (AC-5 enforces).
_CHECKPOINT_SCHEMA_SQL: Final[str] = """\
CREATE TABLE IF NOT EXISTS checkpoint_chain (
    sequence       INTEGER PRIMARY KEY AUTOINCREMENT,
    transition_id  TEXT    NOT NULL UNIQUE,
    prior_head     TEXT    NOT NULL,
    next_head      TEXT    NOT NULL,
    event_bytes    BLOB    NOT NULL,
    written_at     TEXT    NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_chain_next_head ON checkpoint_chain(next_head);
"""


_PRAGMAS: Final[tuple[str, ...]] = (
    "PRAGMA journal_mode=WAL;",
    "PRAGMA synchronous=FULL;",
    "PRAGMA busy_timeout=5000;",
)


def _default_clock() -> datetime:
    return datetime.now(UTC)


class SqliteCheckpointStore:
    """SQLite-WAL implementation of :class:`CheckpointStore`.

    One SQLite file per workflow (cleanup is ``rm -rf
    .codegenie/remediation/<run-id>/``). Per-workflow ``fcntl.flock``
    file beside each SQLite for cross-process exclusion (mirrors the
    Phase-3 :class:`ZstdAppendingFileSink` ``lock()`` shape).
    """

    __slots__ = ("_root", "_clock", "_connections")

    def __init__(
        self,
        root: Path,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._root = Path(root)
        self._clock = clock if clock is not None else _default_clock
        self._connections: dict[WorkflowId, sqlite3.Connection] = {}

    # ---- public Protocol surface -----------------------------------------

    def append(self, event: TransitionEvent) -> ChainHead:
        _assert_boundary(event)
        payload = _canonical_event_bytes(event)
        if len(payload) > _MAX_EVENT_BYTES:
            raise CheckpointPayloadTooLargeError(_PAYLOAD_TOO_LARGE_DIRECTIVE)
        # AC-12 — canonical sanitizer is the single regex-set declaration
        # site; forking ``re`` into this file would trip the AST fence
        # at tests/fence/test_checkpoint_sanitizer_imports.py.
        stored = sanitize_for_persistence(payload)
        # Phase-6 S2-02 AC-3 sanitization-aware chain discipline: the
        # chain head protects the BYTES ON DISK (the persisted, possibly
        # redacted payload), NOT the in-memory live event. This is the
        # invariant the replay verifier (S2-02) reproduces by reading
        # the persisted bytes and re-folding. For events with no
        # secret-shaped content the reconstructed event is byte-equal to
        # the live event, so chain heads are unchanged (existing
        # goldens valid).
        chain_input_event = TransitionEvent.model_validate_json(stored)
        with self.lock(event.workflow_id):
            conn = self._connection_for(event.workflow_id)
            prior = self._tail_chain_head_locked(conn)
            next_head = _compute_chain_head(prior, chain_input_event)
            written_at = self._clock().isoformat()
            conn.execute(
                "INSERT INTO checkpoint_chain "
                "(transition_id, prior_head, next_head, event_bytes, written_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    event.transition_id,
                    prior,
                    next_head,
                    stored,
                    written_at,
                ),
            )
            conn.commit()
            return next_head

    def read_all_for_workflow(self, workflow_id: WorkflowId) -> Iterator[TransitionEvent]:
        conn = self._connection_for(workflow_id)
        cursor = conn.execute("SELECT event_bytes FROM checkpoint_chain ORDER BY sequence ASC")
        for (row,) in cursor:
            yield TransitionEvent.model_validate_json(row)

    def iter_persisted_chain(
        self, workflow_id: WorkflowId
    ) -> Iterator[tuple[TransitionEvent, ChainHead]]:
        conn = self._connection_for(workflow_id)
        cursor = conn.execute(
            "SELECT event_bytes, next_head FROM checkpoint_chain ORDER BY sequence ASC"
        )
        for event_bytes, next_head in cursor:
            yield TransitionEvent.model_validate_json(event_bytes), ChainHead(next_head)

    def tail_chain_head(self, workflow_id: WorkflowId) -> ChainHead:
        conn = self._connection_for(workflow_id)
        return self._tail_chain_head_locked(conn)

    @contextmanager
    def lock(self, workflow_id: WorkflowId) -> Iterator[None]:
        path = self._workflow_dir(workflow_id) / "checkpoints.lock"
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)

    def close(self) -> None:
        for conn in self._connections.values():
            conn.close()
        self._connections.clear()

    # ---- private helpers --------------------------------------------------

    def _workflow_dir(self, workflow_id: WorkflowId) -> Path:
        return self._root / workflow_id

    def _connection_for(self, workflow_id: WorkflowId) -> sqlite3.Connection:
        cached = self._connections.get(workflow_id)
        if cached is not None:
            return cached
        directory = self._workflow_dir(workflow_id)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "checkpoints.sqlite"
        conn = sqlite3.connect(str(path), isolation_level=None)
        for pragma in _PRAGMAS:
            conn.execute(pragma)
        conn.executescript(_CHECKPOINT_SCHEMA_SQL)
        self._connections[workflow_id] = conn
        return conn

    def _tail_chain_head_locked(self, conn: sqlite3.Connection) -> ChainHead:
        """Return the persisted ``next_head`` of the most recent row, or genesis.

        **Detection-substrate-only** (AC-11): this method returns
        whatever the substrate persisted. No chain recomputation — that
        is the S2-02 verifier's job.
        """
        row = conn.execute(
            "SELECT next_head FROM checkpoint_chain ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return _GENESIS_CHAIN_HEAD
        return ChainHead(row[0])
