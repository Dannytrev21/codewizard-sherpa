"""Phase 7 S2-01 — `Layer` + `Ecosystem` enums + ``_REGISTRY`` +
``@register_provenance_adapter`` decorator.

This module is the **kernel** of the ``vuln.provenance`` primitive's adapter
seam (Phase 7 ADR-0004, ADR-0006, ADR-0007; production ADR-0031 / ADR-0038).

Plugin/Registry pattern (the fifth instance of the decorator-registry family
in this codebase — the prior four are
:mod:`codegenie.probes.registry`, :mod:`codegenie.indices.registry`,
:mod:`codegenie.depgraph.registry`, and :mod:`codegenie.plugins.registry`).
Rule-of-three observation: the four prior sites diverge non-trivially in
their dispatch shape (``for_task`` filter + LRU / ``dispatch_all`` total /
single-``dispatch`` with ``has_strategy`` query / ``register_plugin`` function
call). Per Phase 7 ADR-0007 + global Rule 2 ("Simplicity First") + Rule 3
("Surgical Changes"), no kernel-extract is prescribed here; the deferral is
recorded as an N≥5 cleanup candidate for a future story.

Decisions pinned by this module's tests:

- **Stores CLASSES, not instances** (Phase 7 ADR-0007 §Decision; closes
  critic BP-3 in ``../phase-arch-design.md``). Construction is dispatch-time
  and DI-aware via S2-02's ``AdapterFactory``.
- **Duplicate ``(Layer, Ecosystem)`` raises ``RegistryError`` at decoration
  time** (ADR-0007 §Consequences). Hard fail at import time so a silent
  shadow never lands; plugin loader (S8-03) reads ``exc.key`` for a
  structured diagnostic.
- **No ordering** (Phase 7 ADR-0006). ``_REGISTRY`` is a plain dict;
  dispatch policy lives in ``_ADAPTER_DISPATCH_ORDER`` (S2-03) and the
  ``Ecosystem``-enum-sort iteration in ``assemble_provenance`` (S2-04).
- **No ``isinstance`` runtime contract guard** (ADR-0007 §Tradeoffs row 4).
  ``Protocol.__runtime_checkable__`` verifies method *names* only; the
  signature gate is ``mypy --strict`` at the registration site.
- **No ``unregister_for_tests``** on the public surface (contrast with
  :mod:`codegenie.indices.registry`). Production registration is the
  ``api.py`` import-line in Phase 3+ plugins; tests use the autouse
  snapshot/restore fixture in
  ``tests/unit/primitives/vuln_provenance/conftest.py``.
"""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum
from typing import TYPE_CHECKING, Final

from codegenie.primitives.vuln_provenance.errors import RegistryError

if TYPE_CHECKING:
    from codegenie.primitives.vuln_provenance.protocols import VulnProvenanceAdapter
    from codegenie.types.identifiers import ProvenanceAdapterId


__all__ = [
    "Ecosystem",
    "Layer",
    "register_provenance_adapter",
]


class Layer(StrEnum):
    """Vulnerability-attribution layer. Declaration order is load-bearing —
    S2-03's ``_ADAPTER_DISPATCH_ORDER`` tuple iterates ``APP → BASE_IMAGE →
    RUNTIME`` in that order. Adding a value is an ADR amendment."""

    APP = "app"
    BASE_IMAGE = "base_image"
    RUNTIME = "runtime"


class Ecosystem(StrEnum):
    """Package/distro ecosystem. Declaration order is load-bearing — S2-03
    iterates intra-layer adapters in this order (``tuple(Ecosystem)``).
    Adding a value is an ADR amendment (arch §4)."""

    NPM = "npm"
    YARN_BERRY = "yarn-berry"
    PNPM = "pnpm"
    APK = "apk"
    DPKG = "dpkg"
    RPM = "rpm"


_REGISTRY: Final[dict[ProvenanceAdapterId, type[VulnProvenanceAdapter]]] = {}
"""Module-level registry mapping ``(Layer, Ecosystem)`` → adapter **class**.

Module-private (leading underscore). Tests reach it via the module path;
production consumers go through ``assemble_provenance`` (S2-04). Test
isolation is handled by the autouse fixture in
``tests/unit/primitives/vuln_provenance/conftest.py`` (Phase 7 ADR-0007
§Consequences)."""


def register_provenance_adapter(
    *, layer: Layer, ecosystem: Ecosystem
) -> Callable[[type[VulnProvenanceAdapter]], type[VulnProvenanceAdapter]]:
    """Decorator that registers an adapter **class** under ``(layer, ecosystem)``.

    The decorator does exactly three things: collision-check the key, assign
    the class (NOT an instance) into ``_REGISTRY``, and return the class
    unchanged. Adding logging, structural validation, or signature inspection
    here would defeat S2-02's ``AdapterFactory`` (DI-aware dispatch) and
    ``mypy --strict`` (signature gate).

    Duplicate ``(layer, ecosystem)`` raises :class:`RegistryError` at
    decoration time — i.e. plugin import. The exception's ``.key`` payload
    carries the colliding pair and the message names both colliding
    ``module.qualname`` strings so the operator can locate both registrations
    from the message alone (mirrors :mod:`codegenie.probes.registry`).
    """

    def _wrap(
        cls: type[VulnProvenanceAdapter],
    ) -> type[VulnProvenanceAdapter]:
        key: ProvenanceAdapterId = (layer, ecosystem)
        if key in _REGISTRY:
            existing = _REGISTRY[key]
            raise RegistryError.duplicate(
                key=key,
                existing_qualname=f"{existing.__module__}.{existing.__qualname__}",
                duplicate_qualname=f"{cls.__module__}.{cls.__qualname__}",
            )
        # CLASS, NOT cls() — see ADR-0007 §Decision; BP-3 regression guard.
        _REGISTRY[key] = cls
        return cls

    return _wrap
