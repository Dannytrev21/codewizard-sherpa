"""ADR-0015 repo dependency loading and CVE resolution helpers.

The orchestrator keeps its frozen ``run(repo, cve, context=None)`` surface by
deriving the dependency set from the repo path. This module is intentionally
narrow: it validates that the context artifact exists, reads npm dependency
names from ``package.json``, and provides a pure resolver from
``VulnerabilityRecord`` rows to the one record that affects the repo.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from codegenie.output.paths import yaml_path
from codegenie.result import Err, Ok, Result
from codegenie.types.identifiers import Ecosystem, PackageName
from codegenie.vuln_index.models import VulnerabilityRecord

__all__ = [
    "CveAffectsMultiple",
    "CveAffectsRepo",
    "CveNotInRepo",
    "CveResolution",
    "InstalledDependency",
    "RepoContextLoadError",
    "RepoContextMissing",
    "RepoContextNoDependencies",
    "RepoContextSchemaInvalid",
    "RepoContextUnreadable",
    "load_installed_dependencies",
    "resolve_cve",
]


class InstalledDependency(BaseModel):
    """One dependency observed in the target repo."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    package: PackageName
    ecosystem: Ecosystem


class RepoContextMissing(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["missing"] = "missing"
    path: str


class RepoContextUnreadable(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["unreadable"] = "unreadable"
    path: str
    message: str


class RepoContextSchemaInvalid(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["schema_invalid"] = "schema_invalid"
    message: str


class RepoContextNoDependencies(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["no_dependencies"] = "no_dependencies"


RepoContextLoadError = Annotated[
    RepoContextMissing
    | RepoContextUnreadable
    | RepoContextSchemaInvalid
    | RepoContextNoDependencies,
    Field(discriminator="kind"),
]


class CveAffectsRepo(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["affects_repo"] = "affects_repo"
    record: VulnerabilityRecord


class CveNotInRepo(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["not_in_repo"] = "not_in_repo"


class CveAffectsMultiple(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["affects_multiple"] = "affects_multiple"
    records: tuple[VulnerabilityRecord, ...]


CveResolution = Annotated[
    CveAffectsRepo | CveNotInRepo | CveAffectsMultiple,
    Field(discriminator="kind"),
]


def load_installed_dependencies(
    repo_root: Path,
) -> Result[tuple[InstalledDependency, ...], RepoContextLoadError]:
    """Load npm dependency names for ``repo_root`` after requiring context output.

    ADR-0015 deliberately avoids a full ``RepoContext`` model. Today the
    human-facing context artifact records node-manifest counts, not names, so
    the narrow loader treats the artifact as the freshness/ingress gate and
    reads dependency names from the repo's ``package.json``.
    """
    context_path = yaml_path(repo_root)
    if not context_path.exists():
        return Err(error=RepoContextMissing(path=str(context_path)))

    package_json = repo_root / "package.json"
    try:
        raw = package_json.read_text(encoding="utf-8")
    except OSError as exc:
        return Err(error=RepoContextUnreadable(path=str(package_json), message=str(exc)))

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return Err(error=RepoContextSchemaInvalid(message=str(exc)))
    if not isinstance(data, dict):
        return Err(error=RepoContextSchemaInvalid(message="package.json root must be an object"))

    names: set[str] = set()
    for key in ("dependencies", "devDependencies", "optionalDependencies", "bundledDependencies"):
        value = data.get(key, {})
        if isinstance(value, dict):
            names.update(k for k in value if isinstance(k, str) and k)
        elif isinstance(value, list):
            names.update(k for k in value if isinstance(k, str) and k)
        elif value not in (None, {}):
            return Err(error=RepoContextSchemaInvalid(message=f"{key} must be object or list"))

    if not names:
        return Err(error=RepoContextNoDependencies())

    deps = tuple(
        InstalledDependency(package=PackageName(name), ecosystem="npm") for name in sorted(names)
    )
    return Ok(value=deps)


def resolve_cve(
    records: list[VulnerabilityRecord] | tuple[VulnerabilityRecord, ...],
    deps: tuple[InstalledDependency, ...],
) -> CveResolution:
    """Intersect CVE records with repo dependencies.

    Zero matches means the target repo cannot be remediated for this CVE.
    One match proceeds. More than one is an honest human-review case because
    Phase 3's day-1 npm remediation is scoped to a single dependency row.
    """
    dep_keys = {(dep.ecosystem, dep.package) for dep in deps}
    matches = tuple(
        sorted(
            (record for record in records if (record.ecosystem, record.package) in dep_keys),
            key=lambda record: (str(record.package), record.ecosystem, str(record.cve_id)),
        )
    )
    if not matches:
        return CveNotInRepo()
    if len(matches) == 1:
        return CveAffectsRepo(record=matches[0])
    return CveAffectsMultiple(records=matches)
