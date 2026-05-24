"""Mutation-guard negatives: the same scanner the live Phase-4 fence uses.

Mirrors the Phase-0 deliberate-negative pattern at
``tests/unit/test_pyproject_fence.py``: invoke the production scanner on planted
fixtures so a future "simplification" of the scanner kills both the live fence
and these tests simultaneously.

Two flavours of mutation guard:

- Four ``violator_*`` fixtures planting genuine ``import``/``from … import``
  forms — the scanner must catch each.
- One ``benign_*`` fixture mentioning ``anthropic`` only in a comment and a
  string literal — the scanner must report **zero** violations (S1-05 AC-21:
  the AST-not-regex guarantee).
"""

from __future__ import annotations

import pathlib

import pytest

from tests.fence._phase4_scanner import walk_imports

FIXTURES: pathlib.Path = pathlib.Path(__file__).parent / "_fixtures_phase4"


@pytest.mark.parametrize(
    "fixture_name,forbidden_pkg",
    [
        ("violator_probe_imports_anthropic.py.txt", "anthropic"),
        ("violator_random_file_imports_torch.py.txt", "torch"),
        ("violator_non_leaf_imports_anthropic.py.txt", "anthropic"),
        ("violator_non_rag_imports_chromadb.py.txt", "chromadb"),
    ],
)
def test_scanner_catches_each_planted_violation(
    tmp_path: pathlib.Path, fixture_name: str, forbidden_pkg: str
) -> None:
    """Each fixture plants exactly one ``forbidden_pkg`` import; the scanner
    must report exactly one violation naming that package."""
    fixture = FIXTURES / fixture_name
    target = tmp_path / "violator.py"
    target.write_text(fixture.read_text())
    out = walk_imports([target], forbidden={forbidden_pkg})
    assert len(out) == 1, f"Scanner missed planted `{forbidden_pkg}` in {fixture_name}: {out}"
    assert out[0].package == forbidden_pkg


def test_scanner_ignores_string_and_comment_mentions(tmp_path: pathlib.Path) -> None:
    """S1-05 AC-21 — the AST-not-regex guarantee.

    A forbidden name appearing only in a comment or string literal is NOT a
    violation. Mutation guard: a regex-based regression of the scanner
    false-positives here and this test dies.
    """
    benign = FIXTURES / "benign_string_literal_mentions_anthropic.py.txt"
    target = tmp_path / "benign.py"
    target.write_text(benign.read_text())
    out = walk_imports([target], forbidden={"anthropic"})
    assert out == [], f"Scanner false-positived on a non-import mention: {out}"
