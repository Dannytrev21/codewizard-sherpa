"""S6-07 — Unit tests for :class:`GitleaksProbe`.

Mirrors the layer_g sibling test pattern (S6-06):
``monkeypatch.setattr(<module>, "run_external_cli", _spy)`` rather than
``pytest-subprocess`` (the ``fp`` fixture is NOT in the dev deps).
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from codegenie.errors import ProbeTimeoutError, ToolMissingError
from codegenie.exec import ProcessResult
from codegenie.hashing import content_hash_bytes
from codegenie.probes._shared.scanner_outcome import (
    ScannerFailed,
    ScannerRan,
    ScannerSkipped,
)
from codegenie.probes.layer_g import gitleaks as gl_mod
from codegenie.probes.layer_g.gitleaks import (
    GitleaksFinding,
    GitleaksProbe,
    GitleaksSlice,
    _fingerprint,
    _parse_gitleaks_stdout,
    _redact_raw_bytes,
)
from codegenie.probes.registry import default_registry
from codegenie.types.identifiers import ProbeId

_SEED = "AKIA1234567890ABCDEF"
_EXPECTED_FP = content_hash_bytes(_SEED.encode("utf-8")).removeprefix("blake3:")[:8]
_AWS_FINDING_RAW = {
    "RuleID": "aws-access-token",
    "Description": "AWS Access Token",
    "File": "src/config.ts",
    "StartLine": 1,
    "Secret": _SEED,
}


# ---------------------------------------------------------------------------
# AC-4 + AC-N1: argv pinning via captured spy
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gitleaks_argv_pins_all_hardening_flags(monkeypatch, repo, ctx) -> None:
    """AC-4 + AC-N1. Mutations caught: dropping ``--no-banner`` (ANSI
    banner breaks JSON parse); omitting ``--no-git`` (silently scans
    history); omitting ``--exit-code 0`` (gitleaks exits 1 on findings,
    mis-classified as failure); wrong first positional (binary string
    instead of ``_PROBE_ID``); wrong cwd; wrong ``timeout_s``."""
    captured: dict[str, Any] = {}

    async def _spy(probe_name, argv, *, cwd, timeout_s, **kwargs):
        captured["probe_name"] = probe_name
        captured["argv"] = list(argv)
        captured["cwd"] = cwd
        captured["timeout_s"] = timeout_s
        return ProcessResult(returncode=0, stdout=b"[]", stderr=b"")

    monkeypatch.setattr(gl_mod, "run_external_cli", _spy)
    await GitleaksProbe().run(repo, ctx)

    assert captured["probe_name"] == gl_mod._PROBE_ID
    assert captured["probe_name"] == ProbeId("gitleaks")
    argv = captured["argv"]
    assert argv[0] == "gitleaks"
    assert argv[1] == "detect"
    for flag in (
        "--no-banner",
        "--no-git",
        "--report-format=json",
        "--report-path=-",
        "--exit-code",
        "0",
        "--source",
        str(repo.root),
    ):
        assert flag in argv, f"missing required flag {flag!r}"
    assert captured["cwd"] == repo.root
    assert captured["timeout_s"] == 30.0


# ---------------------------------------------------------------------------
# AC-5 + AC-RP2: fingerprint chokepoint-derived; raw bytes redacted
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_finding_carries_8hex_fingerprint_and_raw_bytes_redacted(
    monkeypatch, repo, ctx
) -> None:
    """AC-5 + AC-RP2. Mutations caught: any ``[:16]`` slice that
    desynchronizes from the redactor marker (B9); raw bytes that retain
    cleartext (RP1 carve-out violation); any cleartext field on the
    Pydantic model."""
    raw_json = json.dumps([_AWS_FINDING_RAW]).encode("utf-8")

    async def _spy(*_a, **_kw):
        return ProcessResult(returncode=0, stdout=raw_json, stderr=b"")

    monkeypatch.setattr(gl_mod, "run_external_cli", _spy)
    output = await GitleaksProbe().run(repo, ctx)
    slice_ = GitleaksSlice.model_validate(output.schema_slice["gitleaks"])

    assert isinstance(slice_.outcome, ScannerRan)
    assert slice_.outcome.findings == []  # closed-set: rich detail is slice-side
    assert slice_.findings_count == 1
    assert len(slice_.findings_detail) == 1
    f = slice_.findings_detail[0]
    assert len(f.match_fingerprint) == 8
    assert all(c in "0123456789abcdef" for c in f.match_fingerprint)
    assert f.match_fingerprint == _EXPECTED_FP
    assert _SEED not in json.dumps(slice_.model_dump(mode="json"))

    # AC-RP2: the on-disk raw-bytes artifact (gitleaks-raw.json) carries
    # the redaction marker and ZERO cleartext bytes.
    raw_paths = [p for p in output.raw_artifacts if p.name == "gitleaks-raw.json"]
    assert len(raw_paths) == 1
    raw_bytes = raw_paths[0].read_bytes()
    assert _SEED.encode("utf-8") not in raw_bytes
    assert f"<REDACTED:fingerprint={_EXPECTED_FP}>".encode() in raw_bytes
    reparsed = json.loads(raw_bytes)
    assert isinstance(reparsed, list)
    assert reparsed[0]["Secret"] == f"<REDACTED:fingerprint={_EXPECTED_FP}>"


@pytest.mark.asyncio
async def test_multiple_distinct_cleartexts_each_get_unique_marker(monkeypatch, repo, ctx) -> None:
    """AC-RP2(b) — multiple findings with distinct cleartexts each get
    their own marker; neither cleartext appears in the persisted bytes."""
    a, b = "AKIAAAAAAAAAAAAAAAAA", "AKIABBBBBBBBBBBBBBBB"
    raw_json = json.dumps(
        [
            {
                "RuleID": "aws-access-token",
                "Description": "x",
                "File": "a.ts",
                "StartLine": 1,
                "Secret": a,
            },
            {
                "RuleID": "aws-access-token",
                "Description": "x",
                "File": "b.ts",
                "StartLine": 1,
                "Secret": b,
            },
        ]
    ).encode("utf-8")

    async def _spy(*_a, **_kw):
        return ProcessResult(returncode=0, stdout=raw_json, stderr=b"")

    monkeypatch.setattr(gl_mod, "run_external_cli", _spy)
    output = await GitleaksProbe().run(repo, ctx)
    raw_bytes = next(p for p in output.raw_artifacts if p.name == "gitleaks-raw.json").read_bytes()
    assert a.encode() not in raw_bytes
    assert b.encode() not in raw_bytes
    fp_a = _fingerprint(a.encode())
    fp_b = _fingerprint(b.encode())
    assert f"<REDACTED:fingerprint={fp_a}>".encode() in raw_bytes
    assert f"<REDACTED:fingerprint={fp_b}>".encode() in raw_bytes


# ---------------------------------------------------------------------------
# AC-T1: timeout → ScannerFailed(124, "gitleaks.timeout")
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_timeout_yields_scanner_failed(monkeypatch, repo, ctx) -> None:
    """AC-T1. Mutation caught: any timeout that escapes past the probe
    boundary breaks coordinator failure isolation."""

    async def _raise(*_a, **_kw):
        raise ProbeTimeoutError("gitleaks timed out")

    monkeypatch.setattr(gl_mod, "run_external_cli", _raise)
    output = await GitleaksProbe().run(repo, ctx)
    slice_ = GitleaksSlice.model_validate(output.schema_slice["gitleaks"])
    assert isinstance(slice_.outcome, ScannerFailed)
    assert slice_.outcome.exit_code == 124
    assert "gitleaks.timeout" in slice_.outcome.stderr_tail
    assert output.confidence == "low"
    # AC-RP1: no raw bytes persisted on the failure path.
    raw_names = {p.name for p in output.raw_artifacts}
    assert "gitleaks-raw.json" not in raw_names


# ---------------------------------------------------------------------------
# AC-EX: exit_code >= 2 → ScannerFailed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_real_crash_exit_2_yields_scanner_failed(monkeypatch, repo, ctx) -> None:
    """AC-EX. Mutation caught: a default-treat-non-zero-as-empty-findings
    convention would silently mask a real scanner crash."""

    async def _spy(*_a, **_kw):
        return ProcessResult(returncode=2, stdout=b"", stderr=b"gitleaks: panic")

    monkeypatch.setattr(gl_mod, "run_external_cli", _spy)
    output = await GitleaksProbe().run(repo, ctx)
    slice_ = GitleaksSlice.model_validate(output.schema_slice["gitleaks"])
    assert isinstance(slice_.outcome, ScannerFailed)
    assert slice_.outcome.exit_code == 2
    assert "panic" in slice_.outcome.stderr_tail
    assert output.confidence == "low"
    assert "gitleaks-raw.json" not in {p.name for p in output.raw_artifacts}


# ---------------------------------------------------------------------------
# AC-12b: malformed JSON (missing required keys) → ScannerFailed("invalid_json")
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_malformed_json_missing_required_keys(monkeypatch, repo, ctx) -> None:
    """AC-12b. Mutation caught: silent KeyError swallow that emits
    ``ScannerRan(findings=[])`` on malformed gitleaks output."""

    async def _spy(*_a, **_kw):
        return ProcessResult(returncode=0, stdout=b'[{"RuleID": "x"}]', stderr=b"")

    monkeypatch.setattr(gl_mod, "run_external_cli", _spy)
    output = await GitleaksProbe().run(repo, ctx)
    slice_ = GitleaksSlice.model_validate(output.schema_slice["gitleaks"])
    assert isinstance(slice_.outcome, ScannerFailed)
    assert slice_.outcome.reason == "invalid_json"
    # AC-RP1: failed-parse path MUST NOT persist the raw bytes (ADR-0005).
    assert "gitleaks-raw.json" not in {p.name for p in output.raw_artifacts}


@pytest.mark.asyncio
async def test_unparseable_json_yields_invalid_json(monkeypatch, repo, ctx) -> None:
    """AC-12b. JSONDecodeError path."""

    async def _spy(*_a, **_kw):
        return ProcessResult(returncode=0, stdout=b"not json at all", stderr=b"")

    monkeypatch.setattr(gl_mod, "run_external_cli", _spy)
    output = await GitleaksProbe().run(repo, ctx)
    slice_ = GitleaksSlice.model_validate(output.schema_slice["gitleaks"])
    assert isinstance(slice_.outcome, ScannerFailed)
    assert slice_.outcome.reason == "invalid_json"


# ---------------------------------------------------------------------------
# tool-missing path → ScannerSkipped
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tool_missing_yields_scanner_skipped(monkeypatch, repo, ctx) -> None:
    """Mirror S6-06 tool-missing. Mutation caught: raise past the probe."""

    async def _raise(*_a, **_kw):
        raise ToolMissingError("gitleaks")

    monkeypatch.setattr(gl_mod, "run_external_cli", _raise)
    output = await GitleaksProbe().run(repo, ctx)
    slice_ = GitleaksSlice.model_validate(output.schema_slice["gitleaks"])
    assert isinstance(slice_.outcome, ScannerSkipped)
    assert slice_.outcome.reason == "tool_missing"
    assert output.confidence == "low"


# ---------------------------------------------------------------------------
# AC-3 + AC-B1: ABC class-attribute pinning (totality)
# ---------------------------------------------------------------------------


def test_gitleaks_pins_all_eight_abc_class_attributes() -> None:
    """AC-3 + AC-B1. Mutation caught: a ``layer = "F"`` typo slips past
    ``mypy --strict``; a ``timeout_seconds = 0.30`` (float) breaks the
    coordinator's ``int`` budget check."""
    p = GitleaksProbe()
    assert p.name == "gitleaks"
    assert p.version == "0.1.0"
    assert p.layer == "G"
    assert p.tier == "base"
    assert p.applies_to_tasks == ["*"]
    assert p.applies_to_languages == ["*"]
    assert p.requires == []
    # Story prescription was ``["**/*"]``; kernel's input-snapshot
    # computer raises ``IsADirectoryError`` on bare ``**/*`` (S6-06
    # attempt-log lesson #1) so we enumerate file globs explicitly.
    assert p.declared_inputs and all(g.startswith("**/") for g in p.declared_inputs)
    assert "**/*" not in p.declared_inputs
    assert p.timeout_seconds == 30


# ---------------------------------------------------------------------------
# AC-R1: registry membership carries heaviness + runs_last only
# ---------------------------------------------------------------------------


def test_gitleaks_registry_entry_carries_heaviness_only() -> None:
    """AC-R1. Mutation caught: dropping the decorator silently loses
    dispatch; flipping ``runs_last`` re-orders the coordinator; an
    accidental ``requires=`` decorator kwarg would fail at import (the
    kernel accepts only ``heaviness`` + ``runs_last`` per 02-ADR-0003
    Option D)."""
    entries = [e for e in default_registry.sorted_for_dispatch() if e.cls is GitleaksProbe]
    assert len(entries) == 1
    entry = entries[0]
    assert entry.heaviness == "medium"
    assert entry.runs_last is False
    fields = {f.name for f in entry.__dataclass_fields__.values()}  # type: ignore[attr-defined]
    assert "requires" not in fields


# ---------------------------------------------------------------------------
# AC-N1: dual-form identity (module name == _PROBE_ID == class name)
# ---------------------------------------------------------------------------


def test_gitleaks_dual_form_identity() -> None:
    """AC-N1. Mutation caught: drift between filename, ``_PROBE_ID``,
    and ``name`` silently breaks either argv-validation or dispatch."""
    assert gl_mod._PROBE_ID == "gitleaks"
    assert GitleaksProbe.name == "gitleaks"
    assert gl_mod.__name__.endswith(".gitleaks")


# ---------------------------------------------------------------------------
# Pure-helper unit tests (functional core)
# ---------------------------------------------------------------------------


def test_fingerprint_uses_chokepoint_helper() -> None:
    """The probe's ``_fingerprint`` MUST equal the chokepoint output
    sliced to 8 hex — any divergence (raw blake3, slice length, salt)
    silently desyncs the probe-side and envelope-side markers."""
    b = b"AKIA1234567890ABCDEF"
    assert _fingerprint(b) == content_hash_bytes(b).removeprefix("blake3:")[:8]
    assert len(_fingerprint(b)) == 8


def test_parse_returns_parallel_tuples() -> None:
    """``_parse_gitleaks_stdout`` returns findings AND the cleartext
    bytes used to compute their fingerprints — the parallel tuples
    must agree element-wise."""
    raw = json.dumps([_AWS_FINDING_RAW]).encode()
    findings, cleartexts = _parse_gitleaks_stdout(raw)
    assert len(findings) == len(cleartexts) == 1
    assert cleartexts[0] == _SEED.encode()
    assert findings[0].match_fingerprint == _fingerprint(cleartexts[0])


def test_redact_raw_bytes_replaces_every_cleartext() -> None:
    raw = b'[{"Secret": "AKIA1234567890ABCDEF"}]'
    findings = (
        GitleaksFinding(
            rule_id="aws",
            file="a.ts",
            line=1,
            description="",
            match_fingerprint=_EXPECTED_FP,
        ),
    )
    cleartexts = (b"AKIA1234567890ABCDEF",)
    out = _redact_raw_bytes(raw, findings, cleartexts)
    assert b"AKIA1234567890ABCDEF" not in out
    assert f"<REDACTED:fingerprint={_EXPECTED_FP}>".encode() in out


def test_empty_stdout_parses_to_no_findings() -> None:
    """gitleaks emits empty stdout when ``--exit-code 0`` is set and
    no leaks are found — the parser must treat that as zero findings,
    not as ``ScannerFailed(invalid_json)``."""
    findings, cleartexts = _parse_gitleaks_stdout(b"")
    assert findings == ()
    assert cleartexts == ()
