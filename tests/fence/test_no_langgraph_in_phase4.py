"""Closure-wide assertion: no ``src/`` source imports ``langgraph`` (S1-05 AC-14).

A deliberate per-rule echo of the langgraph subset of the omnibus AC-8(2)
``test_closure_wide_phase4_still_forbidden`` — keep both per ADR-0003 §Consequences
("per-fence-rule unit tests" + "the omnibus … cross-cutting assertion"). Phase 6
owns the langgraph admission ADR; Phase 4 must not silently leak it.
"""

from __future__ import annotations

import pathlib

import codegenie
from tests.fence._phase4_scanner import walk_imports

_SRC_ROOT = pathlib.Path(codegenie.__file__).parent


def test_no_langgraph_anywhere() -> None:
    offenders = walk_imports(list(_SRC_ROOT.rglob("*.py")), forbidden={"langgraph"})
    assert not offenders, (
        f"`langgraph` is Phase 6's admission, not Phase 4 "
        f"(ADR-0003 §Consequences); offenders: {offenders}"
    )
