"""S7-03 AC-25 — golden count guard.

Asserts three identities:

1. on-disk ``*.json`` count under ``tests/golden/probes/`` == int in
   ``tests/golden/probes/COUNT.txt``;
2. ``COUNT.txt`` == ``_compute_expected_golden_count()`` (the matrix is
   the single source of truth);
3. matrix == ``len(_UNIVERSAL_PROBES) * len(_FIXTURE_NAMES)`` (no silent
   matrix divergence).
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


def test_committed_golden_count_matches_count_file() -> None:
    root = _REPO_ROOT / "tests" / "golden" / "probes"
    expected = int((root / "COUNT.txt").read_text(encoding="utf-8").strip())
    actual = sum(1 for _ in root.rglob("*.json"))
    assert actual == expected, (
        f"Golden count drift: committed {actual} *.json files; "
        f"COUNT.txt says {expected}. Update COUNT.txt as a deliberate "
        "PR step (re-run `python scripts/regen_golden.py --update --portfolio`)."
    )


def test_count_file_matches_matrix() -> None:
    mod = _load_regen_module()
    expected_from_matrix = mod._compute_expected_golden_count()  # type: ignore[attr-defined]
    root = _REPO_ROOT / "tests" / "golden" / "probes"
    count = int((root / "COUNT.txt").read_text(encoding="utf-8").strip())
    assert count == expected_from_matrix, (
        f"COUNT.txt ({count}) ≠ _compute_expected_golden_count() "
        f"({expected_from_matrix}). Edit _UNIVERSAL_PROBES + _FIXTURE_NAMES + "
        "COUNT.txt in lock-step."
    )


def test_matrix_count_matches_simple_product() -> None:
    mod = _load_regen_module()
    expected = (
        len(mod._UNIVERSAL_PROBES)  # type: ignore[attr-defined]
        * len(mod._FIXTURE_NAMES)  # type: ignore[attr-defined]
    )
    assert mod._compute_expected_golden_count() == expected  # type: ignore[attr-defined]
