"""S7-01 AC-31 — distroless-target/regenerate.sh invokes only allowlisted binaries.

Additional explicit assertion: ``docker`` MUST appear in the
invoked-binary set (this is the only Phase-2 fixture that builds a
real container image).
"""

from __future__ import annotations

from pathlib import Path

from codegenie.exec import ALLOWED_BINARIES
from tests.unit._fixture_regen_allowlist import (
    _SHELL_COREUTILS_ALLOWLIST,
    _SHELL_FORBIDDEN,
    tokenize_invoked_binaries,
)

_FIXTURE = Path(__file__).parent.parent / "fixtures" / "portfolio" / "distroless-target"


def test_regenerate_invokes_only_allowlisted_binaries() -> None:
    """AC-31 — every invoked binary is in ALLOWED_BINARIES ∪ coreutils."""
    script_bytes = (_FIXTURE / "regenerate.sh").read_bytes()
    invoked = tokenize_invoked_binaries(script_bytes)
    allowed = ALLOWED_BINARIES | _SHELL_COREUTILS_ALLOWLIST
    illegal = invoked - allowed
    assert not illegal, (
        f"distroless-target/regenerate.sh invokes non-allowlisted binaries: {sorted(illegal)}"
    )


def test_regenerate_invokes_docker() -> None:
    """AC-31 — docker MUST appear in the invoked-binary set."""
    script_bytes = (_FIXTURE / "regenerate.sh").read_bytes()
    invoked = tokenize_invoked_binaries(script_bytes)
    assert "docker" in invoked, (
        "distroless-target/regenerate.sh must invoke `docker` to build "
        "the distroless target image; got invoked-binary set "
        f"{sorted(invoked)!r}"
    )


def test_regenerate_does_not_invoke_forbidden() -> None:
    """AC-31 — explicit forbidden tokens (eval, curl, pnpm, ...) absent."""
    script_bytes = (_FIXTURE / "regenerate.sh").read_bytes()
    invoked = tokenize_invoked_binaries(script_bytes)
    bad = invoked & _SHELL_FORBIDDEN
    assert not bad, f"distroless-target/regenerate.sh invokes forbidden tokens: {sorted(bad)}"
