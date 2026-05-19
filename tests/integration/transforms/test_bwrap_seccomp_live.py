"""AC-3 (kernel-boundary) — Linux-only live seccomp test.

Runs a blocked syscall inside the jail (``unshare -U /bin/true``) and
asserts a non-zero exit / SIGSYS surface. Pre-S4-05 (bwrap not in
``ALLOWED_BINARIES``), the test ``xfail``-s with the
``binary-not-allowlisted`` marker so the CI signal stays loud once
S4-05 ships.
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


@pytest.mark.asyncio
async def test_bwrap_seccomp_blocks_unshare(tmp_path: Path) -> None:
    if sys.platform != "linux":
        pytest.skip("bwrap is the Linux substrate")
    if shutil.which("bwrap") is None:
        # See test_bwrap_hello_world for the xfail rationale.
        pytest.xfail("S9-01 pending — bwrap not installed on the CI runner.")

    cmd: tuple[str, ...]
    if shutil.which("unshare"):
        cmd = ("/usr/bin/unshare", "-U", "/bin/true")
    elif shutil.which("python3"):
        # Fallback: invoke CLONE_NEWUSER via libc. ``python3`` is NOT in
        # ALLOWED_BINARIES today; once S4-05 lands, this branch becomes
        # the cross-distro path.
        cmd = (
            "python3",
            "-c",
            "import ctypes; ctypes.CDLL('libc.so.6').unshare(0x10000000)",
        )
    else:
        pytest.fail(
            "Neither /usr/bin/unshare nor python3 available on Linux runner — CI image regressed."
        )

    spec = JailedSubprocessSpec(
        cmd=cmd,
        cwd=SandboxedPath(absolute=tmp_path),
        env=NpmEnv(),
        network=DenyAll(),
        time_budget_s=5.0,
        memory_mib=64,
        pids_max=32,
    )
    result = await BwrapAdapter().run(spec)
    if isinstance(result, JailSetupFailed):
        assert result.reason in {"binary-not-allowlisted", "bwrap-not-on-path"}
        pytest.xfail("S4-05 not landed — bwrap not in ALLOWED_BINARIES yet")
    assert isinstance(result, Completed)
    # SIGSYS surfaces in different ways depending on bwrap's seccomp
    # death routing; the only invariant is that the call did NOT
    # exit zero.
    assert result.exit_code != 0, (
        f"unshare(2) was permitted inside the jail — seccomp filter not "
        f"installed correctly. exit_code={result.exit_code}"
    )
