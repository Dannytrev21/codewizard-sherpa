"""SemgrepProbe — Layer G semgrep scanner (S6-06). Carve-out: exit 0
and exit 1 both = parse stdout (semgrep emits 1 on findings); exit ≥ 2
= real error. Inline by design — phase-arch-design row 7."""

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

__all__ = ["SemgrepFinding", "SemgrepProbe", "SemgrepSlice"]

_PROBE_ID: Final[ProbeId] = ProbeId("semgrep")
_TIMEOUT_S: Final[int] = 60
_SLICE_FILENAME: Final[str] = "semgrep.json"
_RAW_TOOL_FILENAME: Final[str] = "semgrep-raw.json"
_DEFAULT_CONFIG: Final[str] = "p/nodejs"


class SemgrepFinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    check_id: str
    path: str
    line: int
    severity: Literal["info", "warning", "error"]
    message: str


class SemgrepSlice(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    outcome: ScannerOutcome
    findings_detail: list[SemgrepFinding]
    rules_run: int | None
    files_scanned: int | None


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


SemgrepAttempt = _ToolMissing | _ProcessTimedOut | _ProcessExited


def _stderr_tail(b: bytes) -> str:
    return b[-STDERR_TAIL_CAP_BYTES:].decode("utf-8", errors="replace")


def _parse_semgrep_stdout(
    stdout: bytes,
) -> tuple[list[SemgrepFinding], int | None, int | None]:
    data = json.loads(stdout)
    if not isinstance(data, dict) or "results" not in data:
        raise ValueError("semgrep stdout missing 'results' key")
    findings: list[SemgrepFinding] = []
    for r in data["results"]:
        findings.append(
            SemgrepFinding(
                check_id=r["check_id"],
                path=r["path"],
                line=r["start"]["line"],
                severity=r["extra"]["severity"].lower(),
                message=r["extra"]["message"],
            )
        )
    paths = data.get("paths", {})
    files_scanned = len(paths.get("scanned", [])) if isinstance(paths, dict) else None
    rules_run = len({f.check_id for f in findings}) or None
    return findings, files_scanned, rules_run


def _classify_semgrep_outcome(
    attempt: SemgrepAttempt,
) -> tuple[ScannerOutcome, list[SemgrepFinding], int | None, int | None]:
    """Total over :data:`SemgrepAttempt`; never raises."""
    match attempt:
        case _ToolMissing():
            return ScannerSkipped(reason="tool_missing"), [], None, None
        case _ProcessTimedOut():
            return ScannerFailed(exit_code=124, stderr_tail="semgrep.timeout"), [], None, None
        case _ProcessExited(exit_code=ec, stdout=stdout, stderr_tail=tail):
            if ec >= 2:
                return ScannerFailed(exit_code=ec, stderr_tail=tail), [], None, None
            try:
                findings, files_scanned, rules_run = _parse_semgrep_stdout(stdout)
            except (json.JSONDecodeError, ValidationError, KeyError, ValueError):
                return (
                    ScannerFailed(exit_code=ec, stderr_tail=tail, reason="invalid_json"),
                    [],
                    None,
                    None,
                )
            return ScannerRan(findings=[]), findings, rules_run, files_scanned


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
class SemgrepProbe(Probe):
    name: str = "semgrep"
    version: str = "0.1.0"
    layer = "G"
    tier = "base"
    applies_to_tasks: list[str] = ["*"]
    applies_to_languages: list[str] = ["*"]
    requires: list[str] = []
    declared_inputs: list[str] = ["**/*.ts", "**/*.tsx", "**/*.js", "**/*.jsx"]
    timeout_seconds: int = _TIMEOUT_S

    async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput:
        t0 = time.perf_counter()
        attempt = await self._attempt(repo.root, ctx.config)
        outcome, findings_detail, rules_run, files_scanned = _classify_semgrep_outcome(attempt)
        slice_dict = SemgrepSlice(
            outcome=outcome,
            findings_detail=findings_detail,
            rules_run=rules_run,
            files_scanned=files_scanned,
        ).model_dump(mode="json")
        ran = isinstance(outcome, ScannerRan)
        rb = attempt.stdout if ran and isinstance(attempt, _ProcessExited) else None
        artifacts = _write_files(repo.root, {"semgrep": slice_dict}, rb)
        confidence: Literal["high", "medium", "low"] = "high" if ran else "low"
        return self._envelope(slice_dict, artifacts, confidence, t0)

    @staticmethod
    async def _attempt(repo_root: Path, config: dict[str, Any]) -> SemgrepAttempt:
        cfg = str(config.get("semgrep_config", _DEFAULT_CONFIG))
        try:
            result: ProcessResult = await run_external_cli(
                _PROBE_ID,
                ["semgrep", "--config", cfg, "--json", "--metrics=off", "--quiet", str(repo_root)],
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

    @staticmethod
    def _envelope(
        slice_dict: dict[str, Any],
        raw_artifacts: list[Path],
        confidence: Literal["high", "medium", "low"],
        t0: float,
    ) -> ProbeOutput:
        return ProbeOutput(
            schema_slice={"semgrep": slice_dict},
            raw_artifacts=raw_artifacts,
            confidence=confidence,
            duration_ms=int((time.perf_counter() - t0) * 1000),
            warnings=[],
            errors=[],
        )
