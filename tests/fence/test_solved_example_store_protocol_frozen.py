"""Phase-4 S4-03 AC-9 — :class:`SolvedExampleStore` Protocol fence.

Pins the public-method surface, the async/sync split, the
``capability`` parameter on ``add`` (the load-bearing gate), and the
literal ``"single-writer constraint"`` substring in the module docstring.
Any of these moving is the Phase-11 conformance bar drifting; the fence
makes the drift loud.

Phase-4 S5-01 candidate-read amendment (2026-05-25)
---------------------------------------------------
``query_candidates`` admitted as the fifth public method — the raw
candidate read seam the S5-01 retriever uses to chain-verify, filter,
and band-classify *before* the BandClassifier sees results. Documented
in :mod:`codegenie.rag.store`'s module docstring §"Phase-4 S5-01
candidate-read amendment".
"""

from __future__ import annotations

import inspect

from codegenie.rag import store as store_module
from codegenie.rag.store import SolvedExampleStore


def test_protocol_has_exactly_five_public_members() -> None:
    public_members = {n for n in dir(SolvedExampleStore) if not n.startswith("_")}
    assert public_members == {"query", "query_candidates", "add", "digest", "close"}, (
        "SolvedExampleStore Protocol surface drifted from the five-method "
        "contract (ADR-0016 + S5-01 candidate-read amendment). A speculative "
        "`update` / `delete` belongs in a Phase-11 ADR amendment, not Phase-4."
    )


def test_query_and_add_are_coroutines() -> None:
    assert inspect.iscoroutinefunction(SolvedExampleStore.query)
    assert inspect.iscoroutinefunction(SolvedExampleStore.add)


def test_digest_and_close_are_synchronous() -> None:
    assert inspect.isfunction(SolvedExampleStore.digest)
    assert inspect.isfunction(SolvedExampleStore.close)
    assert not inspect.iscoroutinefunction(SolvedExampleStore.digest)
    assert not inspect.iscoroutinefunction(SolvedExampleStore.close)


def test_add_signature_is_pinned() -> None:
    sig = inspect.signature(SolvedExampleStore.add)
    assert list(sig.parameters) == ["self", "example", "capability"], (
        "SolvedExampleStore.add lost the capability gate — without it the "
        "type-level write capability is unenforceable (ADR-0016 §Capability)."
    )


def test_query_signature_is_pinned() -> None:
    sig = inspect.signature(SolvedExampleStore.query)
    params = list(sig.parameters.values())
    names = [p.name for p in params]
    assert names == ["self", "q", "top_k", "similarity_floor"]
    top_k = sig.parameters["top_k"]
    floor = sig.parameters["similarity_floor"]
    assert top_k.kind == inspect.Parameter.KEYWORD_ONLY
    assert floor.kind == inspect.Parameter.KEYWORD_ONLY


def test_digest_and_close_take_only_self() -> None:
    assert list(inspect.signature(SolvedExampleStore.digest).parameters) == ["self"]
    assert list(inspect.signature(SolvedExampleStore.close).parameters) == ["self"]


def test_module_docstring_carries_single_writer_constraint_phrase() -> None:
    doc = store_module.__doc__ or ""
    assert "single-writer constraint" in doc, (
        "ADR-0016's load-bearing framing must appear verbatim in the "
        "store module docstring so a Phase-11 pgvector adapter author "
        "reads the conformance bar."
    )
