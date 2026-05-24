"""Phase-4 S2-02 AC-6 — ``fence_pure`` is side-effect-free.

AST-walks the function body and asserts every resolvable ``ast.Call`` is in
the pure-allowlist (fail-closed). Mirrors the
``tests/unit/plugins/test_events.py`` ``ast.walk`` + ``ast.Call`` /
``ast.Attribute`` idiom — not brittle source-substring matching.

The companion denylist (`open`, ``os.*``, ``subprocess.*``, ``random.*``,
``secrets.*``, ``EventLog(``, ``emit_internal``, ``emit_spanning``,
``logging.*``, ``time.*``, ``datetime.now``, ``print``, ``sys.std*``)
is exercised via the same allowlist (anything not in the allowlist fails
the assertion). The allowlist is the source of truth; the denylist
documents what would specifically be caught.
"""

from __future__ import annotations

import ast
import inspect
from typing import Final

import codegenie.fallback.fence.wrapper as wrapper_module
from codegenie.fallback.fence.wrapper import fence_pure

# Calls fence_pure is permitted to make. Anything outside this set fails.
_PURE_ALLOWED_CALLS: Final[frozenset[str]] = frozenset(
    {
        # Module-private helper for codepoint-safe truncation.
        "_truncate_utf8_safe",
        # Constructors for the function's return + tagged-union types.
        "FencedSegment",
        "CanaryClean",
        "CanaryCollision",
        # Scanner Protocol — the injected port.
        "scanner.scan",
        # Stdlib pure idioms used by the function body.
        "len",
        "payload.encode",
        "isinstance",
        # Delimiter format strings live at module scope as ``_DELIM_*_FMT``.
        "_DELIM_OPEN_FMT.format",
        "_DELIM_CLOSE_FMT.format",
    }
)


def _resolve_call_name(node: ast.Call) -> str | None:
    """Return a dotted name for a ``Call`` node, or ``None`` if unresolved.

    Resolves ``f(x)``, ``a.b(x)``, ``a.b.c(x)``. Unresolved (e.g., a call
    on a subscripted expression) returns ``None`` and the test fails.
    """
    target = node.func
    parts: list[str] = []
    while True:
        if isinstance(target, ast.Name):
            parts.append(target.id)
            break
        if isinstance(target, ast.Attribute):
            parts.append(target.attr)
            target = target.value
            continue
        return None
    return ".".join(reversed(parts))


def test_fence_pure_only_calls_pure_allowlisted_names() -> None:
    source = inspect.getsource(fence_pure)
    tree = ast.parse(inspect.cleandoc(source))
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _resolve_call_name(node)
        if name is None:
            offenders.append(f"<unresolved call at line {node.lineno}>")
            continue
        if name not in _PURE_ALLOWED_CALLS:
            offenders.append(name)
    assert offenders == [], (
        f"fence_pure made impure or unknown calls: {sorted(set(offenders))}. "
        f"Allowed set: {sorted(_PURE_ALLOWED_CALLS)}."
    )


def test_fence_pure_module_does_not_import_io_or_logging() -> None:
    """Even allowlisted at call time, the module must not import I/O surfaces."""
    forbidden_import_roots = frozenset(
        {
            "logging",
            "subprocess",
            "socket",
            "urllib",
            "requests",
            "httpx",
            "aiohttp",
            "os.path",
        }
    )
    source = inspect.getsource(wrapper_module)
    tree = ast.parse(source)
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in forbidden_import_roots:
                    offenders.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            root = node.module.split(".")[0]
            if node.module in forbidden_import_roots or root in forbidden_import_roots:
                offenders.append(node.module)
    assert offenders == [], (
        f"codegenie.fallback.fence.wrapper imported forbidden I/O modules: {offenders}"
    )


def test_fence_pure_signature_is_stdlib_plus_pydantic_only() -> None:
    """The function must not accept any spend surface as a parameter."""
    sig = inspect.signature(fence_pure)
    parameter_names = set(sig.parameters)
    assert parameter_names == {"payload", "nonce", "source_kind", "scanner"}
    forbidden_names = {"event_log", "token", "budget", "guard", "logger", "clock"}
    assert forbidden_names.isdisjoint(parameter_names)
