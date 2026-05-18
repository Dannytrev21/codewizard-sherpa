"""Phase 3 S1-02 AC-14 — every ``match`` over ``ScopeDim`` in ``scope.py``
ends with ``case _: assert_never(...)``.

AST-walk the source. Adding a future ``Negation`` / ``Range`` variant without
updating every consumer's ``match`` block MUST break the build at mypy time;
this AST test is the belt-and-braces guarantee that the wildcard arm is wired
to ``assert_never`` rather than a silent ``pass`` / fallthrough.
"""

from __future__ import annotations

import ast
import inspect

import codegenie.plugins.scope as scope_mod


def test_scope_match_blocks_have_assert_never() -> None:
    src = inspect.getsource(scope_mod)
    tree = ast.parse(src)
    match_nodes = [n for n in ast.walk(tree) if isinstance(n, ast.Match)]
    assert match_nodes, "expected at least one `match` block in scope.py"
    for m in match_nodes:
        last = m.cases[-1]
        # Last case must be `case _: ...`
        assert isinstance(last.pattern, ast.MatchAs) and last.pattern.pattern is None, (
            f"last case in match at line {m.lineno} is not a wildcard `_`"
        )
        # Body must be a single Expr wrapping a Call to assert_never
        body = last.body
        assert len(body) == 1 and isinstance(body[0], ast.Expr), (
            f"wildcard arm at line {m.lineno} is not a single assert_never expression"
        )
        call = body[0].value
        assert isinstance(call, ast.Call) and getattr(call.func, "id", None) == "assert_never", (
            f"wildcard arm at line {m.lineno} does not call assert_never(...)"
        )
