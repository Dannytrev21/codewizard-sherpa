"""S3-03 — AC-C4 mypy-strict meta-test for closed-Literal ``reason`` rejection.

A typed ``VulnParseError(reason="typo", ...)`` snippet must fail
``mypy --strict`` AND raise ``ValidationError`` at runtime. The
``--strict`` typo-rejection is the load-bearing half — without it, a
mis-spelled reason silently slips past type-checking and only fires at
runtime.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest


@pytest.mark.skipif(shutil.which(sys.executable) is None, reason="python on PATH")
def test_invalid_reason_literal_rejected_by_mypy(tmp_path: Path) -> None:
    snippet = textwrap.dedent(
        """
        from codegenie.vuln_index.parsers import VulnParseError

        e: VulnParseError = VulnParseError(reason="typo", details={})
        """
    )
    f = tmp_path / "snip.py"
    f.write_text(snippet)
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "mypy",
            "--strict",
            "--no-incremental",
            "--explicit-package-bases",
            str(f),
        ],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=Path.cwd(),
    )
    assert proc.returncode != 0, (
        f"mypy --strict did NOT reject reason='typo' snippet:\n{proc.stdout}\n{proc.stderr}"
    )
    combined = (proc.stdout + proc.stderr).lower()
    assert "reason" in combined or "literal" in combined or "argument" in combined, (
        f"mypy output did not mention reason/Literal: {proc.stdout}"
    )
