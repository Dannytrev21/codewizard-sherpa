"""Mutation-resistance gate for the oracle invariants — Story S3-04, AC-9.

The oracle invariants in ``test_yarn_parser_oracle.py`` are decoration
unless they catch obviously-wrong parser output. This module proves they
do: for each fixture (excluding the empty fixture, which has nothing to
mutate), parse to obtain a real ``YarnLock``, then apply three known-bad
transforms (rename, version-swap, drop-entry) and assert each
corresponding invariant raises ``AssertionError`` on the mutated input
while accepting the original. Mutation-resistance becomes a CI gate per
global Rule 9 ("tests verify intent, not just behavior").

Sources:

- ``docs/phases/01-context-gather-layer-a-node/stories/S3-04-yarn-parser-parity-oracle.md``
  §"Acceptance criteria" AC-9.
- The mutators live here (rule of two — used once each, no extraction);
  the ``_check_invariant_*`` helpers live in ``test_yarn_parser_oracle``
  (also rule of two — used by the oracle module and here).
"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from codegenie.probes._lockfiles import _yarn
from codegenie.probes._lockfiles._yarn import YarnLock
from tests.unit.probes._lockfiles.test_yarn_parser_oracle import (
    _check_invariant_1,
    _check_invariant_2,
    _check_invariant_3,
)

CORPUS_DIR = Path(__file__).resolve().parents[3] / "fixtures" / "_yarn_corpus"
# Self-check runs on fixtures that have ≥ 1 entry — the empty fixture has
# nothing to mutate; the zero-boundary is covered by the oracle test's
# parametrized arm over the empty fixture.
LOCKFILES = [p for p in sorted(CORPUS_DIR.glob("*/yarn.lock")) if p.parent.name != "empty"]


def _mutate_invent_name(result: YarnLock) -> YarnLock:
    out = copy.deepcopy(result)
    entries = out.get("entries", {})
    first_key = next(iter(entries))
    entries["zzz_phantom_pkg_definitely_not_in_lockfile@^9.9.9"] = entries.pop(first_key)
    return out


def _mutate_bad_version(result: YarnLock) -> YarnLock:
    out = copy.deepcopy(result)
    entries = out.get("entries", {})
    first = entries[next(iter(entries))]
    first["version"] = "999.999.999-not-in-lockfile"
    return out


def _mutate_drop_entry(result: YarnLock) -> YarnLock:
    out = copy.deepcopy(result)
    entries = out.get("entries", {})
    entries.pop(next(iter(entries)))
    return out


@pytest.mark.parametrize("lockfile", LOCKFILES, ids=lambda p: p.parent.name)
def test_invariant_1_catches_invented_name(lockfile: Path) -> None:
    """AC-9. Baseline: real parse passes invariant 1. Mutation: renaming
    an entry to a string absent from the lockfile bytes must raise.
    """
    body = lockfile.read_text()
    real = _yarn.parse(lockfile)
    _check_invariant_1(real, body)
    with pytest.raises(AssertionError):
        _check_invariant_1(_mutate_invent_name(real), body)


@pytest.mark.parametrize("lockfile", LOCKFILES, ids=lambda p: p.parent.name)
def test_invariant_2_catches_bad_version(lockfile: Path) -> None:
    """AC-9. Baseline: real parse passes invariant 2. Mutation: swapping
    a version to a string absent from the lockfile bytes must raise.
    """
    body = lockfile.read_text()
    real = _yarn.parse(lockfile)
    _check_invariant_2(real, body)
    with pytest.raises(AssertionError):
        _check_invariant_2(_mutate_bad_version(real), body)


@pytest.mark.parametrize("lockfile", LOCKFILES, ids=lambda p: p.parent.name)
def test_invariant_3_catches_dropped_entry(lockfile: Path) -> None:
    """AC-9. Baseline: real parse passes invariant 3. Mutation: dropping
    an entry so the count diverges from header-line count must raise.
    """
    body = lockfile.read_text()
    real = _yarn.parse(lockfile)
    _check_invariant_3(real, body)
    with pytest.raises(AssertionError):
        _check_invariant_3(_mutate_drop_entry(real), body)
