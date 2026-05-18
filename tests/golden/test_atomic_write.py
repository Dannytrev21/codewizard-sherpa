"""S7-03 AC-34 — ``regen_golden.py`` writes goldens atomically via
``tempfile`` + ``os.replace``. A SIGINT or crash mid-write must not leave
a partial golden on disk.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_regen_module() -> object:
    spec = importlib.util.spec_from_file_location(
        "_regen_golden_module", _REPO_ROOT / "scripts" / "regen_golden.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_atomic_write_preserves_original_on_failure(tmp_path: Path) -> None:
    mod = _load_regen_module()
    target = tmp_path / "golden.json"
    target.write_text("ORIGINAL\n", encoding="utf-8")
    original_bytes = target.read_bytes()

    with patch.object(mod.os, "replace", side_effect=OSError("simulated SIGINT")):  # type: ignore[attr-defined]
        with pytest.raises(OSError, match="simulated SIGINT"):
            mod._atomic_write_text(target, "NEW CONTENT\n")  # type: ignore[attr-defined]

    assert target.read_bytes() == original_bytes, (
        "Original file was modified after a mid-write failure; atomic-write "
        "discipline broken (AC-34)."
    )
    # The tmp file should also be cleaned up — no stray ``.golden.json.*``
    stray = list(tmp_path.glob(".golden.json.*"))
    assert not stray, f"stray tmp file left on disk: {stray}"


def test_atomic_write_creates_parent_dir(tmp_path: Path) -> None:
    mod = _load_regen_module()
    target = tmp_path / "deep" / "nested" / "golden.json"
    mod._atomic_write_text(target, "hi\n")  # type: ignore[attr-defined]
    assert target.read_text(encoding="utf-8") == "hi\n"
