"""AST source-scan — no direct ``yaml`` import inside ``codegenie.conventions``.

S2-02 AC-10: alias-resistant variant of the original ripgrep check. A future
contributor reaching for ``yaml`` directly fails this test instead of slipping
past review (e.g., ``from yaml import safe_load as _y`` is caught).
"""

from __future__ import annotations

import ast
import pathlib

import codegenie.conventions as conventions_pkg

_CONVENTIONS_ROOT = pathlib.Path(conventions_pkg.__file__).parent


def test_no_conventions_module_imports_yaml_directly() -> None:
    offenders: list[tuple[str, int]] = []
    for py_path in _CONVENTIONS_ROOT.rglob("*.py"):
        tree = ast.parse(py_path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "yaml" or alias.name.startswith("yaml."):
                        offenders.append((str(py_path), node.lineno))
            elif isinstance(node, ast.ImportFrom):
                if node.module == "yaml" or (
                    node.module is not None and node.module.startswith("yaml.")
                ):
                    offenders.append((str(py_path), node.lineno))
    assert not offenders, (
        "codegenie.conventions MUST route every YAML parse through "
        f"codegenie.parsers.safe_yaml; direct yaml import sites: {offenders}"
    )
