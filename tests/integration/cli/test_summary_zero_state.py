"""S8-02 AC-7 — zero-state grep-ability of the summary block.

Per ``phase-arch-design.md §"Logging"`` — *"a 0-count run is grep-able."*
On a clean ``minimal-ts`` gather (no seeded secrets, no skill
collisions), stdout must contain the literal zero-state substrings so
``grep secrets_redacted_count=0`` / ``grep 'fingerprints=\\[\\]'`` /
``grep 'skill_shadowed=\\[\\]'`` all succeed.
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


def test_three_zero_lines_present(tmp_path: Path) -> None:
    """AC-7 — all three zero-state lines appear literally on stdout."""
    from codegenie.cli import cli

    fixture = _seed_minimal_ts(tmp_path)
    with capture_logs():
        result = CliRunner().invoke(cli, ["--no-gitignore", "gather", str(fixture)])
    assert result.exit_code == 0, result.output
    assert "secrets_redacted_count=0" in result.stdout
    assert "fingerprints=[]" in result.stdout
    assert "skill_shadowed=[]" in result.stdout
