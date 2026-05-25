"""Phase-4 S4-06 — capability-mint module-boundary fence (AC-6/AC-7).

The interim Phase-4 mint lives at :mod:`codegenie.rag._capability_mint` and
must be importable only from :mod:`codegenie.rag.ingest`. This module
encodes that boundary as three coupled fences:

1. **Contract shape** — the ``pyproject.toml`` ``[tool.importlinter]``
   forbidden contract has the exact shape S4-06 AC-6 names (name, type,
   ``as_packages``, ``source_modules``, ``forbidden_modules``,
   ``ignore_imports``).
2. **AST scope** — no production file outside ``src/codegenie/rag/
   ingest.py`` references the private mint module *by any spelling*
   (full-module ``import``, ``from … import _capability_mint``,
   ``from codegenie.rag.ingest import _phase4_local_capability_mint``).
3. **Live-fire** — a planted violator file in ``src/codegenie/`` is
   actually caught by the real ``lint-imports`` console script, and the
   contract name appears in its output.

Per S4-06 §"Notes for the implementer" §1: import-linter is module-level,
not symbol-level. The private-module split is what makes the boundary
mechanically enforceable.
"""

from __future__ import annotations

import ast
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any, Final

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
PYPROJECT: Final[Path] = REPO_ROOT / "pyproject.toml"
CONTRACT: Final[str] = "ADR-0016: phase4 solved-example mint module is scoped"
# Planted under `codegenie.probes` (an `as_packages = true` source row) so
# `import-linter` actually walks the planted import. A top-level
# `src/codegenie/<file>.py` lives outside every enumerated source module
# and would be silently ignored — the same trap the BudgetToken contract
# (ADR-0010) navigated by listing siblings individually.
PLANTED: Final[Path] = REPO_ROOT / "src/codegenie/probes/_test_phase4_mint_scope_violation.py"

# AC-7 contract-shape expectation: the eight `codegenie.rag.*` siblings of
# `_capability_mint` must appear, the bare `codegenie.rag` row must not
# (would trigger import-linter's "Modules have shared descendants").
_EXPECTED_RAG_SIBLINGS: Final[frozenset[str]] = frozenset(
    {
        "codegenie.rag.cli",
        "codegenie.rag.embedder",
        "codegenie.rag.embedding_cache",
        "codegenie.rag.errors",
        "codegenie.rag.ingest",
        "codegenie.rag.models",
        "codegenie.rag.provenance",
        "codegenie.rag.store",
    }
)


def _load_contract() -> dict[str, Any]:
    """Find the ADR-0016 phase4 contract row in ``pyproject.toml``.

    Raises ``AssertionError`` (loudly — Rule 12) if the row is missing so
    the shape test's downstream assertions don't ``KeyError`` and obscure
    the real failure (the contract was never added at all).
    """
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    contracts = data.get("tool", {}).get("importlinter", {}).get("contracts", [])
    for entry in contracts:
        if entry.get("name") == CONTRACT:
            return dict(entry)
    raise AssertionError(
        f"pyproject.toml [tool.importlinter.contracts] is missing the "
        f"S4-06 mint-scope contract named {CONTRACT!r}"
    )


def test_phase4_mint_contract_shape() -> None:
    """AC-6/AC-7: the contract has the exact shape S4-06 names.

    The story's ``source_modules = ["codegenie"]`` reading is the user-
    intent shorthand; the load-bearing realization is "every
    ``codegenie.*`` subpackage". Listing the bare ``codegenie`` package
    triggers import-linter's "Modules have shared descendants" check
    (the forbidden module is a descendant), so siblings of
    ``codegenie.rag._capability_mint`` are enumerated individually — the
    same shape the ADR-0010 BudgetToken contract uses. The exact
    ``as_packages`` / ``forbidden_modules`` / ``ignore_imports`` rows
    remain pinned verbatim.
    """
    contract = _load_contract()
    assert contract["type"] == "forbidden"
    assert contract["as_packages"] is True
    assert contract["forbidden_modules"] == ["codegenie.rag._capability_mint"]
    assert contract["ignore_imports"] == [
        "codegenie.rag.ingest -> codegenie.rag._capability_mint",
    ]

    sources: list[str] = list(contract["source_modules"])
    # The bare `codegenie` umbrella must NOT appear — it would shadow the
    # forbidden descendant.
    assert "codegenie" not in sources
    assert "codegenie.rag" not in sources
    # Every `codegenie.rag.*` sibling of the mint must be a source.
    missing = _EXPECTED_RAG_SIBLINGS - set(sources)
    assert not missing, (
        f"contract source_modules is missing {sorted(missing)!r} — every "
        f"`codegenie.rag.*` sibling of `_capability_mint` must be policed"
    )
    # And the forbidden module must NOT be on the source list (would also
    # trigger shared-descendants).
    assert "codegenie.rag._capability_mint" not in sources


def test_no_production_imports_private_mint_outside_ingest() -> None:
    """AC-7: AST sweep proves no production file *but* ingest.py
    references the private mint module by any spelling.

    Three spellings are forbidden:

    1. ``import codegenie.rag._capability_mint`` (direct).
    2. ``from codegenie.rag._capability_mint import …`` (symbol pull).
    3. ``from codegenie.rag import _capability_mint`` (package-level alias).

    Plus a fourth: ``from codegenie.rag.ingest import _phase4_local_capability_mint``
    — ``import-linter`` cannot see that (it is a symbol, not a module),
    so the AST sweep is the only enforcement.
    """
    violators: list[str] = []
    src_root = REPO_ROOT / "src/codegenie"
    for path in src_root.rglob("*.py"):
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel == "src/codegenie/rag/ingest.py":
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue  # pragma: no cover — surfaced by other test suites
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "codegenie.rag._capability_mint":
                        violators.append(f"{rel}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                names = {alias.name for alias in node.names}
                if module == "codegenie.rag._capability_mint":
                    violators.append(f"{rel}: from {module} import …")
                if module == "codegenie.rag" and "_capability_mint" in names:
                    violators.append(f"{rel}: from codegenie.rag import _capability_mint")
                if module == "codegenie.rag.ingest" and "_phase4_local_capability_mint" in names:
                    violators.append(
                        f"{rel}: from codegenie.rag.ingest import _phase4_local_capability_mint"
                    )
    assert not violators, "Private mint module imported from disallowed sites:\n" + "\n".join(
        violators
    )


def test_lint_imports_catches_planted_mint_scope_violation() -> None:
    """AC-7: real ``lint-imports`` run rejects a planted violator file.

    Plants ``src/codegenie/_test_phase4_mint_scope_violation.py`` that
    imports the private mint module, runs the actual ``lint-imports``
    console script with ``--no-cache``, asserts non-zero exit, and
    asserts the contract name appears in stdout/stderr. Cleans up the
    planted file in ``finally`` so a flaky run never leaves the tree
    poisoned (Rule 12 — fail loud, but never leave a mess).
    """
    binary = Path(sys.executable).parent / "lint-imports"
    if not binary.exists():
        found = shutil.which("lint-imports")
        assert found is not None, "lint-imports must be installed for fence tests"
        binary = Path(found)
    try:
        PLANTED.write_text(
            "import codegenie.rag._capability_mint  # noqa: F401\n",
            encoding="utf-8",
        )
        result = subprocess.run(
            [str(binary), "--config", "pyproject.toml", "--no-cache"],
            cwd=REPO_ROOT,
            env=os.environ.copy(),
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode != 0, (
            "lint-imports unexpectedly passed with a planted mint-scope violator. "
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )
        combined = result.stdout + result.stderr
        assert CONTRACT in combined, (
            f"Contract name {CONTRACT!r} not in lint-imports output:\n{combined}"
        )
    finally:
        PLANTED.unlink(missing_ok=True)
