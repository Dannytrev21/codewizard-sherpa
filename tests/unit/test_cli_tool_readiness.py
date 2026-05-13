"""S4-02 — tool-readiness cache invariants (AC-7, AC-22, AC-23).

Covers the modes-and-atomicity contract on ``~/.codegenie/.tool-cache.json``
(``0700`` dir, ``0600`` file, no ``.tmp`` sidecar after a write, corrupt JSON
treated as a miss + re-written).
"""

from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest
import structlog
from click.testing import CliRunner


@pytest.fixture()
def tmp_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    return home


def test_first_run_creates_dir_and_cache_at_correct_modes(tmp_home: Path, tmp_path: Path) -> None:
    """AC-7 — ``~/.codegenie/`` created at 0700; ``.tool-cache.json`` at 0600."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.js").write_text("//")
    from codegenie.cli import cli

    CliRunner().invoke(cli, ["gather", str(repo)])
    cache = tmp_home / ".codegenie" / ".tool-cache.json"
    assert cache.exists(), "tool-cache.json must be written on first run"
    assert stat.S_IMODE(cache.stat().st_mode) == 0o600
    assert stat.S_IMODE(cache.parent.stat().st_mode) == 0o700
    payload = json.loads(cache.read_text())
    assert "git" in payload, "cache must contain the git version slot"


def test_corrupt_tool_cache_becomes_miss_then_rewritten(
    tmp_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-22 / edge case row 11 — truncated JSON → miss → re-detect →
    valid JSON; modes preserved; ``tool_cache.invalid`` warning emitted."""
    (tmp_home / ".codegenie").mkdir(mode=0o700)
    cache = tmp_home / ".codegenie" / ".tool-cache.json"
    cache.write_bytes(b"{not-jso")
    cache.chmod(0o600)

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.js").write_text("//")
    from codegenie import cli as cli_mod

    # ``configure_logging`` replaces the structlog config; suppress it here
    # so ``capture_logs()`` retains its processor chain (otherwise events
    # emitted after step 1 are lost to the captured buffer).
    monkeypatch.setattr(cli_mod, "_seam_configure_logging", lambda verbose: None)

    with structlog.testing.capture_logs() as logs:
        CliRunner().invoke(cli_mod.cli, ["gather", str(repo)])
    payload = json.loads(cache.read_text())
    assert "git" in payload
    assert stat.S_IMODE(cache.stat().st_mode) == 0o600
    assert any(r.get("event") == "tool_cache.invalid" for r in logs), (
        "warning event must surface the corruption (Rule 12)"
    )


def test_atomic_write_leaves_no_tmp_sidecar(tmp_home: Path, tmp_path: Path) -> None:
    """AC-23 — no ``.tool-cache.json.tmp`` (or sibling tmp) survives the
    write. Atomic-write pattern (``<tmp> → fsync → os.replace``) is
    enforced by post-write inspection of ``~/.codegenie/``."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.js").write_text("//")
    from codegenie.cli import cli

    CliRunner().invoke(cli, ["gather", str(repo)])
    siblings = list((tmp_home / ".codegenie").iterdir())
    tmps = [s for s in siblings if s.name.endswith(".tmp") or ".tmp" in s.name.lower()]
    assert tmps == [], f"no .tmp sidecar must survive: {tmps}"


def test_refresh_tools_forces_re_detection(
    tmp_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-2 — ``--refresh-tools`` re-runs detection even when the cache is
    fresh. Patching ``_detect_git_version`` lets us count invocations."""
    from codegenie import cli as cli_mod

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.js").write_text("//")
    runner = CliRunner()
    runner.invoke(cli_mod.cli, ["gather", str(repo)])

    calls = {"n": 0}

    def _spy() -> str:
        calls["n"] += 1
        return "git version 2.43.0"

    monkeypatch.setattr(cli_mod, "_detect_git_version", _spy)
    runner.invoke(cli_mod.cli, ["--refresh-tools", "gather", str(repo)])
    assert calls["n"] >= 1, "--refresh-tools must force re-detection"
