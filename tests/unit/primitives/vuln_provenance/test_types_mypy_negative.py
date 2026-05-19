"""Phase 7 S1-02 AC-15 — `mypy --strict` negative-cases meta-test.

Three things the runtime tests can't prove on their own:

1. `DistroPackage(distro="centos", ...)` is a `mypy --strict` error
   (Literal mismatch — runtime catches it via Pydantic, but the type
   system must reject it at the call site).
2. Passing a raw `str` (`"high"`) where `AdapterConfidence` is annotated is
   a `mypy --strict` error — `StrEnum` is a *subtype* of `str`, not the
   reverse direction.
3. Returning a non-`UnknownReason` literal from a function annotated
   `-> UnknownReason` is a `mypy --strict` error.

Companion `test_mypy_accepts_correct_usage_phase7_provenance_types` is a
negative-control: a CI environment where `mypy` silently fails to start
would otherwise make every "rejects" case pass for the wrong reason.

Mirrors the S1-01 pattern (`tests/unit/types/test_identifiers_phase7_mypy_negative.py`).
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]


def _run_mypy_strict(tmp_path: Path, body: str) -> subprocess.CompletedProcess[str]:
    src_file = tmp_path / "snippet.py"
    src_file.write_text(textwrap.dedent(body), encoding="utf-8")
    return subprocess.run(
        [sys.executable, "-m", "mypy", "--strict", "--no-incremental", str(src_file)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_mypy_rejects_distro_literal_mismatch(tmp_path: Path) -> None:
    proc = _run_mypy_strict(
        tmp_path,
        """
        from codegenie.primitives.vuln_provenance.types import DistroPackage

        _ = DistroPackage(name="x", version="1", distro="centos")
        """,
    )
    assert proc.returncode != 0, (
        f"mypy --strict accepted distro='centos' (Literal mismatch). stdout={proc.stdout!r}"
    )
    assert "centos" in proc.stdout or "argument" in proc.stdout or "incompatible" in proc.stdout


def test_mypy_rejects_raw_str_where_adapter_confidence_expected(tmp_path: Path) -> None:
    proc = _run_mypy_strict(
        tmp_path,
        """
        from codegenie.primitives.vuln_provenance.types import AdapterConfidence

        def expect_confidence(c: AdapterConfidence) -> None:
            return None

        expect_confidence("high")
        """,
    )
    assert proc.returncode != 0, (
        "mypy --strict accepted a raw str where AdapterConfidence was expected. "
        f"stdout={proc.stdout!r}"
    )


def test_mypy_rejects_non_member_literal_for_unknown_reason(tmp_path: Path) -> None:
    proc = _run_mypy_strict(
        tmp_path,
        """
        from codegenie.primitives.vuln_provenance.types import UnknownReason

        def emit() -> UnknownReason:
            return "totally_unrelated_reason"
        """,
    )
    assert proc.returncode != 0, (
        "mypy --strict accepted a non-member Literal return for UnknownReason. "
        f"stdout={proc.stdout!r}"
    )


@pytest.mark.parametrize(
    "body",
    [
        # Happy-path DistroPackage construction.
        """
        from codegenie.primitives.vuln_provenance.types import DistroPackage

        _ = DistroPackage(name="openssl", version="3.0.7", distro="alpine")
        """,
        # AdapterConfidence accepts its own enum members.
        """
        from codegenie.primitives.vuln_provenance.types import AdapterConfidence

        def expect_confidence(c: AdapterConfidence) -> None:
            return None

        expect_confidence(AdapterConfidence.HIGH)
        """,
        # UnknownReason: a member literal is accepted.
        """
        from codegenie.primitives.vuln_provenance.types import UnknownReason

        def emit() -> UnknownReason:
            return "no_adapter_resolved"
        """,
    ],
    ids=["distro_alpine", "adapter_high", "unknown_member_literal"],
)
def test_mypy_accepts_correct_usage_phase7_provenance_types(tmp_path: Path, body: str) -> None:
    """Negative-control. If `mypy` silently fails to start in CI, the
    rejects-cases above would all pass for the wrong reason; this proves
    `mypy` runs and is configured against the real package."""
    proc = _run_mypy_strict(tmp_path, body)
    assert proc.returncode == 0, (
        f"mypy --strict rejected correct usage. stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )
