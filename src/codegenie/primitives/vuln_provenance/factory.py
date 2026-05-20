"""Phase 7 S2-02 — `AdapterFactory` Protocol + `DefaultAdapterFactory`.

Phase 7 ADR-0007 §Decision stores adapter **classes** in `_REGISTRY`
(S2-01); instance construction is deferred to dispatch time. This module
is that construction seam: `assemble_provenance` (S2-04) hands a registered
adapter class to an `AdapterFactory`, which inspects the class's `__init__`
signature and supplies a **closed, well-known set** of dependency-injection
kwargs.

The closed vocabulary is `_DI_KWARGS = {sbom_reader, logger,
image_manifest_cache}` (ADR-0007 §Decision; §Tradeoffs row 1 — the set is
load-bearing). An adapter that needs a dependency outside this set has
exactly two options: declare it as a well-known kwarg (which costs an
ADR-0007 amendment to the closed set) or accept the default factory's
empty-kwarg path. The factory NEVER passes a kwarg outside `_DI_KWARGS`,
even when an adapter declares a parameter with a matching name — the
closed vocabulary is the *iteration domain* of `__call__`, so a name
outside it is structurally unreachable, not merely filtered.

To grow the DI vocabulary: (1) propose an ADR-0007 amendment to the
closed set; (2) extend `_DI_KWARGS`; (3) extend
`DefaultAdapterFactory.__init__` and the `available` mapping in
`__call__`; (4) update this docstring; (5) update ADR-0007 §Consequences.

The three DI parameters are typed `object | None`: the factory is a pure
pass-through that never invokes a dependency, and the concrete reader /
cache / logger types are not yet pinned (S1-05 ships the SBOM models, not
a reader abstraction; the codebase logs via `structlog`, not stdlib
`logging`). `mypy --strict` enforces the real dependency types at each
adapter's own `__init__` (S3-02+), which is where they are consumed.

ADRs honored: Phase 7 ADR-0004 (primitive home), Phase 7 ADR-0007
(registry stores classes; the factory owns construction), production
ADR-0031 (Plugin/Registry), production ADR-0033 (the closed kwarg
vocabulary is enum-shaped domain modeling).
"""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Final, Protocol, runtime_checkable

if TYPE_CHECKING:
    from codegenie.primitives.vuln_provenance.protocols import VulnProvenanceAdapter


__all__ = [
    "AdapterFactory",
    "DefaultAdapterFactory",
    "default_adapter_factory",
]


_DI_KWARGS: Final[frozenset[str]] = frozenset({"sbom_reader", "logger", "image_manifest_cache"})
"""Closed dependency-injection kwarg vocabulary (ADR-0007 §Decision).

`DefaultAdapterFactory` passes ONLY these names, and ONLY when the adapter's
`__init__` declares them. Growing this set is an ADR-0007 amendment
(§Tradeoffs row 1) — never a silent edit."""


@runtime_checkable
class AdapterFactory(Protocol):
    """Construction seam for registered vuln-provenance adapter classes.

    `assemble_provenance` (S2-04) accepts an `adapter_factory:
    AdapterFactory | None` parameter; tests substitute a deterministic
    factory by shape alone. The Protocol is `@runtime_checkable` so that
    call site can `isinstance`-guard the injected factory.
    """

    def __call__(self, cls: type[VulnProvenanceAdapter], /) -> VulnProvenanceAdapter:
        """Construct an adapter instance from its registered class."""
        ...


class DefaultAdapterFactory:
    """The production `AdapterFactory`: inspect `__init__`, inject the
    closed DI vocabulary.

    Construction-time dependencies all default to `None`; production code
    builds an instance with real dependencies and injects it via
    `assemble_provenance(..., adapter_factory=...)`. The module-level
    `default_adapter_factory` (all-`None`) is the no-DI convenience
    instance for tests and genuinely dependency-free adapters.
    """

    def __init__(
        self,
        *,
        sbom_reader: object | None = None,
        logger: object | None = None,
        image_manifest_cache: object | None = None,
    ) -> None:
        self._sbom_reader = sbom_reader
        self._logger = logger
        self._image_manifest_cache = image_manifest_cache

    def __call__(self, cls: type[VulnProvenanceAdapter], /) -> VulnProvenanceAdapter:
        """Construct ``cls`` with the DI kwargs it declares.

        `inspect.signature` reports the adapter's `__init__` parameters; the
        comprehension iterates `_DI_KWARGS` (the closed vocabulary), so a
        parameter the adapter declares outside that set is never injected.
        """
        parameters = inspect.signature(cls.__init__).parameters
        available: dict[str, object | None] = {
            "sbom_reader": self._sbom_reader,
            "logger": self._logger,
            "image_manifest_cache": self._image_manifest_cache,
        }
        kwargs = {name: available[name] for name in _DI_KWARGS if name in parameters}
        return cls(**kwargs)


default_adapter_factory: Final[AdapterFactory] = DefaultAdapterFactory()
"""All-`None` DI convenience factory for tests and dependency-free adapters.

Production code constructs an explicit `DefaultAdapterFactory(sbom_reader=...,
logger=..., image_manifest_cache=...)` and injects it through
`assemble_provenance` (S2-04) — this singleton injects `None` for every
declared DI kwarg."""
