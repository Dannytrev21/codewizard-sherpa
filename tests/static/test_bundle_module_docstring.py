"""S3-04 AC-1 — module docstring of ``codegenie.plugins.bundle`` cites
ADR-0008 and the rejection of hedged-race composition.
"""

from __future__ import annotations

import ast
from pathlib import Path


def test_module_docstring_cites_adr_and_rejection() -> None:
    tree = ast.parse(Path("src/codegenie/plugins/bundle.py").read_text())
    doc = ast.get_docstring(tree) or ""
    assert "ADR-0008" in doc, "module docstring must cite ADR-0008"
    assert "hedged-race" in doc, (
        "module docstring must name the rejection of hedged-race composition"
    )
