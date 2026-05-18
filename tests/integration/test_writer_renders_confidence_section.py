"""Integration test for S8-01 — writer renders ``CONTEXT_REPORT.md``.

AC-6 surface:

- (a) ``CONTEXT_REPORT.md`` exists post-gather alongside ``repo-context.yaml``.
- (b) Contains a ``## Confidence`` heading.
- (c) Contains at least one row per ``IndexFreshness`` that
  ``IndexHealthProbe`` emits for this fixture.
- (d) Byte-identical across two back-to-back gathers against the same fixture.

The test invokes ``python -m codegenie gather`` against a copy of
``tests/fixtures/portfolio/minimal-ts`` — the canonical small TS fixture —
and runs it twice in the same workdir so the second invocation observes the
first run's outputs. The byte-identical property is verified after both
runs complete.

ADR-0009 honored: serial execution, ``subprocess.run`` (not asyncio /
xdist). ``python`` is not in ``ALLOWED_BINARIES`` so the test-scope
``subprocess.run`` shape mirrors the portfolio sweep (S7-05).
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FIXTURE = _REPO_ROOT / "tests" / "fixtures" / "portfolio" / "minimal-ts"


def _gather(workdir: Path) -> None:
    """Run ``codegenie gather`` against *workdir*; assert exit 0."""
    result = subprocess.run(  # noqa: S603 — tests/-scope subprocess
        [
            sys.executable,
            "-m",
            "codegenie",
            "--no-gitignore",
            "gather",
            str(workdir),
        ],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert result.returncode == 0, (
        f"gather exit={result.returncode}\n"
        f"--- stdout ---\n{result.stdout}\n"
        f"--- stderr (last 2000 bytes) ---\n{result.stderr[-2000:]}\n"
    )


@pytest.mark.serial
def test_context_report_md_written_with_confidence_section(tmp_path: Path) -> None:
    """AC-6 (a)+(b)+(c): file exists, has Confidence heading + at least one row."""
    workdir = tmp_path / "minimal-ts"
    shutil.copytree(_FIXTURE, workdir)

    _gather(workdir)

    ctx_md = workdir / ".codegenie" / "context" / "CONTEXT_REPORT.md"
    assert ctx_md.is_file(), f"missing {ctx_md}"

    content = ctx_md.read_text(encoding="utf-8")
    assert "## Confidence" in content, f"no ## Confidence heading in CONTEXT_REPORT.md:\n{content}"
    # ``IndexHealthProbe`` registers SCIP/runtime_trace/semgrep/gitleaks/conventions
    # at import time, so the registry is non-empty for *any* fixture. Every
    # registered check produces a typed ``IndexFreshness`` — at least one row
    # MUST appear.
    has_ok = "[OK]" in content
    has_stale = "[STALE]" in content
    assert has_ok or has_stale, (
        f"CONTEXT_REPORT.md has no [OK]/[STALE] rows under ## Confidence:\n{content}"
    )


@pytest.mark.serial
def test_context_report_md_byte_identical_across_runs(tmp_path: Path) -> None:
    """AC-6 (d): two consecutive gathers produce the same CONTEXT_REPORT.md.

    Determinism is the load-bearing property — Confidence section rows are
    sorted ASCII-lex; ``Fresh.indexed_at`` flows from sibling slices that
    are themselves cached/content-addressed. Across a same-workdir replay
    the bytes match exactly.
    """
    workdir = tmp_path / "minimal-ts"
    shutil.copytree(_FIXTURE, workdir)
    ctx_md = workdir / ".codegenie" / "context" / "CONTEXT_REPORT.md"

    _gather(workdir)
    first_bytes = ctx_md.read_bytes()
    first_sha = hashlib.sha256(first_bytes).hexdigest()

    _gather(workdir)
    second_bytes = ctx_md.read_bytes()
    second_sha = hashlib.sha256(second_bytes).hexdigest()

    assert first_sha == second_sha, (
        "CONTEXT_REPORT.md diverged across two consecutive gathers — "
        "renderer is not deterministic.\n"
        f"--- first (len={len(first_bytes)}) ---\n{first_bytes.decode('utf-8')}\n"
        f"--- second (len={len(second_bytes)}) ---\n{second_bytes.decode('utf-8')}\n"
    )
