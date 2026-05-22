"""Phase 4 S1-01 — mypy rejects cross-newtype substitution."""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

SWAP_PAIRS: list[tuple[str, str]] = [
    ("BudgetTokenId", "LeafResponseId"),
    ("StoreDigest", "ChainHead"),
    ("HexNonce", "ChainHead"),
    ("ModelId", "CassetteId"),
    ("SolvedExampleId", "BlobDigest"),
    ("BudgetTokenId", "CassetteId"),
    ("LeafResponseId", "StoreDigest"),
    ("CassetteId", "ModelId"),
    ("ChainHead", "SolvedExampleId"),
    ("HexNonce", "BudgetTokenId"),
    ("Similarity", "TokenCount"),
    ("TokenCount", "Similarity"),
    ("EmbeddingVector", "SolvedExampleId"),
]


def _ctor_arg(name: str) -> str:
    if name == "TokenCount":
        return "1"
    if name == "Similarity":
        return "0.9"
    if name == "EmbeddingVector":
        return "()"
    return '"x"'


@pytest.mark.parametrize(
    "a,b", SWAP_PAIRS, ids=lambda value: value if isinstance(value, str) else ""
)
def test_mypy_rejects_phase4_cross_newtype_swap(tmp_path: Path, a: str, b: str) -> None:
    source = textwrap.dedent(
        f"""
        from codegenie.types.identifiers import {a}, {b}

        def _accept(_value: {a}) -> None: ...

        _accept({b}({_ctor_arg(b)}))
        """
    )
    target = tmp_path / "swap.py"
    target.write_text(source)
    result = subprocess.run(
        [sys.executable, "-m", "mypy", "--strict", str(target)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0, (
        f"mypy accepted {a} <- {b}; stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "incompatible type" in result.stdout.lower() or "argument" in result.stdout.lower()


def test_mypy_accepts_phase4_correct_usage(tmp_path: Path) -> None:
    source = textwrap.dedent(
        """
        from codegenie.types.identifiers import (
            BudgetTokenId, CassetteId, ChainHead, EmbeddingVector, HexNonce,
            LeafResponseId, ModelId, Similarity, SolvedExampleId, StoreDigest,
            TokenCount,
        )

        def _budget(_value: BudgetTokenId) -> None: ...
        def _cassette(_value: CassetteId) -> None: ...
        def _chain(_value: ChainHead) -> None: ...
        def _embedding(_value: EmbeddingVector) -> None: ...
        def _hex(_value: HexNonce) -> None: ...
        def _leaf(_value: LeafResponseId) -> None: ...
        def _model(_value: ModelId) -> None: ...
        def _similarity(_value: Similarity) -> None: ...
        def _solved(_value: SolvedExampleId) -> None: ...
        def _store(_value: StoreDigest) -> None: ...
        def _tokens(_value: TokenCount) -> None: ...

        _budget(BudgetTokenId("x"))
        _cassette(CassetteId("x"))
        _chain(ChainHead("x"))
        _embedding(EmbeddingVector(()))
        _hex(HexNonce("x"))
        _leaf(LeafResponseId("x"))
        _model(ModelId("x"))
        _similarity(Similarity(0.9))
        _solved(SolvedExampleId("x"))
        _store(StoreDigest("x"))
        _tokens(TokenCount(1))
        """
    )
    target = tmp_path / "ok.py"
    target.write_text(source)
    result = subprocess.run(
        [sys.executable, "-m", "mypy", "--strict", str(target)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"mypy rejected correct usage; stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
