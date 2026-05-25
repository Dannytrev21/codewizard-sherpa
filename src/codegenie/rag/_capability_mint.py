"""Phase-4-local mint shim for :class:`SolvedExampleWriteCapability`.

Private, single-purpose module. The lint boundary that pins its scope is
the ``pyproject.toml`` ``[tool.importlinter.contracts]`` forbidden row
``"ADR-0016: phase4 solved-example mint module is scoped"``: every
:mod:`codegenie` module is forbidden from importing this one EXCEPT the
single allowed edge ``codegenie.rag.ingest -> codegenie.rag._capability_mint``.

The story's hardened design pulled the mint out of ``ingest.py`` because
``import-linter`` is module-level — it cannot forbid the import of a
single function inside a public module while still allowing imports of
``ingest_solved_example``. A one-purpose private module *can* be
mechanically scoped (Notes-for-implementer §1).

This is **Phase-4-local**. The TODO is load-bearing: when Phase 5's
``GateRunner`` lands, the production mint becomes
``codegenie.gates._capability_mint.mint_solved_example_capability``, the
forbidden contract grows a second ``ignore_imports`` edge, and this
shim is removed by the same change. Until then ``chain_head`` is
accepted at the boundary and intentionally discarded — S4-03's marker
carries only ``workflow_id``.
"""

from __future__ import annotations

from codegenie.rag.store import SolvedExampleWriteCapability
from codegenie.types.identifiers import ChainHead, WorkflowId


def _phase4_local_capability_mint(
    *,
    workflow_id: WorkflowId,
    chain_head: ChainHead,
) -> SolvedExampleWriteCapability:
    """Mint a Phase-4-local :class:`SolvedExampleWriteCapability`.

    ``chain_head`` is accepted to match the Phase-5 mint signature so
    callers can be ported by removing one import rather than editing
    every call site. It is intentionally discarded here because S4-03's
    marker carries only ``workflow_id``.

    TODO(phase-5): replace this shim with
    ``codegenie.gates._capability_mint.mint_solved_example_capability``
    once :class:`GateRunner` lands. Until then this is the sole mint
    surface and the forbidden contract above is the sole boundary.
    """
    del chain_head  # forward-compat placeholder; see docstring.
    return SolvedExampleWriteCapability(workflow_id=workflow_id)


__all__ = ["_phase4_local_capability_mint"]
