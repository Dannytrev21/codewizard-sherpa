"""Deliberately-incomplete match over ``DerivedQuery`` — failure target for
S2-03 AC-13. This file is NEVER imported by runtime code; it is invoked only
as input to ``python -m mypy --strict`` inside
``tests/integration/tccm/test_dispatcher_coverage_ratchet.py``.

Pin to production ADR-0030 §Consequences: every consumer of ``DerivedQuery``
MUST close its match with ``assert_never(value)``. The ``warn_unreachable =
true`` repo-wide setting (Phase 0 ``pyproject.toml``) turns this from a
runtime catch into a mypy build-failure — a sixth variant cannot land green
without a corresponding ``case`` arm.
"""

from __future__ import annotations

from typing import assert_never

from codegenie.tccm.queries import ConsumersOf, DerivedQuery


def dispatch(query: DerivedQuery) -> None:
    match query:
        case ConsumersOf():
            return
        # The four remaining variants are intentionally omitted — this is the
        # warn_unreachable trigger; mypy must report `assert_never(query)`
        # unreachable because `query` is not exhaustively narrowed to Never.
    assert_never(query)
