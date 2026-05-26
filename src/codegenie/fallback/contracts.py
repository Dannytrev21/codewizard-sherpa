"""Phase-4 S6-01 — local stubs for Phase-3/Phase-5-owned contract types.

The FallbackTier story prose references three contract types
(:class:`CveAdvisory`, :class:`RecipeSelection`, :class:`RepoContext`)
that Phase-3 / Phase-5 are scheduled to ship but have not yet. To
unblock S6-01 + downstream S6-* / S7-* stories, this module defines
minimal Pydantic-v2 stubs that the FallbackTier composes against.

Stub discipline:

* **Phase-4-local.** Future Phase-5 contract types will replace these.
  An import-linter rule (added when Phase-5 ships) routes consumers
  to the canonical site; this module is the temporary bridge.
* **Frozen + ``extra="forbid"``.** Mirrors the rest of
  ``codegenie/fallback/`` config.
* **No methods.** Pure data containers; the FallbackTier
  collaborators consume them via field access only.

The story's other contract reference, ``RecipeApplication``, is
deliberately **not** stubbed here: the Phase-4 :data:`PlanOutcome`
discriminated union (S1-03) is the load-bearing return shape and is
the actual type ``FallbackTier.run`` returns.
"""

from __future__ import annotations

from typing import Final

from pydantic import BaseModel, ConfigDict

from codegenie.primitives.vuln_provenance.syft_reader import SyftSbom
from codegenie.types.identifiers import (
    CveId,
    ImageRef,
    PackageId,
    PackageManager,
)

__all__ = [
    "CveAdvisory",
    "RecipeSelection",
    "RepoContext",
]


_FROZEN_FORBID: Final[ConfigDict] = ConfigDict(frozen=True, extra="forbid")


class CveAdvisory(BaseModel):
    """Minimal CVE-advisory stub for FallbackTier composition.

    Carries the fields the FallbackTier passes to its collaborators:

    * ``cve_id``, ``affected_package``, ``image_ref``, ``sbom`` →
      :meth:`ProvenanceGate.classify`.
    * ``description`` → :meth:`PromptBuilder.build(cve_description=...)`.

    Phase-5 will ship the canonical 20+-field ``CveAdvisory``; this
    stub is the bridge until then.
    """

    model_config = _FROZEN_FORBID
    cve_id: CveId
    affected_package: PackageId
    description: str
    image_ref: ImageRef | None = None
    sbom: SyftSbom | None = None


class RecipeSelection(BaseModel):
    """Minimal recipe-selection stub.

    Identifies which Phase-3 recipe the orchestrator selected for this
    advisory (e.g., ``"npm_dep_bump"`` for an npm prototype-pollution
    CVE). The FallbackTier passes this through to the prompt-builder
    so the system prompt can name the recipe.
    """

    model_config = _FROZEN_FORBID
    recipe_name: str
    build_system: PackageManager


class RepoContext(BaseModel):
    """Minimal repo-context stub.

    ``repo_root`` is the directory the FallbackTier hands to
    :class:`PromptBuilder` for ``repo_readme`` discovery; future
    Phase-5 will widen to the full RepoContext envelope. ``readme``
    + ``transitive_dep_meta`` are pre-extracted by the orchestrator
    so the FallbackTier never reads files.
    """

    model_config = _FROZEN_FORBID
    repo_root: str
    readme: str = ""
    transitive_dep_meta: tuple[str, ...] = ()
