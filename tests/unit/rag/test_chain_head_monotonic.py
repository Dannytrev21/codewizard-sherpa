"""Phase-4 S4-04 — chain_head monotonicity + prefix-stability (AC-8).

AC-8 splits into TWO contracts:

1. **Monotonic + unique** — 10 sequential adds yield 10 distinct chain
   heads (no collision; insertion-order sensitive).
2. **Prefix-stable** — ``chain_head_after_N`` depends ONLY on records
   0..N-1, not on later records. Pinned two ways:
     (a) against the *pure* ``_roll_chain_head`` core with synthetic
         bytes (no filesystem),
     (b) a two-store cross-check: store A with N records vs store B with
         N+5; A's ``digest()`` equals ``blake3`` of B's first-N record
         bytes.
"""

from __future__ import annotations

from pathlib import Path

import blake3

from codegenie.rag.store import (
    ChromaPersistentStore,
    SolvedExampleWriteCapability,
    _roll_chain_head,
)
from codegenie.types.identifiers import ChainHead, WorkflowId
from tests.fixtures.rag.fake_solved_example import make_solved_example

# ---------------------------------------------------------------------------
# AC-8 a — monotonic + unique
# ---------------------------------------------------------------------------


async def test_chain_head_monotonic_and_unique(tmp_path: Path) -> None:
    """Sequentially add 10 records; collect chain_head at each step;
    every head must be distinct (no collision, insertion-order
    sensitive)."""
    store = ChromaPersistentStore(root_dir=tmp_path)
    cap = SolvedExampleWriteCapability(workflow_id=WorkflowId("wf-mono"))
    heads: list[str] = []
    for i in range(10):
        await store.add(make_solved_example(id_=f"ex-{i:02d}"), cap)
        heads.append(store.digest())
    assert len(set(heads)) == 10, f"expected 10 distinct heads; got {len(set(heads))}"
    store.close()


# ---------------------------------------------------------------------------
# AC-8 b — prefix-stable via the pure _roll_chain_head core
# ---------------------------------------------------------------------------


def test_roll_chain_head_is_prefix_stable_on_synthetic_bytes() -> None:
    """Pure table test on ``_roll_chain_head``. The reduction of
    ``[b0, b1, b2]`` must equal the 3-prefix of ``[b0, b1, b2, b3, b4]``.

    A mutant that re-hashes everything on each step (rolls the whole
    list every time) would still pass distinctness — this test catches
    it."""
    blobs = [f"blob-{i}\n".encode() for i in range(5)]
    head_3_isolated = _roll_chain_head(blobs[:3])

    # Streaming reduction of the full 5-list, asserting the 3-prefix
    h = blake3.blake3()
    head_at_step: list[str] = []
    for blob in blobs:
        h.update(blob)
        head_at_step.append(h.hexdigest())
    head_3_in_stream = ChainHead(head_at_step[2])
    assert head_3_isolated == head_3_in_stream


def test_roll_chain_head_empty_iter_is_blake3_of_empty() -> None:
    """Pure-core empty-iter contract — the empty roll equals
    ``blake3(b"").hexdigest()``."""
    assert _roll_chain_head([]) == ChainHead(blake3.blake3(b"").hexdigest())


# ---------------------------------------------------------------------------
# AC-8 c — prefix-stable across two stores
# ---------------------------------------------------------------------------


async def test_chain_head_prefix_stable_across_two_stores(tmp_path: Path) -> None:
    """Store A with N records; Store B with N+5. A's ``digest()`` must
    equal ``blake3`` of B's first-N canonical YAML bytes — proves the
    chain head at step N depends ONLY on records 0..N-1."""
    cap = SolvedExampleWriteCapability(workflow_id=WorkflowId("wf-prefix"))
    n = 3

    store_a = ChromaPersistentStore(root_dir=tmp_path / "store-a")
    for i in range(n):
        await store_a.add(make_solved_example(id_=f"ex-{i:02d}"), cap)
    digest_a = store_a.digest()
    store_a.close()

    store_b = ChromaPersistentStore(root_dir=tmp_path / "store-b")
    for i in range(n + 5):
        await store_b.add(make_solved_example(id_=f"ex-{i:02d}"), cap)

    first_n_bytes = b"".join(
        (tmp_path / "store-b" / "records" / f"ex-{i:02d}.yaml").read_bytes() for i in range(n)
    )
    expected = blake3.blake3(first_n_bytes).hexdigest()
    assert digest_a == expected
    store_b.close()
