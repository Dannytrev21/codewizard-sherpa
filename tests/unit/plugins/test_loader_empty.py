"""S2-03 — empty-lock + zero-plugins happy path.

The Phase-3 / Step-2 ship state: ``plugins/PLUGINS.lock`` is ``{}`` and
``plugins/`` contains no plugin subdirectories. The loader must succeed
with ``Ok(LoadReport(loaded=(), total_walked=0))`` — empty-lock is the
intentional Step-2 state, not a misconfiguration to guard against.
"""

from __future__ import annotations

from pathlib import Path

from codegenie.plugins.loader import LoadReport, load_plugins
from tests.fixtures.plugins.loader_fixtures import write_lockfile


def test_empty_lock_zero_plugins(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugins"
    plugin_root.mkdir()
    lock_path = write_lockfile(plugin_root, {})

    result = load_plugins(plugin_root, lock_path)
    assert result.is_ok()
    report = result.unwrap()
    assert isinstance(report, LoadReport)
    assert report.loaded == ()
    assert report.total_walked == 0


def test_repo_root_plugins_lock_ships_empty() -> None:
    """The committed ``plugins/PLUGINS.lock`` is the empty-object happy path.

    A maintainer who pre-populates the lock without a concrete plugin
    tripping this test signals the partial-migration condition ADR-0011
    warns about.
    """
    repo_root = Path(__file__).resolve().parents[3]
    lock_path = repo_root / "plugins" / "PLUGINS.lock"
    content = lock_path.read_text(encoding="utf-8").strip()
    assert content == "{}", (
        f"plugins/PLUGINS.lock is non-empty; expected '{{}}' until S7-01 lands "
        f"the first concrete plugin. Got: {content!r}"
    )
