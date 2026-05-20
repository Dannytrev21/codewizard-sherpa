"""Phase 7 S1-04 — `VulnProvenanceAdapter` Protocol (hexagonal port).

The Protocol is the **port** in the Port + Adapter pattern: every concrete
vuln-provenance adapter (S3-02 npm, S4-02 alpine, S4-03 distroless)
implements this duck-typed contract and the
``@register_provenance_adapter`` decorator (S2-01) stores classes typed as
``type[VulnProvenanceAdapter]``. ``assemble_provenance`` (S2-04) dispatches
through a factory (S2-02) that instantiates the class then calls
``attribute(...)``.

The Protocol shape is verbatim from
``docs/phases/07-migration-task-class/phase-arch-design.md §Component design``
and is intentionally minimal:

- **Exactly two methods** — ``attribute`` and ``confidence``. The arch and
  Phase 7 ADR-0007 explicitly reject ``cost_band`` / ``applies_when``
  fields (critic Perf-5: those concerns belong on the factory / dispatch
  policy, not on the kernel Protocol).
- **Structurally a `typing.Protocol`, NOT an `abc.ABC`** (Phase 7 ADR-0007).
  Adapters implement the contract by shape; the kernel never inherits.
- **No ``__init__`` enumeration** — DI happens at dispatch time via S2-02's
  ``AdapterFactory``, which inspects the adapter's ``__init__`` signature
  and supplies a closed set of well-known kwargs
  (``sbom_reader``, ``logger``, ``image_manifest_cache``). Adding a Protocol
  ``__init__`` here would force every adapter to share the same kwargs and
  defeat the factory's role.
- **``@runtime_checkable``** — admits ``isinstance(obj, VulnProvenanceAdapter)``
  duck-type checks. Python's ``runtime_checkable`` checks **method names
  only** (not signatures); signature mismatches surface at call time as
  typed errors. ``mypy --strict`` at the registration site is the gate
  for the signatures.
- **`sbom: SyftSbom`** — the real S1-05 Pydantic model, imported under
  ``TYPE_CHECKING`` (annotation-only). The runtime annotation stays the
  bare string ``"SyftSbom"`` (via ``from __future__ import annotations``);
  ``typing.get_type_hints(...)`` resolves it to the concrete model.

ADRs honored: Phase 7 ADR-0004 (module home), Phase 7 ADR-0007 (registry
stores classes; Protocol is the duck-typed contract, not an ABC),
production ADR-0032 (Adapter-Protocol shape precedent), production
ADR-0038 (the contract this Protocol names).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from codegenie.primitives.vuln_provenance.types import AdapterConfidence, Provenance
from codegenie.types.identifiers import CveId, ImageRef, PackageId

if TYPE_CHECKING:
    # S1-05 shipped the real `SyftSbom` Pydantic model; S2-04 — the first
    # `attribute(...)` caller (`assemble_provenance`) — swaps the former
    # placeholder for the concrete import so `mypy --strict` resolves the
    # `sbom` parameter to the real type. The import stays `TYPE_CHECKING`-
    # guarded (annotation-only): the runtime annotation is still the bare
    # string ``"SyftSbom"`` (PEP 563 via ``from __future__ import
    # annotations``), so the AC-6 forward-reference test is unchanged.
    from codegenie.primitives.vuln_provenance.syft_reader import SyftSbom


__all__ = ["VulnProvenanceAdapter"]


@runtime_checkable
class VulnProvenanceAdapter(Protocol):
    """Hexagonal port for a vulnerability-provenance adapter.

    Adapters are registered as classes (Phase 7 ADR-0007); the
    ``@runtime_checkable`` decorator admits ``isinstance(obj, _)`` duck-type
    checks but verifies method names only, not signatures —
    ``mypy --strict`` is the gate for the signature shape.
    """

    def attribute(
        self,
        cve_id: CveId,
        package_id: PackageId,
        image_ref: ImageRef | None,
        sbom: SyftSbom,
    ) -> Provenance:
        """Attribute ``(cve_id, package_id)`` to a `Provenance` variant.

        Adapters consult their layer-specific evidence (app manifest, distro
        package database, SBOM layer attribution) and return one of the
        seven `Provenance` variants. Adapter-specific failures must raise
        :class:`codegenie.primitives.vuln_provenance.errors.AdapterError`
        so ``assemble_provenance`` (S2-04) converts them to
        ``Unknown(reason="adapter_error")``.
        """
        ...

    def confidence(self) -> AdapterConfidence:
        """The adapter's static confidence band — `HIGH`, `DEGRADED`, or
        `UNAVAILABLE`. Per-call confidence rides on the returned
        `Provenance` variant's own ``confidence`` field; this method
        reports the **adapter-class-level** confidence used by the
        dispatch tie-breaker (S2-03)."""
        ...
