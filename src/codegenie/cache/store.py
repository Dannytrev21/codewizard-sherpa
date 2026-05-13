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

**Permissions (ADR-0011).** Directories ``0700``, files ``0600``. After every
write, ``os.chmod`` is walked across the cache tree to defeat the CI
``actions/cache`` restore that flattens modes to umask defaults. Tests assert
post-``put`` state, not the transient post-restore window.

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
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from codegenie.cache.keys import _ProbeLike
from codegenie.cache.keys import key_for as _key_for_module
from codegenie.errors import CacheError
from codegenie.hashing import content_hash_bytes, identity_hash_bytes

if TYPE_CHECKING:
    from codegenie.probes.base import ProbeOutput, RepoSnapshot, Task


__all__ = ["CacheStore"]

_MAX_RECORD_BYTES = 4096  # PIPE_BUF on Linux/macOS; concurrent O_APPEND atomicity bound
_DIR_MODE = 0o700
_FILE_MODE = 0o600

_log = structlog.get_logger(__name__)


def _serialize_output(output: ProbeOutput) -> bytes:
    """Serialize a :class:`ProbeOutput` to deterministic JSON bytes.

    ``sort_keys=True`` + ``separators=(",", ":")`` makes the byte stream
    byte-identical for byte-identical content — required so the BLAKE3
    filename and the SHA-256 tamper-check are reproducible on second run.
    ``raw_artifacts`` is serialized as a list of stringified paths;
    deserialization restores them as :class:`pathlib.Path` instances.
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
    """Write ``data`` to ``target`` via ``<target>.tmp`` + fsync + os.replace."""
    tmp = target.with_suffix(target.suffix + ".tmp")
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
    bits as advisory).
    """
    os.chmod(root, _DIR_MODE)
    for current, dirs, files in os.walk(root):
        for d in dirs:
            os.chmod(Path(current) / d, _DIR_MODE)
        for f in files:
            os.chmod(Path(current) / f, _FILE_MODE)


class CacheStore:
    """Filesystem cache for :class:`ProbeOutput` values, keyed by SHA-256 identity.

    Construct with the cache root directory and a TTL in hours. The store
    is stateless across instances — every read/write touches the index and
    the blob tree directly; restarting the process loses nothing.
    """

    def __init__(self, cache_dir: Path, ttl_hours: int) -> None:
        self._cache_dir = cache_dir
        self._ttl_hours = ttl_hours
        # populated by ``key_for``; ``put`` reads ``(name, version)`` from
        # here when stamping the index record so the public signature stays
        # ``put(key, output)`` as the story sketches.
        self._key_meta: dict[str, tuple[str, str]] = {}
        _ensure_dir(self._cache_dir)

    # ------------------------------------------------------------------ paths

    @property
    def _index_path(self) -> Path:
        return self._cache_dir / "index.jsonl"

    def _blob_path(self, blake3_hex: str) -> Path:
        shard = blake3_hex[:2]
        return self._cache_dir / "blobs" / shard / f"{blake3_hex}.json"

    # ------------------------------------------------------------------ keys

    def key_for(self, probe: _ProbeLike, snapshot: RepoSnapshot, task: Task) -> str:
        """Delegate to :func:`codegenie.cache.keys.key_for` and stash metadata.

        ``put`` later reads the ``(probe.name, probe.version)`` tuple keyed
        by the returned hash to populate the index record. The coordinator
        always calls ``key_for`` before ``put``; tests follow the same
        sequence.
        """
        key = _key_for_module(probe, snapshot, task)
        self._key_meta[key] = (probe.name, probe.version)
        return key

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

        record = self._latest_record_for(key)
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

    def _latest_record_for(self, key: str) -> dict[str, Any] | None:
        """Linear scan; return the LAST record whose ``"key"`` equals ``key``.

        Last-write-wins is the story's contract (AC-11): two ``put`` calls
        with the same key result in two index records; ``get`` returns the
        most recent. A mutant returning the first match regresses.
        """
        latest: dict[str, Any] | None = None
        with self._index_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    # Edge-case 12: a partial line from a torn write. Skip
                    # and keep walking; the rest of the index stays valid.
                    continue
                if record.get("key") == key:
                    latest = record
        return latest

    # ------------------------------------------------------------------ put

    def put(self, key: str, output: ProbeOutput) -> None:
        """Persist ``output`` under ``key`` — atomic blob + appended index line.

        Sequence: serialize → record-size guard → write blob (atomic) →
        append index line → re-apply ``0700``/``0600`` modes across the
        cache tree. The blob write is atomic so a crash between the two
        writes leaves no orphan record pointing at a missing blob (the next
        ``get`` would surface ``cache.blob.invalid`` and the coordinator
        would re-run anyway). Raises :class:`CacheError` only for the
        record-size precondition violation; every other failure surface is
        the OS layer (filesystem full / permissions) and propagates.
        """
        try:
            probe_name, probe_version = self._key_meta[key]
        except KeyError as exc:
            raise CacheError(
                f"CacheStore.put({key!r}, ...) called before key_for(...) populated "
                "probe metadata. The coordinator must compute the key via "
                "CacheStore.key_for(probe, snapshot, task) before storing the output."
            ) from exc

        blob_bytes = _serialize_output(output)
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

        _reapply_modes(self._cache_dir)
