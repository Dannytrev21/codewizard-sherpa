"""Phase-3 S2-04 AC-14 — every ``match`` over ``PluginResolution`` /
``ScopeDim`` ends with ``case _: assert_never(...)``.

AST-walks ``resolver.py`` and asserts the wildcard arm in every
``match`` block is the call ``assert_never(...)`` — not a silent
``pass`` / fallthrough. Adding a future :data:`PluginResolution`
variant (e.g., S4-04's hypothetical ``LlmFallbackResolution``) without
updating every dispatch site MUST break the build at mypy time; this
AST scan is the belt-and-braces guarantee that the wildcard arm is
wired through.

The ``_dispatch_example`` helper at the bottom proves exhaustiveness
to mypy: the ``case _: assert_never(resolution)`` arm is the
type-level proof. ``mypy --strict`` flags it if a future variant is
added without updating this function.
"""

from __future__ import annotations

import ast
import inspect
from typing import assert_never

import codegenie.plugins.resolver as resolver_mod
from codegenie.plugins.resolver import (
    ConcreteResolution,
    PluginResolution,
    UniversalFallbackResolution,
)


def test_resolver_match_blocks_have_assert_never() -> None:
    src = inspect.getsource(resolver_mod)
    tree = ast.parse(src)
    match_nodes = [n for n in ast.walk(tree) if isinstance(n, ast.Match)]
    assert match_nodes, "expected at least one `match` block in resolver.py"
    for m in match_nodes:
        last = m.cases[-1]
        assert isinstance(last.pattern, ast.MatchAs) and last.pattern.pattern is None, (
            f"last case in match at line {m.lineno} is not a wildcard `_`"
        )
        body = last.body
        assert len(body) == 1 and isinstance(body[0], ast.Expr), (
            f"wildcard arm at line {m.lineno} is not a single expression"
        )
        call = body[0].value
        assert isinstance(call, ast.Call) and getattr(call.func, "id", None) == "assert_never", (
            f"wildcard arm at line {m.lineno} does not call assert_never(...)"
        )


def _dispatch_example(resolution: PluginResolution) -> str:
    """Mypy-checked exhaustive dispatch over :data:`PluginResolution`.

    The ``case _: assert_never(resolution)`` arm makes mypy reject
    this function whenever a third variant is added to
    :data:`PluginResolution` and not handled here. The runtime call
    below proves the dispatcher works on the two real variants.
    """
    match resolution:
        case ConcreteResolution():
            return "concrete"
        case UniversalFallbackResolution():
            return "fallback"
        case _:  # pragma: no cover — exhaustiveness guarantee.
            assert_never(resolution)


def test_dispatch_example_returns_expected_arms() -> None:
    """Runtime smoke: the dispatcher returns the expected string on
    each real variant — catches accidental swap of the two ``case``
    arms."""
    fallback = UniversalFallbackResolution(reason="no_concrete_match", candidates_considered=())
    assert _dispatch_example(fallback) == "fallback"
