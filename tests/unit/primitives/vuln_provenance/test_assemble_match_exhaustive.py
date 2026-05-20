"""Phase 7 S2-04 AC-9 — AST-walk pinning the `assemble_provenance`
`match (app_result, base_result)` exhaustiveness discipline.

Phase 7 ADR-0006 §Consequences: the composition is a `match`/`assert_never`
block — never an `if r.kind in {...}` string-set comparison (BP-4 closure).
This test parses `assembly.py`, locates `assemble_provenance`'s single
`match` statement, and asserts it carries exactly four composition arms plus
a `case _: assert_never(...)` guard. The guard is what makes `mypy --strict`
prove the four arms exhaust `(Provenance | None, Provenance | None)`; a bare
`case _: pass` would silently drop that static guarantee.
"""

from __future__ import annotations

import ast
import inspect

from codegenie.primitives.vuln_provenance.assembly import assemble_provenance


def _match_node() -> ast.Match:
    """Return the single `match` statement inside `assemble_provenance`."""
    func = ast.parse(inspect.getsource(assemble_provenance)).body[0]
    assert isinstance(func, ast.FunctionDef)
    matches = [n for n in ast.walk(func) if isinstance(n, ast.Match)]
    assert len(matches) == 1, f"expected exactly one match statement, found {len(matches)}"
    return matches[0]


def test_match_has_four_composition_arms_plus_assert_never_guard() -> None:
    """AC-9 — four `(app_result, base_result)` composition arms
    (`(None, None)`, `(app, None)`, `(None, base)`, `(app, base)`) plus one
    `case _` guard = five `case` clauses total."""
    cases = _match_node().cases

    assert len(cases) == 5, (
        f"expected 4 composition arms + 1 assert_never guard, found {len(cases)} cases"
    )


def test_match_guard_arm_is_wildcard_calling_assert_never() -> None:
    """AC-9 — the fifth arm must be `case _:` and its body must call
    `assert_never(...)`. That is the exhaustiveness proof (ADR-0006); a
    `raise` or `pass` here would compile but lose the `mypy --strict`
    guarantee that no `(Provenance | None, ...)` shape is unhandled."""
    guard = _match_node().cases[-1]

    # `case _` parses as a bare capture pattern: MatchAs(pattern=None, name=None).
    assert isinstance(guard.pattern, ast.MatchAs)
    assert guard.pattern.pattern is None
    assert guard.pattern.name is None

    called = {
        node.func.id
        for node in ast.walk(guard)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "assert_never" in called, "the `case _` guard must call assert_never(...)"
