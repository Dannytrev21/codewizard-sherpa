"""Phase 6 — public-surface fence + Phase-6.5 import boundary.

* **S1-01 / ADR-0001** — the four harness-facing contract names are
  importable from ``codegenie.workflows`` and are NOT re-exported from any
  private submodule under ``codegenie.workflows._*``.
* **S1-02 / ADR-0003** — the ten ledger-substrate names extend the
  allowlist additively (AC-13). The allowlist below is the single
  pinning point.

Adding a fifteenth name requires (a) ADR amendment, (b) editing this
allowlist, (c) editing the ``__all__`` list in
``src/codegenie/workflows/__init__.py`` — never silent.
"""

from __future__ import annotations

import ast
import glob
from pathlib import Path

import codegenie.workflows as workflows_pkg

_S1_01_ALLOWLIST = {
    "VulnRemediationCase",
    "VulnRemediationResult",
    "SutDigest",
    "VulnRemediationSut",
}
_S1_02_ALLOWLIST = {
    # The seven ledger variants.
    "NeedsPlan",
    "PlanReady",
    "PatchApplied",
    "GateFailedRetryable",
    "AwaitingHumanReview",
    "Completed",
    "FailedUnrecoverable",
    # The closed umbrella + kind alias.
    "VulnLedgerState",
    "LedgerStateKind",
    # The transition record + per-event identifier (re-exported from
    # codegenie.types.identifiers for harness convenience).
    "TransitionEvent",
    "TransitionId",
}
_ALLOWLIST = _S1_01_ALLOWLIST | _S1_02_ALLOWLIST


def test_ac1_four_names_importable_from_package() -> None:
    for name in _ALLOWLIST:
        assert hasattr(workflows_pkg, name), (
            f"AC-1: {name} missing from codegenie.workflows public surface"
        )


def test_ac6_no_private_module_re_exports_the_four_names() -> None:
    """No file under ``codegenie/workflows/_*.py`` (excluding ``__init__.py``,
    which is the *public* re-export site) may re-export the public names.

    S1-01 ADR-0001 (the four contract names) must live only in
    ``vuln_sut.py``. S1-02 / ADR-0003 (the ten ledger names) must live only
    in ``vuln_ledger.py`` — the underscore-prefixed ``_chain.py`` carries
    only the pure chain-head helper, never a public name.
    """
    pkg_root = Path(workflows_pkg.__file__).resolve().parent
    private_modules = [
        p for p in glob.glob(str(pkg_root / "_*.py")) if not p.endswith("__init__.py")
    ]
    for path in private_modules:
        src = Path(path).read_text()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            # Forbid `__all__ = [...]` exposing any of the allowlist names.
            if (
                isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == "__all__"
            ):
                if isinstance(node.value, ast.List | ast.Tuple):
                    elts = {e.value for e in node.value.elts if isinstance(e, ast.Constant)}
                    leaked = elts & _ALLOWLIST
                    assert not leaked, (
                        f"AC-6: private module {path} re-exports {leaked} — "
                        f"public names must live only in vuln_sut.py / vuln_ledger.py."
                    )


def test_ac12_init_all_is_exact_allowlist() -> None:
    """``codegenie.workflows.__init__.__all__`` is exactly the 14-name allowlist.

    Adding a fifteenth name requires (a) ADR amendment, (b) editing this
    allowlist, (c) editing the ``__all__`` list — never silent.
    """
    init_path = Path(workflows_pkg.__file__)
    tree = ast.parse(init_path.read_text())
    all_node = None
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "__all__"
        ):
            all_node = node
            break
    assert all_node is not None, "AC-12: __all__ must be present in workflows/__init__.py"
    assert isinstance(all_node.value, ast.List | ast.Tuple)
    declared = {e.value for e in all_node.value.elts if isinstance(e, ast.Constant)}
    assert declared == _ALLOWLIST, (
        f"AC-12: __all__ drifted from the ADR-0001 allowlist. Got {declared}, "
        f"want {_ALLOWLIST}. This is the extension-by-addition seam — a fifth "
        f"public name requires an ADR amendment + an explicit edit here."
    )


def test_ac12_public_dir_filtered_matches_allowlist() -> None:
    """Every non-underscore attribute exposed by the package is in the allowlist.

    Catches the case where ``__all__`` is correct but someone added a
    private-name import without an underscore prefix (which ``dir()`` would
    surface even though ``from .workflows import *`` would skip it).
    """
    public = {name for name in dir(workflows_pkg) if not name.startswith("_")}
    # Module-level submodules created by Python (e.g. ``vuln_sut``) appear in
    # ``dir()``; filter them down to symbols listed in ``__all__``.
    public_in_all = public & _ALLOWLIST
    extra = public_in_all - _ALLOWLIST
    assert not extra, f"AC-12: extra public names leaked: {extra}"
    assert public_in_all == _ALLOWLIST, f"AC-12: missing public names: {_ALLOWLIST - public_in_all}"
