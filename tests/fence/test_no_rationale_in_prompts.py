"""Phase 4 S1-02 — AC-9 skeleton: rationale stays out of prompts.

ADR-0001 §Consequences: ``PlanProposal.rationale`` is **audit-log-only**; it
must never re-enter an LLM prompt (every consumer reads rationale only to log
it). This AST guard walks ``src/codegenie/fallback/`` for f-string interpolations
that pull ``.rationale`` into a string literal — the easiest way to accidentally
re-prompt.

F19 caveat: this skeleton catches only f-strings (``ast.JoinedStr``). The
``S2-04 PromptBuilder`` story MUST extend it to ``str.format`` and
``%``-formatting before declaring the guard production-ready.
"""

from __future__ import annotations

import ast
import pathlib

import codegenie

_ROOT = pathlib.Path(codegenie.__file__).parent / "fallback"


def test_rationale_does_not_flow_into_prompt_strings() -> None:
    if not _ROOT.exists():
        return
    offenders: list[tuple[str, int]] = []
    for py in _ROOT.rglob("*.py"):
        tree = ast.parse(py.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.JoinedStr):
                for v in node.values:
                    if (
                        isinstance(v, ast.FormattedValue)
                        and isinstance(v.value, ast.Attribute)
                        and v.value.attr == "rationale"
                    ):
                        offenders.append((str(py), node.lineno))
    assert not offenders, f"PlanProposal.rationale must not re-enter prompts: {offenders}"
