"""Single-callsite assertion: only ``fallback/leaf/anthropic_adapter.py`` imports
``anthropic`` (S1-05 AC-12 / ADR-0003 single-callsite rule).

Vacuously green until S3-02 lands the adapter — no file imports ``anthropic``
yet, so the offender list is empty. Once any import exists, the test asserts
the exact filename match.
"""

from __future__ import annotations

import pathlib

import codegenie
from tests.fence._phase4_scanner import walk_imports

_SRC_ROOT = pathlib.Path(codegenie.__file__).parent
_LEAF = _SRC_ROOT / "fallback" / "leaf" / "anthropic_adapter.py"


def test_only_leaf_imports_anthropic() -> None:
    leaf_resolved = _LEAF.resolve() if _LEAF.exists() else _LEAF
    offenders = [
        v
        for v in walk_imports(list(_SRC_ROOT.rglob("*.py")), forbidden={"anthropic"})
        if pathlib.Path(v.file).resolve() != leaf_resolved
    ]
    assert not offenders, (
        f"Only {_LEAF} may import `anthropic` (ADR-0003 single-callsite rule); "
        f"offenders: {offenders}"
    )
