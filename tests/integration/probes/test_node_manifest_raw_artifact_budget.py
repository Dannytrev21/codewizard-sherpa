"""S3-06 AC-8 / AC-9 / AC-10 — raw-artifact-budget truncation on
``NodeManifestProbe``.

Story AC group 5 is the **first end-to-end exercise** of S1-09's soft
raw-artifact truncation policy on a real probe. The test pins three load-
bearing properties:

- **AC-8** — a synthetic 30 MiB lockfile triggers the truncation path
  without writing 30 MiB to tmpfs (CI disk budget). The size is simulated
  via the ``os.fstat`` monkey-patch pattern of record
  (``_validation/S3-05-node-manifest-probe.md`` T-9 +
  ``_validation/S3-01..03``). The CLI raw-artifact loop now opens the file
  and reads ``os.fstat(fd).st_size`` before deciding how much to read
  (S3-06 B-2 unblocker).
- **AC-9** — the truncated artifact on disk parses as JSON and carries the
  exact wrapper shape: ``__truncated_at_budget__: True`` (boolean — no
  coerce), ``original_bytes >= 30 MiB``, ``budget_bytes == 25 MiB``,
  ``original_bytes >= budget_bytes``.
- **AC-10** — exactly one ``probe.raw_artifact.truncated`` structlog event
  (``len(events) == 1``, not ``>= 1`` — kills the loop-bug mutant emitting
  one event per MB). Events captured via :func:`structlog.testing.capture_logs`
  per the project's S1-07 / S1-08 / S3-04 burn — never ``caplog`` under the
  ``WriteLoggerFactory`` config.

**Deviation D-7 (story AC-9 filename).** The story prescribed
``.codegenie/context/raw/node_manifest.json``; the writer names raw
artifacts by basename (``raw_path.name``) so the actual on-disk path is
``.codegenie/context/raw/pnpm-lock.yaml``. The story's filename presumed a
writer-side rename pass that doesn't exist; introducing one would widen
S3-06's scope (Rule 3 — surgical changes). The wrapper's *content* is JSON
regardless of the file extension, so the load-bearing AC-9 invariants
(parses as JSON + marker keys) are preserved verbatim.
"""

from __future__ import annotations

import json
import os
from os import stat_result
from pathlib import Path
from typing import Any

import structlog
from click.testing import CliRunner
from structlog.testing import capture_logs

from codegenie.cli import cli
from codegenie.probes._lockfiles import _pnpm

ONE_MIB = 1_048_576
SYNTHETIC_ORIGINAL_BYTES = 30 * ONE_MIB
EXPECTED_BUDGET_BYTES = 25 * ONE_MIB  # NodeManifestProbe override


def _write_minimal_pnpm_fixture(repo: Path) -> Path:
    """Write a small structurally-parseable pnpm fixture to ``repo``.

    Returns the lockfile path. The fixture is small (~150 bytes) — the
    synthetic 30 MiB size is simulated via ``os.fstat`` monkey-patch so the
    parse-cap codepath never fires before the raw-artifact truncation runs.
    """
    repo.mkdir(parents=True, exist_ok=True)
    (repo / "package.json").write_text(
        json.dumps({"name": "x", "version": "1.0.0", "dependencies": {"a": "1.0.0"}}),
        encoding="utf-8",
    )
    lockfile = repo / "pnpm-lock.yaml"
    lockfile.write_text(
        "lockfileVersion: '6.0'\n"
        "settings:\n"
        "  autoInstallPeers: true\n"
        "dependencies:\n"
        "  a:\n"
        "    specifier: 1.0.0\n"
        "    version: 1.0.0\n"
        "packages:\n"
        "  /a@1.0.0:\n"
        "    resolution: {integrity: sha512-deadbeef}\n",
        encoding="utf-8",
    )
    return lockfile


def _patch_fstat_for_lockfile(monkeypatch: Any, lockfile: Path) -> None:
    """Monkey-patch ``os.fstat`` so the lockfile reports 30 MiB size.

    Other fds (the readiness cache, audit record, repo-context.yaml, the
    raw artifact write tmp file, etc.) must still see real sizes — patching
    every fd would break the writer's ``os.fsync`` accounting and the
    audit-record SHA hash. Pattern of record: S3-05 T-9.
    """
    real_fstat = os.fstat
    target_inode = lockfile.stat().st_ino

    def _fake_fstat(fd: int) -> os.stat_result:
        real = real_fstat(fd)
        if real.st_ino == target_inode:
            return stat_result(
                (
                    real.st_mode,
                    real.st_ino,
                    real.st_dev,
                    real.st_nlink,
                    real.st_uid,
                    real.st_gid,
                    SYNTHETIC_ORIGINAL_BYTES,
                    real.st_atime,
                    real.st_mtime,
                    real.st_ctime,
                )
            )
        return real

    monkeypatch.setattr(os, "fstat", _fake_fstat)


def test_30mb_lockfile_triggers_truncation_marker_and_single_event(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """AC-8 / AC-9 / AC-10 — synthetic 30 MiB ``pnpm-lock.yaml`` truncates
    cleanly via the cli's ``os.fstat`` size pre-check.

    Mutation killers:

    - **AC-8**: a cli that read the file via ``Path.read_bytes()`` instead
      of ``os.open`` + ``os.fstat`` + ``os.read`` would never observe the
      monkey-patched 30 MiB size — the truncation policy would see the
      real ~150-byte payload and report ``Untruncated``. The test would
      then fail on the missing event (AC-10) and the missing on-disk
      marker (AC-9).
    - **AC-9 (boolean coerce)**: a wrapper that wrote
      ``"__truncated_at_budget__": 1`` (truthy int) would fail
      ``parsed["__truncated_at_budget__"] is True`` — pin against silent
      type coercion in any future JSON-encoder swap.
    - **AC-10 (loop-bug)**: a probe that re-emitted the truncation event
      once per MB (or once per chunk) would land 30 events; the
      ``len(...) == 1`` assertion catches it.
    """
    repo = tmp_path / "repo"
    lockfile = _write_minimal_pnpm_fixture(repo)

    # AC-8 — sanity-check the lockfile is structurally parseable BEFORE the
    # truncation path runs, so any failure here surfaces the parse-cap
    # codepath (S3-01 / S3-02 / S3-03) rather than the truncation path we
    # actually want to exercise.
    parsed = _pnpm.parse(lockfile)
    assert parsed is not None, "synthetic pnpm-lock.yaml must parse cleanly"

    _patch_fstat_for_lockfile(monkeypatch, lockfile)

    # AC-10 — capture every structlog event emitted during the gather.
    # ``capture_logs`` is the only reliable surface under the project's
    # ``WriteLoggerFactory`` config (S1-07 / S1-08 / S3-04 burned ``caplog``).
    with capture_logs() as logs:
        result = CliRunner().invoke(
            cli, ["--no-gitignore", "gather", str(repo)], catch_exceptions=False
        )

    assert result.exit_code == 0, f"gather exited {result.exit_code}: {result.output}"

    # AC-9 — the truncated artifact is on disk, parses as JSON, carries the
    # exact wrapper shape.
    raw_path = repo / ".codegenie" / "context" / "raw" / "pnpm-lock.yaml"
    assert raw_path.is_file(), f"truncated raw artifact missing at {raw_path}"
    wrapper = json.loads(raw_path.read_text(encoding="utf-8"))
    assert wrapper["__truncated_at_budget__"] is True, (
        "wrapper marker must be the literal boolean True — kills the "
        "int-coerce mutant ({'__truncated_at_budget__': 1})"
    )
    assert wrapper["original_bytes"] >= SYNTHETIC_ORIGINAL_BYTES
    assert wrapper["budget_bytes"] == EXPECTED_BUDGET_BYTES, (
        f"NodeManifestProbe declares raw_artifact_truncate_mb=25 → "
        f"budget_bytes must be {EXPECTED_BUDGET_BYTES}, got {wrapper['budget_bytes']}"
    )
    assert wrapper["original_bytes"] >= wrapper["budget_bytes"], (
        "truncation by definition means original exceeded budget"
    )

    # AC-10 — exactly one truncation event, with the contracted payload.
    truncate_events = [e for e in logs if e["event"] == "probe.raw_artifact.truncated"]
    assert len(truncate_events) == 1, (
        f"expected exactly one probe.raw_artifact.truncated event, got "
        f"{len(truncate_events)} — kills the once-per-MB / once-per-chunk loop mutant"
    )
    event = truncate_events[0]
    assert event["probe"] == "node_manifest"
    assert event["original_bytes"] >= SYNTHETIC_ORIGINAL_BYTES
    assert event["budget_bytes"] == EXPECTED_BUDGET_BYTES


def test_under_budget_lockfile_emits_no_truncation_event(tmp_path: Path) -> None:
    """Negative-side AC-10 pin — a small lockfile (no fstat monkey-patch)
    must NOT emit ``probe.raw_artifact.truncated``.

    Kills mutant: a cli that emitted the truncation event unconditionally
    (or via wrong polarity on the outcome tag check) would land an event
    here. This complements the positive AC-10 assertion without doubling
    the test surface — same fixture shape, no monkeypatch, opposite
    expectation. Surfaces a regression in the ``isinstance(outcome,
    Truncated)`` guard.
    """
    repo = tmp_path / "repo"
    _write_minimal_pnpm_fixture(repo)

    with capture_logs() as logs:
        result = CliRunner().invoke(
            cli, ["--no-gitignore", "gather", str(repo)], catch_exceptions=False
        )

    assert result.exit_code == 0, f"gather exited {result.exit_code}: {result.output}"
    assert not any(e["event"] == "probe.raw_artifact.truncated" for e in logs), (
        "small lockfile must not trigger the truncation event"
    )

    # The raw artifact on disk is the *untruncated* pnpm-lock.yaml contents
    # (passes through unchanged) — pins the Untruncated branch of the
    # outcome dispatch.
    raw_path = repo / ".codegenie" / "context" / "raw" / "pnpm-lock.yaml"
    assert raw_path.is_file()
    body = raw_path.read_text(encoding="utf-8")
    assert "lockfileVersion" in body, (
        "untruncated branch must preserve the original YAML content verbatim"
    )


_ = structlog  # silence unused-import on the success path; capture_logs is the real consumer
