"""AC-10 — macOS-only, nightly-only ``sandbox-exec`` hello-world test.

Fails (does NOT skip) on darwin when ``sandbox-exec`` is missing — it is
built-in to macOS so absence indicates a broken runner (Rule 12). On
non-darwin the test skips with a clear "macOS substrate" message.

NB: ``sandbox-exec`` is intentionally NOT in ``ALLOWED_BINARIES`` until
S4-05 lands. Until then this test exits at the chokepoint and surfaces
``JailSetupFailed(reason='binary-not-allowlisted')`` — that is the
documented behaviour on a pre-S4-05 darwin runner. Coordinated with the
nightly cadence from ADR-0006 §Consequences row 4: per-PR macOS CI is
explicitly out of scope.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

from codegenie.transforms.sandbox.sandbox_exec import SandboxExecAdapter
from codegenie.transforms.sandbox_jail import (
    Completed,
    DenyAll,
    JailedSubprocessSpec,
    JailSetupFailed,
    NpmEnv,
)


@pytest.mark.nightly_macos
@pytest.mark.asyncio
async def test_sandbox_exec_hello_world(tmp_path: Path) -> None:
    if sys.platform != "darwin":
        pytest.skip("sandbox-exec is the macOS substrate; Linux uses bwrap (S4-02)")
    if shutil.which("sandbox-exec") is None:
        # sandbox-exec ships built-in to macOS; absence means the runner
        # itself is broken. Rule 12: fail loud, do not silently skip.
        pytest.fail(
            "nightly macOS runner is broken: sandbox-exec missing "
            "(built-in to macOS — should always be on PATH)"
        )
    spec = JailedSubprocessSpec(
        cmd=("/bin/echo", "hello"),
        cwd=tmp_path,
        env=NpmEnv(),
        network=DenyAll(),
        time_budget_s=5.0,
        memory_mib=64,
        pids_max=32,
    )
    result = await SandboxExecAdapter().run(spec)
    # Until S4-05 admits ``sandbox-exec`` to ``ALLOWED_BINARIES`` the
    # chokepoint refuses the spawn — the result is the documented
    # ``JailSetupFailed`` variant. After S4-05 lands, the result must be
    # ``Completed(exit_code=0)``. Both shapes are tracked so the test
    # captures the substitution unambiguously.
    assert isinstance(result, Completed | JailSetupFailed)
    if isinstance(result, Completed):
        assert result.exit_code == 0
    else:
        assert result.reason == "binary-not-allowlisted"
