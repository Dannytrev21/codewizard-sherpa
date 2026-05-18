"""S6-06 — Unit tests for :class:`AstGrepProbe`.

Default error convention: any non-zero exit → ``ScannerFailed`` (no
exit-1 carve-out — ast-grep documents exit 0 as the only success).
NDJSON parser: one JSON object per line on stdout.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import ValidationError

from codegenie.errors import ProbeTimeoutError, ToolMissingError
from codegenie.exec import ProcessResult
from codegenie.probes._shared.scanner_outcome import (
    ScannerFailed,
    ScannerRan,
    ScannerSkipped,
)
from codegenie.probes.layer_g import ast_grep as ag_mod
from codegenie.probes.layer_g.ast_grep import (
    AstGrepFinding,
    AstGrepProbe,
    AstGrepSlice,
    _classify_ast_grep_outcome,
    _ProcessExited,
    _ProcessTimedOut,
    _ToolMissing,
)
from codegenie.probes.registry import default_registry

# ---------------------------------------------------------------------------
# AC-6: argv pinning
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ast_grep_argv_uses_json_stream(monkeypatch, repo, ctx) -> None:
    """AC-6. ``--json=stream`` (NDJSON one-finding-per-line) is
    mandatory — ``--json=compact`` inverts peak memory from O(one) to
    O(all)."""
    captured: dict[str, Any] = {}

    async def _spy(probe_name, argv, *, cwd, timeout_s, **kwargs):
        captured["probe_name"] = probe_name
        captured["argv"] = list(argv)
        captured["cwd"] = cwd
        captured["timeout_s"] = timeout_s
        return ProcessResult(returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr(ag_mod, "run_external_cli", _spy)
    output = await AstGrepProbe().run(repo, ctx)

    assert captured["probe_name"] == ag_mod._PROBE_ID
    assert captured["argv"][0] == "ast-grep"
    assert "scan" in captured["argv"]
    assert "--json=stream" in captured["argv"]
    assert "--json=compact" not in captured["argv"]
    assert captured["cwd"] == repo.root
    assert captured["timeout_s"] == 30.0
    assert output.confidence == "high"


# ---------------------------------------------------------------------------
# AC-11: non-zero exit → ScannerFailed (default convention; no carve-out)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ast_grep_exit_code_1_is_scanner_failed(monkeypatch, repo, ctx) -> None:
    """AC-11. ast-grep has no exit-1 carve-out — exit 1 is a real
    error (rule parse failure, etc.)."""

    async def _spy(*_a, **_kw):
        return ProcessResult(returncode=1, stdout=b"", stderr=b"rule parse error")

    monkeypatch.setattr(ag_mod, "run_external_cli", _spy)
    output = await AstGrepProbe().run(repo, ctx)
    slice_ = AstGrepSlice.model_validate(output.schema_slice["ast_grep"])

    assert isinstance(slice_.outcome, ScannerFailed)
    assert slice_.outcome.exit_code == 1


# ---------------------------------------------------------------------------
# NDJSON parse — happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ast_grep_ndjson_findings_parsed_into_slice(monkeypatch, repo, ctx) -> None:
    """AC-9. Per-scanner rich finding model lives on slice."""
    line_a = json.dumps(
        {"file": "src/a.ts", "range": {"start": {"line": 7}}, "message": "x", "ruleId": "no-eval"}
    )
    line_b = json.dumps(
        {"file": "src/b.ts", "range": {"start": {"line": 9}}, "message": "y", "ruleId": "no-spawn"}
    )
    stdout = (line_a + "\n" + line_b + "\n").encode()

    async def _spy(*_a, **_kw):
        return ProcessResult(returncode=0, stdout=stdout, stderr=b"")

    monkeypatch.setattr(ag_mod, "run_external_cli", _spy)
    output = await AstGrepProbe().run(repo, ctx)
    slice_ = AstGrepSlice.model_validate(output.schema_slice["ast_grep"])

    assert isinstance(slice_.outcome, ScannerRan)
    assert slice_.outcome.findings == []
    assert len(slice_.findings_detail) == 2
    assert slice_.findings_detail[0].file == "src/a.ts"
    assert slice_.findings_detail[0].line == 7
    assert slice_.findings_detail[0].rule_id == "no-eval"


# ---------------------------------------------------------------------------
# AC-12: invalid JSON line → ScannerFailed(reason="invalid_json")
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ast_grep_invalid_json_yields_scanner_failed(monkeypatch, repo, ctx) -> None:
    """AC-12. Any NDJSON line failing the smart constructor produces
    typed failure, not silent swallow."""

    async def _spy(*_a, **_kw):
        return ProcessResult(returncode=0, stdout=b"not json at all", stderr=b"")

    monkeypatch.setattr(ag_mod, "run_external_cli", _spy)
    output = await AstGrepProbe().run(repo, ctx)
    slice_ = AstGrepSlice.model_validate(output.schema_slice["ast_grep"])

    assert isinstance(slice_.outcome, ScannerFailed)
    assert slice_.outcome.reason == "invalid_json"


# ---------------------------------------------------------------------------
# AC-10: tool missing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ast_grep_tool_missing_yields_scanner_skipped(monkeypatch, repo, ctx) -> None:
    async def _raise(*_a, **_kw):
        raise ToolMissingError("ast-grep")

    monkeypatch.setattr(ag_mod, "run_external_cli", _raise)
    output = await AstGrepProbe().run(repo, ctx)
    slice_ = AstGrepSlice.model_validate(output.schema_slice["ast_grep"])

    assert isinstance(slice_.outcome, ScannerSkipped)
    assert slice_.outcome.reason == "tool_missing"
    assert output.confidence == "low"


# ---------------------------------------------------------------------------
# AC-T1: timeout
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ast_grep_timeout_yields_scanner_failed_124(monkeypatch, repo, ctx) -> None:
    async def _timeout(*_a, **_kw):
        raise ProbeTimeoutError("ast-grep exceeded 30s")

    monkeypatch.setattr(ag_mod, "run_external_cli", _timeout)
    output = await AstGrepProbe().run(repo, ctx)
    slice_ = AstGrepSlice.model_validate(output.schema_slice["ast_grep"])

    assert isinstance(slice_.outcome, ScannerFailed)
    assert slice_.outcome.exit_code == 124
    assert slice_.outcome.stderr_tail == "ast_grep.timeout"


# ---------------------------------------------------------------------------
# AC-E1: empty findings
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ast_grep_empty_stdout_yields_scanner_ran(monkeypatch, repo, ctx) -> None:
    async def _spy(*_a, **_kw):
        return ProcessResult(returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr(ag_mod, "run_external_cli", _spy)
    output = await AstGrepProbe().run(repo, ctx)
    slice_ = AstGrepSlice.model_validate(output.schema_slice["ast_grep"])

    assert isinstance(slice_.outcome, ScannerRan)
    assert slice_.findings_detail == []
    assert output.confidence == "high"


# ---------------------------------------------------------------------------
# AC-B1 / AC-N1 / AC-R1: identity + ABC pinning + registry
# ---------------------------------------------------------------------------


def test_ast_grep_abc_class_attributes_pinned() -> None:
    assert AstGrepProbe.name == "ast_grep"
    assert AstGrepProbe.layer == "G"
    assert AstGrepProbe.tier == "base"
    assert AstGrepProbe.applies_to_tasks == ["*"]
    assert AstGrepProbe.applies_to_languages == ["*"]
    assert AstGrepProbe.requires == []
    assert AstGrepProbe.timeout_seconds == 30


def test_ast_grep_dual_form_identity() -> None:
    assert ag_mod._PROBE_ID == "ast_grep"
    assert AstGrepProbe.name == "ast_grep"
    assert ag_mod.__name__.endswith(".ast_grep")


def test_ast_grep_registry_entry_carries_heaviness_only() -> None:
    entries = [e for e in default_registry.sorted_for_dispatch() if e.cls is AstGrepProbe]
    assert len(entries) == 1
    entry = entries[0]
    assert entry.heaviness == "medium"
    assert entry.runs_last is False


# ---------------------------------------------------------------------------
# AC-W1: two-file write split
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ast_grep_writes_slice_and_raw_on_success(monkeypatch, repo, ctx) -> None:
    async def _spy(*_a, **_kw):
        return ProcessResult(returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr(ag_mod, "run_external_cli", _spy)
    output = await AstGrepProbe().run(repo, ctx)
    names = {p.name for p in output.raw_artifacts}
    assert "ast_grep.json" in names
    assert "ast_grep-raw.json" in names


@pytest.mark.asyncio
async def test_ast_grep_does_not_write_raw_on_failure(monkeypatch, repo, ctx) -> None:
    async def _spy(*_a, **_kw):
        return ProcessResult(returncode=1, stdout=b"garbage", stderr=b"err")

    monkeypatch.setattr(ag_mod, "run_external_cli", _spy)
    output = await AstGrepProbe().run(repo, ctx)
    names = {p.name for p in output.raw_artifacts}
    assert "ast_grep.json" in names
    assert "ast_grep-raw.json" not in names


# ---------------------------------------------------------------------------
# Pure classifier
# ---------------------------------------------------------------------------


def test_classify_ast_grep_outcome_tool_missing() -> None:
    outcome, findings = _classify_ast_grep_outcome(_ToolMissing())
    assert isinstance(outcome, ScannerSkipped)
    assert outcome.reason == "tool_missing"
    assert findings == []


def test_classify_ast_grep_outcome_timeout() -> None:
    outcome, _ = _classify_ast_grep_outcome(_ProcessTimedOut())
    assert isinstance(outcome, ScannerFailed)
    assert outcome.exit_code == 124


def test_classify_ast_grep_outcome_exit_zero_no_carve_out() -> None:
    outcome, findings = _classify_ast_grep_outcome(
        _ProcessExited(exit_code=0, stdout=b"", stderr_tail="")
    )
    assert isinstance(outcome, ScannerRan)
    assert findings == []


def test_classify_ast_grep_outcome_exit_one_is_failed() -> None:
    """ast-grep default convention: exit 1 = real error."""
    outcome, _ = _classify_ast_grep_outcome(
        _ProcessExited(exit_code=1, stdout=b"", stderr_tail="err")
    )
    assert isinstance(outcome, ScannerFailed)


def test_ast_grep_finding_is_frozen_extra_forbid() -> None:
    with pytest.raises(ValidationError):
        AstGrepFinding(  # type: ignore[call-arg]
            file="p", line=1, message="m", rule_id="r", extra_field="bad"
        )
