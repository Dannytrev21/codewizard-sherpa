"""S2-03 — empty-lock + zero-plugins happy path.

The Phase-3 / Step-2 ship state: ``plugins/PLUGINS.lock`` is ``{}`` and
``plugins/`` contains no plugin subdirectories. The loader must succeed
with ``Ok(LoadReport(loaded=(), total_walked=0))`` — empty-lock is the
intentional Step-2 state, not a misconfiguration to guard against.
"""

from __future__ import annotations

import json
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


def test_repo_root_plugins_lock_pins_landed_plugins() -> None:
    """The committed ``plugins/PLUGINS.lock`` pins exactly the plugins
    whose directory has shipped.

    Pre-S7-01 this fence enforced the empty-object happy path. S7-01
    (Phase-4) landed the first concrete plugin
    (``vulnerability-remediation--node--npm``) and its manifest. The
    fence now enforces the load-bearing invariant directly: every
    plugin directory under ``plugins/`` must be in the lock, and every
    locked plugin name must have a directory. Adding a plugin requires
    refreshing the lock in the same PR.
    """
    repo_root = Path(__file__).resolve().parents[3]
    plugin_root = repo_root / "plugins"
    lock_path = plugin_root / "PLUGINS.lock"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    assert isinstance(lock, dict), f"PLUGINS.lock must be a JSON object; got {type(lock)!r}"

    on_disk = {
        p.name for p in plugin_root.iterdir() if p.is_dir() and (p / "plugin.yaml").is_file()
    }
    locked = set(lock.keys())
    missing_from_lock = on_disk - locked
    extra_in_lock = locked - on_disk
    assert not missing_from_lock, (
        f"plugins on disk but not in PLUGINS.lock: {sorted(missing_from_lock)!r}. "
        f"Run the plugin-digest pinning step before committing."
    )
    assert not extra_in_lock, (
        f"plugins in PLUGINS.lock but not on disk: {sorted(extra_in_lock)!r}. "
        f"Stale lock entries must be removed in the same PR that deletes the "
        f"plugin directory."
    )
