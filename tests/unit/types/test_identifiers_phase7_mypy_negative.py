"""Phase 7 S1-01 AC-6 — cross-newtype swap is a mypy --strict error.

Executable subprocess-mypy meta-test. For each ``(A, B)`` pair in the swap
matrix, write a temp ``.py`` that calls ``def _accept_<a>(_: A) -> None`` with
a ``B(...)`` value and assert that ``mypy --strict`` exits non-zero with an
``argument`` / ``incompatible type`` diagnostic.

The companion ``test_mypy_accepts_correct_usage_phase7`` is a negative-control:
without it, a CI environment where ``mypy`` silently fails to start would make
every swap test pass for the wrong reason. Mirrors Phase 3's S1-01 precedent
in ``test_identifiers_phase3_mypy_negative.py``.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

PHASE7_STR_NEWTYPES = ("ImageRef", "ImageDigest", "LayerDigest", "RuntimeId", "DockerStageName")

# Every Phase 7 newtype appears as either A or B in ≥ 1 pair.
SWAP_PAIRS: list[tuple[str, str]] = [
    ("ImageDigest", "LayerDigest"),
    ("LayerDigest", "ImageDigest"),
    ("ImageRef", "ImageDigest"),
    ("ImageDigest", "ImageRef"),
    ("RuntimeId", "DockerStageName"),
    ("DockerStageName", "RuntimeId"),
]


def _ctor_arg(name: str) -> str:
    """Return a syntactically-correct literal-string for ``name(...)``.

    NewType constructors do NOT validate at runtime; this only needs to be a
    string. Choosing inputs that resemble each newtype's grammar keeps the
    intent of the test readable for a human reviewer (mirrors Phase 3's
    ``_ctor_arg`` precedent).
    """
    if name in ("ImageDigest", "LayerDigest"):
        return f'"sha256:{"0" * 64}"'
    if name == "ImageRef":
        return '"node:20-alpine"'
    if name == "RuntimeId":
        return '"node20"'
    if name == "DockerStageName":
        return '"builder"'
    raise AssertionError(f"unknown Phase-7 newtype {name!r}")


@pytest.mark.parametrize("a,b", SWAP_PAIRS, ids=lambda v: v if isinstance(v, str) else "")
def test_mypy_rejects_phase7_swap(tmp_path: Path, a: str, b: str) -> None:
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


def test_mypy_accepts_correct_usage_phase7(tmp_path: Path) -> None:
    """Negative-control — calling each ``_accept_<a>(A(...))`` must type-check.

    Without this, a broken mypy harness would make every swap pass for the
    wrong reason (Phase 3 precedent — ``test_mypy_accepts_correct_usage``).
    """
    lines = [
        "from codegenie.types.identifiers import (",
        *(f"    {n}," for n in PHASE7_STR_NEWTYPES),
        ")",
        "",
    ]
    for n in PHASE7_STR_NEWTYPES:
        lines.append(f"def _accept_{n.lower()}(_x: {n}) -> None: ...")
        lines.append(f"_accept_{n.lower()}({n}({_ctor_arg(n)}))")
    tmp = tmp_path / "ok.py"
    tmp.write_text("\n".join(lines) + "\n")
    result = subprocess.run(
        [sys.executable, "-m", "mypy", "--strict", str(tmp)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"mypy --strict rejected correct usage; stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
