"""S4-02 — ``audit verify`` reachable via the ``cli`` group (AC-8).

S3-06 ships the verification body and its exit-code mapping. This story
only asserts that the subcommand stays addressable through the new top-level
``cli`` group (``CliRunner().invoke(cli, ["audit", "verify", ...])``) and
that the ``0`` / ``4`` exit codes are preserved.

The hand-built fixture mirrors `test_audit_anchors.py:populated_run` at
the smallest viable size — a single clean run-record with a real cache
blob. A tamper toggle re-runs through the CLI to assert the exit-4 path.
"""

from __future__ import annotations

import os
import stat
from dataclasses import asdict
from pathlib import Path

import pytest
from click.testing import CliRunner

from codegenie.audit import AuditWriter
from codegenie.cache.store import CacheStore
from codegenie.coordinator.coordinator import GatherResult, Ran
from codegenie.hashing import identity_hash_bytes
from codegenie.output.sanitizer import SanitizedProbeOutput
from codegenie.probes.base import ProbeOutput, RepoSnapshot, Task


@pytest.fixture()
def populated_run(tmp_path: Path) -> dict[str, Path]:
    """Build the minimal trio expected by ``verify_runs``: runs/, cache/,
    repo-context.yaml. Returns the absolute paths."""
    runs_root = tmp_path / "runs_root"
    runs_root.mkdir()
    cache_dir = tmp_path / "cache"
    cache = CacheStore(cache_dir=cache_dir, ttl_hours=24)

    class _FakeProbe:
        name = "language_detection"
        version = "0.1.1"
        applies_to_tasks = ["*"]
        applies_to_languages = ["*"]
        declared_inputs = ["**/*.js"]

        def applies(self, *_a: object, **_kw: object) -> bool:
            return True

        async def run(self, *_a: object, **_kw: object) -> ProbeOutput:  # pragma: no cover
            raise NotImplementedError

    snap = RepoSnapshot(
        root=tmp_path.resolve(),
        git_commit=None,
        detected_languages={},
        config={},
    )
    task = Task(type="__bullet_tracer__", options={})
    key = cache.key_for(_FakeProbe(), snap, task)  # type: ignore[arg-type]

    output = SanitizedProbeOutput(
        schema_slice={"language_stack": {"counts": {"javascript": 1}, "primary": "javascript"}},
        raw_artifacts=[],
        confidence="high",
        duration_ms=1,
        warnings=[],
        errors=[],
    )
    # Put the blob through the real cache machinery — the verifier looks
    # it up by ``cache_key`` so the blob has to exist.
    probe_output = ProbeOutput(**asdict(output))
    cache.put(key, probe_output)

    gather_result = GatherResult(
        outputs={"language_detection": output},
        executions={"language_detection": Ran(output=output, key=key)},
    )

    yaml_path = tmp_path / "repo-context.yaml"
    yaml_bytes = b"schema_version: 0.1.0\n"
    yaml_path.write_bytes(yaml_bytes)
    yaml_path.chmod(0o600)
    yaml_sha = identity_hash_bytes(yaml_bytes)

    AuditWriter(runs_root).record(
        gather_result,
        cli_version="0.1.0",
        sherpa_commit=None,
        tool_versions={},
        yaml_sha256=yaml_sha,
    )

    # Tighten the cache index file mode to ``0600`` (the post-walk chmod
    # already happens in the cache code path).
    index = cache_dir / "index.jsonl"
    os.chmod(index, 0o600)

    return {
        "runs_dir": runs_root / "runs",
        "cache_dir": cache_dir,
        "yaml_path": yaml_path,
    }


def test_audit_verify_clean_returns_zero(populated_run: dict[str, Path]) -> None:
    """AC-8 — clean run → exit 0 through the ``cli`` group."""
    from codegenie.cli import cli

    result = CliRunner().invoke(
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
    assert result.exit_code == 0, result.output


def test_audit_verify_tampered_returns_four(populated_run: dict[str, Path]) -> None:
    """AC-8 — a tampered YAML → exit 4 (slot owned by audit verify per S3-06)."""
    yaml_path = populated_run["yaml_path"]
    os.chmod(yaml_path, 0o600)
    yaml_path.write_bytes(yaml_path.read_bytes() + b"# tamper\n")

    from codegenie.cli import cli

    result = CliRunner().invoke(
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
    assert result.exit_code == 4, result.output


def test_audit_verify_help_documents_exit_codes() -> None:
    """AC-8 cousin — the subcommand's --help text names exit codes 0 and 4
    so operators see the mapping inline."""
    from codegenie.cli import cli

    out = CliRunner().invoke(cli, ["audit", "verify", "--help"]).output.lower()
    assert "exit 0" in out
    assert "exit 4" in out


def test_audit_verify_flags_unchanged() -> None:
    """AC-8 — flag surface (``--runs-dir / --cache-dir / --yaml-path``)
    survived the S4-02 reshape. A missing flag must error out."""
    from codegenie.cli import cli

    out = CliRunner().invoke(cli, ["audit", "verify"])
    assert out.exit_code != 0
    assert "runs-dir" in out.output.lower()


# Keep stat import live for future mode assertions added by S4-04.
_ = stat
