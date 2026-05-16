"""Deliberately-incomplete match over IndexFreshness — the failure target for
S1-11 AC-5. This file is NEVER imported by runtime code; it is invoked only
as input to ``python -m mypy --strict`` inside the test
(``tests/unit/test_mypy_warn_unreachable_fixture.py``).

Pin to 02-ADR-0006 §Consequences: every consumer of ``IndexFreshness`` MUST
close its match with ``assert_never(value)``; the ``warn_unreachable = true``
repo-wide setting (Phase 0 ``pyproject.toml`` line 134) turns this from a
runtime catch into a mypy build-failure.
"""

from __future__ import annotations

from typing import assert_never

from codegenie.indices.freshness import Fresh, IndexFreshness


def describe(value: IndexFreshness) -> str:
    match value:
        case Fresh():
            return "fresh"
        # case Stale(): intentionally omitted — this is the warn_unreachable trigger.
    assert_never(value)
