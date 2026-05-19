"""Documented bypass shapes for the Phase-3 ``Any`` annotation fence.

Each shape below is a known limitation of ``codegenie._phase3_fence`` — the
walker either does not descend into the context where ``Any`` appears
(type-comments are stored on a separate attribute), or the symbol is
aliased so the visitor's name check misses it.

These files are NOT under ``src/codegenie/`` and are therefore outside the
walker's live scope. They exist so ``tests/fence/test_no_any_in_plugin_surface.py``
can prove each bypass is real (otherwise we'd be leaning on a stale
``KNOWN_BYPASSES`` constant — Rule 12, fail loud).

Tracking: each entry corresponds to one key in
``codegenie._phase3_fence.KNOWN_BYPASSES``. If the walker grows the ability
to catch one, remove both the bypass entry here and the matching
``KNOWN_BYPASSES`` member in the same PR.
"""

from __future__ import annotations

from typing import Any as _Any  # aliased — walker's name check misses this  # noqa: F401

# Type-comment annotation — stored on ``ast.AnnAssign.type_comment`` (PEP 484
# legacy syntax) when ``ast.parse(..., type_comments=True)``; current walker
# uses default ``type_comments=False``. KNOWN_BYPASSES key: ``type-comment-annotation``.
type_comment_bypass = {}  # type: dict[str, Any]

# Aliased import via stdlib ``typing``. KNOWN_BYPASSES key:
# ``from-typing-import-any-as-alias``. Step-1 PRs introducing this aliasing
# fail review by convention (ADR-0011 CODEOWNERS anchor).
aliased_bypass: _Any = 1
