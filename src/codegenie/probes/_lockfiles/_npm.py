"""package-lock.json parser — thin ``safe_json.load`` wrapper.

The parser shapes nothing and validates no fields — its job is to
translate exactly one exception class (:class:`MalformedJSONError` ->
:class:`MalformedLockfileError`) while preserving the original on
``__cause__`` so the catch site in ``NodeManifestProbe`` (S3-05)
constructs the structured ``WarningId`` per ADR-0007 from
``exc.args[0]``.

All other typed exceptions raised by :func:`safe_json.load` propagate
unchanged (:class:`SizeCapExceeded`, :class:`DepthCapExceeded`,
:class:`SymlinkRefusedError`). ``FileNotFoundError`` and other
``OSError`` subclasses propagate from the underlying open.

npm's lockfile has three on-disk shapes:

- ``lockfileVersion`` 1 (npm 5/6): legacy nested ``dependencies`` only.
- ``lockfileVersion`` 2 (npm 7+): both flat ``packages`` and nested
  ``dependencies`` (for backward compatibility — why this format is
  larger than pnpm/yarn equivalents and why the 50 MB cap matters).
- ``lockfileVersion`` 3 (npm 9+): flat ``packages`` only.

``NpmLock`` is ``total=False`` to admit all three shapes without
defaulting at the parser layer — version reconciliation is
``NodeManifestProbe``'s job.

Sources:

- ``docs/phases/01-context-gather-layer-a-node/phase-arch-design.md``
  §"Component design" #9 — interface and ~100 ms p50 budget.
- ``docs/phases/01-context-gather-layer-a-node/ADRs/`` —
  ``0008-in-process-parse-caps-not-per-probe-sandbox.md`` (ADR-0008)
  ratifies the in-process caps; ``0009-no-new-c-extension-parser-dependencies.md``
  (ADR-0009) pins stdlib ``json`` as the only allowed JSON parser.

Phase-0 marker invariant: :class:`MalformedLockfileError` accepts a
single positional message string; the path lives in ``args[0]``, the
cause lives on ``__cause__`` via ``raise ... from cause``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Final, TypedDict, cast

from codegenie.errors import MalformedJSONError, MalformedLockfileError
from codegenie.parsers import safe_json

__all__ = ["NpmLock", "parse"]

NPM_LOCKFILE_MAX_BYTES: Final[int] = 50 * 1024 * 1024
NPM_LOCKFILE_MAX_DEPTH: Final[int] = 64


class NpmLock(TypedDict, total=False):
    """``package-lock.json`` shape — ``total=False`` is load-bearing.

    npm v1 ships ``dependencies`` only; v2 ships both ``packages`` and
    ``dependencies``; v3 ships ``packages`` only. The parser does NOT
    default missing keys — version reconciliation is
    ``NodeManifestProbe``'s job.
    """

    name: str
    version: str
    lockfileVersion: int
    requires: bool
    packages: dict[str, Any]
    dependencies: dict[str, Any]


def parse(path: Path) -> NpmLock:
    """Parse a ``package-lock.json`` under the 50 MB / depth 64 caps.

    Raises:
        SizeCapExceeded: re-raised unchanged from ``safe_json.load``.
        DepthCapExceeded: re-raised unchanged from ``safe_json.load``.
        SymlinkRefusedError: re-raised unchanged from ``safe_json.load``.
        MalformedLockfileError: translated from ``MalformedJSONError``;
            the original is preserved on ``__cause__``. The message in
            ``args[0]`` includes ``str(path)`` so downstream
            ``WarningId`` construction can recover the path. Covers all
            three ``safe_json`` malformed-JSON paths: decode error,
            empty file, and top-level non-mapping.
        FileNotFoundError: propagated from the underlying open.
    """
    try:
        raw = safe_json.load(
            path,
            max_bytes=NPM_LOCKFILE_MAX_BYTES,
            max_depth=NPM_LOCKFILE_MAX_DEPTH,
        )
    except MalformedJSONError as cause:
        raise MalformedLockfileError(f"{path}: {type(cause).__name__}: {cause}") from cause
    return cast(NpmLock, raw)
