"""S6-06 — Unit tests for :class:`SemgrepProbe`.

Mirrors the ``tests/unit/probes/layer_c/test_sbom.py`` pattern: the
subprocess is mocked via ``monkeypatch.setattr(<module>, "run_external_cli", _spy)``
(repo precedent, 10+ call sites). The wrapper itself is exercised by
``tests/unit/exec/test_run_external_cli.py`` (S1-07's own suite); this
file pins the probe-side contract surface only.
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
from codegenie.probes.layer_g import semgrep as sg_mod
from codegenie.probes.layer_g.semgrep import (
    SemgrepFinding,
    SemgrepProbe,
    SemgrepSlice,
    _classify_semgrep_outcome,
    _ProcessExited,
    _ProcessTimedOut,
    _ToolMissing,
)
from codegenie.probes.registry import default_registry

# ---------------------------------------------------------------------------
# AC-5: argv pinning via captured spy
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_semgrep_argv_includes_metrics_off_and_quiet(monkeypatch, repo, ctx) -> None:
    """AC-5. Mutation: dropping ``--metrics=off`` would let semgrep
    phone home; dropping ``--quiet`` would let stderr breach the 64 MB
    cap. Both flags are pinned by argv capture (not source-substring)."""
    captured: dict[str, Any] = {}

    async def _spy(probe_name, argv, *, cwd, timeout_s, **kwargs):
        captured["probe_name"] = probe_name
        captured["argv"] = list(argv)
        captured["cwd"] = cwd
        captured["timeout_s"] = timeout_s
        return ProcessResult(
            returncode=0,
            stdout=b'{"results": [], "paths": {"scanned": [], "skipped": []}}',
            stderr=b"",
        )

    monkeypatch.setattr(sg_mod, "run_external_cli", _spy)
    output = await SemgrepProbe().run(repo, ctx)

    assert captured["probe_name"] == sg_mod._PROBE_ID  # AC-N1 + AC-T7
    assert captured["argv"][0] == "semgrep"
    assert "--metrics=off" in captured["argv"]
    assert "--quiet" in captured["argv"]
    assert "--json" in captured["argv"]
    assert "--config" in captured["argv"]
    assert captured["cwd"] == repo.root
    assert captured["timeout_s"] == 60.0
    assert output.confidence == "high"


# ---------------------------------------------------------------------------
# AC-15: exit code 1 = findings present (semgrep carve-out)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_semgrep_exit_code_1_is_findings_not_failure(monkeypatch, repo, ctx) -> None:
    """AC-15. Mutation: a default-error convention applied to semgrep
    silently mis-classifies findings-present runs as ScannerFailed."""
    findings_stdout = json.dumps(
        {
            "results": [
                {
                    "check_id": "p/nodejs.eval-detected",
                    "path": "src/loader.ts",
                    "start": {"line": 42},
                    "extra": {"severity": "ERROR", "message": "eval call"},
                }
            ],
            "paths": {"scanned": ["src/loader.ts"], "skipped": []},
        }
    ).encode()

    async def _spy(*_a, **_kw):
        return ProcessResult(returncode=1, stdout=findings_stdout, stderr=b"")

    monkeypatch.setattr(sg_mod, "run_external_cli", _spy)
    output = await SemgrepProbe().run(repo, ctx)
    slice_ = SemgrepSlice.model_validate(output.schema_slice["semgrep"])

    assert isinstance(slice_.outcome, ScannerRan)
    assert slice_.outcome.findings == []  # AC-9: ScannerRan.findings is empty
    assert len(slice_.findings_detail) == 1  # rich shape is slice-side
    assert slice_.findings_detail[0].check_id == "p/nodejs.eval-detected"
    assert slice_.findings_detail[0].line == 42
    assert slice_.findings_detail[0].severity == "error"
    assert output.confidence == "high"


# ---------------------------------------------------------------------------
# AC-15: exit code 2 = real failure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_semgrep_exit_code_2_is_scanner_failed(monkeypatch, repo, ctx) -> None:
    """AC-15. Mutation: treating exit code 2 as findings (parse-then-
    emit-empty) would mask real semgrep config errors."""

    async def _spy(*_a, **_kw):
        return ProcessResult(returncode=2, stdout=b"", stderr=b"Error: invalid rule config")

    monkeypatch.setattr(sg_mod, "run_external_cli", _spy)
    output = await SemgrepProbe().run(repo, ctx)
    slice_ = SemgrepSlice.model_validate(output.schema_slice["semgrep"])

    assert isinstance(slice_.outcome, ScannerFailed)
    assert slice_.outcome.exit_code == 2
    assert "invalid rule config" in slice_.outcome.stderr_tail
    assert output.confidence == "low"


# ---------------------------------------------------------------------------
# AC-12: invalid JSON → ScannerFailed(reason="invalid_json")
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_semgrep_invalid_json_yields_scanner_failed_invalid_json(
    monkeypatch, repo, ctx
) -> None:
    """AC-12. Mutation: silent ``except ValidationError: pass`` swallow
    would emit ScannerRan(findings=[]) for what is actually corrupted
    output."""

    async def _spy(*_a, **_kw):
        return ProcessResult(returncode=0, stdout=b"not json at all", stderr=b"")

    monkeypatch.setattr(sg_mod, "run_external_cli", _spy)
    output = await SemgrepProbe().run(repo, ctx)
    slice_ = SemgrepSlice.model_validate(output.schema_slice["semgrep"])

    assert isinstance(slice_.outcome, ScannerFailed)
    assert slice_.outcome.reason == "invalid_json"
    assert output.confidence == "low"


# ---------------------------------------------------------------------------
# AC-10: tool missing → ScannerSkipped
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_semgrep_tool_missing_yields_scanner_skipped(monkeypatch, repo, ctx) -> None:
    """AC-10. Mutation: a ``raise`` past the probe boundary would break
    coordinator per-probe isolation."""

    async def _raise(*_a, **_kw):
        raise ToolMissingError("semgrep")

    monkeypatch.setattr(sg_mod, "run_external_cli", _raise)
    output = await SemgrepProbe().run(repo, ctx)
    slice_ = SemgrepSlice.model_validate(output.schema_slice["semgrep"])

    assert isinstance(slice_.outcome, ScannerSkipped)
    assert slice_.outcome.reason == "tool_missing"
    assert output.confidence == "low"


# ---------------------------------------------------------------------------
# AC-T1: timeout → ScannerFailed(exit_code=124, stderr_tail="semgrep.timeout")
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_semgrep_timeout_yields_scanner_failed_124(monkeypatch, repo, ctx) -> None:
    """AC-T1. Mutation: any timeout that escapes past the probe
    boundary breaks coordinator isolation (the next probe sees the
    exception)."""

    async def _timeout(*_a, **_kw):
        raise ProbeTimeoutError("semgrep exceeded 60s")

    monkeypatch.setattr(sg_mod, "run_external_cli", _timeout)
    output = await SemgrepProbe().run(repo, ctx)
    slice_ = SemgrepSlice.model_validate(output.schema_slice["semgrep"])

    assert isinstance(slice_.outcome, ScannerFailed)
    assert slice_.outcome.exit_code == 124
    assert slice_.outcome.stderr_tail == "semgrep.timeout"


# ---------------------------------------------------------------------------
# AC-E1: empty findings on exit 0
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_semgrep_empty_findings_yields_scanner_ran_high_confidence(
    monkeypatch, repo, ctx
) -> None:
    """AC-E1. Mutation: returning ScannerSkipped on empty findings
    would erase a real "scanned, found nothing" signal."""
    empty_stdout = json.dumps({"results": [], "paths": {"scanned": [], "skipped": []}}).encode()

    async def _spy(*_a, **_kw):
        return ProcessResult(returncode=0, stdout=empty_stdout, stderr=b"")

    monkeypatch.setattr(sg_mod, "run_external_cli", _spy)
    output = await SemgrepProbe().run(repo, ctx)
    slice_ = SemgrepSlice.model_validate(output.schema_slice["semgrep"])

    assert isinstance(slice_.outcome, ScannerRan)
    assert slice_.findings_detail == []
    assert output.confidence == "high"


# ---------------------------------------------------------------------------
# AC-13: truncation tolerance — tail-start-mid-token → invalid_json
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_semgrep_truncated_tail_starting_mid_token_is_invalid_json(
    monkeypatch, repo, ctx
) -> None:
    """AC-13. Mutation: any probe that raises on cap-exceeded breaks
    the wrapper's tail-truncation contract. Invented
    ``reason="output_too_large"`` is NOT in the closed set (ADR-0006)."""
    truncated_garbage = b'<TRUNC>...}, "extra": {"sev'

    async def _spy(*_a, **_kw):
        return ProcessResult(returncode=0, stdout=truncated_garbage, stderr=b"")

    monkeypatch.setattr(sg_mod, "run_external_cli", _spy)
    output = await SemgrepProbe().run(repo, ctx)
    slice_ = SemgrepSlice.model_validate(output.schema_slice["semgrep"])

    assert isinstance(slice_.outcome, ScannerFailed)
    assert slice_.outcome.reason == "invalid_json"


# ---------------------------------------------------------------------------
# AC-B1: ABC class attributes pinned
# ---------------------------------------------------------------------------


def test_semgrep_abc_class_attributes_pinned() -> None:
    """AC-B1. Mutation: a ``layer = "F"`` typo would slip past mypy
    --strict; this test pins every one of the eight required attrs."""
    assert SemgrepProbe.name == "semgrep"
    assert SemgrepProbe.layer == "G"
    assert SemgrepProbe.tier == "base"
    assert SemgrepProbe.applies_to_tasks == ["*"]
    assert SemgrepProbe.applies_to_languages == ["*"]
    assert SemgrepProbe.requires == []
    assert SemgrepProbe.timeout_seconds == 60
    assert isinstance(SemgrepProbe.declared_inputs, list)
    assert all(isinstance(p, str) for p in SemgrepProbe.declared_inputs)


# ---------------------------------------------------------------------------
# AC-N1: dual-form identity discipline
# ---------------------------------------------------------------------------


def test_semgrep_dual_form_identity() -> None:
    """AC-N1. Mutation: drift between filename, ``_PROBE_ID``, and
    ``name`` silently breaks either argv-validation or kernel dispatch."""
    assert sg_mod._PROBE_ID == "semgrep"  # ProbeId is str-newtype
    assert SemgrepProbe.name == "semgrep"
    assert sg_mod.__name__.endswith(".semgrep")


# ---------------------------------------------------------------------------
# AC-R1: registry-membership smoke
# ---------------------------------------------------------------------------


def test_semgrep_registry_entry_carries_heaviness_only() -> None:
    """AC-R1. Mutation: dropping the decorator silently loses dispatch;
    a ``requires=`` decorator kwarg phantom would fail at import (the
    kernel accepts only ``heaviness`` + ``runs_last`` per 02-ADR-0003
    Option D)."""
    entries = [e for e in default_registry.sorted_for_dispatch() if e.cls is SemgrepProbe]
    assert len(entries) == 1
    entry = entries[0]
    assert entry.heaviness == "medium"
    assert entry.runs_last is False
    fields = {f.name for f in entry.__dataclass_fields__.values()}  # type: ignore[attr-defined]
    assert "requires" not in fields


# ---------------------------------------------------------------------------
# AC-W1: two-file write split
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_semgrep_writes_slice_and_raw_on_success(monkeypatch, repo, ctx) -> None:
    """AC-W1. Mutation: writing the raw file on a failure path would
    persist potentially-secret-containing malformed bytes (ADR-0005)."""
    findings_stdout = b'{"results": [], "paths": {"scanned": [], "skipped": []}}'

    async def _spy(*_a, **_kw):
        return ProcessResult(returncode=0, stdout=findings_stdout, stderr=b"")

    monkeypatch.setattr(sg_mod, "run_external_cli", _spy)
    output = await SemgrepProbe().run(repo, ctx)
    names = {p.name for p in output.raw_artifacts}
    assert "semgrep.json" in names
    assert "semgrep-raw.json" in names  # raw written only on ScannerRan


@pytest.mark.asyncio
async def test_semgrep_does_not_write_raw_on_failure(monkeypatch, repo, ctx) -> None:
    """AC-W1. The malformed raw bytes must NOT be persisted (ADR-0005
    no-plaintext-on-malformed)."""

    async def _spy(*_a, **_kw):
        return ProcessResult(returncode=2, stdout=b"not json", stderr=b"err")

    monkeypatch.setattr(sg_mod, "run_external_cli", _spy)
    output = await SemgrepProbe().run(repo, ctx)
    names = {p.name for p in output.raw_artifacts}
    assert "semgrep.json" in names
    assert "semgrep-raw.json" not in names


# ---------------------------------------------------------------------------
# Pure classifier — direct unit coverage of the totality branches
# ---------------------------------------------------------------------------


def test_classify_semgrep_outcome_tool_missing() -> None:
    outcome, findings, rules, files = _classify_semgrep_outcome(_ToolMissing())
    assert isinstance(outcome, ScannerSkipped)
    assert outcome.reason == "tool_missing"
    assert findings == [] and rules is None and files is None


def test_classify_semgrep_outcome_timeout() -> None:
    outcome, _, _, _ = _classify_semgrep_outcome(_ProcessTimedOut())
    assert isinstance(outcome, ScannerFailed)
    assert outcome.exit_code == 124
    assert outcome.stderr_tail == "semgrep.timeout"


def test_classify_semgrep_outcome_exit_zero_with_findings() -> None:
    stdout = json.dumps(
        {
            "results": [
                {
                    "check_id": "rule/a",
                    "path": "a.ts",
                    "start": {"line": 1},
                    "extra": {"severity": "WARNING", "message": "x"},
                }
            ],
            "paths": {"scanned": ["a.ts"]},
        }
    ).encode()
    outcome, findings, _, files = _classify_semgrep_outcome(
        _ProcessExited(exit_code=0, stdout=stdout, stderr_tail="")
    )
    assert isinstance(outcome, ScannerRan)
    assert len(findings) == 1
    assert findings[0].severity == "warning"
    assert files == 1


def test_classify_semgrep_outcome_exit_one_with_findings_is_ran() -> None:
    stdout = json.dumps({"results": [], "paths": {"scanned": []}}).encode()
    outcome, _, _, _ = _classify_semgrep_outcome(
        _ProcessExited(exit_code=1, stdout=stdout, stderr_tail="")
    )
    assert isinstance(outcome, ScannerRan)


def test_classify_semgrep_outcome_exit_two_is_failed() -> None:
    outcome, _, _, _ = _classify_semgrep_outcome(
        _ProcessExited(exit_code=2, stdout=b"", stderr_tail="err")
    )
    assert isinstance(outcome, ScannerFailed)
    assert outcome.exit_code == 2


def test_classify_semgrep_outcome_invalid_json_is_failed_with_reason() -> None:
    outcome, _, _, _ = _classify_semgrep_outcome(
        _ProcessExited(exit_code=0, stdout=b"{not json", stderr_tail="")
    )
    assert isinstance(outcome, ScannerFailed)
    assert outcome.reason == "invalid_json"


def test_semgrep_finding_is_frozen_extra_forbid() -> None:
    """AC-9. The rich finding shape is frozen + extra='forbid'."""
    with pytest.raises(ValidationError):
        SemgrepFinding(  # type: ignore[call-arg]
            check_id="x",
            path="p",
            line=1,
            severity="error",
            message="m",
            extra_field="bad",
        )
