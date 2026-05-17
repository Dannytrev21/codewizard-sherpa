"""``CveProbe`` — Layer C CVE scanner (``grype``) — S5-04.

Runs ``grype sbom:<path-to-syft-sbom.json> -o json`` against the SBOM
:class:`~codegenie.probes.layer_c.sbom.SbomProbe` wrote and normalizes
the output into the ``cve`` slice (``localv2.md §5.3 C3``). The outcome
is a typed :data:`~codegenie.probes._shared.scanner_outcome.ScannerOutcome`
sum (S5-01) so sibling consumers can pattern-match exhaustively.

Module layout (split for the 200-LOC budget per the story AC):

- :mod:`._cve_models` — Pydantic models over grype's JSON +
  ``ScannerAttempt`` tagged-union input to the classifier.
- :mod:`._cve_aggregation` — pure helpers that fold grype output into
  the slice's ``by_severity`` / ``by_source`` / ``top_findings``.
- this module — the probe class, the classifier, and the imperative
  shell (subprocess invocation + file writes).

Discipline (mirrors :mod:`~codegenie.probes.layer_c.sbom`):

- ``requires = ["sbom"]`` is a class attribute (metadata-only;
  02-ADR-0003 Option D). Correctness flows from the defensive
  :func:`read_raw_slices` read, not coordinator dispatch.
- Sibling slices via :func:`read_raw_slices` on :func:`raw_dir`; AST
  audit forbids open-coded disk-IO.
- Subprocess via :func:`run_external_cli` (not ``run_allowlisted``).
- :class:`GrypeJsonSchema` is ``extra="allow"`` (forward-compat); the
  emitted slice schema is strict (``additionalProperties: false``).
- Two files: ``<raw_dir>/cve.json`` (typed slice) +
  ``<raw_dir>/grype-cves.json`` (raw grype bytes).
- When the upstream sbom slice's outcome is ``ran`` but the raw
  ``syft-sbom.json`` is missing on disk, emit
  ``ScannerFailed(reason="sbom_artifact_missing", ...)`` rather than
  silently invoke ``grype`` against a non-existent file.

Source: ``docs/phases/02-context-gather-layers-b-g/stories/\
S5-04-sbom-cve-probes.md``.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Final, Literal

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
from codegenie.probes.layer_b.index_health import read_raw_slices
from codegenie.probes.layer_c._cve_aggregation import (
    _TOP_FINDINGS_N,
    _by_severity,
    _by_source,
    _empty_buckets,
    _top_findings,
)
from codegenie.probes.layer_c._cve_models import (
    GrypeJsonSchema,
    ScannerAttempt,
    _ProcessExited,
    _SbomArtifactMissing,
    _ToolMissing,
)
from codegenie.probes.registry import register_probe
from codegenie.types.identifiers import IndexName, ProbeId

__all__ = ["CveProbe", "GrypeJsonSchema", "_TOP_FINDINGS_N", "_top_findings"]

_PROBE_ID: Final[ProbeId] = ProbeId("cve")
_GRYPE_TIMEOUT_S: Final[int] = 30
_SLICE_FILENAME: Final[str] = "cve.json"
_RAW_TOOL_FILENAME: Final[str] = "grype-cves.json"


def _stderr_tail(b: bytes) -> str:
    return b[-STDERR_TAIL_CAP_BYTES:].decode("utf-8", errors="replace")


def _classify_grype_outcome(attempt: ScannerAttempt) -> ScannerOutcome:
    """Pure, total classifier over :data:`ScannerAttempt`. Never raises."""
    match attempt:
        case _ToolMissing():
            return ScannerSkipped(reason="tool_missing")
        case _SbomArtifactMissing(expected_path=path):
            return ScannerFailed(
                exit_code=-1,
                stderr_tail=f"sbom artifact missing at {path}",
                reason="sbom_artifact_missing",
            )
        case _ProcessExited(exit_code=exit_code, stdout=stdout, stderr_tail=tail):
            if exit_code != 0:
                return ScannerFailed(exit_code=exit_code, stderr_tail=tail)
            try:
                GrypeJsonSchema.model_validate_json(stdout)
            except Exception:  # noqa: BLE001
                return ScannerFailed(exit_code=exit_code, stderr_tail=tail, reason="invalid_json")
            return ScannerRan(findings=[])


def _upstream_sbom_artifact(slices: dict[IndexName, dict[str, object]]) -> tuple[str, str] | None:
    """Resolve upstream ``artifact_uri`` + scanned image digest, or ``None``."""
    payload = slices.get(IndexName("sbom"))
    if payload is None:
        return None
    outcome = payload.get("outcome")
    if not isinstance(outcome, dict) or outcome.get("kind") != "ran":
        return None
    artifact_uri = payload.get("artifact_uri")
    digest = payload.get("built_image_digest")
    if not isinstance(artifact_uri, str) or not isinstance(digest, str):
        return None
    return artifact_uri, digest


def _build_slice(
    *,
    artifact_uri: str | None,
    scanned_image_digest: str | None,
    outcome: ScannerOutcome,
    confidence: Literal["high", "medium", "low", "unavailable"],
    parsed: GrypeJsonSchema | None = None,
) -> dict[str, Any]:
    """Build the cve slice dict — branches on whether *parsed* is populated."""
    if parsed is None:
        return {
            "artifact_uri": artifact_uri,
            "scanner": "grype",
            "scanned_image_digest": scanned_image_digest,
            "total": 0,
            "by_severity": _empty_buckets(),
            "by_source": {},
            "top_findings": [],
            "outcome": outcome.model_dump(mode="json"),
            "confidence": confidence,
        }
    return {
        "artifact_uri": artifact_uri,
        "scanner": "grype",
        "scanned_image_digest": scanned_image_digest,
        "total": len(parsed.matches),
        "by_severity": _by_severity(parsed),
        "by_source": _by_source(parsed),
        "top_findings": _top_findings(parsed),
        "outcome": outcome.model_dump(mode="json"),
        "confidence": confidence,
    }


def _write_files(repo_root: Path, slice_dict: dict[str, Any], tool_bytes: bytes) -> list[Path]:
    rd = raw_dir(repo_root)
    rd.mkdir(parents=True, exist_ok=True)
    slice_path = rd / _SLICE_FILENAME
    slice_path.write_text(json.dumps(slice_dict, sort_keys=True))
    out = [slice_path]
    if tool_bytes:
        tool_path = rd / _RAW_TOOL_FILENAME
        tool_path.write_bytes(tool_bytes)
        out.append(tool_path)
    return out


@register_probe(heaviness="medium", runs_last=False)
class CveProbe(Probe):
    """Layer C — CVE scanner over the syft SBOM (``grype``).

    ``requires`` is metadata-only (02-ADR-0003 Option D).
    """

    name: str = "cve"
    version: str = "0.1.0"
    layer = "C"
    tier = "base"
    applies_to_tasks: list[str] = ["*"]
    applies_to_languages: list[str] = ["*"]
    requires: list[str] = ["sbom"]
    declared_inputs: list[str] = ["image-digest:<resolved>"]
    timeout_seconds: int = 60

    async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput:
        t0 = time.perf_counter()
        upstream = _upstream_sbom_artifact(read_raw_slices(raw_dir(repo.root)))
        if upstream is None:
            slice_dict = _build_slice(
                artifact_uri=None,
                scanned_image_digest=None,
                outcome=ScannerSkipped(reason="upstream_unavailable"),
                confidence="unavailable",
            )
            return self._envelope(slice_dict, _write_files(repo.root, slice_dict, b""), "low", t0)
        sbom_path_str, scanned_digest = upstream
        sbom_path = Path(sbom_path_str)
        if not sbom_path.is_file() or sbom_path.stat().st_size == 0:
            outcome = _classify_grype_outcome(_SbomArtifactMissing(expected_path=str(sbom_path)))
            slice_dict = _build_slice(
                artifact_uri=None,
                scanned_image_digest=scanned_digest,
                outcome=outcome,
                confidence="low",
            )
            return self._envelope(slice_dict, _write_files(repo.root, slice_dict, b""), "low", t0)

        attempt = await self._attempt(sbom_path, repo.root)
        outcome = _classify_grype_outcome(attempt)
        tool_bytes = attempt.stdout if isinstance(attempt, _ProcessExited) else b""

        if isinstance(outcome, ScannerRan):
            parsed = GrypeJsonSchema.model_validate_json(tool_bytes)
            slice_dict = _build_slice(
                artifact_uri=str(raw_dir(repo.root) / _RAW_TOOL_FILENAME),
                scanned_image_digest=scanned_digest,
                outcome=outcome,
                confidence="high",
                parsed=parsed,
            )
            return self._envelope(
                slice_dict, _write_files(repo.root, slice_dict, tool_bytes), "high", t0
            )

        slice_dict = _build_slice(
            artifact_uri=None,
            scanned_image_digest=scanned_digest,
            outcome=outcome,
            confidence="low",
        )
        return self._envelope(slice_dict, _write_files(repo.root, slice_dict, b""), "low", t0)

    @staticmethod
    async def _attempt(sbom_path: Path, cwd: Path) -> ScannerAttempt:
        try:
            result: ProcessResult = await run_external_cli(
                _PROBE_ID,
                ["grype", f"sbom:{sbom_path}", "-o", "json"],
                cwd=cwd,
                timeout_s=float(_GRYPE_TIMEOUT_S),
            )
        except ToolMissingError:
            return _ToolMissing()
        except ProbeTimeoutError:
            return _ProcessExited(exit_code=124, stdout=b"", stderr_tail="grype.timeout")
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
            schema_slice={"cve": slice_dict},
            raw_artifacts=raw_artifacts,
            confidence=confidence,
            duration_ms=int((time.perf_counter() - t0) * 1000),
            warnings=[],
            errors=[],
        )
