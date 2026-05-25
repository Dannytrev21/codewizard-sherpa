"""Phase-4 S3-05 — unit tests for the pure scanner helpers (AC-19, AC-23).

Exercises ``_collect_sanitizer_findings`` and ``_collect_lock_findings``
against tmp directories so the aggregation semantics (one bad cassette
must not hide the next) are verified independently of the repo state.
Also covers the AC-23 ``--check`` no-write semantics for the CLI.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

from codegenie.cli import cli
from codegenie.fallback.cassette.manifest import rebuild_lockfile
from tests.security.test_cassettes_clean import (
    _collect_lock_findings,
    _collect_sanitizer_findings,
)

# Minimal sanitized cassette YAML payload — passes the sanitizer.
_CLEAN_CASSETTE_YAML = """interactions:
- request:
    method: POST
    uri: https://api.anthropic.com/v1/messages
    headers: {}
    body: '{"model": "claude-3-5-sonnet"}'
  response:
    status:
      code: 200
      message: OK
    headers:
      content-type:
      - application/json
    body:
      string: '{"id": "msg_test", "type": "message"}'
"""

# A leaky cassette with an Authorization header.
_DIRTY_CASSETTE_YAML = """interactions:
- request:
    method: POST
    uri: https://api.anthropic.com/v1/messages
    headers:
      Authorization: Bearer sk-ant-FIXTURE-NOT-REAL-1234567890abcdef
    body: '{}'
  response:
    status:
      code: 200
      message: OK
    headers: {}
    body:
      string: '{}'
"""


def _write_clean(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_CLEAN_CASSETTE_YAML, encoding="utf-8")


def _write_dirty(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_DIRTY_CASSETTE_YAML, encoding="utf-8")


def _write_lock(anthropic_dir: Path, entries: dict[str, str]) -> None:
    """Write a properly-formatted (sorted, two-space, trailing newline) lock."""
    anthropic_dir.mkdir(parents=True, exist_ok=True)
    if not entries:
        (anthropic_dir / "cassettes.lock").write_text("", encoding="utf-8")
        return
    rows = sorted(entries.items())
    text = "".join(f"{relpath}  {digest}\n" for relpath, digest in rows)
    (anthropic_dir / "cassettes.lock").write_text(text, encoding="utf-8")


# --- _collect_sanitizer_findings ------------------------------------------


def test_collect_sanitizer_findings_is_empty_on_empty_dir(tmp_path: Path) -> None:
    """No cassettes → no findings (the bootstrap path)."""
    cassettes = tmp_path / "cassettes"
    cassettes.mkdir()
    assert _collect_sanitizer_findings(cassettes) == ()


def test_collect_sanitizer_findings_is_empty_on_nonexistent_dir(tmp_path: Path) -> None:
    """Missing root dir → empty findings (defensive — pre-bootstrap state)."""
    missing = tmp_path / "does_not_exist"
    assert _collect_sanitizer_findings(missing) == ()


def test_collect_sanitizer_findings_returns_all_leaks(tmp_path: Path) -> None:
    """Two dirty cassettes → BOTH appear in the findings (AC-19 no-hiding)."""
    cassettes = tmp_path / "cassettes" / "anthropic"
    _write_dirty(cassettes / "a.yaml")
    _write_dirty(cassettes / "b.yaml")
    _write_clean(cassettes / "c.yaml")
    findings = _collect_sanitizer_findings(tmp_path / "cassettes")
    assert any("anthropic/a.yaml" in f for f in findings)
    assert any("anthropic/b.yaml" in f for f in findings)
    assert all("anthropic/c.yaml" not in f for f in findings)


# --- _collect_lock_findings ----------------------------------------------


def test_collect_lock_findings_empty_on_bootstrap_dir(tmp_path: Path) -> None:
    """Empty anthropic/ + empty lock → no findings."""
    anthropic = tmp_path / "anthropic"
    _write_lock(anthropic, {})
    assert _collect_lock_findings(anthropic) == ()


def test_collect_lock_findings_reports_all_drift_orphan_and_stale(tmp_path: Path) -> None:
    """One drift + one orphan + one stale all surface in a single pass (AC-19)."""
    anthropic = tmp_path / "anthropic"
    drifted = anthropic / "drift.yaml"
    orphan = anthropic / "orphan.yaml"
    _write_clean(drifted)
    _write_clean(orphan)
    # Lock entry for drift.yaml has the *wrong* digest; stale.yaml is in the
    # lock but absent from disk; orphan.yaml is on disk but absent from lock.
    _write_lock(
        anthropic,
        {
            "drift.yaml": "0" * 64,
            "stale.yaml": "f" * 64,
        },
    )
    findings = _collect_lock_findings(anthropic)
    joined = "\n".join(findings)
    assert "cassette.lock_drift: drift.yaml" in joined
    assert "cassette.lock_orphan: orphan.yaml" in joined
    assert "cassette.lock_stale: stale.yaml" in joined


def test_collect_lock_findings_reports_missing_lock(tmp_path: Path) -> None:
    """Missing lock file → exactly one ``cassette.lock_malformed`` finding."""
    anthropic = tmp_path / "anthropic"
    _write_clean(anthropic / "a.yaml")  # cassette exists, but no lock yet
    findings = _collect_lock_findings(anthropic)
    assert len(findings) == 1
    assert "cassette.lock_malformed: missing_lockfile" in findings[0]


def test_collect_lock_findings_reports_malformed_lock(tmp_path: Path) -> None:
    """A malformed lock short-circuits drift/orphan/stale checks (one finding)."""
    anthropic = tmp_path / "anthropic"
    _write_clean(anthropic / "a.yaml")
    # Single-space separator → ``missing_separator`` reason.
    (anthropic / "cassettes.lock").write_text("a.yaml " + "0" * 64 + "\n", encoding="utf-8")
    findings = _collect_lock_findings(anthropic)
    assert len(findings) == 1
    assert "cassette.lock_malformed: missing_separator" in findings[0]


def test_collect_lock_findings_passes_when_lock_matches(tmp_path: Path) -> None:
    """The happy path: every cassette digest matches its lock entry."""
    anthropic = tmp_path / "anthropic"
    _write_clean(anthropic / "good.yaml")
    rebuilt = rebuild_lockfile(anthropic)
    (anthropic / "cassettes.lock").write_text(rebuilt, encoding="utf-8")
    assert _collect_lock_findings(anthropic) == ()


# --- CLI ``--check`` no-write semantics (AC-23) --------------------------


def test_rebuild_lockfile_write_mode_creates_lock(tmp_path: Path) -> None:
    """Write mode produces the lock file and exits 0 on first run."""
    anthropic = tmp_path / "anthropic"
    _write_clean(anthropic / "a.yaml")
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["cassette", "rebuild-lockfile", "--cassettes-dir", str(anthropic)],
    )
    assert result.exit_code == 0, result.output + (result.exception or "").__repr__()
    lock = (anthropic / "cassettes.lock").read_text(encoding="utf-8")
    assert lock == rebuild_lockfile(anthropic)


def test_rebuild_lockfile_write_mode_is_idempotent(tmp_path: Path) -> None:
    """Second write against a consistent lock is byte-idempotent (AC-23)."""
    anthropic = tmp_path / "anthropic"
    _write_clean(anthropic / "a.yaml")
    runner = CliRunner()
    runner.invoke(cli, ["cassette", "rebuild-lockfile", "--cassettes-dir", str(anthropic)])
    first = (anthropic / "cassettes.lock").read_bytes()
    runner.invoke(cli, ["cassette", "rebuild-lockfile", "--cassettes-dir", str(anthropic)])
    second = (anthropic / "cassettes.lock").read_bytes()
    assert first == second


def test_rebuild_lockfile_check_mode_no_write_on_drift(tmp_path: Path) -> None:
    """--check on a stale lock exits non-zero and leaves bytes unchanged."""
    anthropic = tmp_path / "anthropic"
    _write_clean(anthropic / "a.yaml")
    # Plant a deliberately-wrong digest under a properly formatted lock so we
    # exercise the drift path (not the malformed path).
    stale_text = f"a.yaml  {'0' * 64}\n"
    (anthropic / "cassettes.lock").write_text(stale_text, encoding="utf-8")
    pre_bytes = (anthropic / "cassettes.lock").read_bytes()
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["cassette", "rebuild-lockfile", "--check", "--cassettes-dir", str(anthropic)],
    )
    assert result.exit_code == 8, result.output
    post_bytes = (anthropic / "cassettes.lock").read_bytes()
    assert post_bytes == pre_bytes


def test_rebuild_lockfile_check_mode_passes_when_consistent(tmp_path: Path) -> None:
    """--check on a consistent lock exits 0 and writes nothing."""
    anthropic = tmp_path / "anthropic"
    _write_clean(anthropic / "a.yaml")
    rebuilt = rebuild_lockfile(anthropic)
    (anthropic / "cassettes.lock").write_text(rebuilt, encoding="utf-8")
    pre_bytes = (anthropic / "cassettes.lock").read_bytes()
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["cassette", "rebuild-lockfile", "--check", "--cassettes-dir", str(anthropic)],
    )
    assert result.exit_code == 0
    assert (anthropic / "cassettes.lock").read_bytes() == pre_bytes


def test_rebuild_lockfile_refuses_dirty_cassette(tmp_path: Path) -> None:
    """AC-4 — the CLI refuses to lock in a sanitizer-violating cassette."""
    anthropic = tmp_path / "anthropic"
    _write_dirty(anthropic / "leak.yaml")
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["cassette", "rebuild-lockfile", "--cassettes-dir", str(anthropic)],
    )
    assert result.exit_code == 9, result.output
    assert not (anthropic / "cassettes.lock").exists()


def test_rebuild_lockfile_default_dir_uses_cwd_anthropic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No ``--cassettes-dir`` flag → resolves to ``cwd/tests/cassettes/anthropic``."""
    # Build a fake repo layout so the default-resolution branch is exercised
    # without our test ever touching the real repo tree.
    fake_root = tmp_path / "fake_repo"
    anthropic = fake_root / "tests" / "cassettes" / "anthropic"
    _write_clean(anthropic / "a.yaml")
    monkeypatch.chdir(fake_root)
    runner = CliRunner()
    result = runner.invoke(cli, ["cassette", "rebuild-lockfile"])
    assert result.exit_code == 0, result.output
    assert (anthropic / "cassettes.lock").exists()


# Cleanup: avoid bleeding artifacts back into the repo if tmp_path resolution
# misbehaves on some platforms (defensive — pytest tmp_path is always per-test).
def _no_repo_pollution_marker() -> None:  # pragma: no cover - module-side check
    repo_lock = Path("tests/cassettes/anthropic/cassettes.lock")
    if repo_lock.exists():
        # We don't fail here — the bootstrap commit will create this file.
        return
    sys.stderr.write(  # noqa: T201
        "[test_cassette_lock_invariants] no real cassettes.lock yet — bootstrap mode\n"
    )


del shutil  # silence unused-import on success paths
