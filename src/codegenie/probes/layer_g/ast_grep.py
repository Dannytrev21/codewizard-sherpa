"""AstGrepProbe — Layer G ast-grep structural scanner (S6-06). Default
convention: any non-zero exit = ScannerFailed (no exit-1 carve-out).
NDJSON stdout (--json=stream) one finding per line."""

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

__all__ = ["AstGrepFinding", "AstGrepProbe", "AstGrepSlice"]

_PROBE_ID: Final[ProbeId] = ProbeId("ast_grep")
_TIMEOUT_S: Final[int] = 30
_SLICE_FILENAME: Final[str] = "ast_grep.json"
_RAW_TOOL_FILENAME: Final[str] = "ast_grep-raw.json"
_DEFAULT_CONFIG: Final[str] = "sgconfig.yml"


class AstGrepFinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    file: str
    line: int
    message: str
    rule_id: str | None


class AstGrepSlice(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    outcome: ScannerOutcome
    findings_detail: list[AstGrepFinding]
    rules_run: int | None


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


AstGrepAttempt = _ToolMissing | _ProcessTimedOut | _ProcessExited


def _stderr_tail(b: bytes) -> str:
    return b[-STDERR_TAIL_CAP_BYTES:].decode("utf-8", errors="replace")


def _parse_ast_grep_stdout(stdout: bytes) -> list[AstGrepFinding]:
    """Parse NDJSON; raises on any malformed line."""
    if not stdout.strip():
        return []
    findings: list[AstGrepFinding] = []
    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        record = json.loads(line)
        if not isinstance(record, dict):
            raise ValueError("ast-grep NDJSON line was not an object")
        rng = record.get("range") or {}
        start = rng.get("start") or {}
        findings.append(
            AstGrepFinding(
                file=record["file"],
                line=int(start.get("line", 0)),
                message=record.get("message", ""),
                rule_id=record.get("ruleId") or record.get("rule_id"),
            )
        )
    return findings


def _classify_ast_grep_outcome(
    attempt: AstGrepAttempt,
) -> tuple[ScannerOutcome, list[AstGrepFinding]]:
    """Total over :data:`AstGrepAttempt`; never raises."""
    match attempt:
        case _ToolMissing():
            return ScannerSkipped(reason="tool_missing"), []
        case _ProcessTimedOut():
            return ScannerFailed(exit_code=124, stderr_tail="ast_grep.timeout"), []
        case _ProcessExited(exit_code=ec, stdout=stdout, stderr_tail=tail):
            if ec != 0:
                return ScannerFailed(exit_code=ec, stderr_tail=tail), []
            try:
                findings = _parse_ast_grep_stdout(stdout)
            except (json.JSONDecodeError, ValidationError, KeyError, ValueError):
                return (
                    ScannerFailed(exit_code=ec, stderr_tail=tail, reason="invalid_json"),
                    [],
                )
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
class AstGrepProbe(Probe):
    name: str = "ast_grep"
    version: str = "0.1.0"
    layer = "G"
    tier = "base"
    applies_to_tasks: list[str] = ["*"]
    applies_to_languages: list[str] = ["*"]
    requires: list[str] = []
    declared_inputs: list[str] = ["**/*.ts", "**/*.tsx", "**/*.js", "**/*.jsx", "**/*.py"]
    timeout_seconds: int = _TIMEOUT_S

    async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput:
        t0 = time.perf_counter()
        attempt = await self._attempt(repo.root, ctx.config)
        outcome, findings_detail = _classify_ast_grep_outcome(attempt)
        rules_run = len({f.rule_id for f in findings_detail if f.rule_id}) or None
        slice_dict = AstGrepSlice(
            outcome=outcome, findings_detail=findings_detail, rules_run=rules_run
        ).model_dump(mode="json")
        ran = isinstance(outcome, ScannerRan)
        rb = attempt.stdout if ran and isinstance(attempt, _ProcessExited) else None
        artifacts = _write_files(repo.root, {"ast_grep": slice_dict}, rb)
        confidence: Literal["high", "medium", "low"] = "high" if ran else "low"
        return self._envelope(slice_dict, artifacts, confidence, t0)

    @staticmethod
    async def _attempt(repo_root: Path, config: dict[str, Any]) -> AstGrepAttempt:
        cfg = str(config.get("ast_grep_config", _DEFAULT_CONFIG))
        try:
            result: ProcessResult = await run_external_cli(
                _PROBE_ID,
                ["ast-grep", "scan", "--config", cfg, "--json=stream", str(repo_root)],
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
            schema_slice={"ast_grep": slice_dict},
            raw_artifacts=raw_artifacts,
            confidence=confidence,
            duration_ms=int((time.perf_counter() - t0) * 1000),
            warnings=[],
            errors=[],
        )
