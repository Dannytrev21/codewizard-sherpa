"""S4-02 — global-flag propagation + stub-subcommand event names
(AC-2, AC-14, AC-16, AC-17, AC-19).

Covers:

- ``--version`` echoes the *exact* string in :data:`codegenie.version.__version__`
- ``--refresh-tools`` / ``--no-gitignore`` / ``--auto-gitignore`` propagate to
  the gather body (assertable by side-effect on the seams)
- ``_gitignore_mutation_stub`` keeps a stable signature (AC-14); a no-op
  invocation makes zero filesystem writes; ``--no-gitignore`` short-circuits
  before the stub is invoked at all
- ``cache gc`` emits exactly one structlog event named ``cache.gc.stub``
- ``--verbose`` raises the log level to DEBUG (the ``Provenance`` log inside
  ``load_config`` surfaces).
"""

from __future__ import annotations

import inspect
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


def test_version_matches_codegenie_version() -> None:
    """AC-16 — ``--version`` output contains exactly :data:`__version__`."""
    from codegenie.cli import cli
    from codegenie.version import __version__

    result = CliRunner().invoke(cli, ["--version"])
    assert result.exit_code == 0, result.output
    assert __version__ in result.output, (
        f"--version output {result.output!r} must contain {__version__!r}"
    )


def test_global_flags_propagate_to_gather(
    tmp_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-2 — ``--refresh-tools``, ``--no-gitignore``, ``--auto-gitignore``
    reach the gather body (assertable via patched seams)."""
    from codegenie import cli as cli_mod

    seen: dict[str, object] = {}

    def _check(refresh: bool) -> dict[str, str]:
        seen["refresh"] = refresh
        return {"git": "stub"}

    def _gitignore(repo_root: Path, *, auto: bool, skip: bool) -> None:
        seen["gitignore"] = (auto, skip)

    monkeypatch.setattr(cli_mod, "_seam_check_tools", _check)
    monkeypatch.setattr(cli_mod, "_seam_maybe_append_gitignore", _gitignore)
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.js").write_text("//")
    CliRunner().invoke(cli_mod.cli, ["--refresh-tools", "--no-gitignore", "gather", str(repo)])
    assert seen["refresh"] is True, "(refresh_tools must reach _seam_check_tools)"
    assert seen["gitignore"] == (False, True), (
        f"--no-gitignore must propagate as skip=True; got {seen['gitignore']!r}"
    )


def test_auto_gitignore_propagates(
    tmp_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-2 — ``--auto-gitignore`` reaches the stub as ``auto=True``."""
    from codegenie import cli as cli_mod

    seen: dict[str, object] = {}

    def _gitignore(repo_root: Path, *, auto: bool, skip: bool) -> None:
        seen["gitignore"] = (auto, skip)

    monkeypatch.setattr(cli_mod, "_seam_maybe_append_gitignore", _gitignore)
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.js").write_text("//")
    CliRunner().invoke(cli_mod.cli, ["--auto-gitignore", "gather", str(repo)])
    assert seen["gitignore"] == (True, False)


def test_cache_gc_stub_emits_exact_event_name() -> None:
    """AC-17 — exact event name ``cache.gc.stub`` is part of the Phase-1+
    migration contract; renames require an ADR amendment."""
    from codegenie.cli import cli

    with structlog.testing.capture_logs() as logs:
        result = CliRunner().invoke(cli, ["cache", "gc"])
    assert result.exit_code == 0, result.output
    stub_events = [e for e in logs if e.get("event") == "cache.gc.stub"]
    assert len(stub_events) == 1, [e.get("event") for e in logs]


def test_gitignore_seam_signature_and_skip_is_noop(tmp_home: Path, tmp_path: Path) -> None:
    """S4-03 — seam signature stays stable; ``skip=True`` is a true filesystem no-op.

    The helper's full branch matrix lives in
    :mod:`tests.unit.test_gitignore_mutation` — this CLI-level test only
    pins the seam contract: signature parity with the S4-02 stub and the
    ``skip=True`` short-circuit that has zero filesystem effect.
    """
    from codegenie.cli import _seam_maybe_append_gitignore as seam

    sig = inspect.signature(seam)
    assert list(sig.parameters) == ["repo_root", "auto", "skip"]
    assert sig.parameters["auto"].kind == inspect.Parameter.KEYWORD_ONLY
    assert sig.parameters["skip"].kind == inspect.Parameter.KEYWORD_ONLY

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    seam(workspace, auto=False, skip=True)
    assert list(workspace.iterdir()) == [], "skip=True must not write any file"


def test_verbose_emits_debug_events(tmp_home: Path, tmp_path: Path) -> None:
    """AC-19 — ``--verbose`` raises the log level to DEBUG. The
    ``config.loaded`` event from :func:`codegenie.config.loader.load_config`
    is emitted at DEBUG level (per phase-arch §Harness engineering /
    Configuration), so a ``--verbose`` run produces at least one event
    rendered at ``"level": "debug"`` on stderr. Without ``--verbose``, the
    same fixture produces no debug events.

    We assert on the JSON-rendered stderr (the non-TTY path
    ``configure_logging`` selects under CliRunner) rather than
    :func:`structlog.testing.capture_logs` because the latter swaps the
    processor chain but NOT the ``wrapper_class`` — ``configure_logging``
    re-installs the verbose ``wrapper_class`` after ``capture_logs`` runs
    its setup, which would lose the captured events."""
    from codegenie.cli import cli

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.js").write_text("//")
    runner = CliRunner()
    result = runner.invoke(cli, ["--verbose", "gather", str(repo)])
    assert result.exit_code == 0, result.output
    # CliRunner with default ``mix_stderr=True`` (click 8.x default) merges
    # stderr into ``result.output``; the structlog JSON renderer writes its
    # ``"level"`` field there so we can substring-check on the merged
    # output buffer.
    assert '"level": "debug"' in result.output or '"level":"debug"' in result.output, (
        f"expected --verbose to surface DEBUG events on stderr; got:\n{result.output}"
    )

    # Sibling case: WITHOUT --verbose, no debug event surfaces.
    repo2 = tmp_path / "repo2"
    repo2.mkdir()
    (repo2 / "b.js").write_text("//")
    result2 = runner.invoke(cli, ["gather", str(repo2)])
    assert result2.exit_code == 0, result2.output
    assert '"level": "debug"' not in result2.output and '"level":"debug"' not in result2.output, (
        f"without --verbose, no debug event should fire; got:\n{result2.output}"
    )
