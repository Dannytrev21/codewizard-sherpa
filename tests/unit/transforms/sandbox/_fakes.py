"""Test-side fakes shared across S4-02 unit tests.

Production-side test helpers are a smell (per the S4-02 validator note);
this module lives under ``tests/`` so the production import closure stays
clean.
"""

from __future__ import annotations

import pathlib
from typing import Any

from codegenie.exec import ProcessResult
from codegenie.transforms._forward import SandboxedPath
from codegenie.transforms.sandbox_jail import (
    DenyAll,
    JailedSubprocessSpec,
    NpmEnv,
)


def make_process_result(
    *,
    returncode: int = 0,
    stdout: bytes = b"",
    stderr: bytes = b"",
) -> ProcessResult:
    """Build a frozen :class:`ProcessResult` for chokepoint mocks."""
    return ProcessResult(returncode=returncode, stdout=stdout, stderr=stderr)


def make_spec(tmp_path: pathlib.Path, **overrides: Any) -> JailedSubprocessSpec:
    """Minimum-valid spec rooted at *tmp_path*; override fields per-test."""
    base: dict[str, Any] = dict(
        cmd=("/bin/echo", "hi"),
        cwd=SandboxedPath(absolute=tmp_path),
        env=NpmEnv(),
        network=DenyAll(),
        time_budget_s=5.0,
        memory_mib=128,
        pids_max=64,
    )
    base.update(overrides)
    return JailedSubprocessSpec(**base)
