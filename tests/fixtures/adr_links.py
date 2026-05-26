"""Cross-link constants for Phase-4 ADRs referenced from test docstrings.

Single source of truth: tests that need to cite an ADR import the
relevant constant from this module rather than embed a stale literal.
:mod:`tests.fence.test_adr_links_resolve` walks every ``ADR-04-NNNN``
literal in this file and asserts the referenced ADR file exists.

Naming convention: ``ADR_04_NNNN`` (Phase-4 phase prefix, four-digit
ADR number). The constant value is a human-readable sentence + the
filesystem path the resolve-fence verifies.
"""

from __future__ import annotations

from typing import Final

ADR_04_0011: Final[str] = (
    "ADR-04-0011: RAG bypass on retry — deliberate departure from "
    "production ADR-0011's chain order. Initial-plan order is "
    "recipe → RAG → LLM; retry order is recipe → (RAG bypassed) → "
    "LLM with prior_failure_summary as the substitute for what RAG "
    "would have contributed. See "
    "docs/phases/04-vuln-llm-fallback-rag/ADRs/0011-rag-bypass-on-retry.md."
)
