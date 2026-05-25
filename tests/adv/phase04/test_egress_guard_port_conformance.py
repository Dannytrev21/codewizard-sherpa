"""AC-24 — :class:`EgressGuard` satisfies S3-02's
:class:`EgressGuardPort` Protocol.

S3-02 declares a local ``EgressGuardPort(Protocol)`` requiring
``pinned_to(host: str) -> AbstractAsyncContextManager[None]`` and injects
it into :class:`AnthropicLeafAdapter`. Because :class:`EgressGuard` is an
all-classmethod class (process-global state, never instantiated), the
**class object itself** is the port — assigned via
``AnthropicLeafAdapter(..., egress_guard=EgressGuard)``.

This test compiles a tiny snippet under ``mypy --strict`` in a
subprocess; the assignment ``guard: EgressGuardPort = EgressGuard`` must
type-check clean. Without this gate, the two stories can silently
diverge on the ``async`` / signature shape.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

pytestmark = pytest.mark.phase04_adv


_MYPY_SNIPPET = textwrap.dedent(
    """
    from __future__ import annotations

    from codegenie.fallback.leaf.anthropic_adapter import EgressGuardPort
    from codegenie.fallback.leaf.egress_guard import EgressGuard

    # AC-24 — typed assignability: the class itself satisfies the Protocol.
    guard: EgressGuardPort = EgressGuard
    reveal_type(guard)
    """
).strip()


def test_egress_guard_class_satisfies_egress_guard_port(tmp_path: Path) -> None:
    # Resolve mypy via the current interpreter's ``python -m mypy``; falling
    # back to ``shutil.which("mypy")`` only matters when the dev extras are
    # missing entirely (in which case import would fail under ``-m`` and we
    # surface that as a real failure rather than silently skipping).
    try:
        subprocess.run(  # noqa: S603 — controlled argv
            [sys.executable, "-m", "mypy", "--version"],
            check=True,
            capture_output=True,
            timeout=30,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        if shutil.which("mypy") is None:
            pytest.skip("mypy not installed; install dev extras")

    snippet = tmp_path / "snippet.py"
    snippet.write_text(_MYPY_SNIPPET)
    result = subprocess.run(  # noqa: S603 — controlled argv
        [sys.executable, "-m", "mypy", "--strict", str(snippet)],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    # The snippet should type-check clean (the only diagnostic mypy emits
    # is the ``reveal_type`` note, which is informational, not an error).
    assert result.returncode == 0, (
        f"EgressGuard does NOT satisfy EgressGuardPort under --strict.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
