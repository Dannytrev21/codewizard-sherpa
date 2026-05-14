"""``jsonc.load`` — chokepoint JSONC (JSON-with-comments) reader.

JSONC is JSON with two extensions: line comments (``// ...`` through
end-of-line) and block comments (``/* ... */``, nestable). It is the
serialization format ``tsconfig.json`` uses; ``NodeBuildSystemProbe``
(S2-02) reads it.

The reader is a chained two-stage transform:

1. **Comment stripper** — :func:`_strip_comments` is a pure
   ``bytes -> bytes`` single-pass state machine. Strings containing
   ``//``, ``/*``, ``*/`` are preserved verbatim; backslash escapes
   inside strings (``\\"``, ``\\\\``) are honored; ``"`` inside a block
   comment is **inert** (does not transition to STRING). Nested block
   comments are supported via an integer depth counter. The stripper is
   the only hand-rolled parser in shared code — pathological inputs
   (unterminated strings, 1 MB unterminated block comments) complete in
   O(n) wall-clock and raise a typed error rather than scan back.
2. **JSON decode** — stdlib :func:`json.loads` on the stripped bytes
   (ADR-0009 forbids ``orjson`` / ``pyjson5``); top-level non-objects
   (lists / scalars / ``null``) raise :class:`MalformedJSONError`.

The three structural defenses every parser shares are honored:

1. ``os.open(path, os.O_RDONLY | os.O_NOFOLLOW)`` refuses a symlink
   whose final component is the link itself (``ELOOP``); translated to
   :class:`codegenie.errors.SymlinkRefusedError`. Only ``ELOOP``
   translates; ``FileNotFoundError``, ``IsADirectoryError``,
   ``PermissionError`` propagate unchanged. macOS still follows symlinks
   in *intermediate* path components; Phase 1's threat model only guards
   the final component (see arch §Filesystem scope).
2. Pre-parse size check via ``os.fstat(fd).st_size`` — the file body is
   **never read** when the size exceeds ``max_bytes``. Raises
   :class:`codegenie.errors.SizeCapExceeded`.
3. Post-parse depth walker (shared
   :func:`codegenie.parsers._depth.assert_max_depth`) descends both
   ``dict`` values and ``list`` items. Raises
   :class:`codegenie.errors.DepthCapExceeded`.

Unlike :mod:`safe_json` and :mod:`safe_yaml`, this module does not
delegate the open + read to :func:`codegenie.parsers._io.open_capped`:
JSONC needs an early ``MalformedJSONError(f"{path}: short read")``
diagnostic (the chained stripper cannot reconstruct a useful error from a
truncated buffer), and that detection has to sit beside the
``os.fstat`` / ``os.read`` calls. The open + cap + read + close shape
mirrors ``open_capped`` exactly; the duplication is ten lines and is the
right trade-off (Rule 2 — three similar lines beats premature
abstraction; Rule 3 — surgical changes).

Sources:

- ``docs/phases/01-context-gather-layer-a-node/phase-arch-design.md``
  §"Component design" #8 — interface, exception map, stripper rationale.
- ``docs/phases/01-context-gather-layer-a-node/phase-arch-design.md``
  §"Edge cases" row 8 — pathological tsconfig inputs.
- ``docs/phases/01-context-gather-layer-a-node/ADRs/`` —
  ``0008-in-process-parse-caps-not-per-probe-sandbox.md`` (ADR-0008)
  ratifies the in-process caps; the no-regex rule below is exactly the
  DoS risk ADR-0008 mitigates.
  ``0009-no-new-c-extension-parser-dependencies.md`` (ADR-0009) pins
  stdlib ``json`` only — no ``pyjson5`` / ``orjson`` / ``hjson``.

**No regex.** ``import re`` is forbidden in this module (asserted by
``test_module_does_not_import_re``); regex on hostile input is exactly
the DoS surface ADR-0008's caps mitigate.

Every typed exception this module raises is a **marker** — a single
positional formatted-message string with no instance state — preserving
the Phase-0 ``test_subclasses_are_markers_only`` invariant.
"""

from __future__ import annotations

import errno
import json
import os
from pathlib import Path
from typing import Final

import structlog

from codegenie.errors import (
    MalformedJSONError,
    SizeCapExceeded,
    SymlinkRefusedError,
)
from codegenie.logging import EVENT_PROBE_PARSER_CAP_EXCEEDED
from codegenie.parsers import JSONValue
from codegenie.parsers._depth import assert_max_depth

__all__ = ["JSONValue", "load"]

_PARSER_KIND: Final[str] = "jsonc"
_CAP_KIND_SIZE: Final[str] = "size"
_MAX_DECODE_DETAIL: Final[int] = 200

# State-machine states for _strip_comments.
_S_CODE: Final[int] = 0
_S_STRING: Final[int] = 1
_S_LINE_COMMENT: Final[int] = 2
_S_BLOCK_COMMENT: Final[int] = 3

# Byte sentinels (avoid repeated ord() in the hot loop).
_BYTE_NEWLINE: Final[int] = ord("\n")
_BYTE_BACKSLASH: Final[int] = ord("\\")
_BYTE_DOUBLE_QUOTE: Final[int] = ord('"')
_BYTE_SLASH: Final[int] = ord("/")
_BYTE_STAR: Final[int] = ord("*")

_logger = structlog.get_logger(__name__)


class _UnterminatedString(Exception):
    """Internal stripper signal — translated by :func:`load` to ``MalformedJSONError``.

    Kept private so :func:`_strip_comments` stays a pure ``bytes -> bytes``
    function (AC-10) — it neither knows nor needs the source path.
    """


class _UnterminatedBlockComment(Exception):
    """Internal stripper signal — translated by :func:`load` to ``MalformedJSONError``."""


def load(path: Path, *, max_bytes: int, max_depth: int = 64) -> dict[str, JSONValue]:
    """Parse ``path`` as a top-level JSONC object with size and depth caps.

    Args:
        path: File to read. Must be a regular file (or fail loudly).
        max_bytes: Hard upper bound on file size; exceeding raises
            :class:`SizeCapExceeded` *before* any bytes are read.
        max_depth: Maximum container nesting depth (``dict`` and ``list``
            edges combined). Defaults to 64.

    Returns:
        The decoded JSONC object as ``dict[str, JSONValue]``.

    Raises:
        SymlinkRefusedError: ``path``'s final component is a symlink
            (``OSError(errno=ELOOP)``).
        SizeCapExceeded: ``os.fstat(fd).st_size > max_bytes``.
        MalformedJSONError: empty file, short read, unterminated string,
            unterminated block comment, ``json.JSONDecodeError``, or
            top-level non-object (list / scalar / ``null``).
        DepthCapExceeded: nesting exceeds ``max_depth``.
        FileNotFoundError: ``path`` does not exist — passes through.
        OSError: any other open-time error (``EISDIR``, ``EACCES``, …) —
            passes through unchanged.
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
            _emit_size_cap_event(path=path, cap=max_bytes)
            raise SizeCapExceeded(f"{path}: size={size} cap={max_bytes}")
        data = os.read(fd, size) if size > 0 else b""
        if len(data) != size:
            raise MalformedJSONError(f"{path}: short read")
    finally:
        os.close(fd)

    try:
        stripped = _strip_comments(data)
    except _UnterminatedString as exc:
        raise MalformedJSONError(f"{path}: unterminated string") from exc
    except _UnterminatedBlockComment as exc:
        raise MalformedJSONError(f"{path}: unterminated block comment") from exc

    if not stripped:
        raise MalformedJSONError(f"{path}: empty file")

    try:
        obj = json.loads(stripped)
    except json.JSONDecodeError as exc:
        # AC-17: never include ``exc.doc`` (raw source bytes) — secret-leak channel.
        detail = str(exc)[:_MAX_DECODE_DETAIL]
        raise MalformedJSONError(f"{path}: {detail}") from exc

    if not isinstance(obj, dict):
        raise MalformedJSONError(f"{path}: expected JSON object at top level")

    assert_max_depth(obj, max_depth=max_depth, path=path, parser_kind=_PARSER_KIND)
    return obj


def _strip_comments(data: bytes) -> bytes:
    """Strip JSONC line and block comments. Pure ``bytes -> bytes``.

    Single-pass O(n) state machine over four states (``_S_CODE``,
    ``_S_STRING``, ``_S_LINE_COMMENT``, ``_S_BLOCK_COMMENT``). Strings are
    preserved verbatim with backslash-escape awareness; block comments
    nest (an ``int`` depth counter is the only state); ``"`` inside a
    block comment is inert (AC-15). The newline that terminates a line
    comment is preserved so downstream ``json.loads`` line numbers track
    the source file (AC-12).

    Raises:
        _UnterminatedString: input ended mid-string (no closing ``"``).
        _UnterminatedBlockComment: input ended mid-block-comment.
    """
    out = bytearray()
    state = _S_CODE
    block_depth = 0
    escaped = False
    i = 0
    n = len(data)

    while i < n:
        b = data[i]
        if state == _S_CODE:
            # Peek for `//` (line comment) or `/*` (block comment).
            if b == _BYTE_SLASH and i + 1 < n:
                nxt = data[i + 1]
                if nxt == _BYTE_SLASH:
                    state = _S_LINE_COMMENT
                    i += 2
                    continue
                if nxt == _BYTE_STAR:
                    state = _S_BLOCK_COMMENT
                    block_depth = 1
                    i += 2
                    continue
            if b == _BYTE_DOUBLE_QUOTE:
                state = _S_STRING
                escaped = False
                out.append(b)
                i += 1
                continue
            out.append(b)
            i += 1
        elif state == _S_STRING:
            # Always emit the byte; the escape flag governs only the
            # CLASSIFICATION of the *next* byte, not whether to emit this one.
            out.append(b)
            if escaped:
                escaped = False
            elif b == _BYTE_BACKSLASH:
                escaped = True
            elif b == _BYTE_DOUBLE_QUOTE:
                state = _S_CODE
            i += 1
        elif state == _S_LINE_COMMENT:
            if b == _BYTE_NEWLINE:
                out.append(b)  # AC-12: preserve the terminating newline.
                state = _S_CODE
            # else: drop the byte (it's inside the comment body).
            i += 1
        else:  # _S_BLOCK_COMMENT — `"` is inert here (AC-15).
            if b == _BYTE_SLASH and i + 1 < n and data[i + 1] == _BYTE_STAR:
                block_depth += 1
                i += 2
                continue
            if b == _BYTE_STAR and i + 1 < n and data[i + 1] == _BYTE_SLASH:
                block_depth -= 1
                i += 2
                if block_depth == 0:
                    state = _S_CODE
                continue
            i += 1

    if state == _S_STRING:
        raise _UnterminatedString
    if state == _S_BLOCK_COMMENT:
        raise _UnterminatedBlockComment
    # _S_LINE_COMMENT at EOF is harmless (no trailing newline; transitions
    # to _S_CODE implicitly by loop exit).

    result = bytes(out)
    # AC-11 structural invariant — stripper must never emit more bytes than it consumed.
    assert len(result) <= len(data), "jsonc stripper invariant: output must not exceed input"
    return result


def _emit_size_cap_event(*, path: Path, cap: int) -> None:
    """Emit the single ``probe.parser.cap_exceeded`` event on size violation.

    Mirrors :func:`codegenie.parsers._io._emit_size_cap_event` but with
    ``parser_kind="jsonc"`` so observers can attribute the violation.
    Depth-cap events are emitted by
    :func:`codegenie.parsers._depth.assert_max_depth`.
    """
    _logger.info(
        EVENT_PROBE_PARSER_CAP_EXCEEDED,
        cap_kind=_CAP_KIND_SIZE,
        cap=cap,
        path=str(path),
        parser=_PARSER_KIND,
        parser_kind=_PARSER_KIND,
    )
