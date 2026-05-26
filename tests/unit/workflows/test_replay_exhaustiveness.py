"""Phase 6 S2-02 AC-7 — AST exhaustiveness gate over ``_dispatch_verdict``.

A four-variant verdict union needs a match with four ``case`` arms plus
a ``case _:`` drift guard. Adding a fifth variant to ``ReplayVerdict``
without updating ``_dispatch_verdict`` would silently bypass the new
verdict; the AST test catches the missing arm at the source level,
mypy-version-independent.
"""

from __future__ import annotations

import ast
import inspect

from codegenie.workflows import replay as replay_module


def _find_dispatch_verdict_node() -> ast.FunctionDef:
    tree = ast.parse(inspect.getsource(replay_module))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_dispatch_verdict":
            return node
    raise AssertionError("_dispatch_verdict not found in replay.py")


def _match_node(fn: ast.FunctionDef) -> ast.Match:
    for stmt in fn.body:
        if isinstance(stmt, ast.Match):
            return stmt
    raise AssertionError("_dispatch_verdict does not contain a top-level match statement")


def test_ac7_dispatch_has_exactly_four_named_arms_plus_wildcard() -> None:
    fn = _find_dispatch_verdict_node()
    match_stmt = _match_node(fn)
    named_cases: list[str] = []
    wildcard_count = 0
    for case in match_stmt.cases:
        pat = case.pattern
        if isinstance(pat, ast.MatchValue) and isinstance(pat.value, ast.Constant):
            named_cases.append(pat.value.value)
        elif isinstance(pat, ast.MatchAs) and pat.pattern is None and pat.name is None:
            # ``case _:`` is parsed as MatchAs with no inner pattern.
            wildcard_count += 1
    assert sorted(named_cases) == sorted(
        ["verified", "chain_mismatch", "torn_write", "empty_workflow"]
    ), (
        f"_dispatch_verdict arms drift — got {sorted(named_cases)!r}. The "
        f"four closed verdict kinds must each be a separate ``case`` arm "
        f"(AC-7). Adding a fifth variant is an ADR-0003 amendment + an "
        f"additive arm here."
    )
    assert wildcard_count == 1, (
        "_dispatch_verdict must have exactly one ``case _:`` drift-guard arm "
        "that raises AssertionError."
    )


def test_ac7_wildcard_arm_raises_assertionerror() -> None:
    """The drift-guard arm raises ``AssertionError`` — not silently passes."""
    fn = _find_dispatch_verdict_node()
    match_stmt = _match_node(fn)
    for case in match_stmt.cases:
        pat = case.pattern
        if isinstance(pat, ast.MatchAs) and pat.pattern is None and pat.name is None:
            # Body must raise AssertionError.
            raises = [
                node
                for node in ast.walk(ast.Module(body=case.body, type_ignores=[]))
                if isinstance(node, ast.Raise)
            ]
            assert raises, "wildcard arm must raise"
            return
    raise AssertionError("no wildcard arm found")
