"""Phase 3 S5-04 — codegenie-owned lockfile-registry policy (Gap 2 fix).

Closes Gap 2 from ``docs/phases/03-vuln-deterministic-recipe/phase-arch-design.md``:
the ``lockfile_policy`` ``TrustSignal`` named a policy but never pinned where it
lives or what shape it takes. This module is the answer.

* :class:`LockfilePolicy` — a frozen Pydantic model carrying the single Phase-3
  rule, ``allowed_registries``.
* :meth:`LockfilePolicy.from_yaml` — the smart constructor (ADR-0010). Returns
  ``Result[LockfilePolicy, PolicyLoadError]``; :data:`PolicyLoadError` is a
  *module-local* discriminated union with one variant per failure mode. The
  canonical fixed-shape :class:`codegenie.types.errors.ParseError` is **not**
  extended — that would fork a kernel type (Rule 7). The shape mirrors the
  ``SkillsLoadError`` precedent in :mod:`codegenie.skills.loader`.
* :meth:`LockfilePolicy.evaluate` — the pure functional core. Walks an npm-v3
  ``package-lock.json`` ``packages`` map and returns the
  :data:`PolicyViolation` list. No I/O — pinned by an AST-walk fence
  (``tests/fence/test_lockfile_policy_evaluate_is_pure.py``).

Ownership: the policy file is **codegenie-owned**. :data:`LOCKFILE_POLICY_PATH`
resolves the wheel-shipped in-package copy via ``importlib.resources`` — never
cwd-relative — so an analyzed repo can never substitute its own allow-list.
``tools/policy/lockfile-policy.yaml`` at the repo root is a human-review mirror
kept byte-equal by a unit test.

YAML parsing deliberately uses ``yaml.safe_load`` directly rather than the
:mod:`codegenie.parsers.safe_yaml` chokepoint: the input is codegenie-owned
and trusted (not hostile analyzed-repo content), and the chokepoint translates
every ``yaml.YAMLError`` into a stateless marker exception, which would destroy
the ``problem_mark`` line/column data :class:`PolicyYamlSyntax` carries.

Phase boundary: this is an in-process one-rule evaluator. Phase 13's ADR-0021
may swap it for a real policy engine (OPA/Rego). The stable contract is
``evaluate(lockfile_doc) -> list[PolicyViolation]`` — keep it stable.

ADRs: phase-3 ADR-0010 (domain-modeling discipline — newtypes, smart
constructor, discriminated unions), ADR-0001 (``TrustSignal`` surface),
ADR-0011 (no ``Any`` in the contract layer).
"""

from __future__ import annotations

from collections.abc import Mapping
from importlib.resources import as_file, files
from pathlib import Path
from typing import Annotated, Final, Literal
from urllib.parse import urlparse

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from codegenie.result import Err, Ok, Result
from codegenie.types.identifiers import RegistryUrl
from codegenie.types.parsers import parse_registry_url

__all__ = [
    "LOCKFILE_POLICY_PATH",
    "LockfilePolicy",
    "PolicyEmptyAllowlist",
    "PolicyFileMissing",
    "PolicyInvalidRegistryUrl",
    "PolicyLoadError",
    "PolicySchemaViolation",
    "PolicyUnknownSchemaVersion",
    "PolicyViolation",
    "PolicyYamlSyntax",
    "UnauthorizedRegistry",
]

# Phase 3 supports schema v1 only. A forward version is refused cleanly
# (``PolicyUnknownSchemaVersion``); Phase 7 widens this tuple when v2 lands.
_SUPPORTED_SCHEMA_VERSIONS: Final[tuple[int, ...]] = (1,)


def _resolve_policy_path() -> Path:
    """Resolve the wheel-shipped in-package policy YAML to a real ``Path``.

    Uses ``importlib.resources`` so the path is correct under both editable
    (``pip install -e .``) and wheel installs — never cwd-relative.
    """
    resource = files("codegenie.transforms.policy") / "lockfile-policy.yaml"
    with as_file(resource) as path:
        return path.resolve()


# Codegenie-owned, wheel-shipped (Phase 3 Gap 2 fix; ADR-0010). Never cwd-relative.
LOCKFILE_POLICY_PATH: Final[Path] = _resolve_policy_path()


# --- PolicyViolation discriminated union -----------------------------------
#
# One arm today. Phase 7 widens this union by adding new variants
# (``UnpinnedDigest``, ``RegistryRedirect``) in a NEW module and re-pointing the
# alias there — ``lockfile_policy.py`` itself is not edited. The
# ``Field(discriminator="kind")`` shape is the Open/Closed seam that keeps that
# extension additive.


class UnauthorizedRegistry(BaseModel):
    """A lockfile entry resolved against a registry not on the allow-list."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["unauthorized_registry"] = "unauthorized_registry"
    registry: RegistryUrl
    package: str


PolicyViolation = Annotated[UnauthorizedRegistry, Field(discriminator="kind")]


# --- PolicyLoadError discriminated union -----------------------------------
#
# Module-local, one variant per failure mode — mirrors the ``SkillsLoadError``
# precedent at ``codegenie.skills.loader``. NOT the canonical ``ParseError``
# (a fixed-shape kernel type; extending it would fork a shared home — Rule 7).


class PolicyFileMissing(BaseModel):
    """The policy path does not exist or is not a regular file."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    reason: Literal["file_missing"] = "file_missing"
    path: Path


class PolicyYamlSyntax(BaseModel):
    """The file is not well-formed YAML; ``line``/``col`` are 0-indexed."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    reason: Literal["yaml_syntax"] = "yaml_syntax"
    path: Path
    line: int
    col: int
    detail: str


class PolicySchemaViolation(BaseModel):
    """The YAML parsed but failed Pydantic validation; ``errors`` is ``ve.errors()``."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    reason: Literal["schema_violation"] = "schema_violation"
    path: Path
    errors: list[dict[str, object]]


class PolicyUnknownSchemaVersion(BaseModel):
    """``schema_version`` is an integer this Phase does not support."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    reason: Literal["unknown_schema_version"] = "unknown_schema_version"
    path: Path
    observed: int
    supported: tuple[int, ...]


class PolicyEmptyAllowlist(BaseModel):
    """``allowed_registries`` is empty — that would deny every install."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    reason: Literal["empty_allowlist"] = "empty_allowlist"
    path: Path


class PolicyInvalidRegistryUrl(BaseModel):
    """An allow-list entry is not a strict-``https://`` trailing-slash URL."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    reason: Literal["invalid_registry_url"] = "invalid_registry_url"
    path: Path
    url: str
    detail: str


PolicyLoadError = Annotated[
    PolicyFileMissing
    | PolicyYamlSyntax
    | PolicySchemaViolation
    | PolicyUnknownSchemaVersion
    | PolicyEmptyAllowlist
    | PolicyInvalidRegistryUrl,
    Field(discriminator="reason"),
]


class LockfilePolicy(BaseModel):
    """Codegenie-owned npm-registry allow-list. Frozen; built via ``from_yaml``."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1]
    # Tuple — frozen, hashable (required by ``frozen=True``), deterministic.
    allowed_registries: tuple[RegistryUrl, ...]

    @classmethod
    def from_yaml(cls, path: Path) -> Result[LockfilePolicy, PolicyLoadError]:
        """Load + validate a policy YAML. Smart constructor (ADR-0010).

        Validation order is pinned: ``is_file`` → ``yaml.safe_load`` →
        ``schema_version`` early-exit → Pydantic validate → empty-allowlist →
        per-URL parse. The first failing step wins.
        """
        if not path.is_file():
            return Err(error=PolicyFileMissing(path=path))
        text = path.read_text(encoding="utf-8")
        try:
            data: object = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            # `problem_mark` is present on MarkedYAMLError subclasses (scanner/
            # parser errors); absent on a bare YAMLError — getattr defaults to 0.
            mark = getattr(exc, "problem_mark", None)
            return Err(
                error=PolicyYamlSyntax(
                    path=path,
                    line=getattr(mark, "line", 0),
                    col=getattr(mark, "column", 0),
                    detail=str(exc),
                )
            )
        # schema_version early-exit: a forward version gets a discriminator-stable
        # error *before* Pydantic's ``Literal[1]`` would emit a schema_violation —
        # a v2-aware caller must be able to tell the two apart.
        observed = data.get("schema_version") if isinstance(data, Mapping) else None
        if (
            isinstance(observed, int)
            and not isinstance(observed, bool)
            and observed not in _SUPPORTED_SCHEMA_VERSIONS
        ):
            return Err(
                error=PolicyUnknownSchemaVersion(
                    path=path,
                    observed=observed,
                    supported=_SUPPORTED_SCHEMA_VERSIONS,
                )
            )
        try:
            policy = cls.model_validate(data)
        except ValidationError as exc:
            return Err(
                error=PolicySchemaViolation(path=path, errors=[dict(e) for e in exc.errors()])
            )
        if not policy.allowed_registries:
            return Err(error=PolicyEmptyAllowlist(path=path))
        for url in policy.allowed_registries:
            parsed = parse_registry_url(url)
            if isinstance(parsed, Err):
                return Err(
                    error=PolicyInvalidRegistryUrl(path=path, url=url, detail=parsed.error.message)
                )
            # ``parse_registry_url`` accepts a missing trailing slash; the policy
            # file requires it for a canonical, unambiguous origin. (S1-01
            # follow-up: ``parse_registry_url`` itself could be tightened.)
            if not url.endswith("/"):
                return Err(
                    error=PolicyInvalidRegistryUrl(
                        path=path,
                        url=url,
                        detail="RegistryUrl: must end with a trailing '/'",
                    )
                )
        return Ok(value=policy)

    def evaluate(self, lockfile_doc: Mapping[str, object]) -> list[PolicyViolation]:
        """Return every lockfile entry resolved against a non-allow-listed registry.

        Pure function — no I/O, no clock (fence-pinned). Walks the npm-v3
        ``packages`` map; an entry whose ``resolved`` origin
        (``scheme://netloc/``) is not on the allow-list is a violation. Host
        matching is strict scheme+netloc equality: a port, userinfo, or scheme
        difference is a host mismatch (defence-in-depth — no normalisation).
        """
        allowed_origins = {
            f"{urlparse(r).scheme}://{urlparse(r).netloc}/" for r in self.allowed_registries
        }
        violations: list[PolicyViolation] = []
        packages = lockfile_doc.get("packages")
        if not isinstance(packages, Mapping):
            return violations
        for pkg_path, entry in packages.items():
            if not isinstance(entry, Mapping):
                continue
            resolved = entry.get("resolved")
            if not isinstance(resolved, str):
                continue
            parsed = urlparse(resolved)
            origin = f"{parsed.scheme}://{parsed.netloc}/"
            if origin not in allowed_origins:
                violations.append(
                    UnauthorizedRegistry(
                        registry=RegistryUrl(origin),
                        package=str(pkg_path),
                    )
                )
        return sorted(violations, key=lambda v: (v.package, v.registry))
