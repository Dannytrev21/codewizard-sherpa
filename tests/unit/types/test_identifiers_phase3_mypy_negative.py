"""Phase 3 S1-01 AC-4c — cross-newtype swap is a mypy --strict error.

Executable subprocess-mypy meta-test. For each (A, B) pair in the swap matrix,
write a temp ``.py`` that calls ``def _accept_<a>(_: A) -> None`` with a
``B(...)`` value and assert that ``mypy --strict`` exits non-zero with an
``argument`` / ``incompatible type`` diagnostic.

Replaces the broken Phase-2 S1-05 pattern in
``test_identifiers_typecheck.py`` where the swap lines were commented-out
prose. See validation report
``_validation/S1-01-phase3-newtype-identifiers.md`` for the rationale.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

# Every Phase-3 newtype appears as either A or B in ≥ 1 pair (14 distinct pairs).
SWAP_PAIRS: list[tuple[str, str]] = [
    ("WorkflowId", "TransformId"),
    ("WorkflowId", "EventId"),
    ("TransformId", "BlobDigest"),
    ("CveId", "PackageId"),
    ("PluginId", "RecipeId"),
    ("BranchName", "RegistryUrl"),
    ("SignalKind", "PrimitiveName"),
    ("SignalKind", "TransformKind"),
    ("AttemptNumber", "WorkflowId"),  # int vs str backing
    ("PrimitiveName", "TransformKind"),
    ("RecipeId", "TransformId"),
    ("EventId", "PluginId"),
    ("PackageId", "BranchName"),
    ("RegistryUrl", "BlobDigest"),
]


def _ctor_arg(name: str) -> str:
    """Return a literal argument expression for ``name(...)``."""
    return "1" if name == "AttemptNumber" else '"x"'


@pytest.mark.parametrize("a,b", SWAP_PAIRS, ids=lambda v: v if isinstance(v, str) else "")
def test_mypy_rejects_cross_newtype_swap(tmp_path: Path, a: str, b: str) -> None:
    src = textwrap.dedent(
        f"""
        from codegenie.types.identifiers import {a}, {b}

        def _accept_{a.lower()}(_x: {a}) -> None: ...

        _accept_{a.lower()}({b}({_ctor_arg(b)}))
        """
    )
    tmp = tmp_path / "swap.py"
    tmp.write_text(src)
    result = subprocess.run(
        [sys.executable, "-m", "mypy", "--strict", str(tmp)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0, (
        f"mypy --strict accepted {a} <- {b}; stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    out = result.stdout.lower()
    assert "incompatible type" in out or "argument" in out, (
        f"mypy rejected but not for the expected reason; stdout:\n{result.stdout}"
    )


def test_mypy_accepts_correct_usage(tmp_path: Path) -> None:
    """Negative-control — calling each accept_<a>(A(...)) must type-check."""
    src_lines = [
        "from codegenie.types.identifiers import (",
        "    PluginId, RecipeId, TransformId, WorkflowId, EventId, CveId,",
        "    PackageId, BranchName, BlobDigest, RegistryUrl, SignalKind,",
        "    PrimitiveName, TransformKind, AttemptNumber,",
        ")",
        "",
    ]
    str_names = [
        "PluginId",
        "RecipeId",
        "TransformId",
        "WorkflowId",
        "EventId",
        "CveId",
        "PackageId",
        "BranchName",
        "BlobDigest",
        "RegistryUrl",
        "SignalKind",
        "PrimitiveName",
        "TransformKind",
    ]
    for n in str_names:
        src_lines.append(f"def _accept_{n.lower()}(_x: {n}) -> None: ...")
        src_lines.append(f'_accept_{n.lower()}({n}("x"))')
    src_lines.append("def _accept_attempt(_x: AttemptNumber) -> None: ...")
    src_lines.append("_accept_attempt(AttemptNumber(1))")
    tmp = tmp_path / "ok.py"
    tmp.write_text("\n".join(src_lines) + "\n")
    result = subprocess.run(
        [sys.executable, "-m", "mypy", "--strict", str(tmp)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"mypy --strict rejected correct usage; stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
