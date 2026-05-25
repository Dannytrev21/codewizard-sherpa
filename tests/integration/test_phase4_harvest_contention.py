"""Phase-4 S4-08 — burst-harvest contention integration test.

Pins **Gap 3** (`phase-arch-design.md §1106`) — the load-bearing
conformance bar Phase-11 pgvector swap must meet. Two harvest coroutines
run under :func:`asyncio.gather` against a real
:class:`ChromaPersistentStore`; both must succeed with a monotonically-
advancing :attr:`_Manifest.chain_head`, byte-identity between
:meth:`ChromaPersistentStore.digest` and the on-disk manifest, and a
deliberate-timeout variant must raise the typed
:class:`StoreWriteContention` *without* leaving any orphan write
(`records/*.yaml`, ``manifest.yaml``, ``_record_ids``).

ADR honours
-----------
- ADR-0016 — single-writer ``asyncio.Lock`` around
  ``ChromaPersistentStore.add``.
- Gap 3 — ``test_phase4_harvest_contention`` is the **pinned conformance
  bar** Phase-11 pgvector swap inherits.

Distinct mutation targets per AC
--------------------------------
- AC-2 / AC-3 — chain-head correctness (would catch a digest computed
  over ID strings or rolled over zero/one record).
- AC-4 — lock granularity (would catch a lock that wraps only the
  chromadb call, leaving ``_record_ids`` and ``manifest.records`` out of
  sync).
- AC-5 / AC-6 — typed-timeout shape + no-orphan posture (would catch
  partial writes under timeout).
- AC-9 — ``asyncio.to_thread`` boundary (would catch a refactor that
  drops the thread wrap and silently makes the chromadb call blocking).
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import Mock

import pytest
import yaml

from codegenie.rag.errors import StoreWriteContention
from codegenie.rag.store import (
    ChromaPersistentStore,
    SolvedExampleWriteCapability,
    _compute_chain_head,
)
from codegenie.types.identifiers import SolvedExampleId, WorkflowId
from tests.fixtures.rag.fake_solved_example import make_solved_example

# Same-collection worst case (AC-1): every ``make_solved_example`` call in
# this module uses the fixture's default ``(task_class, language,
# build_system)`` triple — ``("vuln_remediation", "typescript", "npm")``
# — so both ``add()`` coroutines collide on the same chromadb collection,
# realistically exercising the single-writer ``asyncio.Lock``. The
# fixture-default-by-relying-on-default approach keeps mypy --strict
# happy where unpacking a ``dict[str, str]`` into the typed kwargs would
# not.


@pytest.fixture
def tmp_root(tmp_path: Path) -> Path:
    return tmp_path / "rag"


@pytest.fixture
def store(tmp_root: Path) -> Iterator[ChromaPersistentStore]:
    s = ChromaPersistentStore(root_dir=tmp_root)
    yield s
    s.close()


def _expected_head(records_dir: Path, order: list[str]) -> str:
    """Independent oracle (mirrors S4-04 AC-5): re-roll BLAKE3 over the
    canonical YAML bytes in the given order.

    Uses :func:`_compute_chain_head` so the chromadb collection identity
    is the only variable across orderings — every other step is shared
    with the production write path.
    """
    return str(
        _compute_chain_head(
            [SolvedExampleId(rid) for rid in order],
            records_dir,
        )
    )


async def test_two_harvests_under_gather_both_succeed_sequenced(
    store: ChromaPersistentStore,
    tmp_root: Path,
) -> None:
    """AC-1..AC-4 — happy path.

    Two coroutines, same-collection writes, both succeed; the resulting
    manifest's ``chain_head`` is one of the two BLAKE3-rolled orderings;
    ``store.digest() == manifest.chain_head``; and
    ``_record_ids == manifest.records`` exactly.
    """
    # AC-2-test-only-direct-construction (S4-03 AC-2 boundary lift) —
    # S4-06's ``_phase4_local_capability_mint`` is fenced to
    # ``src/codegenie/gates/`` + ``src/codegenie/rag/ingest.py`` (S4-06
    # AC-6 path-scoped fence), and a test module is outside that
    # allowlist.
    cap_a = SolvedExampleWriteCapability(workflow_id=WorkflowId("wf-A"))
    cap_b = SolvedExampleWriteCapability(workflow_id=WorkflowId("wf-B"))
    ex_a = make_solved_example(id_="ex-A", cve_id="CVE-2026-AAAA")
    ex_b = make_solved_example(id_="ex-B", cve_id="CVE-2026-BBBB")

    results = await asyncio.gather(store.add(ex_a, cap_a), store.add(ex_b, cap_b))

    # AC-1: both succeeded — order is lock-acquisition dependent, so set-equal.
    assert set(results) == {SolvedExampleId("ex-A"), SolvedExampleId("ex-B")}
    assert len(store._record_ids) == 2

    manifest = yaml.safe_load((tmp_root / "manifest.yaml").read_text("utf-8"))
    assert set(manifest["records"]) == {"ex-A", "ex-B"}

    # AC-3: digest() byte-identical to manifest chain head under contention.
    assert manifest["chain_head"] == str(store.digest())

    # AC-4: _record_ids order == manifest.records order (lock granularity catch).
    assert store._record_ids == [SolvedExampleId(rid) for rid in manifest["records"]]

    # AC-2: chain_head is one of the two valid orderings (content deterministic,
    # ordering is not). The empty-roll and single-record-only mutants are also
    # excluded by exclusion below.
    records_dir = tmp_root / "records"
    head_ab = _expected_head(records_dir, ["ex-A", "ex-B"])
    head_ba = _expected_head(records_dir, ["ex-B", "ex-A"])
    assert manifest["chain_head"] in {head_ab, head_ba}
    # AC-2 single-record-only mutant guard: confirm chain head is NOT
    # the one-record roll of either record alone, NOR the empty roll.
    head_a_only = _expected_head(records_dir, ["ex-A"])
    head_b_only = _expected_head(records_dir, ["ex-B"])
    assert manifest["chain_head"] not in {head_a_only, head_b_only}


async def test_harvest_contention_timeout_raises_typed_exception(
    store: ChromaPersistentStore,
    tmp_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-5..AC-7 — deliberate-timeout fixture.

    Expected emission (S6-03 responsibility — NOT wired here):
      event = SolvedExampleIngestFailed(
          reason="write_contention",
          workflow_id=cap_b.workflow_id,
      )
    """
    monkeypatch.setattr("codegenie.rag.store._ADD_LOCK_TIMEOUT_SECONDS", 0.1)

    # AC-2-test-only-direct-construction (S4-03 AC-2 boundary lift)
    cap_b = SolvedExampleWriteCapability(workflow_id=WorkflowId("wf-B"))
    ex_b = make_solved_example(id_="ex-B")
    # Notes §5: slow_add_a() hijacks the lock only — no SolvedExample,
    # no capability needed.

    async def slow_add_a() -> SolvedExampleId:
        # Notes §5: raw .acquire() — the free lock returns without
        # suspending so slow_add_a holds it before yielding, guaranteeing
        # the second coroutine finds it held. Do NOT "tidy" into a
        # wait_for or store.add(...) call.
        await store._add_lock.acquire()
        try:
            await asyncio.sleep(0.5)  # well past the 0.1s timeout
            return SolvedExampleId("ex-A-skipped")
        finally:
            store._add_lock.release()

    results = await asyncio.gather(
        slow_add_a(),
        store.add(ex_b, cap_b),
        return_exceptions=True,
    )

    # AC-5: typed exception with the right workflow_id.
    assert results[0] == SolvedExampleId("ex-A-skipped")
    assert isinstance(results[1], StoreWriteContention)
    assert results[1].workflow_id == WorkflowId("wf-B")

    # AC-6: a timed-out harvest leaves NO trace anywhere. The lock is
    # acquired BEFORE the first write, so none of YAML/chromadb/manifest
    # ran for ex-B.
    assert not (tmp_root / "records" / "ex-B.yaml").exists()
    assert SolvedExampleId("ex-B") not in store._record_ids
    assert not (tmp_root / "manifest.yaml").exists()

    # AC-5: lock not leaked — a subsequent add succeeds.
    assert store._add_lock.locked() is False

    # AC-2-test-only-direct-construction (S4-03 AC-2 boundary lift)
    cap_c = SolvedExampleWriteCapability(workflow_id=WorkflowId("wf-C"))
    sid_c = await store.add(make_solved_example(id_="ex-C"), cap_c)
    assert sid_c == SolvedExampleId("ex-C")

    # AC-6 closing assertion: ex-B left no trace — the manifest lists
    # exactly ["ex-C"]. Transitively proves ex-B never reached
    # _record_ids, the manifest, the chain head, or the chromadb write
    # (last in the lock-held sequence).
    manifest = yaml.safe_load((tmp_root / "manifest.yaml").read_text("utf-8"))
    assert manifest["records"] == ["ex-C"]


async def test_to_thread_invoked_per_add(
    store: ChromaPersistentStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-9 — every chromadb ``add`` is dispatched through
    ``asyncio.to_thread`` and wraps the ``collection.add`` bound method.

    Catches both an *unwrap* (count drops to 0) and a *wrong-target*
    mutant (count stays but the wrapped callable is something else).
    Production-posture guard (arch §Concurrency) — NOT a contention-
    correctness assertion (see story TDD §Red).
    """
    real_to_thread = asyncio.to_thread
    mock = Mock(wraps=real_to_thread)
    # Patch the module attribute so ``store.py``'s call-time
    # ``asyncio.to_thread`` resolution picks up the wrapped callable.
    monkeypatch.setattr(asyncio, "to_thread", mock)

    cap_a = SolvedExampleWriteCapability(workflow_id=WorkflowId("wf-A"))
    cap_b = SolvedExampleWriteCapability(workflow_id=WorkflowId("wf-B"))
    ex_a = make_solved_example(id_="ex-A")
    ex_b = make_solved_example(id_="ex-B")

    await store.add(ex_a, cap_a)
    await store.add(ex_b, cap_b)

    # AC-9(a): exactly one to_thread call per add().
    assert mock.call_count == 2
    # AC-9(b): every call wraps the chromadb ``collection.add`` bound method.
    for call in mock.call_args_list:
        first_arg = call.args[0]
        assert callable(first_arg)
        assert getattr(first_arg, "__name__", None) == "add"
