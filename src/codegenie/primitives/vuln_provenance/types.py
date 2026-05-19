"""Phase 7 vuln-provenance type vocabulary — `_Frozen`, `DistroPackage`,
`UnknownReason`, `AdapterConfidence`.

This module seeds the seven-variant `Provenance` discriminated union that
S1-03 lands and the `VulnProvenanceAdapter` Protocol that S1-04 lands.
Every name + value here is verbatim from
`docs/phases/07-migration-task-class/phase-arch-design.md §Data model` and
production ADR-0038 §Contract.

S1-03 will additively grow this module with the seven variants (`AppDirect`,
`AppTransitive`, `AppVendored`, `BaseImage`, `RuntimeBundled`, `Both`,
`Unknown`) and the `AppKind` / `BaseKind` discriminated-union aliases. This
story (S1-02) does **not** ship `AppKind` / `BaseKind` — placeholder
sentinels would either raise `ImportError` at runtime or widen the static
surface to `Any` for the next story to undo (story §AC-5).

ADRs:
- Phase 7 ADR-0004 — primitive home (`src/codegenie/primitives/vuln_provenance/`).
- production ADR-0033 — sum-type discipline: `UnknownReason` is a `Literal`
  union (closed set, JSON-round-trippable), not a `str`. `AdapterConfidence`
  is a string-valued `Enum` so adapters dump the value without `.value`
  lookups.
- production ADR-0038 — names every type here; the shape below is the
  verbatim contract Phase 7 ships.

The module is intentionally pure: imports are restricted to
``{__future__, typing, enum, pydantic}`` and the fence at
`tests/unit/primitives/vuln_provenance/test_types_module_purity.py`
catches drift.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

__all__ = [
    "AdapterConfidence",
    "DistroPackage",
    "UnknownReason",
]


# ---------------------------------------------------------------------------
# Shared frozen base — new to Phase 7. Locks `frozen=True, extra="forbid"`
# behind one inheritance hook so the AC-11 AST-walk fence
# (`tests/fence/test_vuln_provenance_frozen_base.py`) can prove every
# Pydantic record under `primitives/vuln_provenance/` inherits it. Phase 3's
# `transforms/outcomes.py` inline `ConfigDict(...)` style is grandfathered;
# the fence scope is this subpackage only.
# ---------------------------------------------------------------------------


class _Frozen(BaseModel):
    """Frozen, extra-forbidding Pydantic base for every supporting record in
    this module."""

    model_config = ConfigDict(frozen=True, extra="forbid")


# ---------------------------------------------------------------------------
# AdapterConfidence — production ADR-0038 §Contract.
# ---------------------------------------------------------------------------


class AdapterConfidence(StrEnum):
    """Three-valued confidence an adapter reports for its resolved
    provenance.

    `StrEnum` (Python 3.11+) is the codebase precedent
    (`transforms/sandbox/_seccomp.py`) and is the modernised form of the
    story-spec'd `(str, Enum)` shape — identical semantics: members satisfy
    ``isinstance(m, str)``, round-trip JSON via their string value, and
    compare equal to the literal string. Adapters dump the value into the
    `Provenance` JSON shape without a `.value` lookup.
    """

    HIGH = "high"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


# ---------------------------------------------------------------------------
# UnknownReason — closed Literal union (production ADR-0033).
# ---------------------------------------------------------------------------


UnknownReason = Literal[
    "sbom_layer_attribution_absent",
    "no_adapter_resolved",
    "adapter_error",
    "base_image_already_distroless",
    "build_failed",
    "dockerfile_parse_failed",
]
"""Closed reason taxonomy for the `Unknown` variant of `Provenance` (S1-03).

Each value maps to a row in `phase-arch-design.md §Edge cases`; adding a new
reason is an ADR-0004 amendment, not a free edit. The exhaustiveness anchor
lives at `tests/unit/primitives/vuln_provenance/test_types_phase7.py`
(`_describe` + `assert_never`)."""


# ---------------------------------------------------------------------------
# DistroPackage — package-database row inside `BaseImage` / `RuntimeBundled`.
# ---------------------------------------------------------------------------


class DistroPackage(_Frozen):
    """A package row attributed to a distro's package database.

    `name` + `version` are stored separately (not a synthetic `name@version`
    `PackageId`) because the arch keeps base-image package coordinates
    decoupled from npm/PyPI-style `PackageId` newtypes — adapters consume
    distro package databases (apk, dpkg) whose native shape is three
    separate fields.

    The closed `distro` set mirrors the four base-image distros Phase 7
    targets. Widening the set is an ADR-0004 amendment.
    """

    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    distro: Literal["alpine", "debian", "ubuntu", "rhel"]

    @field_validator("name", "version")
    @classmethod
    def _reject_whitespace_contamination(cls, value: str) -> str:
        """Reject whitespace-only and leading/trailing-whitespace input.

        `Field(min_length=1)` alone admits ``" "`` (length 1), which would
        let an adapter index `(distro, name, version)` with a contaminated
        key — silent downstream-poisoning since two records that differ only
        in leading whitespace would mis-hash. The strip-equality check
        rejects every variant: empty after strip OR strip-changed-the-value
        (leading / trailing whitespace) both fail.
        """
        if value != value.strip() or value == "":
            raise ValueError("must be non-empty and free of leading/trailing whitespace")
        return value
