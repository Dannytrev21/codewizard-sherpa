"""S5-03 — :class:`EntrypointProbe` (Layer C marker probe).

Reads the ``dockerfile`` sibling slice from disk via
:func:`~codegenie.probes.layer_b.index_health.read_raw_slices` and emits
a per-Dockerfile entrypoint classification (``exec`` / ``shell`` /
``absent`` / ``malformed``). All disk IO flows through the S4-01 helper
— no per-probe disk reads; the frozen :class:`ProbeContext` carries no
sibling-slice attribute and inventing one would re-litigate Phase 0
ADR-0007.

``requires`` is metadata-only — the Phase 2 coordinator does not
topo-sort by it (02-ADR-0003). Per-dispatch correctness is ensured by
the absent-upstream fallback (slice missing on disk → confidence
``unavailable``, no exception).
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Literal

from codegenie.output.paths import raw_dir
from codegenie.probes.base import Probe, ProbeContext, ProbeOutput, RepoSnapshot
from codegenie.probes.layer_b.index_health import read_raw_slices
from codegenie.probes.registry import register_probe
from codegenie.types.identifiers import IndexName

__all__ = ["EntrypointProbe"]


def _read_dockerfile_slice(repo_root: Path) -> dict[str, Any] | None:
    """Return the ``dockerfile`` sibling slice or ``None`` if absent."""
    slices = read_raw_slices(raw_dir(repo_root))
    payload = slices.get(IndexName("dockerfile"))
    if payload is None:
        return None
    inner = payload.get("dockerfile")
    return inner if isinstance(inner, dict) else payload


def _summarize(
    slice_payload: dict[str, Any],
) -> tuple[list[dict[str, Any]], Literal["high", "medium", "low"]]:
    dockerfiles = slice_payload.get("dockerfiles", [])
    summaries: list[dict[str, Any]] = []
    confidence: Literal["high", "medium", "low"] = "high"
    for df in dockerfiles:
        stages = df.get("stages", [])
        if not stages:
            continue
        final = stages[-1]
        form = final.get("entrypoint_form", "absent")
        if form == "absent" and final.get("cmd_form", "absent") == "absent":
            confidence = "low"
        summaries.append({
            "path": df.get("path"),
            "form": form,
            "argv": list(final.get("entrypoint_argv", [])),
            "command": final.get("entrypoint_command"),
        })
    return summaries, confidence


@register_probe(heaviness="light")
class EntrypointProbe(Probe):
    """Layer C — entrypoint marker probe.

    ``requires`` is metadata-only — see 02-ADR-0003.
    """

    name: str = "entrypoint"
    version: str = "0.1.0"
    layer = "C"
    tier = "base"
    applies_to_tasks: list[str] = ["*"]
    applies_to_languages: list[str] = ["*"]
    requires: list[str] = ["dockerfile"]
    declared_inputs: list[str] = [".codegenie/context/raw/dockerfile.json"]
    timeout_seconds: int = 5

    async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput:
        t0 = time.perf_counter()
        slice_payload = _read_dockerfile_slice(repo.root)
        if slice_payload is None:
            return ProbeOutput(
                schema_slice={"entrypoint": {"entrypoints": [], "confidence": "unavailable"}},
                raw_artifacts=[],
                confidence="low",
                duration_ms=int((time.perf_counter() - t0) * 1000),
                warnings=["entrypoint.upstream_dockerfile_unavailable"],
                errors=[],
            )
        summaries, conf = _summarize(slice_payload)
        return ProbeOutput(
            schema_slice={"entrypoint": {"entrypoints": summaries, "confidence": conf}},
            raw_artifacts=[],
            confidence=conf,
            duration_ms=int((time.perf_counter() - t0) * 1000),
            warnings=[],
            errors=[],
        )
