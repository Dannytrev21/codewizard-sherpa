"""Phase-4 S3-02 AC-12 — the adapter must never mint prompt newtypes.

S2-04 pins :class:`PromptBuilder` as the sole minting site for
:data:`TrustedPrompt` and :data:`FencedPromptBody`. The malformed-output
retry needs to append a trusted suffix to the SDK request user content;
it must do so as plain ``str`` concatenation, not by re-constructing a
:data:`FencedPromptBody` (which would break the sole-mint invariant).

AST source-scan: every ``ast.Call`` whose function name is
``TrustedPrompt`` or ``FencedPromptBody`` in the adapter source is a
violation.
"""

from __future__ import annotations

import ast
import pathlib
from typing import Final

import codegenie

_ADAPTER: Final[pathlib.Path] = (
    pathlib.Path(codegenie.__file__).parent / "fallback" / "leaf" / "anthropic_adapter.py"
)
_FORBIDDEN_CTORS: Final[frozenset[str]] = frozenset({"TrustedPrompt", "FencedPromptBody"})


def test_adapter_does_not_mint_prompt_newtypes() -> None:
    """AC-12 — no ``TrustedPrompt(...)`` / ``FencedPromptBody(...)`` calls in
    the adapter source."""
    tree = ast.parse(_ADAPTER.read_text(encoding="utf-8"))
    offenders: list[str] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in _FORBIDDEN_CTORS
        ):
            offenders.append(f"{node.func.id}(...) at line {node.lineno}")
    assert not offenders, (
        "AnthropicLeafAdapter must not mint TrustedPrompt / FencedPromptBody — "
        f"PromptBuilder is the sole-mint site (S2-04). Offenders: {offenders}"
    )
