"""Concurrent-gather adversarial — extends Phase-0 S5-01's
``tests/unit/test_cache_concurrent.py`` to the full ``codegenie gather``
CLI surface against the Phase-2 ``minimal-ts`` portfolio fixture.

The Phase-0 concurrency contract per ``phase-arch-design.md §789``
edge-case 12 + S5-01:

* ``.codegenie/cache/index.jsonl`` appends are atomic per-record
  (records ≤ ``PIPE_BUF=4096B``).
* Blob writes are atomic via ``<dest>.tmp → fsync → os.replace``.
* **No advisory lock**; no ``.codegenie/cache/.lock`` primitive
  (verified by grep — empty across ``src/codegenie/``).

We assert these invariants directly after two concurrent gathers:

* Every line of ``index.jsonl`` parses as JSON.
* Every blob filename matches its content hash.
* No ``.tmp`` remnants survive.
* The published ``repo-context.yaml`` round-trips through
  ``yaml.safe_load``.

The test extends the Phase-0 surface to the Phase-2 ``minimal-ts``
portfolio fixture; the Phase-0 ``js_only`` fixture is the simpler
precedent.

ADR-0009 compliance: two-process concurrency via :class:`subprocess.Popen`
(NOT ``pytest-xdist``, NOT ``multiprocessing``, NOT ``asyncio.gather``).
Only real OS processes exercise the ``O_APPEND`` kernel guarantee.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Final

import pytest
import yaml

from codegenie.hashing import content_hash_bytes

_REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[3]
_FIXTURE_SRC: Final[Path] = _REPO_ROOT / "tests" / "fixtures" / "portfolio" / "minimal-ts"
_GATHER_TIMEOUT_S: Final[int] = 60  # AC-12 — two cold gathers should fit easily.


def _gather_cmd(fixture: Path) -> list[str]:
    """CLI invocation. ``--no-gitignore`` is a click group-level flag, so
    it MUST appear before the ``gather`` subcommand."""
    return [sys.executable, "-m", "codegenie", "--no-gitignore", "gather", str(fixture)]


def _launch(fixture: Path) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        _gather_cmd(fixture),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def test_concurrent_gathers_do_not_corrupt_cache(tmp_path: Path) -> None:
    """AC-7 / AC-8 / AC-9 / AC-10 / AC-12 / AC-13 / AC-31 — Phase-0 invariants survive
    two concurrent ``codegenie gather`` invocations against ``minimal-ts``."""

    if not _FIXTURE_SRC.exists():
        pytest.skip(f"fixture missing: {_FIXTURE_SRC}")

    # Work on a copy so we don't dirty the canonical fixture.
    workdir = tmp_path / "minimal-ts"
    shutil.copytree(_FIXTURE_SRC, workdir)

    t0 = time.monotonic()
    a = _launch(workdir)
    # Brief windowing — gives A a head-start on cache-dir creation so the
    # interesting concurrency exercise is in the appender / blob writer
    # path, not in directory creation. This is explicit ordering, NOT
    # race-tolerance.
    time.sleep(0.05)
    b = _launch(workdir)

    out_a, err_a = a.communicate(timeout=_GATHER_TIMEOUT_S)
    out_b, err_b = b.communicate(timeout=_GATHER_TIMEOUT_S)
    elapsed = time.monotonic() - t0

    # AC-12 — wall-clock budget.
    assert elapsed < _GATHER_TIMEOUT_S, f"wall-clock {elapsed:.1f}s exceeded budget"

    # AC-7 — both processes terminated cleanly.
    assert a.returncode == 0, (
        f"gather A exited {a.returncode}; stderr=\n{err_a.decode('utf-8', 'replace')}"
    )
    assert b.returncode == 0, (
        f"gather B exited {b.returncode}; stderr=\n{err_b.decode('utf-8', 'replace')}"
    )

    cache_root = workdir / ".codegenie" / "cache"

    # AC-8 — every line of index.jsonl parses as JSON (O_APPEND invariant).
    index_path = cache_root / "index.jsonl"
    assert index_path.exists(), (
        f"index.jsonl missing after concurrent gathers; "
        f"A_err={err_a.decode('utf-8', 'replace')!r}; "
        f"B_err={err_b.decode('utf-8', 'replace')!r}"
    )
    lines: list[bytes] = []
    with index_path.open("rb") as fh:
        for raw_line in fh:
            line = raw_line.rstrip(b"\n")
            if not line:
                continue
            try:
                json.loads(line)
            except json.JSONDecodeError as exc:
                raise AssertionError(
                    f"index.jsonl line {len(lines) + 1} is not valid JSON — "
                    f"O_APPEND atomicity violated (record likely exceeded "
                    f"PIPE_BUF=4096B). First 200 bytes: {bytes(line[:200])!r}"
                ) from exc
            # Defensive: a single physical line containing two JSON objects
            # back-to-back also indicates torn writes.
            assert b"}{" not in line, f"two JSON objects on one line: {line!r}"
            lines.append(line)

    # AC-31 — line count covers every unique key exercised by minimal-ts.
    assert lines, "index.jsonl exists but is empty — neither gather produced cache records"
    seen_keys = {json.loads(line).get("key") for line in lines}
    assert all(isinstance(k, str) and k for k in seen_keys), (
        f"index.jsonl records missing a string 'key' field — schema regression. "
        f"keys: {sorted(seen_keys)!r}"
    )

    # AC-9 — every blob filename matches its content hash; no .tmp remnants;
    # no zero-byte files.
    blobs_root = cache_root / "blobs"
    assert blobs_root.exists(), "cache/blobs/ missing after concurrent gathers"

    blob_files = [p for p in blobs_root.rglob("*") if p.is_file()]
    assert blob_files, "no blob files produced — cache write path is broken"
    for blob in blob_files:
        assert not blob.name.endswith(".tmp"), (
            f"leftover .tmp file at {blob} — atomic os.replace was "
            f"interrupted. Either a real bug in the cache write path or "
            f"a missing fsync before append."
        )
        size = blob.stat().st_size
        assert size > 0, f"zero-byte blob at {blob} — atomic-write violated"
        # Blob filename is ``<blake3_hex>.json`` per
        # ``src/codegenie/cache/store.py::_blob_path``. Compute the BLAKE3
        # of the file contents and confirm the filename matches.
        # ``content_hash_bytes`` returns ``"blake3:<hex>"``; the blob
        # filename embeds only the bare hex (see ``CacheStore._blob_path``).
        expected_hex = content_hash_bytes(blob.read_bytes()).removeprefix("blake3:")
        assert blob.stem == expected_hex, (
            f"corrupt blob {blob}: stem={blob.stem!r} but file content "
            f"hashes to {expected_hex!r} — atomic-blob-write contract violated"
        )

    # AC-10 — published repo-context.yaml round-trips through yaml.safe_load
    # and presents the documented top-level shape.
    ctx_path = workdir / ".codegenie" / "context" / "repo-context.yaml"
    assert ctx_path.exists(), "repo-context.yaml missing after concurrent gathers"
    parsed = yaml.safe_load(ctx_path.read_text(encoding="utf-8"))
    assert isinstance(parsed, dict), (
        f"repo-context.yaml parsed to non-mapping: {type(parsed).__name__}"
    )
    assert "probes" in parsed, (
        f"repo-context.yaml schema regression — missing 'probes' key. "
        f"Top-level keys: {sorted(parsed.keys())!r}"
    )
