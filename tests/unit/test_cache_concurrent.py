"""S5-01 — edge case #12 (phase-arch-design.md §789): two-process concurrent
``codegenie gather`` against the same ``.codegenie/cache/index.jsonl``.

This test is process-level, not asyncio-task-level. Edge case #12's invariant
("``O_APPEND`` atomic for records ≤ ``PIPE_BUF=4096B``; JSONL parses
line-by-line") is a *kernel* guarantee that requires real concurrent
processes/threads — two asyncio tasks share one OS thread and would
serialize at the Python level, never exercising the kernel guarantee.
Subprocess invocations of the real CLI also test the end-to-end install
(``sys.executable -m codegenie``) which is what edge case #12 actually
contemplates.

ADRs honored: ADR-0001 (BLAKE3 content addressing), ADR-0003 (per-probe
schema-version invalidation; both gathers must hit the same key),
ADR-0009 (``ProbeExecution`` tagged union surface for the metamorphic
``CacheHit`` partner), ADR-0011 (``0700``/``0600`` post-gather invariant
extended to the concurrent-gather case).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

# Importing the language_detection module is what triggers its
# ``@register_probe`` decorator on the ``default_registry``. The CLI does
# this lazily via ``importlib``; in-process tests must do it explicitly.
import codegenie.probes.language_detection  # noqa: F401 — side-effect import
from codegenie.cache.store import CacheStore
from codegenie.config.defaults import Config
from codegenie.coordinator.coordinator import CacheHit, gather
from codegenie.coordinator.snapshot import build_snapshot
from codegenie.output.sanitizer import OutputSanitizer
from codegenie.probes.registry import default_registry

_FIXTURE_SRC = Path(__file__).parent.parent / "fixtures" / "js_only"
_GATHER_TIMEOUT_S = 60


def _hash_tree(root: Path) -> dict[str, str]:
    """Recursive SHA-256 manifest for fixture-immutability assertions."""
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def _gather_cmd(fixture: Path) -> list[str]:
    """CLI invocation. ``--no-gitignore`` is a group-level flag (click
    binds options left-to-right) so it MUST appear before ``gather``."""
    return [sys.executable, "-m", "codegenie", "--no-gitignore", "gather", str(fixture)]


def _run_gather(fixture: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        _gather_cmd(fixture),
        capture_output=True,
        text=True,
        timeout=_GATHER_TIMEOUT_S,
        check=False,
    )


def _assert_codegenie_perms(cache_root: Path) -> None:
    """Walk ``cache_root`` and assert every dir is 0700, every file 0600.

    Extends ADR-0011's post-``gather`` permission invariant to the
    concurrent-gather case. The transient ``actions/cache`` restore
    window is explicitly NOT asserted here.
    """
    for entry in cache_root.rglob("*"):
        mode = stat.S_IMODE(entry.stat().st_mode)
        expected = 0o700 if entry.is_dir() else 0o600
        assert mode == expected, f"{entry}: expected {oct(expected)}, got {oct(mode)}"


def test_two_concurrent_gathers_leave_consistent_cache(tmp_path: Path) -> None:
    """Edge case #12: two ``codegenie gather`` *processes* against the same
    ``.codegenie/cache/index.jsonl`` must both exit 0; ``index.jsonl`` parses
    line-by-line with no torn / concatenated records; post-finish mode bits
    are 0600/0700; the analyzed fixture is byte-for-byte unchanged.
    """
    fixture = tmp_path / "js_only"
    shutil.copytree(_FIXTURE_SRC, fixture)
    pre_hashes = _hash_tree(fixture)

    p1 = subprocess.Popen(
        _gather_cmd(fixture),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    p2 = subprocess.Popen(
        _gather_cmd(fixture),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    _, err1 = p1.communicate(timeout=_GATHER_TIMEOUT_S)
    _, err2 = p2.communicate(timeout=_GATHER_TIMEOUT_S)

    # AC: both processes exited 0
    assert p1.returncode == 0, f"p1 stderr: {err1!r}"
    assert p2.returncode == 0, f"p2 stderr: {err2!r}"

    # AC: at least one envelope was published — both processes target the
    # same output dir under the shared fixture, so the second writer's
    # os.replace overwrites the first's. The contract is that *an* envelope
    # exists post-concurrent-runs (vs. partial / .tmp leftovers).
    envelope = fixture / ".codegenie" / "context" / "repo-context.yaml"
    assert envelope.exists(), f"envelope missing at {envelope}"

    cache_root = fixture / ".codegenie" / "cache"

    # AC: index.jsonl parses line-by-line — no torn records, no two JSON
    # objects concatenated on one line with no separating newline.
    index_path = cache_root / "index.jsonl"
    assert index_path.exists(), f"index missing under {cache_root}"
    with index_path.open("rb") as fh:
        for raw_line in fh:
            line = raw_line.rstrip(b"\n")
            if not line:
                continue
            json.loads(line)  # raises on torn record
            assert b"}{" not in line, f"two JSON objects on one line: {line!r}"

    # AC: ADR-0011 permission invariant extended to concurrent case.
    _assert_codegenie_perms(cache_root)

    # AC: audit records — both runs recorded language_detection with
    # exit_status="ok"; the combined cache_hit shape is (False, False)
    # (both miss-then-write — benign collision under deterministic bytes)
    # OR (False, True) (one wrote, the other read). Never any other shape.
    runs_dir = fixture / ".codegenie" / "context" / "runs"
    run_files = sorted(runs_dir.glob("*.json"))
    assert len(run_files) >= 2, f"expected ≥2 audit records, got {len(run_files)}"

    cache_hits: list[bool] = []
    for rf in run_files[-2:]:
        record = json.loads(rf.read_text())
        ld = next(
            (pe for pe in record["probes"] if pe["name"] == "language_detection"),
            None,
        )
        assert ld is not None, f"language_detection missing from {rf}"
        assert ld["exit_status"] == "ok", ld
        cache_hits.append(bool(ld.get("cache_hit", False)))
    assert sorted(cache_hits) in ([False, False], [False, True]), cache_hits

    # AC: fixture immutability — neither process wrote into the analyzed-repo
    # tree (excluding the .codegenie/ outputs we expect both to create).
    post_filtered = {
        k: v for k, v in _hash_tree(fixture).items() if not k.startswith(".codegenie/")
    }
    pre_filtered = {k: v for k, v in pre_hashes.items() if not k.startswith(".codegenie/")}
    assert post_filtered == pre_filtered, "fixture mutated by gather"


def test_concurrent_then_in_process_third_gather_is_cache_hit(tmp_path: Path) -> None:
    """Metamorphic partner to the concurrent test.

    Without this assertion, AC "(False, False) OR (False, True)" admits a
    cache-never-hits regression: with two concurrent miss-then-writes both
    landing as ``Ran``, the (False, False) branch passes vacuously. The
    third in-process ``gather`` against the same cache MUST return
    :class:`CacheHit` for ``language_detection`` — proving at least one of
    the two concurrent writes produced a readable blob (ADR-0009).
    """
    fixture = tmp_path / "js_only"
    shutil.copytree(_FIXTURE_SRC, fixture)

    p1 = subprocess.Popen(_gather_cmd(fixture))
    p2 = subprocess.Popen(_gather_cmd(fixture))
    assert p1.wait(timeout=_GATHER_TIMEOUT_S) == 0
    assert p2.wait(timeout=_GATHER_TIMEOUT_S) == 0

    # Third gather, in-process, observes GatherResult.executions directly.
    cfg = Config()
    snap = build_snapshot(fixture, cfg)
    cache = CacheStore(
        cache_dir=fixture / ".codegenie" / "cache",
        ttl_hours=cfg.cache_ttl_hours,
    )
    sanitizer = OutputSanitizer()
    # The CLI dispatches the bullet tracer with ``frozenset({"unknown"})``
    # (cli.py:_seam_registry_for_task); use the same filter so the same
    # probe set is resolved and the cache lookup uses the same key tuple.
    probe_classes = default_registry.for_task("__bullet_tracer__", frozenset({"unknown"}))
    probes = [cls() for cls in probe_classes]
    assert probes, "no probes registered for the bullet tracer task"

    from codegenie.probes.base import Task

    task = Task(type="__bullet_tracer__", options={})
    result = asyncio.run(gather(snap, task, probes, cfg, cache, sanitizer))
    assert isinstance(result.executions["language_detection"], CacheHit), result.executions


def test_perm_restoration_after_concurrent_runs(tmp_path: Path) -> None:
    """ADR-0011 metamorphic perm-restoration check.

    After the concurrent pair completes, dirty one cached blob's mode to
    0644; a subsequent ``gather`` whose cache key differs (so a fresh
    ``put`` fires) MUST result in ALL blob files at mode 0600 — the
    ``_reapply_modes`` walk in :meth:`CacheStore.put` is the only thing
    that restores the dirtied file. Catches a "chmod-on-CacheStore.__init__-
    only, never on subsequent puts" regression that the post-run mode walk
    on a fresh cache alone would not.
    """
    fixture = tmp_path / "js_only"
    shutil.copytree(_FIXTURE_SRC, fixture)

    assert _run_gather(fixture).returncode == 0
    assert _run_gather(fixture).returncode == 0  # ensure ≥1 blob exists

    cache_root = fixture / ".codegenie" / "cache"
    blob = next(cache_root.glob("blobs/*/*.json"))
    os.chmod(blob, 0o644)
    assert stat.S_IMODE(blob.stat().st_mode) == 0o644

    # Mutate a tracked input so the next gather's cache key differs and a
    # fresh ``put`` fires — the ``put`` call's tail ``_reapply_modes`` walk
    # is what restores any 0644-dirtied sibling blob to 0600.
    target = fixture / "a.js"
    target.write_text(target.read_text() + "// change\n")
    assert _run_gather(fixture).returncode == 0

    for entry in cache_root.glob("blobs/*/*.json"):
        actual = stat.S_IMODE(entry.stat().st_mode)
        assert actual == 0o600, f"{entry}: {oct(actual)} (expected 0o600)"
