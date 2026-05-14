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

The first two defenses share a single primitive with :mod:`safe_yaml`:
:func:`codegenie.parsers._io.open_capped`. The depth walker is shared
via :func:`codegenie.parsers._depth.assert_max_depth`. Adding a future
parser (``safe_toml``, …) is a new caller of these primitives plus a new
``parser_kind`` literal — no edits to existing parsers.

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

import json
from pathlib import Path
from typing import Final

from codegenie.errors import MalformedJSONError
from codegenie.parsers import JSONValue
from codegenie.parsers._depth import assert_max_depth
from codegenie.parsers._io import open_capped

__all__ = ["JSONValue", "load"]

_PARSER_KIND: Final[str] = "safe_json"
_MAX_DECODE_DETAIL: Final[int] = 200


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
        MalformedJSONError: empty file, ``json.JSONDecodeError``, or
            top-level non-object (list / scalar / null).
        DepthCapExceeded: nesting exceeds ``max_depth``.
        FileNotFoundError: ``path`` does not exist — passes through.
        OSError: any other open-time error (``EISDIR``, ``EACCES``, …) —
            passes through unchanged.
    """
    data = open_capped(path, max_bytes=max_bytes, parser_kind=_PARSER_KIND)
    obj = _decode(data, path=path)
    assert_max_depth(obj, max_depth=max_depth, path=path, parser_kind=_PARSER_KIND)
    return obj


def _decode(data: bytes, *, path: Path) -> dict[str, JSONValue]:
    """Decode bytes; assert top-level-object shape."""
    if not data:
        raise MalformedJSONError(f"{path}: empty file")
    try:
        obj = json.loads(data)
    except json.JSONDecodeError as exc:
        detail = str(exc)[:_MAX_DECODE_DETAIL]
        raise MalformedJSONError(f"{path}: {detail}") from exc
    if not isinstance(obj, dict):
        raise MalformedJSONError(f"{path}: expected JSON object at top level")
    return obj
