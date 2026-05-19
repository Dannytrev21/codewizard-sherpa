"""Regression: cold-process imports must not trip a circular import.

Before commit ``0ffbd07`` the chain

    plugins.manifest -> types.identifiers -> probes.node_build_system
                     -> probes.__init__   -> layer_b.dep_graph
                     -> depgraph.registry -> types.identifiers (mid-init)

raised ``ImportError: cannot import name 'PackageManager' from partially
initialized module 'codegenie.types.identifiers'``. The test suite never
caught it because pytest collection primes ``codegenie.probes.__init__``
before ``types.identifiers`` is first imported — the cycle only fires
when an outside-``probes`` module triggers ``types.identifiers`` cold.

Each entry point below runs in a fresh subprocess so the module cache
starts empty — the only way to exercise the real cold-start ordering.
Adding a future kernel-tier consumer that imports ``types.identifiers``
ahead of ``probes.*`` should extend this list, not silently re-introduce
the bug (Phase 3 ADR-0013).
"""

from __future__ import annotations

import subprocess
import sys

import pytest

# Entry points whose first transitive hop is ``codegenie.types.identifiers``.
# ``codegenie.depgraph.registry`` itself sits on a separate, pre-existing
# cycle through ``codegenie.probes.base`` (Phase 2 S1-10) and is out of
# scope here — flagged in Phase 3 ADR-0013 §Consequences for follow-up.
_COLD_IMPORT_ENTRY_POINTS = [
    "from codegenie.plugins.manifest import PluginManifest",
    "from codegenie.types.identifiers import PackageManager",
    "from codegenie.types import PackageManager",
    "from codegenie.transforms.outcomes import Trusted, Degraded, Unavailable",
    "from codegenie.adapters.confidence import AdapterConfidence",
]


@pytest.mark.parametrize("stmt", _COLD_IMPORT_ENTRY_POINTS)
def test_cold_import_succeeds(stmt: str) -> None:
    proc = subprocess.run(
        [sys.executable, "-c", stmt],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, (
        f"cold import failed: {stmt}\n--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
    )
