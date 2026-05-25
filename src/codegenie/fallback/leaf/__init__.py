"""Phase-4 S3-01 — ``LeafLlm`` Protocol package (the single seam to any LLM vendor).

Re-exports :class:`LeafLlm` and :class:`LeafResponse` from :mod:`port` so
downstream consumers (``FallbackTier``, plugin adapters, retry logic) program
against the SDK-free Protocol rather than against ``anthropic.AsyncAnthropic``.

Concrete adapters live as siblings of :mod:`port` (``anthropic_adapter`` ships
in S3-02; production ADR-0020 reserves the seam for a second vendor). The
path-scoped fence (ADR-0003) admits ``anthropic`` only under
``src/codegenie/fallback/leaf/anthropic_adapter.py``; :mod:`port` is asserted
SDK-free by ``tests/unit/fallback/test_port_module_purity.py``.
"""

from __future__ import annotations

from codegenie.fallback.leaf.port import LeafLlm, LeafResponse

__all__ = ("LeafLlm", "LeafResponse")
