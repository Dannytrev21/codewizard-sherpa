"""Local file-read helper for ``codegenie.conventions``.

The :class:`codegenie.probes.base.RepoSnapshot` contract is frozen by Phase 0
ADR-0007 — no ``read_text`` method, no factory. ``_apply_*`` helpers in
``catalog.py`` read repo files at ``repo.root / relpath`` via this small
capped reader rather than amending the frozen contract.

The cap is conservative (1 MiB by default — non-idiomatic Dockerfiles and
config files do not exceed this). Files beyond the cap are *truncated* by
this reader — pattern matches happen against the first ``max_bytes`` only.
This matches the Phase 2 documented behavior (S2-02 story §"Goal" Invariant
11): an operator inspecting unusual repos can observe the truncation via
byte-counting, but pattern checks remain bounded.

This helper is the *only* file-read entry point from the ``_apply_*``
helpers. Adding additional readers requires a follow-up ADR.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

__all__ = ["DEFAULT_MAX_BYTES", "read_capped_text"]

DEFAULT_MAX_BYTES: Final[int] = 1 << 20


def read_capped_text(path: Path, *, max_bytes: int = DEFAULT_MAX_BYTES) -> str | None:
    """Return decoded text up to ``max_bytes``; ``None`` if the file does not exist.

    TOCTOU-safe: a ``FileNotFoundError`` between the caller's existence check
    and this read returns ``None`` rather than propagating.

    Args:
        path: File to read.
        max_bytes: Hard upper bound on bytes consumed; defaults to 1 MiB.

    Returns:
        The decoded text (``utf-8`` with ``errors="replace"``) or ``None``
        when the file is absent.
    """
    try:
        with path.open("rb") as fh:
            return fh.read(max_bytes).decode("utf-8", errors="replace")
    except FileNotFoundError:
        return None
