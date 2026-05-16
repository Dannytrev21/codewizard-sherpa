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

from codegenie.probes import (
    base,
    ci,
    deployment,
    language_detection,
    node_build_system,
    node_manifest,
    registry,
    test_inventory,
)
from codegenie.probes.layer_b import (
    index_health,  # noqa: F401 — S4-01 registration
    scip_index,  # noqa: F401 — S4-03 registration
)

__all__ = [
    "base",
    "ci",
    "default_registry",
    "deployment",
    "index_health",
    "language_detection",
    "node_build_system",
    "node_manifest",
    "registry",
    "scip_index",
    "test_inventory",
]

# Imported here so the public-import expression in the loader stays additive.
from codegenie.probes.registry import default_registry  # noqa: E402 — see above
