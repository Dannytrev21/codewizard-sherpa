"""Phase 7 vuln-provenance type vocabulary — `_Frozen`, `DistroPackage`,
`UnknownReason`, `AdapterConfidence`, the seven-variant `Provenance`
discriminated union, and the `AppKind` / `BaseKind` nested-union aliases.

Every name + value here is verbatim from
`docs/phases/07-migration-task-class/phase-arch-design.md §Data model` and
production ADR-0038 §Contract.

S1-02 seeded the module with `_Frozen`, `AdapterConfidence`,
`UnknownReason`, `DistroPackage`. S1-03 lands the seven variants
(`AppDirect`, `AppTransitive`, `AppVendored`, `BaseImage`,
`RuntimeBundled`, `Both`, `Unknown`), the `AppKind` / `BaseKind`
discriminated-union aliases, and the final `Provenance` alias. S1-04 will
land the `VulnProvenanceAdapter` Protocol that consumes `Provenance` as
its return type.

The `Both` variant's recursion guard is the load-bearing correctness pin:
`Both.app_record: AppKind` and `Both.base_record: BaseKind` are themselves
discriminated unions over **non-`Both`, non-`Unknown` variants only**, so
`Both(Both(...), ...)` raises `ValidationError` at construction time, not
at some downstream `match` arm. The arch is explicit: "the type system
itself enforces the recursion guard, not a runtime check."

ADRs:
- Phase 7 ADR-0004 — primitive home (`src/codegenie/primitives/vuln_provenance/`).
- Phase 7 ADR-0006 — `match`/`assert_never` discipline. This module's
  shape makes the exhaustiveness check possible.
- production ADR-0033 — sum-type discipline: `UnknownReason` is a `Literal`
  union (closed set, JSON-round-trippable), not a `str`. `AdapterConfidence`
  is a string-valued `Enum` so adapters dump the value without `.value`
  lookups. Every variant is `frozen=True, extra="forbid"`.
- production ADR-0038 — names every type here; the shape below is the
  verbatim contract Phase 7 ships.

The module is intentionally pure: imports are restricted to
``{__future__, typing, enum, pathlib, pydantic,
codegenie.types.identifiers}`` and the fence at
`tests/unit/primitives/vuln_provenance/test_types_module_purity.py`
catches drift. The `codegenie.types.identifiers` import is the single
sibling-package dependency admitted by ADR-0004 — it carries the kernel-
tier newtypes (`ImageDigest`, `LayerDigest`, `RuntimeId`,
`DockerStageName`, `PackageId`) referenced by the variant shapes.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from codegenie.types.identifiers import (
    DockerStageName,
    ImageDigest,
    LayerDigest,
    PackageId,
    RuntimeId,
)

__all__ = [
    "AdapterConfidence",
    "AppDirect",
    "AppKind",
    "AppTransitive",
    "AppVendored",
    "BaseImage",
    "BaseKind",
    "Both",
    "DistroPackage",
    "Provenance",
    "RuntimeBundled",
    "Unknown",
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


# ---------------------------------------------------------------------------
# Seven-variant Provenance discriminated union (S1-03).
#
# Order matters: each `Both`-eligible variant must be declared before the
# `AppKind` / `BaseKind` aliases that reference it; `Both` itself is
# declared after the aliases. `Unknown` lives outside the `AppKind` /
# `BaseKind` aliases (arch §Component design §2): `Both` carries
# non-`Unknown` records — an `Unknown` app or base layer routes through
# `assemble_provenance`'s `(None, base)` / `(None, None)` arm instead
# (S2-04).
# ---------------------------------------------------------------------------


class AppDirect(_Frozen):
    """`AppDirect` — package appears as a direct dependency in the manifest
    (no parent in the resolution chain). Resolved by the NPM adapter
    (S3-02) when `chain` length is exactly 1; the chain-length-1 case
    collapses to this shape so `AppTransitive.chain` length ≥ 2 invariant
    holds (AC-8)."""

    kind: Literal["app_direct"] = "app_direct"
    manifest_path: Path
    package: PackageId
    confidence: AdapterConfidence


class AppTransitive(_Frozen):
    """`AppTransitive` — package appears as a transitive dependency, with
    `chain` carrying the resolution path from root to leaf. `chain` length
    ≥ 2 is enforced at the type level (`Field(min_length=2)`) — without
    this, an adapter could mis-classify a direct dep as
    ``AppTransitive(chain=(pkg,))``. The arch's NPM-adapter rule "chain
    length 1 → `AppDirect`; chain length > 1 → `AppTransitive`" is what
    this Field-level minimum pins."""

    kind: Literal["app_transitive"] = "app_transitive"
    manifest_path: Path
    package: PackageId
    chain: Annotated[tuple[PackageId, ...], Field(min_length=2)]
    confidence: AdapterConfidence


class AppVendored(_Frozen):
    """`AppVendored` — package is vendored into the application tree (a
    `vendor/` directory or equivalent), not declared in the manifest. The
    npm adapter emits this when it finds a copy whose path does not map to
    any manifest entry. `vendored_path` is the on-disk path to the
    vendored copy."""

    kind: Literal["app_vendored"] = "app_vendored"
    vendored_path: Path
    package: PackageId
    confidence: AdapterConfidence


class BaseImage(_Frozen):
    """`BaseImage` — the vulnerability lives in a package owned by the
    Dockerfile's base image (apk/dpkg row). `image_digest` is the
    digest of the base layer that contributes the package; `layer_digest`
    pins the specific layer (SyftSbom layer attribution, S1-05).

    `stage` is the BuildKit `AS <name>` for the stage that pulled this
    base — `None` for single-stage Dockerfiles. The arch deliberately
    keeps it optional rather than introducing a sentinel string.
    """

    kind: Literal["base_image"] = "base_image"
    image_digest: ImageDigest
    layer_digest: LayerDigest
    distro_pkg: DistroPackage
    stage: DockerStageName | None
    confidence: AdapterConfidence


class RuntimeBundled(_Frozen):
    """`RuntimeBundled` — the vulnerability lives in a package shipped
    inside a language-runtime image (e.g., `node20`, `python3-11`),
    bundled under `bundled_path`. Distinct from `BaseImage` because the
    runtime layer's package database may be language-specific (npm-in-
    runtime, pip-in-runtime) rather than the distro's apk/dpkg."""

    kind: Literal["runtime_bundled"] = "runtime_bundled"
    runtime: RuntimeId
    bundled_path: Path
    package: PackageId
    confidence: AdapterConfidence


AppKind = Annotated[
    AppDirect | AppTransitive | AppVendored,
    Field(discriminator="kind"),
]
"""App-layer discriminated union — variants the application owns. Used as
`Both.app_record`'s field type so the type system enforces "no `Both` and
no `Unknown` nested inside `Both`" at validation time."""

BaseKind = Annotated[
    BaseImage | RuntimeBundled,
    Field(discriminator="kind"),
]
"""Base-layer discriminated union — variants the base/runtime image owns.
Used as `Both.base_record`'s field type for the same recursion-guard
reason as `AppKind` above."""


class Both(_Frozen):
    """`Both` — the CVE is present in both the application layer and the
    base/runtime image. The type system rejects `Both(Both(...), ...)`
    and `Both(Unknown, ...)` at construction because `AppKind` /
    `BaseKind` are nested discriminated unions over non-`Both`,
    non-`Unknown` variants only — no runtime guard is needed.

    No `confidence` field on `Both` itself: the nested `app_record` and
    `base_record` carry their own (the arch is explicit about this).
    """

    kind: Literal["both"] = "both"
    app_record: AppKind
    base_record: BaseKind


class Unknown(_Frozen):
    """`Unknown` — adapter could not resolve provenance for this CVE.
    `reason` is a closed `Literal` union (the `UnknownReason` taxonomy)
    so every emission path is auditable. `details` is `dict[str, str]`
    (not `dict[str, Any]` — the no-`Any` fence S1-06 will plant catches
    the latter)."""

    kind: Literal["unknown"] = "unknown"
    reason: UnknownReason
    details: dict[str, str] | None = None


Provenance = Annotated[
    AppDirect | AppTransitive | AppVendored | BaseImage | RuntimeBundled | Both | Unknown,
    Field(discriminator="kind"),
]
"""The seven-variant `Provenance` discriminated union — production
ADR-0038 §Contract. Every Phase 7 adapter returns this; `assemble_provenance`
(S2-04) composes it; the event log nests it. Round-tripping via
`TypeAdapter(Provenance).validate_python(payload)` routes by the `kind`
discriminator to the right variant — adapters and callers MUST use the
outer alias for deserialization, not per-class `model_validate`, which
short-circuits the discriminator path."""
