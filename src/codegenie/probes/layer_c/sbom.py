"""``SbomProbe`` — Layer C SBOM scanner (``syft``) — S5-04.

Runs ``syft <image> -o json --quiet`` against the image
:class:`~codegenie.probes.layer_c.runtime_trace.RuntimeTraceProbe` built
(S5-02) and normalizes the output into the ``sbom`` slice
(``localv2.md §5.3 C2``). The outcome is a typed
:data:`~codegenie.probes._shared.scanner_outcome.ScannerOutcome`
discriminated union (S5-01) so sibling consumers
(:class:`~codegenie.probes.layer_c.cve.CveProbe`, S5-05 freshness check,
S8-01 renderer) can pattern-match exhaustively without re-parsing
scanner stdout.

Load-bearing disciplines:

- **``requires = ["runtime_trace"]`` is a class attribute (metadata-only)**
  per 02-ADR-0003 Option D. Correctness flows from the defensive
  :func:`read_raw_slices` read, NOT from coordinator dispatch ordering.
- **Sibling-slice reads go through the S4-01 kernel** —
  :func:`read_raw_slices` on :func:`raw_dir`. No
  ``open(...)`` / ``json.loads(Path(...).read_text())`` / ``Path.glob``
  appears in this module; an AST audit is the structural enforcement.
- **Subprocess flows through** :func:`~codegenie.exec.run_external_cli`,
  not :func:`~codegenie.exec.run_allowlisted` (Layer C *scanners* are
  benefited by ``bubblewrap --unshare-net``; only ``docker``/``strace``
  in S5-02 use ``run_allowlisted`` directly because the daemon socket /
  ``PTRACE_ATTACH`` capability make wrapping infeasible).
- **Pydantic ``extra`` asymmetry.** :class:`SyftJsonSchema`
  (in :mod:`_sbom_models`) declares ``extra="allow"`` — the forward-
  compat seam against syft's evolving JSON; the emitted slice schema
  (``sbom.schema.json``) declares ``additionalProperties: false`` —
  the backward-compat side our downstream consumers rely on.
- **Two raw files written.** ``<raw_dir>/sbom.json`` is the typed slice
  ``read_raw_slices`` exposes to siblings under ``IndexName("sbom")``;
  ``<raw_dir>/syft-sbom.json`` is the raw syft JSON bytes that
  :class:`~codegenie.probes.layer_c.cve.CveProbe` consumes via the
  grype ``sbom:<path>`` URI scheme. On ``invalid_json`` only
  ``sbom.json`` (carrying the failure outcome) is written; the
  malformed ``syft-sbom.json`` is NOT written and ``artifact_uri`` is
  ``None``.

Sources:

- ``docs/phases/02-context-gather-layers-b-g/stories/S5-04-sbom-cve-probes.md``
- ``docs/phases/02-context-gather-layers-b-g/phase-arch-design.md``
  §"Component design" #5, §"Edge cases" rows 1/2/3/13.
- ``docs/phases/02-context-gather-layers-b-g/ADRs/0001-...md`` —
  ``syft``/``grype`` allowlist.
- ``docs/phases/02-context-gather-layers-b-g/ADRs/0004-image-digest-...md`` —
  declared-input token mechanism.
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
from codegenie.probes.layer_c._sbom_models import (
    ScannerAttempt,
    SyftJsonSchema,
    _ProcessExited,
    _ToolMissing,
)
from codegenie.probes.registry import register_probe
from codegenie.types.identifiers import IndexName, ProbeId

__all__ = ["SbomProbe", "SyftJsonSchema"]

_PROBE_ID: Final[ProbeId] = ProbeId("sbom")
_SYFT_TIMEOUT_S: Final[int] = 30
_IMAGE_REF_PREFIX: Final[str] = "codegenie-sbom:"
_SLICE_FILENAME: Final[str] = "sbom.json"
_RAW_TOOL_FILENAME: Final[str] = "syft-sbom.json"
_OS_PKG_TYPES: Final[frozenset[str]] = frozenset({"apk", "deb", "rpm", "alpm", "portage"})


def _image_ref_for_digest(digest: str) -> str:
    """Short-12 hex tag derived from *digest* — mirrors S5-02's helper."""
    body = digest[len("sha256:") :] if digest.startswith("sha256:") else digest
    return _IMAGE_REF_PREFIX + body[:12]


def _stderr_tail(b: bytes) -> str:
    return b[-STDERR_TAIL_CAP_BYTES:].decode("utf-8", errors="replace")


def _classify_syft_outcome(attempt: ScannerAttempt) -> ScannerOutcome:
    """Pure, total classifier over :data:`ScannerAttempt`. Never raises."""
    match attempt:
        case _ToolMissing():
            return ScannerSkipped(reason="tool_missing")
        case _ProcessExited(exit_code=exit_code, stdout=stdout, stderr_tail=tail):
            if exit_code != 0:
                return ScannerFailed(exit_code=exit_code, stderr_tail=tail)
            try:
                SyftJsonSchema.model_validate_json(stdout)
            except Exception:  # noqa: BLE001 — any parse failure → typed
                return ScannerFailed(exit_code=exit_code, stderr_tail=tail, reason="invalid_json")
            return ScannerRan(findings=[])


def _packages_by_source(parsed: SyftJsonSchema) -> dict[str, int]:
    counts: dict[str, int] = {}
    for a in parsed.artifacts:
        counts[a.type or "unknown"] = counts.get(a.type or "unknown", 0) + 1
    return counts


def _native_npm_count(parsed: SyftJsonSchema) -> int:
    """Count npm packages whose syft metadata flags a native module."""
    count = 0
    for art in parsed.artifacts:
        if art.type != "npm":
            continue
        if art.metadata.get("type") == "native":
            count += 1
            continue
        for loc in art.locations:
            if loc.path.endswith(".node"):
                count += 1
                break
    return count


def _os_classification(parsed: SyftJsonSchema | None) -> dict[str, int]:
    """Conservative Phase-2 classification: every OS package → runtime_required."""
    runtime = (
        sum(1 for a in parsed.artifacts if a.type in _OS_PKG_TYPES) if parsed is not None else 0
    )
    return {"runtime_required": runtime, "build_only": 0, "convenience": 0, "unknown": 0}


def _upstream_image_digest(slices: dict[IndexName, dict[str, object]]) -> str | None:
    """Pull ``built_image_digest`` from the ``runtime_trace`` slice.

    Collapses the four absent-upstream sub-cases (slice missing,
    unparseable, outcome != ran via ``trace_coverage_confidence ==
    unavailable``, digest is ``None``) into a single ``None`` return.
    """
    payload = slices.get(IndexName("runtime_trace"))
    if payload is None:
        return None
    digest = payload.get("built_image_digest")
    if not isinstance(digest, str):
        return None
    if payload.get("trace_coverage_confidence") == "unavailable":
        return None
    return digest


def _build_slice(
    *,
    artifact_uri: str | None,
    built_image_digest: str | None,
    outcome: ScannerOutcome,
    confidence: Literal["high", "medium", "low", "unavailable"],
    parsed: SyftJsonSchema | None = None,
) -> dict[str, Any]:
    if parsed is None:
        return {
            "artifact_uri": artifact_uri,
            "built_image_digest": built_image_digest,
            "package_count": 0,
            "packages_by_source": {},
            "os_packages_classification": _os_classification(None),
            "npm_packages_native_module_count": 0,
            "total_size_bytes": None,
            "outcome": outcome.model_dump(mode="json"),
            "confidence": confidence,
        }
    return {
        "artifact_uri": artifact_uri,
        "built_image_digest": built_image_digest,
        "package_count": len(parsed.artifacts),
        "packages_by_source": _packages_by_source(parsed),
        "os_packages_classification": _os_classification(parsed),
        "npm_packages_native_module_count": _native_npm_count(parsed),
        "total_size_bytes": parsed.source.target.imageSize,
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
class SbomProbe(Probe):
    """Layer C — SBOM scanner over the built image (``syft``).

    ``requires`` is metadata-only (02-ADR-0003 Option D); correctness
    flows from the defensive :func:`read_raw_slices` read.
    """

    name: str = "sbom"
    version: str = "0.1.0"
    layer = "C"
    tier = "base"
    applies_to_tasks: list[str] = ["*"]
    applies_to_languages: list[str] = ["*"]
    requires: list[str] = ["runtime_trace"]
    declared_inputs: list[str] = ["Dockerfile", "image-digest:<resolved>"]
    timeout_seconds: int = 60

    async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput:
        t0 = time.perf_counter()
        built_digest = _upstream_image_digest(read_raw_slices(raw_dir(repo.root)))
        if built_digest is None:
            slice_dict = _build_slice(
                artifact_uri=None,
                built_image_digest=None,
                outcome=ScannerSkipped(reason="upstream_unavailable"),
                confidence="unavailable",
            )
            return self._envelope(slice_dict, _write_files(repo.root, slice_dict, b""), "low", t0)

        attempt = await self._attempt(_image_ref_for_digest(built_digest), repo.root)
        outcome = _classify_syft_outcome(attempt)
        tool_bytes = attempt.stdout if isinstance(attempt, _ProcessExited) else b""

        if isinstance(outcome, ScannerRan):
            slice_dict = _build_slice(
                artifact_uri=str(raw_dir(repo.root) / _RAW_TOOL_FILENAME),
                built_image_digest=built_digest,
                outcome=outcome,
                confidence="high",
                parsed=SyftJsonSchema.model_validate_json(tool_bytes),
            )
            return self._envelope(
                slice_dict, _write_files(repo.root, slice_dict, tool_bytes), "high", t0
            )

        slice_dict = _build_slice(
            artifact_uri=None,
            built_image_digest=built_digest,
            outcome=outcome,
            confidence="low",
        )
        return self._envelope(slice_dict, _write_files(repo.root, slice_dict, b""), "low", t0)

    @staticmethod
    async def _attempt(image_ref: str, cwd: Path) -> ScannerAttempt:
        try:
            result: ProcessResult = await run_external_cli(
                _PROBE_ID,
                ["syft", image_ref, "-o", "json", "--quiet"],
                cwd=cwd,
                timeout_s=float(_SYFT_TIMEOUT_S),
            )
        except ToolMissingError:
            return _ToolMissing()
        except ProbeTimeoutError:
            return _ProcessExited(exit_code=124, stdout=b"", stderr_tail="syft.timeout")
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
            schema_slice={"sbom": slice_dict},
            raw_artifacts=raw_artifacts,
            confidence=confidence,
            duration_ms=int((time.perf_counter() - t0) * 1000),
            warnings=[],
            errors=[],
        )
