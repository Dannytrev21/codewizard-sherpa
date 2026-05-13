"""S4-02 — orchestration ordering + run-id correlation (AC-13, AC-15, AC-18, AC-20).

Three properties of the gather pipeline:

- **AC-20** — the 11 collaborator seams fire in the documented order. A
  reordering bug would break this test.
- **AC-13** — ``cli.start`` and ``cli.end`` share a ``run_id`` of length 16
  (``secrets.token_hex(8)``); ``cli.end`` carries an ``outcome`` field.
- **AC-15** — a non-:class:`CodegenieError` exception escaping the body
  emits ``cli.unhandled`` + ``cli.end(outcome="crash")`` and the process
  exits 1 via the click fallback.
- **AC-18** — a non-git ``tmp_path`` produces ``repo.git_commit is None``
  with no exception escaping.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import structlog
import yaml
from click.testing import CliRunner


@pytest.fixture()
def tmp_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    return home


def test_startup_order_matches_ac5_spec(
    tmp_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-20 — record call order of the 11 collaborators in AC-5."""
    from codegenie import cli as cli_mod
    from codegenie.coordinator.coordinator import GatherResult, Ran
    from codegenie.output.sanitizer import SanitizedProbeOutput

    sanitized = SanitizedProbeOutput(
        schema_slice={"language_stack": {"counts": {"javascript": 1}, "primary": "javascript"}},
        raw_artifacts=[],
        confidence="high",
        duration_ms=1,
        warnings=[],
        errors=[],
    )
    fake_result = GatherResult(
        outputs={"language_detection": sanitized},
        executions={"language_detection": Ran(output=sanitized, key="k")},
    )

    calls: list[str] = []

    def _spy(name: str, retval: object) -> object:
        def _wrap(*_a: object, **_kw: object) -> object:
            calls.append(name)
            return retval

        return _wrap

    class _StubConfig:
        max_concurrent_probes = 8
        cache_ttl_hours = 24
        enable_audit = True

    monkeypatch.setattr(cli_mod, "_seam_configure_logging", _spy("configure_logging", None))
    monkeypatch.setattr(cli_mod, "_seam_check_tools", _spy("check_tools", {"git": "stub"}))
    monkeypatch.setattr(cli_mod, "_seam_gitignore_mutation_stub", _spy("gitignore_stub", None))
    monkeypatch.setattr(cli_mod, "_seam_load_config", _spy("load_config", _StubConfig()))
    monkeypatch.setattr(cli_mod, "_seam_git_rev_parse", _spy("run_allowlisted", None))
    monkeypatch.setattr(cli_mod, "_seam_registry_for_task", _spy("registry_for_task", []))
    monkeypatch.setattr(
        cli_mod, "_seam_coordinator_gather", _spy("coordinator_gather", fake_result)
    )

    real_shallow = cli_mod._seam_shallow_merge

    def _shallow(envelope: dict[str, object], outputs: dict[str, object]) -> object:
        calls.append("shallow_merge")
        return real_shallow(envelope, outputs)

    monkeypatch.setattr(cli_mod, "_seam_shallow_merge", _shallow)
    monkeypatch.setattr(cli_mod, "_seam_validate_envelope", _spy("validate", None))
    monkeypatch.setattr(cli_mod, "_seam_write_envelope", _spy("writer_write", b"yaml: bytes\n"))
    monkeypatch.setattr(cli_mod, "_seam_audit_record", _spy("audit_record", tmp_path / "r.json"))

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.js").write_text("//")
    result = CliRunner().invoke(cli_mod.cli, ["gather", str(repo)])
    assert result.exit_code == 0, result.output
    assert calls == [
        "configure_logging",
        "check_tools",
        "gitignore_stub",
        "load_config",
        "run_allowlisted",
        "registry_for_task",
        "coordinator_gather",
        "shallow_merge",
        "validate",
        "writer_write",
        "audit_record",
    ], calls


def test_cli_start_and_end_events_share_run_id(
    tmp_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-13 — the 16-hex ``run_id`` is identical across ``cli.start`` and
    ``cli.end``; ``cli.end`` carries ``outcome="ok"``."""
    from codegenie import cli as cli_mod

    monkeypatch.setattr(cli_mod, "_seam_configure_logging", lambda verbose: None)

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.js").write_text("//")
    with structlog.testing.capture_logs() as logs:
        CliRunner().invoke(cli_mod.cli, ["gather", str(repo)])
    starts = [e for e in logs if e.get("event") == "cli.start"]
    ends = [e for e in logs if e.get("event") == "cli.end"]
    assert len(starts) == 1, starts
    assert len(ends) == 1, ends
    assert starts[0]["run_id"] == ends[0]["run_id"]
    assert len(starts[0]["run_id"]) == 16  # secrets.token_hex(8)
    assert ends[0]["outcome"] == "ok"


def test_unhandled_exception_exits_1_with_crash_outcome(
    tmp_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-15 — a non-CodegenieError → click fallback → exit 1; ``cli.end``
    carries ``outcome="crash"`` and ``cli.unhandled`` is emitted."""
    from codegenie import cli as cli_mod

    monkeypatch.setattr(cli_mod, "_seam_configure_logging", lambda verbose: None)

    def _explode(*_a: object, **_kw: object) -> None:
        raise RuntimeError("synthetic")

    monkeypatch.setattr(cli_mod, "_run_gather_pipeline", _explode)
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.js").write_text("//")
    with structlog.testing.capture_logs() as logs:
        result = CliRunner().invoke(cli_mod.cli, ["gather", str(repo)])
    assert result.exit_code == 1, result.output
    assert any(e.get("event") == "cli.unhandled" for e in logs)
    end = [e for e in logs if e.get("event") == "cli.end"][0]
    assert end["outcome"] == "crash"


def test_probe_name_collision_emits_cli_unhandled(
    tmp_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-24 — defense-in-depth: ``ProbeNameCollisionError`` → exit 1 with
    ``cli.unhandled`` carrying the class name. The S2-05 registry rejects
    duplicates at registration time so this path is rarely hit in practice;
    the test documents the fallback."""
    from codegenie import cli as cli_mod

    monkeypatch.setattr(cli_mod, "_seam_configure_logging", lambda verbose: None)

    def _collide(*_a: object, **_kw: object) -> None:
        raise cli_mod.ProbeNameCollisionError("language_detection")

    monkeypatch.setattr(cli_mod, "_run_gather_pipeline", _collide)
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.js").write_text("//")
    with structlog.testing.capture_logs() as logs:
        result = CliRunner().invoke(cli_mod.cli, ["gather", str(repo)])
    assert result.exit_code == 1
    unhandled = [e for e in logs if e.get("event") == "cli.unhandled"]
    assert unhandled
    assert "ProbeNameCollisionError" in unhandled[0].get("error_repr", "")


def test_non_git_path_yields_null_git_commit(tmp_home: Path, tmp_path: Path) -> None:
    """AC-18 — a ``tmp_path`` without ``.git/`` produces
    ``envelope.repo.git_commit is None`` with no exception escaping."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.js").write_text("//")
    from codegenie.cli import cli

    result = CliRunner().invoke(cli, ["gather", str(repo)])
    assert result.exit_code == 0, result.output
    env = yaml.safe_load((repo / ".codegenie" / "context" / "repo-context.yaml").read_text())
    assert env["repo"]["git_commit"] is None
