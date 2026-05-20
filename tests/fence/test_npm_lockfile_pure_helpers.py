"""AC-Pure-1 fence — the functional-core helpers of ``npm_lockfile.py`` are
side-effect free.

The named pure helpers carry the engine's logic; ``apply`` and
``_run_npm_install`` are the only impure code. This AST walk asserts the six
helpers contain no ``await`` and call nothing rooted at ``os`` /
``subprocess`` / ``shutil``. Mirrors the S1-05 ``_no_io_in_pure_helpers``
precedent. Live + planted cases share :func:`_impurity_violations`.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_NPM_LOCKFILE = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "codegenie"
    / "transforms"
    / "engines"
    / "npm_lockfile.py"
)
_PURE_HELPERS = frozenset(
    {
        "_read_package_json",
        "_edit_dep_version",
        "_max_depth",
        "_build_unified_diff",
        "_parse_lockfile",
        "_compute_transform_id",
    }
)
_FORBIDDEN_CALL_ROOTS = frozenset({"os", "subprocess", "shutil"})


def _call_root(func: ast.expr) -> str | None:
    current: ast.expr = func
    while isinstance(current, ast.Attribute):
        current = current.value
    return current.id if isinstance(current, ast.Name) else None


def _impurity_violations(source: str, label: str) -> list[str]:
    """Return every ``await`` / forbidden-call site inside a named pure helper."""
    out: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        if node.name not in _PURE_HELPERS:
            continue
        for sub in ast.walk(node):
            if isinstance(sub, ast.Await):
                out.append(f"{label}:{node.name} contains await")
            if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute):
                root = _call_root(sub.func)
                if root in _FORBIDDEN_CALL_ROOTS:
                    out.append(f"{label}:{node.name} calls {root}.*")
    return out


def test_npm_lockfile_pure_helpers_are_side_effect_free() -> None:
    """AC-Pure-1 live check — the six helpers carry no await / os / subprocess /
    shutil."""
    violations = _impurity_violations(_NPM_LOCKFILE.read_text("utf-8"), "npm_lockfile.py")
    assert violations == [], f"impure pure-helper: {violations}"


@pytest.mark.parametrize(
    "snippet",
    [
        "import os\ndef _max_depth(o):\n    os.system('x')\n    return 0\n",
        "async def _read_package_json(p):\n    return await p\n",
        "import subprocess\ndef _parse_lockfile(p):\n    subprocess.run(['x'])\n",
        "import shutil\ndef _compute_transform_id(b):\n    shutil.rmtree('x')\n",
    ],
)
def test_scanner_catches_planted_impurity(snippet: str) -> None:
    """AC-Pure-1 planted-positive — the same scanner catches each impurity."""
    assert _impurity_violations(snippet, "planted") != []


def test_scanner_allows_orjson_blake3_difflib_and_sandboxed_path_open() -> None:
    """AC-Pure-1 complement — the helpers' real dependencies are not impure."""
    ok = "def _read_package_json(p):\n    raw = p.open('rb').read()\n    return orjson.loads(raw)\n"
    assert _impurity_violations(ok, "ok") == []
