"""Phase 6 S2-02 AC-11 — AST fence over replay.py: no non-terminal ledger-state construction.

The integrity-policy gate must NOT pre-materialize any non-terminal
ledger state. The only state-class construction permitted in
``replay.py`` is ``FailedUnrecoverable`` (on the failure path) — the
hydrated path returns a typed ``Hydrated`` carrier of events; the
subgraph constructs the materialized state.

This is the structural defense behind ADR-0003's "no patch work
resumes" guarantee — the failure path cannot accidentally produce a
materialized non-terminal state that the subgraph would consume.
"""

from __future__ import annotations

import ast
import inspect

from codegenie.workflows import replay as replay_module

_FORBIDDEN_LEDGER_CONSTRUCTORS = {
    "NeedsPlan",
    "PlanReady",
    "PatchApplied",
    "GateFailedRetryable",
    "AwaitingHumanReview",
    "Completed",
}


def test_replay_module_constructs_no_non_terminal_ledger_states() -> None:
    tree = ast.parse(inspect.getsource(replay_module))
    bad: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in _FORBIDDEN_LEDGER_CONSTRUCTORS:
                bad.append(f"{node.func.id}() @ line {node.lineno}")
    assert not bad, (
        "AC-11: replay.py constructs non-terminal ledger-state variants — "
        "the verifier MUST NOT pre-materialize state on the failure path. "
        "Only FailedUnrecoverable construction is allowed:\n  - " + "\n  - ".join(sorted(set(bad)))
    )
