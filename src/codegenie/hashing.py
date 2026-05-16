"""BLAKE3 + SHA-256 chokepoint for every hash decision in codegenie (ADR-0001).

This module is the **single source of truth** for hashing. By contract — see
``docs/phases/00-bullet-tracer-foundations/ADRs/0001-cache-content-hash-algorithm.md``
— no other file under ``src/codegenie/`` imports ``blake3`` or
``hashlib.sha256``. Phase 0 enforces this discipline by code review; an
AST-scan analog is deferred to Phase 1 (see story S2-03 §Out of scope).

The split:

- **BLAKE3** for bulk content hashing (``content_hash``, ``content_hash_of_inputs``)
  — cryptographic AND ~3 GB/s on commodity hardware.
- **SHA-256** for the cache-key identity tuple and audit anchor
  (``identity_hash``) — stable across CPython upgrades and compatible with the
  ``localv2.md §8`` audit-anchor format.

Return values are prefix-tagged (``blake3:<64-hex>`` or ``sha256:<64-hex>``)
so on-disk artifacts are self-describing across future algorithm migrations.

``blake3`` is **lazy-imported inside every public function that uses it**:
keeping it out of ``import codegenie.hashing``'s transitive closure preserves
the CLI ``--help`` cold-start budget. ``hashlib`` is stdlib and imported at
module top.

The separator bytes (``\\x1f`` unit, ``\\x1e`` record) are ASCII control
characters that cannot appear in a filesystem path on POSIX or Windows, nor
in a stringified integer size — using them defuses the boundary-shift
collision attack a printable separator like ``|`` would open.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Iterable
from pathlib import Path

__all__ = [
    "content_hash",
    "content_hash_bytes",
    "content_hash_fd",
    "content_hash_of_inputs",
    "identity_hash",
    "identity_hash_bytes",
]


_UNIT_SEP = "\x1f"
_RECORD_SEP = b"\x1e"
_CHUNK_BYTES = 65_536


def content_hash(path: Path) -> str:
    """Return ``blake3:<64-hex>`` of the file at ``path``, streamed in 64 KB chunks.

    Streams to bound memory at the chunk size regardless of file size; the
    digest is identical to the single-shot ``blake3(bytes)`` of the same
    contents.
    """
    from blake3 import blake3 as _blake3

    hasher = _blake3()
    with path.open("rb") as f:
        while chunk := f.read(_CHUNK_BYTES):
            hasher.update(chunk)
    return f"blake3:{hasher.hexdigest()}"


def identity_hash(*parts: str) -> str:
    """Return ``sha256:<64-hex>`` of the joined ``parts`` (cache-key identity).

    A one-byte arity witness (``min(len(parts), 255)``) is prepended to the
    ``\\x1f``-joined payload so that distinct part-tuples never collide:
    ``identity_hash()`` differs from ``identity_hash("")``, and boundary-shift
    attacks like ``identity_hash("ab", "c")`` vs ``identity_hash("a", "bc")``
    are blocked.
    """
    arity_byte = bytes([min(len(parts), 255)])
    joined = _UNIT_SEP.join(parts).encode("utf-8")
    digest = hashlib.sha256(arity_byte + joined).hexdigest()
    return f"sha256:{digest}"


def content_hash_bytes(b: bytes) -> str:
    """Return ``blake3:<64-hex>`` of the in-memory bytes ``b``.

    Companion to :func:`content_hash` that takes already-materialized bytes
    rather than a file path. Used by the cache store to compute the
    content-addressed BLAKE3 filename for a serialized probe blob without
    making the cache import ``blake3`` directly (ADR-0001 chokepoint
    discipline).
    """
    from blake3 import blake3 as _blake3

    return f"blake3:{_blake3(b).hexdigest()}"


def identity_hash_bytes(b: bytes) -> str:
    """Return ``sha256:<64-hex>`` of the in-memory bytes ``b``.

    Companion to :func:`identity_hash`: takes raw bytes (rather than a
    variadic string tuple) so the cache store can compute the tamper-check
    SHA-256 of a serialized blob without importing ``hashlib.sha256``
    directly. ADR-0001's "one chokepoint" invariant is preserved — this is
    an *additive* extension to the chokepoint, not a bypass.
    """
    return f"sha256:{hashlib.sha256(b).hexdigest()}"


def content_hash_fd(fd: int, *, offset: int, size: int) -> str:
    """Return ``blake3:<64-hex>`` of ``size`` bytes starting at ``offset`` in ``fd``.

    Streams ``os.read(fd, 64 KiB)`` chunks through the running BLAKE3 hasher
    without materializing the body as a single ``bytes`` value — the budget
    that ``SkillsLoader`` (S2-01) protects with a ``tracemalloc`` peak of
    < 20 KB on a 100 MB body. The digest is identical to
    :func:`content_hash_bytes` of the same span.

    The function ``os.lseek(fd, offset, os.SEEK_SET)`` first; the caller's
    file-descriptor position is therefore mutated. Callers that share the
    fd with other readers must restore the cursor or reopen.

    Args:
        fd: Open file descriptor (from ``os.open``). The function does not
            close it — fd lifecycle remains the caller's responsibility.
        offset: Byte offset from start-of-file to begin hashing.
        size: Number of bytes to hash. Reading fewer bytes than ``size``
            (e.g., file truncated mid-read) raises :class:`OSError`.

    Returns:
        ``f"blake3:{hexdigest}"`` — same format as :func:`content_hash`.

    Raises:
        OSError: ``os.lseek`` or ``os.read`` fails; fewer than ``size``
            bytes available.
    """
    from blake3 import blake3 as _blake3

    os.lseek(fd, offset, os.SEEK_SET)
    hasher = _blake3()
    remaining = size
    while remaining > 0:
        chunk = os.read(fd, min(_CHUNK_BYTES, remaining))
        if not chunk:
            raise OSError(
                f"content_hash_fd: short read — expected {size} bytes from offset "
                f"{offset}, got {size - remaining}"
            )
        hasher.update(chunk)
        remaining -= len(chunk)
    return f"blake3:{hasher.hexdigest()}"


def content_hash_of_inputs(paths: Iterable[Path]) -> str:
    """Return ``blake3:<64-hex>`` of a sort-stable manifest of ``paths``.

    The manifest is the sorted list of ``(str(path), st_size)`` tuples — hashed
    as ``"<path>\\x1f<size>"`` records joined by ``\\x1e``. The function hashes
    the **manifest**, not the file contents, so two files at identical paths
    with identical sizes but different bytes produce the same hash. This is
    the cache-key fingerprint shape; ``content_hash`` is the per-file content
    digest.

    ``FileNotFoundError`` from ``Path.stat`` propagates uncaught; the cache
    store catches it and treats the lookup as a miss.
    """
    from blake3 import blake3 as _blake3

    manifest = sorted((str(p), p.stat().st_size) for p in paths)
    serialized = _RECORD_SEP.join(f"{p}{_UNIT_SEP}{s}".encode() for p, s in manifest)
    return f"blake3:{_blake3(serialized).hexdigest()}"
