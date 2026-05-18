"""``TestCoverageMappingProbe`` — Layer G, medium heaviness (S6-08).

Reads ``coverage/lcov.info`` or ``coverage/coverage-final.json`` if
present and emits a typed ``test_coverage_map`` slice. The raw artifact
Phase-3's ``TestInventoryAdapter.tests_exercising`` projects against
(``production/adrs/0030-graph-aware-context-queries.md``).

Per-line attribution is deliberately out of scope here (Phase 3 adapter
concern); Phase 2 ships the raw evidence only. ``CoverageRecord`` is
closed at three fields (``test_file``, ``source_file``, ``lines_covered``)
— architecturally pinned by ``test_coverage_record_fields_are_frozen``.

No new external CLI is added (file-only readers). The file consumes —
does NOT re-implement:

- :func:`codegenie.parsers._io.open_capped` — ``O_NOFOLLOW`` + fstat
  size cap.
- :func:`codegenie.probes._lcov_scanner.scan_records` — Phase-1 S4-03's
  no-regex prefix-map state machine, extended additively here.
- :func:`codegenie.parsers.safe_json.load` — bounded JSON parser.

Sources:

- ``docs/phases/02-context-gather-layers-b-g/stories/``
  ``S6-08-coverage-mapping-and-freshness-registry.md``
- ``docs/phases/02-context-gather-layers-b-g/phase-arch-design.md`` §5.
- ``docs/localv2.md §5.6 G3``.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict

from codegenie.errors import (
    DepthCapExceeded,
    MalformedJSONError,
    SizeCapExceeded,
    SymlinkRefusedError,
)
from codegenie.parsers import safe_json
from codegenie.probes._lcov_scanner import scan_records
from codegenie.probes._shared.scanner_outcome import (
    ScannerFailed,
    ScannerOutcome,
    ScannerRan,
    ScannerSkipped,
)
from codegenie.probes.base import Probe, ProbeContext, ProbeOutput, RepoSnapshot
from codegenie.probes.registry import register_probe
from codegenie.types.identifiers import ProbeId

__all__ = ["CoverageRecord", "TestCoverageMappingProbe", "TestCoverageSlice"]

_MAX_BYTES: Final[int] = 50 * 1024 * 1024  # Phase-1 lcov cap; alignment, not drift.
_PROBE_ID: Final[ProbeId] = ProbeId("test_coverage_mapping")


class CoverageRecord(BaseModel):
    """Per-source-file coverage evidence. Field set is frozen (AC-21)."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    test_file: str | None
    source_file: str
    lines_covered: tuple[int, ...]


class TestCoverageSlice(BaseModel):
    """Layer-G slice for ``TestCoverageMappingProbe``.

    ``findings_detail`` carries the typed :class:`CoverageRecord`s
    (parallel to ``GitleaksSlice.findings_detail`` / ``SemgrepSlice``
    pattern — ``ScannerOutcome.findings`` carries generic ``Finding``s
    which do not fit the coverage shape; sibling-pattern reuse keeps
    the shared sum type intact without an ADR amendment).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    outcome: ScannerOutcome
    format: Literal["lcov", "istanbul"] | None
    files_seen: int | None
    findings_detail: tuple[CoverageRecord, ...] = ()


def _parse_istanbul(payload: object) -> tuple[CoverageRecord, ...]:
    """Pure projection of Istanbul-format JSON into ``CoverageRecord``s.

    Iterates ``statementMap`` × ``s`` per file to assemble the covered-
    lines set. Any per-file shape mismatch raises ``ValueError`` which
    the caller maps to a ``ScannerFailed`` outcome.
    """
    if not isinstance(payload, dict):
        raise ValueError("istanbul top-level must be an object")
    records: list[CoverageRecord] = []
    for source_file in sorted(payload):
        entry = payload[source_file]
        if not isinstance(entry, dict):
            raise ValueError(f"istanbul entry for {source_file!r} must be an object")
        statement_map = entry.get("statementMap") or {}
        counts = entry.get("s") or {}
        if not isinstance(statement_map, dict) or not isinstance(counts, dict):
            raise ValueError(f"istanbul {source_file!r} statementMap/s must be objects")
        lines: list[int] = []
        for stmt_id in sorted(statement_map, key=lambda k: int(k) if k.isdigit() else 0):
            hits = counts.get(stmt_id, 0)
            try:
                hits_int = int(hits)
            except (TypeError, ValueError):
                continue
            if hits_int <= 0:
                continue
            stmt = statement_map[stmt_id]
            if not isinstance(stmt, dict):
                continue
            start = stmt.get("start")
            if not isinstance(start, dict):
                continue
            line = start.get("line")
            if isinstance(line, int) and not isinstance(line, bool):
                lines.append(line)
        records.append(
            CoverageRecord(
                test_file=None,
                source_file=source_file,
                lines_covered=tuple(lines),
            )
        )
    return tuple(records)


def _build_output(
    outcome: ScannerOutcome,
    *,
    fmt: Literal["lcov", "istanbul"] | None,
    files_seen: int | None,
    findings: tuple[CoverageRecord, ...],
    confidence: Literal["high", "medium", "low"],
    start_ns: int,
) -> ProbeOutput:
    slice_ = TestCoverageSlice(
        outcome=outcome,
        format=fmt,
        files_seen=files_seen,
        findings_detail=findings,
    )
    return ProbeOutput(
        schema_slice={"test_coverage_mapping": slice_.model_dump(mode="json")},
        raw_artifacts=[],
        confidence=confidence,
        duration_ms=max(0, (time.monotonic_ns() - start_ns) // 1_000_000),
        warnings=[],
        errors=[],
    )


@register_probe(heaviness="medium")
class TestCoverageMappingProbe(Probe):
    """Layer G — coverage mapping (the fifth Layer G probe). See module docstring."""

    name: str = "test_coverage_mapping"
    version: str = "0.1.0"
    layer: Literal["G"] = "G"
    tier: Literal["base"] = "base"
    applies_to_tasks: list[str] = ["*"]
    applies_to_languages: list[str] = ["*"]
    requires: list[str] = []
    declared_inputs: list[str] = [
        "coverage/lcov.info",
        "coverage/coverage-final.json",
    ]
    timeout_seconds: int = 30

    async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput:
        start_ns = time.monotonic_ns()
        lcov = repo.root / "coverage" / "lcov.info"
        istanbul = repo.root / "coverage" / "coverage-final.json"
        target: Path | None = lcov if lcov.exists() else (istanbul if istanbul.exists() else None)
        if target is None:
            return _build_output(
                ScannerSkipped(reason="upstream_unavailable"),
                fmt=None,
                files_seen=None,
                findings=(),
                confidence="low",
                start_ns=start_ns,
            )
        fmt: Literal["lcov", "istanbul"] = "lcov" if target.name == "lcov.info" else "istanbul"

        try:
            if fmt == "lcov":
                records = scan_records(target, max_bytes=_MAX_BYTES)
                findings = tuple(
                    CoverageRecord(
                        test_file=r.test_file,
                        source_file=r.source_file,
                        lines_covered=r.lines_covered,
                    )
                    for r in records
                )
            else:
                payload = safe_json.load(target, max_bytes=_MAX_BYTES)
                findings = _parse_istanbul(payload)
        except SizeCapExceeded:
            diagnostic = "oversized"
        except (SymlinkRefusedError, MalformedJSONError, DepthCapExceeded, ValueError) as exc:
            diagnostic = f"parse error: {exc}"
        else:
            files_seen = len({r.source_file for r in findings})
            confidence: Literal["high", "medium", "low"] = "high" if findings else "low"
            return _build_output(
                ScannerRan(findings=[]),
                fmt=fmt,
                files_seen=files_seen,
                findings=findings,
                confidence=confidence,
                start_ns=start_ns,
            )
        return _build_output(
            ScannerFailed(exit_code=0, reason=None, stderr_tail=diagnostic),
            fmt=fmt,
            files_seen=None,
            findings=(),
            confidence="low",
            start_ns=start_ns,
        )
