"""Phase-3 ``Transform`` ABC and ``TransformProvenance`` payload — S1-04.

The ABC pattern mirrors :mod:`codegenie.probes.base` (``Probe(ABC)``): the
contract is declared as **class-level type annotations** on the abstract
class, and each concrete subclass defines those attributes as class variables
or per-instance state. There is no ``@property @abstractmethod`` —
mixing patterns was the V-D-F4 closure on the original story draft.

Phase 5's ``GateContext.transform_output: Transform`` and the
``isinstance(t, Transform)`` checks Phase 5 ADR-0006 commits to drive the
choice of ABC over Protocol. The asymmetry is documented:
``Plugin`` / ``RecipeEngine`` are Protocols; ``Transform`` is the lone ABC.

``TransformProvenance`` ships the seven fields named by
``phase-arch-design.md §Component design C4 (L800-806)`` — including the
load-bearing ``capability_use_id: EventId`` audit anchor ADR-0011 requires.
The Phase-3-Step-1 contract is frozen; any field rename or addition is a
Phase-3 ADR amendment that re-generates the S6-06 contract snapshot.

ADRs: ADR-0001 (ship Phase-5 contract surface), ADR-0010 (smart-constructor
discipline + ``frozen=True``/``extra="forbid"`` everywhere), ADR-0011
(Capability audit anchor; ``SandboxedPath`` framing).
"""

from __future__ import annotations

import re
from abc import ABC
from datetime import UTC, datetime
from typing import Final

from pydantic import BaseModel, ConfigDict, Field, field_validator

from codegenie.transforms._forward import SandboxedPath
from codegenie.types.identifiers import (
    EventId,
    PluginId,
    RecipeId,
    TransformId,
    TransformKind,
)

__all__ = ["Transform", "TransformProvenance"]


# ---------------------------------------------------------------------------
# Semver boundary regex — Phase-3-Step-1 string-only defence.
#
# Arch §Data model L803-L804 references a ``SemverVersion`` newtype, but
# S1-01's 14-name newtype catalog does not include it. Promoting to a real
# newtype is a Phase-3 ADR amendment that belongs to S1-01, not this story
# (scope discipline per ``Notes for the implementer``). The regex is the
# boundary defence in the meantime.
# ---------------------------------------------------------------------------

_SEMVER_RX: Final[re.Pattern[str]] = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][\w.-]+)?$")


# ---------------------------------------------------------------------------
# ``Transform`` ABC — class-level annotations only.
# ---------------------------------------------------------------------------


class Transform(ABC):
    """Abstract base class for every concrete transform shipped under
    ``codegenie.transforms``.

    Phase-3-time concrete subclasses (S5-02 ``NpmLockfileTransform``;
    S5-03 ``DockerfileBaseImageTransform``) declare the four contract
    attributes as class variables on the subclass. The ABC itself does not
    set defaults — that's intentional, because the attributes are the
    *output* of the recipe-engine call, not configuration.

    Minimal subclass example::

        class FakeTransform(Transform):
            transform_id: TransformId = TransformId("a" * 64)
            diff_bytes: bytes = b""
            files_changed: tuple[SandboxedPath, ...] = ()
            provenance: TransformProvenance = ...

    ``isinstance(t, Transform)`` works without any ``runtime_checkable``
    decorator — Phase 5's ``GateContext.transform_output: Transform`` field
    dispatches via the ABC.

    Extension-by-addition path: Phase 4's ``LLMProducedTransform(Transform)``
    and Phase 7's ``DistrolessImageTransform(Transform)`` subclass this
    surface without editing it. Adding an attribute to ``Transform`` itself
    requires a Phase-3 ADR amendment + S6-06 snapshot regeneration.
    """

    transform_id: TransformId
    diff_bytes: bytes
    files_changed: tuple[SandboxedPath, ...]
    provenance: TransformProvenance

    def __new__(cls, *args: object, **kwargs: object) -> Transform:
        # AC-8a — direct instantiation of the ABC is a contract break; AC-1
        # follows the ``Probe(ABC)`` precedent of class-level annotations
        # rather than ``@abstractmethod`` on each attribute, so the standard
        # ABCMeta block doesn't fire on its own. Subclasses pass through.
        if cls is Transform:
            raise TypeError(
                "Cannot instantiate abstract class Transform directly — "
                "subclass it and declare transform_id / diff_bytes / "
                "files_changed / provenance."
            )
        return super().__new__(cls)


# ---------------------------------------------------------------------------
# ``TransformProvenance`` Pydantic model — 7 fields per arch §C4 L800-L806.
# ---------------------------------------------------------------------------


class TransformProvenance(BaseModel):
    """Audit-anchor payload attached to every produced :class:`Transform`.

    The ``capability_use_id`` field is the load-bearing tie between this
    transform and the ``CapabilityUsed`` event in the S6-01 two-stream event
    log (ADR-0011 §Audit + lint). Omitting it weakens the Phase-9
    replay-consistency property; the V-B-F1 validation closure surfaced it
    as missing from the original story draft.

    Versions are ``str`` with a regex validator (semver boundary) because
    S1-01's newtype catalog does not yet include ``SemverVersion`` — see
    module docstring for the arch-drift note.

    ``applied_at`` is timezone-aware UTC. The default factory uses
    ``datetime.now(UTC)``; a ``field_validator`` rejects naive datetimes
    explicitly (a naive value would silently be read as UTC downstream).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    plugin_id: PluginId
    plugin_version: str
    recipe_id: RecipeId
    recipe_version: str
    transform_kind: TransformKind
    applied_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    capability_use_id: EventId

    @field_validator("plugin_version", "recipe_version")
    @classmethod
    def _semver_shape(cls, v: str) -> str:
        if not _SEMVER_RX.match(v):
            raise ValueError(
                f"version must match semver-shape regex "
                f"^[0-9]+\\.[0-9]+\\.[0-9]+(?:[-+][\\w.-]+)?$; got {v!r}"
            )
        return v

    @field_validator("applied_at")
    @classmethod
    def _utc_required(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("applied_at must be timezone-aware UTC; got naive datetime")
        offset = v.utcoffset()
        if offset is None or offset.total_seconds() != 0:
            # Non-UTC tz: normalize to UTC rather than silently accept and
            # let downstream readers misinterpret the wall-clock as UTC.
            v = v.astimezone(UTC)
        return v
