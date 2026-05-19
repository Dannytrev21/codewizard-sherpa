"""``PluginManifest`` — frozen Pydantic schema for ``plugin.yaml`` + ``from_yaml``
loader returning :class:`codegenie.result.Result`.

Phase-3 S2-02. The model is the canonical single-source-of-truth for the
``plugin.yaml`` shape pinned by production ADR-0031 §Plugin manifest. Every
submodel ships with ``model_config = ConfigDict(frozen=True, extra="forbid")``
so a typo in a manifest field (``precedance:`` for ``precedence:``) surfaces
as a typed :class:`SchemaViolation` at load time, never as silently-ignored
config.

The :meth:`PluginManifest.from_yaml` classmethod is the **only** I/O entry
point — it routes every read through
:func:`codegenie.parsers.safe_yaml.load`, the Phase 1 ADR-0009 chokepoint
that closes alias-amplification, billion-laughs, symlink-TOCTOU, and
non-mapping-top-level. **Never** raises for any documented failure mode;
returns ``Err(...)`` carrying one of four tagged-union variants:

- :class:`SizeCapExceeded` — input larger than the 1 MiB cap (the
  ``safe_yaml`` chokepoint short-circuits on ``os.fstat`` before any bytes
  are decoded; the variant carries ``actual_bytes`` from a guarded re-stat).
- :class:`MalformedYaml` — empty file, ``yaml.YAMLError`` (any subclass),
  top-level non-mapping (list / scalar / ``null``), depth-cap exceeded.
- :class:`SchemaViolation` — Pydantic ``ValidationError`` (unknown fields,
  wrong types, ``parse_plugin_id`` lift failure on ``name`` / ``extends``).
  ``field_errors`` is rendered from ``ve.errors()[*]['loc']`` — the stable
  Pydantic v2 ``ErrorDetails['loc']`` API; if Pydantic 3 lands, update
  :func:`_render_field_errors` and fix the failing tests rather than
  relaxing them (Rule 12 — fail loud).
- :class:`IoError` — every ``OSError`` subclass (``FileNotFoundError``,
  ``PermissionError``, ``IsADirectoryError``, …) plus the
  :class:`codegenie.errors.SymlinkRefusedError` marker the
  ``O_NOFOLLOW`` open raises (translated to ``errno.ELOOP``).

The ``name`` and ``extends`` fields lift their raw ``str`` payloads through
:func:`codegenie.types.parsers.parse_plugin_id` (the S1-01 free-function
smart constructor) inside ``@field_validator(mode="after")`` blocks; a
lift failure raises ``ValueError`` which Pydantic wraps into the outer
``ValidationError`` that ``from_yaml`` translates to ``SchemaViolation``.
``NewType`` cannot host classmethods (S1-01 Notes §"Arch ↔ NewType API
drift") — the lift stays a free function.

Open/Closed: ``extra="forbid"`` is the intended schema-drift discipline
(ADR-0010 §Tradeoffs row 5). Adding a Phase 7 distroless
``contributes.containers`` field is an explicit, ADR-worthy edit to this
file; never flip to ``extra="allow"`` or add a ``dict[str, JSONValue]``
escape hatch.

Precedent citations:

- 1 MiB cap follows Phase 2 ``S2-02-conventions-catalog-loader.md`` (catalog
  YAML) and Phase 2 ``S1-04-tccm-model-loader.md`` (TCCM YAML).
- Tagged-union sum-type discipline follows ADR-0010 §Decision 3 —
  evidence per variant; impossible-by-construction via the ``kind``
  discriminator.
- The translation table mirrors :func:`codegenie.tccm.loader._classify`'s
  shape (different reason set; same prefix-pin discipline).
"""

from __future__ import annotations

import errno as _errno
from pathlib import Path
from typing import Annotated, Final, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    field_validator,
)

from codegenie.errors import (
    DepthCapExceeded,
    MalformedYAMLError,
)
from codegenie.errors import SizeCapExceeded as _SafeYamlSizeCap
from codegenie.errors import SymlinkRefusedError as _SafeYamlSymlinkRefused
from codegenie.parsers import safe_yaml
from codegenie.result import Err, Ok, Result
from codegenie.types.identifiers import PluginId, PrimitiveName, ProbeId
from codegenie.types.parsers import parse_plugin_id

__all__ = [
    "IoError",
    "ManifestContributes",
    "ManifestError",
    "ManifestRequirements",
    "ManifestScope",
    "MalformedYaml",
    "PluginManifest",
    "SchemaViolation",
    "SizeCapExceeded",
]

# 1 MiB cap matches Phase 2 conventions-catalog-loader + TCCM precedents
# (ADR-0010 §Smart constructor — boundary input is bounded before parse).
_MANIFEST_MAX_BYTES: Final[int] = 1 << 20


# --- ManifestError tagged union (ADR-0010 §Decision 3) ----------------------


class SizeCapExceeded(BaseModel):
    """``safe_yaml.load`` refused the file because ``os.fstat(fd).st_size``
    exceeded ``cap``. ``actual_bytes`` is re-read from ``path.stat`` *after*
    the refusal — the chokepoint never allocates past the cap."""

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    kind: Literal["size_cap_exceeded"] = "size_cap_exceeded"
    path: Path
    actual_bytes: int
    cap: int


class MalformedYaml(BaseModel):
    """``safe_yaml`` raised :class:`codegenie.errors.MalformedYAMLError` or
    :class:`codegenie.errors.DepthCapExceeded` — empty file, broken syntax,
    top-level non-mapping, or alias-amplified depth-cap-exceeded structure."""

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    kind: Literal["malformed_yaml"] = "malformed_yaml"
    path: Path
    message: str


class SchemaViolation(BaseModel):
    """Pydantic ``ValidationError``: unknown field (``extra="forbid"``),
    wrong type, or ``parse_plugin_id`` lift failure on ``name`` / ``extends``.
    ``field_errors`` is the dotted ``loc`` of every error in declaration
    order — derived from Pydantic v2's stable ``ErrorDetails['loc']``."""

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    kind: Literal["schema_violation"] = "schema_violation"
    path: Path
    field_errors: tuple[str, ...]


class IoError(BaseModel):
    """Every ``OSError`` subclass plus the ``SymlinkRefusedError`` marker the
    ``O_NOFOLLOW`` open raises (translated to ``errno.ELOOP``). Carries the
    OS errno so the CLI can render a meaningful exit-message."""

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    kind: Literal["io_error"] = "io_error"
    path: Path
    errno: int
    message: str


ManifestError = Annotated[
    SizeCapExceeded | MalformedYaml | SchemaViolation | IoError,
    Field(discriminator="kind"),
]


# --- Submodels --------------------------------------------------------------


class ManifestScope(BaseModel):
    """Raw scope shape as it appears in YAML — ``str`` or ``list[str]`` per
    axis. ``"*"`` is the wildcard literal carried verbatim; the sum-type lift
    to :class:`codegenie.plugins.scope.PluginScope` happens in S2-04's
    ``ResolvedManifest`` (per arch §C2 line 755 follow-up)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    task_class: str | list[str]
    languages: str | list[str]
    build_systems: str | list[str]


class ManifestContributes(BaseModel):
    """``contributes.*`` — paths/IDs the plugin contributes to the kernel.

    The ``adapters`` value strings (``module:Class``) are validated for
    *shape* by Pydantic (non-empty); the ``module:Class`` grammar parse is
    S2-04's resolver concern (per ADR-0002 §"keep the registry dumb").
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    adapters: dict[PrimitiveName, str] = Field(default_factory=dict)
    tccm: str = "./tccm.yaml"
    subgraph: str = "./subgraph/"
    skills: str = "./skills/"
    recipes: str = "./recipes/"
    probes: tuple[ProbeId, ...] = ()


class ManifestRequirements(BaseModel):
    """``requirements.*`` — external + optional CLI tools the plugin needs.

    Shape pinned to production ADR-0031 lines 102-106: ``external_tools``
    and ``optional`` only. New requirement classes (sandbox capabilities,
    grammar files) are an ADR amendment to ADR-0031, not a silent extension.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    external_tools: tuple[str, ...] = ()
    optional: tuple[str, ...] = ()


# --- Top-level model + loader ------------------------------------------------


class PluginManifest(BaseModel):
    """Frozen schema for ``plugin.yaml`` (production ADR-0031 §Plugin manifest).

    The four-arm ``from_yaml`` translation table is the user-visible
    contract; pin it here AND in the module docstring's prose table.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: PluginId
    version: Annotated[str, StringConstraints(min_length=1)]
    scope: ManifestScope
    extends: tuple[PluginId, ...] = ()
    # production-ADR-0031 default is 50 — arch §C2 line 756's "0" is wrong.
    precedence: int = 50
    contributes: ManifestContributes
    requirements: ManifestRequirements = Field(default_factory=ManifestRequirements)

    @field_validator("name", mode="after")
    @classmethod
    def _lift_name(cls, value: str) -> PluginId:
        """Smart-constructor lift via the S1-01 free function — never cast."""
        parsed = parse_plugin_id(value)
        if isinstance(parsed, Err):
            raise ValueError(parsed.error.message)
        return parsed.value

    @field_validator("extends", mode="after")
    @classmethod
    def _lift_extends(cls, value: tuple[str, ...]) -> tuple[PluginId, ...]:
        """Lift every entry through ``parse_plugin_id``; short-circuit on the
        first failure so the rendered ``field_errors`` names ``extends``."""
        lifted: list[PluginId] = []
        for i, item in enumerate(value):
            parsed = parse_plugin_id(item)
            if isinstance(parsed, Err):
                raise ValueError(f"extends[{i}]: {parsed.error.message}")
            lifted.append(parsed.value)
        return tuple(lifted)

    @classmethod
    def from_yaml(cls, path: Path) -> Result[PluginManifest, ManifestError]:
        """Load + validate a ``plugin.yaml``; never raises.

        Translation table — public contract, pin against Pydantic minor
        upgrades (Pydantic v2 ``ErrorDetails['loc']`` is the stable API):

        - :class:`codegenie.errors.SizeCapExceeded` (safe_yaml fstat refusal)
          → :class:`SizeCapExceeded` variant; ``actual_bytes`` via a guarded
          re-stat (failed re-stat falls through to :class:`IoError`).
        - :class:`codegenie.errors.SymlinkRefusedError` (``O_NOFOLLOW``) →
          :class:`IoError` with ``errno=ELOOP`` per ADR-0011 honest-framing.
        - :class:`codegenie.errors.MalformedYAMLError` or
          :class:`codegenie.errors.DepthCapExceeded` → :class:`MalformedYaml`
          (depth-cap is a structural YAML defence; surfacing it to operator
          as "malformed" matches Phase 4's fail-loud handling).
        - ``OSError`` (any subclass: ``FileNotFoundError``,
          ``PermissionError``, ``IsADirectoryError``, …) →
          :class:`IoError` with the original errno.
        - :class:`pydantic.ValidationError` → :class:`SchemaViolation` with
          ``field_errors`` rendered from ``ve.errors()[*]['loc']``.
        """
        try:
            data = safe_yaml.load(path, max_bytes=_MANIFEST_MAX_BYTES)
        except _SafeYamlSizeCap:
            actual_bytes = _restat_or_zero(path)
            cap_err: ManifestError = SizeCapExceeded(
                path=path, actual_bytes=actual_bytes, cap=_MANIFEST_MAX_BYTES
            )
            return Err(error=cap_err)
        except _SafeYamlSymlinkRefused:
            symlink_err: ManifestError = IoError(
                path=path, errno=_errno.ELOOP, message="symlink refused"
            )
            return Err(error=symlink_err)
        except (MalformedYAMLError, DepthCapExceeded) as exc:
            malformed_err: ManifestError = MalformedYaml(path=path, message=str(exc))
            return Err(error=malformed_err)
        except OSError as exc:
            io_err: ManifestError = IoError(path=path, errno=exc.errno or 0, message=str(exc))
            return Err(error=io_err)

        try:
            manifest = cls.model_validate(dict(data))
        except ValidationError as exc:
            schema_err: ManifestError = SchemaViolation(
                path=path, field_errors=_render_field_errors(exc)
            )
            return Err(error=schema_err)
        return Ok(value=manifest)


def _render_field_errors(ve: ValidationError) -> tuple[str, ...]:
    """Render ``ve.errors()[*]['loc']`` as dotted strings, declaration order.

    Pydantic v2 ``ErrorDetails['loc']`` is stable across minor versions; a
    Pydantic 3 upgrade that re-formats the structure must update this helper
    and the failing AC tests — do not relax the tests (Rule 12).
    """
    return tuple(".".join(str(p) for p in err["loc"]) for err in ve.errors())


def _restat_or_zero(path: Path) -> int:
    """Best-effort ``path.stat().st_size`` — used only to populate
    :class:`SizeCapExceeded.actual_bytes` after the chokepoint refused the
    file. A failed re-stat returns ``0`` rather than masking the original
    refusal with an IoError; the caller still gets the size-cap variant."""
    try:
        return path.stat().st_size
    except OSError:
        return 0
