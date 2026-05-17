"""S5-05 — ``_check_runtime_trace_freshness`` purity + ``Final[str]`` audits.

Covers AC-3 (``Final[str]`` constants) and AC-4 (AST-walk purity audit).

The AST walk is the structural defense — source-grep is bypassable via
string concatenation; AST-walk is not.
"""

from __future__ import annotations

import ast
import inspect
import typing
from typing import Final, get_type_hints

from codegenie.probes.layer_c import runtime_trace as rt
from codegenie.probes.layer_c.runtime_trace import _check_runtime_trace_freshness

# ---------------------------------------------------------------------------
# AC-3 — ``Final[str]`` constants
# ---------------------------------------------------------------------------


_MSG_CONSTANT_NAMES: tuple[str, ...] = (
    "_MSG_UPSTREAM_UNAVAILABLE",
    "_MSG_NO_BUILT_IMAGE",
    "_MSG_NO_TRACE_RECORDED",
    "_MSG_SLICE_MALFORMED",
)


def test_all_message_constants_annotated_final_str() -> None:
    """Each ``_MSG_*`` is module-scope ``Final[str]`` so a typo flips the
    constant-pin test red at import time."""
    hints = get_type_hints(rt, include_extras=True)
    for name in _MSG_CONSTANT_NAMES:
        assert name in hints, f"{name!r} not found in module type hints"
        annotation = hints[name]
        # ``Final[str]`` is ``typing.Final[str]``; the typing inspection
        # returns the inner type after stripping ``Final``. Pydantic-style:
        # check that the annotation is recorded as Final via typing.get_origin.
        origin = typing.get_origin(annotation)
        args = typing.get_args(annotation)
        assert origin is Final, f"{name} annotation is not Final[...]: {annotation!r}"
        assert args == (str,), f"{name} is Final[{args!r}], expected Final[str]"


def test_message_constants_values_are_unique() -> None:
    """Avoid copy-paste regressions where two branches share a message
    — only AC-2(a) and (b) intentionally share ``_MSG_UPSTREAM_UNAVAILABLE``."""
    values = [getattr(rt, name) for name in _MSG_CONSTANT_NAMES]
    assert len(values) == len(set(values))


def test_message_constants_match_id_pattern() -> None:
    """Each message string is a stable identifier, not a free-form sentence
    (Phase 1 ADR-0007 ``^[a-z][a-z0-9_]*$`` for single-segment IDs)."""
    import re

    pattern = re.compile(r"^[a-z][a-z0-9_]*$")
    for name in _MSG_CONSTANT_NAMES:
        value = getattr(rt, name)
        assert pattern.match(value), f"{name}={value!r} does not match identifier pattern"


# ---------------------------------------------------------------------------
# AC-4 — AST-walk purity audit
# ---------------------------------------------------------------------------


_FORBIDDEN_ATTR_REFS: frozenset[tuple[str, str]] = frozenset(
    {
        ("datetime", "now"),
        ("datetime", "utcnow"),
        ("time", "time"),
        ("time", "monotonic"),
        ("time", "perf_counter"),
        ("os", "stat"),
        ("os", "getmtime"),
        ("Path", "stat"),
        ("Path", "exists"),
    }
)

_FORBIDDEN_FULL_DOTTED: frozenset[str] = frozenset(
    {
        "datetime.now",
        "datetime.datetime.now",
        "datetime.utcnow",
        "datetime.datetime.utcnow",
        "time.time",
        "time.monotonic",
        "time.perf_counter",
        "os.stat",
        "os.path.getmtime",
        "pathlib.Path.stat",
    }
)


def _dotted(node: ast.AST) -> str | None:
    """Render a chain of ``ast.Attribute`` / ``ast.Name`` as a dotted string."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        left = _dotted(node.value)
        if left is None:
            return None
        return f"{left}.{node.attr}"
    return None


def _function_body_ast() -> ast.FunctionDef:
    src = inspect.getsource(_check_runtime_trace_freshness)
    module = ast.parse(src)
    fn = next(
        node
        for node in ast.walk(module)
        if isinstance(node, ast.FunctionDef) and node.name == "_check_runtime_trace_freshness"
    )
    return fn


def test_function_body_has_no_clock_or_io_calls() -> None:
    fn = _function_body_ast()
    for sub in ast.walk(fn):
        if isinstance(sub, ast.Attribute):
            dotted = _dotted(sub)
            if dotted is None:
                continue
            # The function uses ``_dt.datetime.fromisoformat``; that's a
            # pure parse, NOT a clock read. Skip ``fromisoformat`` arms.
            if dotted.endswith(".fromisoformat"):
                continue
            for forbidden in _FORBIDDEN_FULL_DOTTED:
                # Allow suffix match because the module alias is ``_dt``.
                assert not dotted.endswith(forbidden), (
                    f"forbidden clock/IO call observed: {dotted!r}"
                )


def test_function_body_has_no_await_or_subprocess() -> None:
    fn = _function_body_ast()
    for sub in ast.walk(fn):
        # No await — synchronous function only.
        assert not isinstance(sub, ast.Await), "await found in freshness function"
        # No subprocess invocations.
        if isinstance(sub, ast.Attribute):
            dotted = _dotted(sub)
            if dotted is None:
                continue
            assert not dotted.startswith("subprocess.")
            assert not dotted.startswith("asyncio.create_subprocess")
            assert not dotted.endswith(".run_allowlisted")
            assert not dotted.endswith(".run_external_cli")


def test_function_body_is_pure_no_assignments_to_outer_state() -> None:
    """No nonlocal / global statements; no mutation of module-level names."""
    fn = _function_body_ast()
    for sub in ast.walk(fn):
        assert not isinstance(sub, (ast.Global, ast.Nonlocal))
