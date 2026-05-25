"""Phase-4 S4-03 — :class:`ChromaPersistentStore` unit tests.

Each test below pins one acceptance criterion (or rejects a specific
mutant) for the in-tree :class:`SolvedExampleStore` adapter described in
``docs/phases/04-vuln-llm-fallback-rag/stories/S4-03-chroma-persistent-store.md``.

The fixtures live in :mod:`tests.fixtures.rag.fake_solved_example`; the
boundary lift of raw ``str`` → :class:`SolvedExampleId` etc. happens
there so individual tests stay free of identifier-construction noise.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from codegenie.rag.errors import StoreClosed, StoreWriteContention
from codegenie.rag.models import RagHit, RagMiss
from codegenie.rag.store import (
    ChromaPersistentStore,
    SolvedExampleWriteCapability,
)
from codegenie.types.identifiers import (
    EmbeddingVector,
    SolvedExampleId,
    StoreDigest,
    WorkflowId,
)
from tests.fixtures.rag.fake_solved_example import (
    make_query_matching,
    make_solved_example,
)

_EMPTY_BLAKE3 = "af1349b9f5f9a1a6a0404dea36dcc9499bcb25c9adc112b7cc9a93cae41f3262"
# BLAKE3 hexdigest of empty input — AC-6 positive-direction pin.


# ---------------------------------------------------------------------------
# AC-3 / AC-4 / AC-6 — add appends a record and digest moves
# ---------------------------------------------------------------------------


async def test_add_appends_record_and_changes_digest(tmp_path: Path) -> None:
    """ADR-0016 §Decision: chromadb is the queryable derived index.
    Catches the "add never writes" mutant: a no-op add leaves digest at
    the empty-BLAKE3 constant."""
    store = ChromaPersistentStore(root_dir=tmp_path)
    # AC-2-test-only-direct-construction — S4-06 ships the mint.
    cap = SolvedExampleWriteCapability(workflow_id=WorkflowId("wf-001"))
    example = make_solved_example(id_="ex-001")
    assert store.digest() == StoreDigest(_EMPTY_BLAKE3)

    sid = await store.add(example, cap)
    assert sid == SolvedExampleId("ex-001")
    assert store.digest() != StoreDigest(_EMPTY_BLAKE3)
    store.close()


# ---------------------------------------------------------------------------
# AC-4 / AC-5 — round-trip through _query_with_embedding
# ---------------------------------------------------------------------------


async def test_add_then_query_with_embedding_returns_rag_hit(tmp_path: Path) -> None:
    """Load-bearing round-trip: a record added to the store is
    retrievable. Catches the "query always returns RagMiss" mutant and
    the "store.add silently drops the vector" mutant. Uses the *private*
    ``_query_with_embedding`` (AC-5) — the public ``query`` has no vector
    by contract."""
    store = ChromaPersistentStore(root_dir=tmp_path)
    cap = SolvedExampleWriteCapability(workflow_id=WorkflowId("wf-001"))
    example = make_solved_example(id_="ex-001")
    await store.add(example, cap)

    q = make_query_matching(example)
    outcome = await store._query_with_embedding(q, example.embedding_vector, top_k=5)
    assert isinstance(outcome, RagHit)
    assert outcome.few_shot.id == SolvedExampleId("ex-001")
    assert outcome.score >= 0.99
    store.close()


# ---------------------------------------------------------------------------
# AC-8 — single-writer contention surfaces as StoreWriteContention
# ---------------------------------------------------------------------------


async def test_add_under_contention_raises_store_write_contention(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Gap 3 + edge case #5: declared 30 s timeout becomes
    :class:`StoreWriteContention`, not a silent hang. If this fails,
    the Phase-11 pgvector conformance bar is unverified — surface per
    Rule 12."""
    monkeypatch.setattr("codegenie.rag.store._ADD_LOCK_TIMEOUT_SECONDS", 0.05)
    store = ChromaPersistentStore(root_dir=tmp_path)
    cap = SolvedExampleWriteCapability(workflow_id=WorkflowId("wf-block"))
    example = make_solved_example(id_="ex-002")

    await store._add_lock.acquire()
    try:
        with pytest.raises(StoreWriteContention) as exc_info:
            await store.add(example, cap)
        assert exc_info.value.workflow_id == WorkflowId("wf-block")
    finally:
        store._add_lock.release()
    # Caller's manual hold must release cleanly — if add() called
    # ``release()`` unguarded the test's own release would have flipped
    # the lock state and this assertion would fail.
    assert store._add_lock.locked() is False
    store.close()


# ---------------------------------------------------------------------------
# AC-6 — empty store digest equals BLAKE3 of empty bytes
# ---------------------------------------------------------------------------


def test_empty_store_digest_is_blake3_of_empty(tmp_path: Path) -> None:
    store = ChromaPersistentStore(root_dir=tmp_path)
    assert store.digest() == StoreDigest(_EMPTY_BLAKE3)
    store.close()


# ---------------------------------------------------------------------------
# AC-6 — order-sensitive; sort-then-roll mutant must fail
# ---------------------------------------------------------------------------


async def test_digest_is_insertion_order_sensitive(tmp_path: Path) -> None:
    cap = SolvedExampleWriteCapability(workflow_id=WorkflowId("wf-001"))
    a = make_solved_example(id_="ex-A")
    b = make_solved_example(id_="ex-B")

    store_ab = ChromaPersistentStore(root_dir=tmp_path / "ab")
    await store_ab.add(a, cap)
    await store_ab.add(b, cap)

    store_ba = ChromaPersistentStore(root_dir=tmp_path / "ba")
    await store_ba.add(b, cap)
    await store_ba.add(a, cap)

    store_ab_2 = ChromaPersistentStore(root_dir=tmp_path / "ab2")
    await store_ab_2.add(a, cap)
    await store_ab_2.add(b, cap)

    assert store_ab.digest() != store_ba.digest()
    assert store_ab.digest() == store_ab_2.digest()
    store_ab.close()
    store_ba.close()
    store_ab_2.close()


# ---------------------------------------------------------------------------
# AC-5 — empty-partition private read returns RagMiss (no raise)
# ---------------------------------------------------------------------------


async def test_query_empty_partition_returns_rag_miss(tmp_path: Path) -> None:
    store = ChromaPersistentStore(root_dir=tmp_path)
    example = make_solved_example()
    q = make_query_matching(example)
    outcome = await store._query_with_embedding(q, example.embedding_vector, top_k=5)
    assert isinstance(outcome, RagMiss)
    store.close()


# ---------------------------------------------------------------------------
# AC-5 — public query() returns RagMiss even after matching add
# ---------------------------------------------------------------------------


async def test_public_query_returns_rag_miss_without_vector(tmp_path: Path) -> None:
    store = ChromaPersistentStore(root_dir=tmp_path)
    cap = SolvedExampleWriteCapability(workflow_id=WorkflowId("wf-001"))
    example = make_solved_example()
    await store.add(example, cap)

    q = make_query_matching(example)
    outcome = await store.query(q, top_k=5)
    assert isinstance(outcome, RagMiss)
    store.close()


# ---------------------------------------------------------------------------
# AC-5b — partition collections are independent
# ---------------------------------------------------------------------------


async def test_partition_collections_are_independent(tmp_path: Path) -> None:
    store = ChromaPersistentStore(root_dir=tmp_path)
    cap = SolvedExampleWriteCapability(workflow_id=WorkflowId("wf-001"))
    npm_example = make_solved_example(
        id_="ex-npm",
        task_class="vuln_remediation",
        language="typescript",
        build_system="npm",
    )
    await store.add(npm_example, cap)

    other_example = make_solved_example(
        id_="ex-yarn",
        task_class="distroless_migration",
        language="typescript",
        build_system="npm",
    )
    q = make_query_matching(other_example)
    outcome = await store._query_with_embedding(q, npm_example.embedding_vector, top_k=5)
    assert isinstance(outcome, RagMiss)
    store.close()


# ---------------------------------------------------------------------------
# AC-7 — close disables subsequent operations
# ---------------------------------------------------------------------------


async def test_close_disables_subsequent_operations(tmp_path: Path) -> None:
    store = ChromaPersistentStore(root_dir=tmp_path)
    cap = SolvedExampleWriteCapability(workflow_id=WorkflowId("wf-001"))
    example = make_solved_example()
    q = make_query_matching(example)

    store.close()

    with pytest.raises(StoreClosed):
        await store.add(example, cap)
    with pytest.raises(StoreClosed):
        await store.query(q)
    with pytest.raises(StoreClosed):
        await store._query_with_embedding(q, example.embedding_vector)


def test_close_is_idempotent(tmp_path: Path) -> None:
    store = ChromaPersistentStore(root_dir=tmp_path)
    store.close()
    # A second close() must raise nothing.
    store.close()


async def test_digest_survives_close(tmp_path: Path) -> None:
    store = ChromaPersistentStore(root_dir=tmp_path)
    cap = SolvedExampleWriteCapability(workflow_id=WorkflowId("wf-001"))
    await store.add(make_solved_example(), cap)
    pre_close = store.digest()
    store.close()
    post_close = store.digest()
    assert pre_close == post_close


# ---------------------------------------------------------------------------
# AC-5 — similarity_floor filters borderline matches
# ---------------------------------------------------------------------------


async def test_similarity_floor_below_top_score_yields_rag_miss(
    tmp_path: Path,
) -> None:
    store = ChromaPersistentStore(root_dir=tmp_path)
    cap = SolvedExampleWriteCapability(workflow_id=WorkflowId("wf-001"))
    example = make_solved_example()
    await store.add(example, cap)

    # Use an orthogonal vector — same-shape but unrelated direction.
    orthogonal: EmbeddingVector = EmbeddingVector(
        tuple([1.0] + [0.0] * (len(example.embedding_vector) - 1))
    )
    q = make_query_matching(example)
    outcome = await store._query_with_embedding(q, orthogonal, top_k=5, similarity_floor=0.99)
    assert isinstance(outcome, RagMiss)
    store.close()
