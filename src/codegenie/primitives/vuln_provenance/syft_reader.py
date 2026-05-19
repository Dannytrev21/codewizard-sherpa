"""Phase 7 S1-05 — Pydantic models for the upstream syft SBOM schema.

This module is the *one* Phase 7 exception to the ``extra="forbid"``
default. The upstream syft JSON schema evolves; making it strict would
break every real-world SBOM the moment Anchore ships a new field. Defense
moves to the consumer boundary: every adapter
(`NpmVulnProvenanceAdapter`, `AlpineVulnProvenanceAdapter`,
`DistroVulnProvenanceAdapter`, `sbom_verifier.py`) reads only the fields
listed in the module-level ``_KNOWN_*_FIELDS`` catalogs, enforced by
S4-04's AST-walk fence.

The module is intentionally types-only — no I/O, no logging, no sibling
imports. The fixture under ``tests/fixtures/syft/minimal_alpine.json``
exercises the round-trip path; future I/O surfaces (parse from disk,
parse from ``docker syft`` stdout) land in a separate module when a
consumer needs them.

ADRs:
- Phase 7 ADR-0004 — primitive home; this reader sits beside
  ``types.py``, ``protocols.py``, ``errors.py`` under the primitive.
- Phase 2 deliberate-decision carry-forward — ``extra="allow"`` is the
  single tolerated exception inside the Phase 7 primitive tree. The
  consumer-side fence (S4-04) is the matching guard.
- production ADR-0038 — names the three models + the load-bearing
  ``locations[].layerID`` field.

# TODO(future): richer parsing — `SyftSource`, `SyftDistro`,
# `descriptor: dict[str, Any]` — deferred until a first consumer needs
# them. Today's adapter set reads only `name`, `version`,
# `locations[].path`, `locations[].layerID`.
"""

from __future__ import annotations

from typing import Final

from pydantic import BaseModel, ConfigDict

# --- Known-field catalogs (S4-04 fence source of truth) ----------------------

_KNOWN_LOCATION_FIELDS: Final[frozenset[str]] = frozenset({"path", "layerID"})
"""Fields adapters may read on a `SyftLocation`. S4-04's AST-walk fence
asserts every adapter reads only members of this set; growing it is a
two-line change here + a one-line fence update."""

_KNOWN_ARTIFACT_FIELDS: Final[frozenset[str]] = frozenset({"name", "version", "locations"})
"""Fields adapters may read on a `SyftArtifact`. Same fence semantics as
``_KNOWN_LOCATION_FIELDS``."""


__all__ = ["SyftArtifact", "SyftLocation", "SyftSbom"]


class SyftLocation(BaseModel):
    """One file location inside a syft artifact.

    ``extra="allow"`` admits unknown upstream fields (``annotations``,
    ``accessPath``, …) silently; adapters read only ``path`` /
    ``layerID`` (the camelCase spelling is the upstream contract — do
    NOT alias to ``layer_id``).
    """

    model_config = ConfigDict(extra="allow")
    path: str
    layerID: str | None = None


class SyftArtifact(BaseModel):
    """One package recorded by syft.

    ``extra="allow"`` admits ``cpes``, ``purl``, ``licenses``, etc.
    Adapters read only ``name``, ``version``, ``locations``.
    """

    model_config = ConfigDict(extra="allow")
    name: str
    version: str
    locations: list[SyftLocation] = []


class SyftSbom(BaseModel):
    """Top-level syft SBOM document.

    ``extra="allow"`` admits ``schema``, ``descriptor``, ``source``,
    ``distro``, … — fields the current adapter set does not need.
    """

    model_config = ConfigDict(extra="allow")
    artifacts: list[SyftArtifact] = []
