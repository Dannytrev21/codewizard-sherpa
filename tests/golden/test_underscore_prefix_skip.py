"""S7-03 AC-40 — directories under ``tests/fixtures/portfolio/`` prefixed
``_`` are skipped by ``regen_golden.py``'s discovery walk.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_regen_module() -> object:
    spec = importlib.util.spec_from_file_location(
        "_regen_golden_module", _REPO_ROOT / "scripts" / "regen_golden.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_underscore_prefixed_dir_is_skipped(tmp_path: Path) -> None:
    """A future contributor creating ``_helpers/`` under the portfolio root
    must not trigger a fixture-walk pass."""
    portfolio = tmp_path / "portfolio"
    portfolio.mkdir()
    (portfolio / "_helpers_test").mkdir()
    (portfolio / "my-fixture").mkdir()
    mod = _load_regen_module()
    discovered = mod._discover_fixtures(portfolio)  # type: ignore[attr-defined]
    names = [p.name for p in discovered]
    assert "_helpers_test" not in names, (
        "_discover_fixtures returned an underscore-prefixed directory; "
        "AC-40 requires it to be skipped."
    )
    assert "my-fixture" in names
