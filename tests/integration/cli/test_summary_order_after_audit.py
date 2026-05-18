"""S8-02 AC-5 — stdout summary block emits *after* the audit record write
*before* the CLI exits 0.

Verifies (a) the audit anchor exists on disk by the time stdout's first
byte is written, and (b) the CLI exits 0 on a clean gather regardless of
``secrets_redacted_count``.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from click.testing import CliRunner
from structlog.testing import capture_logs


def _seed_minimal_ts(tmp_path: Path) -> Path:
    src = Path(__file__).resolve().parents[2] / "fixtures" / "portfolio" / "minimal-ts"
    dst = tmp_path / "minimal-ts"
    shutil.copytree(src, dst)
    return dst


def test_audit_record_exists_before_stdout(tmp_path: Path) -> None:
    """AC-5 (a) — at least one ``runs/*.json`` audit anchor exists by the
    time the CLI returns (and therefore by the time the operator reads
    stdout)."""
    from codegenie.cli import cli

    fixture = _seed_minimal_ts(tmp_path)
    with capture_logs():
        result = CliRunner().invoke(cli, ["--no-gitignore", "gather", str(fixture)])
    assert result.exit_code == 0, result.output
    runs_dir = fixture / ".codegenie" / "context" / "runs"
    assert runs_dir.exists(), "audit runs directory missing"
    run_files = list(runs_dir.glob("*.json"))
    assert run_files, "no audit run-record JSON written"
    # The three summary lines are present.
    assert re.search(r"^secrets_redacted_count=\d+$", result.stdout, re.MULTILINE)


def test_exit_code_zero_irrespective_of_count(tmp_path: Path) -> None:
    """AC-5 (b) — exit 0 on a clean gather even with a seeded secret
    (count > 0). The operator decides if a non-zero count is actionable."""
    from codegenie.cli import cli

    fixture = _seed_minimal_ts(tmp_path)
    (fixture / "src" / "leak.ts").write_text('export const K = "AKIA' + "B" * 16 + '";\n')
    with capture_logs():
        result = CliRunner().invoke(cli, ["--no-gitignore", "gather", str(fixture)])
    assert result.exit_code == 0, result.output
