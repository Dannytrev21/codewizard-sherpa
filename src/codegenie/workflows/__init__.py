"""Phase 6 — harness-facing contract surface (ADR-0001) + ledger substrate (ADR-0003).

Public ``__all__`` is exactly the 14 names committed by Phase 6 ADR-0001
(S1-01: four names) + ADR-0003 (S1-02: ten names):

* **S1-01 / ADR-0001:** :class:`VulnRemediationCase`,
  :class:`VulnRemediationResult`, :data:`SutDigest`,
  :class:`VulnRemediationSut`.
* **S1-02 / ADR-0003:** :data:`VulnLedgerState`, :class:`NeedsPlan`,
  :class:`PlanReady`, :class:`PatchApplied`, :class:`GateFailedRetryable`,
  :class:`AwaitingHumanReview`, :class:`Completed`,
  :class:`FailedUnrecoverable`, :data:`LedgerStateKind`,
  :class:`TransitionEvent`, :data:`TransitionId`.

Adding a fifteenth public name requires:

1. An ADR-0001 / ADR-0003 amendment (or a successor ADR).
2. An explicit edit to this ``__all__`` list.
3. An explicit edit to the allowlist sentinel in
   ``tests/fence/test_workflows_public_surface.py``.

No silent extension — the fence test fails loud otherwise.

Re-exporting :data:`TransitionId` here (it physically lives in
:mod:`codegenie.types.identifiers`) is a harness-convenience: the bench
fixture builder pulls the four S1-01 names + the ten ledger names from a
single import path. The kernel-tier identifier is still the canonical
declaration site.
"""

from __future__ import annotations

from codegenie.types.identifiers import TransitionId
from codegenie.workflows.vuln_ledger import (
    AwaitingHumanReview,
    Completed,
    FailedUnrecoverable,
    GateFailedRetryable,
    LedgerStateKind,
    NeedsPlan,
    PatchApplied,
    PlanReady,
    TransitionEvent,
    VulnLedgerState,
)
from codegenie.workflows.vuln_sut import (
    SutDigest,
    VulnRemediationCase,
    VulnRemediationResult,
    VulnRemediationSut,
)

__all__ = [
    "AwaitingHumanReview",
    "Completed",
    "FailedUnrecoverable",
    "GateFailedRetryable",
    "LedgerStateKind",
    "NeedsPlan",
    "PatchApplied",
    "PlanReady",
    "SutDigest",
    "TransitionEvent",
    "TransitionId",
    "VulnLedgerState",
    "VulnRemediationCase",
    "VulnRemediationResult",
    "VulnRemediationSut",
]
