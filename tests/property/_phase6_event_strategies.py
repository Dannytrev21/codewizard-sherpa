"""Phase 6 S2-01 — shared Hypothesis strategies for checkpoint property tests.

Boundary-only events (every ``next_state_id`` is in
:data:`~codegenie.workflows.checkpoints._SEMANTIC_BOUNDARY_KINDS`) so the
parity / chain-forward / read-ordering tests do not collide with AC-4
boundary policy. Adapter-parametrize factories live here too.
"""

from __future__ import annotations

import string
from pathlib import Path
from typing import Final

from hypothesis import strategies as st

from codegenie.workflows.in_memory_checkpoints import InMemoryCheckpointStore
from codegenie.workflows.sqlite_checkpoints import SqliteCheckpointStore
from codegenie.workflows.vuln_ledger import TransitionEvent

_HEX: Final[str] = "0123456789abcdef"
_ULID_ALPHABET: Final[str] = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

# Only legal edges whose ``next_state_id`` is a semantic boundary.
BOUNDARY_LEGAL_PAIRS: Final[list[tuple[str, str]]] = [
    ("needs_plan", "plan_ready"),
    ("plan_ready", "patch_applied"),
    ("patch_applied", "completed"),
    ("plan_ready", "awaiting_human_review"),
    ("plan_ready", "failed_unrecoverable"),
    ("patch_applied", "gate_failed_retryable"),
    ("patch_applied", "awaiting_human_review"),
    ("patch_applied", "failed_unrecoverable"),
    ("gate_failed_retryable", "awaiting_human_review"),
    ("gate_failed_retryable", "failed_unrecoverable"),
    ("awaiting_human_review", "plan_ready"),
    ("awaiting_human_review", "completed"),
    ("awaiting_human_review", "failed_unrecoverable"),
]


def _ulid(draw: st.DrawFn) -> str:
    return "0" + "".join(draw(st.lists(st.sampled_from(_ULID_ALPHABET), min_size=25, max_size=25)))


@st.composite
def boundary_events_for_workflow(draw: st.DrawFn, workflow_id: str) -> TransitionEvent:
    """Draw a single boundary-only :class:`TransitionEvent` for ``workflow_id``."""
    prior, nxt = draw(st.sampled_from(BOUNDARY_LEGAL_PAIRS))
    transition_id = _ulid(draw)
    evidence = "".join(draw(st.lists(st.sampled_from(_HEX), min_size=64, max_size=64)))
    head = "".join(draw(st.lists(st.sampled_from(_HEX), min_size=64, max_size=64)))
    payload = draw(
        st.dictionaries(
            keys=st.text(alphabet=string.ascii_lowercase, min_size=1, max_size=8),
            values=st.text(alphabet=string.ascii_lowercase, max_size=16),
            max_size=4,
        )
    )
    return TransitionEvent(
        transition_id=transition_id,  # type: ignore[arg-type]
        prior_state_id=prior,  # type: ignore[arg-type]
        next_state_id=nxt,  # type: ignore[arg-type]
        triggering_outcome=payload,
        evidence_digest="blake3:" + evidence,  # type: ignore[arg-type]
        chain_head=head,  # type: ignore[arg-type]
        workflow_id=workflow_id,  # type: ignore[arg-type]
    )


def make_in_memory_store(root: Path) -> InMemoryCheckpointStore:
    return InMemoryCheckpointStore(root)


def make_sqlite_store(root: Path) -> SqliteCheckpointStore:
    return SqliteCheckpointStore(root)


# Parametrize factories for adapter parity. New adapters (Phase-9
# Postgres) land additively here.
ADAPTER_FACTORIES: Final[list] = [make_in_memory_store, make_sqlite_store]
ADAPTER_FACTORY_IDS: Final[list[str]] = ["in_memory", "sqlite"]
