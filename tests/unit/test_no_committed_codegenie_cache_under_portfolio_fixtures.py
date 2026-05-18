"""S7-01 AC-34 — no ``.codegenie/cache/`` under any portfolio fixture.

Precursor to S8-03's ``portfolio`` CI job startup check. Walks
``tests/fixtures/portfolio/`` and asserts no committed cache artifacts
exist. The per-fixture ``.gitignore`` keeps the directory out of source
control; this test enforces the policy globally so a future contributor
who force-adds a cache blob fails loud.
"""

from __future__ import annotations

from pathlib import Path

_PORTFOLIO = Path(__file__).parent.parent / "fixtures" / "portfolio"


def test_no_committed_codegenie_cache_under_portfolio_fixtures() -> None:
    """AC-34 — no `.codegenie/cache/` directory or file under any fixture."""
    if not _PORTFOLIO.is_dir():
        return  # No fixtures yet; nothing to assert.
    offenders: list[str] = []
    for path in _PORTFOLIO.rglob(".codegenie"):
        # A `.codegenie/` directory (cache or otherwise) under a portfolio
        # fixture is forbidden by AC-33 / AC-34.
        offenders.append(str(path.relative_to(_PORTFOLIO)))
    assert not offenders, (
        f"`.codegenie/` directories committed under portfolio fixtures: {offenders}. "
        f"`.codegenie/` is the runtime output namespace and is gitignored — "
        f"a committed copy would either collide with CI's runtime writes or "
        f"silently dirty goldens."
    )
