"""Phase-4 S3-04 AC-23 — ``CassetteSanitizer`` AST purity fence.

Modelled on :mod:`tests/fence/test_engines_pure_helpers.py` and
:mod:`tests/fence/test_engines_no_module_state.py`. Asserts three structural
invariants of ``src/codegenie/fallback/cassette/sanitizer.py``:

(a) the named pure helpers reference no ``random`` / ``time`` / ``uuid`` /
    ``secrets`` / ``logging`` module and call no bare ``open(``;
(b) ``sanitizer.py`` holds no module-level mutable non-``Final`` state;
(c) ``verify_cassette`` is the ONLY function referencing ``Path`` / ``open`` /
    ``yaml``.

The scanner carries planted-positive checks so the fence itself is
mutation-resistant.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_SANITIZER_SOURCE = Path(__file__).resolve().parents[2] / (
    "src/codegenie/fallback/cassette/sanitizer.py"
)

_PURE_HELPERS = frozenset(
    {
        "_normalize_headers",
        "_strip_headers",
        "_redact_header_values",
        "_redact_body",
        "_scan_cassette_doc",
    }
)
_FORBIDDEN_NAMES_IN_HELPERS = frozenset({"random", "time", "uuid", "secrets", "logging"})


def _function_defs(source: str) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    out: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            out[node.name] = node
    return out


def _helper_impurity_violations(source: str, helper_names: frozenset[str]) -> list[str]:
    """Return every impurity finding (forbidden module ref, bare ``open(``)
    inside the named helper functions.
    """
    out: list[str] = []
    for name, fn in _function_defs(source).items():
        if name not in helper_names:
            continue
        for node in ast.walk(fn):
            if isinstance(node, ast.Name) and node.id in _FORBIDDEN_NAMES_IN_HELPERS:
                out.append(f"{name}:{node.lineno} {node.id}")
            elif (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "open"
            ):
                out.append(f"{name}:{node.lineno} bare open()")
    return out


# --- AC-23(a) — pure helpers reference no forbidden module + no open() ---


def test_pure_helpers_exist() -> None:
    """A rename must not silently void this fence."""
    defs = _function_defs(_SANITIZER_SOURCE.read_text("utf-8"))
    missing = [h for h in _PURE_HELPERS if h not in defs]
    assert missing == [], f"missing pure helpers: {missing}"


def test_pure_helpers_are_pure() -> None:
    """Live check — the functional-core helpers carry no impurity."""
    violations = _helper_impurity_violations(_SANITIZER_SOURCE.read_text("utf-8"), _PURE_HELPERS)
    assert violations == [], f"impurity inside CassetteSanitizer pure helpers: {violations}"


@pytest.mark.parametrize(
    "snippet",
    [
        "def _normalize_headers():\n    import random\n    return random.random()\n",
        "def _strip_headers():\n    return time.time()\n",
        "def _redact_header_values():\n    return uuid.uuid4()\n",
        "def _redact_body():\n    return secrets.token_hex()\n",
        "def _scan_cassette_doc():\n    logging.warning('x')\n",
        "def _scan_cassette_doc():\n    return open('x').read()\n",
    ],
)
def test_scanner_catches_each_planted_impurity(snippet: str) -> None:
    """Planted-positive — the same scanner catches every impurity form.

    Without this row the live test cannot tell "no impurity" from "scanner
    silently broken." (Same mutation-resistance pattern as
    :mod:`test_engines_pure_helpers`.)
    """
    assert _helper_impurity_violations(snippet, _PURE_HELPERS) != []


def test_scanner_allows_genuinely_pure_helper() -> None:
    """Complement of the planted-positive: a pure body is not flagged."""
    pure = "def _redact_body(b):\n    return b.replace(b'x', b'y')\n"
    assert _helper_impurity_violations(pure, _PURE_HELPERS) == []


# --- AC-23(b) — no module-level mutable non-``Final`` state --------------


def test_module_level_state_is_final_or_constant() -> None:
    """sanitizer.py holds no module-level mutable non-``Final`` state.

    Every top-level assignment must be either: an ``ast.AnnAssign`` with a
    ``Final[...]`` annotation; OR an ``__all__`` tuple; OR a private type
    alias (``_X = <expression with no Call>``). A Call on the RHS of a plain
    Assign would be mutable shared state; that is what this fence guards.
    """
    source = _SANITIZER_SOURCE.read_text("utf-8")
    tree = ast.parse(source)
    violations: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.AnnAssign):
            ann = node.annotation
            is_final = (
                isinstance(ann, ast.Subscript)
                and isinstance(ann.value, ast.Name)
                and ann.value.id == "Final"
            )
            if not is_final:
                violations.append(f"line {node.lineno} non-Final AnnAssign: {ast.dump(ann)[:60]}")
        elif isinstance(node, ast.Assign):
            target_names = {t.id for t in node.targets if isinstance(t, ast.Name)}
            # ``__all__`` is the only sanctioned ALL-CAPS-style plain Assign.
            if target_names == {"__all__"}:
                continue
            # Allow private type aliases (``_X = Literal[...]``) when the RHS
            # is a non-Call expression — type aliases are immutable shared
            # type information, not mutable state.
            rhs_contains_call = any(isinstance(n, ast.Call) for n in ast.walk(node.value))
            all_private = all(name.startswith("_") for name in target_names)
            if all_private and not rhs_contains_call:
                continue
            violations.append(f"line {node.lineno} mutable module-level Assign to {target_names}")
    assert violations == [], f"sanitizer.py has mutable module-level state: {violations}"


# --- AC-23(c) — ``verify_cassette`` is the only function touching I/O ----


_IO_NAMES = frozenset({"Path", "open", "yaml"})


def _io_references_outside(source: str, allowed_function: str) -> list[str]:
    """Return every reference to ``Path`` / ``open`` / ``yaml`` (as a
    name OR an attribute root) that appears inside a function body other
    than ``allowed_function``.
    """
    out: list[str] = []
    for name, fn in _function_defs(source).items():
        if name == allowed_function:
            continue
        for node in ast.walk(fn):
            # Plain name reference (e.g., ``Path(...)`` / ``open(...)`` / ``yaml.safe_load(...)``)
            if isinstance(node, ast.Name) and node.id in _IO_NAMES:
                out.append(f"{name}:{node.lineno} {node.id}")
    return out


def test_only_verify_cassette_touches_io() -> None:
    """``verify_cassette`` is the only function referencing Path / open / yaml."""
    source = _SANITIZER_SOURCE.read_text("utf-8")
    violations = _io_references_outside(source, allowed_function="verify_cassette")
    assert violations == [], f"I/O reference leaked outside verify_cassette: {violations}"


@pytest.mark.parametrize(
    "snippet",
    [
        "def other():\n    return open('x').read()\n",
        "def other():\n    return yaml.safe_load('x')\n",
        "def other():\n    return Path('x')\n",
    ],
)
def test_io_scanner_catches_each_planted_leak(snippet: str) -> None:
    """Planted-positive — the same scanner catches every I/O leak."""
    assert _io_references_outside(snippet, allowed_function="verify_cassette") != []
