"""AC-25 — subprocess-mypy fence over the ``match spec.network`` dispatch.

Mirrors the S4-01 AC-9a precedent. A fixture that omits the
``RegistryAllowlist`` arm must fail ``mypy --strict`` with an
``assert_never`` narrowing error. Adding a third
:class:`~codegenie.transforms.sandbox_jail.NetworkPolicy` variant in
Phase 5 (e.g., ``TunneledEgress``) re-arms this fence automatically.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

_FIXTURE = textwrap.dedent(
    """
    from typing import assert_never
    from codegenie.transforms.sandbox_jail import (
        DenyAll,
        NetworkPolicy,
    )

    # ``RegistryAllowlist`` arm intentionally omitted — mypy must flag.
    def dispatch(net: NetworkPolicy) -> str:
        match net:
            case DenyAll():
                return "deny"
            case _ as unexpected:
                assert_never(unexpected)
        return ""
    """
)


def test_mypy_strict_catches_missing_network_policy_arm(tmp_path: Path) -> None:
    fixture = tmp_path / "negative.py"
    fixture.write_text(_FIXTURE)
    repo_root = Path(__file__).resolve().parents[4]
    proc = subprocess.run(
        [sys.executable, "-m", "mypy", "--strict", str(fixture)],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(repo_root),
    )
    combined = (proc.stdout + proc.stderr).lower()
    assert proc.returncode != 0, (
        "mypy --strict accepted a match with a missing NetworkPolicy arm: "
        f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )
    assert "never" in combined or "assert_never" in combined or "argument" in combined, (
        f"mypy error did not reference assert_never narrowing: "
        f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )
