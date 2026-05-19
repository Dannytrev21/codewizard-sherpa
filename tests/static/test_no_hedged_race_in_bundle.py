"""S3-04 AC-27 — AST positive structural defense against hedged-race
re-introduction in ``codegenie.plugins.bundle``.

The walker enforces:

(a) ``_resolve_chain`` contains zero calls to ``asyncio.gather`` /
    ``asyncio.wait`` / ``asyncio.as_completed`` / ``asyncio.TaskGroup``.
(b) Exactly one ``Call`` site invokes a callable named ``dispatch`` (the
    single dispatch site — a future speculative pre-fetch would fail this).
(c) ``_compose_entry`` is ``def`` (not ``async def``) and contains zero
    ``Await`` nodes and zero references to ``asyncio`` — functional-core
    proof.
"""

from __future__ import annotations

import ast
from pathlib import Path

_BUNDLE_PATH = Path("src/codegenie/plugins/bundle.py")
_FORBIDDEN_RACE_ATTRS = {"gather", "wait", "as_completed", "TaskGroup"}


def _find_function(tree: ast.Module, name: str) -> ast.AsyncFunctionDef | ast.FunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"{name} not found in bundle.py")


def test_resolve_chain_has_no_race_primitives() -> None:
    """AC-27 (a) — no race primitives anywhere inside ``_resolve_chain``."""

    tree = ast.parse(_BUNDLE_PATH.read_text())
    fn = _find_function(tree, "_resolve_chain")
    for node in ast.walk(fn):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in _FORBIDDEN_RACE_ATTRS, (
                f"hedged-race anti-pattern in _resolve_chain: {ast.unparse(node)}"
            )


def test_exactly_one_dispatch_call_site() -> None:
    """AC-27 (b) — exactly one site calls a ``dispatch``-named callable."""

    tree = ast.parse(_BUNDLE_PATH.read_text())
    dispatch_call_sites: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            target = ast.unparse(node.func)
            if target == "dispatch" or target.endswith(".dispatch"):
                dispatch_call_sites.append(ast.unparse(node))
    assert len(dispatch_call_sites) == 1, (
        f"expected exactly one dispatch site, found {len(dispatch_call_sites)}:"
        f" {dispatch_call_sites!r}"
    )


def test_compose_entry_is_pure_sync() -> None:
    """AC-27 (c) — ``_compose_entry`` is sync, no ``Await``, no ``asyncio``."""

    tree = ast.parse(_BUNDLE_PATH.read_text())
    fn = _find_function(tree, "_compose_entry")
    assert isinstance(fn, ast.FunctionDef), "_compose_entry must be ``def``, not ``async def``"
    for node in ast.walk(fn):
        assert not isinstance(node, ast.Await), "_compose_entry must contain no Await nodes"
        if isinstance(node, ast.Name):
            assert node.id != "asyncio", "_compose_entry must not reference asyncio"


def test_resolve_chain_is_async() -> None:
    """Symmetric proof — ``_resolve_chain`` IS ``async def``."""

    tree = ast.parse(_BUNDLE_PATH.read_text())
    fn = _find_function(tree, "_resolve_chain")
    assert isinstance(fn, ast.AsyncFunctionDef), "_resolve_chain must be ``async def``"
