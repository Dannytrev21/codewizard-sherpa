"""Cold-start invariant: ``import codegenie`` must not transitively load heavy modules.

Test (a) is load-bearing — it spawns a subprocess to measure REAL runtime
side-effects. Tests (b) / (c) are fast AST guards over the module-level imports
of ``cli.py`` and ``__init__.py``. Owned by story S1-05.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN_HEAVY = {"yaml", "jsonschema", "pydantic", "blake3", "structlog"}


def test_importing_codegenie_does_not_load_heavy_modules() -> None:
    """AC-7(a) — LOAD-BEARING.

    Mutation guard: a ``from .submodule import X`` re-export where
    ``.submodule`` top-level imports ``yaml`` is caught HERE (the AST scan
    misses transitive imports).
    """
    probe = (
        "import sys, json; "
        "pre = set(sys.modules); "
        "import codegenie; "
        "loaded = set(sys.modules) - pre; "
        "print(json.dumps(sorted(loaded)))"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
        cwd=PROJECT_ROOT,
    )
    loaded = set(json.loads(result.stdout))
    leaked = FORBIDDEN_HEAVY & loaded
    assert leaked == set(), (
        f"Importing `codegenie` transitively loaded forbidden heavy modules: {leaked}. "
        f"Move the offending import inside a function body. "
        f"See phase-arch-design.md §Component design — CLI."
    )


def _top_level_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    names: set[str] = set()
    for node in tree.body:  # module-level only
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module.split(".")[0])
    return names


def test_cli_does_not_top_level_import_heavy_modules() -> None:
    # AC-7(b): fast AST guard for cli.py. Explicit pytest.skip (NOT silent
    # `return`) when cli.py doesn't yet exist — see story §Note on the
    # cli-targeted import-linter contract.
    cli = PROJECT_ROOT / "src" / "codegenie" / "cli.py"
    if not cli.exists():
        pytest.skip(
            "cli.py lands in S4-02 (vertical slice); see story S1-05 §Note. "
            "AC-10's deliberate-negative canary exercises the import-linter "
            "contract until then."
        )
    leaked = _top_level_imports(cli) & FORBIDDEN_HEAVY
    assert leaked == set(), (
        f"cli.py must defer heavy imports inside command bodies; leaked: {leaked}."
    )


def test_package_init_does_not_top_level_import_heavy_modules() -> None:
    # AC-7(c): operative immediately — __init__.py exists from S1-01.
    init = PROJECT_ROOT / "src" / "codegenie" / "__init__.py"
    leaked = _top_level_imports(init) & FORBIDDEN_HEAVY
    assert leaked == set(), (
        f"codegenie/__init__.py must stay light (AST scan); leaked: {leaked}. "
        f"NOTE: this AST scan is a fast guard — the load-bearing test is "
        f"test_importing_codegenie_does_not_load_heavy_modules above."
    )
