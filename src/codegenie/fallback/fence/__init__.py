"""Phase-4 S2-02 — ``FenceWrapper`` + ``fence_pure`` trust-boundary primitive.

ADR-0013 ships the scan-untruncated-first ordering: every untrusted byte is
wrapped in a per-invocation nonce'd delimiter
(``<UNTRUSTED_INPUT id=NONCE>…</UNTRUSTED_INPUT id=NONCE>``) so the LLM
cannot mistake injected text for instructions.

The module pairs a stdlib-only pure core (:func:`fence_pure`) with an
imperative shell (:class:`FenceWrapper`) that mints the nonce and emits
audit events. The :class:`Scanner` Protocol is the dependency-inverted
port — S2-03 ships the production ``CanaryGuard`` implementation; this
module ships only the port + a test-only ``_AlwaysCleanScanner`` double.

ADRs honored:

- Phase-4 ADR-0013 — scan-before-truncate ordering; per-source truncation
  caps; functional-core / imperative-shell separation.
- Phase-4 ADR-0003 — path-scoped fence admits ``src/codegenie/fallback/``.
- Production ADR-0033 — newtype + smart-constructor + functional-core
  discipline.
"""

from __future__ import annotations

from codegenie.fallback.fence.wrapper import (
    CanaryClean,
    CanaryCollision,
    CanaryResult,
    FencedSegment,
    FenceWrapper,
    Scanner,
    SourceKind,
    fence_pure,
)

__all__ = [
    "CanaryClean",
    "CanaryCollision",
    "CanaryResult",
    "FenceWrapper",
    "FencedSegment",
    "Scanner",
    "SourceKind",
    "fence_pure",
]
