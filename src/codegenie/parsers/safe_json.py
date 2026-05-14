"""``safe_json.load`` — chokepoint JSON reader with O_NOFOLLOW + size + depth caps.

Every Phase 1 probe that reads JSON (``package.json``, ``package-lock.json``,
``tsconfig.json`` via :mod:`codegenie.parsers.jsonc`) routes through this
function. The three structural defenses are:

1. ``os.open(path, os.O_RDONLY | os.O_NOFOLLOW)`` refuses a symlink whose
   final component is the symlink itself (``ELOOP``) — translated to
   :class:`codegenie.errors.SymlinkRefusedError`. macOS still follows
   symlinks in *intermediate* path components; Phase 1's threat model only
   guards the final component (see arch §Filesystem scope).
2. Pre-parse size check via ``os.fstat`` — the file body is **never read**
   when the size exceeds ``max_bytes``. Raises
   :class:`codegenie.errors.SizeCapExceeded`.
3. Post-parse depth walker (stdlib-only second pass) — descends both
   ``dict`` values and ``list`` items. Raises
   :class:`codegenie.errors.DepthCapExceeded`. The stdlib ``json`` C
   extension exposes no native depth limit, so this walker is load-bearing.

Sources:

- ``docs/phases/01-context-gather-layer-a-node/phase-arch-design.md``
  §"Component design" #8 — full interface, exception map.
- ``docs/phases/01-context-gather-layer-a-node/ADRs/`` —
  ``0008-in-process-parse-caps-not-per-probe-sandbox.md`` (ADR-0008)
  ratifies the in-process caps; ``0009-no-new-c-extension-parser-dependencies.md``
  (ADR-0009) pins stdlib ``json`` only — no ``orjson`` / ``pyjson5``.

Every typed exception this module raises is a **marker** — a single
positional formatted-message string with no instance state — preserving the
Phase-0 ``test_subclasses_are_markers_only`` invariant. The catch site (a
probe) reconstructs the structured ``WarningId`` per ADR-0007 from probe
context; the message in ``args[0]`` carries the path + cap/detail for
human-readable error reporting.
"""

from __future__ import annotations

import errno
import json
import os
from pathlib import Path
from typing import Final

import structlog

from codegenie.errors import (
    DepthCapExceeded,
    MalformedJSONError,
    SizeCapExceeded,
    SymlinkRefusedError,
)
from codegenie.parsers import JSONValue

__all__ = ["JSONValue", "load"]

_PARSER_NAME: Final[str] = "safe_json"
_EVENT_CAP_EXCEEDED: Final[str] = "probe.parser.cap_exceeded"
_MAX_DECODE_DETAIL: Final[int] = 200

_logger = structlog.get_logger(__name__)


def load(path: Path, *, max_bytes: int, max_depth: int = 64) -> dict[str, JSONValue]:
    """Parse ``path`` as a top-level JSON object with size and depth caps.

    Args:
        path: File to read. Must be a regular file (or fail loudly).
        max_bytes: Hard upper bound on file size; exceeding raises
            :class:`SizeCapExceeded` *before* any bytes are read.
        max_depth: Maximum nesting depth (dict-edges + list-edges combined).
            Defaults to 64 — Phase 1's published cap for ``package.json``
            and friends.

    Returns:
        The decoded JSON object as ``dict[str, JSONValue]``.

    Raises:
        SymlinkRefusedError: ``path``'s final component is a symlink
            (``OSError(errno=ELOOP)``).
        SizeCapExceeded: ``os.fstat(fd).st_size > max_bytes``.
        MalformedJSONError: empty file, short read, ``json.JSONDecodeError``,
            or top-level non-object (list / scalar / null).
        DepthCapExceeded: nesting exceeds ``max_depth``.
        FileNotFoundError: ``path`` does not exist — passes through.
        OSError: any other open-time error (``EISDIR``, ``EACCES``, …) —
            passes through unchanged.
    """
    data = _open_and_read(path, max_bytes=max_bytes)
    return _decode_and_validate(data, path=path, max_depth=max_depth)


def _open_and_read(path: Path, *, max_bytes: int) -> bytes:
    """Open ``path`` with O_NOFOLLOW, enforce the size cap, return the bytes.

    Symlink at the final component → :class:`SymlinkRefusedError`. Oversize
    → :class:`SizeCapExceeded` *before* any read. Short read →
    :class:`MalformedJSONError`. All other ``OSError`` subtypes propagate.
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
            _emit_cap_event(cap_kind="size", path=path)
            raise SizeCapExceeded(f"{path}: size={size} cap={max_bytes}")
        data = os.read(fd, size) if size > 0 else b""
        if len(data) != size:
            raise MalformedJSONError(f"{path}: short read")
        return data
    finally:
        os.close(fd)


def _decode_and_validate(data: bytes, *, path: Path, max_depth: int) -> dict[str, JSONValue]:
    """Decode bytes, enforce top-level-object shape, run the depth walker."""
    if not data:
        raise MalformedJSONError(f"{path}: empty file")
    try:
        obj = json.loads(data)
    except json.JSONDecodeError as exc:
        detail = str(exc)[:_MAX_DECODE_DETAIL]
        raise MalformedJSONError(f"{path}: {detail}") from exc
    if not isinstance(obj, dict):
        raise MalformedJSONError(f"{path}: expected JSON object at top level")
    _assert_depth(obj, max_depth=max_depth, current=0, path=path)
    return obj


def _assert_depth(obj: object, *, max_depth: int, current: int, path: Path) -> None:
    """Recursively assert the nested structure does not exceed ``max_depth``.

    Depth counts *container nesting*, not scalar leaves. The root dict is
    depth ``0``; descending into one nested container makes the inner
    container depth ``1``. ``current == max_depth`` is allowed;
    ``current > max_depth`` raises. Scalars terminate the walk without
    counting against the cap (a deeply-nested ``True`` is not deeper than
    the dict that contains it).
    """
    if not isinstance(obj, (dict, list)):
        return
    if current > max_depth:
        _emit_cap_event(cap_kind="depth", path=path)
        raise DepthCapExceeded(f"{path}: depth>{max_depth}")
    next_depth = current + 1
    if isinstance(obj, dict):
        for value in obj.values():
            _assert_depth(value, max_depth=max_depth, current=next_depth, path=path)
    else:
        for item in obj:
            _assert_depth(item, max_depth=max_depth, current=next_depth, path=path)


def _emit_cap_event(*, cap_kind: str, path: Path) -> None:
    """Emit the single ``probe.parser.cap_exceeded`` structlog event.

    S1-10 will lift the literal event name into a module-level constant in
    :mod:`codegenie.logging`; this story uses the literal pending that.
    """
    _logger.info(
        _EVENT_CAP_EXCEEDED,
        cap_kind=cap_kind,
        path=str(path),
        parser=_PARSER_NAME,
        parser_kind=_PARSER_NAME,
    )
