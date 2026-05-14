"""pnpm-lock.yaml parser — thin ``safe_yaml.load`` wrapper.

The parser shapes nothing and validates no fields — its job is to
translate exactly one exception class (:class:`MalformedYAMLError` ->
:class:`MalformedLockfileError`) while preserving the original on
``__cause__`` so the catch site in ``NodeManifestProbe`` (S3-05)
constructs the structured ``WarningId`` per ADR-0007 from
``exc.args[0]``.

All other typed exceptions raised by :func:`safe_yaml.load` propagate
unchanged (:class:`SizeCapExceeded`, :class:`DepthCapExceeded`,
:class:`SymlinkRefusedError`). ``FileNotFoundError`` and other
``OSError`` subclasses propagate from the underlying open.

Sources:

- ``docs/phases/01-context-gather-layer-a-node/phase-arch-design.md``
  §"Component design" #9 — interface and ~250 ms p50 budget.
- ``docs/phases/01-context-gather-layer-a-node/ADRs/`` —
  ``0008-in-process-parse-caps-not-per-probe-sandbox.md`` (ADR-0008)
  ratifies the in-process caps;
  ``0009-no-new-c-extension-parser-dependencies.md`` (ADR-0009) pins
  ``CSafeLoader`` as the only allowed YAML loader.

Phase-0 marker invariant: :class:`MalformedLockfileError` accepts a
single positional message string; the path lives in ``args[0]``, the
cause lives on ``__cause__`` via ``raise ... from cause``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Final, TypedDict, cast

from codegenie.errors import MalformedLockfileError, MalformedYAMLError
from codegenie.parsers import safe_yaml

__all__ = ["PnpmLock", "parse"]

PNPM_LOCKFILE_MAX_BYTES: Final[int] = 50 * 1024 * 1024
PNPM_LOCKFILE_MAX_DEPTH: Final[int] = 64


class PnpmLock(TypedDict, total=False):
    """``pnpm-lock.yaml`` shape — ``total=False`` is load-bearing.

    pnpm v6 ships ``lockfileVersion``, ``packages``, ``importers``;
    pnpm v9 adds ``snapshots``. The parser does NOT default missing
    keys — version reconciliation is ``NodeManifestProbe``'s job.
    """

    lockfileVersion: str | float
    packages: dict[str, Any]
    importers: dict[str, Any]
    snapshots: dict[str, Any]


def parse(path: Path) -> PnpmLock:
    """Parse a ``pnpm-lock.yaml`` under the 50 MB / depth 64 caps.

    Raises:
        SizeCapExceeded: re-raised unchanged from ``safe_yaml.load``.
        DepthCapExceeded: re-raised unchanged from ``safe_yaml.load``.
        SymlinkRefusedError: re-raised unchanged from ``safe_yaml.load``.
        MalformedLockfileError: translated from ``MalformedYAMLError``;
            the original is preserved on ``__cause__``. The message in
            ``args[0]`` includes ``str(path)`` so downstream
            ``WarningId`` construction can recover the path.
        FileNotFoundError: propagated from the underlying open.
    """
    try:
        raw = safe_yaml.load(
            path,
            max_bytes=PNPM_LOCKFILE_MAX_BYTES,
            max_depth=PNPM_LOCKFILE_MAX_DEPTH,
        )
    except MalformedYAMLError as cause:
        raise MalformedLockfileError(f"{path}: {type(cause).__name__}: {cause}") from cause
    return cast(PnpmLock, raw)
