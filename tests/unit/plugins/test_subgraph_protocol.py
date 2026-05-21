"""S6-03 — SubgraphNode Protocol + SubgraphState + canonical-site reconciliation.

Covers AC-1..AC-20 of
``docs/phases/03-vuln-deterministic-recipe/stories/S6-03-subgraph-node-protocol.md``
that are observable at runtime. The ``assert_never`` type-time exhaustiveness
(AC-19) is fenced by the subprocess-mypy meta-test in
``test_subgraph_mypy_negative.py``.
"""

from __future__ import annotations

from typing import assert_never

import pytest
from pydantic import TypeAdapter, ValidationError

from codegenie.plugins.subgraph import (
    Advance,
    Escalate,
    NodeTransition,
    ShortCircuit,
    SubgraphNode,
    SubgraphState,
)
from codegenie.transforms.outcomes import (
    RemediationError,
    RemediationFailed,
    RemediationOutcome,
)
from codegenie.types.identifiers import CveId, ErrorId, WorkflowId


def _minimal_subgraph_state() -> SubgraphState:
    return SubgraphState(
        workflow_id=WorkflowId("01HFEEDFACE0000000000000000"),
        cve=CveId("CVE-2024-21501"),
    )


def _failed_outcome() -> RemediationOutcome:
    return RemediationFailed(
        error=RemediationError(
            error_id=ErrorId("test.stub"),
            message="stub failure for tests",
        ),
    )


class _AdvanceNode:
    async def run(self, state: SubgraphState) -> NodeTransition:
        return Advance(state=state.model_copy(update={}))


class _ShortCircuitNode:
    async def run(self, state: SubgraphState) -> NodeTransition:
        return ShortCircuit(outcome=_failed_outcome())


class _EscalateNode:
    async def run(self, state: SubgraphState) -> NodeTransition:
        return Escalate(reason="filesystem_race")


class _MissingRunNode:
    async def evaluate(self, state: SubgraphState) -> NodeTransition: ...


class _SyncRunNode:
    def run(self, state: SubgraphState) -> NodeTransition:  # not async
        return Advance(state=state)


# AC-3 — re-exports are class-identity with the canonical outcomes site.
def test_re_exports_are_identity_with_outcomes() -> None:
    from codegenie.plugins.subgraph import Advance as PA
    from codegenie.plugins.subgraph import Escalate as PE
    from codegenie.plugins.subgraph import NodeTransition as PN
    from codegenie.plugins.subgraph import ShortCircuit as PS
    from codegenie.transforms.outcomes import Advance as OA
    from codegenie.transforms.outcomes import Escalate as OE
    from codegenie.transforms.outcomes import NodeTransition as ON
    from codegenie.transforms.outcomes import ShortCircuit as OS

    assert PA is OA
    assert PS is OS
    assert PE is OE
    assert PN is ON


# AC-2 — __all__ is the exact 6-name public surface.
def test_all_is_exact_set() -> None:
    import codegenie.plugins.subgraph as sg

    assert set(sg.__all__) == {
        "SubgraphNode",
        "SubgraphState",
        "NodeTransition",
        "Advance",
        "ShortCircuit",
        "Escalate",
    }


# AC-4 — SubgraphNode is a @runtime_checkable single-method Protocol.
def test_subgraph_node_is_runtime_checkable_single_method_protocol() -> None:
    assert getattr(SubgraphNode, "_is_protocol", False) is True
    assert getattr(SubgraphNode, "_is_runtime_protocol", False) is True
    members = {
        name
        for name in set(dir(SubgraphNode)) | set(getattr(SubgraphNode, "__annotations__", {}))
        if not name.startswith("_")
    }
    assert members == {"run"}


# AC-5 — a duck-typed node passes isinstance without explicit inheritance.
def test_protocol_is_runtime_checkable() -> None:
    assert isinstance(_AdvanceNode(), SubgraphNode)
    assert isinstance(_ShortCircuitNode(), SubgraphNode)
    assert isinstance(_EscalateNode(), SubgraphNode)
    assert _AdvanceNode.__mro__[1:] == (object,)  # no explicit Protocol inheritance


# AC-6 — a class missing `run` fails isinstance.
def test_missing_run_fails_isinstance() -> None:
    assert not isinstance(_MissingRunNode(), SubgraphNode)


# AC-7 — PEP 544 limitation: a sync `run` still passes runtime isinstance.
def test_sync_run_passes_runtime_isinstance_pep544_limitation() -> None:
    """Protocol cannot structurally distinguish sync from async at runtime.

    The actual sync/async enforcement is mypy --strict (see
    test_subgraph_mypy_negative.py). This test documents the runtime
    behaviour so a future contributor doesn't try to over-strengthen the
    runtime check.
    """
    assert isinstance(_SyncRunNode(), SubgraphNode) is True


async def test_advance_returns_advance_variant() -> None:
    transition = await _AdvanceNode().run(_minimal_subgraph_state())
    assert isinstance(transition, Advance)
    assert transition.kind == "advance"


async def test_short_circuit_returns_short_circuit_variant() -> None:
    transition = await _ShortCircuitNode().run(_minimal_subgraph_state())
    assert isinstance(transition, ShortCircuit)
    assert transition.kind == "short_circuit"


async def test_escalate_returns_escalate_variant() -> None:
    transition = await _EscalateNode().run(_minimal_subgraph_state())
    assert isinstance(transition, Escalate)
    assert transition.kind == "escalate"
    assert transition.reason == "filesystem_race"


# AC-20 — runtime exhaustiveness over the three-arm outer loop.
async def test_subgraph_outer_loop_match_exhaustive_at_runtime() -> None:
    nodes: list[SubgraphNode] = [_AdvanceNode(), _ShortCircuitNode(), _EscalateNode()]
    seen: set[str] = set()
    for node in nodes:
        transition = await node.run(_minimal_subgraph_state())
        match transition:
            case Advance(state=s):
                seen.add("advance")
                assert s.workflow_id == _minimal_subgraph_state().workflow_id
            case ShortCircuit(outcome=o):
                seen.add("short_circuit")
                assert isinstance(o, RemediationFailed)
            case Escalate(reason=r):
                seen.add("escalate")
                assert r in {
                    "plugin_extends_cycle",
                    "manifest_rejected",
                    "capability_missing",
                    "filesystem_race",
                    "subprocess_jail_unavailable",
                    "audit_chain_corrupted",
                    "vuln_index_corrupted",
                }
            case _ as unexpected:
                assert_never(unexpected)
    assert seen == {"advance", "short_circuit", "escalate"}


# AC-9 / AC-10 — SubgraphState is frozen.
def test_subgraph_state_is_frozen() -> None:
    s = _minimal_subgraph_state()
    with pytest.raises(ValidationError):
        s.workflow_id = WorkflowId("other")  # type: ignore[misc]


# AC-9 — required fields raise when omitted.
def test_subgraph_state_requires_workflow_id_and_cve() -> None:
    with pytest.raises(ValidationError):
        SubgraphState()  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        SubgraphState(workflow_id=WorkflowId("x"))  # type: ignore[call-arg]


# AC-9 — accumulator fields default to None.
def test_subgraph_state_accumulator_fields_default_none() -> None:
    s = _minimal_subgraph_state()
    assert s.resolution is None
    assert s.bundle is None
    assert s.recipe_outcome is None
    assert s.transform is None
    assert s.trust_outcome is None
    assert s.branch is None


# AC-11 — model_copy(update={...}) preserves field types.
def test_subgraph_state_model_copy_preserves_workflow_id_and_cve() -> None:
    s = _minimal_subgraph_state()
    s2 = s.model_copy(update={"cve": CveId("CVE-9999-9999")})
    assert isinstance(s2, SubgraphState)
    assert s2.workflow_id == s.workflow_id
    assert s2.cve == CveId("CVE-9999-9999")
    assert s2.resolution is None


# AC-14 — Advance carries a SubgraphState payload.
def test_advance_carries_subgraph_state() -> None:
    s = _minimal_subgraph_state()
    a = Advance(state=s)
    assert a.state is s
    assert a.kind == "advance"


# AC-15 — Advance rejects non-SubgraphState payloads (the primitive-dict
# variant is fully replaced, not unioned).
@pytest.mark.parametrize("bad", [{"k": 1}, [1, 2], None, 42, "string"])
def test_advance_rejects_non_subgraph_state_payload(bad: object) -> None:
    with pytest.raises(ValidationError):
        Advance(state=bad)  # type: ignore[arg-type]


# AC-15 — Advance round-trips a SubgraphState through the union adapter.
def test_advance_round_trips_subgraph_state() -> None:
    s = _minimal_subgraph_state()
    a = Advance(state=s)
    adapter = TypeAdapter(NodeTransition)
    decoded = adapter.validate_json(adapter.dump_json(a))
    assert isinstance(decoded, Advance)
    assert decoded.state.workflow_id == s.workflow_id
    assert decoded.state.cve == s.cve


# AC-17 — unknown escalation reason rejected.
def test_escalate_rejects_unknown_reason() -> None:
    with pytest.raises(ValidationError):
        Escalate(reason="bogus_reason")  # type: ignore[arg-type]


# AC-18 — each new in-subgraph reason constructs.
@pytest.mark.parametrize(
    "reason",
    [
        "filesystem_race",
        "subprocess_jail_unavailable",
        "audit_chain_corrupted",
        "vuln_index_corrupted",
    ],
)
def test_escalate_accepts_in_subgraph_reasons(reason: str) -> None:
    e = Escalate(reason=reason)  # type: ignore[arg-type]
    assert e.reason == reason


# AC-12 — module imports cleanly (build-order tolerance).
def test_subgraph_module_imports_without_trust_scorer() -> None:
    """The TrustOutcome forward reference must not make this module's import
    depend on a not-yet-merged S6-02; the module imports cleanly today."""
    import importlib

    mod = importlib.import_module("codegenie.plugins.subgraph")
    assert hasattr(mod, "SubgraphState")
    assert hasattr(mod, "SubgraphNode")
