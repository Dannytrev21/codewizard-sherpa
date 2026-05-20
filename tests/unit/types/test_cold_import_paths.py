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

# Cold-start entry points — each, run first in a fresh interpreter, once
# tripped an import cycle. All are fixed by ADR-0013 Amendment 2026-05-20:
# the ``types/identifiers ↔ probes`` cycle (``PackageManager`` relocated to
# the kernel ``types`` package) and the ``depgraph.registry ↔ probes.base``
# cycle (``ProbeContext`` demoted to a TYPE_CHECKING forward-ref).
_COLD_IMPORT_ENTRY_POINTS = [
    "from codegenie.plugins.manifest import PluginManifest",
    "from codegenie.types.identifiers import PackageManager",
    "from codegenie.types import PackageManager",
    "from codegenie.transforms.outcomes import Trusted, Degraded, Unavailable",
    "from codegenie.adapters.confidence import AdapterConfidence",
    "import codegenie.depgraph.registry",
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
