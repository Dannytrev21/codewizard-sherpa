"""S7-01 AC-31 — minimal-ts/regenerate.sh invokes only allowlisted binaries.

The tokenizer is shared with the other S7-01 fixtures via
``tests/unit/_fixture_regen_allowlist.py`` (rule-of-three carve-out:
the policy is load-bearing).
"""

from __future__ import annotations

from pathlib import Path

from codegenie.exec import ALLOWED_BINARIES

from tests.unit._fixture_regen_allowlist import (
    _SHELL_COREUTILS_ALLOWLIST,
    _SHELL_FORBIDDEN,
    tokenize_invoked_binaries,
)

_FIXTURE = Path(__file__).parent.parent / "fixtures" / "portfolio" / "minimal-ts"


def test_regenerate_invokes_only_allowlisted_binaries() -> None:
    """AC-31 — every invoked binary is in ALLOWED_BINARIES ∪ coreutils."""
    script_bytes = (_FIXTURE / "regenerate.sh").read_bytes()
    invoked = tokenize_invoked_binaries(script_bytes)
    allowed = ALLOWED_BINARIES | _SHELL_COREUTILS_ALLOWLIST
    illegal = invoked - allowed
    assert not illegal, (
        f"minimal-ts/regenerate.sh invokes non-allowlisted binaries: {sorted(illegal)}. "
        f"Allowed = ALLOWED_BINARIES ∪ coreutils."
    )


def test_regenerate_does_not_invoke_forbidden() -> None:
    """AC-31 — explicit forbidden tokens (eval, curl, pnpm, npm, ...) absent."""
    script_bytes = (_FIXTURE / "regenerate.sh").read_bytes()
    invoked = tokenize_invoked_binaries(script_bytes)
    bad = invoked & _SHELL_FORBIDDEN
    assert not bad, (
        f"minimal-ts/regenerate.sh invokes forbidden tokens: {sorted(bad)}"
    )
