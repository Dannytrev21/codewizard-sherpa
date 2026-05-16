"""S4-01 AC-15 — ``mypy --warn-unreachable`` fires when an exhaustive ``case``
arm is removed from ``_derive_confidence``.

Slow test (subprocesses ``mypy``). Skipped if mypy is not importable, so
local dev without the dev-dependency installed still passes; CI always has
mypy via the pre-commit + pyproject closure.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
MODULE_PATH = REPO_ROOT / "src" / "codegenie" / "probes" / "layer_b" / "index_health.py"


def _mypy_available() -> bool:
    return shutil.which("mypy") is not None or _python_has_mypy()


def _python_has_mypy() -> bool:
    proc = subprocess.run(
        [sys.executable, "-c", "import mypy"], capture_output=True, check=False
    )
    return proc.returncode == 0


pytestmark = pytest.mark.skipif(not _mypy_available(), reason="mypy not installed")


def test_baseline_module_passes_mypy_warn_unreachable() -> None:
    """Positive control — unmodified module passes ``mypy --warn-unreachable``."""
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "mypy",
            "--strict",
            "--warn-unreachable",
            "--no-incremental",
            str(MODULE_PATH),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, (
        f"baseline mypy failed:\nstdout=\n{proc.stdout}\nstderr=\n{proc.stderr}"
    )


def test_mypy_warn_unreachable_fires_on_removed_arm(tmp_path: Path) -> None:
    """T-19 — AC-15: removing the IndexerError arm makes mypy unreachable fire."""
    src = MODULE_PATH.read_text()
    # Identify the IndexerError case arm and delete it. We match on a stable
    # canonical phrase the production module uses; the test is *intentionally*
    # brittle to that phrase so a refactor renames everything atomically.
    target = "case IndexerError():"
    assert target in src, (
        f"expected production module to contain {target!r} — refactor "
        "should update this test"
    )
    # Delete the entire case-arm block (case header + indented body until
    # next dedent or function end). Implement as a line-scoped excision so
    # the result still parses.
    lines = src.splitlines()
    out_lines: list[str] = []
    i = 0
    while i < len(lines):
        if target in lines[i]:
            # Skip this case-header and its body. Compute indent of the case
            # header; skip lines whose indent is greater than the header's
            # until we hit a dedent.
            header_indent = len(lines[i]) - len(lines[i].lstrip())
            i += 1
            while i < len(lines):
                if lines[i].strip() == "":
                    i += 1
                    continue
                cur_indent = len(lines[i]) - len(lines[i].lstrip())
                if cur_indent <= header_indent:
                    break
                i += 1
            continue
        out_lines.append(lines[i])
        i += 1
    mutated = "\n".join(out_lines) + "\n"

    # Copy the mutated source into a sibling file under tmp_path tree that
    # mypy treats as the same module name. The minimum reliable approach is
    # to write it as a standalone .py file and mypy that one file.
    mutated_path = tmp_path / "_mutated_index_health.py"
    mutated_path.write_text(mutated)

    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "mypy",
            "--strict",
            "--warn-unreachable",
            "--no-incremental",
            "--follow-imports=silent",
            str(mutated_path),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    # Either the mypy run fails with "unreachable" in output, or the match
    # block raises a different exhaustiveness error. The discipline is that
    # SOMETHING must complain.
    assert proc.returncode != 0, (
        f"mypy passed on mutated module (should have failed):\n{proc.stdout}"
    )
    combined = proc.stdout + proc.stderr
    assert (
        "unreachable" in combined.lower()
        or "assert_never" in combined.lower()
        or "argument" in combined.lower()
    ), f"expected unreachable/assert_never complaint; got:\n{combined}"
