"""Integration test — ``AstGrepProbe`` against the real ``ast-grep`` binary.

The S6-06 unit tests mock ``run_external_cli``; this one exercises the real
binary end to end: org-config resolution → ``ast-grep scan`` → NDJSON parse →
``ScannerRan`` with findings. It is the test that would have caught the
pre-2026-05-21 defect, where the probe scanned with a repo-relative
``sgconfig.yml`` that never existed and reported ``ScannerFailed`` (exit 6).

Skips loudly when ``ast-grep`` is absent (mirrors the scip-typescript
skip-loudly precedent) — it never silently passes.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

import pytest

from codegenie.probes._shared.scanner_outcome import ScannerRan
from codegenie.probes.base import ProbeContext, RepoSnapshot
from codegenie.probes.layer_g.ast_grep import AstGrepProbe, AstGrepSlice

pytestmark = pytest.mark.skipif(
    shutil.which("ast-grep") is None,
    reason="ast-grep not on PATH — install it (e.g. `brew install ast-grep`) to run this",
)


def _write_org_rules(root: Path) -> Path:
    """Write a real ast-grep project (``sgconfig.yml`` + one rule) under
    ``root``; return the ``sgconfig.yml`` path."""
    (root / "rules").mkdir(parents=True)
    (root / "rules" / "no-eval.yml").write_text(
        "id: no-eval\nlanguage: javascript\nrule:\n  pattern: eval($A)\nmessage: avoid eval\n",
        encoding="utf-8",
    )
    sgconfig = root / "sgconfig.yml"
    sgconfig.write_text("ruleDirs:\n  - rules\n", encoding="utf-8")
    return sgconfig


async def test_ast_grep_real_binary_scans_and_reports_finding(tmp_path: Path) -> None:
    sgconfig = _write_org_rules(tmp_path / "org-rules")

    repo_root = tmp_path / "repo"
    (repo_root / "src").mkdir(parents=True)
    (repo_root / "src" / "a.js").write_text("const x = 1;\neval(x);\n", encoding="utf-8")

    repo = RepoSnapshot(
        root=repo_root,
        git_commit=None,
        detected_languages={"javascript": 100},
        config={},
    )
    ctx = ProbeContext(
        cache_dir=tmp_path / "cache",
        output_dir=tmp_path / "out",
        workspace=tmp_path / "ws",
        logger=logging.getLogger("ast_grep_integration"),
        config={"ast_grep_config": str(sgconfig)},
    )

    output = await AstGrepProbe().run(repo, ctx)
    slice_ = AstGrepSlice.model_validate(output.schema_slice["ast_grep"])

    assert isinstance(slice_.outcome, ScannerRan), (
        f"expected ScannerRan against the real binary, got {slice_.outcome!r}"
    )
    assert len(slice_.findings_detail) == 1
    finding = slice_.findings_detail[0]
    assert finding.rule_id == "no-eval"
    assert finding.file.endswith("a.js")
    assert finding.line == 1  # ast-grep lines are 0-indexed; `eval` is line 2
    assert output.confidence == "high"
