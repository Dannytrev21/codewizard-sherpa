"""S6-02 — the open ``SignalKind`` registry the trust scorer dispatches against.

Phase 3 registers five signal kinds at import time (``build``, ``install``,
``tests``, ``lockfile_policy``, ``cve_delta``). Phase 5 widens the set with
``trace`` / ``policy`` (`05-ADR-0003`), Phase 7 with ``baseimage`` /
``shell_presence`` — each addition is one :func:`register_signal_kind` call in
a new module, never an edit to :class:`~codegenie.transforms.trust_scorer.TrustScorer`.
This is the Open/Closed seam ADR-0010 §Decision 3 names.

``register_signal_kind`` is a **function call**, NOT a class decorator — it
mirrors :func:`codegenie.plugins.registry.register_plugin`'s shape, not
``@register_probe``'s. A ``SignalKind`` is a bare name string, so the
registration is a value-producing call (``BUILD = register_signal_kind("build")``)
rather than a class annotation.

**Rule-of-three observation — now five registries.** This is the **5th**
register-helper-backed registry in the codebase
(:mod:`codegenie.probes.registry`, :mod:`codegenie.indices.registry`,
:mod:`codegenie.depgraph.registry`, :mod:`codegenie.plugins.registry`, this
module). ``plugins/registry.py:39-49`` pins the kernel-extract trigger at
"N=5 **OR** a registry needing only the common surface". N=5 now fires — but
the four prior registries each carry divergent dispatch machinery
(``for_task`` + LRU; ``dispatch_all``; ``has_strategy``; ``resolve`` +
extends-walk) while :class:`SignalKindRegistry` is the *smallest* surface
(``register`` + ``__contains__`` + ``fresh`` — no dispatch at all). Extracting
a shared ``KernelRegistry[K, V]`` base would couple this minimal registry to
four heavyweight ones for negligible LOC saving. **Defer** — following the
precedent set in ``indices/registry.py:26-31`` and ``depgraph/registry.py``.
The 6th registry's author has a clean five-precedent grep trail.
"""

from __future__ import annotations

import inspect
from typing import Final

from codegenie.errors import CodegenieError
from codegenie.types.identifiers import SignalKind

__all__ = [
    "BUILD",
    "CVE_DELTA",
    "INSTALL",
    "LOCKFILE_POLICY",
    "TESTS",
    "SignalKindAlreadyRegistered",
    "SignalKindRegistry",
    "register_signal_kind",
    "signal_kind_registry",
]


class SignalKindAlreadyRegistered(CodegenieError):
    """Raised by :meth:`SignalKindRegistry.register` when ``name`` collides.

    Carries a typed ``.name: SignalKind`` plus the ``.existing`` /
    ``.duplicate`` ``module.qualname`` origin strings of both registration
    call sites — an operator grepping a multi-plugin tree can locate both
    from the message alone. Mirrors
    :class:`codegenie.plugins.errors.PluginAlreadyRegistered`.

    This is a *configuration* error (two modules registered the same name at
    import time) — categorically distinct from
    :class:`~codegenie.transforms.trust_scorer.UnregisteredSignalKind`, which
    is a *usage* error at ``score`` time. They are deliberately not unified
    under one base class.
    """

    name: SignalKind

    def __init__(self, name: SignalKind, existing: str, duplicate: str) -> None:
        self.name = name
        self.existing = existing
        self.duplicate = duplicate
        super().__init__(f"duplicate signal kind {name!r}: {existing} and {duplicate}")


class SignalKindRegistry:
    """Collision-checked collection of registered :class:`SignalKind` names.

    Production code registers into the module-level :data:`signal_kind_registry`
    singleton via :func:`register_signal_kind`; tests build independent
    instances with :meth:`fresh` so they never pollute each other (the
    per-instance discipline ADR-0002 established for ``PluginRegistry``).
    """

    def __init__(self) -> None:
        # Maps each registered kind to the ``module.qualname`` origin of its
        # registration call — kept so a duplicate error can name both sites.
        self._origins: dict[SignalKind, str] = {}

    def register(self, name: str, *, origin: str) -> SignalKind:
        """Register ``name``; return it as a typed :class:`SignalKind`.

        Raises :class:`SignalKindAlreadyRegistered` (naming both colliding
        call sites) when ``name`` is already registered. There is no
        idempotent path — every duplicate raises, regardless of caller.
        """
        kind = SignalKind(name)
        if kind in self._origins:
            raise SignalKindAlreadyRegistered(kind, self._origins[kind], origin)
        self._origins[kind] = origin
        return kind

    def __contains__(self, kind: SignalKind) -> bool:
        """Return whether ``kind`` has been registered into this instance."""
        return kind in self._origins

    @classmethod
    def fresh(cls) -> SignalKindRegistry:
        """Return a new, empty registry — the per-test isolation constructor."""
        return cls()


signal_kind_registry: Final[SignalKindRegistry] = SignalKindRegistry()
"""Process-wide :class:`SignalKindRegistry` — the registry the scorer reads.

``Final`` is intentional: a new signal kind is added by a
:func:`register_signal_kind` call in a new module, never by replacing this
singleton. Tests pass fresh instances through ``register_signal_kind(name,
registry=...)`` instead.
"""


def register_signal_kind(
    name: str,
    *,
    registry: SignalKindRegistry | None = None,
) -> SignalKind:
    """Register ``name`` into ``registry`` (or :data:`signal_kind_registry`).

    A function call, not a class decorator (see the module docstring). The
    caller's ``module.qualname`` is introspected so the duplicate-collision
    error can name both registration sites without the caller passing an
    explicit ``origin``.
    """
    frame = inspect.currentframe()
    caller = frame.f_back if frame is not None else None
    if caller is not None:
        origin = f"{caller.f_globals.get('__name__', '?')}.{caller.f_code.co_qualname}"
    else:  # pragma: no cover — CPython always supplies a caller frame
        origin = "<unknown>"
    return (registry if registry is not None else signal_kind_registry).register(
        name, origin=origin
    )


# --- Phase 3 signal kinds — registered at import time ------------------------
# These five module-level calls ARE the registration mechanism: importing this
# module populates ``signal_kind_registry``. ``transforms/__init__.py`` imports
# this module so every ``from codegenie.transforms import ...`` consumer sees a
# populated registry (AC-12).

BUILD = register_signal_kind("build")
INSTALL = register_signal_kind("install")
TESTS = register_signal_kind("tests")
LOCKFILE_POLICY = register_signal_kind("lockfile_policy")
CVE_DELTA = register_signal_kind("cve_delta")
