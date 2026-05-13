"""Tests for ``codegenie.cache.store.CacheStore`` — story S3-01.

Three tiers:

- **Tier 1** (round-trip, last-write-wins, index record schema, cold-start):
  the happy-path and load-bearing structural invariants.
- **Tier 2** (miss matrix — four independent paths, each one mutation-killer
  for the corresponding verification step): blob unreadable / SHA-256
  mismatch / blob missing / TTL stale. Each path collapses to ``None`` + the
  named structured log event (``cache.blob.invalid`` / ``cache.stale``).
- **Tier 3** (atomic write, ``0700``/``0600`` modes including ``index.jsonl``,
  record-size guard): the durability + permissions + concurrency
  invariants.

Synthetic probe + snapshot fixtures stay in this file so the test surface is
self-contained; the cache-keys tests in ``test_cache_invalidation_scope.py``
exercise the schema-path resolver against a monkeypatched ``_SCHEMA_DIR``.
"""

from __future__ import annotations

import importlib
import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest import mock

import pytest
import structlog

from codegenie.errors import CacheError
from codegenie.probes.base import ProbeOutput, RepoSnapshot, Task

# ---------------------------------------------------------------------------
# Synthetic probe + snapshot fixtures
# ---------------------------------------------------------------------------


@dataclass
class _SynthProbe:
    name: str = "synth"
    version: str = "1.0"
    declared_inputs: list[str] = field(default_factory=lambda: ["**/*.txt"])


def _make_snapshot(tmp_path: Path) -> RepoSnapshot:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "a.txt").write_bytes(b"alpha")
    return RepoSnapshot(root=root, git_commit=None, detected_languages={}, config={})


def _make_output(**overrides: Any) -> ProbeOutput:
    defaults: dict[str, Any] = {
        "schema_slice": {"v": 1, "lang": "python"},
        "raw_artifacts": [Path("raw") / "out.json"],
        "confidence": "high",
        "duration_ms": 42,
        "warnings": ["w1"],
        "errors": [],
    }
    defaults.update(overrides)
    return ProbeOutput(**defaults)  # type: ignore[arg-type]


def _store_with_key(
    tmp_path: Path,
    *,
    ttl_hours: int = 24,
    schema_slice: dict[str, Any] | None = None,
) -> tuple[Any, str, ProbeOutput]:
    """Build a fresh ``CacheStore``, register a synthetic probe, and return
    ``(store, key, output)`` ready for ``store.put(key, output)``."""
    from codegenie.cache.store import CacheStore

    cache_dir = tmp_path / "cache"
    store = CacheStore(cache_dir=cache_dir, ttl_hours=ttl_hours)
    snapshot = _make_snapshot(tmp_path)
    probe = _SynthProbe()
    key = store.key_for(probe, snapshot, Task(type="t", options={}))  # type: ignore[arg-type]
    output = _make_output(schema_slice=schema_slice or {"v": 1, "lang": "python"})
    return store, key, output


def _resolve_blob_path(store: Any, key: str) -> Path:
    """Walk the index and return the on-disk blob path for the latest record."""
    index = store._index_path  # noqa: SLF001 — test-only access
    last_line = [ln for ln in index.read_text().splitlines() if ln.strip()][-1]
    record = json.loads(last_line)
    blake3_hex = record["blob_blake3"].removeprefix("blake3:")
    return store._blob_path(blake3_hex)  # noqa: SLF001


# ---------------------------------------------------------------------------
# Tier 1 — round-trip, cold-start, last-write-wins, index-record schema
# ---------------------------------------------------------------------------


def test_put_then_get_returns_equivalent_output(tmp_path: Path) -> None:
    """AC: round-trip happy path. A ``put`` that silently no-ops fails here;
    a ``get`` that returns a partial reconstruction fails here."""
    store, key, output = _store_with_key(tmp_path)
    store.put(key, output)
    got = store.get(key)
    assert got is not None
    assert got.schema_slice == output.schema_slice
    assert got.confidence == output.confidence
    assert got.duration_ms == output.duration_ms
    assert got.warnings == output.warnings
    assert got.errors == output.errors
    assert [str(p) for p in got.raw_artifacts] == [str(p) for p in output.raw_artifacts]


def test_get_none_on_cold_start_no_index(tmp_path: Path) -> None:
    """AC: cold-start. Empty ``cache_dir`` → ``None`` + ``cache.miss``."""
    from codegenie.cache.store import CacheStore

    fresh = tmp_path / "fresh"
    store = CacheStore(cache_dir=fresh, ttl_hours=24)
    with structlog.testing.capture_logs() as captured:
        assert store.get("sha256:" + "0" * 64) is None
    assert any(r.get("event") == "cache.miss" for r in captured)
    assert fresh.stat().st_mode & 0o777 == 0o700


def test_last_write_wins_on_multi_record(tmp_path: Path) -> None:
    """AC: a ``get`` that returns the first matching index line (instead of the
    last) regresses here. Two ``put`` calls land two records; the second must win."""
    store, key, out1 = _store_with_key(tmp_path, schema_slice={"v": 1})
    store.put(key, out1)
    out2 = _make_output(schema_slice={"v": 2})
    store.put(key, out2)
    got = store.get(key)
    assert got is not None and got.schema_slice == {"v": 2}


def test_index_record_schema_pin(tmp_path: Path) -> None:
    """AC: every ``index.jsonl`` line is a JSON object with the named fields,
    ``sort_keys`` + compact separators (no whitespace)."""
    store, key, output = _store_with_key(tmp_path)
    store.put(key, output)
    line = (tmp_path / "cache" / "index.jsonl").read_text().splitlines()[0]
    record = json.loads(line)
    assert set(record) >= {
        "key",
        "blob_blake3",
        "blob_sha256",
        "created_at_unix_s",
        "probe_name",
        "probe_version",
    }
    assert isinstance(record["created_at_unix_s"], int)
    assert record["blob_sha256"].startswith("sha256:")
    assert record["blob_blake3"].startswith("blake3:")
    assert record["probe_name"] == "synth"
    assert record["probe_version"] == "1.0"
    # serialization shape: compact separators, sorted keys
    assert ", " not in line and ": " not in line
    # sorted keys: the JSON object's keys appear in alphabetical order
    keys_in_order = re.findall(r'"([a-z_0-9]+)":', line)
    assert keys_in_order == sorted(keys_in_order)


# ---------------------------------------------------------------------------
# Tier 2 — miss-matrix (four independent paths from AC-5)
# ---------------------------------------------------------------------------


def test_get_none_on_corrupt_blob_zero_bytes(tmp_path: Path) -> None:
    """AC 5a: blob bytes unreadable as JSON (truncated to 0 bytes).

    Mutation-killer: a ``get`` that doesn't validate JSON-decodability
    raises here instead of returning ``None``."""
    store, key, output = _store_with_key(tmp_path)
    store.put(key, output)
    blob = _resolve_blob_path(store, key)
    os.chmod(blob, 0o600)  # ensure writable; cache may have applied 0400
    blob.write_bytes(b"")
    with structlog.testing.capture_logs() as captured:
        assert store.get(key) is None
    assert any(r.get("event") == "cache.blob.invalid" for r in captured)


def test_get_none_on_blob_sha256_mismatch(tmp_path: Path) -> None:
    """AC 5b: blob is valid JSON but its SHA-256 ≠ the index record's
    ``blob_sha256``. Mutation-killer: a ``CacheStore`` that skips the SHA-256
    verification step returns the tampered output instead of ``None``."""
    store, key, output = _store_with_key(tmp_path)
    store.put(key, output)
    blob = _resolve_blob_path(store, key)
    os.chmod(blob, 0o600)
    blob.write_text(
        '{"schema_slice":{"tampered":true},"confidence":"low",'
        '"duration_ms":0,"warnings":[],"errors":[],"raw_artifacts":[]}'
    )
    with structlog.testing.capture_logs() as captured:
        assert store.get(key) is None
    assert any(r.get("event") == "cache.blob.invalid" for r in captured)


def test_get_none_on_missing_blob(tmp_path: Path) -> None:
    """AC 5c: orphan index record — blob file is gone but the record remains."""
    store, key, output = _store_with_key(tmp_path)
    store.put(key, output)
    blob = _resolve_blob_path(store, key)
    os.chmod(blob, 0o600)
    blob.unlink()
    with structlog.testing.capture_logs() as captured:
        assert store.get(key) is None
    assert any(r.get("event") == "cache.blob.invalid" for r in captured)


def test_get_none_on_ttl_stale_entry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC 5d: index record older than ``ttl_hours``.

    Mutation-killer: a ``CacheStore`` that ignores ``ttl_hours`` returns the
    value here instead of ``None``."""
    store, key, output = _store_with_key(tmp_path, ttl_hours=1)
    store.put(key, output)
    frozen = time.time() + 2 * 3600  # 2 hours ahead — past the 1-hour TTL
    monkeypatch.setattr("codegenie.cache.store.time.time", lambda: frozen)
    with structlog.testing.capture_logs() as captured:
        assert store.get(key) is None
    assert any(r.get("event") == "cache.stale" for r in captured)


def test_get_none_when_key_not_in_index(tmp_path: Path) -> None:
    """AC: a key the store has never seen returns ``None`` + ``cache.miss``."""
    store, _key, output = _store_with_key(tmp_path)
    # put a different key first so the index file exists
    other_key = "sha256:" + "1" * 64
    store._key_meta[other_key] = ("synth", "1.0")  # noqa: SLF001
    store.put(other_key, output)
    with structlog.testing.capture_logs() as captured:
        assert store.get("sha256:" + "2" * 64) is None
    assert any(r.get("event") == "cache.miss" for r in captured)


# ---------------------------------------------------------------------------
# Tier 3 — atomic write, permissions, record-size guard
# ---------------------------------------------------------------------------


def test_atomic_write_no_partial_visible(tmp_path: Path) -> None:
    """AC: atomic write. If ``os.replace`` raises mid-write, no destination
    file exists at the final path; a subsequent ``get`` returns ``None``
    (miss), never a partial blob."""
    store, key, output = _store_with_key(tmp_path)
    with mock.patch(
        "codegenie.cache.store.os.replace",
        side_effect=OSError("simulated mid-write crash"),
    ):
        with pytest.raises(OSError, match="simulated mid-write crash"):
            store.put(key, output)
    # final blob path was never made visible by os.replace
    shard_dir = tmp_path / "cache" / "blobs"
    final_blobs = list(shard_dir.rglob("*.json")) if shard_dir.exists() else []
    assert final_blobs == []
    assert store.get(key) is None


def test_post_write_modes_pin_dirs_blobs_and_index(tmp_path: Path) -> None:
    """AC: every dir ``0700``, every blob file ``0600``, ``index.jsonl``
    ``0600`` (asserted separately so a "forgot to chmod index.jsonl" mutant
    fails distinctly from the blob-mode assertion)."""
    store, key, output = _store_with_key(tmp_path)
    store.put(key, output)
    cache_root = tmp_path / "cache"
    assert cache_root.stat().st_mode & 0o777 == 0o700
    index = cache_root / "index.jsonl"
    assert index.stat().st_mode & 0o777 == 0o600
    for p in cache_root.rglob("*"):
        if p.is_dir():
            assert p.stat().st_mode & 0o777 == 0o700, f"{p} dir mode"
        else:
            assert p.stat().st_mode & 0o777 == 0o600, f"{p} file mode"


def test_record_size_guard_refuses_oversize(tmp_path: Path) -> None:
    """AC-12: a record whose serialized length exceeds ``PIPE_BUF=4096`` B is
    refused (:class:`CacheError`); ``index.jsonl`` is unchanged afterwards.

    The index record schema (``probe_name``, ``probe_version``, two hashes,
    a timestamp) makes the probe-version field the only input the test
    controls that lands directly in the serialized line — a pathological
    long version forces the record over 4096 B without bloating the blob.
    The guard fires whether the input is version, name, or a future
    additive field (Edge case 12, ``phase-arch-design.md``)."""
    from codegenie.cache.store import CacheStore

    cache_dir = tmp_path / "cache"
    store = CacheStore(cache_dir=cache_dir, ttl_hours=24)
    snapshot = _make_snapshot(tmp_path)
    huge_probe = _SynthProbe(name="synth", version="v" * 5000)
    key = store.key_for(huge_probe, snapshot, Task(type="t", options={}))  # type: ignore[arg-type]
    output = _make_output()
    index = cache_dir / "index.jsonl"
    before = index.read_bytes() if index.exists() else b""
    with pytest.raises(CacheError, match="exceeds PIPE_BUF"):
        store.put(key, output)
    after = index.read_bytes() if index.exists() else b""
    assert before == after


def test_serialized_blob_is_deterministic(tmp_path: Path) -> None:
    """AC: same content → same blob bytes (sort_keys + compact separators).
    A non-deterministic serializer would produce different BLAKE3 filenames
    on second run and silently bust the cache."""
    from codegenie.cache.store import _serialize_output

    o1 = _make_output(schema_slice={"b": 2, "a": 1})
    o2 = _make_output(schema_slice={"a": 1, "b": 2})  # same content, swapped insertion order
    assert _serialize_output(o1) == _serialize_output(o2)


def test_index_jsonl_records_separated_by_single_newline(tmp_path: Path) -> None:
    """Edge-case 12: each record is exactly one line ending in ``\\n`` —
    no trailing whitespace, no extra blank lines. ``O_APPEND`` atomicity
    requires the record to fit in one ``write(2)`` call."""
    store, key, output = _store_with_key(tmp_path)
    store.put(key, output)
    store.put(key, _make_output(schema_slice={"v": 99}))
    raw = (tmp_path / "cache" / "index.jsonl").read_bytes()
    lines = raw.split(b"\n")
    # two records + one trailing empty (from terminator)
    assert len(lines) == 3 and lines[-1] == b""
    for ln in lines[:-1]:
        # each record is valid JSON
        json.loads(ln)


# ---------------------------------------------------------------------------
# Import surface — the cache package re-exports the documented names
# ---------------------------------------------------------------------------


def test_cache_package_reexports() -> None:
    """The story files-to-touch row promises ``cache.__init__`` re-exports
    ``CacheStore`` and ``key_for`` so callers don't have to know the
    submodule layout."""
    cache_pkg = importlib.import_module("codegenie.cache")
    assert hasattr(cache_pkg, "CacheStore")
    assert hasattr(cache_pkg, "key_for")
    assert hasattr(cache_pkg, "envelope_schema_version")
    assert hasattr(cache_pkg, "per_probe_schema_version")
    assert hasattr(cache_pkg, "declared_inputs_for")
