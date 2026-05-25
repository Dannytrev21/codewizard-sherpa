"""Fence — :class:`codegenie.rag.embedder.Embedder` Protocol surface freeze.

Phase-4 S4-01 AC-9. The cache-key contract S4-02 reads depends on this
Protocol's surface staying at exactly three members. Adding a fourth
(e.g., ``close``, ``warmup``) or removing one fails this assertion at
CI time.

Methodology mirrors ``tests/fence/test_plugin_protocol_frozen.py``: a
:class:`typing.Protocol` does not surface attribute-only members via
:func:`dir` alone (`@runtime_checkable` quirks differ across Python
versions), so the public surface is the union of ``dir`` (sans dunders)
and ``__annotations__`` (sans dunders).
"""

from __future__ import annotations

import inspect

from codegenie.rag.embedder import Embedder

_EXPECTED_MEMBERS = frozenset({"embed", "embed_batch", "model_digest"})


def test_embedder_protocol_has_exactly_three_members() -> None:
    """S4-01 AC-9 — the public surface is exactly three method names.

    Drift fails loudly so the S4-02 cache-key contract stays pinned.
    """
    public_dir = {name for name in dir(Embedder) if not name.startswith("_")}
    annotated = {name for name in Embedder.__annotations__ if not name.startswith("_")}
    members = frozenset(public_dir | annotated)
    assert members == _EXPECTED_MEMBERS, (
        f"Embedder Protocol surface drifted from S4-01 freeze: "
        f"got={sorted(members)} expected={sorted(_EXPECTED_MEMBERS)}"
    )


def test_embedder_protocol_three_methods_are_functions() -> None:
    """Each member is a function (method on the Protocol). An accidental
    demotion to an attribute or a property would slip past the count
    check above — this test catches the type drift."""
    assert inspect.isfunction(Embedder.embed)
    assert inspect.isfunction(Embedder.embed_batch)
    assert inspect.isfunction(Embedder.model_digest)


def test_embedder_protocol_is_runtime_checkable() -> None:
    """``@runtime_checkable`` is load-bearing — it lets the retriever
    (S5-01) ``isinstance``-check incoming adapters without importing
    fastembed. Without the decorator that check raises
    :class:`TypeError`."""
    # ``Protocol`` subclasses created with ``@runtime_checkable`` carry
    # a class-level ``_is_runtime_protocol`` attribute set to True by
    # the typing machinery. Reading it (rather than catching the
    # TypeError) makes the intent of this test self-documenting.
    assert getattr(Embedder, "_is_runtime_protocol", False) is True
