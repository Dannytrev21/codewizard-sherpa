"""AC-12 — postinstall-canary substrate test (two variants).

Variant A: ``npm install --ignore-scripts --package-lock-only`` should
    NOT execute ``postinstall`` (CLI flag + ``NpmEnv`` both engaged).
Variant B (negative control): ``npm install --package-lock-only`` (CLI
    flag DISABLED, ``NpmEnv`` still sets ``npm_config_ignore_scripts=true``)
    — proves the *env half* (not the CLI flag) is what suppresses the
    canary inside the substrate. Without this variant, AC-12 would
    pass against a misconfigured bwrap that shares writes.

S8-04 owns the full adversarial corpus; this story lands the integration
precursor + the negative control.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

from codegenie.transforms._forward import SandboxedPath
from codegenie.transforms.sandbox.bwrap import BwrapAdapter
from codegenie.transforms.sandbox_jail import (
    Completed,
    DenyAll,
    JailedSubprocessSpec,
    JailSetupFailed,
    NpmEnv,
)

_FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures/phase03/postinstall_canary"


def _linux_bwrap_node_or_fail() -> None:
    if sys.platform != "linux":
        pytest.skip("Linux substrate")
    if shutil.which("bwrap") is None:
        pytest.fail("bwrap missing on Linux runner — apt-get install -y bubblewrap")
    if shutil.which("node") is None:
        pytest.fail("node missing on Linux runner")
    if shutil.which("npm") is None:
        pytest.fail("npm missing on Linux runner")


@pytest.mark.asyncio
async def test_postinstall_canary_blocked_with_flag_and_env(tmp_path: Path) -> None:
    """Variant A — both halves of the split defence engaged."""
    _linux_bwrap_node_or_fail()
    work = tmp_path / "work"
    work.mkdir()
    (work / "package.json").write_text((_FIXTURE_DIR / "package.json").read_text())
    canary_path = tmp_path / ".codegenie-canary"

    spec = JailedSubprocessSpec(
        cmd=("npm", "install", "--ignore-scripts", "--package-lock-only"),
        cwd=SandboxedPath(work),
        env=NpmEnv(),
        network=DenyAll(),
        time_budget_s=30.0,
        memory_mib=256,
        pids_max=128,
    )
    result = await BwrapAdapter().run(spec)
    if isinstance(result, JailSetupFailed):
        pytest.xfail(f"precondition not met: {result.reason}")
    # Canary-absent check FIRST — a Completed-with-side-effect mutant
    # would still pass the variant check but fail this one.
    assert not canary_path.exists(), f"postinstall canary leaked through substrate: {canary_path}"
    assert isinstance(result, Completed)


@pytest.mark.asyncio
async def test_postinstall_canary_blocked_with_env_only(tmp_path: Path) -> None:
    """Variant B (negative control) — CLI flag dropped; ``NpmEnv`` alone
    must suppress the canary. Proves the env half is the load-bearing
    defence, not just the CLI flag."""
    _linux_bwrap_node_or_fail()
    work = tmp_path / "work"
    work.mkdir()
    (work / "package.json").write_text((_FIXTURE_DIR / "package.json").read_text())
    canary_path = tmp_path / ".codegenie-canary"

    spec = JailedSubprocessSpec(
        cmd=("npm", "install", "--package-lock-only"),
        cwd=SandboxedPath(work),
        env=NpmEnv(),
        network=DenyAll(),
        time_budget_s=30.0,
        memory_mib=256,
        pids_max=128,
    )
    result = await BwrapAdapter().run(spec)
    if isinstance(result, JailSetupFailed):
        pytest.xfail(f"precondition not met: {result.reason}")
    assert not canary_path.exists(), (
        f"postinstall canary leaked through substrate with env-only defence: {canary_path}"
    )
    assert isinstance(result, Completed)
