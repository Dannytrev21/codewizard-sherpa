"""S7-01 AC-31 — native-modules/regenerate.sh invokes only allowlisted binaries.

Additional explicit assertion: ``pnpm``, ``npm``, ``node-gyp`` must
NOT appear in the invoked-binary set. Their absence is the structural
guarantee that backs the hand-authored lockfile precedent.
"""

from __future__ import annotations

from pathlib import Path

from codegenie.exec import ALLOWED_BINARIES

from tests.unit._fixture_regen_allowlist import (
    _SHELL_COREUTILS_ALLOWLIST,
    _SHELL_FORBIDDEN,
    tokenize_invoked_binaries,
)

_FIXTURE = Path(__file__).parent.parent / "fixtures" / "portfolio" / "native-modules"


def test_regenerate_invokes_only_allowlisted_binaries() -> None:
    """AC-31 — every invoked binary is in ALLOWED_BINARIES ∪ coreutils."""
    script_bytes = (_FIXTURE / "regenerate.sh").read_bytes()
    invoked = tokenize_invoked_binaries(script_bytes)
    allowed = ALLOWED_BINARIES | _SHELL_COREUTILS_ALLOWLIST
    illegal = invoked - allowed
    assert not illegal, (
        f"native-modules/regenerate.sh invokes non-allowlisted binaries: {sorted(illegal)}"
    )


def test_regenerate_does_not_invoke_pnpm_npm_or_node_gyp() -> None:
    """AC-31 — explicit assertion: none of pnpm, npm, node-gyp appear.

    The hand-authored lockfile precedent (Phase-1 node_typescript_helm/)
    requires that regenerate.sh never reach for a package manager.
    """
    script_bytes = (_FIXTURE / "regenerate.sh").read_bytes()
    invoked = tokenize_invoked_binaries(script_bytes)
    leaked = invoked & {"pnpm", "npm", "node-gyp", "yarn"}
    assert not leaked, (
        f"native-modules/regenerate.sh must not invoke a package manager; got {sorted(leaked)}"
    )


def test_regenerate_does_not_invoke_forbidden() -> None:
    """AC-31 — explicit forbidden tokens (eval, curl, pnpm, ...) absent."""
    script_bytes = (_FIXTURE / "regenerate.sh").read_bytes()
    invoked = tokenize_invoked_binaries(script_bytes)
    bad = invoked & _SHELL_FORBIDDEN
    assert not bad, (
        f"native-modules/regenerate.sh invokes forbidden tokens: {sorted(bad)}"
    )
