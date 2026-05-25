"""Phase 6 — harness-facing contract surface (ADR-0001).

Public ``__all__`` is exactly the four names ADR-0001 commits the harness
across Phases 6 + 6.5 + 9 + 10 to: :class:`VulnRemediationCase`,
:class:`VulnRemediationResult`, :data:`SutDigest`,
:class:`VulnRemediationSut`. Adding a fifth public name requires:

1. An ADR-0001 amendment (or a successor ADR).
2. An explicit edit to this ``__all__`` list.
3. An explicit edit to the AC-12 allowlist sentinel in
   ``tests/fence/test_workflows_public_surface.py``.

No silent extension — the fence test fails loud otherwise.
"""

from __future__ import annotations

from codegenie.workflows.vuln_sut import (
    SutDigest,
    VulnRemediationCase,
    VulnRemediationResult,
    VulnRemediationSut,
)

__all__ = [
    "SutDigest",
    "VulnRemediationCase",
    "VulnRemediationResult",
    "VulnRemediationSut",
]
