"""Pre-dispatch input-snapshot pass — S1-08 (Gap 1 closure).

The coordinator calls :func:`compute_input_snapshot` for each probe before
dispatch, stat- and content-hashing every ``declared_inputs`` match exactly
once, and freezes the result on the runtime
:class:`codegenie.coordinator.budget.BudgetingContext`'s ``input_snapshot``
field. :func:`make_parsed_manifest_adapter` wraps the per-gather
:class:`codegenie.coordinator.parsed_manifest_memo.ParsedManifestMemo` so
``ctx.parsed_manifest(p)`` keys parsed dicts by the snapshot's
``content_hash`` rather than by live ``os.stat``. The Gap-1 TOCTOU window
between cache-key derivation and probe parse is closed within a single
gather: a file edited mid-gather cannot poison a probe's cache key, and
every probe that consumes the same path sees the same pinned bytes.

References
----------
- ``docs/phases/01-context-gather-layer-a-node/phase-arch-design.md``
  §"Gap analysis" Gap 1 (lines 982–990) — rationale and protocol.
- ``docs/phases/01-context-gather-layer-a-node/ADRs/0002-parsed-manifest-memo-on-probe-context.md``
  — the additive ``content_hash`` key shape (departure from arch's
  prescribed full-flip, recorded per Rule 7).
- ``docs/phases/00-bullet-tracer-foundations/ADRs/0001-cache-content-hash-algorithm.md``
  — BLAKE3 single-chokepoint discipline; all hashing routes through
  :func:`codegenie.hashing.content_hash_bytes`.
- ``docs/phases/00-bullet-tracer-foundations/ADRs/0007-probe-contract-frozen-by-doc-snapshot.md``
  — ``probes/base.py`` is stdlib-only; :class:`InputFingerprint`
  construction discipline lives here (this module), NOT as a classmethod
  on the newtype.

Design notes
------------
- **Functional core / imperative shell.** ``_fingerprint_from_fd`` is the
  pure half (an fd + bytes → :class:`InputFingerprint` mapping); the impure
  shell (``compute_input_snapshot``) owns globbing + open/close + event
  emission. The split is what lets the determinism property (T-10) be a
  simple equality test rather than a property-based test with FS mocking.
- **Phase 14 seam.** A future ``compute_input_snapshot_parallel`` sibling
  will fan out the inner loop across worker threads; today's sequential
  pass is correct and cheap (~5 ms p50 on the 1k-file fixture).
- **Adapter as Hexagonal port.** :func:`make_parsed_manifest_adapter`
  precomputes a ``{path: content_hash}`` dict once for O(1) lookups; Phase
  14's git-aware adapter swaps the implementation without editing this
  module.
"""

from __future__ import annotations

import errno
import os
import time
from collections.abc import Callable, Mapping
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any, Final, Protocol, runtime_checkable

import structlog

from codegenie.coordinator.parsed_manifest_memo import ParsedManifestMemo
from codegenie.hashing import content_hash_bytes
from codegenie.probes.base import InputFingerprint

__all__ = ["compute_input_snapshot", "make_parsed_manifest_adapter"]

# 50 MiB — see phase-arch-design.md §"Component design" #3. Probes that
# legitimately consume larger artifacts (e.g., SBOMs in Phase 2) get their
# own per-call ``max_bytes_per_file`` override; the default protects the
# warm-path probes (``package.json``, ``pnpm-lock.yaml``, …) from a
# pathological repo blowing the pre-dispatch I/O budget.
_DEFAULT_MAX_BYTES_PER_FILE: Final[int] = 52_428_800

# Sentinel content_hash values — the memo branches on the leading ``"<"`` to
# bypass caching (AC-15). Downstream consumers should check the prefix, not
# import these names, so the contract is the string protocol.
_CONTENT_HASH_OVERSIZE: Final[str] = "<oversize>"
_CONTENT_HASH_REFUSED: Final[str] = "<refused>"

_EVENT_COMPUTED: Final[str] = "probe.input_snapshot.computed"
_EVENT_OVERSIZE: Final[str] = "probe.input_snapshot.oversize"
_EVENT_SYMLINK_REFUSED: Final[str] = "probe.input_snapshot.symlink_refused"

_logger = structlog.get_logger(__name__)


@runtime_checkable
class _ProbeLike(Protocol):
    """Structural protocol — only the two fields the snapshot pass reads."""

    name: str
    declared_inputs: list[str]


def _fingerprint_from_fd(
    fd: int, abs_path: str, *, max_bytes: int
) -> tuple[InputFingerprint, bool]:
    """Build an :class:`InputFingerprint` from an open file descriptor.

    Returns ``(fingerprint, oversize)`` — the caller emits the oversize
    event so it can attribute the violation to the probe by name. The
    descriptor is consulted via :func:`os.fstat` (NOT a separate
    ``path.stat()`` — guarantees the size we cap-check matches the bytes
    we read).
    """
    st = os.fstat(fd)
    mtime_ns = st.st_mtime_ns
    size = st.st_size
    if size > max_bytes:
        return (
            InputFingerprint(
                path=abs_path,
                mtime_ns=mtime_ns,
                size=size,
                content_hash=_CONTENT_HASH_OVERSIZE,
            ),
            True,
        )
    data = os.read(fd, size) if size > 0 else b""
    return (
        InputFingerprint(
            path=abs_path,
            mtime_ns=mtime_ns,
            size=size,
            content_hash=content_hash_bytes(data),
        ),
        False,
    )


def _canonical_abs_path(matched: Path) -> str:
    """Return the absolute, canonicalized path WITHOUT following the final
    component as a symlink.

    The protocol — canonicalize the parent (which may legitimately involve
    symlinks pointing to real directories), then join the literal final
    component — guarantees:

    - For regular files: identical to ``str(matched.resolve())`` (the leaf
      is not a symlink, so following or not yields the same string).
    - For symlinks at the final component (refused branch): the
      fingerprint's ``path`` reflects the declared input name, not the
      symlink's target — which is what the probe declared and what every
      downstream lookup expects.
    """
    return str(matched.parent.resolve() / matched.name)


def _fingerprint_for_symlink(matched: Path) -> InputFingerprint:
    """Record a refused symlink without following it.

    ``mtime_ns`` and ``size`` are sourced from :func:`os.lstat` (the link's
    own stat, not the target's). The retry pathway is: delete the symlink
    and re-run; the next pass will hit ``_fingerprint_from_fd`` cleanly.
    """
    lst = os.lstat(matched)
    return InputFingerprint(
        path=_canonical_abs_path(matched),
        mtime_ns=lst.st_mtime_ns,
        size=lst.st_size,
        content_hash=_CONTENT_HASH_REFUSED,
    )


def compute_input_snapshot(
    probe: _ProbeLike,
    repo_root: Path,
    *,
    max_bytes_per_file: int = _DEFAULT_MAX_BYTES_PER_FILE,
) -> frozenset[InputFingerprint]:
    """Compute the per-probe input fingerprint set under ``repo_root``.

    For each pattern in ``probe.declared_inputs``, enumerate matches under
    ``repo_root`` via :func:`pathlib.Path.glob` and filter with
    :func:`fnmatch.fnmatchcase` so matching is case-sensitive even on
    case-insensitive filesystems (default macOS APFS, default Windows
    NTFS) — matches the S1-07 ``ParsedManifestMemo`` allowlist discipline.

    Each match is opened with ``os.O_RDONLY | os.O_NOFOLLOW`` to refuse a
    symlink at the final path component; ``os.fstat`` + ``os.read`` on the
    same fd guarantee the bytes hashed are the bytes whose size was just
    cap-checked.

    Rule 12 — every ``OSError`` propagates EXCEPT:

    - ``OSError(errno=ELOOP)`` → record ``_CONTENT_HASH_REFUSED`` sentinel.
    - ``FileNotFoundError`` (glob race; file vanished between ``glob`` and
      ``open``) → silently skip.

    Returns
    -------
    frozenset[InputFingerprint]
        Empty when ``declared_inputs`` is empty or no patterns match.

    Raises
    ------
    OSError
        Any subclass other than the two narrow cases above (e.g.
        :class:`PermissionError`, :class:`IsADirectoryError`,
        :class:`OSError(errno=EIO)`) propagates unchanged.
    """
    t0 = time.perf_counter()
    fingerprints: set[InputFingerprint] = set()
    oversize_count = 0
    # ``structlog.testing.capture_logs`` skips ``merge_contextvars``, so the
    # ambient ``run_id`` must be threaded explicitly onto every emitted
    # event — the lifecycle-event run_id-coverage test (S3-05 AC-23/24)
    # asserts this. Match the pattern in ``coordinator.py``.
    run_id = structlog.contextvars.get_contextvars().get("run_id")

    for pattern in probe.declared_inputs:
        for matched in repo_root.glob(pattern):
            rel = str(matched.relative_to(repo_root))
            # Case-sensitive post-filter — case_sensitive= is 3.12+, but
            # fnmatchcase works uniformly back to 3.11.
            if not fnmatchcase(rel, pattern):
                continue
            abs_path = _canonical_abs_path(matched)
            try:
                fd = os.open(matched, os.O_RDONLY | os.O_NOFOLLOW)
            except FileNotFoundError:
                # Glob race: matched then vanished — skip without an event.
                continue
            except OSError as exc:
                if exc.errno == errno.ELOOP:
                    fp = _fingerprint_for_symlink(matched)
                    fingerprints.add(fp)
                    _logger.info(
                        _EVENT_SYMLINK_REFUSED,
                        probe=probe.name,
                        path=fp.path,
                        run_id=run_id,
                    )
                    continue
                # Every other OSError propagates (Rule 12).
                raise

            try:
                fp, oversize = _fingerprint_from_fd(fd, abs_path, max_bytes=max_bytes_per_file)
            finally:
                os.close(fd)

            if oversize:
                oversize_count += 1
                _logger.warning(
                    _EVENT_OVERSIZE,
                    probe=probe.name,
                    path=fp.path,
                    size_bytes=fp.size,
                    cap_bytes=max_bytes_per_file,
                    run_id=run_id,
                )
            fingerprints.add(fp)

    wall_clock_ms = int((time.perf_counter() - t0) * 1000)
    total_bytes = sum(fp.size for fp in fingerprints if not fp.content_hash.startswith("<"))
    _logger.info(
        _EVENT_COMPUTED,
        probe=probe.name,
        entries=len(fingerprints),
        total_bytes=total_bytes,
        wall_clock_ms=wall_clock_ms,
        oversize_entries=oversize_count,
        run_id=run_id,
    )
    return frozenset(fingerprints)


def make_parsed_manifest_adapter(
    snapshot: frozenset[InputFingerprint],
    memo: ParsedManifestMemo,
) -> Callable[[Path], Mapping[str, Any] | None]:
    """Return the per-probe adapter the coordinator threads onto ``ctx``.

    The adapter precomputes a ``{path: content_hash}`` mapping once so each
    ``ctx.parsed_manifest(p)`` call is O(1). When the requested path is in
    the snapshot, the memo is keyed by ``content_hash`` (Gap-1 closure);
    when absent, the adapter passes ``content_hash=None`` and the memo
    falls back to S1-07's ``(absolute_path, mtime_ns, size)`` key shape.
    The path-resolution roundtrip — snapshot stored under
    ``str(matched.resolve())``, adapter looks up under
    ``str(path.resolve())`` — is the single most subtle correctness defect
    Phase 1 navigates; both halves are pinned by tests.
    """
    by_path: dict[str, str] = {fp.path: fp.content_hash for fp in snapshot}

    def _adapter(path: Path) -> Mapping[str, Any] | None:
        return memo.get(path, content_hash=by_path.get(str(path.resolve())))

    # Expose the underlying memo identity so coordinator-wiring tests can
    # assert same-gather sharing / cross-gather isolation without poking
    # through the closure cell. (S1-07's tests previously read
    # ``ctx.parsed_manifest.__self__`` when the ctx-bound callable was
    # ``memo.get``; the adapter is now a closure with no ``__self__``, so
    # we surface the memo as a labelled attribute.)
    _adapter.__memo__ = memo  # type: ignore[attr-defined]
    return _adapter
