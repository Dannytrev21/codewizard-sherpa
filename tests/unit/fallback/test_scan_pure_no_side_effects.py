"""Phase-4 S2-03 AC-3 — ``scan_pure`` is side-effect-free.

AST-walks the function body and asserts every resolvable ``ast.Call`` is in
the pure-allowlist (fail-closed). Mirrors the S2-02
``test_fence_pure_no_side_effects.py`` idiom. The allowlist — not a
denylist — is the source of truth: any call outside it fails the test.
"""

from __future__ import annotations

import ast
import inspect
from typing import Final

from codegenie.fallback.fence.canary import scan_pure
from codegenie.fallback.fence.wrapper import CanaryClean

# Calls ``scan_pure`` is permitted to make. Anything outside this set fails.
_PURE_ALLOWED_CALLS: Final[frozenset[str]] = frozenset(
    {
        "payload.encode",
        "encoded.lower",
        "pat.lower",
        "CanaryClean",
        "CanaryCollision",
    }
)


def _resolve_call_name(node: ast.Call) -> str | None:
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


def test_scan_pure_only_calls_pure_allowlisted_names() -> None:
    # ``inspect.cleandoc`` strips the body's indentation when the signature is
    # collapsed to a single line, producing ``IndentationError``. Top-level
    # functions are already column-0; raw source parses directly.
    source = inspect.getsource(scan_pure)
    tree = ast.parse(source)
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
        f"scan_pure made impure or unknown calls: {sorted(set(offenders))}. "
        f"Allowed set: {sorted(_PURE_ALLOWED_CALLS)}."
    )


def test_scan_pure_signature_is_payload_and_patterns_only() -> None:
    sig = inspect.signature(scan_pure)
    parameter_names = set(sig.parameters)
    assert parameter_names == {"payload", "patterns"}
    forbidden_names = {"event_log", "token", "budget", "guard", "logger", "clock", "nonce"}
    assert forbidden_names.isdisjoint(parameter_names)


def test_scan_pure_empty_payload_returns_clean() -> None:
    """AC-3 — empty payload is a real fast-path that must return CanaryClean."""
    result = scan_pure("", (("ignore_previous_instructions", b"ignore previous instructions"),))
    assert result == CanaryClean()
