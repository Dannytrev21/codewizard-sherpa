"""S3-06 — AuditWriter + verify_runs (Gap 2 closure, ADR-0004).

Pinned by `docs/phases/00-bullet-tracer-foundations/stories/S3-06-audit-writer-verify.md`.
Tests Sections A (writer surface), B (per-variant anchor population),
C (verify_runs semantics), D (CLI subcommand wiring), E (event-name contract).
"""

from __future__ import annotations

import json
import os
import re
import stat
from dataclasses import fields
from pathlib import Path
from unittest import mock

import pytest
import structlog.testing

from codegenie.audit import (
    AuditWriter,
    ProbeExecutionRecord,
    RunRecord,
    _exit_status_for,
    verify_runs,
)
from codegenie.cache.store import CacheStore, serialize_output
from codegenie.coordinator.coordinator import CacheHit, GatherResult, Ran, Skipped
from codegenie.hashing import identity_hash_bytes
from codegenie.output.sanitizer import SanitizedProbeOutput
from codegenie.probes.base import ProbeOutput

_SHA = "sha256:" + "0" * 64


def _sanitized(
    schema_slice: dict | None = None, errors: list[str] | None = None
) -> SanitizedProbeOutput:
    return SanitizedProbeOutput(
        schema_slice=schema_slice or {"v": 1},
        raw_artifacts=[],
        confidence="high",
        duration_ms=10,
        warnings=[],
        errors=errors or [],
    )


def _gather_result(executions: dict) -> GatherResult:
    """Build a ``GatherResult`` for the audit writer tests.

    ``outputs`` carries Ran (clean) + CacheHit; errored Ran is excluded —
    matches the coordinator contract that errored outputs are not promoted
    to ``outputs`` (S3-05 amendment).
    """
    outputs = {
        name: exe.output
        for name, exe in executions.items()
        if isinstance(exe, (Ran, CacheHit)) and not (isinstance(exe, Ran) and exe.output.errors)
    }
    return GatherResult(outputs=outputs, executions=executions)


@pytest.fixture
def writer(tmp_path) -> AuditWriter:
    return AuditWriter(output_dir=tmp_path)


# --- Section A: writer surface + atomic write + permissions ---


def test_record_writes_runs_subdir_at_0700(writer, tmp_path):
    """AC-1: runs/ dir created with mode 0700."""
    result = _gather_result({"p": Ran(output=_sanitized(), key="sha256:" + "a" * 64)})
    path = writer.record(
        result,
        cli_version="0.1.0",
        sherpa_commit=None,
        tool_versions={},
        yaml_sha256=_SHA,
    )
    runs_dir = tmp_path / "runs"
    assert runs_dir.is_dir()
    assert stat.S_IMODE(runs_dir.stat().st_mode) == 0o700
    assert path.parent == runs_dir


def test_filename_is_filesystem_portable_pattern(writer):
    """AC-2: filename matches the Windows-safe pattern; no colons."""
    result = _gather_result({"p": Ran(output=_sanitized(), key=_SHA)})
    path = writer.record(
        result,
        cli_version="0.1.0",
        sherpa_commit=None,
        tool_versions={},
        yaml_sha256=_SHA,
    )
    assert ":" not in path.name
    assert re.fullmatch(r"\d{8}T\d{6}Z-[0-9a-f]{8}\.json", path.name)


def test_run_record_file_is_mode_0600_under_loose_umask(monkeypatch, writer):
    """AC-3 + ADR-0011: mode 0600 even when host umask is loose."""
    prev = os.umask(0o022)
    try:
        result = _gather_result({"p": Ran(output=_sanitized(), key=_SHA)})
        path = writer.record(
            result,
            cli_version="0.1.0",
            sherpa_commit=None,
            tool_versions={},
            yaml_sha256=_SHA,
        )
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    finally:
        os.umask(prev)


def test_record_fsyncs_before_replace(monkeypatch, writer):
    """AC-3: fsync ordered before os.replace (mirror test_output_writer.py:60-71)."""
    import codegenie.audit as audit_mod

    real_fsync, real_replace = os.fsync, os.replace
    manager = mock.Mock()
    fsync_spy = mock.MagicMock(side_effect=real_fsync)
    replace_spy = mock.MagicMock(side_effect=real_replace)
    manager.attach_mock(fsync_spy, "fsync")
    manager.attach_mock(replace_spy, "replace")
    monkeypatch.setattr(audit_mod.os, "fsync", fsync_spy)
    monkeypatch.setattr(audit_mod.os, "replace", replace_spy)

    result = _gather_result({"p": Ran(output=_sanitized(), key=_SHA)})
    writer.record(
        result,
        cli_version="0.1.0",
        sherpa_commit=None,
        tool_versions={},
        yaml_sha256=_SHA,
    )

    names = [c[0] for c in manager.mock_calls if c[0] in {"fsync", "replace"}]
    assert names == ["fsync", "replace"]


def test_atomic_write_no_partial_file_on_replace_failure(monkeypatch, writer, tmp_path):
    """AC-3: os.replace raising leaves no runs/*.json; .tmp if present is 0600."""
    import codegenie.audit as audit_mod

    monkeypatch.setattr(audit_mod.os, "replace", mock.MagicMock(side_effect=OSError("sim")))
    result = _gather_result({"p": Ran(output=_sanitized(), key=_SHA)})
    with pytest.raises(OSError):
        writer.record(
            result,
            cli_version="0.1.0",
            sherpa_commit=None,
            tool_versions={},
            yaml_sha256=_SHA,
        )
    runs_dir = tmp_path / "runs"
    assert list(runs_dir.glob("*.json")) == []
    for tmp in runs_dir.glob("*.tmp"):
        assert stat.S_IMODE(tmp.stat().st_mode) == 0o600


def test_audit_write_failed_event_on_oserror(monkeypatch, writer):
    """AC-3: structlog event audit.write.failed on OSError mid-write."""
    import codegenie.audit as audit_mod

    monkeypatch.setattr(audit_mod.os, "replace", mock.MagicMock(side_effect=OSError("disk full")))
    result = _gather_result({"p": Ran(output=_sanitized(), key=_SHA)})
    with structlog.testing.capture_logs() as logs:
        with pytest.raises(OSError):
            writer.record(
                result,
                cli_version="0.1.0",
                sherpa_commit=None,
                tool_versions={},
                yaml_sha256=_SHA,
            )
    events = [r["event"] for r in logs]
    assert "audit.write.failed" in events


def test_collision_retry_uses_fresh_suffix(monkeypatch, writer):
    """AC-4: collision on the final path triggers a fresh token_hex retry."""
    import codegenie.audit as audit_mod

    calls = iter(["aaaaaaaa", "aaaaaaaa", "bbbbbbbb"])
    monkeypatch.setattr(audit_mod.secrets, "token_hex", lambda n: next(calls))

    # Freeze the timestamp so the second call can collide deterministically
    # — without this, the second record might roll into a new wallclock
    # second and miss the collision the test is asserting on.
    fixed_ts = "20260513T120000Z"

    class _FixedDT:
        @staticmethod
        def now(tz=None):  # noqa: ARG004
            import datetime as _dt

            return _dt.datetime(2026, 5, 13, 12, 0, 0, tzinfo=_dt.UTC)

    monkeypatch.setattr(audit_mod, "datetime", _FixedDT)
    result = _gather_result({"p": Ran(output=_sanitized(), key=_SHA)})
    p1 = writer.record(
        result,
        cli_version="0.1.0",
        sherpa_commit=None,
        tool_versions={},
        yaml_sha256=_SHA,
    )
    p2 = writer.record(
        result,
        cli_version="0.1.0",
        sherpa_commit=None,
        tool_versions={},
        yaml_sha256=_SHA,
    )
    assert p1.name == f"{fixed_ts}-aaaaaaaa.json"
    assert p2.name == f"{fixed_ts}-bbbbbbbb.json"


# --- Section B: per-variant anchor population (the Gap-2 contract) ---


@pytest.mark.parametrize(
    "name, execution, expected_status, blob_sha_nonempty, key_nonempty",
    [
        ("p_ok", Ran(output=_sanitized(), key="sha256:" + "a" * 64), "ok", True, True),
        (
            "p_err",
            Ran(output=_sanitized(errors=["RuntimeError: boom"]), key="sha256:" + "b" * 64),
            "error",
            False,
            True,
        ),
        (
            "p_to",
            Ran(output=_sanitized(errors=["timeout: 30s"]), key="sha256:" + "c" * 64),
            "timeout",
            False,
            True,
        ),
        ("p_hit", CacheHit(output=_sanitized(), key="sha256:" + "d" * 64), "ok", True, True),
        ("p_skp", Skipped(reason="applies() returned False"), "skipped", False, False),
    ],
)
def test_anchor_matrix_per_variant(
    writer, name, execution, expected_status, blob_sha_nonempty, key_nonempty
):
    """AC-7: per-variant cache_key + blob_sha256 + exit_status mapping."""
    result = _gather_result({name: execution})
    path = writer.record(
        result,
        cli_version="0.1.0",
        sherpa_commit=None,
        tool_versions={},
        yaml_sha256=_SHA,
    )
    record = RunRecord.model_validate_json(path.read_text())  # AC-18 round-trip
    [probe] = record.probes
    assert probe.exit_status == expected_status, name
    if key_nonempty:
        assert probe.cache_key.startswith("sha256:"), name
    else:
        assert probe.cache_key == "", name
    if blob_sha_nonempty:
        assert probe.blob_sha256.startswith("sha256:"), name
    else:
        assert probe.blob_sha256 == "", name


def test_exit_status_helper_isolated():
    """AC-7: the _exit_status_for helper itself, tested independently."""
    assert _exit_status_for(Skipped(reason="x")) == "skipped"
    assert _exit_status_for(CacheHit(output=_sanitized(), key=_SHA)) == "ok"
    assert _exit_status_for(Ran(output=_sanitized(), key=_SHA)) == "ok"
    assert _exit_status_for(Ran(output=_sanitized(errors=["timeout: 5s"]), key=_SHA)) == "timeout"
    assert _exit_status_for(Ran(output=_sanitized(errors=["ValueError: x"]), key=_SHA)) == "error"


def test_audit_module_has_no_hashlib_or_blake3_imports():
    """AC-8: ADR-0001 chokepoint discipline."""
    source = Path("src/codegenie/audit.py").read_text()
    # Strip docstrings — they may legitimately mention the names.
    code = re.sub(r'"""[\s\S]*?"""', "", source)
    assert "hashlib" not in code, "audit.py must not import hashlib (ADR-0001 chokepoint)"
    assert "blake3" not in code, "audit.py must not import blake3 (ADR-0001 chokepoint)"


def test_blob_sha256_hashes_sanitized_not_raw_output(writer, tmp_path):
    """AC-9: ADR-0004 §Consequences — sanitized bytes are hashed."""
    from codegenie.output.sanitizer import OutputSanitizer

    san = OutputSanitizer()
    raw = ProbeOutput(
        schema_slice={"file": str(tmp_path.resolve() / "foo.py")},
        raw_artifacts=[],
        confidence="high",
        duration_ms=1,
        warnings=[],
        errors=[],
    )
    sanitized = san.scrub(raw, repo_root=tmp_path.resolve())
    raw_bytes = serialize_output(raw)
    san_bytes = serialize_output(sanitized)
    assert raw_bytes != san_bytes
    expected_sha = identity_hash_bytes(san_bytes)
    not_expected = identity_hash_bytes(raw_bytes)

    result = _gather_result({"p": Ran(output=sanitized, key=_SHA)})
    path = writer.record(
        result,
        cli_version="0.1.0",
        sherpa_commit=None,
        tool_versions={},
        yaml_sha256=_SHA,
    )
    record = RunRecord.model_validate_json(path.read_text())
    assert record.probes[0].blob_sha256 == expected_sha
    assert record.probes[0].blob_sha256 != not_expected


def test_sanitized_and_probe_output_fields_match():
    """AC-9 corollary: defeat future field-set drift between the two types."""
    assert {f.name for f in fields(SanitizedProbeOutput)} == {f.name for f in fields(ProbeOutput)}


def test_record_handles_empty_gather_result(writer):
    """Negative-space: zero probes still produces a valid record."""
    result = GatherResult(outputs={}, executions={})
    path = writer.record(
        result,
        cli_version="0.1.0",
        sherpa_commit=None,
        tool_versions={},
        yaml_sha256=_SHA,
    )
    record = RunRecord.model_validate_json(path.read_text())
    assert record.probes == []
    assert record.yaml_sha256 == _SHA


# --- Section C: verify_runs semantics ---


@pytest.fixture
def populated_run(tmp_path, writer):
    """A clean run-record + a cache containing one blob for the Ran probe."""
    cache_dir = tmp_path / "cache"
    cache = CacheStore(cache_dir, ttl_hours=24)
    sanitized = _sanitized()
    key = "sha256:" + "e" * 64
    cache._key_meta[key] = ("p_ok", "1.0.0")
    cache.put(key, sanitized)
    result = _gather_result({"p_ok": Ran(output=sanitized, key=key)})
    yaml_path = tmp_path / "repo-context.yaml"
    yaml_bytes = b"schema_version: 0.1.0\nprobes:\n  p_ok:\n    v: 1\n"
    yaml_path.write_bytes(yaml_bytes)
    yaml_sha = identity_hash_bytes(yaml_bytes)
    path = writer.record(
        result,
        cli_version="0.1.0",
        sherpa_commit=None,
        tool_versions={},
        yaml_sha256=yaml_sha,
    )
    return {
        "runs_dir": path.parent,
        "cache_dir": cache_dir,
        "yaml_path": yaml_path,
        "key": key,
    }


def test_verify_runs_zero_on_clean_run(populated_run):
    """AC-10 + AC-11 + AC-13: zero mismatches on an untampered system."""
    n = verify_runs(
        populated_run["runs_dir"], populated_run["cache_dir"], populated_run["yaml_path"]
    )
    assert n == 0


def test_verify_runs_is_idempotent_no_side_effects(populated_run):
    """Pure-read function: two calls return zero AND leave files unchanged."""
    args = (
        populated_run["runs_dir"],
        populated_run["cache_dir"],
        populated_run["yaml_path"],
    )
    files = list(populated_run["runs_dir"].iterdir())
    mtimes_before = {f: f.stat().st_mtime for f in files}
    bytes_before = {f: f.read_bytes() for f in files}
    assert verify_runs(*args) == 0
    assert verify_runs(*args) == 0
    for f in files:
        assert f.stat().st_mtime == mtimes_before[f]
        assert f.read_bytes() == bytes_before[f]


def test_verify_runs_detects_byte_level_blob_tamper(populated_run):
    """AC-11: tampering blob bytes (cache index unchanged) is detected by recompute."""
    index_path = populated_run["cache_dir"] / "index.jsonl"
    index = index_path.read_text().strip().splitlines()
    rec = json.loads(index[-1])
    blob_hex = rec["blob_blake3"].removeprefix("blake3:")
    blob_path = populated_run["cache_dir"] / "blobs" / blob_hex[:2] / f"{blob_hex}.json"
    os.chmod(blob_path, 0o600)
    blob_path.write_text(
        json.dumps(
            {
                "schema_slice": {"TAMPERED": True},
                "raw_artifacts": [],
                "confidence": "low",
                "duration_ms": 0,
                "warnings": [],
                "errors": [],
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    with structlog.testing.capture_logs() as logs:
        n = verify_runs(
            populated_run["runs_dir"], populated_run["cache_dir"], populated_run["yaml_path"]
        )
    assert n == 1
    events = [r for r in logs if r["event"] == "audit.verify.mismatch"]
    assert len(events) == 1
    assert events[0]["cache_key"] == populated_run["key"]
    assert events[0]["probe_name"] == "p_ok"


def test_verify_runs_recomputes_not_reads_stored_hash(populated_run):
    """AC-11 mutation-killer: a verifier that READS blob_sha256 from index instead of
    recomputing would survive tamper. Here we tamper ONLY the index's blob_sha256 field,
    leaving the blob bytes intact. The audit record's blob_sha256 was computed at write
    time over the (still-intact) blob bytes; a correct verifier recomputes from bytes and
    reports 0 mismatches. A mutant reading from index reports 1 (false positive)."""
    index_path = populated_run["cache_dir"] / "index.jsonl"
    lines = index_path.read_text().splitlines()
    rec = json.loads(lines[-1])
    rec["blob_sha256"] = "sha256:" + "f" * 64
    lines[-1] = json.dumps(rec, sort_keys=True, separators=(",", ":"))
    os.chmod(index_path, 0o600)
    index_path.write_text("\n".join(lines) + "\n")
    n = verify_runs(
        populated_run["runs_dir"], populated_run["cache_dir"], populated_run["yaml_path"]
    )
    assert n == 0


def test_verify_runs_missing_blob_logs_and_continues(populated_run):
    """AC-12: missing blob = mismatch + audit.verify.missing_blob event + walk continues."""
    index_path = populated_run["cache_dir"] / "index.jsonl"
    rec = json.loads(index_path.read_text().strip().splitlines()[-1])
    blob_hex = rec["blob_blake3"].removeprefix("blake3:")
    blob_path = populated_run["cache_dir"] / "blobs" / blob_hex[:2] / f"{blob_hex}.json"
    blob_path.unlink()
    with structlog.testing.capture_logs() as logs:
        n = verify_runs(
            populated_run["runs_dir"], populated_run["cache_dir"], populated_run["yaml_path"]
        )
    assert n == 1
    assert any(r["event"] == "audit.verify.missing_blob" for r in logs)


def test_verify_runs_detects_yaml_tamper(populated_run):
    """AC-13: yaml_sha256 anchor re-verification (closes exit criterion #12)."""
    yaml_path = populated_run["yaml_path"]
    os.chmod(yaml_path, 0o600)
    yaml_path.write_bytes(yaml_path.read_bytes() + b"\n# tamper\n")
    with structlog.testing.capture_logs() as logs:
        n = verify_runs(populated_run["runs_dir"], populated_run["cache_dir"], yaml_path)
    assert n >= 1
    assert any(r["event"] == "audit.verify.yaml_mismatch" for r in logs)


def test_verify_runs_skips_empty_blob_sha_records(writer, tmp_path):
    """AC-14: Skipped + errored-Ran + timeout-Ran records have blob_sha256='' and
    are NOT walked for blob verification. No missing_blob events fire for them."""
    result = _gather_result(
        {
            "p_skp": Skipped(reason="x"),
            "p_err": Ran(output=_sanitized(errors=["ValueError"]), key="sha256:" + "1" * 64),
        }
    )
    yaml_bytes = b"empty\n"
    yaml_path = tmp_path / "y.yaml"
    yaml_path.write_bytes(yaml_bytes)
    path = writer.record(
        result,
        cli_version="0.1.0",
        sherpa_commit=None,
        tool_versions={},
        yaml_sha256=identity_hash_bytes(yaml_bytes),
    )
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    os.chmod(cache_dir, 0o700)
    (cache_dir / "index.jsonl").touch(mode=0o600)
    with structlog.testing.capture_logs() as logs:
        n = verify_runs(path.parent, cache_dir, yaml_path)
    assert not any(r["event"] == "audit.verify.missing_blob" for r in logs)
    assert n == 0


def test_verify_runs_emits_summary_event(populated_run):
    """AC-15: audit.verify.ok summary event emitted exactly once."""
    with structlog.testing.capture_logs() as logs:
        verify_runs(
            populated_run["runs_dir"], populated_run["cache_dir"], populated_run["yaml_path"]
        )
    summary = [r for r in logs if r["event"] == "audit.verify.ok"]
    assert len(summary) == 1
    assert "mismatch_count" in summary[0]


# --- Section D: CLI subcommand ---


def test_cli_audit_verify_exit_codes(populated_run):
    """AC-16: clean → exit 0; tampered → exit 4 (slot per arch §CLI exit codes)."""
    from click.testing import CliRunner

    from codegenie.cli import cli

    runner = CliRunner()
    r_clean = runner.invoke(
        cli,
        [
            "audit",
            "verify",
            "--runs-dir",
            str(populated_run["runs_dir"]),
            "--cache-dir",
            str(populated_run["cache_dir"]),
            "--yaml-path",
            str(populated_run["yaml_path"]),
        ],
    )
    assert r_clean.exit_code == 0, r_clean.output

    yaml_path = populated_run["yaml_path"]
    os.chmod(yaml_path, 0o600)
    yaml_path.write_bytes(yaml_path.read_bytes() + b"# tamper\n")
    r_tamp = runner.invoke(
        cli,
        [
            "audit",
            "verify",
            "--runs-dir",
            str(populated_run["runs_dir"]),
            "--cache-dir",
            str(populated_run["cache_dir"]),
            "--yaml-path",
            str(populated_run["yaml_path"]),
        ],
    )
    assert r_tamp.exit_code != 0
    assert r_tamp.exit_code != 1
    assert r_tamp.exit_code == 4


# --- Section E: event-name contract ---


def test_audit_event_names_frozen(populated_run):
    """AC-17: literal event-name set is frozen (Phase 11 + Phase 13 subscribe by name)."""
    yaml_path = populated_run["yaml_path"]
    os.chmod(yaml_path, 0o600)
    yaml_path.write_bytes(yaml_path.read_bytes() + b"tamper\n")
    with structlog.testing.capture_logs() as logs:
        try:
            verify_runs(populated_run["runs_dir"], populated_run["cache_dir"], yaml_path)
        except Exception:  # noqa: BLE001
            pass
    names = sorted({r["event"] for r in logs if r["event"].startswith("audit.")})
    expected = {"audit.verify.ok", "audit.verify.yaml_mismatch"}
    assert expected <= set(names)
    allowed = {
        "audit.write.ok",
        "audit.write.failed",
        "audit.verify.ok",
        "audit.verify.mismatch",
        "audit.verify.missing_blob",
        "audit.verify.yaml_mismatch",
    }
    assert set(names) <= allowed


def test_probe_execution_record_round_trips(writer):
    """AC-18 corollary: RunRecord JSON round-trips through the Pydantic model."""
    result = _gather_result({"p": Ran(output=_sanitized(), key=_SHA)})
    path = writer.record(
        result,
        cli_version="0.1.0",
        sherpa_commit=None,
        tool_versions={"git": "2.39.0"},
        yaml_sha256=_SHA,
    )
    record = RunRecord.model_validate_json(path.read_text())
    assert isinstance(record.probes[0], ProbeExecutionRecord)
    assert record.tool_versions == {"git": "2.39.0"}
