"""Phase-4 RAG package — solved-example retrieval models + (later) store.

S1-04 lands the Pydantic v2 contract surface every Phase-4 consumer types
against; later stories add the ChromaDB-embedded persistent store
(S4-03), the YAML canonical record (S4-04), the chain-verify provenance
(S4-05), and the retriever / two-threshold classifier (S5-01..S5-04).

Imports from ``chromadb`` / ``fastembed`` / ``onnxruntime`` are
path-scoped-fenced into the modules that need them (S1-05); ``models.py``
is pure Pydantic and is admitted by every fence.
"""

from __future__ import annotations

from codegenie.rag.models import (
    FailureModeTag,
    Query,
    RagDegraded,
    RagHit,
    RagMiss,
    RecordProvenance,
    RetrievalOutcome,
    SolvedExample,
    TypecheckNodeSignal,
)

__all__ = (
    "FailureModeTag",
    "Query",
    "RagDegraded",
    "RagHit",
    "RagMiss",
    "RecordProvenance",
    "RetrievalOutcome",
    "SolvedExample",
    "TypecheckNodeSignal",
)
