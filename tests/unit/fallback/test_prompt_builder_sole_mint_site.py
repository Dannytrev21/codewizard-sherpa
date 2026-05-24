"""Phase-4 S2-04 — AST-walking sole-mint test for ``TrustedPrompt`` and
``FencedPromptBody``.

ADR-0013 §Decision pins ``PromptBuilder`` as the **only** site that may
construct these two newtypes. This test walks every ``.py`` file under
``src/codegenie/`` with :mod:`ast` and asserts no module other than
``src/codegenie/fallback/fence/prompt_builder.py`` contains a ``Call`` whose
``func`` is ``TrustedPrompt`` or ``FencedPromptBody``.

A positive-control test (``test_positive_control_forged_minter_is_caught_by_visitor``)
parses ``tests/fixtures/violators/forged_prompt_mint.py`` and asserts the
visitor *would* flag it — guards against the AST walk silently breaking and
declaring an empty walk a pass.

Caveat: the visitor catches direct ``TrustedPrompt(...)`` / ``FencedPromptBody(...)``
calls but **not** reflective constructions like ``globals()["TrustedPrompt"](...)``
or ``getattr(module, "TrustedPrompt")(...)``. These are out of scope here —
the ``forbidden-patterns`` pre-commit hook already bans ``eval(``, ``exec(``,
and ``__import__(`` repo-wide.
"""

from __future__ import annotations

import ast
from pathlib import Path

_SRC_ROOT = Path("src/codegenie")
_ALLOWED_MINTER = _SRC_ROOT / "fallback" / "fence" / "prompt_builder.py"
_FORBIDDEN_NEWTYPES = frozenset({"TrustedPrompt", "FencedPromptBody"})


def _calls_to_newtype(tree: ast.AST, names: frozenset[str]) -> list[tuple[str, int]]:
    """Return ``(name, lineno)`` for every ``Call(func=Name(id in names))`` in ``tree``."""
    hits: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in names:
                hits.append((node.func.id, node.lineno))
    return hits


def test_only_prompt_builder_mints_trusted_prompt_and_fenced_body() -> None:
    """AC-3: the AST walk under ``src/codegenie/`` finds zero forbidden mint sites.

    Asserts ``_ALLOWED_MINTER.exists()`` first so an empty walk cannot pass
    before the module is shipped.
    """
    assert _ALLOWED_MINTER.exists(), (
        f"PromptBuilder module must exist before the scan runs — missing {_ALLOWED_MINTER}."
    )
    violations: list[tuple[Path, str, int]] = []
    for py in _SRC_ROOT.rglob("*.py"):
        if py == _ALLOWED_MINTER:
            continue
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for name, lineno in _calls_to_newtype(tree, _FORBIDDEN_NEWTYPES):
            violations.append((py, name, lineno))
    assert violations == [], (
        f"Found {len(violations)} forbidden mint sites — "
        f"only {_ALLOWED_MINTER} may construct TrustedPrompt / FencedPromptBody.\n"
        + "\n".join(f"  {p}:{ln} -> {n}(...)" for p, n, ln in violations)
    )


def test_positive_control_forged_minter_is_caught_by_visitor() -> None:
    """AC-3: a deliberate forged minter under ``tests/fixtures/violators/`` is flagged.

    If this passes vacuously, the AST visitor is broken — the sole-mint test
    above would also pass against any future violator.
    """
    forged = Path("tests/fixtures/violators/forged_prompt_mint.py")
    assert forged.exists(), (
        f"Positive-control fixture must exist at {forged} — without it the "
        f"sole-mint visitor has no regression guard."
    )
    tree = ast.parse(forged.read_text(encoding="utf-8"))
    hits = _calls_to_newtype(tree, _FORBIDDEN_NEWTYPES)
    assert len(hits) >= 1, (
        "Positive control failed: visitor did not flag a deliberate violator. "
        "If this passes, the AST walk is broken and the sole-mint test above "
        "is a tautology."
    )
