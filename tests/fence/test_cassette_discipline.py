"""Phase-4 S3-04 AC-13 — cassette-discipline contract fence.

Two assertions:

1. ``CODEGENIE_LIVE_LLM`` is **unset** in the current process. The
   ``vcr_config`` fixture branches on this env var to flip
   ``record_mode="all"``; unsetting in CI is what keeps cassette refresh
   intentional. The env check passes vacuously on a runner where the var
   merely happens to be unset, so:

2. We **statically parse** the ``Makefile`` and assert the ``test:``
   recipe does NOT set ``CODEGENIE_LIVE_LLM``. Until S3-06 lands the
   ``refresh-cassettes`` target this is the source-of-truth assertion;
   once that target exists, this fence asserts it is the SOLE setter.

The static check fails deterministically when the contract is violated,
independent of the ambient environment (AC-13).
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MAKEFILE = _REPO_ROOT / "Makefile"

# A line like ``test:`` followed by indented recipe lines (tabs).
# Per POSIX Make: a target's recipe ends at the first non-tab-prefixed line
# (other than blank lines / comments).
_TARGET_HEADER_RE = re.compile(r"^([A-Za-z0-9_./-]+):\s*(.*)$")


def _parse_make_targets(makefile_path: Path | None = None) -> dict[str, list[str]]:
    """Return a {target: recipe-lines} map for every target in the Makefile.

    ``makefile_path`` defaults to the repo's Makefile; the planted-positive
    test passes its own path so the parser can be exercised against an
    in-memory violation without modifying repo state.
    """
    target_file = makefile_path if makefile_path is not None else _MAKEFILE
    out: dict[str, list[str]] = {}
    current: str | None = None
    for raw_line in target_file.read_text(encoding="utf-8").splitlines():
        # Recipe lines must start with TAB per POSIX make.
        if raw_line.startswith("\t"):
            if current is not None:
                out.setdefault(current, []).append(raw_line[1:])
            continue
        line = raw_line.rstrip()
        if not line or line.startswith("#"):
            current = None
            continue
        match = _TARGET_HEADER_RE.match(line)
        if match and not line.lstrip().startswith("."):
            # `.PHONY:` etc. — skip pseudo-targets that aren't real rules.
            target_name = match.group(1)
            if target_name.startswith("."):
                current = None
                continue
            current = target_name
            out.setdefault(current, [])
        else:
            current = None
    return out


def test_codegenie_live_llm_unset_in_current_process() -> None:
    """The env-var must be unset in the current pytest process (CI default)."""
    assert "CODEGENIE_LIVE_LLM" not in os.environ, (
        "CODEGENIE_LIVE_LLM must NOT be set under `make test` — only the "
        "operator-facing `make refresh-cassettes` target may set it (S3-06)."
    )


def test_makefile_test_target_does_not_set_codegenie_live_llm() -> None:
    """Statically parse the Makefile; assert the ``test:`` recipe does NOT set the var.

    Defends against an environment-dependent vacuous pass (the env-only
    check above passes on any runner where the var simply isn't set).
    """
    targets = _parse_make_targets()
    assert "test" in targets, "Makefile is missing a `test:` target"
    recipe = "\n".join(targets["test"])
    assert "CODEGENIE_LIVE_LLM" not in recipe, (
        f"`make test` must not set CODEGENIE_LIVE_LLM; recipe:\n{recipe}"
    )


def test_refresh_cassettes_is_the_sole_codegenie_live_llm_setter() -> None:
    """S3-06 introduced ``refresh-cassettes`` as the sole permitted setter
    of ``CODEGENIE_LIVE_LLM``. Any other target setting the var is a
    regression — `make test` / `make check` / `make fence` and friends
    must stay tokenless. Adding a second setter requires an ADR amendment
    AND an update to this whitelist.
    """
    targets = _parse_make_targets()
    setters = [
        name
        for name, recipe in targets.items()
        if any("CODEGENIE_LIVE_LLM" in line for line in recipe)
    ]
    assert setters == ["refresh-cassettes"], (
        f"Unexpected Makefile targets set CODEGENIE_LIVE_LLM: {setters}. "
        "Only `refresh-cassettes` may set this var (S3-06 / ADR-0014 §Decision item 6)."
    )


@pytest.mark.parametrize(
    "fake_makefile",
    [
        "test:\n\tCODEGENIE_LIVE_LLM=1 pytest -q\n",
        "test:\n\texport CODEGENIE_LIVE_LLM=1\n\tpytest -q\n",
    ],
)
def test_parser_catches_planted_makefile_violation(
    fake_makefile: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Planted-positive — the parser sees CODEGENIE_LIVE_LLM in any recipe form."""
    # Mutation guard: a refactor that quietly loses Makefile recipe parsing
    # would silently make `test_no_makefile_target_sets_codegenie_live_llm_today`
    # vacuous. Re-run the parsing helper against a planted-positive in-memory
    # Makefile and assert the violation is surfaced.
    planted_makefile = tmp_path / "Makefile"
    planted_makefile.write_text(fake_makefile)
    del monkeypatch  # unused
    targets = _parse_make_targets(planted_makefile)
    assert "test" in targets
    setters = [
        name
        for name, recipe in targets.items()
        if any("CODEGENIE_LIVE_LLM" in line for line in recipe)
    ]
    assert "test" in setters
