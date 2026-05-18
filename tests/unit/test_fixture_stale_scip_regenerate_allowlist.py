"""S7-02 AC-31 — stale-scip/regenerate.sh invokes only allowlisted binaries.

`scip-typescript` is in `ALLOWED_BINARIES`, but the seed-build ritual
(AC-21a) is OUT-OF-BAND — contributor's local box, NOT inside
`regenerate.sh`. This test asserts: (1) every invoked binary at
regen-time is in `ALLOWED_BINARIES ∪ _SHELL_COREUTILS_ALLOWLIST`;
(2) `scip-typescript` does NOT appear in the invoked set at regen time
(the explicit AC-31 assertion); (3) no forbidden shell token appears.
"""

from __future__ import annotations

from pathlib import Path

from codegenie.exec import ALLOWED_BINARIES
from tests.unit._fixture_regen_allowlist import (
    _SHELL_COREUTILS_ALLOWLIST,
    _SHELL_FORBIDDEN,
    tokenize_invoked_binaries,
)

_FIXTURE = Path(__file__).parent.parent / "fixtures" / "portfolio" / "stale-scip"


def test_regenerate_invokes_only_allowlisted_binaries() -> None:
    """AC-31 — every invoked binary is in ALLOWED_BINARIES ∪ coreutils."""
    script_bytes = (_FIXTURE / "regenerate.sh").read_bytes()
    invoked = tokenize_invoked_binaries(script_bytes)
    allowed = ALLOWED_BINARIES | _SHELL_COREUTILS_ALLOWLIST
    illegal = invoked - allowed
    assert not illegal, (
        f"stale-scip/regenerate.sh invokes non-allowlisted binaries: {sorted(illegal)}. "
        f"Allowed = ALLOWED_BINARIES ∪ coreutils."
    )


def test_regenerate_does_not_invoke_scip_typescript() -> None:
    """AC-31 — `scip-typescript` is explicitly absent at regen time.

    `scip-typescript` IS in `ALLOWED_BINARIES`, but the seed-build
    ritual (AC-21a) is OUT-OF-BAND — contributor's local box, NOT
    inside `regenerate.sh`. A contributor "tidying up" by inlining
    `scip-typescript .` into regenerate.sh would silently make
    fixture regeneration non-deterministic (the binary's bytes depend
    on tool version, locale, file ordering) and slow CI.
    """
    script_bytes = (_FIXTURE / "regenerate.sh").read_bytes()
    invoked = tokenize_invoked_binaries(script_bytes)
    assert "scip-typescript" not in invoked, (
        "stale-scip/regenerate.sh must NOT invoke `scip-typescript` at regen time. "
        "The seed binary `_seed/scip-index.scip` is committed bytes produced "
        "OUT-OF-BAND per the AC-21a seed-build ritual."
    )


def test_regenerate_does_not_invoke_forbidden() -> None:
    """AC-31 — explicit forbidden tokens (eval, curl, pnpm, ...) absent."""
    script_bytes = (_FIXTURE / "regenerate.sh").read_bytes()
    invoked = tokenize_invoked_binaries(script_bytes)
    bad = invoked & _SHELL_FORBIDDEN
    assert not bad, f"stale-scip/regenerate.sh invokes forbidden tokens: {sorted(bad)}"
