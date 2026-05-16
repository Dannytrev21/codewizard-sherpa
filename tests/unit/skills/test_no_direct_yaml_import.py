"""AST source-scan — no direct ``yaml`` import inside ``codegenie.skills``.

AC-24 of S2-01: ripgrep-style text checks are alias-smugglable (``from yaml
import safe_load as _y``). An AST walk over every ``Import`` / ``ImportFrom``
node names the modules durably; a future contributor who reaches for ``yaml``
directly fails this test instead of slipping past review.
"""

from __future__ import annotations

import ast
import pathlib

import codegenie.skills as skills_pkg

_SKILLS_ROOT = pathlib.Path(skills_pkg.__file__).parent


def test_no_skills_module_imports_yaml_directly() -> None:
    offenders: list[tuple[str, int]] = []
    for py_path in _SKILLS_ROOT.rglob("*.py"):
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
        "codegenie.skills MUST route every YAML parse through "
        f"codegenie.parsers.safe_yaml; direct yaml import sites: {offenders}"
    )
