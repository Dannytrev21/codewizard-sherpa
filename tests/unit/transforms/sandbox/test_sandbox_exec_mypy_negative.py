"""AC-2 — subprocess-mypy fence over :class:`SandboxExecAdapter` structural
conformance, and AC-25 fence over the :class:`Hostname` newtype.

Two negative fixtures: (1) a class with the wrong ``run`` signature is
rejected when bound to a ``SubprocessJail``-typed variable, proving the
Port's structural typing is load-bearing; (2) ``_render_allow_network_clause``
is rejected when called with a raw ``str`` host, proving the
:class:`Hostname` newtype boundary holds at typecheck time.

The Port is intentionally NOT ``@runtime_checkable`` (S4-01 AC-2) — these
fixtures pin the only discipline that remains: type-check-time structural
conformance.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

_BAD_SIGNATURE_FIXTURE = textwrap.dedent(
    """
    from codegenie.transforms.sandbox_jail import SubprocessJail

    class BogusAdapter:
        # Wrong signature — ``run`` takes no spec and returns int.
        async def run(self) -> int:
            return 0

    # mypy must reject the structural bind because the run signatures diverge.
    jail: SubprocessJail = BogusAdapter()  # type: ignore[assignment]  # sentinel
    """
)


_HOSTNAME_RAW_STR_FIXTURE = textwrap.dedent(
    """
    from codegenie.transforms.sandbox.sandbox_exec import (
        _render_allow_network_clause,
    )

    # Passing a raw ``str`` (not a ``Hostname`` newtype) must be rejected.
    out: str = _render_allow_network_clause("registry.npmjs.org", 443)
    """
)


def _run_mypy_strict(fixture_path: Path) -> subprocess.CompletedProcess[str]:
    repo_root = Path(__file__).resolve().parents[4]
    return subprocess.run(
        [sys.executable, "-m", "mypy", "--strict", str(fixture_path)],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(repo_root),
    )


def test_mypy_strict_catches_bogus_adapter_signature(tmp_path: Path) -> None:
    """A class with the wrong ``run`` signature must NOT structurally
    conform to :class:`SubprocessJail` under ``mypy --strict`` — the
    ``# type: ignore`` sentinel proves an error would be reported absent
    the ignore.
    """
    # Remove the ignore comment so mypy will report; assert a non-zero
    # exit + the expected error code surfaces.
    fixture = tmp_path / "bogus_adapter.py"
    body = _BAD_SIGNATURE_FIXTURE.replace("# type: ignore[assignment]  # sentinel", "")
    fixture.write_text(body)
    proc = _run_mypy_strict(fixture)
    assert proc.returncode != 0, (
        "mypy --strict accepted a BogusAdapter bound to SubprocessJail:\n"
        f"stdout={proc.stdout!r}\nstderr={proc.stderr!r}"
    )
    combined = (proc.stdout + proc.stderr).lower()
    assert "incompatible" in combined or "subprocessjail" in combined or "assignment" in combined, (
        f"unexpected mypy output:\nstdout={proc.stdout!r}\nstderr={proc.stderr!r}"
    )


def test_mypy_strict_rejects_raw_str_for_hostname(tmp_path: Path) -> None:
    """:class:`Hostname` is a :func:`typing.NewType` — passing a raw
    ``str`` to :func:`_render_allow_network_clause` must be rejected by
    ``mypy --strict``.
    """
    fixture = tmp_path / "raw_str_hostname.py"
    fixture.write_text(_HOSTNAME_RAW_STR_FIXTURE)
    proc = _run_mypy_strict(fixture)
    assert proc.returncode != 0, (
        "mypy --strict accepted a raw str where Hostname newtype is required:\n"
        f"stdout={proc.stdout!r}\nstderr={proc.stderr!r}"
    )
    combined = (proc.stdout + proc.stderr).lower()
    assert "hostname" in combined or "argument" in combined, (
        f"unexpected mypy output:\nstdout={proc.stdout!r}\nstderr={proc.stderr!r}"
    )
