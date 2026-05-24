"""Phase-4 S2-01 — ``ProvenanceGate`` tier-0 short-circuit primitive.

ADR-0012 lifts production ADR-0038's ``vuln.provenance`` refuse-mode from
"implicit Phase-3 return path" to an **explicit tier-0 step** that runs
before any LLM tokens are spent, any RAG record is queried, or any recipe
is matched.

This module is the Phase-4 consumer of the production ADR-0038
``Provenance`` primitive (``codegenie.primitives.vuln_provenance``). It
does *not* fork that primitive. ``ProvenanceClassifier`` is a small
Phase-4 facade Protocol over already-extracted typed inputs — the gate's
dependency-inverted port. The actual hexagonal adapter port stays
``codegenie.primitives.vuln_provenance.VulnProvenanceAdapter``; S6-01
extracts ``CveId`` / ``PackageId`` / ``ImageRef`` / ``SyftSbom`` from the
advisory + repo context before calling this primitive.

The gate has **no spend surface**: it does not import or accept any
``BudgetToken``, ``LeafLlm``, ``PromptBuilder``, ``LlmInvocationGuard``,
or RAG retriever. ``tests/fence/test_provenance_gate_zero_spend_boundary.py``
AST-walks the imports and the method signature to make that invariant
load-bearing.

The named rule ``is_app_layer`` is the Specification pattern hook: S6-01
calls the same predicate when projecting any non-app-layer ``Provenance``
to ``Refused(PROVENANCE_NOT_APP_LAYER)``. Phase-7 widens the app-layer set
for distroless / base-image migrations by amending
``_APP_LAYER_PROVENANCE_KINDS`` and the table fixture — until that
amendment, only ``app_direct``, ``app_transitive``, ``app_vendored``, and
``both`` are actionable.

ADRs honored:

- Phase-4 ADR-0012 — explicit tier-0 gate; Specification-pattern fit.
- Phase-4 ADR-0003 — path-scoped fence admits ``src/codegenie/fallback/``.
- Production ADR-0038 — seven-variant ``Provenance`` discriminated union
  and refuse-mode semantics.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final, Protocol, runtime_checkable

from codegenie.plugins.events import EventLog, ProvenanceClassified
from codegenie.primitives.vuln_provenance import (
    Provenance,
    ProvenanceError,
    SyftSbom,
    Unknown,
)
from codegenie.types.identifiers import CveId, EventId, ImageRef, PackageId

__all__ = [
    "_APP_LAYER_PROVENANCE_KINDS",
    "ProvenanceClassifier",
    "ProvenanceGate",
    "is_app_layer",
]


_APP_LAYER_PROVENANCE_KINDS: Final[frozenset[str]] = frozenset(
    {"app_direct", "app_transitive", "app_vendored", "both"}
)
"""Closed lower-case set of ``Provenance.kind`` values Phase-4 treats as
application-owned. ``base_image`` and ``runtime_bundled`` are the work of
Phase-7's distroless / base-image adapters and require an ADR-0012
amendment to admit; ``unknown`` refuses before spend by design."""


@runtime_checkable
class ProvenanceClassifier(Protocol):
    """Phase-4 facade Protocol over ``assemble_provenance`` / plugin wiring.

    This is *not* a second adapter family. The hexagonal port stays
    ``codegenie.primitives.vuln_provenance.VulnProvenanceAdapter`` — this
    Protocol is the dependency-inverted seam the gate consumes after
    S6-01 has already pulled the typed inputs out of the advisory + repo
    context.
    """

    def classify(
        self,
        cve_id: CveId,
        package_id: PackageId,
        image_ref: ImageRef | None,
        sbom: SyftSbom,
    ) -> Provenance:
        """Return the provenance the classifier resolved, or raise
        :class:`~codegenie.primitives.vuln_provenance.ProvenanceError`
        (the gate folds it to ``Unknown``)."""


def is_app_layer(provenance: Provenance) -> bool:
    """Specification-pattern predicate: ``True`` when the CVE is owned by
    the application layer and Phase-4 may proceed; ``False`` when the
    caller must project to ``Refused(PROVENANCE_NOT_APP_LAYER)``.

    Pure expression over ``provenance.kind`` — no isinstance walk, no
    runtime guard. The class-vs-discriminator mismatch is the load-bearing
    invariant: variant *classes* are ``AppDirect`` / ``BaseImage`` / …,
    but the runtime discriminator value is ``"app_direct"`` / ``"base_image"`` /
    … (production ADR-0033 lower-case sum-type discipline).
    """
    return provenance.kind in _APP_LAYER_PROVENANCE_KINDS


def _new_event_id() -> EventId:
    """Mint a deterministic-shape event identifier for one ``ProvenanceClassified``
    emission.

    Test assertions only require that *some* event exists; the exact id is
    intentionally not pinned so the helper stays a private implementation
    detail (the ULID-like ``01HPRV`` prefix is operator-friendly grep bait).
    """
    return EventId("01HPRV" + uuid.uuid4().hex[:20].upper())


@dataclass(frozen=True, slots=True)
class ProvenanceGate:
    """Tier-0 short-circuit: classify provenance, emit one typed event, return.

    Holds no state beyond its two collaborators. No cache, no retry
    policy, no RAG query, no leaf call, no budget token. Adapter-domain
    failures (``ProvenanceError`` and its ``AdapterError`` subclass) fold
    to ``Unknown(reason="adapter_error")`` so the caller's downstream
    sum-type dispatch stays exhaustive; every other exception propagates
    per global Rule 12.
    """

    classifier: ProvenanceClassifier
    event_log: EventLog

    def classify(
        self,
        cve_id: CveId,
        package_id: PackageId,
        image_ref: ImageRef | None,
        sbom: SyftSbom,
    ) -> Provenance:
        """Delegate once, fold ``ProvenanceError`` to ``Unknown``, emit one
        ``ProvenanceClassified`` event, return the resolved provenance."""
        try:
            result: Provenance = self.classifier.classify(cve_id, package_id, image_ref, sbom)
            adapter_error: str | None = None
        except ProvenanceError as exc:
            message = str(exc)
            result = Unknown(reason="adapter_error", details={"error": message})
            adapter_error = message

        # `EventLog._stamp` overwrites this with the log's injected clock
        # before the bytes hit disk — the placeholder satisfies the typed
        # `timestamp: datetime` field at construction time without dragging
        # a clock dependency into the gate.
        self.event_log.emit_internal(
            ProvenanceClassified(
                event_id=_new_event_id(),
                workflow_id=self.event_log.workflow_id,
                timestamp=datetime.now(UTC),
                provenance_kind=result.kind,
                adapter_error=adapter_error,
            )
        )
        return result
