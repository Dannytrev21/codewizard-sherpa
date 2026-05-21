"""S5-04 AC-Eval-7 — structural fence on `LockfilePolicy.evaluate`: no I/O.

AST-walks the `evaluate` method body and asserts no banned-name call
(`Path`, `open`, `os.`, `socket.`, `urllib.request`, `time.`, `random.`,
`datetime.`) appears — the functional-core / imperative-shell discipline made
structural. `from_yaml` (the imperative shell) is deliberately not checked.
"""

from __future__ import annotations

import ast
import inspect

from codegenie.transforms.policy import lockfile_policy as mod

_BANNED_NAMES = frozenset({"open", "Path"})
_BANNED_PREFIXES = ("os.", "socket.", "urllib.request", "time.", "random.", "datetime.")


def _collect_calls(tree: ast.AST) -> list[str]:
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                out.append(func.id)
            elif isinstance(func, ast.Attribute):
                parts: list[str] = [func.attr]
                cur: ast.AST = func.value
                while isinstance(cur, ast.Attribute):
                    parts.append(cur.attr)
                    cur = cur.value
                if isinstance(cur, ast.Name):
                    parts.append(cur.id)
                out.append(".".join(reversed(parts)))
    return out


def test_evaluate_is_pure_no_io_no_clock() -> None:
    src = inspect.getsource(mod)
    tree = ast.parse(src)
    evaluate_node: ast.FunctionDef | None = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "evaluate":
            evaluate_node = node
            break
    assert evaluate_node is not None, "evaluate() method not found in lockfile_policy.py"
    calls = _collect_calls(evaluate_node)
    bad = [c for c in calls if c in _BANNED_NAMES or any(c.startswith(p) for p in _BANNED_PREFIXES)]
    assert bad == [], f"evaluate() must be pure; found banned calls: {bad}"
