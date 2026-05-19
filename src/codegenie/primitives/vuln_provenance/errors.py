"""Phase 7 S1-04 — typed error hierarchy for the vuln-provenance primitive.

Three behavior-free marker classes rooted at the codegenie error tree:

- :class:`ProvenanceError` is the **catch base** for ``assemble_provenance``
  (S2-04). Any subclass raised inside an adapter's ``attribute()`` is
  caught and converted to ``Unknown(reason="adapter_error")``; every other
  exception propagates per global Rule 12 ("Fail loud").
- :class:`RegistryError` is raised at decoration time by S2-01's
  ``@register_provenance_adapter`` for a duplicate ``(Layer, Ecosystem)``
  key — hard fail at import time, mirroring
  :class:`codegenie.errors.FreshnessRegistryError`.
- :class:`AdapterError` is raised inside an adapter's ``attribute()`` for
  adapter-specific failures (e.g., SBOM layer attribution absent for a
  specific row). S2-04 catches it and converts to the closed
  ``Unknown(reason="adapter_error")`` taxonomy entry.

ADRs honored:

- Phase 7 ADR-0004 — primitive home; ``errors.py`` is named in
  §Consequences as one of the module names under
  ``primitives/vuln_provenance/``.
- Phase 7 ADR-0007 — `RegistryError` is the typed surface for duplicate
  registration; the registry stores classes, not instances, so the only
  registration-time failure mode is duplicate-key collision.
- Production ADR-0038 — the `VulnProvenanceAdapter` contract names
  `ProvenanceError` as the catch-shaped base.

The hierarchy is intentionally flat — three classes, all marker-only (no
``__init__``, no class state). Behavior on the exception (e.g., structured
``WarningId`` per Phase 1 ADR-0007) is composed by the catch site, not
embedded on the class.
"""

from __future__ import annotations

from codegenie.errors import CodegenieError

__all__ = [
    "AdapterError",
    "ProvenanceError",
    "RegistryError",
]


class ProvenanceError(CodegenieError):
    """Base for vulnerability-provenance errors. Caught by
    ``assemble_provenance`` (S2-04) and converted to
    ``Unknown(reason="adapter_error")``."""


class RegistryError(ProvenanceError):
    """Raised by ``@register_provenance_adapter`` (S2-01) on a duplicate
    ``(Layer, Ecosystem)`` key. Hard fail at import time so a silent
    shadow never lands in the registry."""


class AdapterError(ProvenanceError):
    """Raised inside a concrete adapter's ``attribute()`` (S3-02 npm,
    S4-02 alpine, S4-03 distroless) when adapter-specific resolution
    fails. Caught by ``assemble_provenance`` and converted to
    ``Unknown(reason="adapter_error")``."""
