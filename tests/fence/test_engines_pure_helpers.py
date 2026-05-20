"""AC-Pure-1 fence — the OpenRewrite engine's functional core stays pure.

``_build_openrewrite_spec`` and ``_map_jail_result`` carry all of the
engine's logic; they must contain no ``await``, no ``os`` / ``time`` /
``subprocess`` / ``logging`` reference, and no raw ``open(`` call. ``apply``
is the *only* impure surface — it is the sole place an ``await`` may appear,
and its body is the thin orchestration ADR-0014 prescribes (build spec →
await jail → map result → conditionally register → return). The live check
and the planted-positive cases share :func:`_pure_helper_violations` so a
regression in the scanner kills both (mutation resistance).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_ENGINE_SOURCE = Path(__file__).resolve().parents[2] / (
    "src/codegenie/transforms/engines/openrewrite.py"
)
_PURE_HELPERS = frozenset({"_build_openrewrite_spec", "_map_jail_result"})
_FORBIDDEN_MODULE_NAMES = frozenset({"os", "time", "subprocess", "logging"})


def _function_defs(source: str) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    """Map every top-level + nested function name to its def node."""
    out: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            out[node.name] = node
    return out


def _pure_helper_violations(source: str, helper_names: frozenset[str]) -> list[str]:
    """Return every impurity (``await`` / forbidden-module reference / raw
    ``open(``) found inside the named helper function bodies."""
    out: list[str] = []
    for name, fn in _function_defs(source).items():
        if name not in helper_names:
            continue
        for node in ast.walk(fn):
            if isinstance(node, ast.Await | ast.AsyncFor | ast.AsyncWith):
                out.append(f"{name}:{node.lineno} await/async")
            elif isinstance(node, ast.Name) and node.id in _FORBIDDEN_MODULE_NAMES:
                out.append(f"{name}:{node.lineno} {node.id}")
            elif (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "open"
            ):
                out.append(f"{name}:{node.lineno} bare open()")
    return out


def test_pure_helpers_exist() -> None:
    """AC-Pure-1 — a rename must not silently void this fence."""
    defs = _function_defs(_ENGINE_SOURCE.read_text("utf-8"))
    for helper in _PURE_HELPERS:
        assert helper in defs, f"pure helper {helper!r} not found — fence is voided"


def test_pure_helpers_are_pure() -> None:
    """AC-Pure-1 live check — the functional-core helpers carry no impurity."""
    violations = _pure_helper_violations(_ENGINE_SOURCE.read_text("utf-8"), _PURE_HELPERS)
    assert violations == [], f"impurity inside OpenRewrite pure helpers: {violations}"


@pytest.mark.parametrize(
    "snippet",
    [
        "def _build_openrewrite_spec():\n    return await x()\n",
        "def _map_jail_result():\n    import os\n    return os.getpid()\n",
        "def _map_jail_result():\n    return time.time()\n",
        "def _build_openrewrite_spec():\n    return subprocess.run(['x'])\n",
        "def _map_jail_result():\n    return open('x').read()\n",
        "def _build_openrewrite_spec():\n    logging.info('x')\n",
    ],
)
def test_scanner_catches_each_planted_impurity(snippet: str) -> None:
    """AC-Pure-1 planted-positive — the same scanner catches every impurity form."""
    assert _pure_helper_violations(snippet, _PURE_HELPERS) != []


def test_scanner_allows_pure_helper_body() -> None:
    """AC-Pure-1 complement — a genuinely pure helper body is not flagged."""
    pure = "def _map_jail_result():\n    return _build_transform(repo, plan)\n"
    assert _pure_helper_violations(pure, _PURE_HELPERS) == []


def test_await_appears_only_inside_apply() -> None:
    """AC-Pure-1 — ``apply`` is the only impure surface: every ``await`` in
    the engine module is lexically inside the ``apply`` coroutine."""
    defs = _function_defs(_ENGINE_SOURCE.read_text("utf-8"))
    for name, fn in defs.items():
        if name == "apply":
            continue
        awaits = [n for n in ast.walk(fn) if isinstance(n, ast.Await)]
        assert awaits == [], f"await leaked out of apply() into {name}()"


def test_apply_body_is_thin_orchestration() -> None:
    """AC-Pure-1 — ``apply``'s body is the ADR-0014 thin orchestration: it
    builds the spec, awaits the jail, maps the result, conditionally
    registers the transform, and returns the bare outcome — nothing else."""
    apply = _function_defs(_ENGINE_SOURCE.read_text("utf-8"))["apply"]
    assert len(apply.body) <= 6, "apply() body grew past the thin-orchestration shape"
    called = {
        node.func.id
        for node in ast.walk(apply)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert {"_build_openrewrite_spec", "_map_jail_result"} <= called
    attr_called = {
        node.func.attr
        for node in ast.walk(apply)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert {"run", "register"} <= attr_called
    assert isinstance(apply.body[-1], ast.Return)
