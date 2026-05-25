"""Phase 6 S1-02 AC-6 — cross-story membership equality for the terminal partition.

S1-01 (``codegenie.workflows.vuln_sut``) pins the *public* Result's
``TerminalState`` Literal at three values:
``{"completed", "awaiting_human_review", "failed_unrecoverable"}``.
S1-02 (``codegenie.workflows.vuln_ledger``) pins the *internal*
seven-variant ledger sum type whose terminal partition MUST agree with
S1-01 byte-for-byte. A future drift like adding ``cancelled`` to one
side but not the other silently breaks the public Result invariant.

This test pulls both sources and asserts membership byte-equality. On
failure, prints the canonical reconciliation directive.
"""

from __future__ import annotations

from typing import get_args

from codegenie.workflows.vuln_ledger import _TERMINAL_LEDGER_KINDS
from codegenie.workflows.vuln_sut import TerminalState

_EXPECTED = frozenset({"completed", "awaiting_human_review", "failed_unrecoverable"})

_DIRECTIVE = (
    "Phase-6 ledger / SUT terminal-state drift. The seven-variant ledger "
    "universe (vuln_ledger.py) and the public Result's TerminalState Literal "
    "(vuln_sut.py) must agree on the terminal partition. Adding or removing "
    "a terminal kind is an ADR-0001 + ADR-0003 amendment; touching one without "
    "the other is forbidden."
)


def test_ac6_terminal_partition_byte_equal_across_s1_01_and_s1_02() -> None:
    ts_set = set(get_args(TerminalState))
    assert ts_set == set(_TERMINAL_LEDGER_KINDS) == _EXPECTED, _DIRECTIVE


def test_ac6_non_terminal_kinds_absent_from_terminal_state() -> None:
    non_terminal = {
        "needs_plan",
        "plan_ready",
        "patch_applied",
        "gate_failed_retryable",
    }
    ts_set = set(get_args(TerminalState))
    for k in non_terminal:
        assert k not in ts_set, _DIRECTIVE
