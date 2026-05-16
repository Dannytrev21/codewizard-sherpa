"""S4-02 AC-5 — `regenerate.sh` guard rejects `LAST_INDEXED == HEAD`.

The script's env-overrideable form lets us deterministically force the
failing branch: invoke once normally (exit 0), then re-invoke with
``LAST_INDEXED=$(git rev-parse HEAD)`` to point at the post-2nd-commit
HEAD; exit 1 + named stderr is the contract.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

SOURCE_FIXTURE = Path(__file__).parent.parent.parent / "fixtures" / "portfolio" / "stale-scip"


def test_regenerate_sh_refuses_last_indexed_equals_head(tmp_path: Path) -> None:
    if shutil.which("bash") is None:
        pytest.fail("`bash` is required to run regenerate.sh; not on $PATH.")
    if shutil.which("git") is None:
        pytest.fail("`git` is required by regenerate.sh; not on $PATH.")

    work = tmp_path / "stale-scip"
    shutil.copytree(SOURCE_FIXTURE, work)
    (work / "regenerate.sh").chmod(0o755)

    # First pass: normal flow, must succeed.
    ok = subprocess.run(  # noqa: S603 — script under test, fixture path.
        ["./regenerate.sh"], cwd=work, capture_output=True, text=True
    )
    assert ok.returncode == 0, (
        f"baseline regenerate.sh failed (exit {ok.returncode}); stderr={ok.stderr!r}"
    )

    # Capture post-v1 HEAD; force the guard with LAST_INDEXED=HEAD.
    head = subprocess.run(  # noqa: S603
        ["git", "rev-parse", "HEAD"], cwd=work, capture_output=True, text=True, check=True
    ).stdout.strip()
    env = {**os.environ, "LAST_INDEXED": head}
    forced = subprocess.run(  # noqa: S603
        ["./regenerate.sh"], cwd=work, capture_output=True, text=True, env=env
    )
    assert forced.returncode == 1, (
        f"Expected exit 1 when LAST_INDEXED==HEAD, got {forced.returncode}. "
        f"stderr={forced.stderr!r}"
    )
    assert "refuses to set last_indexed_commit == HEAD" in forced.stderr, (
        f"Expected guard message in stderr, got: {forced.stderr!r}"
    )
