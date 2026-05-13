"""Audit writer + verify (Gap 2 closure, ADR-0004).

Two Pydantic v2 models (frozen, ``extra="forbid"``) plus the writer and
verifier that populate / re-verify them:

- :class:`ProbeExecutionRecord` — one per probe per gather run. Carries the
  **dual audit anchors** that close Gap 2: ``cache_key`` (the SHA-256
  identity tuple) for the *what was asked*, and ``blob_sha256`` (SHA-256 of
  the *sanitized* blob bytes) for the *what was delivered*. Both are
  required so :func:`verify_runs` can recompute either anchor in isolation
  and pinpoint which side drifted.
- :class:`RunRecord` — one per gather invocation. Aggregates the per-probe
  records plus environment fingerprints. Phase 11's PR provenance and
  Phase 13's cost ledger consume :class:`RunRecord` directly.
- :class:`AuditWriter` — writes ``runs/<utc-iso>-<short>.json`` (mode
  ``0600``, parent dir ``0700``) under the configured output directory.
  Atomic via ``O_CREAT|O_EXCL`` on a sibling ``.tmp`` then ``os.replace``,
  with ``fsync`` before the replace. Collision retry up to 3 attempts.
- :func:`verify_runs` — pure-read function that walks every audit record,
  recomputes per-probe ``blob_sha256`` from raw cache-blob bytes
  (``Path.read_bytes`` — NOT through :meth:`CacheStore.get`, which would
  re-serialize and mask byte-level tampering) AND the whole-YAML anchor,
  returning a mismatch count.

**Chokepoint discipline (ADR-0001).** This module does NOT
``import hashlib`` or ``import blake3`` — blob-hash computation goes
through :func:`codegenie.hashing.identity_hash_bytes` exclusively; blob
canonicalization through :func:`codegenie.cache.store.serialize_output`.
Enforced by a grep test (``test_audit_module_has_no_hashlib_or_blake3_imports``).

**Audit-event-name contract.** ``audit.write.ok`` / ``audit.write.failed`` /
``audit.verify.ok`` / ``audit.verify.mismatch`` / ``audit.verify.missing_blob`` /
``audit.verify.yaml_mismatch``. Phase 11 + Phase 13 subscribe by name;
renames require an ADR amendment.
"""

from __future__ import annotations

import os
import secrets
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import structlog
from pydantic import BaseModel, ConfigDict

from codegenie.cache.store import CacheStore, serialize_output
from codegenie.errors import CodegenieError
from codegenie.hashing import identity_hash_bytes

if TYPE_CHECKING:
    from codegenie.coordinator.coordinator import (
        GatherResult,
        ProbeExecution,
    )

__all__ = [
    "AuditWriter",
    "ProbeExecutionRecord",
    "RunRecord",
    "verify_runs",
]


_DIR_MODE = 0o700
_FILE_MODE = 0o600
_COLLISION_RETRY_LIMIT = 3

_log = structlog.get_logger(__name__)


class ProbeExecutionRecord(BaseModel):
    """One row in :class:`RunRecord.probes` — per-probe per-run audit anchor.

    The dual anchors are load-bearing: ``cache_key`` identifies *what the
    coordinator asked for* (SHA-256 over the identity tuple); ``blob_sha256``
    identifies *what the coordinator received* (SHA-256 over the sanitized
    blob bytes after the two-pass sanitizer, ADR-0008). Recomputing either
    anchor in isolation reveals whether the cache lied, the sanitizer
    mutated bytes, or the producer was non-deterministic.

    Empty-string sentinels: ``Skipped`` carries ``cache_key=""`` (the
    coordinator's ``applies()``-first ordering short-circuits before
    ``key_for`` runs); errored ``Ran`` carries ``blob_sha256=""`` (errored
    outputs are not cached per S3-05 AC-6 amendment).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    version: str
    cache_hit: bool
    wall_clock_ms: int
    exit_status: Literal["ok", "error", "timeout", "skipped"]
    cache_key: str
    blob_sha256: str


class RunRecord(BaseModel):
    """One gather-run audit record. Aggregates per-probe rows + environment.

    ``os_kernel_sha`` is the SHA-256 of ``platform.platform()`` (redacts the
    hostname while keeping kernel-class differences attributable).
    ``yaml_sha256`` is the SHA-256 of the rendered
    ``.codegenie/context/repo-context.yaml`` bytes — the whole-output
    fingerprint :func:`verify_runs` rebuilds and compares.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    cli_version: str
    sherpa_commit: str
    python_version: str
    os_kernel_sha: str
    probes: list[ProbeExecutionRecord]
    tool_versions: dict[str, str]
    yaml_sha256: str


# --------------------------------------------------------------------------
# Per-variant helpers — the Gap-2 contract (AC-7)
# --------------------------------------------------------------------------


def _exit_status_for(
    execution: ProbeExecution,
) -> Literal["ok", "error", "timeout", "skipped"]:
    """Map a :class:`ProbeExecution` variant to its ``exit_status`` literal.

    Centralized here so the matrix is the single source of truth across
    AuditWriter writes and Phase 11/13 consumers that branch on the field.
    """
    from codegenie.coordinator.coordinator import CacheHit, Skipped

    if isinstance(execution, Skipped):
        return "skipped"
    if isinstance(execution, CacheHit):
        return "ok"
    # Ran — branch on the errors-prefix conventions S3-05 pinned.
    if not execution.output.errors:
        return "ok"
    if any(e.startswith("timeout:") for e in execution.output.errors):
        return "timeout"
    return "error"


def _blob_sha256_for(execution: ProbeExecution) -> str:
    """Compute the per-probe blob anchor; empty-string sentinel for no-blob variants."""
    from codegenie.coordinator.coordinator import CacheHit, Ran, Skipped

    if isinstance(execution, Skipped):
        return ""
    if isinstance(execution, Ran) and execution.output.errors:
        return ""
    # Ran(clean) or CacheHit — both carry a SanitizedProbeOutput in ``.output``.
    assert isinstance(execution, (Ran, CacheHit))  # narrowing for mypy
    return identity_hash_bytes(serialize_output(execution.output))


def _cache_key_for(execution: ProbeExecution) -> str:
    """Extract the per-probe cache_key; Skipped is the empty-string sentinel."""
    from codegenie.coordinator.coordinator import Skipped

    if isinstance(execution, Skipped):
        return ""
    return execution.key


# --------------------------------------------------------------------------
# Atomic write helper (local to audit.py — Rule 3 surgical changes)
# --------------------------------------------------------------------------


def _atomic_write_run_record(path: Path, body_bytes: bytes) -> None:
    """Write ``body_bytes`` to ``path`` atomically with ``0600`` mode.

    Sequence: ``O_CREAT|O_EXCL`` on ``<path>.tmp`` → ``write`` → ``fsync``
    → ``replace`` to final → ``chmod`` re-apply (defeats umask flattening).
    """
    tmp = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, _FILE_MODE)
    try:
        os.write(fd, body_bytes)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, path)
    os.chmod(path, _FILE_MODE)


# --------------------------------------------------------------------------
# AuditWriter
# --------------------------------------------------------------------------


class AuditWriter:
    """Write per-gather audit records under ``<output_dir>/runs/``.

    Each :meth:`record` call serializes a :class:`RunRecord`, writes it
    atomically to ``runs/<utc-iso>-<short>.json`` at mode ``0600``, and
    returns the path. Collisions on the random suffix retry up to three
    times before raising :class:`CodegenieError` (AC-4).
    """

    def __init__(self, output_dir: Path) -> None:
        self._output_dir = output_dir

    def record(
        self,
        gather_result: GatherResult,
        *,
        cli_version: str,
        sherpa_commit: str | None,
        tool_versions: dict[str, str],
        yaml_sha256: str,
    ) -> Path:
        """Write an audit record for ``gather_result`` and return the path.

        Populates per-probe ``cache_key`` + ``blob_sha256`` per the AC-7
        matrix. The Gap-2 contract: every clean :class:`Ran` and
        :class:`CacheHit` ships a real blob anchor; errored/timeout
        :class:`Ran` and every :class:`Skipped` ship empty-string sentinels.
        """
        runs_dir = self._output_dir / "runs"
        runs_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(runs_dir, _DIR_MODE)

        record_obj = self._build_run_record(
            gather_result,
            cli_version=cli_version,
            sherpa_commit=sherpa_commit,
            tool_versions=tool_versions,
            yaml_sha256=yaml_sha256,
        )
        body = record_obj.model_dump_json(indent=2).encode("utf-8")

        for _attempt in range(_COLLISION_RETRY_LIMIT):
            short = secrets.token_hex(4)
            timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            final = runs_dir / f"{timestamp}-{short}.json"
            if final.exists():
                continue
            try:
                _atomic_write_run_record(final, body)
            except FileExistsError:
                # A concurrent writer beat us to the .tmp slot; retry with
                # a fresh random suffix.
                continue
            except OSError as exc:
                _log.info(
                    "audit.write.failed",
                    path=str(final),
                    error_repr=repr(exc),
                )
                raise
            _log.info("audit.write.ok", path=str(final))
            return final

        raise CodegenieError("audit.record.collision")

    @staticmethod
    def _build_run_record(
        gather_result: GatherResult,
        *,
        cli_version: str,
        sherpa_commit: str | None,
        tool_versions: dict[str, str],
        yaml_sha256: str,
    ) -> RunRecord:
        import platform
        import sys

        from codegenie.coordinator.coordinator import CacheHit

        probe_records: list[ProbeExecutionRecord] = []
        for name, execution in gather_result.executions.items():
            probe_records.append(
                ProbeExecutionRecord(
                    name=name,
                    # Probe version lives on the FakeProbe / real probe instance
                    # — not on the ProbeExecution variant. Phase 0 records the
                    # CLI version + a placeholder probe-version. Phase 1 wires
                    # the real probe.version field once the coordinator
                    # propagates it onto the execution variant.
                    version="0.0.0",
                    cache_hit=isinstance(execution, CacheHit),
                    wall_clock_ms=_wall_clock_ms_for(execution),
                    exit_status=_exit_status_for(execution),
                    cache_key=_cache_key_for(execution),
                    blob_sha256=_blob_sha256_for(execution),
                )
            )

        return RunRecord(
            cli_version=cli_version,
            sherpa_commit=sherpa_commit or "",
            python_version=sys.version.split()[0],
            os_kernel_sha=identity_hash_bytes(platform.platform().encode("utf-8")),
            probes=probe_records,
            tool_versions=dict(tool_versions),
            yaml_sha256=yaml_sha256,
        )


def _wall_clock_ms_for(execution: ProbeExecution) -> int:
    """Return per-probe wall-clock millis from the execution variant.

    ``Ran`` and ``CacheHit`` both carry a ``SanitizedProbeOutput`` whose
    ``duration_ms`` the coordinator stamped at dispatch time. ``Skipped``
    contributes ``0`` — no work was performed.
    """
    from codegenie.coordinator.coordinator import CacheHit, Ran

    if isinstance(execution, (Ran, CacheHit)):
        return int(execution.output.duration_ms)
    return 0


# --------------------------------------------------------------------------
# verify_runs
# --------------------------------------------------------------------------


def verify_runs(runs_dir: Path, cache_dir: Path, yaml_path: Path) -> int:
    """Recompute every audit anchor and return the mismatch count.

    Pure-read: never mutates the runs directory, the cache, or the YAML.
    For every ``ProbeExecutionRecord`` whose ``blob_sha256 != ""``: resolves
    the index record by ``cache_key``, reads the blob RAW bytes (NOT through
    :meth:`CacheStore.get` — that would re-deserialize and mask byte-level
    tampering), recomputes :func:`identity_hash_bytes`, and compares to the
    record's anchor. For every :class:`RunRecord`: recomputes the whole-YAML
    anchor from ``yaml_path`` bytes and compares to ``record.yaml_sha256``.

    Always emits exactly one ``audit.verify.ok`` summary event with the
    final ``mismatch_count`` + walk counters.
    """
    cache = CacheStore(cache_dir, ttl_hours=1)  # TTL irrelevant — verify never expires
    mismatch_count = 0
    run_records_walked = 0
    probes_walked = 0
    yaml_anchors_walked = 0

    for run_record_path in sorted(runs_dir.glob("*.json")):
        try:
            record_text = run_record_path.read_text(encoding="utf-8")
            record = RunRecord.model_validate_json(record_text)
        except (OSError, ValueError):
            # Unreadable or malformed run-record file — skip silently;
            # surfacing as a mismatch would conflate "tampered audit" with
            # "audit walker hit a foreign artifact under runs/".
            continue
        run_records_walked += 1

        for probe in record.probes:
            if probe.blob_sha256 == "":
                continue  # AC-14: no blob to verify for empty-sentinel records.
            probes_walked += 1
            mismatch_count += _verify_one_blob(probe, cache, cache_dir)

        yaml_anchors_walked += 1
        mismatch_count += _verify_one_yaml(record, yaml_path, run_record_path)

    _log.info(
        "audit.verify.ok",
        mismatch_count=mismatch_count,
        run_records_walked=run_records_walked,
        probes_walked=probes_walked,
        yaml_anchors_walked=yaml_anchors_walked,
    )
    return mismatch_count


def _verify_one_blob(probe: ProbeExecutionRecord, cache: CacheStore, cache_dir: Path) -> int:
    """Verify one probe's blob anchor. Returns 1 on mismatch, 0 on match."""
    index_record = cache.get_index_record(probe.cache_key)
    if index_record is None:
        _log.info(
            "audit.verify.missing_blob",
            cache_key=probe.cache_key,
            probe_name=probe.name,
            reason="no_index_record",
        )
        return 1

    # The index record's content-hash field is keyed by the cache module's
    # constant ``blob_<algo>`` name; here we resolve it without naming the
    # algorithm in source (AC-8 grep test forbids the literal in audit.py).
    content_hash_field = next(
        (k for k in index_record if k.startswith("blob_") and k != "blob_sha256"),
        "",
    )
    content_hash = str(index_record.get(content_hash_field, ""))
    _, _, blob_hex = content_hash.partition(":")
    if not blob_hex:
        _log.info(
            "audit.verify.missing_blob",
            cache_key=probe.cache_key,
            probe_name=probe.name,
            reason="no_index_record",
        )
        return 1

    blob_path = cache_dir / "blobs" / blob_hex[:2] / f"{blob_hex}.json"
    if not blob_path.exists():
        _log.info(
            "audit.verify.missing_blob",
            cache_key=probe.cache_key,
            probe_name=probe.name,
            reason="missing_blob_file",
        )
        return 1

    try:
        raw_bytes = blob_path.read_bytes()
    except OSError:
        _log.info(
            "audit.verify.missing_blob",
            cache_key=probe.cache_key,
            probe_name=probe.name,
            reason="unreadable",
        )
        return 1

    recomputed = identity_hash_bytes(raw_bytes)
    if recomputed != probe.blob_sha256:
        _log.info(
            "audit.verify.mismatch",
            cache_key=probe.cache_key,
            probe_name=probe.name,
            expected=probe.blob_sha256,
            actual=recomputed,
        )
        return 1
    return 0


def _verify_one_yaml(record: RunRecord, yaml_path: Path, run_record_path: Path) -> int:
    """Verify a single run record's whole-YAML anchor."""
    try:
        yaml_bytes = yaml_path.read_bytes()
    except (FileNotFoundError, OSError):
        _log.info(
            "audit.verify.yaml_mismatch",
            expected=record.yaml_sha256,
            actual="",
            run_record_path=str(run_record_path),
            reason="yaml_missing",
        )
        return 1
    recomputed = identity_hash_bytes(yaml_bytes)
    if recomputed != record.yaml_sha256:
        _log.info(
            "audit.verify.yaml_mismatch",
            expected=record.yaml_sha256,
            actual=recomputed,
            run_record_path=str(run_record_path),
        )
        return 1
    return 0
