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
    dep_graph,  # noqa: F401 — S4-05 registration
    generated_code,  # noqa: F401 — S4-06 registration
    index_health,  # noqa: F401 — S4-01 registration
    node_reflection,  # noqa: F401 — S4-06 registration
    scip_index,  # noqa: F401 — S4-03 registration
    semantic_index_meta,  # noqa: F401 — S4-06 registration
    tree_sitter_import_graph,  # noqa: F401 — S4-04 registration
)
from codegenie.probes.layer_c import (
    certificate,  # noqa: F401 — S5-03 registration
    dockerfile,  # noqa: F401 — S5-03 registration
    entrypoint,  # noqa: F401 — S5-03 registration
    runtime_trace,  # noqa: F401 — S5-02 registration
    shell_usage,  # noqa: F401 — S5-03 registration
)
from codegenie.probes.layer_d import (
    adrs,  # noqa: F401 — S6-03 registration
    conventions,  # noqa: F401 — S6-02 registration
    exceptions,  # noqa: F401 — S6-03 registration
    external_docs,  # noqa: F401 — S6-04 registration
    policy,  # noqa: F401 — S6-03 registration
    repo_config,  # noqa: F401 — S6-03 registration
    repo_notes,  # noqa: F401 — S6-03 registration
    skills_index,  # noqa: F401 — S6-01 registration
)
from codegenie.probes.layer_e import (
    ownership,  # noqa: F401 — S6-05 registration
    service_topology_stub,  # noqa: F401 — S6-05 registration
    slo_stub,  # noqa: F401 — S6-05 registration
)

__all__ = [
    "adrs",
    "base",
    "certificate",
    "ci",
    "conventions",
    "default_registry",
    "dep_graph",
    "deployment",
    "dockerfile",
    "entrypoint",
    "exceptions",
    "external_docs",
    "generated_code",
    "index_health",
    "language_detection",
    "node_build_system",
    "node_manifest",
    "node_reflection",
    "ownership",
    "policy",
    "registry",
    "repo_config",
    "repo_notes",
    "runtime_trace",
    "scip_index",
    "semantic_index_meta",
    "service_topology_stub",
    "shell_usage",
    "skills_index",
    "slo_stub",
    "test_inventory",
    "tree_sitter_import_graph",
]

# Imported here so the public-import expression in the loader stays additive.
from codegenie.probes.registry import default_registry  # noqa: E402 — see above
