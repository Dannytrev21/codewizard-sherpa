"""Phase 6 S2-01 AC-7 — chain-forward extension + stability + isolation.

Three sub-properties, parametrized over both adapters
(:class:`InMemoryCheckpointStore` + :class:`SqliteCheckpointStore`):

* **stability** — ``tail_chain_head`` returns byte-equal output across
  two calls.
* **chain-forward extension** — the head after N appends equals the
  iterative fold of ``_compute_chain_head`` over the same sequence (a
  buggy store that swallows ``prior_head`` fails on ``min_size=2``).
* **cross-workflow isolation** — appends to ``workflow_A`` do not
  change ``tail_chain_head(workflow_B)``.

Mutation-resistance: a store that uses ``_GENESIS_CHAIN_HEAD`` for every
append (ignoring ``prior_head``) fails sub-property #2; a store that
shares chain heads across workflow_ids fails sub-property #3.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from codegenie.types.identifiers import ChainHead, WorkflowId
from codegenie.workflows._chain import _compute_chain_head
from codegenie.workflows.checkpoints import _GENESIS_CHAIN_HEAD, CheckpointStore
from tests.property._phase6_event_strategies import (
    ADAPTER_FACTORIES,
    ADAPTER_FACTORY_IDS,
    boundary_events_for_workflow,
)


@pytest.mark.parametrize("store_factory", ADAPTER_FACTORIES, ids=ADAPTER_FACTORY_IDS)
def test_ac7_tail_is_genesis_on_empty_workflow(
    store_factory: Callable[[Path], CheckpointStore], tmp_path: Path
) -> None:
    store = store_factory(tmp_path)
    try:
        wf = WorkflowId("01HZZZZZZZZZZZZZZZZZZZZZZZ")
        assert store.tail_chain_head(wf) == _GENESIS_CHAIN_HEAD
    finally:
        store.close()


# Module-level counter so each Hypothesis example gets a unique
# sub-directory under the test's ``tmp_path``. Across examples the
# SQLite store would otherwise see prior-example transition ids and
# raise UNIQUE constraint violations on shrunk re-tries.
_EXAMPLE_COUNTER = {"n": 0}


def _fresh_subdir(tmp_path: Path) -> Path:
    _EXAMPLE_COUNTER["n"] += 1
    sub = tmp_path / f"ex{_EXAMPLE_COUNTER['n']}"
    sub.mkdir(parents=True, exist_ok=True)
    return sub


@given(data=st.data())
@settings(
    max_examples=15,
    deadline=None,
    suppress_health_check=(HealthCheck.function_scoped_fixture,),
)
@pytest.mark.parametrize("store_factory", ADAPTER_FACTORIES, ids=ADAPTER_FACTORY_IDS)
def test_ac7_chain_forward_extension(
    store_factory: Callable[[Path], CheckpointStore],
    tmp_path: Path,
    data: st.DataObject,
) -> None:
    """``tail_chain_head`` after N appends == iterative ``_compute_chain_head``."""
    store = store_factory(_fresh_subdir(tmp_path))
    try:
        wf = WorkflowId("01HZZZZZZZZZZZZZZZZZZZZZZZ")
        events = data.draw(
            st.lists(
                boundary_events_for_workflow(workflow_id=wf),
                min_size=1,
                max_size=8,
                unique_by=lambda e: e.transition_id,
            )
        )
        head: ChainHead = _GENESIS_CHAIN_HEAD
        for e in events:
            head = _compute_chain_head(head, e)
            store.append(e)
        # Stability — two reads must agree.
        first = store.tail_chain_head(wf)
        second = store.tail_chain_head(wf)
        assert first == second
        # Chain-forward extension — the persisted head matches the fold.
        assert first == head
    finally:
        store.close()


@given(data=st.data())
@settings(
    max_examples=10,
    deadline=None,
    suppress_health_check=(HealthCheck.function_scoped_fixture,),
)
@pytest.mark.parametrize("store_factory", ADAPTER_FACTORIES, ids=ADAPTER_FACTORY_IDS)
def test_ac7_cross_workflow_isolation(
    store_factory: Callable[[Path], CheckpointStore],
    tmp_path: Path,
    data: st.DataObject,
) -> None:
    """Appends to ``wf_a`` do not change ``tail_chain_head(wf_b)``."""
    store = store_factory(_fresh_subdir(tmp_path))
    try:
        wf_a = WorkflowId("01HZZZZZZZZZZZZZZZZZZZZZZA")
        wf_b = WorkflowId("01HZZZZZZZZZZZZZZZZZZZZZZB")
        baseline_b = store.tail_chain_head(wf_b)
        # Append to A
        a_events = data.draw(
            st.lists(
                boundary_events_for_workflow(workflow_id=wf_a),
                min_size=1,
                max_size=5,
                unique_by=lambda e: e.transition_id,
            )
        )
        for e in a_events:
            store.append(e)
        assert store.tail_chain_head(wf_b) == baseline_b
        # And the symmetric case
        b_events = data.draw(
            st.lists(
                boundary_events_for_workflow(workflow_id=wf_b),
                min_size=1,
                max_size=5,
                unique_by=lambda e: e.transition_id,
            )
        )
        head_a_before = store.tail_chain_head(wf_a)
        for e in b_events:
            store.append(e)
        assert store.tail_chain_head(wf_a) == head_a_before
    finally:
        store.close()
