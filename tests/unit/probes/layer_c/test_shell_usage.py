"""S5-03 — ShellUsageProbe tests."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from codegenie.output.paths import raw_dir
from codegenie.probes.base import ProbeContext, RepoSnapshot
from codegenie.probes.layer_c.shell_usage import (
    RunCommandEntry,
    ShellUsageProbe,
    StaticShellEvidence,
)
from codegenie.probes.registry import default_registry


def _make_repo(p: Path) -> RepoSnapshot:
    return RepoSnapshot(root=p, git_commit=None, detected_languages={}, config={})


def _make_ctx(p: Path) -> ProbeContext:
    return ProbeContext(
        cache_dir=p / "_c",
        output_dir=p / "_o",
        workspace=p / "_w",
        logger=logging.getLogger("t"),
        config={},
    )


def _write_raw(tmp_path: Path, name: str, payload: dict[str, Any]) -> None:
    rd = raw_dir(tmp_path)
    rd.mkdir(parents=True, exist_ok=True)
    (rd / f"{name}.json").write_text(json.dumps(payload))


async def _run(tmp_path: Path) -> dict[str, Any]:
    return (await ShellUsageProbe().run(_make_repo(tmp_path), _make_ctx(tmp_path))).schema_slice


def test_shell_usage_probe_register_light_with_class_attr_requires() -> None:
    """AC: heaviness='light'; requires is class attr (NOT decorator kwarg)."""
    entries = default_registry.sorted_for_dispatch()
    match = [e for e in entries if e.cls.__name__ == "ShellUsageProbe"]
    assert len(match) == 1
    assert match[0].heaviness == "light"
    assert ShellUsageProbe.requires == ["dockerfile", "runtime_trace"]


def test_static_evidence_models_frozen() -> None:
    e = StaticShellEvidence()
    assert e.model_config.get("frozen") is True
    assert e.model_config.get("extra") == "forbid"
    r = RunCommandEntry(command="x", classification="build_time")
    assert r.classification == "build_time"


def test_shell_usage_static_only_with_classification(tmp_path: Path) -> None:
    """AC: build_time vs runtime classification based on stage."""
    _write_raw(
        tmp_path,
        "dockerfile",
        {
            "dockerfile": {
                "dockerfiles": [
                    {
                        "path": "Dockerfile",
                        "stages": [
                            {
                                "index": 0,
                                "base_image": "alpine",
                                "entrypoint_form": "absent",
                                "cmd_form": "absent",
                            },
                            {
                                "index": 1,
                                "base_image": "alpine",
                                "entrypoint_form": "exec",
                                "cmd_form": "absent",
                            },
                        ],
                        "run_commands": [
                            {"command": "apt-get update", "stage_index": 0},
                            {"command": "/bin/start.sh", "stage_index": 1},
                        ],
                    }
                ]
            }
        },
    )
    _write_raw(
        tmp_path, "runtime_trace", {"shell_invocations": 0, "trace_coverage_confidence": "low"}
    )
    out = asyncio.run(_run(tmp_path))
    static = out["shell_usage"]["static"]
    entries = static["final_stage_run_commands"]
    assert {(e["command"], e["classification"]) for e in entries} == {
        ("apt-get update", "build_time"),
        ("/bin/start.sh", "runtime"),
    }
    assert static["final_stage_entrypoint_form"] == "exec"


def test_shell_usage_dynamic_count_when_runtime_trace_unavailable(tmp_path: Path) -> None:
    """AC: runtime_trace.confidence='unavailable' → dynamic count is None."""
    _write_raw(tmp_path, "dockerfile", {"dockerfile": {"dockerfiles": []}})
    _write_raw(
        tmp_path,
        "runtime_trace",
        {"shell_invocations": 5, "trace_coverage_confidence": "unavailable"},
    )
    out = asyncio.run(_run(tmp_path))
    assert out["shell_usage"]["dynamic_shell_invocation_count"] is None


def test_shell_usage_dynamic_count_present(tmp_path: Path) -> None:
    _write_raw(tmp_path, "dockerfile", {"dockerfile": {"dockerfiles": []}})
    _write_raw(
        tmp_path, "runtime_trace", {"shell_invocations": 3, "trace_coverage_confidence": "high"}
    )
    out = asyncio.run(_run(tmp_path))
    assert out["shell_usage"]["dynamic_shell_invocation_count"] == 3


def test_shell_usage_no_dockerfile_unavailable(tmp_path: Path) -> None:
    """AC-V2 — dockerfile slice absent → confidence='unavailable', no exception."""
    out = asyncio.run(_run(tmp_path))
    assert out["shell_usage"]["confidence"] == "unavailable"
    assert out["shell_usage"]["static"]["final_stage_run_commands"] == []
