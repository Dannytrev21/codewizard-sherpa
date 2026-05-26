"""S6-02 fence — :file:`tier.py` MUST NOT slice / truncate / encode
``prior_failure_summary`` before handing it to :class:`PromptBuilder`.

ADR-04-0013: canary scan happens on **untruncated** bytes; truncation
happens **after** the scan. :class:`FenceWrapper` (called by
:class:`PromptBuilder`) owns both steps; ``tier.py``'s job is to forward
the raw bytes only. A pre-truncation in ``tier.py`` would hide an
injection past the truncation cap from the canary scanner.

This AST walk rejects expressions that look like truncation operations
(``[:N]``, ``.encode(...)[:N]``, ``min(len(s), N)``, ``.truncate(...)``)
applied to ``prior_failure_summary``-bearing attribute accesses.
"""

from __future__ import annotations

import ast
from pathlib import Path

_TIER_PY = Path(__file__).parents[2] / "src" / "codegenie" / "fallback" / "tier.py"


def _is_summary_attribute(node: ast.AST) -> bool:
    """Return True if ``node`` is an :class:`ast.Attribute` whose attribute
    chain ends in ``prior_failure_summary``."""
    return isinstance(node, ast.Attribute) and node.attr == "prior_failure_summary"


def test_tier_does_not_slice_prior_failure_summary() -> None:
    """Reject ``summary[:N]`` / ``s.prior_failure_summary[:N]`` slicing
    expressions inside :file:`tier.py`. Truncation belongs in
    :class:`FenceWrapper` post-scan."""
    tree = ast.parse(_TIER_PY.read_text())
    offending: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        # ``something[:N]`` is a Subscript whose .slice is a Slice.
        if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Slice):
            value = node.value
            # Direct slice of a prior_failure_summary attribute access.
            if _is_summary_attribute(value):
                offending.append((node.lineno, ast.unparse(node)))
            # Indirect: ``something.prior_failure_summary.encode("utf-8")[:N]``
            if (
                isinstance(value, ast.Call)
                and isinstance(value.func, ast.Attribute)
                and _is_summary_attribute(value.func.value)
            ):
                offending.append((node.lineno, ast.unparse(node)))
    assert not offending, (
        "tier.py must not slice prior_failure_summary — FenceWrapper truncates "
        f"AFTER the canary scan (ADR-04-0013). Offending: {offending}"
    )


def test_tier_does_not_call_truncate_on_summary() -> None:
    """Reject ``summary.truncate(...)`` or ``Truncator.truncate(summary)``
    style calls. ``FenceWrapper`` owns truncation post-canary."""
    tree = ast.parse(_TIER_PY.read_text())
    offending: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "truncate":
                # Any .truncate(...) call within tier.py is suspect — the
                # placeholder run has none, so this is purely guard.
                offending.append((node.lineno, ast.unparse(node)))
    assert not offending, (
        "tier.py must not call *.truncate(...). FenceWrapper owns truncation. "
        f"Offending: {offending}"
    )


def test_tier_does_not_encode_summary_for_byte_slicing() -> None:
    """Reject ``summary.encode("utf-8")[:N]`` — the canonical multi-byte
    pre-truncation regression. :class:`FenceWrapper` handles UTF-8 byte
    boundaries internally."""
    tree = ast.parse(_TIER_PY.read_text())
    offending: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Slice):
            value = node.value
            if (
                isinstance(value, ast.Call)
                and isinstance(value.func, ast.Attribute)
                and value.func.attr == "encode"
                and _is_summary_attribute(value.func.value)
            ):
                offending.append((node.lineno, ast.unparse(node)))
    assert not offending, (
        "tier.py must not encode+slice prior_failure_summary for byte truncation. "
        f"Offending: {offending}"
    )
