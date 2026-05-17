"""S5-03 — EntrypointProbe tests."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from codegenie.output.paths import raw_dir
from codegenie.probes.base import ProbeContext, RepoSnapshot
from codegenie.probes.layer_c.entrypoint import EntrypointProbe
from codegenie.probes.registry import default_registry


def _make_repo(tmp_path: Path) -> RepoSnapshot:
    return RepoSnapshot(root=tmp_path, git_commit=None, detected_languages={}, config={})


def _make_ctx(tmp_path: Path) -> ProbeContext:
    return ProbeContext(
        cache_dir=tmp_path / "_cache",
        output_dir=tmp_path / "_out",
        workspace=tmp_path / "_ws",
        logger=logging.getLogger("test"),
        config={},
    )


def _write_dockerfile_slice(tmp_path: Path, payload: dict[str, Any]) -> None:
    rd = raw_dir(tmp_path)
    rd.mkdir(parents=True, exist_ok=True)
    (rd / "dockerfile.json").write_text(json.dumps({"dockerfile": payload}))


async def _run(tmp_path: Path) -> dict[str, Any]:
    return (await EntrypointProbe().run(_make_repo(tmp_path), _make_ctx(tmp_path))).schema_slice


def test_entrypoint_probe_register_light() -> None:
    entries = default_registry.sorted_for_dispatch()
    match = [e for e in entries if e.cls.__name__ == "EntrypointProbe"]
    assert len(match) == 1
    assert match[0].heaviness == "light"


def test_entrypoint_probe_requires_class_attr_not_decorator() -> None:
    """AC: EntrypointProbe.requires is class attribute, NOT a decorator kwarg."""
    assert EntrypointProbe.requires == ["dockerfile"]


def test_entrypoint_exec_form(tmp_path: Path) -> None:
    _write_dockerfile_slice(
        tmp_path,
        {
            "dockerfiles": [
                {
                    "path": "Dockerfile",
                    "stages": [
                        {
                            "index": 0,
                            "base_image": "alpine",
                            "entrypoint_form": "exec",
                            "entrypoint_argv": ["sh", "-c", "echo hi"],
                            "entrypoint_command": None,
                        }
                    ],
                }
            ]
        },
    )
    out = asyncio.run(_run(tmp_path))
    ep = out["entrypoint"]["entrypoints"][0]
    assert ep["form"] == "exec"
    assert ep["argv"] == ["sh", "-c", "echo hi"]


def test_entrypoint_shell_form(tmp_path: Path) -> None:
    _write_dockerfile_slice(
        tmp_path,
        {
            "dockerfiles": [
                {
                    "path": "Dockerfile",
                    "stages": [
                        {
                            "index": 0,
                            "base_image": "alpine",
                            "entrypoint_form": "shell",
                            "entrypoint_argv": [],
                            "entrypoint_command": "echo hi",
                        }
                    ],
                }
            ]
        },
    )
    out = asyncio.run(_run(tmp_path))
    ep = out["entrypoint"]["entrypoints"][0]
    assert ep["form"] == "shell"
    assert ep["command"] == "echo hi"


def test_entrypoint_absent_dockerfile_with_no_entry_or_cmd(tmp_path: Path) -> None:
    """Dockerfile present but no ENTRYPOINT and no CMD → form=absent, confidence=low."""
    _write_dockerfile_slice(
        tmp_path,
        {
            "dockerfiles": [
                {
                    "path": "Dockerfile",
                    "stages": [
                        {
                            "index": 0,
                            "base_image": "alpine",
                            "entrypoint_form": "absent",
                            "cmd_form": "absent",
                            "entrypoint_argv": [],
                            "entrypoint_command": None,
                        }
                    ],
                }
            ]
        },
    )
    out = asyncio.run(_run(tmp_path))
    assert out["entrypoint"]["entrypoints"][0]["form"] == "absent"
    assert out["entrypoint"]["confidence"] == "low"


def test_entrypoint_marker_absent_no_dockerfile_slice(tmp_path: Path) -> None:
    """AC-V2 — upstream dockerfile slice absent → confidence=unavailable, no exception."""
    out = asyncio.run(_run(tmp_path))
    assert out["entrypoint"]["confidence"] == "unavailable"
    assert out["entrypoint"]["entrypoints"] == []


def test_entrypoint_does_not_raise_when_raw_dir_missing(tmp_path: Path) -> None:
    """AC-V2 stronger — raw/ dir does not exist; run must not raise."""
    # No raw dir created at all; the helper should return empty dict.
    out = asyncio.run(_run(tmp_path))
    assert out["entrypoint"]["confidence"] == "unavailable"
