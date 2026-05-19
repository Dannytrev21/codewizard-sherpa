"""S3-04 AC-14 — AST proof of ``match`` + ``assert_never`` dispatch on
``AdapterConfidence`` (Phase-3 ADR-0010 sum-type discipline).
"""

from __future__ import annotations

import ast
from pathlib import Path

_BUNDLE_PATH = Path("src/codegenie/plugins/bundle.py")


def test_confidence_match_has_assert_never_arm() -> None:
    tree = ast.parse(_BUNDLE_PATH.read_text())
    match_nodes = [n for n in ast.walk(tree) if isinstance(n, ast.Match)]
    on_confidence = [m for m in match_nodes if ast.unparse(m.subject).endswith(".confidence")]
    assert len(on_confidence) >= 1, "no Match on confidence subject"
    m = on_confidence[0]
    case_patterns = [ast.unparse(c.pattern) for c in m.cases]
    assert any("Trusted()" in p for p in case_patterns), (
        f"expected Trusted() arm; got {case_patterns!r}"
    )
    assert any("Degraded()" in p and "Unavailable()" in p for p in case_patterns), (
        f"expected combined Degraded()|Unavailable() arm; got {case_patterns!r}"
    )
    # final arm exists with assert_never
    final = m.cases[-1]
    body_src = "\n".join(ast.unparse(s) for s in final.body)
    assert "assert_never" in body_src, f"expected assert_never final arm; got body {body_src!r}"
