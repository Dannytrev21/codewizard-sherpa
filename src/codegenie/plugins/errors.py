"""Typed failure markers for the Phase 3 plugin kernel.

Four exit-code-4 failure modes (Phase-3 ADR-0002 §Consequences):

- :class:`PluginAlreadyRegistered` — duplicate ``manifest.name`` at
  ``PluginRegistry.register`` time. Carries a typed ``.name: PluginId``
  attribute so the S2-03 loader and the exit-code-4 formatter can
  consume a structured field rather than parsing ``args[0]``. Message
  names both colliding ``module.qualname`` strings — mirrors
  ``codegenie.probes.registry``'s
  ``ProbeError`` collision message (``probes/registry.py:154-158``).
- :class:`PluginNotRegistered` — :meth:`PluginRegistry.get` miss. Carries
  the missing ``.name: PluginId`` as a typed attribute.
- :class:`PluginExtendsCycle` — raised by S2-04's resolver when the
  ``extends`` chain cycles. Placeholder here so the exception hierarchy
  lives in one file; the resolver wires it up.
- :class:`PluginRejected` — raised by S2-03's loader when the integrity
  check (``PLUGINS.lock`` mismatch) or import-time validation fails.
  Placeholder here for the same reason.

All four extend :class:`codegenie.errors.CodegenieError`. Each is a marker
+ a structured payload — no behavior, no logging, no I/O. The kernel
discipline ADR-0002 §Decision names.
"""

from __future__ import annotations

from codegenie.errors import CodegenieError
from codegenie.types.identifiers import PluginId

__all__ = [
    "PluginAlreadyRegistered",
    "PluginExtendsCycle",
    "PluginNotRegistered",
    "PluginRejected",
]


class PluginAlreadyRegistered(CodegenieError):
    """Raised by :meth:`PluginRegistry.register` when a plugin's
    ``manifest.name`` is already registered into the same registry.

    Carries a typed ``.name: PluginId`` attribute so consumers (the S2-03
    loader, the exit-code-4 formatter) read structured data. The message
    names both colliding ``module.qualname`` strings — an operator
    grepping a multi-plugin tree can locate both registrations from the
    message alone (precedent: ``probes/registry.py:154-158``).
    """

    name: PluginId

    def __init__(self, name: PluginId, existing: str, duplicate: str) -> None:
        self.name = name
        self.existing = existing
        self.duplicate = duplicate
        super().__init__(f"duplicate plugin name {name!r}: {existing} and {duplicate}")


class PluginNotRegistered(CodegenieError):
    """Raised by :meth:`PluginRegistry.get` when the requested name is
    not in the registry.

    Carries a typed ``.name: PluginId`` attribute (not just a stringified
    message) so the resolver in S2-04 and CLI formatters can match on a
    structured field.
    """

    name: PluginId

    def __init__(self, name: PluginId) -> None:
        self.name = name
        super().__init__(f"plugin {name!r} is not registered")


class PluginExtendsCycle(CodegenieError):
    """Raised by S2-04's resolver when the ``extends`` chain cycles.

    Placeholder declaration here so the Phase 3 plugin-error hierarchy
    lives in one file — S2-04 wires the raise site and adds the
    cycle-chain payload.
    """


class PluginRejected(CodegenieError):
    """Raised by S2-03's loader when integrity-check (``PLUGINS.lock``
    mismatch) or import-time validation fails.

    Placeholder declaration here for hierarchy locality — S2-03 wires the
    raise site and adds the rejection-reason payload.
    """
