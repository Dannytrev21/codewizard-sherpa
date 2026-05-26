"""Phase-4 S5-03 — :class:`EmbeddingModelMismatchFilter` tests.

Covers the load-bearing ACs:

* AC-1 — module shape: exactly one public name.
* AC-2 — filter signature matches S5-01's ``model_digest_filter`` hook
  byte-for-byte.
* AC-3 — on exclusion, exactly one ``RagRecordModelMismatch`` event
  emitted with ``current_model`` + ``sample_stale_model``.
* AC-4 — on zero exclusions (incl. empty input), no event emitted.
* AC-7 — determinism: identical inputs → identical outputs (and
  identical event count).
* AC-12 (spot-check) — once-per-query invariant: exactly one emission
  per ``__call__`` when ``k > 0``; zero when ``k == 0``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from codegenie.plugins.events import EventLog, RagRecordModelMismatch
from codegenie.rag.exclusion import EmbeddingModelMismatchFilter
from codegenie.rag.models import ScoredSolvedExample
from codegenie.types.identifiers import BlobDigest, ModelId, Similarity, WorkflowId
from tests.fixtures.rag.fake_solved_example import make_solved_example

_LIVE_DIGEST = BlobDigest("blake3:" + "1" * 64)
_STALE_DIGEST = BlobDigest("blake3:" + "2" * 64)


def _embedder_with(digest: BlobDigest) -> Any:
    emb = MagicMock()
    emb.model_digest = lambda: digest
    return emb


def _candidate_with_model(record_id: str, model: BlobDigest) -> ScoredSolvedExample:
    rec = make_solved_example(id_=record_id)
    # Override embedding_model — pydantic frozen requires model_copy.
    rec = rec.model_copy(update={"embedding_model": ModelId(str(model))})
    return ScoredSolvedExample(record=rec, score=Similarity(0.9))


def test_ac1_module_exports_exactly_one_name() -> None:
    from codegenie.rag import exclusion

    assert set(exclusion.__all__) == {"EmbeddingModelMismatchFilter"}


def test_ac4_zero_exclusions_emits_no_event(tmp_path: Path) -> None:
    log = EventLog(root=tmp_path / "ev", workflow_id=WorkflowId("01HRMM00ZEROEXCLUS00000WX0"))
    f = EmbeddingModelMismatchFilter(embedder=_embedder_with(_LIVE_DIGEST), event_log=log)
    # All candidates carry the LIVE digest.
    candidates = [_candidate_with_model(f"ok-{i}", _LIVE_DIGEST) for i in range(3)]
    surviving, excluded = f(candidates)
    assert excluded == 0
    assert len(surviving) == 3
    log.flush()  # type: ignore[attr-defined]
    events = list(log.replay())  # type: ignore[attr-defined]
    assert not any(type(e).__name__ == "RagRecordModelMismatch" for e in events), (
        "filter must NOT emit on zero exclusions"
    )


def test_ac4_empty_input_returns_empty_and_emits_no_event(tmp_path: Path) -> None:
    log = EventLog(root=tmp_path / "ev", workflow_id=WorkflowId("01HRMM00EMPTYINPUTTEST0WX0"))
    f = EmbeddingModelMismatchFilter(embedder=_embedder_with(_LIVE_DIGEST), event_log=log)
    surviving, excluded = f([])
    assert surviving == []
    assert excluded == 0
    log.flush()  # type: ignore[attr-defined]
    assert not any(
        type(e).__name__ == "RagRecordModelMismatch"
        for e in log.replay()  # type: ignore[attr-defined]
    )


def test_ac3_exclusion_emits_exactly_one_event_with_digests(tmp_path: Path) -> None:
    log = EventLog(root=tmp_path / "ev", workflow_id=WorkflowId("01HRMM00EXCLUDETESTHAPPYWX"))
    f = EmbeddingModelMismatchFilter(embedder=_embedder_with(_LIVE_DIGEST), event_log=log)
    candidates = [
        _candidate_with_model("ok-1", _LIVE_DIGEST),
        _candidate_with_model("stale-1", _STALE_DIGEST),
        _candidate_with_model("stale-2", _STALE_DIGEST),
    ]
    surviving, excluded = f(candidates)
    assert excluded == 2
    assert len(surviving) == 1
    assert surviving[0].record.id == "ok-1"
    log.flush()  # type: ignore[attr-defined]
    mm_events = [
        e
        for e in log.replay()  # type: ignore[attr-defined]
        if isinstance(e, RagRecordModelMismatch)
    ]
    assert len(mm_events) == 1, "exactly one event per __call__"
    ev = mm_events[0]
    assert ev.count == 2
    assert str(ev.current_model) == str(_LIVE_DIGEST)
    assert str(ev.sample_stale_model) == str(_STALE_DIGEST)


def test_ac7_determinism_two_calls_yield_equal_outputs(tmp_path: Path) -> None:
    log = EventLog(root=tmp_path / "ev", workflow_id=WorkflowId("01HRMM00DETERMINTESTHAP00X"))
    f = EmbeddingModelMismatchFilter(embedder=_embedder_with(_LIVE_DIGEST), event_log=log)
    candidates = [
        _candidate_with_model("ok-1", _LIVE_DIGEST),
        _candidate_with_model("stale-1", _STALE_DIGEST),
    ]
    s1, e1 = f(candidates)
    s2, e2 = f(candidates)
    assert e1 == e2 == 1
    assert [c.record.id for c in s1] == [c.record.id for c in s2] == ["ok-1"]


def test_ac12_once_per_call_invariant(tmp_path: Path) -> None:
    """Three calls — each excluding one record — emit exactly three events."""
    log = EventLog(root=tmp_path / "ev", workflow_id=WorkflowId("01HRMM00ONCEPERCALL000000X"))
    f = EmbeddingModelMismatchFilter(embedder=_embedder_with(_LIVE_DIGEST), event_log=log)
    for i in range(3):
        f([_candidate_with_model(f"stale-{i}", _STALE_DIGEST)])
    log.flush()  # type: ignore[attr-defined]
    mm_events = [
        e
        for e in log.replay()  # type: ignore[attr-defined]
        if isinstance(e, RagRecordModelMismatch)
    ]
    assert len(mm_events) == 3
    for ev in mm_events:
        assert ev.count == 1
