"""S7-02 AC-31 — monorepo-pnpm/regenerate.sh invokes only allowlisted binaries.

`pnpm` is NOT in `ALLOWED_BINARIES` (per ADR-0001 / S1-06). The
`pnpm-lock.yaml` shipped alongside this fixture is hand-authored bytes
generated OUT-OF-BAND; `regenerate.sh` is `mkdir`/coreutils-only.

This test asserts: (1) every invoked binary is in
`ALLOWED_BINARIES ∪ _SHELL_COREUTILS_ALLOWLIST`; (2) `pnpm` does NOT
appear in the invoked set (explicit AC-31 assertion); (3) no forbidden
shell token (`eval`, `curl`, `wget`, `npm`, `yarn`, `node-gyp`, ...)
appears.
"""

from __future__ import annotations

from pathlib import Path

from codegenie.exec import ALLOWED_BINARIES
from tests.unit._fixture_regen_allowlist import (
    _SHELL_COREUTILS_ALLOWLIST,
    _SHELL_FORBIDDEN,
    tokenize_invoked_binaries,
)

_FIXTURE = Path(__file__).parent.parent / "fixtures" / "portfolio" / "monorepo-pnpm"


def test_regenerate_invokes_only_allowlisted_binaries() -> None:
    """AC-31 — every invoked binary is in ALLOWED_BINARIES ∪ coreutils."""
    script_bytes = (_FIXTURE / "regenerate.sh").read_bytes()
    invoked = tokenize_invoked_binaries(script_bytes)
    allowed = ALLOWED_BINARIES | _SHELL_COREUTILS_ALLOWLIST
    illegal = invoked - allowed
    assert not illegal, (
        f"monorepo-pnpm/regenerate.sh invokes non-allowlisted binaries: {sorted(illegal)}. "
        f"Allowed = ALLOWED_BINARIES ∪ coreutils."
    )


def test_regenerate_does_not_invoke_pnpm() -> None:
    """AC-31 — `pnpm` is explicitly absent.

    `pnpm` is the load-bearing forbidden token for monorepo-pnpm: a
    contributor "tidying up" the regen script by re-introducing
    `pnpm install --frozen-lockfile` (looks innocuous; pnpm is a real
    tool) would silently expand the regen surface beyond the ADR-0001
    allowlist. This assertion is the front-line guard.
    """
    script_bytes = (_FIXTURE / "regenerate.sh").read_bytes()
    invoked = tokenize_invoked_binaries(script_bytes)
    assert "pnpm" not in invoked, (
        "monorepo-pnpm/regenerate.sh must NOT invoke `pnpm` — the lockfile is "
        "hand-authored bytes generated OUT-OF-BAND. `pnpm` is NOT in "
        "ALLOWED_BINARIES per ADR-0001 / S1-06."
    )


def test_regenerate_does_not_invoke_forbidden() -> None:
    """AC-31 — explicit forbidden tokens (eval, curl, npm, ...) absent."""
    script_bytes = (_FIXTURE / "regenerate.sh").read_bytes()
    invoked = tokenize_invoked_binaries(script_bytes)
    bad = invoked & _SHELL_FORBIDDEN
    assert not bad, f"monorepo-pnpm/regenerate.sh invokes forbidden tokens: {sorted(bad)}"
