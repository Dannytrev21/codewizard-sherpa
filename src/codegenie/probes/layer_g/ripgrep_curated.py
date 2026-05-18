"""RipgrepCuratedProbe — Layer G ripgrep curated-pattern scanner (S6-06).
Carve-out: exit 0 + exit 1 = parse (rg emits 1 on no-matches); exit ≥ 2 =
real error. Pattern set is closed — adding patterns is a code + test change."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from codegenie.errors import ProbeTimeoutError, ToolMissingError
from codegenie.exec import ProcessResult, run_external_cli
from codegenie.output.paths import raw_dir
from codegenie.probes._shared.scanner_outcome import (
    STDERR_TAIL_CAP_BYTES,
    ScannerFailed,
    ScannerOutcome,
    ScannerRan,
    ScannerSkipped,
)
from codegenie.probes.base import Probe, ProbeContext, ProbeOutput, RepoSnapshot
from codegenie.probes.registry import register_probe
from codegenie.types.identifiers import ProbeId

__all__ = ["RipgrepCuratedProbe", "RipgrepCuratedSlice", "RipgrepFinding"]

_PROBE_ID: Final[ProbeId] = ProbeId("ripgrep_curated")
_TIMEOUT_S: Final[int] = 30
_SLICE_FILENAME: Final[str] = "ripgrep_curated.json"
_RAW_TOOL_FILENAME: Final[str] = "ripgrep_curated-raw.json"
# fmt: off
_CURATED_PATTERNS: Final[tuple[str, ...]] = (
    "/bin/", "/usr/bin/", "/sbin/",
    r"exec\(", r"spawn\(", r"execSync\(",
    r"process\.platform", r"os\.platform\(",
    "LD_PRELOAD", "LD_LIBRARY_PATH",
)
_PATTERN_ARGS: Final[tuple[str, ...]] = tuple(a for p in _CURATED_PATTERNS for a in ("-e", p))
_DECLARED_INPUTS: Final[list[str]] = [
    "**/*.ts", "**/*.tsx", "**/*.js", "**/*.jsx", "**/*.mjs", "**/*.cjs",
    "**/*.py", "**/*.go", "**/*.rs", "**/*.rb", "**/*.sh", "**/*.bash",
    "**/*.yml", "**/*.yaml", "**/*.json", "**/*.toml", "**/Dockerfile",
]
# fmt: on


class RipgrepFinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    pattern: str
    file: str
    line: int
    snippet: str


class RipgrepCuratedSlice(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    outcome: ScannerOutcome
    findings_detail: list[RipgrepFinding]
    patterns_matched: int | None


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


RipgrepAttempt = _ToolMissing | _ProcessTimedOut | _ProcessExited


def _stderr_tail(b: bytes) -> str:
    return b[-STDERR_TAIL_CAP_BYTES:].decode("utf-8", errors="replace")


def _match_pattern(submatches: list[dict[str, Any]]) -> str:
    if not submatches or not isinstance(submatches[0], dict):
        return ""
    m = submatches[0].get("match")
    return str(m.get("text", "") if isinstance(m, dict) else (m or ""))


def _parse_ripgrep_stdout(stdout: bytes) -> list[RipgrepFinding]:
    """Parse rg --json NDJSON; walk only ``type=match`` lines."""
    findings: list[RipgrepFinding] = []
    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        record = json.loads(line)
        if not isinstance(record, dict) or record.get("type") != "match":
            continue
        data = record.get("data") or {}
        findings.append(
            RipgrepFinding(
                pattern=_match_pattern(data.get("submatches") or []),
                file=str((data.get("path") or {}).get("text", "")),
                line=int(data.get("line_number", 0)),
                snippet=str((data.get("lines") or {}).get("text", "")).rstrip("\n"),
            )
        )
    return findings


def _classify_ripgrep_outcome(
    attempt: RipgrepAttempt,
) -> tuple[ScannerOutcome, list[RipgrepFinding]]:
    """Total over :data:`RipgrepAttempt`; never raises."""
    match attempt:
        case _ToolMissing():
            return ScannerSkipped(reason="tool_missing"), []
        case _ProcessTimedOut():
            return ScannerFailed(exit_code=124, stderr_tail="ripgrep_curated.timeout"), []
        case _ProcessExited(exit_code=ec, stdout=stdout, stderr_tail=tail):
            if ec >= 2:
                return ScannerFailed(exit_code=ec, stderr_tail=tail), []
            try:
                findings = _parse_ripgrep_stdout(stdout)
            except (json.JSONDecodeError, ValidationError, KeyError, ValueError):
                return ScannerFailed(exit_code=ec, stderr_tail=tail, reason="invalid_json"), []
            return ScannerRan(findings=[]), findings


def _write_files(
    repo_root: Path, slice_dict: dict[str, Any], tool_bytes: bytes | None
) -> list[Path]:
    rd = raw_dir(repo_root)
    rd.mkdir(parents=True, exist_ok=True)
    slice_path = rd / _SLICE_FILENAME
    slice_path.write_text(json.dumps(slice_dict, sort_keys=True))
    out = [slice_path]
    if tool_bytes is not None:
        tool_path = rd / _RAW_TOOL_FILENAME
        tool_path.write_bytes(tool_bytes)
        out.append(tool_path)
    return out


@register_probe(heaviness="medium", runs_last=False)
class RipgrepCuratedProbe(Probe):
    name: str = "ripgrep_curated"
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
        outcome, fd = _classify_ripgrep_outcome(attempt)
        pm = len({f.pattern for f in fd if f.pattern}) or None
        slice_dict = RipgrepCuratedSlice(
            outcome=outcome, findings_detail=fd, patterns_matched=pm
        ).model_dump(mode="json")
        ran = isinstance(outcome, ScannerRan)
        rb = attempt.stdout if ran and isinstance(attempt, _ProcessExited) else None
        artifacts = _write_files(repo.root, {"ripgrep_curated": slice_dict}, rb)
        confidence: Literal["high", "medium", "low"] = "high" if ran else "low"
        return self._envelope(slice_dict, artifacts, confidence, t0)

    @staticmethod
    async def _attempt(repo_root: Path) -> RipgrepAttempt:
        # fmt: off
        argv: list[str] = [
            "rg", "--json", "--max-count", "100", "--type-not", "lock",
            *_PATTERN_ARGS, str(repo_root),
        ]
        # fmt: on
        try:
            result: ProcessResult = await run_external_cli(
                _PROBE_ID, argv, cwd=repo_root, timeout_s=float(_TIMEOUT_S)
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

    @staticmethod
    def _envelope(
        slice_dict: dict[str, Any],
        raw_artifacts: list[Path],
        confidence: Literal["high", "medium", "low"],
        t0: float,
    ) -> ProbeOutput:
        return ProbeOutput(
            schema_slice={"ripgrep_curated": slice_dict},
            raw_artifacts=raw_artifacts,
            confidence=confidence,
            duration_ms=int((time.perf_counter() - t0) * 1000),
            warnings=[],
            errors=[],
        )
