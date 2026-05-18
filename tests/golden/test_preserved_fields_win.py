"""S7-03 AC-37 — ``_PRESERVED_FIELDS`` inclusion list always wins over
``_EXCLUDED_FIELD_NAMES`` (conflict resolution rule).
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


def test_preserved_field_overrides_excluded_name() -> None:
    """If a field appears in both tables, preserved wins."""
    mod = _load_regen_module()
    # Synthetic conflict: pretend ``image_digest`` were in both lists.
    # _is_excluded_field is the function under test.
    is_excluded = mod._is_excluded_field  # type: ignore[attr-defined]
    for name in mod._PRESERVED_FIELDS:  # type: ignore[attr-defined]
        assert not is_excluded(name), (
            f"{name!r} is in _PRESERVED_FIELDS but _is_excluded_field "
            f"returned True — inclusion must always win over exclusion (AC-37)."
        )


def test_preserved_fields_documented() -> None:
    """``_PRESERVED_FIELDS`` mentions at least the declared-input tokens."""
    mod = _load_regen_module()
    required = {"image_digest", "fingerprint", "fingerprints", "last_indexed"}
    missing = required - set(mod._PRESERVED_FIELDS)  # type: ignore[attr-defined]
    assert not missing, (
        f"_PRESERVED_FIELDS is missing declared-input tokens: {missing}. "
        "Document each addition with the rationale (declared-input token "
        "name or ADR pointer)."
    )
