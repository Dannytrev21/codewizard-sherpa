"""``codegenie.probes`` — frozen probe contract surface (ADR-0007).

This package's public shape — :mod:`codegenie.probes.base` — is locked
byte-for-byte to ``docs/localv2.md §4`` and pinned by
``tests/unit/test_probe_contract.py``. Adding new probes is *extension by
addition*; editing the contract requires the ADR-amendment workflow in
``templates/adr-amendment.md``.

Explicit imports — no ``importlib.metadata`` scan, no side-effecting
registration discovery. The registry (:mod:`codegenie.probes.registry`,
S2-05) collects probes via the ``@register_probe`` decorator at module
import time; concrete probe modules are imported by name below as Phase 1
stories land.
"""

from codegenie.probes import base, language_detection, node_build_system, registry
from codegenie.probes.registry import default_registry

__all__ = ["base", "default_registry", "language_detection", "node_build_system", "registry"]
