"""Test-only import-order fix for the ``tests/fence/`` collection.

``codegenie.transforms`` (imported by ``test_transforms_module_purity``) →
``codegenie.types.identifiers`` re-exports ``PackageManager`` from
``codegenie.probes.node_build_system`` →  ``codegenie.probes.__init__``
loads ``layer_b.dep_graph`` →  ``codegenie.depgraph.registry`` re-imports
``PackageManager`` from ``codegenie.types.identifiers`` while the latter is
still partially initialized. In the full ``pytest`` collection some other
test indirectly imports ``codegenie.depgraph`` first and breaks the cycle;
running ``pytest tests/fence/`` in isolation does not.

Eagerly importing ``codegenie.depgraph`` here makes the cycle resolve in
the expected order so AC-9 (``pytest tests/fence/`` exits 0 with no
collection errors) holds. The underlying re-export pattern is a Phase 1/2
shape that pre-dates this story; a proper fix would move the
``PackageManager`` Literal into a leaf module both sides import from
(tracked as a follow-up, NOT included in S1-05 per Rule 3).
"""

from __future__ import annotations

import codegenie.probes  # noqa: F401  # eager-import to break the cycle
