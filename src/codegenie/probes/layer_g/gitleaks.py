"""GitleaksProbe — Layer G gitleaks scanner (S6-07).

Carve-out from S6-06 AC-W1: gitleaks' raw stdout JSON carries cleartext
in the ``Secret`` field; the envelope-level redactor (S3-03) does NOT
scrub bytes inside ``raw_artifacts``, so this probe redacts cleartext
in its own raw bytes BEFORE persistence (AC-RP1) — ADR-0010 one rung
earlier. Fingerprints use the Phase-0 ``content_hash_bytes`` chokepoint
and match the S3-01 ``<REDACTED:fingerprint=<8hex>>`` marker format
byte-for-byte. Inline by design — phase-arch-design row 7."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict

from codegenie.errors import ProbeTimeoutError, ToolMissingError
from codegenie.exec import ProcessResult, run_external_cli
from codegenie.hashing import content_hash_bytes
from codegenie.indices.freshness import IndexFreshness
from codegenie.indices.registry import register_index_freshness_check
from codegenie.output.paths import raw_dir
from codegenie.probes._shared.scanner_outcome import (
    STDERR_TAIL_CAP_BYTES,
    ScannerFailed,
    ScannerOutcome,
    ScannerRan,
    ScannerSkipped,
)
from codegenie.probes._shared.version_freshness import compare_versions
from codegenie.probes.base import Probe, ProbeContext, ProbeOutput, RepoSnapshot
from codegenie.probes.registry import register_probe
from codegenie.types.identifiers import IndexName, ProbeId

__all__ = ["GitleaksFinding", "GitleaksProbe", "GitleaksSlice"]


_PROBE_ID: Final[ProbeId] = ProbeId("gitleaks")
_TIMEOUT_S: Final[int] = 30
_SLICE_FILENAME: Final[str] = "gitleaks.json"
_RAW_TOOL_FILENAME: Final[str] = "gitleaks-raw.json"
# Explicit file-glob list — story prescription was ``["**/*"]`` but the
# coordinator's input-snapshot computer ``os.open``s every match and
# raises ``IsADirectoryError`` on bare ``**/*`` (S6-06 attempt-log
# lesson #1). Matches the sibling ``ripgrep_curated`` shape with
# additional secret-hunting targets (markdown / envrc / pem / lock).
# fmt: off
_DECLARED_INPUTS: Final[list[str]] = [
    "**/*.ts", "**/*.tsx", "**/*.js", "**/*.jsx", "**/*.mjs", "**/*.cjs",
    "**/*.py", "**/*.go", "**/*.rs", "**/*.rb", "**/*.java", "**/*.kt",
    "**/*.sh", "**/*.bash", "**/*.zsh",
    "**/*.yml", "**/*.yaml", "**/*.json", "**/*.toml", "**/*.ini",
    "**/*.md", "**/*.txt", "**/*.env", "**/*.envrc",
    "**/Dockerfile", "**/Makefile",
]
# fmt: on
# ``--no-banner`` for deterministic stdout; ``--no-git`` confines the
# scan to the working tree (history is Phase 3+); ``--exit-code 0``
# overrides gitleaks' default exit-1-on-findings so the classifier
# treats findings via parsed JSON, never via exit code.
# fmt: off
_GITLEAKS_ARGV_BASE: Final[tuple[str, ...]] = (
    "gitleaks", "detect", "--no-banner", "--report-format=json",
    "--report-path=-", "--no-git", "--exit-code", "0",
)
# fmt: on


class GitleaksFinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    rule_id: str
    file: str
    line: int
    description: str
    match_fingerprint: str  # 8-hex; NEVER the cleartext.


class GitleaksSlice(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    outcome: ScannerOutcome
    findings_count: int
    findings_detail: list[GitleaksFinding]


# fmt: off
@dataclass(frozen=True)
class _ToolMissing: ...
@dataclass(frozen=True)
class _ProcessTimedOut: ...
@dataclass(frozen=True)
class _ProcessExited:
    exit_code: int
    stdout: bytes
    stderr_tail: str
# fmt: on


GitleaksAttempt = _ToolMissing | _ProcessTimedOut | _ProcessExited


def _fingerprint(b: bytes) -> str:
    """Phase-0 chokepoint → 8 lowercase hex chars (S3-01 AC-13 / AC-14)."""
    return content_hash_bytes(b).removeprefix("blake3:")[:8]


def _stderr_tail(b: bytes) -> str:
    return b[-STDERR_TAIL_CAP_BYTES:].decode("utf-8", errors="replace")


def _parse_gitleaks_stdout(
    stdout: bytes,
) -> tuple[tuple[GitleaksFinding, ...], tuple[bytes, ...]]:
    """Pure parser. Returns parallel tuples of findings and cleartext
    bytes; caller redacts ``stdout`` with the latter then drops the
    reference. Raises on JSON / schema errors → ``invalid_json``."""
    data = json.loads(stdout) if stdout else []
    if not isinstance(data, list):
        raise ValueError("gitleaks stdout top-level not a list")
    findings: list[GitleaksFinding] = []
    cleartexts: list[bytes] = []
    for f in data:
        clear = f["Secret"].encode("utf-8")
        # fmt: off
        findings.append(GitleaksFinding(
            rule_id=f["RuleID"], file=f["File"], line=int(f["StartLine"]),
            description=f.get("Description", ""),
            match_fingerprint=_fingerprint(clear),
        ))
        # fmt: on
        cleartexts.append(clear)
    return tuple(findings), tuple(cleartexts)


def _redact_raw_bytes(
    raw: bytes, findings: tuple[GitleaksFinding, ...], cleartexts: tuple[bytes, ...]
) -> bytes:
    """Pure byte-level substitution. ``cleartexts`` goes out of scope
    when ``run`` returns — no cleartext reference escapes (AC-RP1)."""
    out = raw
    for finding, clear in zip(findings, cleartexts, strict=True):
        marker = f"<REDACTED:fingerprint={finding.match_fingerprint}>".encode()
        out = out.replace(clear, marker)
    return out


def _classify_gitleaks_outcome(
    attempt: GitleaksAttempt,
) -> tuple[ScannerOutcome, list[GitleaksFinding], bytes | None]:
    """Total over :data:`GitleaksAttempt`. Returns outcome, slice-side
    findings, and redacted raw bytes (``None`` on any non-ran path —
    malformed bytes MUST NOT be persisted per ADR-0005)."""
    match attempt:
        case _ToolMissing():
            return ScannerSkipped(reason="tool_missing"), [], None
        case _ProcessTimedOut():
            return ScannerFailed(exit_code=124, stderr_tail="gitleaks.timeout"), [], None
        case _ProcessExited(exit_code=ec, stdout=stdout, stderr_tail=tail):
            if ec >= 2:
                return ScannerFailed(exit_code=ec, stderr_tail=tail), [], None
            try:
                findings, cleartexts = _parse_gitleaks_stdout(stdout)
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                return (
                    ScannerFailed(exit_code=ec, stderr_tail=tail, reason="invalid_json"),
                    [],
                    None,
                )
            redacted = _redact_raw_bytes(stdout, findings, cleartexts)
            # Stable sort on slice-side findings — gitleaks emits in FS
            # traversal order, which differs across CI containers and trips
            # the two-cold-gathers byte-identity adversarial. Redaction is
            # finding-order-independent so this only re-orders the slice.
            ordered = sorted(findings, key=lambda f: (f.file, f.line, f.rule_id))
            return ScannerRan(findings=[]), list(ordered), redacted


def _write_files(
    repo_root: Path, slice_dict: dict[str, Any], redacted_raw: bytes | None
) -> list[Path]:
    rd = raw_dir(repo_root)
    rd.mkdir(parents=True, exist_ok=True)
    slice_path = rd / _SLICE_FILENAME
    slice_path.write_text(json.dumps(slice_dict, sort_keys=True))
    paths = [slice_path]
    if redacted_raw is not None:
        raw_path = rd / _RAW_TOOL_FILENAME
        raw_path.write_bytes(redacted_raw)
        paths.append(raw_path)
    return paths


@register_probe(heaviness="medium", runs_last=False)
class GitleaksProbe(Probe):
    name: str = "gitleaks"
    version: str = "0.1.0"
    layer = "G"
    tier = "base"
    applies_to_tasks: list[str] = ["*"]
    applies_to_languages: list[str] = ["*"]
    requires: list[str] = []
    declared_inputs: list[str] = _DECLARED_INPUTS
    timeout_seconds: int = _TIMEOUT_S

    async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput:
        t0 = time.perf_counter()
        attempt = await self._attempt(repo.root)
        outcome, findings_detail, redacted_raw = _classify_gitleaks_outcome(attempt)
        slice_dict = GitleaksSlice(
            outcome=outcome,
            findings_count=len(findings_detail),
            findings_detail=findings_detail,
        ).model_dump(mode="json")
        artifacts = _write_files(repo.root, {"gitleaks": slice_dict}, redacted_raw)
        ran = isinstance(outcome, ScannerRan)
        confidence: Literal["high", "medium", "low"] = "high" if ran else "low"
        return ProbeOutput(
            schema_slice={"gitleaks": slice_dict},
            raw_artifacts=artifacts,
            confidence=confidence,
            duration_ms=int((time.perf_counter() - t0) * 1000),
            warnings=[],
            errors=[],
        )

    @staticmethod
    async def _attempt(repo_root: Path) -> GitleaksAttempt:
        argv = [*_GITLEAKS_ARGV_BASE, "--source", str(repo_root)]
        try:
            result: ProcessResult = await run_external_cli(
                _PROBE_ID,
                argv,
                cwd=repo_root,
                timeout_s=float(_TIMEOUT_S),
            )
        except ToolMissingError:
            return _ToolMissing()
        except ProbeTimeoutError:
            return _ProcessTimedOut()
        return _ProcessExited(
            exit_code=result.returncode,
            stdout=result.stdout,
            stderr_tail=_stderr_tail(result.stderr),
        )


@register_index_freshness_check(IndexName("gitleaks"))
def _gitleaks_freshness(slice_: dict[str, object], _head: str) -> IndexFreshness:
    """S6-08 — Open/Closed registration in the owning module (not B2)."""
    return compare_versions(slice_, "gitleaks", "rule_pack_version")
