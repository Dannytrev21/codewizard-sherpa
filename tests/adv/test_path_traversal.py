"""Adversarial: CLI ``gather`` path argument is rejected by click's ``exists=True``.

The structural invariant is "non-existent paths cannot be gathered." A
second xfail-strict test documents the current gap: Phase 0 does NOT enforce
repo-root containment for paths that resolve to an existing directory
outside the caller's intended root (``cli.py:360`` uses ``.resolve()``
without ``strict=True``). See the story's Validation notes (2026-05-13).

Traces to:
- ADR-0008 (output sanitizer chokepoint, indirectly — rejection happens
  before any artifact write).
- ``phase-arch-design.md §Component design — CLI``.
- ``cli.py:544`` — ``click.Path(exists=True, file_okay=False,
  path_type=Path)`` is the chokepoint pinned here.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner


def test_path_traversal_nonexistent_refused(tmp_path: Path) -> None:
    """
    Pins: a ``..``-bearing path whose final resolved component does not exist
          on disk is refused by ``click.Path(exists=True)`` at ``cli.py:544``
          with a non-zero exit. Exit-code value is intentionally unpinned —
          coupling the test to a specific value (2 for click usage, 1 for
          unhandled, ...) would couple the assertion to the rejection
          mechanism (Rule 3 — surgical changes).
    Traces to: phase-arch-design.md §Component design — CLI; cli.py:544.
    Catches: a regression that removed ``exists=True`` from the click.Path
             validator — the bad path would be accepted and downstream code
             would fail later with a less specific error (file-not-found at
             probe-walk time) instead of fast-rejecting at the boundary.
    """
    from codegenie.cli import cli

    escapeful = str(tmp_path / "sub" / ".." / ".." / "etc")
    result = CliRunner().invoke(cli, ["gather", escapeful])

    assert result.exit_code != 0, (
        f"non-existent path was NOT refused; exit_code={result.exit_code}, output={result.output!r}"
    )
    # AC-2c — no .codegenie/ written anywhere under tmp_path on rejection.
    # A regression that wrote artifacts before validating the path would fail.
    assert not list(tmp_path.rglob(".codegenie")), (
        "rejection leaked artifacts to disk before the path validator fired"
    )


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Phase 0 does not enforce repo-root containment for the gather "
        "argument when the resolved path exists. Tracked as a follow-up "
        "against S4-02; when containment lands, this xfail flips to PASS "
        "and strict=True fails the suite until this test is un-xfail'd."
    ),
)
def test_path_traversal_existing_outside_root_refused(tmp_path: Path) -> None:
    """
    Pins (aspirationally): a ``..``-bearing path that resolves to an existing
          directory outside the caller's intended root is refused.
    Traces to: phase-arch-design.md §Edge cases (path traversal is a
          structural defense); story Validation notes 2026-05-13.
    Catches: a future regression to any repo-root-containment check S4-02 ships.
    """
    from codegenie.cli import cli

    (tmp_path / "repo").mkdir()
    (tmp_path / "outside").mkdir()
    escapeful = str(tmp_path / "repo" / ".." / "outside")
    result = CliRunner().invoke(cli, ["gather", escapeful])

    assert result.exit_code != 0, (
        f"escape to existing out-of-root directory was NOT refused; "
        f"exit_code={result.exit_code}, output={result.output!r}"
    )
