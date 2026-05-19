"""AC-11 — macOS-only, nightly-only ``sandbox-exec`` network-policy test.

Two cases:

1. ``RegistryAllowlist({https://registry.npmjs.org})`` + ``curl
   --max-time 5 https://registry.npmjs.org/`` → ``Completed``.
2. Same allowlist + ``curl --max-time 5 https://github.com/`` →
   ``NetworkDenied(host="github.com")``.

Until S4-05 admits ``sandbox-exec`` to ``ALLOWED_BINARIES`` the chokepoint
refuses the spawn — both cases produce ``JailSetupFailed`` on a pre-S4-05
runner. Post-S4-05, the assertions above hold.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

from codegenie.transforms import SandboxedPath
from codegenie.transforms.sandbox.sandbox_exec import SandboxExecAdapter
from codegenie.transforms.sandbox_jail import (
    Completed,
    JailedSubprocessSpec,
    JailSetupFailed,
    NetworkDenied,
    NpmEnv,
    RegistryAllowlist,
)
from codegenie.types.identifiers import RegistryUrl


def _registry_allowlist() -> RegistryAllowlist:
    return RegistryAllowlist(hosts=frozenset({RegistryUrl("https://registry.npmjs.org")}))


def _maybe_skip_or_fail() -> None:
    if sys.platform != "darwin":
        pytest.skip("sandbox-exec is the macOS substrate; Linux uses bwrap (S4-02)")
    if shutil.which("sandbox-exec") is None:
        pytest.fail(
            "nightly macOS runner is broken: sandbox-exec missing "
            "(built-in to macOS — should always be on PATH)"
        )


@pytest.mark.nightly_macos
@pytest.mark.asyncio
async def test_sandbox_exec_allows_allowlisted_host(tmp_path: Path) -> None:
    _maybe_skip_or_fail()
    spec = JailedSubprocessSpec(
        cmd=(
            "/usr/bin/curl",
            "--max-time",
            "5",
            "-o",
            "/dev/null",
            "-s",
            "https://registry.npmjs.org/",
        ),
        cwd=SandboxedPath(absolute=tmp_path),
        env=NpmEnv(),
        network=_registry_allowlist(),
        time_budget_s=15.0,
        memory_mib=128,
        pids_max=64,
    )
    result = await SandboxExecAdapter().run(spec)
    # Pre-S4-05: JailSetupFailed(binary-not-allowlisted). Post-S4-05:
    # Completed.
    assert isinstance(result, Completed | JailSetupFailed)
    if isinstance(result, JailSetupFailed):
        assert result.reason == "binary-not-allowlisted"


@pytest.mark.nightly_macos
@pytest.mark.asyncio
async def test_sandbox_exec_denies_non_allowlisted_host(tmp_path: Path) -> None:
    _maybe_skip_or_fail()
    spec = JailedSubprocessSpec(
        cmd=(
            "/usr/bin/curl",
            "--max-time",
            "5",
            "-o",
            "/dev/null",
            "-s",
            "https://github.com/",
        ),
        cwd=SandboxedPath(absolute=tmp_path),
        env=NpmEnv(),
        network=_registry_allowlist(),
        time_budget_s=15.0,
        memory_mib=128,
        pids_max=64,
    )
    result = await SandboxExecAdapter().run(spec)
    # Pre-S4-05: JailSetupFailed(binary-not-allowlisted). Post-S4-05:
    # NetworkDenied(host="github.com").
    assert isinstance(result, NetworkDenied | JailSetupFailed)
    if isinstance(result, NetworkDenied):
        assert result.host == "github.com"
    else:
        assert result.reason == "binary-not-allowlisted"
