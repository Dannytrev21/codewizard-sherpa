"""S7-01 AC-34 — no committed ``.codegenie/`` under any portfolio fixture.

Precursor to S8-03's ``portfolio`` CI job startup check. Queries the
git index (``git ls-files``) so the check honors per-fixture
``.gitignore`` automatically — a local ``codegenie gather`` run that
writes a runtime ``.codegenie/`` directory inside a fixture (legitimate
during dev) does NOT trip the test, only a *tracked* ``.codegenie/``
path does. That is the load-bearing distinction: the rule is "do not
commit", not "do not run".
"""

from __future__ import annotations

import asyncio
from pathlib import Path

_PORTFOLIO = Path(__file__).parent.parent / "fixtures" / "portfolio"
_REPO_ROOT = Path(__file__).parent.parent.parent


def _tracked_files_under_portfolio() -> list[str]:
    """Return tracked files under tests/fixtures/portfolio/ via run_allowlisted."""
    from codegenie.exec import run_allowlisted

    relative = _PORTFOLIO.resolve().relative_to(_REPO_ROOT.resolve())
    result = asyncio.run(
        run_allowlisted(
            ["git", "ls-files", "-z", str(relative)],
            cwd=_REPO_ROOT.resolve(),
            timeout_s=10.0,
        )
    )
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", "replace")
        raise RuntimeError(f"git ls-files failed (rc={result.returncode}): {stderr}")
    out: list[str] = []
    for entry in result.stdout.split(b"\x00"):
        if not entry:
            continue
        out.append(entry.decode("utf-8"))
    return out


def test_no_committed_codegenie_cache_under_portfolio_fixtures() -> None:
    """AC-34 — no tracked `.codegenie/` path under any portfolio fixture."""
    if not _PORTFOLIO.is_dir():
        return
    offenders = [p for p in _tracked_files_under_portfolio() if "/.codegenie/" in f"/{p}"]
    assert not offenders, (
        f"tracked `.codegenie/` paths under portfolio fixtures: {offenders}. "
        f"`.codegenie/` is the runtime output namespace and is gitignored — "
        f"a committed copy would either collide with CI's runtime writes or "
        f"silently dirty goldens."
    )
