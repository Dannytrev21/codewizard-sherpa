"""S5-03 — :class:`ShellUsageProbe` (Layer C marker probe).

Static-only shell-usage evidence. Reads the ``dockerfile`` and
``runtime_trace`` sibling slices from disk via
:func:`~codegenie.probes.layer_b.index_health.read_raw_slices` (the
S4-01 helper; the frozen :class:`ProbeContext` carries no
sibling-slice attribute).

Emits typed :class:`StaticShellEvidence` (frozen, ``extra=forbid``)
holding the final stage's entrypoint / cmd forms and a list of
:class:`RunCommandEntry` rows classified ``build_time`` vs ``runtime``.
The replacement-catalog flow (``localv2.md`` §5.3 C5) is deferred to
Phase 3+.

``requires`` is metadata-only — the Phase 2 coordinator does not
topo-sort by it (02-ADR-0003).
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from codegenie.output.paths import raw_dir
from codegenie.probes.base import Probe, ProbeContext, ProbeOutput, RepoSnapshot
from codegenie.probes.layer_b.index_health import read_raw_slices
from codegenie.probes.registry import register_probe
from codegenie.types.identifiers import IndexName

__all__ = ["RunCommandEntry", "ShellUsageProbe", "StaticShellEvidence"]


class RunCommandEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    command: str
    classification: Literal["build_time", "runtime"]


class StaticShellEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    final_stage_entrypoint_form: Literal["exec", "shell", "absent", "malformed"] = "absent"
    final_stage_cmd_form: Literal["exec", "shell", "absent", "malformed"] = "absent"
    final_stage_run_commands: list[RunCommandEntry] = Field(default_factory=list)


def _read_slice(repo_root: Path, name: str) -> dict[str, Any] | None:
    slices = read_raw_slices(raw_dir(repo_root))
    payload = slices.get(IndexName(name))
    if payload is None:
        return None
    inner = payload.get(name)
    return inner if isinstance(inner, dict) else payload


def _build_evidence(df_slice: dict[str, Any]) -> StaticShellEvidence:
    dockerfiles = df_slice.get("dockerfiles", [])
    if not dockerfiles:
        return StaticShellEvidence()
    final_df = dockerfiles[0]
    stages = final_df.get("stages", [])
    if not stages:
        return StaticShellEvidence()
    final_stage_idx = len(stages) - 1
    final = stages[final_stage_idx]
    runs = final_df.get("run_commands", [])
    entries = [
        RunCommandEntry(
            command=str(r.get("command", "")),
            classification="runtime" if r.get("stage_index") == final_stage_idx else "build_time",
        )
        for r in runs
    ]
    return StaticShellEvidence(
        final_stage_entrypoint_form=final.get("entrypoint_form", "absent"),
        final_stage_cmd_form=final.get("cmd_form", "absent"),
        final_stage_run_commands=entries,
    )


@register_probe(heaviness="light")
class ShellUsageProbe(Probe):
    """Layer C — static-only shell-usage marker probe.

    ``requires`` is metadata-only — see 02-ADR-0003.
    """

    name: str = "shell_usage"
    version: str = "0.1.0"
    layer = "C"
    tier = "base"
    applies_to_tasks: list[str] = ["*"]
    applies_to_languages: list[str] = ["*"]
    requires: list[str] = ["dockerfile", "runtime_trace"]
    declared_inputs: list[str] = [
        ".codegenie/context/raw/dockerfile.json",
        ".codegenie/context/raw/runtime_trace.json",
    ]
    timeout_seconds: int = 5

    async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput:
        t0 = time.perf_counter()
        df_slice = _read_slice(repo.root, "dockerfile")
        rt_slice = _read_slice(repo.root, "runtime_trace")
        warnings: list[str] = []
        if df_slice is None:
            warnings.append("shell_usage.upstream_dockerfile_unavailable")
            evidence = StaticShellEvidence()
            confidence: Literal["high", "medium", "low"] = "low"
        else:
            evidence = _build_evidence(df_slice)
            confidence = "high"
        dynamic_count: int | None
        if rt_slice is None or rt_slice.get("trace_coverage_confidence") == "unavailable":
            dynamic_count = None
        else:
            raw_count = rt_slice.get("shell_invocations")
            dynamic_count = int(raw_count) if isinstance(raw_count, int) else None
        slice_payload = {
            "shell_usage": {
                "static": evidence.model_dump(mode="json"),
                "dynamic_shell_invocation_count": dynamic_count,
                "confidence": "unavailable" if df_slice is None else confidence,
            }
        }
        return ProbeOutput(
            schema_slice=slice_payload,
            raw_artifacts=[],
            confidence=confidence,
            duration_ms=int((time.perf_counter() - t0) * 1000),
            warnings=warnings,
            errors=[],
        )
