"""S6-06 — Unit tests for :class:`RipgrepCuratedProbe`.

Carve-out: ripgrep exit code 1 = "no matches found" (not an error);
exit ≥ 2 = real error. Mirror of semgrep's exit-1 carve-out but with
opposite semantics — second textbook example of why a shared
``ScannerRunner`` base is wrong.
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
from codegenie.probes.layer_g import ripgrep_curated as rg_mod
from codegenie.probes.layer_g.ripgrep_curated import (
    _CURATED_PATTERNS,
    RipgrepCuratedProbe,
    RipgrepCuratedSlice,
    RipgrepFinding,
    _classify_ripgrep_outcome,
    _ProcessExited,
    _ProcessTimedOut,
    _ToolMissing,
)
from codegenie.probes.registry import default_registry

# ---------------------------------------------------------------------------
# AC-7: argv pinning — every curated pattern present, --type-not lock,
#       --max-count 100, -e prefix on every pattern
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ripgrep_argv_includes_all_curated_patterns_and_flags(monkeypatch, repo, ctx) -> None:
    """AC-7. Mutation: dropping ``-e`` prefix would let rg interpret
    ``/bin/`` as a path; dropping ``--max-count`` would risk the
    64 MB tail-truncation path on hot hits."""
    captured: dict[str, Any] = {}

    async def _spy(probe_name, argv, *, cwd, timeout_s, **kwargs):
        captured["probe_name"] = probe_name
        captured["argv"] = list(argv)
        captured["cwd"] = cwd
        captured["timeout_s"] = timeout_s
        return ProcessResult(returncode=1, stdout=b"", stderr=b"")  # exit 1 = no matches

    monkeypatch.setattr(rg_mod, "run_external_cli", _spy)
    output = await RipgrepCuratedProbe().run(repo, ctx)
    argv = captured["argv"]

    assert captured["probe_name"] == rg_mod._PROBE_ID
    assert argv[0] == "rg"
    assert "--json" in argv
    assert "--max-count" in argv
    assert "100" in argv
    assert "--type-not" in argv
    assert "lock" in argv

    # --type-not lock must come before patterns (rg parses positionally)
    idx_type_not = argv.index("--type-not")
    idx_first_pattern = next(i for i, a in enumerate(argv) if a == "-e" and i > 1)
    assert idx_type_not < idx_first_pattern

    # Every curated pattern is present, each preceded by -e.
    for pattern in _CURATED_PATTERNS:
        assert pattern in argv
        pos = argv.index(pattern)
        assert argv[pos - 1] == "-e", (
            f"pattern {pattern!r} not preceded by '-e' — rg would interpret as path"
        )

    assert captured["cwd"] == repo.root
    assert captured["timeout_s"] == 30.0
    assert output.confidence == "high"


def test_ripgrep_curated_patterns_are_closed_set() -> None:
    """AC-7. The pattern set is closed; adding a pattern is a code +
    test change, not a config option."""
    expected = (
        "/bin/",
        "/usr/bin/",
        "/sbin/",
        r"exec\(",
        r"spawn\(",
        r"execSync\(",
        r"process\.platform",
        r"os\.platform\(",
        "LD_PRELOAD",
        "LD_LIBRARY_PATH",
    )
    assert _CURATED_PATTERNS == expected


# ---------------------------------------------------------------------------
# Ripgrep exit-1 carve-out (no matches found)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ripgrep_exit_code_1_is_no_matches(monkeypatch, repo, ctx) -> None:
    """AC-7 / Notes #7. Mutation: a default-error convention applied
    to ripgrep silently mis-classifies "scanned, found nothing" as
    ScannerFailed."""

    async def _spy(*_a, **_kw):
        return ProcessResult(returncode=1, stdout=b"", stderr=b"")

    monkeypatch.setattr(rg_mod, "run_external_cli", _spy)
    output = await RipgrepCuratedProbe().run(repo, ctx)
    slice_ = RipgrepCuratedSlice.model_validate(output.schema_slice["ripgrep_curated"])

    assert isinstance(slice_.outcome, ScannerRan)
    assert slice_.findings_detail == []
    assert output.confidence == "high"


@pytest.mark.asyncio
async def test_ripgrep_exit_code_2_is_scanner_failed(monkeypatch, repo, ctx) -> None:
    """Mutation: treating exit 2 as findings would mask real rg errors
    (invalid regex, permission denied, etc.)."""

    async def _spy(*_a, **_kw):
        return ProcessResult(returncode=2, stdout=b"", stderr=b"rg: invalid regex")

    monkeypatch.setattr(rg_mod, "run_external_cli", _spy)
    output = await RipgrepCuratedProbe().run(repo, ctx)
    slice_ = RipgrepCuratedSlice.model_validate(output.schema_slice["ripgrep_curated"])

    assert isinstance(slice_.outcome, ScannerFailed)
    assert slice_.outcome.exit_code == 2


# ---------------------------------------------------------------------------
# NDJSON parse — happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ripgrep_parses_match_lines_into_findings(monkeypatch, repo, ctx) -> None:
    """AC-9. Per-scanner rich finding model on slice. Walks only
    ``"type": "match"`` lines; ignores begin/end/summary."""
    begin = json.dumps({"type": "begin", "data": {"path": {"text": "a.ts"}}})
    match = json.dumps(
        {
            "type": "match",
            "data": {
                "path": {"text": "a.ts"},
                "lines": {"text": "  if (exec(cmd)) {\n"},
                "line_number": 7,
                "submatches": [{"match": {"text": "exec("}, "start": 5, "end": 10}],
            },
        }
    )
    summary = json.dumps({"type": "summary", "data": {"elapsed_total": {"secs": 0}}})
    stdout = (begin + "\n" + match + "\n" + summary + "\n").encode()

    async def _spy(*_a, **_kw):
        return ProcessResult(returncode=0, stdout=stdout, stderr=b"")

    monkeypatch.setattr(rg_mod, "run_external_cli", _spy)
    output = await RipgrepCuratedProbe().run(repo, ctx)
    slice_ = RipgrepCuratedSlice.model_validate(output.schema_slice["ripgrep_curated"])

    assert isinstance(slice_.outcome, ScannerRan)
    assert len(slice_.findings_detail) == 1
    assert slice_.findings_detail[0].file == "a.ts"
    assert slice_.findings_detail[0].line == 7
    assert slice_.findings_detail[0].pattern == "exec("


# ---------------------------------------------------------------------------
# AC-12: invalid JSON
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ripgrep_invalid_json_yields_scanner_failed(monkeypatch, repo, ctx) -> None:
    async def _spy(*_a, **_kw):
        return ProcessResult(returncode=0, stdout=b"this is not json at all\n", stderr=b"")

    monkeypatch.setattr(rg_mod, "run_external_cli", _spy)
    output = await RipgrepCuratedProbe().run(repo, ctx)
    slice_ = RipgrepCuratedSlice.model_validate(output.schema_slice["ripgrep_curated"])

    assert isinstance(slice_.outcome, ScannerFailed)
    assert slice_.outcome.reason == "invalid_json"


# ---------------------------------------------------------------------------
# AC-10: tool missing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ripgrep_tool_missing_yields_scanner_skipped(monkeypatch, repo, ctx) -> None:
    async def _raise(*_a, **_kw):
        raise ToolMissingError("rg")

    monkeypatch.setattr(rg_mod, "run_external_cli", _raise)
    output = await RipgrepCuratedProbe().run(repo, ctx)
    slice_ = RipgrepCuratedSlice.model_validate(output.schema_slice["ripgrep_curated"])

    assert isinstance(slice_.outcome, ScannerSkipped)
    assert slice_.outcome.reason == "tool_missing"


# ---------------------------------------------------------------------------
# AC-T1: timeout
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ripgrep_timeout_yields_scanner_failed_124(monkeypatch, repo, ctx) -> None:
    async def _timeout(*_a, **_kw):
        raise ProbeTimeoutError("rg exceeded 30s")

    monkeypatch.setattr(rg_mod, "run_external_cli", _timeout)
    output = await RipgrepCuratedProbe().run(repo, ctx)
    slice_ = RipgrepCuratedSlice.model_validate(output.schema_slice["ripgrep_curated"])

    assert isinstance(slice_.outcome, ScannerFailed)
    assert slice_.outcome.exit_code == 124
    assert slice_.outcome.stderr_tail == "ripgrep_curated.timeout"


# ---------------------------------------------------------------------------
# AC-B1 / AC-N1 / AC-R1: identity + ABC pinning + registry
# ---------------------------------------------------------------------------


def test_ripgrep_abc_class_attributes_pinned() -> None:
    assert RipgrepCuratedProbe.name == "ripgrep_curated"
    assert RipgrepCuratedProbe.layer == "G"
    assert RipgrepCuratedProbe.tier == "base"
    assert RipgrepCuratedProbe.applies_to_tasks == ["*"]
    assert RipgrepCuratedProbe.applies_to_languages == ["*"]
    assert RipgrepCuratedProbe.requires == []
    assert RipgrepCuratedProbe.timeout_seconds == 30


def test_ripgrep_dual_form_identity() -> None:
    assert rg_mod._PROBE_ID == "ripgrep_curated"
    assert RipgrepCuratedProbe.name == "ripgrep_curated"
    assert rg_mod.__name__.endswith(".ripgrep_curated")


def test_ripgrep_registry_entry_carries_heaviness_only() -> None:
    entries = [e for e in default_registry.sorted_for_dispatch() if e.cls is RipgrepCuratedProbe]
    assert len(entries) == 1
    entry = entries[0]
    assert entry.heaviness == "medium"
    assert entry.runs_last is False


# ---------------------------------------------------------------------------
# AC-W1: two-file write split
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ripgrep_writes_slice_and_raw_on_success(monkeypatch, repo, ctx) -> None:
    async def _spy(*_a, **_kw):
        return ProcessResult(returncode=1, stdout=b"", stderr=b"")  # no matches = success

    monkeypatch.setattr(rg_mod, "run_external_cli", _spy)
    output = await RipgrepCuratedProbe().run(repo, ctx)
    names = {p.name for p in output.raw_artifacts}
    assert "ripgrep_curated.json" in names
    assert "ripgrep_curated-raw.json" in names


@pytest.mark.asyncio
async def test_ripgrep_does_not_write_raw_on_failure(monkeypatch, repo, ctx) -> None:
    async def _spy(*_a, **_kw):
        return ProcessResult(returncode=2, stdout=b"garbage", stderr=b"err")

    monkeypatch.setattr(rg_mod, "run_external_cli", _spy)
    output = await RipgrepCuratedProbe().run(repo, ctx)
    names = {p.name for p in output.raw_artifacts}
    assert "ripgrep_curated.json" in names
    assert "ripgrep_curated-raw.json" not in names


# ---------------------------------------------------------------------------
# Pure classifier — direct unit coverage
# ---------------------------------------------------------------------------


def test_classify_ripgrep_outcome_tool_missing() -> None:
    outcome, findings = _classify_ripgrep_outcome(_ToolMissing())
    assert isinstance(outcome, ScannerSkipped)
    assert findings == []


def test_classify_ripgrep_outcome_timeout() -> None:
    outcome, _ = _classify_ripgrep_outcome(_ProcessTimedOut())
    assert isinstance(outcome, ScannerFailed)
    assert outcome.exit_code == 124


def test_classify_ripgrep_outcome_exit_zero_with_matches() -> None:
    line = json.dumps(
        {
            "type": "match",
            "data": {
                "path": {"text": "x.js"},
                "lines": {"text": "exec(\n"},
                "line_number": 1,
                "submatches": [{"match": {"text": "exec("}, "start": 0, "end": 5}],
            },
        }
    ).encode()
    outcome, findings = _classify_ripgrep_outcome(
        _ProcessExited(exit_code=0, stdout=line, stderr_tail="")
    )
    assert isinstance(outcome, ScannerRan)
    assert len(findings) == 1


def test_classify_ripgrep_outcome_exit_one_is_no_matches() -> None:
    """Carve-out: rg exit 1 = success-with-no-matches, NOT failure."""
    outcome, findings = _classify_ripgrep_outcome(
        _ProcessExited(exit_code=1, stdout=b"", stderr_tail="")
    )
    assert isinstance(outcome, ScannerRan)
    assert findings == []


def test_classify_ripgrep_outcome_exit_two_is_failed() -> None:
    outcome, _ = _classify_ripgrep_outcome(
        _ProcessExited(exit_code=2, stdout=b"", stderr_tail="rg: error")
    )
    assert isinstance(outcome, ScannerFailed)
    assert outcome.exit_code == 2


def test_classify_ripgrep_outcome_invalid_json() -> None:
    outcome, _ = _classify_ripgrep_outcome(
        _ProcessExited(exit_code=0, stdout=b"{not valid", stderr_tail="")
    )
    assert isinstance(outcome, ScannerFailed)
    assert outcome.reason == "invalid_json"


def test_ripgrep_finding_is_frozen_extra_forbid() -> None:
    with pytest.raises(ValidationError):
        RipgrepFinding(  # type: ignore[call-arg]
            pattern="x", file="p", line=1, snippet="s", extra_field="bad"
        )
