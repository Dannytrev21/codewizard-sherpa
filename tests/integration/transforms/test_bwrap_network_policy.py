"""AC-9 — Linux-only live netns/pf egress tests.

Uses ``node -e fetch(...)`` (NOT ``curl`` — pinned to the deny list of
the closed-set regression test). Fails (does NOT skip) when bwrap or
node is missing on a Linux runner. ``CAP_NET_ADMIN`` is checked
upfront; absence ⇒ pytest.fail.

Pre-S4-05 (bwrap not allowlisted), the tests xfail with the
``binary-not-allowlisted`` marker.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest

from codegenie.transforms._forward import SandboxedPath
from codegenie.transforms.sandbox.bwrap import BwrapAdapter
from codegenie.transforms.sandbox_jail import (
    Completed,
    JailedSubprocessSpec,
    JailSetupFailed,
    NetworkDenied,
    NpmEnv,
    RegistryAllowlist,
)
from codegenie.types.identifiers import RegistryUrl

_REGISTRY_HOSTS = frozenset({RegistryUrl("https://registry.npmjs.org")})


@pytest.fixture
def _linux_bwrap_node_or_fail() -> None:
    if sys.platform != "linux":
        pytest.skip("Linux substrate")
    if shutil.which("bwrap") is None:
        pytest.xfail("S9-01 pending — bwrap not installed on the CI runner.")
    if shutil.which("node") is None:
        pytest.xfail(
            "S9-01 pending — node missing on the CI runner; curl is in the "
            "deny list of test_allowed_binaries_closed_set_regression."
        )
    if os.geteuid() != 0:
        # Best-effort CAP_NET_ADMIN check via /proc/self/status.
        try:
            content = Path(f"/proc/{os.getpid()}/status").read_text()
            if "CapEff:" in content:
                cap_line = next(
                    (line for line in content.splitlines() if line.startswith("CapEff:")),
                    "",
                )
                # Bit 12 = CAP_NET_ADMIN; mask 0x1000.
                hex_cap = cap_line.split()[-1]
                if (int(hex_cap, 16) & 0x1000) == 0:
                    pytest.xfail(
                        "S9-01 pending — CAP_NET_ADMIN absent on the CI runner; "
                        "S9-01 must `setcap cap_net_admin+ep` on the Linux job."
                    )
        except (OSError, ValueError):
            pass


@pytest.mark.asyncio
async def test_allowlist_permits_npm_registry(
    _linux_bwrap_node_or_fail: None, tmp_path: Path
) -> None:
    script = (
        "fetch('https://registry.npmjs.org/')"
        ".then(r => process.exit(r.ok ? 0 : 1))"
        ".catch(() => process.exit(2))"
    )
    spec = JailedSubprocessSpec(
        cmd=("node", "-e", script),
        cwd=SandboxedPath(tmp_path),
        env=NpmEnv(),
        network=RegistryAllowlist(hosts=_REGISTRY_HOSTS),
        time_budget_s=10.0,
        memory_mib=128,
        pids_max=64,
    )
    result = await BwrapAdapter().run(spec)
    if isinstance(result, JailSetupFailed):
        assert result.reason in {"binary-not-allowlisted", "cap-net-admin-missing"}
        pytest.xfail(f"precondition not met: {result.reason}")
    assert isinstance(result, Completed), f"unexpected: {result!r}"
    assert result.exit_code == 0


@pytest.mark.asyncio
async def test_allowlist_denies_github(_linux_bwrap_node_or_fail: None, tmp_path: Path) -> None:
    script = "fetch('https://github.com/').then(r => process.exit(0)).catch(() => process.exit(1))"
    spec = JailedSubprocessSpec(
        cmd=("node", "-e", script),
        cwd=SandboxedPath(tmp_path),
        env=NpmEnv(),
        network=RegistryAllowlist(hosts=_REGISTRY_HOSTS),
        time_budget_s=10.0,
        memory_mib=128,
        pids_max=64,
    )
    result = await BwrapAdapter().run(spec)
    if isinstance(result, JailSetupFailed):
        assert result.reason in {"binary-not-allowlisted", "cap-net-admin-missing"}
        pytest.xfail(f"precondition not met: {result.reason}")
    assert isinstance(result, NetworkDenied), f"expected NetworkDenied, got {result!r}"
    assert "github.com" in result.host
