"""Phase-4 S6-08 — JSONL projection writer for :class:`AttemptAnchor`.

Single function, not a class — pure I/O, no event-log writes. Called from
two sites (``FallbackTier.run`` refusal branches; ``FallbackTier.on_validated``
success branch), one file shape. ADR-04-0017 §Decision pins this surface.

Append-only discipline: ``O_APPEND`` guarantees atomic writes per line up to
``PIPE_BUF`` on POSIX. Directory mode ``0o700`` (operator-only); file mode
``0o600``. Both set explicitly via ``mkdir(mode=...)`` and ``os.open(..., mode=...)``
to remain umask-independent.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from codegenie.fallback.attempt_anchor import AttemptAnchor

__all__ = ["write"]

_DIR_MODE: Final[int] = 0o700
_FILE_MODE: Final[int] = 0o600


def _utc_date_dirname(timestamp_utc: datetime) -> str:
    """Render the anchor's ``timestamp_utc`` as a ``YYYY-MM-DD`` directory
    component anchored to UTC. Tz-aware enforcement is the anchor's own
    validator; this helper trusts that contract."""
    return timestamp_utc.astimezone(UTC).strftime("%Y-%m-%d")


def write(anchor: AttemptAnchor, output_dir: Path) -> None:
    """Append ``anchor`` as one JSONL line to
    ``{output_dir}/{utc-date}/{workflow_id}.jsonl``.

    AC-WRITER-1: pure I/O, no event-log writes.
    AC-WRITER-4: ``O_APPEND`` semantics — successive calls produce one line
    per call, no truncation.
    AC-WRITER-5: directory mode ``0o700``, file mode ``0o600``, both set
    explicitly via ``mkdir(mode=...)`` and ``os.open(..., mode=...)``.
    AC-WRITER-6: ``anchor.model_dump_json()`` produces the canonical
    schema_version=1 line — every consumer must round-trip via
    ``pydantic.TypeAdapter[AttemptAnchor].validate_json(...)``.
    """
    date_dir = output_dir / _utc_date_dirname(anchor.timestamp_utc)
    date_dir.mkdir(parents=True, exist_ok=True, mode=_DIR_MODE)

    file_path = date_dir / f"{anchor.workflow_id}.jsonl"
    payload = anchor.model_dump_json().encode("utf-8") + b"\n"

    fd = os.open(
        os.fspath(file_path),
        os.O_APPEND | os.O_CREAT | os.O_WRONLY,
        mode=_FILE_MODE,
    )
    try:
        os.write(fd, payload)
        os.fsync(fd)
    finally:
        os.close(fd)
