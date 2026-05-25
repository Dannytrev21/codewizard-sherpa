"""Phase 6 S2-01 AC-8 — ``read_all_for_workflow`` returns events in append order.

Two properties, parametrized over both adapters:

* **append-order** — the returned sequence is byte-equal to the
  append-order list.
* **cross-workflow filter** — appending interleaved A/B events,
  ``read_all_for_workflow(wf_a)`` yields ONLY A events in A's
  append-order; ``read_all_for_workflow(wf_b)`` yields ONLY B events in
  B's append-order. A buggy store that filters by ``next_head`` index
  (unique but not append-ordered) is killed by the first property; a
  store that omits the workflow filter is killed by the second.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from codegenie.types.identifiers import WorkflowId
from codegenie.workflows.checkpoints import CheckpointStore
from tests.property._phase6_event_strategies import (
    ADAPTER_FACTORIES,
    ADAPTER_FACTORY_IDS,
    boundary_events_for_workflow,
)

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
def test_ac8_read_yields_append_order(
    store_factory: Callable[[Path], CheckpointStore],
    tmp_path: Path,
    data: st.DataObject,
) -> None:
    store = store_factory(_fresh_subdir(tmp_path))
    try:
        wf = WorkflowId("01HZZZZZZZZZZZZZZZZZZZZZZZ")
        events = data.draw(
            st.lists(
                boundary_events_for_workflow(workflow_id=wf),
                min_size=0,
                max_size=8,
                unique_by=lambda e: e.transition_id,
            )
        )
        for e in events:
            store.append(e)
        read_back = list(store.read_all_for_workflow(wf))
        assert read_back == events, (
            "read_all_for_workflow must yield events in append order; "
            "a store that sorts by transition_id or chain head fails here."
        )
    finally:
        store.close()


@given(data=st.data())
@settings(
    max_examples=10,
    deadline=None,
    suppress_health_check=(HealthCheck.function_scoped_fixture,),
)
@pytest.mark.parametrize("store_factory", ADAPTER_FACTORIES, ids=ADAPTER_FACTORY_IDS)
def test_ac8_cross_workflow_filter(
    store_factory: Callable[[Path], CheckpointStore],
    tmp_path: Path,
    data: st.DataObject,
) -> None:
    """Interleaved A/B appends; reads filter by workflow_id."""
    store = store_factory(_fresh_subdir(tmp_path))
    try:
        wf_a = WorkflowId("01HZZZZZZZZZZZZZZZZZZZZZZA")
        wf_b = WorkflowId("01HZZZZZZZZZZZZZZZZZZZZZZB")
        a_events = data.draw(
            st.lists(
                boundary_events_for_workflow(workflow_id=wf_a),
                min_size=1,
                max_size=4,
                unique_by=lambda e: e.transition_id,
            )
        )
        b_events = data.draw(
            st.lists(
                boundary_events_for_workflow(workflow_id=wf_b),
                min_size=1,
                max_size=4,
                unique_by=lambda e: e.transition_id,
            )
        )
        # Interleave append order: a0, b0, a1, b1, ...
        max_len = max(len(a_events), len(b_events))
        for i in range(max_len):
            if i < len(a_events):
                store.append(a_events[i])
            if i < len(b_events):
                store.append(b_events[i])
        assert list(store.read_all_for_workflow(wf_a)) == a_events
        assert list(store.read_all_for_workflow(wf_b)) == b_events
    finally:
        store.close()
