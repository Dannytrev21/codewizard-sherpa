"""Shared file-open + size-cap primitive for ``codegenie.parsers``.

Single source of truth for the three pre-parse defenses every parser in
this package shares:

1. ``os.open(path, os.O_RDONLY | os.O_NOFOLLOW)`` — refuses a symlink at
   the final path component (``ELOOP``); translated to
   :class:`codegenie.errors.SymlinkRefusedError`. All other ``OSError``
   subclasses (``FileNotFoundError``, ``IsADirectoryError``,
   ``PermissionError``, …) propagate **unchanged**.
2. ``os.fstat(fd).st_size`` is checked **before** any ``os.read`` call;
   exceeding ``max_bytes`` raises :class:`codegenie.errors.SizeCapExceeded`
   without allocating the body.
3. ``try``/``finally`` wraps every read so ``os.close`` runs on every exit
   path — fd-lifecycle parity is asserted by the parser unit tests.

Each parser supplies its own ``parser_kind`` literal (``"safe_json"``,
``"safe_yaml"``, …) so the structured ``probe.parser.cap_exceeded`` event
remains discriminable downstream. This is the registry pattern in its
smallest possible form: the kernel knows nothing about specific parsers;
adding a future ``safe_toml`` is a new caller of this primitive with a
new ``parser_kind`` literal — zero edits here.

Sources:

- ``docs/phases/01-context-gather-layer-a-node/phase-arch-design.md``
  §"Component design" #8 — ``O_NOFOLLOW`` + size-cap rationale.
- ``docs/phases/01-context-gather-layer-a-node/ADRs/`` —
  ``0008-in-process-parse-caps-not-per-probe-sandbox.md`` (in-process
  caps replace per-probe sandboxes; this primitive is the chokepoint).
"""

from __future__ import annotations

import errno
import os
from pathlib import Path
from typing import Final

import structlog

from codegenie.errors import SizeCapExceeded, SymlinkRefusedError

__all__ = ["open_capped"]

_EVENT_CAP_EXCEEDED: Final[str] = "probe.parser.cap_exceeded"
_CAP_KIND_SIZE: Final[str] = "size"

_logger = structlog.get_logger(__name__)


def open_capped(path: Path, *, max_bytes: int, parser_kind: str) -> bytes:
    """Open ``path`` with ``O_NOFOLLOW``, enforce the size cap, return bytes.

    Args:
        path: File to read. Must be a regular file (or fail loudly).
        max_bytes: Hard upper bound on file size. Exceeding raises
            :class:`SizeCapExceeded` *before* any ``os.read`` is invoked.
        parser_kind: Caller-supplied discriminator (``"safe_json"``,
            ``"safe_yaml"``, …) — surfaces on the cap-exceeded event so
            downstream observability can attribute the violation.

    Returns:
        The file body as ``bytes`` (empty on a zero-byte file; the caller
        decides whether empty is malformed).

    Raises:
        SymlinkRefusedError: ``path``'s final component is a symlink
            (``OSError(errno=ELOOP)`` on the ``O_NOFOLLOW`` open).
        SizeCapExceeded: ``os.fstat(fd).st_size > max_bytes``.
        OSError: any other open-time error (``EISDIR``, ``EACCES``,
            ``ENOENT``, …) — propagates as the concrete subtype.
    """
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise SymlinkRefusedError(f"{path}: O_NOFOLLOW refused symlink") from exc
        raise

    try:
        size = os.fstat(fd).st_size
        if size > max_bytes:
            _emit_size_cap_event(path=path, cap=max_bytes, parser_kind=parser_kind)
            raise SizeCapExceeded(f"{path}: size={size} cap={max_bytes}")
        return os.read(fd, size) if size > 0 else b""
    finally:
        os.close(fd)


def _emit_size_cap_event(*, path: Path, cap: int, parser_kind: str) -> None:
    """Emit the single ``probe.parser.cap_exceeded`` event on size violation."""
    _logger.info(
        _EVENT_CAP_EXCEEDED,
        cap_kind=_CAP_KIND_SIZE,
        cap=cap,
        path=str(path),
        parser=parser_kind,
        parser_kind=parser_kind,
    )
