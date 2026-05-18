"""S8-02 AC-9 — two consecutive gathers produce byte-identical summary blocks.

Determinism is a property of the pure formatter's sort+dedup discipline.
Two back-to-back gathers against the same fixture must produce
byte-identical stdout (after the structlog event capture is in place so
log lines don't pollute stdout). Both the zero-state path and a
non-empty (multiple seeded secrets) path are exercised.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from click.testing import CliRunner
from structlog.testing import capture_logs


def _seed_minimal_ts(tmp_path: Path) -> Path:
    src = Path(__file__).resolve().parents[2] / "fixtures" / "portfolio" / "minimal-ts"
    dst = tmp_path / "minimal-ts"
    shutil.copytree(src, dst)
    return dst


def _run_gather(fixture: Path) -> str:
    from codegenie.cli import cli

    with capture_logs():
        result = CliRunner().invoke(cli, ["--no-gitignore", "gather", str(fixture)])
    assert result.exit_code == 0, result.output
    return result.stdout


def test_byte_identical_across_two_runs_zero_state(tmp_path: Path) -> None:
    """AC-9 (zero-state) — same fixture, same stdout, byte-for-byte."""
    fixture = _seed_minimal_ts(tmp_path)
    s1 = _run_gather(fixture)
    s2 = _run_gather(fixture)
    assert s1 == s2, f"summary block not byte-identical across two runs:\nrun1={s1!r}\nrun2={s2!r}"


def test_byte_identical_with_three_seeded_secrets(tmp_path: Path) -> None:
    """AC-9 (non-empty) — three distinct seeded secrets exercise the
    sort+dedup branch; output is still byte-identical across two runs."""
    fixture = _seed_minimal_ts(tmp_path)
    # Three distinct AWS-access-key plaintexts → three distinct fingerprints.
    (fixture / "src" / "leak1.ts").write_text('export const A = "AKIA' + "A" * 16 + '";\n')
    (fixture / "src" / "leak2.ts").write_text('export const B = "AKIA' + "B" * 16 + '";\n')
    (fixture / "src" / "leak3.ts").write_text('export const C = "AKIA' + "C" * 16 + '";\n')
    s1 = _run_gather(fixture)
    s2 = _run_gather(fixture)
    assert s1 == s2
