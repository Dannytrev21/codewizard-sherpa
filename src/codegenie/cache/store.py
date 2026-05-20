"""Content-addressed cache store — JSONL index + sharded blobs (ADR-0001, ADR-0011).

Storage layout under ``cache_dir``::

    cache_dir/
      index.jsonl                              # append-only, one record per line
      blobs/
        <2-char-blake3-shard>/
          <blake3-hex>.json                    # serialized ``ProbeOutput``

**Identity vs content split (ADR-0001).** The blob filename uses the BLAKE3
content hash of the serialized blob bytes (~3 GB/s); the index record carries
*both* the BLAKE3 filename component *and* a SHA-256 of the same bytes — the
SHA-256 is the tamper-check that ``get`` recomputes before returning, and the
audit anchor S3-06's ``AuditWriter`` reads (ADR-0004).

**Miss-on-error (``phase-arch-design.md §Failure behavior``).** Four
independent paths collapse to ``get(...) == None`` plus one structured log
event each: blob unreadable as JSON, blob SHA-256 mismatch, blob missing
underneath an index record, TTL-stale index record. The coordinator's response
is to re-run the probe — **never** to raise to the user. The single in-process
precondition that does raise is the record-size guard (story AC-12): a record
whose serialized length would exceed ``PIPE_BUF=4096`` bytes breaks the
``O_APPEND`` atomicity invariant from edge-case 12, so ``put`` rejects it
loudly rather than tearing concurrent records.

**Permissions (ADR-0011).** Directories ``0700``, files ``0600``. The full
mode re-walk runs once in ``__init__`` to defeat the CI ``actions/cache``
restore that flattens modes to umask defaults — a restore happens at process
start, so one walk per process catches it. Each ``put`` then re-asserts modes
only on the blob and index line it just wrote; nothing else flattens modes
mid-process. Tests assert post-``put`` state, not the transient post-restore
window.

**Concurrency.** ``index.jsonl`` is opened ``O_APPEND`` and written with a
single ``os.write`` call so the kernel guarantees record-level atomicity for
records ≤ ``PIPE_BUF`` (POSIX). Blob writes are atomic via the
``<dest>.tmp → fsync → os.replace`` sequence. Phase 14's webhook fan-out
stress-test lives in S5-01's ``test_cache_concurrent.py``; the unit tests
here cover single-process correctness.
"""

from __future__ import annotations

import json
import os
import secrets
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from codegenie.cache.keys import _ProbeLike
from codegenie.cache.keys import key_for as _key_for_module
from codegenie.errors import CacheError
from codegenie.hashing import content_hash_bytes, identity_hash_bytes

if TYPE_CHECKING:
    from codegenie.output.sanitizer import SanitizedProbeOutput
    from codegenie.probes.base import ProbeOutput, RepoSnapshot, Task


__all__ = ["CacheStore", "serialize_output"]

_MAX_RECORD_BYTES = 4096  # PIPE_BUF on Linux/macOS; concurrent O_APPEND atomicity bound
_DIR_MODE = 0o700
_FILE_MODE = 0o600

_log = structlog.get_logger(__name__)


def serialize_output(output: ProbeOutput | SanitizedProbeOutput) -> bytes:
    """Serialize a probe output to deterministic JSON bytes.

    Single source of truth for blob canonicalization — used by both
    :meth:`CacheStore.put` (writes the blob) and
    :class:`codegenie.audit.AuditWriter` (computes the audit anchor over the
    *same* bytes). ``sort_keys=True`` + ``separators=(",", ":")`` produces
    byte-identical output for byte-identical content, so the BLAKE3 filename
    and SHA-256 audit anchor are both reproducible on a second run.

    The signature accepts both :class:`ProbeOutput` and
    :class:`SanitizedProbeOutput` — they share the same six fields by
    construction (``output/sanitizer.py:50``), and the audit writer hashes
    the *sanitized* form (ADR-0004 §Consequences) while the cache stores
    the same sanitized bytes.
    """
    payload: dict[str, Any] = {
        "schema_slice": output.schema_slice,
        "raw_artifacts": [str(p) for p in output.raw_artifacts],
        "confidence": output.confidence,
        "duration_ms": output.duration_ms,
        "warnings": list(output.warnings),
        "errors": list(output.errors),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


# Backward-compatible alias for the pre-S3-06 private name. The S3-01 test
# ``test_serialized_blob_is_deterministic`` imports ``_serialize_output``;
# keeping the alias avoids a churn-only test edit. New call sites use the
# public ``serialize_output``.
_serialize_output = serialize_output


def _deserialize_output(blob_bytes: bytes) -> ProbeOutput:
    from codegenie.probes.base import ProbeOutput

    obj = json.loads(blob_bytes)
    return ProbeOutput(
        schema_slice=obj["schema_slice"],
        raw_artifacts=[Path(p) for p in obj["raw_artifacts"]],
        confidence=obj["confidence"],
        duration_ms=obj["duration_ms"],
        warnings=list(obj["warnings"]),
        errors=list(obj["errors"]),
    )


def _atomic_write_bytes(target: Path, data: bytes) -> None:
    """Write ``data`` to ``target`` via per-writer tmp + fsync + os.replace.

    The tmp filename embeds ``os.getpid()`` + a random short token so two
    concurrent ``codegenie gather`` processes writing the same blob path
    do not race on the same ``<target>.tmp`` slot (edge case #12 in
    ``phase-arch-design.md §789``). Without this disambiguation, the second
    writer's ``os.replace`` raises ``FileNotFoundError`` after the first's
    replace has already moved the shared tmp out of the way.
    """
    tmp = target.with_suffix(target.suffix + f".{os.getpid()}.{secrets.token_hex(4)}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, _FILE_MODE)
    try:
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, target)


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, _DIR_MODE)


def _reapply_modes(root: Path) -> None:
    """Re-walk ``root`` and re-apply ``0700``/``0600`` modes (ADR-0011).

    Idempotent; defeats the ``actions/cache`` umask flattening between
    restore and the next write. Cross-platform safe (Windows treats mode
    bits as advisory). ``FileNotFoundError`` is tolerated mid-walk — under
    concurrent ``put`` calls another process's ``<dest>.tmp`` may be
    listed by ``os.walk`` and then unlinked by that process's
    ``os.replace`` before this loop reaches it.
    """
    try:
        os.chmod(root, _DIR_MODE)
    except FileNotFoundError:
        return
    for current, dirs, files in os.walk(root):
        for d in dirs:
            try:
                os.chmod(Path(current) / d, _DIR_MODE)
            except FileNotFoundError:
                continue
        for f in files:
            try:
                os.chmod(Path(current) / f, _FILE_MODE)
            except FileNotFoundError:
                continue


class CacheStore:
    """Filesystem cache for :class:`ProbeOutput` values, keyed by SHA-256 identity.

    Construct with the cache root directory and a TTL in hours. The store
    is stateless across instances — every read/write touches the index and
    the blob tree directly; restarting the process loses nothing.
    """

    def __init__(self, cache_dir: Path, ttl_hours: int) -> None:
        self._cache_dir = cache_dir
        self._ttl_hours = ttl_hours
        # In-memory {key: latest_record} view of index.jsonl, lazily built
        # and reused while the file size is unchanged. index.jsonl is
        # append-only, so its size strictly increases — a changed size is a
        # cheap, exact signal that a record was appended (by this process or
        # a concurrent one) and the map must be rebuilt.
        self._index_cache: dict[str, dict[str, Any]] | None = None
        self._index_size: int = -1
        _ensure_dir(self._cache_dir)
        # One full mode re-walk per process. The ``actions/cache`` restore
        # that flattens modes to umask defaults happens at process start, so
        # a single walk here catches it; each ``put`` re-asserts modes only
        # on what it wrote.
        _reapply_modes(self._cache_dir)

    # ------------------------------------------------------------------ paths

    @property
    def _index_path(self) -> Path:
        return self._cache_dir / "index.jsonl"

    def _blob_path(self, blake3_hex: str) -> Path:
        shard = blake3_hex[:2]
        return self._cache_dir / "blobs" / shard / f"{blake3_hex}.json"

    # ------------------------------------------------------------------ keys

    def key_for(self, probe: _ProbeLike, snapshot: RepoSnapshot, task: Task) -> str:
        """Delegate to :func:`codegenie.cache.keys.key_for`.

        Pure pass-through — the ``(probe.name, probe.version)`` pair the
        index record needs is passed explicitly to :meth:`put`, so there is
        no ordering coupling between ``key_for`` and ``put``.
        """
        return _key_for_module(probe, snapshot, task)

    # ------------------------------------------------------------------ get

    def get(self, key: str) -> ProbeOutput | None:
        """Return the cached output for ``key`` or ``None`` on any miss path.

        Miss paths (all four emit a structured event; coordinator re-runs):

        - cold-start: ``index.jsonl`` does not exist → ``cache.miss``
        - key not in index → ``cache.miss``
        - latest record older than ``ttl_hours`` → ``cache.stale``
        - blob unreadable as JSON / SHA-256 mismatch / blob missing
          → ``cache.blob.invalid``
        """
        _ensure_dir(self._cache_dir)
        index = self._index_path
        if not index.exists():
            _log.info("cache.miss", key=key)
            return None

        record = self.get_index_record(key)
        if record is None:
            _log.info("cache.miss", key=key)
            return None

        age_s = time.time() - record["created_at_unix_s"]
        if age_s > self._ttl_hours * 3600:
            _log.info("cache.stale", key=key, age_s=age_s)
            return None

        blob_blake3 = record["blob_blake3"].removeprefix("blake3:")
        blob_file = self._blob_path(blob_blake3)
        if not blob_file.exists():
            _log.info("cache.blob.invalid", key=key, reason="missing")
            return None

        blob_bytes = blob_file.read_bytes()
        recomputed_sha = identity_hash_bytes(blob_bytes)
        if recomputed_sha != record["blob_sha256"]:
            _log.info("cache.blob.invalid", key=key, reason="sha256_mismatch")
            return None

        try:
            return _deserialize_output(blob_bytes)
        except (json.JSONDecodeError, KeyError, ValueError):
            _log.info("cache.blob.invalid", key=key, reason="json_decode")
            return None

    def get_index_record(self, key: str) -> dict[str, Any] | None:
        """Return the LAST index record whose ``"key"`` equals ``key``.

        Served from an in-memory ``{key: latest_record}`` map that is rebuilt
        only when ``index.jsonl``'s size changes — the file is append-only so
        a changed size means a record was added (by this process or a
        concurrent one). Last-write-wins is preserved: the rebuild replays
        every line in order, so a later record for the same key overwrites an
        earlier one. A mutant returning the first match regresses.

        Public for the S3-06 audit verifier — ``codegenie.audit.verify_runs``
        resolves a ``cache_key`` to its on-disk blob path without going
        through :meth:`get` (which would re-deserialize and mask byte-level
        tampering). Returns ``None`` if no record matches or the index file
        does not exist.
        """
        try:
            current_size = self._index_path.stat().st_size
        except FileNotFoundError:
            return None
        if self._index_cache is None or current_size != self._index_size:
            self._index_cache = self._load_index()
            self._index_size = current_size
        return self._index_cache.get(key)

    def _load_index(self) -> dict[str, dict[str, Any]]:
        """Parse ``index.jsonl`` into ``{key: latest_record}`` (last-write-wins).

        A torn partial line (edge-case 12) fails ``json.loads`` and is
        skipped; the rest of the index stays valid.
        """
        out: dict[str, dict[str, Any]] = {}
        try:
            fh = self._index_path.open("r", encoding="utf-8")
        except FileNotFoundError:
            return out
        with fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                rec_key = record.get("key")
                if isinstance(rec_key, str):
                    out[rec_key] = record
        return out

    # ------------------------------------------------------------------ put

    def put(
        self,
        key: str,
        output: ProbeOutput,
        *,
        probe_name: str,
        probe_version: str,
    ) -> None:
        """Persist ``output`` under ``key`` — atomic blob + appended index line.

        Sequence: serialize → record-size guard → write blob (atomic) →
        append index line → re-assert ``0700``/``0600`` modes on the blob
        and index just written. The blob write is atomic so a crash between
        the two writes leaves no orphan record pointing at a missing blob
        (the next ``get`` would surface ``cache.blob.invalid`` and the
        coordinator would re-run anyway). ``probe_name`` / ``probe_version``
        stamp the index record — passed explicitly so ``put`` carries no
        hidden dependency on a prior ``key_for`` call. Raises
        :class:`CacheError` only for the record-size precondition violation;
        every other failure surface is the OS layer (filesystem full /
        permissions) and propagates.
        """
        blob_bytes = serialize_output(output)
        blob_blake3 = content_hash_bytes(blob_bytes)
        blob_sha256 = identity_hash_bytes(blob_bytes)

        record = {
            "key": key,
            "blob_blake3": blob_blake3,
            "blob_sha256": blob_sha256,
            "created_at_unix_s": int(time.time()),
            "probe_name": probe_name,
            "probe_version": probe_version,
        }
        line = json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
        line_bytes = line.encode("utf-8")
        if len(line_bytes) > _MAX_RECORD_BYTES:
            raise CacheError(
                f"index record for key {key!r} is {len(line_bytes)} bytes; "
                f"exceeds PIPE_BUF={_MAX_RECORD_BYTES} (concurrent O_APPEND atomicity "
                "would be broken). Shrink the probe output or split the artifact."
            )

        blob_hex = blob_blake3.removeprefix("blake3:")
        blob_file = self._blob_path(blob_hex)
        _ensure_dir(blob_file.parent.parent)  # cache_dir/blobs
        _ensure_dir(blob_file.parent)  # cache_dir/blobs/<shard>
        _atomic_write_bytes(blob_file, blob_bytes)

        index = self._index_path
        # Ensure the file exists with the right mode BEFORE the append,
        # so the O_APPEND path doesn't inherit a 0644 default from umask.
        if not index.exists():
            os.close(os.open(index, os.O_CREAT | os.O_WRONLY, _FILE_MODE))
        fd = os.open(index, os.O_WRONLY | os.O_APPEND)
        try:
            os.write(fd, line_bytes)
        finally:
            os.close(fd)

        # Re-assert modes only on what this put wrote — the blob's parent
        # dirs are already chmod'd by ``_ensure_dir`` above, and the full
        # cache-tree re-walk ran once in ``__init__``.
        os.chmod(blob_file, _FILE_MODE)
        os.chmod(index, _FILE_MODE)

        # Keep the in-memory index view coherent with our own append so a
        # following get() needn't re-parse the file. A concurrent process's
        # append changes the file size, which get_index_record's size guard
        # catches independently.
        if self._index_cache is not None:
            self._index_cache[key] = record
            self._index_size = index.stat().st_size
