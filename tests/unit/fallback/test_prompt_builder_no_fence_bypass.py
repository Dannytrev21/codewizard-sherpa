"""Phase-4 S2-04 AC-13 — ``PromptBuilder`` is a composer, never a fence.

AST-walks ``src/codegenie/fallback/fence/prompt_builder.py`` and fails if the
module:

- constructs :class:`FencedSegment`, :class:`CanaryClean`, or
  :class:`CanaryCollision` directly;
- imports or calls :class:`CanaryGuard.scan`, :func:`scan_pure`,
  :func:`fence_pure`, or the private ``_TRUNCATION_CAPS`` table;
- embeds the delimiter literals ``<UNTRUSTED_INPUT`` or ``</UNTRUSTED_INPUT``.

``PromptBuilder`` may only call ``self.fence.fence(...)`` for untrusted
payloads. The structural guard keeps the builder a composition shell over
S2-02 (``FenceWrapper``) and S2-03 (``CanaryGuard``) instead of forking a
second fence implementation.
"""

from __future__ import annotations

import ast
from pathlib import Path

_PROMPT_BUILDER_PATH = Path("src/codegenie/fallback/fence/prompt_builder.py")

# Direct constructions (``Call(func=Name(id=...))``) the builder must not make.
_FORBIDDEN_CONSTRUCTIONS = frozenset(
    {
        "FencedSegment",
        "CanaryClean",
        "CanaryCollision",
    }
)

# Names that, if imported into the builder, would unlock a fence bypass.
_FORBIDDEN_IMPORTS = frozenset(
    {
        "scan_pure",
        "fence_pure",
        "CanaryGuard",
        "_TRUNCATION_CAPS",
    }
)

# Delimiter literals (substrings — the per-nonce open/close forms expand at
# runtime, so checking the prefix is sufficient and stable).
_FORBIDDEN_LITERAL_SUBSTRINGS = (
    "<UNTRUSTED_INPUT",
    "</UNTRUSTED_INPUT",
)


def _module_tree() -> ast.AST:
    assert _PROMPT_BUILDER_PATH.exists(), (
        f"PromptBuilder module must exist before the no-bypass scan — "
        f"missing {_PROMPT_BUILDER_PATH}."
    )
    return ast.parse(_PROMPT_BUILDER_PATH.read_text(encoding="utf-8"))


def test_no_direct_construction_of_fence_or_canary_types() -> None:
    """AC-13: forbid ``FencedSegment(...)``, ``CanaryClean(...)``, ``CanaryCollision(...)``."""
    tree = _module_tree()
    hits: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in _FORBIDDEN_CONSTRUCTIONS:
                hits.append((node.func.id, node.lineno))
    assert hits == [], (
        f"PromptBuilder must not construct fence/canary types directly: "
        f"{hits}. Use ``self.fence.fence(...)`` for untrusted payloads."
    )


def test_no_imports_of_pure_helpers_or_truncation_caps() -> None:
    """AC-13: pure-helpers / ``CanaryGuard`` / ``_TRUNCATION_CAPS`` not imported here."""
    tree = _module_tree()
    bad: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name in _FORBIDDEN_IMPORTS:
                    bad.append(alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in _FORBIDDEN_IMPORTS:
                    bad.append(alias.name)
    assert bad == [], (
        f"PromptBuilder must not import {bad} — bypassing FenceWrapper "
        f"breaks the functional-core/imperative-shell split."
    )


def test_no_direct_call_to_canary_guard_scan() -> None:
    """AC-13: even via an attribute, ``CanaryGuard.scan`` must not be called here."""
    tree = _module_tree()
    bad: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "scan" and isinstance(node.func.value, ast.Name):
                if node.func.value.id in {"CanaryGuard", "scanner"}:
                    bad.append((node.func.value.id + ".scan", node.lineno))
    assert bad == [], f"PromptBuilder must not invoke ``CanaryGuard.scan`` directly: {bad}."


def test_no_delimiter_literals_embedded() -> None:
    """AC-13: the ``<UNTRUSTED_INPUT`` open/close literals must not appear in the source.

    ``FenceWrapper`` is the sole owner of delimiter assembly — duplicating
    those bytes here would let a future edit drift the two surfaces apart
    without the import-time test catching it.
    """
    source = _PROMPT_BUILDER_PATH.read_text(encoding="utf-8")
    # The literals appear only inside the module docstring's reference to
    # the no-bypass test text below — exclude this very test's path. The
    # builder module never references the literals.
    for needle in _FORBIDDEN_LITERAL_SUBSTRINGS:
        assert needle not in source, (
            f"PromptBuilder source contains forbidden delimiter literal {needle!r}. "
            f"Delegate to ``self.fence.fence(...)``."
        )
