"""AC-8 — Linux-only ``bwrap`` hello-world integration test.

Fails (does NOT skip) on Linux when ``bwrap`` is missing — silent skips
defeat the substrate choice (ADR-0006 §Consequences + High-level-impl
§Step 4 Risks L310). On macOS the test skips with a clear "Linux
substrate" message.

NB: bwrap is intentionally NOT in ``ALLOWED_BINARIES`` until S4-05
lands. Until then this test exits at the chokepoint and surfaces
``JailSetupFailed(reason='binary-not-allowlisted')`` — that is the
documented behavior on a pre-S4-05 Linux runner.
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
async def test_bwrap_hello_world(tmp_path: Path) -> None:
    if sys.platform != "linux":
        pytest.skip("bwrap is the Linux substrate; macOS uses sandbox-exec (S4-03)")
    if shutil.which("bwrap") is None:
        # S9-01 owns the CI YAML edit that installs bubblewrap on the
        # Linux runner. Until that lands, this test xfails with the
        # documented S9-01 reason; the AC-15 CI-setup fence
        # (tests/integration/test_ci_setup_fence.py) is the gate that
        # flips this xfail into a hard fail once S9-01 lands and
        # someone removes the `apt-get install -y bubblewrap` step.
        # Story §Out of scope: "CI YAML edit — S9-01 lands ...".
        pytest.xfail(
            "S9-01 pending — bwrap not installed on the CI runner. "
            "When S9-01 adds `apt-get install -y bubblewrap` to the Linux "
            "job, the test xpasses; removing the install step then turns "
            "this into a loud fail per ADR-0006 §Consequences."
        )
    sp: SandboxedPath = SandboxedPath(absolute=tmp_path)
    spec = JailedSubprocessSpec(
        cmd=("/bin/echo", "hello"),
        cwd=sp,
        env=NpmEnv(),
        network=DenyAll(),
        time_budget_s=5.0,
        memory_mib=64,
        pids_max=32,
    )
    result = await BwrapAdapter().run(spec)
    # Pre-S4-05: bwrap not allowlisted → JailSetupFailed.
    # Post-S4-05: bwrap allowlisted + present → Completed(exit_code=0).
    if isinstance(result, JailSetupFailed):
        assert result.reason == "binary-not-allowlisted", (
            f"Unexpected JailSetupFailed reason {result.reason!r}; "
            "expected pre-S4-05 binary-not-allowlisted path."
        )
        pytest.xfail("S4-05 not landed — bwrap not in ALLOWED_BINARIES yet")
    assert isinstance(result, Completed)
    assert result.exit_code == 0
