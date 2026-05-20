"""Phase-3 S5-01b — :class:`TransformRegistry`, the channel by which a
:class:`~codegenie.transforms.recipe_engine.RecipeEngine` surfaces its
produced :class:`~codegenie.transforms.transform.Transform` to the
orchestrator.

ADR-0014 decides this. ``RecipeEngine.apply`` stays ``-> RecipeOutcome``
(the ADR-0001 / ADR-0009 frozen surface, untouched); an engine is
constructor-injected with a :class:`TransformRegistry`, calls
:meth:`TransformRegistry.register` on a successful apply, and returns
``Applied(transform_id=...)``. The :class:`RemediationOrchestrator`
(S6-04) — which created the registry — looks the object back up via
:meth:`TransformRegistry.get` using the ``Applied.transform_id`` it
received from ``apply``.

**Per-workflow, not a process-wide singleton.** Unlike ``@register_probe``
/ ``@register_recipe`` (import-time registration into a ``default_*``
singleton), :class:`~codegenie.transforms.transform.Transform` objects
register at *runtime* — once per ``apply`` call. The orchestrator creates
one :class:`TransformRegistry` per workflow ``run()`` and discards it
afterwards; there is deliberately no module-level instance and no
``default_transform_registry``. This module is an internal orchestration
mechanism — NOT one of ADR-0001's six Phase-5 contract symbols, and NOT
re-exported from :mod:`codegenie.transforms` (imported directly, like
:mod:`codegenie.transforms.sandbox_jail`).

The typed error markers mirror
:mod:`codegenie.plugins.recipe_registry`'s ``RecipeAlreadyRegistered`` /
``RecipeNotFound``: a :class:`~codegenie.errors.CodegenieError` subclass
carrying a typed ``.transform_id`` so callers match on a structured
field, not a parsed message.

ADRs honored: ADR-0014 (this module ships the decision), ADR-0010
(newtype ``TransformId`` key, typed error markers).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from codegenie.errors import CodegenieError
from codegenie.types.identifiers import TransformId

if TYPE_CHECKING:
    from codegenie.transforms.transform import Transform


__all__ = [
    "TransformAlreadyRegistered",
    "TransformNotFound",
    "TransformRegistry",
]


# --- Typed failure markers -------------------------------------------------


class TransformAlreadyRegistered(CodegenieError):
    """Raised by :meth:`TransformRegistry.register` when the
    ``transform_id`` is already registered.

    Carries a typed ``.transform_id: TransformId`` so callers match on a
    structured field. The message names both colliding
    ``module.qualname`` origin strings, mirroring
    :class:`codegenie.plugins.recipe_registry.RecipeAlreadyRegistered`.
    A duplicate id within one workflow means a real bug (two distinct
    diffs collided on a BLAKE3 digest, or a double-register) — per Rule
    12 it surfaces loud rather than silently overwriting.
    """

    transform_id: TransformId

    def __init__(self, transform_id: TransformId, existing: str, duplicate: str) -> None:
        self.transform_id = transform_id
        self.existing = existing
        self.duplicate = duplicate
        super().__init__(f"duplicate transform_id {transform_id!r}: {existing} and {duplicate}")


class TransformNotFound(CodegenieError):
    """Raised by :meth:`TransformRegistry.get` when the requested
    ``transform_id`` is not registered. Carries a typed ``.transform_id``
    attribute.
    """

    transform_id: TransformId

    def __init__(self, transform_id: TransformId) -> None:
        self.transform_id = transform_id
        super().__init__(f"transform {transform_id!r} is not registered")


# --- Registry --------------------------------------------------------------


class TransformRegistry:
    """Per-workflow, in-memory store of produced
    :class:`~codegenie.transforms.transform.Transform` objects keyed by
    :data:`~codegenie.types.identifiers.TransformId`.

    A :class:`~codegenie.transforms.recipe_engine.RecipeEngine` is
    constructor-injected with one instance and :meth:`register`s the
    :class:`Transform` it produces on a successful apply. The
    :class:`RemediationOrchestrator` (S6-04) — which created the
    instance — :meth:`get`s the object back by the ``Applied.transform_id``
    it received from ``apply``.

    Lifetime is one workflow run: the orchestrator constructs a fresh
    registry per ``run()`` and discards it afterwards. There is no
    eviction, no size cap, and no ``default_*`` singleton (ADR-0014) —
    the registry holds at most a handful of transforms and never
    outlives the workflow that owns it.
    """

    def __init__(self) -> None:
        self._transforms: dict[TransformId, Transform] = {}
        # Origin strings ("module.qualname") for duplicate-collision
        # messages — mirrors RecipeRegistry._origins.
        self._origins: dict[TransformId, str] = {}

    def register(self, transform: Transform) -> Transform:
        """Register ``transform`` under its ``transform_id``.

        Raises :class:`TransformAlreadyRegistered` (typed
        ``.transform_id``) if the id is already registered — registration
        is strict, never an overwrite. Returns ``transform`` unchanged so
        :func:`register_recipe`-style register-and-return call sites stay
        one expression.
        """
        tid = transform.transform_id
        new_origin = f"{type(transform).__module__}.{type(transform).__qualname__}"
        if tid in self._transforms:
            raise TransformAlreadyRegistered(tid, self._origins[tid], new_origin)
        self._transforms[tid] = transform
        self._origins[tid] = new_origin
        return transform

    def get(self, transform_id: TransformId) -> Transform:
        """Return the :class:`Transform` registered under ``transform_id``.

        Raises :class:`TransformNotFound` (typed ``.transform_id``) on a
        miss — no :class:`KeyError` ever escapes the registry.
        """
        try:
            return self._transforms[transform_id]
        except KeyError:
            raise TransformNotFound(transform_id) from None

    def __contains__(self, transform_id: object) -> bool:
        """``transform_id in registry`` — ``True`` iff a transform is
        registered under that id. Accepts any object (Python's ``in``
        protocol contract) and never raises."""
        return transform_id in self._transforms

    def __len__(self) -> int:
        """Number of registered transforms."""
        return len(self._transforms)
