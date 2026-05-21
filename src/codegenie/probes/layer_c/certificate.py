"""S5-03 — :class:`CertificateProbe` (Layer C marker probe).

Reads the ``runtime_trace`` sibling slice from disk via
:func:`~codegenie.probes.layer_b.index_health.read_raw_slices` and
classifies the captured ``cert_paths_read`` list into one of four
``certificate_source`` buckets.

``requires`` is metadata-only — the Phase 2 coordinator does not
topo-sort by it (02-ADR-0003).
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Literal

from codegenie.output.paths import raw_dir
from codegenie.probes.base import Probe, ProbeContext, ProbeOutput, RepoSnapshot
from codegenie.probes.layer_b.index_health import read_raw_slices
from codegenie.probes.registry import register_probe
from codegenie.types.identifiers import IndexName

__all__ = ["CertificateProbe", "classify_certificate_source"]

CertificateSource = Literal["ca-certificates", "vendored", "absent", "unknown"]
_CA_PATHS = ("/etc/ssl/certs/ca-certificates.crt", "/etc/ssl/certs/")
_VENDORED_PREFIXES = ("/app/vendor/certs/", "/vendor/certs/")


def classify_certificate_source(paths: list[str]) -> CertificateSource:
    if not paths:
        return "absent"
    if any(p.startswith(_CA_PATHS) for p in paths):
        return "ca-certificates"
    if any(p.startswith(_VENDORED_PREFIXES) for p in paths):
        return "vendored"
    return "unknown"


def _read_runtime_trace_slice(repo_root: Path) -> dict[str, object] | None:
    slices = read_raw_slices(raw_dir(repo_root))
    payload = slices.get(IndexName("runtime_trace"))
    return payload


@register_probe(heaviness="light")
class CertificateProbe(Probe):
    """Layer C — certificate marker probe.

    ``requires`` is metadata-only — see 02-ADR-0003.
    """

    name: str = "certificate"
    version: str = "0.1.0"
    layer = "C"
    tier = "base"
    applies_to_tasks: list[str] = ["*"]
    applies_to_languages: list[str] = ["*"]
    requires: list[str] = ["runtime_trace"]
    declared_inputs: list[str] = [".codegenie/context/raw/runtime_trace.json"]
    timeout_seconds: int = 5

    async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput:
        t0 = time.perf_counter()
        payload = _read_runtime_trace_slice(repo.root)
        if payload is None:
            return ProbeOutput(
                schema_slice={
                    "certificate": {
                        "cert_paths_read": [],
                        "certificate_source": "absent",
                        "confidence": "unavailable",
                    }
                },
                raw_artifacts=[],
                confidence="low",
                duration_ms=int((time.perf_counter() - t0) * 1000),
                warnings=["certificate.upstream_runtime_trace_unavailable"],
                errors=[],
            )
        raw_paths = payload.get("cert_paths_read", [])
        paths = [p for p in raw_paths if isinstance(p, str)] if isinstance(raw_paths, list) else []
        source = classify_certificate_source(paths)
        return ProbeOutput(
            schema_slice={
                "certificate": {
                    "cert_paths_read": sorted(paths),
                    "certificate_source": source,
                    "confidence": "high",
                }
            },
            raw_artifacts=[],
            confidence="high",
            duration_ms=int((time.perf_counter() - t0) * 1000),
            warnings=[],
            errors=[],
        )
